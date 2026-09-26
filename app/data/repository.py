"""app/data/repository.py — JEDYNA warstwa z SQL (reguły R2, R13; specyfikacja §4.5).

Wszystkie zapytania parametryzowane (`?`), transakcje przez `with conn:`,
żadnego składania SQL ze stringów. Wywoływane wyłącznie z DbWorker (lub testów).
"""

from __future__ import annotations

import sqlite3
from typing import Dict, List, Optional

from app.core.timeutil import utc_now_iso
from app.domain.models import (
    Donghua,
    MediaType,
    Status,
    StreamingLink,
    Universe,
    normalize_media_type,
)

_DONGHUA_COLUMNS = (
    "id, mal_id, anilist_id, provider, title, title_alt, total_episodes, current_episode, "
    "status, score, media_type, start_year, cover_key, universe_id, universe_order, note, "
    "added_at, updated_at, deleted_at"
)


def _row_to_donghua(row: sqlite3.Row) -> Donghua:
    return Donghua(
        id=int(row["id"]),
        mal_id=row["mal_id"],
        anilist_id=row["anilist_id"],
        provider=row["provider"] or "manual",
        title=row["title"] or "",
        title_alt=row["title_alt"],
        total_episodes=int(row["total_episodes"] or 0),
        current_episode=int(row["current_episode"] or 0),
        status=Status(row["status"]) if row["status"] else Status.PLANNED,
        score=row["score"],
        media_type=normalize_media_type(row["media_type"]),
        start_year=row["start_year"],
        cover_key=row["cover_key"],
        universe_id=row["universe_id"],
        universe_order=row["universe_order"],
        note=row["note"],
        added_at=row["added_at"] or "",
        updated_at=row["updated_at"] or "",
        deleted_at=row["deleted_at"],
    )


