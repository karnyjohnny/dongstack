"""Testy ApiCache: klucze, TTL, stale-if-error, vacuum."""

from __future__ import annotations

from app.data.api_cache import ApiCache, details_key, normalize_query, related_key, search_key


def test_key_builders():
    assert normalize_query("  Ling   LONG ") == "ling_long"
    assert normalize_query("x" * 200) == "x" * 64
    assert search_key("mal", "Doupo", 20) == "mal:search:doupo:20"
    assert details_key("mal", 37176) == "mal:anime:37176"
    assert related_key(36491) == "mal:related:36491"


def test_set_get_fresh(db_conn):
    cache = ApiCache(db_conn)
    now = 1_000_000
    cache.set(search_key("mal", "doupo", 20), "mal", '{"data":[]}', ttl_s=3600, now=now)
    got = cache.get(search_key("mal", "doupo", 20), now=now + 60)
    assert got is not None
    payload, fresh = got
    assert payload == '{"data":[]}'
    assert fresh is True


def test_expired_without_stale_is_none(db_conn):
    cache = ApiCache(db_conn)
    now = 1_000_000
    cache.set("k1", "mal", "{}", ttl_s=10, now=now)
    assert cache.get("k1", now=now + 11) is None


def test_expired_with_stale_returns_payload(db_conn):
    cache = ApiCache(db_conn)
    now = 1_000_000
    cache.set("k1", "mal", '{"stale":true}', ttl_s=10, now=now)
    got = cache.get("k1", now=now + 11, allow_stale=True)
    assert got is not None
    payload, fresh = got
    assert fresh is False
    assert payload == '{"stale":true}'


def test_set_overwrites(db_conn):
    cache = ApiCache(db_conn)
    cache.set("k", "mal", "v1", ttl_s=100, now=500)
    cache.set("k", "mal", "v2", ttl_s=100, now=600)
    assert cache.count() == 1
    assert cache.get("k", now=650)[0] == "v2"


def test_vacuum_removes_long_expired(db_conn):
    cache = ApiCache(db_conn)
    now = 10_000_000
    cache.set("old", "mal", "{}", ttl_s=10, now=now - 86400 * 10)  # wygasł 10 dni temu
    cache.set("recent", "mal", "{}", ttl_s=3600, now=now - 60)  # świeży
    cache.set("mid", "mal", "{}", ttl_s=10, now=now - 86400 * 2)  # wygasł 2 dni temu (w grace)
    removed = cache.vacuum(now=now, grace_s=7 * 86400)
    assert removed == 1  # tylko "old" (fetched+ttl < now-7d)
    assert cache.get("recent", now=now) is not None
    assert cache.get("mid", now=now, allow_stale=True) is not None
