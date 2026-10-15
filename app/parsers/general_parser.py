
"""Coordinate parsers and prepare documents for indexing."""

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from .glossary_parser import GlossaryEntry, GlossaryParser
from .rules_parser import Rule, RulesParser


DocumentKind = Literal["rule", "glossary"]


@dataclass(frozen=True, slots=True)
class IndexDocument:
    kind: DocumentKind
    source_id: str
    content: str
    page_start: int
    page_end: int
    section: str | None = None
    references: tuple[str, ...] = ()

    @property
    def metadata(self) -> dict:
        return {
            "kind": self.kind,
            "source_id": self.source_id,
            "page_start": self.page_start,
            "page_end": self.page_end,
            "section": self.section,
            "references": list(self.references),
            "source_version": "2026-04-17",
        }


class GeneralParser:
    """Build a unified indexable corpus."""

    def __init__(self) -> None:
        self.rules_parser = RulesParser()
        self.glossary_parser = GlossaryParser()
        self.paragraphs: list[IndexDocument] = []

    @staticmethod
    def _from_rule(rule: Rule) -> IndexDocument:
        content = (
            "Magic: The Gathering Comprehensive Rules\n"
            f"Rule: {rule.rule_id}\n"
            f"Section: {rule.section}\n\n"
            f"{rule.text}"
        )

        return IndexDocument(
            kind="rule",
            source_id=f"rule:{rule.rule_id}",
            content=content,
            page_start=rule.page_start,
            page_end=rule.page_end,
            section=rule.section,
        )

    @staticmethod
    def _from_glossary(entry: GlossaryEntry) -> IndexDocument:
        content = (
            "Magic: The Gathering Glossary\n"
            f"Term: {entry.term}\n\n"
            f"Definition: {entry.definition}"
        )

        return IndexDocument(
            kind="glossary",
            source_id=f"glossary:{entry.term.casefold()}",
            content=content,
            page_start=entry.page_start,
            page_end=entry.page_end,
            references=entry.references,
        )

    def parse(self, path: Path) -> list[IndexDocument]:
        rules = self.rules_parser.parse(path)
        glossary = self.glossary_parser.parse(path)

        self.paragraphs = [
            *(self._from_rule(rule) for rule in rules),
            *(self._from_glossary(entry) for entry in glossary),
        ]

        return self.paragraphs
