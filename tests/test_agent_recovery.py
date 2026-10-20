"""Regression tests for tool-calling finalization and graceful fallback."""

from types import SimpleNamespace

from google.genai import types

from app.agents.agent import MtgSageAgent
from app.agents.conversation import ConversationStore


class FakeTools:
    def search_rules(self, question, limit=5, kind=None):
        return {
            "indexed_documents": 579,
            "evidence": [{
                "source_id": "rule:500.1",
                "section": "500. General",
                "page_start": 83,
                "content": "A turn consists of five phases.",
            }],
        }

    def search_cards(self, **kwargs):
        return {"cards": [], "total_count": 0}

    def get_card(self, card_id):
        return {"card": {"id": card_id, "name": "Test Card"}}


class FakeLLM:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.modes = []

    def generate(self, contents, *, tools=None, system_instruction=None,
                 tool_mode="AUTO"):
        self.modes.append(tool_mode)
        return next(self.responses)


def tool_request():
    call = types.FunctionCall(
        name="search_rules", args={"question": "Turn phases"}
    )
    content = types.Content(
        role="model", parts=[types.Part(function_call=call)]
    )
    return SimpleNamespace(
        function_calls=[call],
        candidates=[SimpleNamespace(content=content)],
        text=None,
    )


def text_reply(text):
    return SimpleNamespace(function_calls=[], candidates=[], text=text)


def test_limit_exhaustion_forces_text_only_and_preserves_sources():
    llm = FakeLLM([
        tool_request(), tool_request(), tool_request(),
        text_reply("El turno tiene cinco fases. [rule:500.1]"),
    ])
    history = ConversationStore()
    session_id = history.create_session()
    agent = MtgSageAgent(llm, FakeTools(), history)

    reply = agent.ask("¿Qué fases tiene un turno?", session_id)

    assert llm.modes == ["AUTO", "AUTO", "AUTO", "NONE"]
    assert reply.model_calls == 4
    assert reply.tool_calls == 3
    assert reply.sources[0].reference == "rule:500.1"
    assert reply.answer.startswith("El turno tiene")
    assert len(history.history(session_id)) == 1


def test_unexpected_function_call_in_final_reply_has_safe_fallback():
    llm = FakeLLM([tool_request(), tool_request()])
    history = ConversationStore()
    session_id = history.create_session()
    agent = MtgSageAgent(llm, FakeTools(), history, max_tool_rounds=1)

    reply = agent.ask("¿Qué fases tiene un turno?", session_id)

    assert llm.modes == ["AUTO", "NONE"]
    assert "rule:500.1" in reply.answer
    assert reply.sources[0].reference == "rule:500.1"
    assert len(history.history(session_id)) == 1
