"""MtgSage Streamlit demo: conversational agent and knowledge indexing."""

from dataclasses import dataclass

import streamlit as st

from app.agents.agent import MtgSageAgent
from app.agents.conversation import ConversationStore
from app.agents.tools import AgentTools
from app.cards.api_client import MagicApiClient
from app.jobs.indexing import IndexJobManager, IndexJobSnapshot
from app.llm.gemini_client import GeminiClient
from app.logger import configure_logging, get_logger
from app.semantic.embedder import OllamaEmbedder
from app.semantic.vector_store import ChromaVectorStore


logger = get_logger("app.mtg_sage")


@dataclass
class ChatResources:
    """Process-wide shared clients; session history is NOT stored here."""

    store: ChromaVectorStore
    embedder: OllamaEmbedder
    cards: MagicApiClient
    llm: GeminiClient
    tools: AgentTools


@st.cache_resource(show_spinner=False)
def job_manager() -> IndexJobManager:
    return IndexJobManager()


@st.cache_resource(show_spinner=False, max_entries=2)
def chat_resources(revision: int) -> ChatResources:
    """A new index revision gets a new Chroma collection handle."""
    store = ChromaVectorStore()
    embedder = OllamaEmbedder()
    cards = MagicApiClient()
    llm = GeminiClient()
    tools = AgentTools(embedder=embedder, store=store, cards=cards)
    return ChatResources(store, embedder, cards, llm, tools)


@st.cache_data(show_spinner=False, ttl=10)
def stored_count(revision: int) -> int:
    """Only called while no index job is writing to Chroma."""
    return ChromaVectorStore().count()


def format_duration(seconds: float | None) -> str:
    if seconds is None:
        return "Calculando…"
    seconds = max(0, round(seconds))
    hours, remaining = divmod(seconds, 3600)
    minutes, seconds = divmod(remaining, 60)
    if hours:
        return f"{hours} h {minutes} min"
    if minutes:
        return f"{minutes} min {seconds} s"
    return f"{seconds} s"


def init_conversation() -> None:
    if "conversations" not in st.session_state:
        conversations = ConversationStore()
        st.session_state.conversations = conversations
        st.session_state.session_id = conversations.create_session()
        st.session_state.messages = []
        st.session_state.agent = None
        st.session_state.agent_revision = -1


def get_agent(revision: int) -> MtgSageAgent:
    if (
        st.session_state.agent is None
        or st.session_state.agent_revision != revision
    ):
        resources = chat_resources(revision)
        st.session_state.agent = MtgSageAgent(
            llm=resources.llm,
            tools=resources.tools,
            conversations=st.session_state.conversations,
        )
        st.session_state.agent_revision = revision
    return st.session_state.agent


def render_evidence(message: dict) -> None:
    sources = message.get("sources", ())
    tools = message.get("tools_used", ())
    if not sources and not tools:
        return

    with st.expander("Cómo se obtuvo esta respuesta", expanded=False):
        if tools:
            st.caption("Herramientas utilizadas: " + ", ".join(tools))
        if message.get("model_calls") is not None:
            st.caption(
                f"Consultas al modelo: {message['model_calls']} · "
                f"Llamadas a herramientas: {message['tool_calls']}"
            )
        if sources:
            st.markdown("**Fuentes realmente consultadas**")
            for source in sources:
                page = f" · página {source.page}" if source.page else ""
                st.markdown(
                    f"- `{source.reference}` — {source.title}{page} "
                    f"({source.source})"
                )
        else:
            st.info("No se recuperaron referencias externas en este turno.")
        st.caption(
            "Estas referencias acreditan consultas a las fuentes; "
            "no garantizan automáticamente la exactitud de cada afirmación."
        )


def render_chat(manager: IndexJobManager) -> None:
    st.header("Chat de MtgSage")
    init_conversation()
    snapshot = manager.snapshot()
    if snapshot.status == "running":
        st.info("Indexación en curso. El chat se reanudará al terminar.")
        available = False
    else:
        try:
            indexed = stored_count(snapshot.revision)
        except Exception:
            logger.exception("Unable to inspect the knowledge index")
            st.error("No se ha podido abrir el índice de reglas.")
            indexed = 0
        st.caption(f"Documentos actualmente indexados: {indexed}")
        available = indexed > 0
        if not available:
            st.warning("Indexa algunos documentos antes de iniciar el chat.")

    if st.button("Nueva conversación", disabled=snapshot.status == "running"):
        conversations = st.session_state.conversations
        conversations.delete_session(st.session_state.session_id)
        st.session_state.session_id = conversations.create_session()
        st.session_state.messages = []
        st.rerun()

    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
            if message["role"] == "assistant":
                render_evidence(message)

    question = st.chat_input(
        "Pregunta por reglas, cartas o interacciones…",
        disabled=not available,
    )
    if not question:
        return

    st.session_state.messages.append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.markdown(question)
    with st.chat_message("assistant"):
        try:
            with st.spinner("Consultando fuentes y preparando la respuesta…"):
                with manager.chat_slot():
                    agent = get_agent(manager.snapshot().revision)
                    reply = agent.ask(
                        question, session_id=st.session_state.session_id,
                    )
        except Exception:
            logger.exception("Chat request failed")
            st.error("No se pudo completar la consulta. Revisa los logs e inténtalo de nuevo.")
            return

        message = {
            "role": "assistant",
            "content": reply.answer,
            "sources": reply.sources,
            "tools_used": reply.tools_used,
            "model_calls": reply.model_calls,
            "tool_calls": reply.tool_calls,
        }
        st.session_state.messages.append(message)
        st.markdown(reply.answer)
        render_evidence(message)


