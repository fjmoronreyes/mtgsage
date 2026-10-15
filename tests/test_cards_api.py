
"""Regression test for the Magic API adapter."""

from dataclasses import replace

import httpx

from app.cards.api_client import MagicApiClient
from app.cards.models import CardQuery


def test_color_filter_and_mana_range_pagination() -> None:
    cards = [
        {
            "id": f"card-{index}",
            "name": f"Warrior {index}",
            "cmc": 1,
            "colors": ["W"],
            "types": ["Creature"],
            "subtypes": ["Warrior"],
        }
        for index in range(18)
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        params = request.url.params

        assert params["colors"] == "W"
        assert params["subtypes"] == "Warrior"

        matching = cards if params["cmc"] == "1" else []
        page = int(params["page"])
        size = int(params["pageSize"])
        start = (page - 1) * size

        return httpx.Response(
            status_code=200,
            json={"cards": matching[start:start + size]},
            headers={"Total-Count": str(len(matching))},
        )

    transport = httpx.MockTransport(handler)

    with httpx.Client(transport=transport) as http_client:
        client = MagicApiClient(client=http_client)

        query = CardQuery(
            colors=("White",),
            subtypes=("Warrior",),
            mana_value_lt=2,
            page_size=10,
        )

        first = client.search(query)
        second = client.search(replace(query, page=2))

    assert first.total_count == second.total_count == 18
    assert len(first.cards) == 10
    assert len(second.cards) == 8

    ids = [
        card.id
        for card in (*first.cards, *second.cards)
    ]
    assert len(ids) == len(set(ids)) == 18