class DonghuaRepository:
    """CRUD pozycji biblioteki. Obiekty Donghua są frozen — repo zwraca nowe instancje."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    # --- odczyt ---------------------------------------------------------------
    def load_alive(self) -> List[Donghua]:
        sql = (
            "SELECT %s FROM donghua WHERE deleted_at IS NULL "
            "ORDER BY updated_at DESC" % _DONGHUA_COLUMNS
        )
        return [_row_to_donghua(r) for r in self._conn.execute(sql).fetchall()]

    def get(self, donghua_id: int) -> Optional[Donghua]:
        sql = "SELECT %s FROM donghua WHERE id = ? AND deleted_at IS NULL" % _DONGHUA_COLUMNS
        row = self._conn.execute(sql, (int(donghua_id),)).fetchone()
        return _row_to_donghua(row) if row is not None else None

    def get_by_mal_id(self, mal_id: int) -> Optional[Donghua]:
        sql = "SELECT %s FROM donghua WHERE mal_id = ? AND deleted_at IS NULL" % _DONGHUA_COLUMNS
        row = self._conn.execute(sql, (int(mal_id),)).fetchone()
        return _row_to_donghua(row) if row is not None else None

    def counts_by_status(self) -> Dict[str, int]:
        counts = {s.value: 0 for s in Status}
        sql = "SELECT status, count(*) AS n FROM donghua WHERE deleted_at IS NULL GROUP BY status"
        for row in self._conn.execute(sql).fetchall():
            key = row["status"]
            if key in counts:
                counts[key] = int(row["n"])
        return counts

    # --- zapis -----------------------------------------------------------------
    def insert(self, d: Donghua) -> int:
        now = utc_now_iso()
        added = d.added_at or now
        if d.mal_id is not None:
            row = self._conn.execute(
                "SELECT id, deleted_at FROM donghua WHERE mal_id = ?", (d.mal_id,)
            ).fetchone()
            if row is not None:
                if row["deleted_at"] is None:
                    return int(row["id"])  # już w bibliotece: bez duplikatu i bez błędu
                # REVIVE soft-deleted (bug produkcyjny: UNIQUE(mal_id) po usunięciu
                # blokował ponowne dodanie tej samej serii)
                sql = (
                    "UPDATE donghua SET anilist_id=?, provider=?, title=?, title_alt=?, "
                    "total_episodes=?, current_episode=?, status=?, score=?, media_type=?, "
                    "start_year=?, cover_key=?, universe_id=?, universe_order=?, note=?, "
                    "added_at=?, updated_at=?, deleted_at=NULL WHERE id=?"
                )
                params = (
                    d.anilist_id,
                    d.provider,
                    d.title,
                    d.title_alt,
                    int(d.total_episodes),
                    int(d.current_episode),
                    d.status.value,
                    d.score,
                    d.media_type.value
                    if isinstance(d.media_type, MediaType)
                    else str(d.media_type or ""),
                    d.start_year,
                    d.cover_key,
                    d.universe_id,
                    d.universe_order,
                    d.note,
                    added,
                    now,
                    int(row["id"]),
                )
                with self._conn:
                    self._conn.execute(sql, params)
                return int(row["id"])
        sql = (
            "INSERT INTO donghua (mal_id, anilist_id, provider, title, title_alt, "
            "total_episodes, current_episode, status, score, media_type, start_year, "
            "cover_key, universe_id, universe_order, note, added_at, updated_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)"
        )
        params = (
            d.mal_id,
            d.anilist_id,
            d.provider,
            d.title,
            d.title_alt,
            int(d.total_episodes),
            int(d.current_episode),
            d.status.value,
            d.score,
            d.media_type.value if isinstance(d.media_type, MediaType) else str(d.media_type or ""),
            d.start_year,
            d.cover_key,
            d.universe_id,
            d.universe_order,
            d.note,
            added,
            now,
        )
        with self._conn:
            cur = self._conn.execute(sql, params)
        return int(cur.lastrowid or 0)

    def update_progress(
        self, donghua_id: int, episode: int, status: Status, now_iso: Optional[str] = None
    ) -> bool:
        sql = (
            "UPDATE donghua SET current_episode = ?, status = ?, updated_at = ? "
            "WHERE id = ? AND deleted_at IS NULL"
        )
        with self._conn:
            cur = self._conn.execute(
                sql, (int(episode), status.value, now_iso or utc_now_iso(), int(donghua_id))
            )
        return cur.rowcount > 0

    def update_full(self, d: Donghua) -> bool:
        sql = (
            "UPDATE donghua SET mal_id=?, anilist_id=?, provider=?, title=?, title_alt=?, "
            "total_episodes=?, current_episode=?, status=?, score=?, media_type=?, "
            "start_year=?, cover_key=?, universe_id=?, universe_order=?, note=?, updated_at=? "
            "WHERE id = ?"
        )
        params = (
            d.mal_id,
            d.anilist_id,
            d.provider,
            d.title,
            d.title_alt,
            int(d.total_episodes),
            int(d.current_episode),
            d.status.value,
            d.score,
            d.media_type.value if isinstance(d.media_type, MediaType) else str(d.media_type or ""),
            d.start_year,
            d.cover_key,
            d.universe_id,
            d.universe_order,
            d.note,
            utc_now_iso(),
            int(d.id),
        )
        with self._conn:
            cur = self._conn.execute(sql, params)
        return cur.rowcount > 0

    def soft_delete(self, donghua_id: int, now_iso: Optional[str] = None) -> bool:
        sql = "UPDATE donghua SET deleted_at = ? WHERE id = ? AND deleted_at IS NULL"
        with self._conn:
            cur = self._conn.execute(sql, (now_iso or utc_now_iso(), int(donghua_id)))
        return cur.rowcount > 0

    def restore(self, donghua_id: int) -> bool:
        sql = "UPDATE donghua SET deleted_at = NULL WHERE id = ?"
        with self._conn:
            cur = self._conn.execute(sql, (int(donghua_id),))
        return cur.rowcount > 0

    def purge_deleted(self, older_than_iso: str) -> int:
        """Trwałe usunięcie soft-deleted starszych niż próg (FK cascade czyści linki)."""
        sql = "DELETE FROM donghua WHERE deleted_at IS NOT NULL AND deleted_at < ?"
        with self._conn:
            cur = self._conn.execute(sql, (older_than_iso,))
        return int(cur.rowcount or 0)

    # --- uniwersa (§4.9) ----------------------------------------------------------
    def set_universe(
        self, donghua_id: int, universe_id: Optional[int], universe_order: Optional[int] = None
    ) -> bool:
        sql = "UPDATE donghua SET universe_id = ?, universe_order = ? WHERE id = ?"
        with self._conn:
            cur = self._conn.execute(sql, (universe_id, universe_order, int(donghua_id)))
        return cur.rowcount > 0

    def list_by_universe(self, universe_id: int) -> List[Donghua]:
        sql = (
            "SELECT %s FROM donghua WHERE universe_id = ? AND deleted_at IS NULL "
            "ORDER BY universe_order IS NULL, universe_order, updated_at DESC" % _DONGHUA_COLUMNS
        )
        return [_row_to_donghua(r) for r in self._conn.execute(sql, (int(universe_id),)).fetchall()]


class LinksRepository:
    """Linki streamingowe pozycji (Biblia §28)."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def list_for(self, donghua_id: int) -> List[StreamingLink]:
        sql = (
            "SELECT id, donghua_id, tag, url, label, position "
            "FROM streaming_links WHERE donghua_id = ? ORDER BY position, id"
        )
        return [self._row(r) for r in self._conn.execute(sql, (int(donghua_id),)).fetchall()]

    def list_all(self) -> Dict[int, List[StreamingLink]]:
        sql = (
            "SELECT id, donghua_id, tag, url, label, position "
            "FROM streaming_links ORDER BY position, id"
        )
        out: Dict[int, List[StreamingLink]] = {}
        for r in self._conn.execute(sql).fetchall():
            out.setdefault(int(r["donghua_id"]), []).append(self._row(r))
        return out

    def replace_links(self, donghua_id: int, links: List[StreamingLink]) -> None:
        """Atomowa podmiana kompletu linków (DELETE+INSERT w jednej transakcji)."""
        with self._conn:
            self._conn.execute(
                "DELETE FROM streaming_links WHERE donghua_id = ?", (int(donghua_id),)
            )
            for pos, link in enumerate(links):
                self._conn.execute(
                    "INSERT INTO streaming_links (donghua_id, tag, url, label, position) "
                    "VALUES (?,?,?,?,?)",
                    (int(donghua_id), link.tag, link.url, link.label, pos),
                )

    @staticmethod
    def _row(r: sqlite3.Row) -> StreamingLink:
        return StreamingLink(
            id=int(r["id"]),
            donghua_id=int(r["donghua_id"]),
            tag=r["tag"] or "",
            url=r["url"] or "",
            label=r["label"],
            position=int(r["position"] or 0),
        )


