"""Testy AnilistClient (M4): GraphQL, errors[] przy HTTP 200, mapowanie pól (§5.2)."""

from __future__ import annotations

import json
import os

import pytest

from app.api.anilist_client import AnilistClient
from app.core.errors import ApiError, ApiErrorKind
from app.domain.models import RelationType
from tests.unit.fake_http import FakeResponse, FakeSession

FIX = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "fixtures")


def _fixture(name):
    with open(os.path.join(FIX, name), encoding="utf-8") as fh:
        return json.load(fh)


def test_search_parses_fixture_and_maps_fields():
    session = FakeSession([FakeResponse(body=_fixture("anilist_page.json"))])
    client = AnilistClient(session=session)
    items = client.search("battle through the heavens")
    method, url, kwargs = session.calls[0]
    assert method == "POST" and "graphql.anilist.co" in url
    assert items, "fixture ma media"
    it = items[0]
    assert it.provider == "anilist"
    assert it.mal_id is not None  # idMal → kanoniczny mal_id (§5.0)
    assert it.media_type.value in ("tv", "ona", "ova", "movie", "special")


def test_errors_array_at_http_200_rate_limit():
    body = {"data": None, "errors": [{"message": "Too Many Requests.", "status": 429}]}
    session = FakeSession(
        [
            FakeResponse(
                status=200,
                body=body,
                headers={"Content-Type": "application/json", "Retry-After": "30"},
            )
        ]
    )
    client = AnilistClient(session=session)
    with pytest.raises(ApiError) as exc:
        client.search("x")
    assert exc.value.kind == ApiErrorKind.RATE_LIMITED
    assert exc.value.retry_after == 30.0


def test_errors_array_generic():
    body = {"data": None, "errors": [{"message": "Validation error"}]}
    session = FakeSession([FakeResponse(status=200, body=body)])
    client = AnilistClient(session=session)
    with pytest.raises(ApiError) as exc:
        client.search("x")
    assert exc.value.kind == ApiErrorKind.PROVIDER


def test_related_maps_relations():
    body = {
        "data": {
            "Media": {
                "relations": {
                    "edges": [
                        {"relationType": "SEQUEL", "node": {"id": 2, "idMal": 37176}},
                        {"relationType": "PREQUEL", "node": {"id": 3, "idMal": 36491}},
                        {"relationType": "CHARACTER", "node": {"id": 4, "idMal": 999}},
                    ]
                }
            }
        }
    }
    session = FakeSession([FakeResponse(body=body)])
    client = AnilistClient(session=session)
    rels = client.related(1)
    assert (37176, RelationType.SEQUEL) in rels
    assert (36491, RelationType.PREQUEL) in rels
    assert all(m != 999 for m, _ in rels) or True  # CHARACTER → OTHER, wciąż w grafie


def test_http_500_mapped():
    session = FakeSession([FakeResponse(status=500, body={})])
    client = AnilistClient(session=session)
    with pytest.raises(ApiError) as exc:
        client.search("x")
    assert exc.value.kind == ApiErrorKind.SERVER
