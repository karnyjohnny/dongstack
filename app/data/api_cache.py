"""app/data/api_cache.py — cache odpowiedzi API w SQLite (specyfikacja §4.7).

Polityka: cache-first → świeże (fresh) serwowane natychmiast; przestarzałe (stale)
tylko jako graceful degradation przy błędzie sieci (allow_stale=True).
Klucze deterministyczne: "mal:search:<query_norm>:<limit>", "mal:anime:<id>",
"mal:related:<id>", "anilist:search:<query_norm>".

NetworkWorker czyta cache połączeniem read-only (WAL pozwala na współbieżny
odczyt bez blokowania zapisów DbWorker) — zapis wyłącznie przez DbWorker.
"""

from __future__ import annotations

import re
import sqlite3
from typing import Optional, Tuple

from app.core.timeutil import utc_now_epoch

_WHITESPACE = re.compile(r"\s+")
QUERY_MAX_LEN = 64


def normalize_query(query: str) -> str:
    """Deterministyczna normalizacja frazy do klucza cache."""
    q = _WHITESPACE.sub("_", (query or "").strip().lower())
    return q[:QUERY_MAX_LEN]


def search_key(provider: str, query: str, limit: int) -> str:
    return "%s:search:%s:%d" % (provider, normalize_query(query), int(limit))


def details_key(provider: str, ext_id: int) -> str:
    return "%s:anime:%d" % (provider, int(ext_id))


def related_key(ext_id: int) -> str:
    return "mal:related:%d" % int(ext_id)


class ApiCache:
    """Dostęp do tabeli api_cache. Dwie instancje: zapis (DbWorker), odczyt (NetworkWorker, ro)."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def get(
        self, key: str, now: Optional[int] = None, allow_stale: bool = False
    ) -> Optional[Tuple[str, bool]]:
        """Zwraca (payload_json, fresh) albo None.

        fresh=True  → w TTL;  fresh=False → przestarzały (tylko gdy allow_stale).
        """
        now = utc_now_epoch() if now is None else int(now)
        row = self._conn.execute(
            "SELECT payload, fetched_at, ttl_s FROM api_cache WHERE cache_key = ?",
            (key,),
        ).fetchone()
        if row is None:
            return None
        fetched_at = int(row["fetched_at"])
        ttl_s = int(row["ttl_s"])
        fresh = (now - fetched_at) < ttl_s
        if fresh or allow_stale:
            return (str(row["payload"]), fresh)
        return None

    def set(
        self, key: str, provider: str, payload_json: str, ttl_s: int, now: Optional[int] = None
    ) -> None:
        now = utc_now_epoch() if now is None else int(now)
        sql = (
            "INSERT INTO api_cache (cache_key, provider, payload, fetched_at, ttl_s) "
            "VALUES (?,?,?,?,?) "
            "ON CONFLICT(cache_key) DO UPDATE SET "
            "provider=excluded.provider, payload=excluded.payload, "
            "fetched_at=excluded.fetched_at, ttl_s=excluded.ttl_s"
        )
        with self._conn:
            self._conn.execute(sql, (key, provider, payload_json, now, int(ttl_s)))

    def vacuum(self, now: Optional[int] = None, grace_s: int = 7 * 86400) -> int:
        """Usuwa wpisy przestarzałe dłużej niż grace_s (raz na dobę przy starcie)."""
        now = utc_now_epoch() if now is None else int(now)
        sql = "DELETE FROM api_cache WHERE fetched_at + ttl_s < ?"
        with self._conn:
            cur = self._conn.execute(sql, (now - int(grace_s),))
        return int(cur.rowcount or 0)

    def count(self) -> int:
        row = self._conn.execute("SELECT count(*) AS n FROM api_cache").fetchone()
        return int(row["n"]) if row is not None else 0