class UniverseRepository:
    """Uniwersa/franczyzy (§4.9.3)."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def create(self, name: str, mal_anchor_id: Optional[int] = None) -> int:
        name = (name or "").strip()
        if not name:
            raise ValueError("Nazwa uniwersum nie może być pusta")
        existing = self.get_by_name(name)
        if existing is not None:
            return existing.id
        sql = "INSERT INTO universes (name, mal_anchor_id, created_at) VALUES (?,?,?)"
        with self._conn:
            cur = self._conn.execute(sql, (name, mal_anchor_id, utc_now_iso()))
        return int(cur.lastrowid or 0)

    def get_by_name(self, name: str) -> Optional[Universe]:
        sql = (
            "SELECT id, name, mal_anchor_id, created_at FROM universes "
            "WHERE name = ? COLLATE NOCASE"
        )
        row = self._conn.execute(sql, ((name or "").strip(),)).fetchone()
        return self._row(row) if row is not None else None

    def get(self, universe_id: int) -> Optional[Universe]:
        sql = "SELECT id, name, mal_anchor_id, created_at FROM universes WHERE id = ?"
        row = self._conn.execute(sql, (int(universe_id),)).fetchone()
        return self._row(row) if row is not None else None

    def list_all(self) -> List[Universe]:
        sql = (
            "SELECT id, name, mal_anchor_id, created_at FROM universes ORDER BY name COLLATE NOCASE"
        )
        return [self._row(r) for r in self._conn.execute(sql).fetchall()]

    def rename(self, universe_id: int, new_name: str) -> bool:
        new_name = (new_name or "").strip()
        if not new_name:
            return False
        sql = "UPDATE universes SET name = ? WHERE id = ?"
        with self._conn:
            cur = self._conn.execute(sql, (new_name, int(universe_id)))
        return cur.rowcount > 0

    def delete(self, universe_id: int) -> bool:
        """Usunięcie uniwersum NIE usuwa pozycji (FK ON DELETE SET NULL)."""
        sql = "DELETE FROM universes WHERE id = ?"
        with self._conn:
            cur = self._conn.execute(sql, (int(universe_id),))
        return cur.rowcount > 0

    @staticmethod
    def _row(r: sqlite3.Row) -> Universe:
        return Universe(
            id=int(r["id"]),
            name=r["name"] or "",
            mal_anchor_id=r["mal_anchor_id"],
            created_at=r["created_at"] or "",
        )
