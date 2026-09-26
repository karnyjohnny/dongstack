"""Testy MetadataService (M4): cache-first, failover, stale-if-error, breakery."""

from __future__ import annotations

import pytest

from app.api.circuit_breaker import CircuitBreaker
from app.api.metadata_service import MetadataService
from app.core.errors import ApiError, ApiErrorKind
from app.domain.models import RelationType, SearchItem


class FakeProvider:
    def __init__(self, name, items=None, error=None, relations=None):
        self.name = name
        self.items = items or []
        self.error = error
        self.relations = relations or []
        self.calls = 0

    def search(self, query, limit=20):
        self.calls += 1
        if self.error:
            raise self.error
        return self.items

    def related(self, mal_id):
        self.calls += 1
        if self.error:
            raise self.error
        return self.relations


class MemCache:
    def __init__(self):
        self.store = {}
        self.writes = []

    def get(self, key, allow_stale=False):
        hit = self.store.get(key)
        if hit is None:
            return None
        payload, fetched, ttl = hit
        fresh = fetched == 0
        if fresh or allow_stale:
            return payload, fresh
        return None

    def set(self, key, provider, payload, ttl):
        self.store[key] = (payload, 0, ttl)
        self.writes.append(key)


def _item(mal_id=1, title="A"):
    return SearchItem(provider="mal", ext_id=mal_id, mal_id=mal_id, title=title)


def _service(providers, cache=None, preferred="mal", breakers=None):
    cache = cache or MemCache()
    svc = MetadataService(
        providers=providers,
        cache_get=cache.get,
        cache_set=cache.set,
        preferred=preferred,
        breakers=breakers or {},
    )
    return svc, cache


def test_cache_hit_skips_provider():
    mal = FakeProvider("mal", items=[_item()])
    svc, cache = _service({"mal": mal})
    first = svc.search("doupo")
    assert first.from_cache is False and mal.calls == 1
    assert cache.writes, "wynik zapisany do cache"
    second = svc.search("doupo")
    assert second.from_cache is True and second.fresh is True
    assert mal.calls == 1  # ZERO dodatkowych żądań (§4.7)


def test_failover_to_anilist_on_mal_server_error():
    mal = FakeProvider("mal", error=ApiError(ApiErrorKind.SERVER, "500", provider="mal"))
    ani = FakeProvider("anilist", items=[_item(mal_id=2, title="B")])
    svc, _ = _service(
        {"mal": mal, "anilist": ani},
        breakers={"mal": CircuitBreaker(), "anilist": CircuitBreaker()},
    )
    out = svc.search("x")
    assert out.provider == "anilist"
    assert mal.calls == 1 and ani.calls == 1


def test_breaker_open_skips_mal_entirely():
    mal = FakeProvider("mal", error=ApiError(ApiErrorKind.THROTTLED_BAN, "ban", provider="mal"))
    ani = FakeProvider("anilist", items=[_item(mal_id=3)])
    breakers = {"mal": CircuitBreaker(), "anilist": CircuitBreaker()}
    svc, _ = _service({"mal": mal, "anilist": ani}, breakers=breakers)
    svc.search("x")  # MAL ban → breaker OPEN → failover
    assert breakers["mal"].allow_request() is False
    ani.calls = 0
    out = svc.search("y")  # kolejne zapyanie NIE próbuje MAL
    assert mal.calls == 1 and ani.calls == 1
    assert out.provider == "anilist"


def test_stale_cache_on_total_outage():
    mal = FakeProvider("mal", items=[_item(title="Świeże")])
    svc, cache = _service({"mal": mal})
    svc.search("q")
    # symulacja wygaśnięcia TTL: fetched w przeszłości
    for key in list(cache.store):
        payload, _, ttl = cache.store[key]
        cache.store[key] = (payload, -99999, ttl)
    mal.error = ApiError(ApiErrorKind.NETWORK, "offline", provider="mal")
    out = svc.search("q")
    assert out.from_cache is True and out.fresh is False  # graceful degradation
    assert out.items[0].title == "Świeże"


def test_related_cached_with_long_ttl():
    rels = [(2, RelationType.SEQUEL)]
    mal = FakeProvider("mal", relations=rels)
    svc, cache = _service({"mal": mal})
    assert svc.related(1) == rels
    assert svc.related(1) == rels
    assert mal.calls == 1
    keys = [k for k in cache.writes if k.startswith("mal:related:")]
    assert keys and cache.store[keys[0]][2] == 7 * 86400


def test_all_providers_down_raises_last_error():
    mal = FakeProvider("mal", error=ApiError(ApiErrorKind.SERVER, "x", provider="mal"))
    ani = FakeProvider("anilist", error=ApiError(ApiErrorKind.SERVER, "y", provider="anilist"))
    svc, _ = _service({"mal": mal, "anilist": ani})
    with pytest.raises(ApiError):
        svc.search("q")
