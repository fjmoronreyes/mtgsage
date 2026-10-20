
"""Tools that give the MtgSage agent access to trusted sources."""

import json
from time import perf_counter
from typing import Any, Literal
from urllib.parse import quote

from app.cards.api_client import API_BASE_URL, MagicApiClient
from app.cards.models import Card, CardQuery
from app.logger import get_logger
from app.semantic.embedder import OllamaEmbedder
from app.semantic.vector_store import ChromaVectorStore


logger = get_logger(__name__)

DocumentKind = Literal["rule", "glossary"]


class AgentTools:
    """Expose rules retrieval and card lookup to the agent."""

    def __init__(
        self,
        embedder: OllamaEmbedder,
        store: ChromaVectorStore,
        cards: MagicApiClient,
    ) -> None:
        self.embedder = embedder
        self.store = store
        self.cards = cards

    @staticmethod
    def _references(value: Any) -> list[str]:
        """Decode glossary references stored in Chroma metadata."""
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except json.JSONDecodeError:
                return []

        return value if isinstance(value, list) else []

    @staticmethod
    def _serialize_card(
        card: Card,
        include_rulings: bool = False,
    ) -> dict[str, Any]:
        """Return a compact, JSON-serializable card representation."""
        data: dict[str, Any] = {
            "id": card.id,
            "name": card.name,
            "mana_cost": card.mana_cost,
            "mana_value": card.mana_value,
            "colors": list(card.colors),
            "types": list(card.types),
            "subtypes": list(card.subtypes),
            "oracle_text": card.oracle_text,
            "set_code": card.set_code,
        }

        if include_rulings:
            data["rulings"] = list(card.rulings)

        return data

    def search_rules(
        self,
        question: str,
        limit: int = 5,
        kind: DocumentKind | None = None,
    ) -> dict[str, Any]:
        """Retrieve relevant rules and glossary definitions."""
        if not question.strip():
            raise ValueError("Rule search question cannot be empty")

        if not 1 <= limit <= 10:
            raise ValueError("Rule search limit must be between 1 and 10")

        if kind not in (None, "rule", "glossary"):
            raise ValueError("Invalid document kind")

        started = perf_counter()

        vector = self.embedder.embed_query(question.strip())

        hits = self.store.search(
            vector,
            limit=limit,
            kind=kind,
        )

        evidence = [
            {
                "source_id": hit.source_id,
                "kind": hit.metadata.get("kind"),
                "content": hit.content,
                "section": hit.metadata.get("section"),
                "page_start": hit.metadata.get("page_start"),
                "page_end": hit.metadata.get("page_end"),
                "source_version": hit.metadata.get("source_version"),
                "references": self._references(
                    hit.metadata.get("references")
                ),
                "distance": hit.distance,
            }
            for hit in hits
        ]

        indexed_documents = self.store.count()

        logger.info(
            "Rules search completed | matches=%d | "
            "indexed_documents=%d | duration=%.2fs",
            len(evidence),
            indexed_documents,
            perf_counter() - started,
        )

        return {
            "source": "MTG Comprehensive Rules",
            "indexed_documents": indexed_documents,
            "evidence": evidence,
        }

    def search_cards(
        self,
        *,
        name: str | None = None,
        colors: list[str] | None = None,
        types: list[str] | None = None,
        subtypes: list[str] | None = None,
        mana_value_lt: int | None = None,
        page: int = 1,
        page_size: int = 5,
    ) -> dict[str, Any]:
        """Search cards using structured provider filters."""
        if not any((
            name,
            colors,
            types,
            subtypes,
            mana_value_lt is not None,
        )):
            raise ValueError("At least one card filter is required")

        if not 1 <= page_size <= 20:
            raise ValueError("Card page size must be between 1 and 20")

        query = CardQuery(
            name=name,
            colors=tuple(colors or ()),
            types=tuple(types or ()),
            subtypes=tuple(subtypes or ()),
            mana_value_lt=mana_value_lt,
            page=page,
            page_size=page_size,
        )

        result = self.cards.search(query)

        return {
            "source": "Magic: The Gathering API",
            "source_url": f"{API_BASE_URL}/cards",
            "page": result.page,
            "total_count": result.total_count,
            "cards": [
                self._serialize_card(card)
                for card in result.cards
            ],
        }

    def get_card(self, card_id: str) -> dict[str, Any]:
        """Retrieve a specific printing, including its rulings."""
        if not card_id.strip():
            raise ValueError("Card ID cannot be empty")

        card = self.cards.get_card(card_id.strip())

        return {
            "source": "Magic: The Gathering API",
            "source_url": (
                f"{API_BASE_URL}/cards/{quote(card.id, safe='')}"
            ),
            "card": self._serialize_card(
                card,
                include_rulings=True,
            ),
        }