def render_indexing(manager: IndexJobManager) -> None:
    st.header("Base de conocimiento")
    st.write(
        "Indexa las reglas oficiales y el glosario en ChromaDB. "
        "Puedes continuar una indexación interrumpida sin recalcular "
        "los documentos que no han cambiado."
    )

    snapshot = manager.snapshot()
    running = snapshot.status == "running"
    if not running:
        try:
            st.metric("Documentos en ChromaDB", stored_count(snapshot.revision))
        except Exception:
            logger.exception("Unable to count indexed documents")
            st.warning("No se ha podido leer el número de documentos almacenados.")

    limit_value = st.number_input(
        "Documentos a indexar (0 = corpus completo)",
        min_value=0, value=20, step=20, disabled=running,
    )
    with st.expander("Opciones avanzadas"):
        batch_size = st.number_input(
            "Documentos por lote",
            min_value=1, max_value=128, value=16, disabled=running,
        )
    confirm_rebuild = st.checkbox(
        "Confirmo que reconstruir desde cero eliminará el índice actual",
        disabled=running,
    )

    col_resume, col_rebuild = st.columns(2)
    with col_resume:
        resume = st.button(
            "Continuar indexación", disabled=running, use_container_width=True,
        )
    with col_rebuild:
        rebuild = st.button(
            "Reconstruir desde cero",
            disabled=running or not confirm_rebuild,
            use_container_width=True,
        )

    if resume or rebuild:
        try:
            manager.start(
                limit=int(limit_value) or None,
                recreate=rebuild,
                batch_size=int(batch_size),
            )
        except (RuntimeError, ValueError, FileNotFoundError) as exc:
            st.error(str(exc))
        else:
            st.session_state.index_was_running = True
            st.rerun()

    # Rerun only this status fragment while the worker is active.
    @st.fragment(run_every="2s" if running else None)
    def progress_panel() -> None:
        state = manager.snapshot()
        st.subheader("Estado de la indexación")
        st.write({
            "idle": "En espera",
            "running": "Indexando…",
            "completed": "Completada",
            "cancelled": "Detenida; progreso conservado",
            "failed": "Error durante la indexación",
        }[state.status])

        if state.total:
            ratio = state.processed / state.total
            st.progress(
                min(ratio, 1.0),
                text=f"{state.processed}/{state.total} documentos ({ratio:.1%})",
            )
            c1, c2, c3 = st.columns(3)
            c1.metric("Nuevos", state.added)
            c2.metric("Actualizados", state.updated)
            c3.metric("Reutilizados", state.unchanged)
            st.caption(
                f"Transcurrido: {format_duration(state.elapsed_seconds)} · "
                f"ETA aproximada: {format_duration(state.eta_seconds)}"
            )
            if state.eta_seconds is not None:
                st.caption(
                    "La estimación supone que los documentos pendientes "
                    "necesitan embeddings; puede ser conservadora."
                )

        if state.status == "running":
            if state.cancel_requested:
                st.warning("Detención solicitada: esperando a que termine el lote actual.")
            elif st.button("Detener indexación"):
                manager.cancel()
                st.rerun(scope="fragment")
        elif state.status == "failed":
            st.error(state.error or "Error desconocido")
        elif state.status in ("completed", "cancelled"):
            st.success(f"Documentos guardados en ChromaDB: {state.stored_after}")

        # Refresh the whole page once after completion: it reenables controls
        # and makes the newest Chroma collection available to future chats.
        if state.status != "running" and st.session_state.get("index_was_running"):
            st.session_state.index_was_running = False
            st.rerun()

    progress_panel()


def main() -> None:
    st.set_page_config(page_title="MtgSage", page_icon="🧙", layout="wide")
    configure_logging()
    manager = job_manager()

    st.sidebar.title("🧙 MtgSage")
    page = st.sidebar.radio("Navegación", ["Chat", "Indexación"])
    st.sidebar.caption("MTG rules assistant · Demo local")
    if page == "Chat":
        render_chat(manager)
    else:
        render_indexing(manager)


if __name__ == "__main__":
    main()
