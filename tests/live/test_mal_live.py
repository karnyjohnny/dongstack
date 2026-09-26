"""Testy LIVE przeciw produkcyjnemu MAL API — OPT-IN (specyfikacja §10.1/§10.2).

Uruchamianie WYŁĄCZNIE ręcznie / workflow_dispatch:
    RUN_LIVE_API_TESTS=1 MAL_CLIENT_ID=<twoje_id> pytest tests/live -m live
CI domyślnie NIE uruchamia (decyzja D5); sekrety wyłącznie z env/GH Secrets.
Limity: 3 żądania z odstępami ≥1.2 s (zgodnie z token bucket 1 req/s).
"""

from __future__ import annotations

import os
import time

import pytest

from app.api.mal_client import MalClient
from app.core.errors import ApiError
from app.domain.models import RelationType

pytestmark = pytest.mark.live

CLIENT_ID = os.environ.get("MAL_CLIENT_ID", "")
RUN = os.environ.get("RUN_LIVE_API_TESTS", "") == "1"

pytestmark = [
    pytestmark,
    pytest.mark.skipif(
        not (RUN and CLIENT_ID), reason="live: wymaga RUN_LIVE_API_TESTS=1 + MAL_CLIENT_ID"
    ),
]


def test_live_search_schema():
    client = MalClient(CLIENT_ID)
    items = client.search("doupo cangqiong", limit=3)
    assert items
    first = items[0]
    assert first.mal_id and first.title
    time.sleep(1.3)


def test_live_related_universe_graph():
    client = MalClient(CLIENT_ID)
    rels = client.related(37176)  # Doupo Cangqiong 2nd Season
    kinds = {r for _, r in rels}
    assert RelationType.PREQUEL in kinds  # franczyza ma S1
    time.sleep(1.3)


def test_live_bad_limit_maps_to_bad_request():
    import requests

    session = requests.Session()
    client = MalClient(CLIENT_ID, session=session)
    with pytest.raises(ApiError) as exc:
        client._get_json("/anime", {"q": "x", "limit": 1500, "fields": "id"})
    assert exc.value.status == 400
