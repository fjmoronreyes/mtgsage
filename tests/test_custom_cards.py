
"""Tests for custom card generation and conversational continuity."""

from types import SimpleNamespace

from app.agents.agent import MtgSageAgent
from app.agents.conversation import ConversationStore


class FakeLLM:
    def __init__(self) -> None:
        self.requests = []
        self.responses = iter([
            (
                "**Carta personalizada — no oficial**\n\n"
                "**Han Solo** — {1}{R}{W}\n\n"
                "Criatura legendaria — Humano Bribón\n\n"
                "Dañar primero\n\n3/2"
            ),
            (
                "**Carta personalizada — no oficial**\n\n"
                "**Han Solo** — {R}{W}\n\n"
                "Criatura legendaria — Humano Bribón\n\n"
                "Dañar primero, prisa\n\n3/2"
            ),
        ])

    def generate(
        self,
        contents,
        *,
        tools=None,
        system_instruction=None,
        tool_mode="AUTO",
    ):
        self.requests.append({
            "contents": list(contents),
            "system_instruction": system_instruction,
            "tool_mode": tool_mode,
        })

        return SimpleNamespace(
            function_calls=[],
            text=next(self.responses),
        )


class FakeTools:
    def search_rules(self, **kwargs):
        raise AssertionError("Unexpected rules search")

    def search_cards(self, **kwargs):
        raise AssertionError("Unexpected card search")

    def get_card(self, **kwargs):
        raise AssertionError("Unexpected card lookup")


def test_custom_card_generation_and_revision():
    llm = FakeLLM()
    conversations = ConversationStore()
    session_id = conversations.create_session()

    agent = MtgSageAgent(
        llm=llm,
        tools=FakeTools(),
        conversations=conversations,
    )

    first = agent.ask(
        "Crea una carta blanca-roja de Han Solo con dañar primero.",
        session_id,
    )

    assert "Han Solo" in first.answer
    assert "Dañar primero" in first.answer
    assert first.tools_used == ()
    assert first.sources == ()
    assert first.model_calls == 1

    second = agent.ask(
        "Ahora reduce su coste en un maná y añade prisa.",
        session_id,
    )

    assert "{R}{W}" in second.answer
    assert "prisa" in second.answer
    assert second.sources == ()
    assert second.tools_used == ()

    # The second Gemini request includes the previous exchange.
    second_contents = llm.requests[1]["contents"]

    assert len(second_contents) == 3
    assert "Han Solo" in second_contents[1].parts[0].text
    assert "CUSTOM CARD CREATION" in (
        llm.requests[0]["system_instruction"]
    )

    assert len(conversations.history(session_id)) == 2
