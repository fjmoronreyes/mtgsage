
"""Extract glossary entries from MTG Comprehensive Rules."""

import re
from dataclasses import dataclass
from pathlib import Path

import pymupdf


RULE_REFERENCE = re.compile(r"\b\d{3}(?:\.\d+[a-z]?)?\b")


@dataclass(frozen=True, slots=True)
class GlossaryEntry:
    term: str
    definition: str
    references: tuple[str, ...]
    page_start: int
    page_end: int


class GlossaryParser:
    """Extract glossary terms using PDF typography."""

    @staticmethod
    def _build_entry(
        term: str,
        lines: list[str],
        first_page: int,
        last_page: int,
    ) -> GlossaryEntry:
        definition = " ".join(lines)

        references = tuple(
            dict.fromkeys(RULE_REFERENCE.findall(definition))
        )

        return GlossaryEntry(
            term=term,
            definition=definition,
            references=references,
            page_start=first_page,
            page_end=last_page,
        )

    def parse(self, path: Path) -> list[GlossaryEntry]:
        entries: list[GlossaryEntry] = []

        inside_glossary = False
        current_term: str | None = None
        current_lines: list[str] = []
        first_page = last_page = 0

        with pymupdf.open(path) as document:
            for page_number, page in enumerate(document, start=1):
                blocks = page.get_text("dict", sort=True)["blocks"]

                for block in blocks:
                    if block["type"] != 0:
                        continue

                    for line in block["lines"]:
                        spans = [
                            span
                            for span in line["spans"]
                            if span["text"].strip()
                        ]

                        if not spans:
                            continue

                        text = "".join(
                            span["text"] for span in line["spans"]
                        ).strip()

                        if not inside_glossary:
                            if text == "Glossary" and spans[0]["size"] > 11:
                                inside_glossary = True
                            continue

                        if text == "Credits" and spans[0]["size"] > 11:
                            if current_term is not None:
                                entries.append(
                                    self._build_entry(
                                        current_term,
                                        current_lines,
                                        first_page,
                                        last_page,
                                    )
                                )
                            return entries

                        is_term = (
                            abs(line["bbox"][0] - 90) < 3
                            and all(span["flags"] & 16 for span in spans)
                            and all(
                                9 <= span["size"] <= 11
                                for span in spans
                            )
                        )

                        if is_term:
                            if current_term is not None:
                                entries.append(
                                    self._build_entry(
                                        current_term,
                                        current_lines,
                                        first_page,
                                        last_page,
                                    )
                                )

                            current_term = text
                            current_lines = []
                            first_page = last_page = page_number

                        elif current_term is not None:
                            current_lines.append(text)
                            last_page = page_number

        raise ValueError(
            "Glossary or Credits section not found correctly"
        )
