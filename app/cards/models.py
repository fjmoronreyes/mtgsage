
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CardQuery:
    name: str | None = None
    colors: tuple[str, ...] = ()
    types: tuple[str, ...] = ()
    subtypes: tuple[str, ...] = ()
    mana_value_lt: int | None = None
    page: int = 1
    page_size: int = 20


@dataclass(frozen=True, slots=True)
class Card:
    id: str
    name: str
    mana_cost: str | None
    mana_value: float | None
    colors: tuple[str, ...]
    types: tuple[str, ...]
    subtypes: tuple[str, ...]
    oracle_text: str | None
    set_code: str | None
    image_url: str | None
    rulings: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class CardPage:
    cards: tuple[Card, ...]
    page: int
    total_count: int | None
