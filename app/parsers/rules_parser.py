
from dataclasses import dataclass
from pathlib import Path
import re

import pymupdf


_RULE_ID = re.compile(
    r"^(?P<id>\d{3}\.\d+[a-z]?)\.?\s+(?P<text>.+)$"
)
_SECTION = re.compile(r"^\d{3}\.\s+\S")
_CHAPTER = re.compile(r"^\d\.\s+\S")


def _join_wrapped_lines(lines: list[str]) -> str:
    """Reconstruct wrapped PDF lines, preserving hyphenated words."""
    if not lines:
        return ""

    text = lines[0].strip()

    for line in lines[1:]:
        line = line.strip()

        if not line:
            continue

        if text.endswith("-") and line[0].isalpha():
            text += line
        else:
            text += f" {line}"

    return text

@dataclass(frozen=True, slots=True)
class Rule:
    rule_id: str
    section: str
    text: str
    page_start: int
    page_end: int


class RulesParser:
    """Parse numbered rules from the April 2026 MTG PDF layout."""

    def parse(self, path: Path) -> list[Rule]:
        rules: list[Rule] = []
        section = ""
        current_section = ""
        current_id: str | None = None
        current_lines: list[str] = []
        first_page = last_page = 0
        started = False

        with pymupdf.open(path) as document:
            for page_number, page in enumerate(document, start=1):
                blocks = page.get_text("dict", sort=True)["blocks"]

                for block in blocks:
                    if block["type"] != 0:
                        continue

                    for line in block["lines"]:
                        text = "".join(
                            span["text"] for span in line["spans"]
                        ).strip()

                        if not text:
                            continue

                        x = line["bbox"][0]

                        if text == "Glossary" and started and abs(x - 90) < 3:
                            if current_id is not None:
                                rules.append(
                                    Rule(
                                        current_id,
                                        current_section,
                                        _join_wrapped_lines(current_lines),
                                        first_page,
                                        last_page,
                                    )
                                )
                            return rules

                        if abs(x - 90) < 3:
                            if _SECTION.match(text):
                                section = text

                            if _SECTION.match(text) or _CHAPTER.match(text):
                                continue

                        match = _RULE_ID.match(text)

                        if match:
                            rule_id = match["id"]
                            expected_x = (
                                120 if rule_id[-1].isalpha() else 105
                            )

                            if abs(x - expected_x) < 3:
                                if current_id is not None:
                                    rules.append(
                                        Rule(
                                            current_id,
                                            current_section,
                                            _join_wrapped_lines(current_lines),
                                            first_page,
                                            last_page,
                                        )
                                    )

                                current_id = rule_id
                                current_section = section
                                current_lines = [match["text"]]
                                first_page = last_page = page_number
                                started = True
                                continue

                        if current_id is not None:
                            current_lines.append(text)
                            last_page = page_number

        if current_id is not None:
            rules.append(
                Rule(
                    current_id,
                    current_section,
                    _join_wrapped_lines(current_lines),
                    first_page,
                    last_page,
                )
            )

        return rules
