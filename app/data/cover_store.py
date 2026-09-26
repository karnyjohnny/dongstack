"""app/data/cover_store.py — okładki na dysku + indeks w SQLite (specyfikacja §4.8).

Pliki: covers\\<klucz[:2]>\\<klucz>.jpg (sharding prefixem — limit plików/katalog).
Klucz: sha1(url + rozmiar docelowy) — ten sam URL w innym rozmiarze to inny wpis.
Zawartość pliku to JPEG już PRZESKALOWANY przez worker (QImageReader.setScaledSize)
— ta warstwa zapisuje/odczytuje wyłącznie gotowe bajty (bez Qt).
"""

from __future__ import annotations

import hashlib
import os
import sqlite3
from typing import Optional

from app.core.timeutil import utc_now_epoch

DEFAULT_SIZE_TAG = "120x170"  # aspect 225/318 (feedback UI); ~2× karta 57×80


def cover_key(url: str, size_tag: str = DEFAULT_SIZE_TAG) -> str:
    raw = "%s|%s" % (url or "", size_tag)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


class CoverStore:
    def __init__(self, conn: sqlite3.Connection, covers_dir: str) -> None:
        self._conn = conn
        self._dir = covers_dir

    # --- ścieżki -------------------------------------------------------------
    def path_for(self, key: str) -> str:
        return os.path.join(self._dir, key[:2], key + ".jpg")

    def has(self, key: str) -> bool:
        return os.path.isfile(self.path_for(key))

    # --- zapis/odczyt ----------------------------------------------------------
    def put(self, key: str, url: str, data: bytes, fetched_at: Optional[int] = None) -> str:
        """Zapisuje bajty okładki + indeks. Zwraca ścieżkę pliku."""
        path = self.path_for(key)
        parent = os.path.dirname(path)
        if not os.path.isdir(parent):
            os.makedirs(parent)
        tmp = path + ".tmp"
        with open(tmp, "wb") as fh:
            fh.write(data)
        os.replace(tmp, path)  # atomowo na NTFS
        fetched = utc_now_epoch() if fetched_at is None else int(fetched_at)
        sql = (
            "INSERT INTO cover_cache (cache_key, url, path, fetched_at) VALUES (?,?,?,?) "
            "ON CONFLICT(cache_key) DO UPDATE SET url=excluded.url, "
            "path=excluded.path, fetched_at=excluded.fetched_at"
        )
        with self._conn:
            self._conn.execute(sql, (key, url, os.path.relpath(path, self._dir), fetched))
        return path

    def get_bytes(self, key: str) -> Optional[bytes]:
        path = self.path_for(key)
        try:
            with open(path, "rb") as fh:
                return fh.read()
        except OSError:
            return None

    def remove(self, key: str) -> None:
        try:
            os.remove(self.path_for(key))
        except OSError:
            pass
        with self._conn:
            self._conn.execute("DELETE FROM cover_cache WHERE cache_key = ?", (key,))

    def count(self) -> int:
        row = self._conn.execute("SELECT count(*) AS n FROM cover_cache").fetchone()
        return int(row["n"]) if row is not None else 0
