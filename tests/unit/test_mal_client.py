"""Testy MalClient (M4): nagłówki, parsowanie, limit, taksonomia błędów (§5.1)."""

from __future__ import annotations

import json
import os

import pytest

from app.api.mal_client import LIMIT_MAX, MalClient
from app.core.errors import ApiError, ApiErrorKind
from app.domain.models import RelationType
from tests.unit.fake_http import FakeResponse, FakeSession

FIX = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "fixtures")


def _fixture(name):
    with open(os.path.join(FIX, name), encoding="utf-8") as fh:
        return json.load(fh)


def test_requires_client_id():
    with pytest.raises(ApiError) as exc:
        MalClient("")
    assert exc.value.kind == ApiErrorKind.AUTH


def test_headers_and_fields():
    session = FakeSession([FakeResponse(body={"data": []})])
    client = MalClient("cid-123", session=session)
    client.search("doupo", limit=20)
    method, url, kwargs = session.calls[0]
    assert method == "GET" and url.endswith("/v2/anime")
    assert kwargs["headers"]["X-MAL-CLIENT-ID"] == "cid-123"
    assert "DongStack" in kwargs["headers"]["User-Agent"]
    assert kwargs["params"]["q"] == "doupo"
    assert kwargs["params"]["limit"] == 20
    assert "related_anime" not in kwargs["params"]["fields"]
    assert kwargs["timeout"] == (5.0, 10.0)


def test_limit_clamped_to_100():
    session = FakeSession([FakeResponse(body={"data": []})])
    client = MalClient("cid", session=session)
    client.search("x", limit=5000)
    assert session.calls[0][2]["params"]["limit"] == LIMIT_MAX


def test_search_parses_fixture():
    session = FakeSession([FakeResponse(body=_fixture("mal_search.json"))])
    client = MalClient("cid", session=session)
    items = client.search("doupo")
    assert len(items) == 3
    first = items[0]
    assert first.provider == "mal" and first.mal_id == first.ext_id
    assert first.title.startswith("Doupo")
    assert first.cover_url.startswith("https://cdn.myanimelist.net")
    assert first.total_episodes > 0
    assert first.year == 2017  # nagranie live: pierwszy node = S1 (2017)
    assert first.media_type.value in ("ona", "tv")


def test_related_parses_fixture():
    session = FakeSession([FakeResponse(body=_fixture("mal_related_37176.json"))])
    client = MalClient("cid", session=session)
    rels = client.related(37176)
    kinds = {r for _, r in rels}
    assert RelationType.PREQUEL in kinds and RelationType.SEQUEL in kinds
    assert (36491, RelationType.PREQUEL) in rels
    assert (38436, RelationType.SEQUEL) in rels


def test_error_taxonomy():
    cases = [
        (FakeResponse(status=400, body=_fixture("mal_400_limit.json")), ApiErrorKind.BAD_REQUEST),
        (FakeResponse(status=401, body={"message": "no"}), ApiErrorKind.AUTH),
        (
            FakeResponse(
                status=403,
                text_body="<html>throttled</html>",
                headers={"Content-Type": "text/html"},
            ),
            ApiErrorKind.THROTTLED_BAN,
        ),
        (FakeResponse(status=404, body={"message": "x"}), ApiErrorKind.NOT_FOUND),
        (
            FakeResponse(
                status=429,
                body={"message": "slow"},
                headers={"Content-Type": "application/json", "Retry-After": "7"},
            ),
            ApiErrorKind.RATE_LIMITED,
        ),
        (FakeResponse(status=503, body={}), ApiErrorKind.SERVER),
    ]
    for resp, kind in cases:
        session = FakeSession([resp])
        client = MalClient("cid", session=session)
        with pytest.raises(ApiError) as exc:
            client.search("x")
        assert exc.value.kind == kind, kind
        if kind == ApiErrorKind.RATE_LIMITED:
            assert exc.value.retry_after == 7.0
        if kind == ApiErrorKind.THROTTLED_BAN:
            assert exc.value.retryable


def test_network_error_mapped():
    import requests

    class Boom(FakeSession):
        def get(self, url, **kwargs):
            raise requests.ConnectionError("brak sieci")

    client = MalClient("cid", session=Boom())
    with pytest.raises(ApiError) as exc:
        client.search("x")
    assert exc.value.kind == ApiErrorKind.NETWORK
    assert exc.value.retryable


def test_parse_error_on_non_json_200():
    session = FakeSession([FakeResponse(status=200, text_body="<!doctype html>")])
    client = MalClient("cid", session=session)
    with pytest.raises(ApiError) as exc:
        client.search("x")
    assert exc.value.kind == ApiErrorKind.PARSE
    assert not exc.value.retryable
