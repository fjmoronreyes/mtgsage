
"""Minimal regression tests for the document parsing pipeline."""

import pytest

from app.config import RULES_PDF_PATH
from app.parsers.general_parser import GeneralParser
from app.parsers.glossary_parser import GlossaryEntry
from app.parsers.rules_parser import Rule


def test_rule_document() -> None:
    rule = Rule(
        rule_id="106.4",
        section="106. Mana",
        text="Mana goes into a player's mana pool.",
        page_start=13,
        page_end=13,
    )

    document = GeneralParser._from_rule(rule)

    assert document.source_id == "rule:106.4"
    assert document.kind == "rule"
    assert "Section: 106. Mana" in document.content
    assert rule.text in document.content
    assert document.metadata["page_start"] == 13


def test_glossary_document() -> None:
    entry = GlossaryEntry(
        term="First Strike",
        definition="A keyword ability.",
        references=("702.7",),
        page_start=280,
        page_end=280,
    )

    document = GeneralParser._from_glossary(entry)

    assert document.source_id == "glossary:first strike"
    assert document.kind == "glossary"
    assert "Term: First Strike" in document.content
    assert document.metadata["references"] == ["702.7"]


@pytest.mark.skipif(
    not RULES_PDF_PATH.is_file(),
    reason="Reference PDF not available",
)
def test_complete_corpus() -> None:
    documents = GeneralParser().parse(RULES_PDF_PATH)

    assert len(documents) == 3868
    assert sum(doc.kind == "rule" for doc in documents) == 3138
    assert sum(doc.kind == "glossary" for doc in documents) == 730

    assert len({doc.source_id for doc in documents}) == len(documents)

    assert documents[0].source_id == "rule:100.1"
    assert documents[-1].source_id == "glossary:zone-change triggers"

    assert all(
        doc.content.strip()
        and 1 <= doc.page_start <= doc.page_end <= 309
        for doc in documents
    )
