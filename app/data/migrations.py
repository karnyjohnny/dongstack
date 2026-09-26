"""app/data/migrations.py — wersjonowanie schematu + backup (specyfikacja §4.3–§4.4).

Mechanika:
- wersja w `PRAGMA user_version`; migracje sekwencyjne w jawnych transakcjach,
- backup PRZED pierwszą migracją istniejącej bazy: `VACUUM INTO` (retencja 3),
- odzyskiwanie bazy uszkodzonej: rename → .corrupt-<ts> + przywrócenie backupu.

SQL jest statyczny (DDL) — brak danych użytkownika, R13 dotyczy zapytań DML
w repository.py (parametryzowane).
"""

from __future__ import annotations

import os
import shutil
import sqlite3
import time
from typing import Dict, List, Optional

from app.core.logging_setup import get_logger

log = get_logger("data.migrations")

SCHEMA_VERSION = 2
BACKUP_KEEP = 3

# --- DDL v1 (schemat z uniwersami od pierwszego wydania — bez migracji danych) --
_DDL_V1: List[str] = [
    """
    CREATE TABLE IF NOT EXISTS universes (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        name            TEXT NOT NULL,
        mal_anchor_id   INTEGER,
        created_at      TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS donghua (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        mal_id          INTEGER UNIQUE,
        anilist_id      INTEGER,
        provider        TEXT NOT NULL DEFAULT 'manual',
        title           TEXT NOT NULL,
        title_alt       TEXT,
        total_episodes  INTEGER NOT NULL DEFAULT 0,
        current_episode INTEGER NOT NULL DEFAULT 0,
        status          TEXT NOT NULL DEFAULT 'planned'
                        CHECK (status IN ('watching','completed','planned','dropped')),
        score           INTEGER CHECK (score IS NULL OR score BETWEEN 1 AND 10),
        media_type      TEXT,
        start_year      INTEGER,
        cover_key       TEXT,
        universe_id     INTEGER REFERENCES universes(id) ON DELETE SET NULL,
        universe_order  INTEGER,
        note            TEXT,
        added_at        TEXT NOT NULL,
        updated_at      TEXT NOT NULL,
        deleted_at      TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS streaming_links (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        donghua_id  INTEGER NOT NULL REFERENCES donghua(id) ON DELETE CASCADE,
        platform    TEXT NOT NULL
                    CHECK (platform IN ('iqiyi','bilibili','youtube','crunchyroll','other')),
        url         TEXT NOT NULL,
        label       TEXT,
        position    INTEGER NOT NULL DEFAULT 0
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS api_cache (
        cache_key   TEXT PRIMARY KEY,
        provider    TEXT NOT NULL,
        payload     TEXT NOT NULL,
        fetched_at  INTEGER NOT NULL,
        ttl_s       INTEGER NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS cover_cache (
        cache_key   TEXT PRIMARY KEY,
        url         TEXT NOT NULL,
        path        TEXT NOT NULL,
        fetched_at  INTEGER NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS meta (
        k TEXT PRIMARY KEY,
        v TEXT NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_donghua_status_updated ON donghua(status, updated_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_donghua_title ON donghua(title COLLATE NOCASE)",
    "CREATE INDEX IF NOT EXISTS idx_donghua_alive ON donghua(deleted_at)",
    "CREATE INDEX IF NOT EXISTS idx_donghua_universe ON donghua(universe_id, universe_order)",
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_universes_name ON universes(name COLLATE NOCASE)",
    "CREATE INDEX IF NOT EXISTS idx_links_donghua ON streaming_links(donghua_id)",
    "CREATE INDEX IF NOT EXISTS idx_cache_fetched ON api_cache(provider, fetched_at)",
]

# v2: linki streamingowe jako wolne [TAG][URL] zamiast sztywnego enumu platform
# (feedback produkcyjny M6-fix: własne domeny, blogi, mirror-y).
_DDL_V2: List[str] = [
    """
    CREATE TABLE IF NOT EXISTS streaming_links_new (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        donghua_id  INTEGER NOT NULL REFERENCES donghua(id) ON DELETE CASCADE,
        tag         TEXT NOT NULL DEFAULT '',
        url         TEXT NOT NULL,
        label       TEXT,
        position    INTEGER NOT NULL DEFAULT 0
    )
    """,
    """
    INSERT INTO streaming_links_new (id, donghua_id, tag, url, label, position)
    SELECT id, donghua_id, platform, url, label, position FROM streaming_links
    """,
    "DROP TABLE streaming_links",
    "ALTER TABLE streaming_links_new RENAME TO streaming_links",
    "CREATE INDEX IF NOT EXISTS idx_links_donghua ON streaming_links(donghua_id)",
]

MIGRATIONS: Dict[int, List[str]] = {
    1: _DDL_V1,
    2: _DDL_V2,
}


def get_user_version(conn: sqlite3.Connection) -> int:
    row = conn.execute("PRAGMA user_version").fetchone()
    return int(row[0]) if row is not None else 0


def _set_user_version(conn: sqlite3.Connection, version: int) -> None:
    conn.execute("PRAGMA user_version = %d" % int(version))


def ensure_schema(conn: sqlite3.Connection, backups_dir: Optional[str] = None) -> int:
    """Doprowadza schemat do SCHEMA_VERSION. Zwraca wersję końcową.

    - świeża baza (user_version=0, brak tabel): DDL bez backupu,
    - istniejąca baza z niższą wersją: backup VACUUM INTO → migracje,
    - każda migracja w jednej transakcji (`with conn:`).
    """
    current = get_user_version(conn)
    if current == SCHEMA_VERSION:
        return current
    if current > SCHEMA_VERSION:
        # baza z NOWSZEJ wersji aplikacji — nie tykamy, komunikat dla użytkownika
        raise sqlite3.DatabaseError(
            "Baza danych pochodzi z nowszej wersji DongStack (schemat v%d > v%d)."
            % (current, SCHEMA_VERSION)
        )
    has_tables = conn.execute(
        "SELECT count(*) FROM sqlite_master WHERE type='table' AND name='donghua'"
    ).fetchone()[0]
    if current > 0 and has_tables and backups_dir:
        create_backup(conn, backups_dir)
    for version in range(current + 1, SCHEMA_VERSION + 1):
        statements = MIGRATIONS[version]
        with conn:  # transakcja: wszystko albo nic
            for stmt in statements:
                conn.execute(stmt)
            _set_user_version(conn, version)
        log.info("migracja schematu -> v%d zastosowana", version)
    return get_user_version(conn)


def create_backup(
    conn: sqlite3.Connection, backups_dir: str, keep: int = BACKUP_KEEP
) -> Optional[str]:
    """Kopia zapasowa przez `VACUUM INTO` (SQLite ≥3.27) + retencja `keep` najnowszych."""
    try:
        if not os.path.isdir(backups_dir):
            os.makedirs(backups_dir)
        stamp = time.strftime("%Y%m%d-%H%M%S")
        dst = os.path.join(backups_dir, "dongstack-%s.sqlite" % stamp)
        conn.execute("VACUUM INTO ?", (dst,))  # parametryzowane (R13)
        _prune_backups(backups_dir, keep)
        log.info("backup bazy: %s", dst)
        return dst
    except (OSError, sqlite3.Error) as exc:
        log.warning("backup nieudany: %s", exc)
        return None


def _prune_backups(backups_dir: str, keep: int) -> None:
    try:
        names = [
            n
            for n in os.listdir(backups_dir)
            if n.startswith("dongstack-") and n.endswith(".sqlite")
        ]
    except OSError:
        return
    names.sort()  # stempl czasowy w nazwie → sort leksykalny = chronologiczny
    for old in names[: -max(1, keep)] if len(names) > keep else []:
        try:
            os.remove(os.path.join(backups_dir, old))
        except OSError:
            pass


def recover_if_corrupt(db_file: str, backups_dir: str) -> Optional[str]:
    """Jeśli baza jest nieotwieralna/uszkodzona: odłożenie .corrupt-<ts> + restore backupu.

    Zwraca komunikat dla użytkownika (lub None gdy wszystko OK).
    """
    try:
        conn = sqlite3.connect(db_file, timeout=3.0)
        try:
            conn.execute("SELECT count(*) FROM sqlite_master").fetchone()
            conn.execute("PRAGMA integrity_check(1)").fetchone()
        finally:
            conn.close()
        return None
    except sqlite3.DatabaseError as exc:
        log.error("baza uszkodzona (%s) — próba odtworzenia z backupu", exc)

    stamp = time.strftime("%Y%m%d-%H%M%S")
    try:
        if os.path.isfile(db_file):
            os.replace(db_file, db_file + ".corrupt-" + stamp)
        for sidecar in (db_file + "-wal", db_file + "-shm"):
            if os.path.isfile(sidecar):
                os.remove(sidecar)
    except OSError as exc:
        return "Nie udało się zabezpieczyć uszkodzonej bazy: %s" % exc

    restored = _restore_latest_backup(backups_dir, db_file)
    if restored:
        return (
            "Baza danych była uszkodzona — odtworzono z kopii %s. "
            "Uszkodzony plik zachowano jako %s.corrupt-%s" % (restored, db_file, stamp)
        )
    return (
        "Baza danych była uszkodzona i brak kopii zapasowych — utworzono nową, pustą bazę. "
        "Uszkodzony plik zachowano jako %s.corrupt-%s" % (db_file, stamp)
    )


def _restore_latest_backup(backups_dir: str, db_file: str) -> Optional[str]:
    try:
        names = sorted(
            n
            for n in os.listdir(backups_dir)
            if n.startswith("dongstack-") and n.endswith(".sqlite")
        )
    except OSError:
        return None
    for name in reversed(names):
        src = os.path.join(backups_dir, name)
        try:
            shutil.copy2(src, db_file)
            return name
        except OSError:
            continue
    return None
