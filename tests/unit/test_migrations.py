"""Testy migracji: świeża baza, idempotencja, backup + retencja, corrupt-recovery."""

from __future__ import annotations

import os
import sqlite3
import time

from app.data import migrations
from app.data.connection import open_connection


def test_ensure_schema_fresh(db_conn):
    version = migrations.get_user_version(db_conn)
    assert version == migrations.SCHEMA_VERSION == 2
    tables = {
        r[0]
        for r in db_conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    }
    for expected in ("universes", "donghua", "streaming_links", "api_cache", "cover_cache", "meta"):
        assert expected in tables


def test_ensure_schema_idempotent(db_conn):
    assert migrations.ensure_schema(db_conn) == migrations.SCHEMA_VERSION
    assert (
        migrations.ensure_schema(db_conn) == migrations.SCHEMA_VERSION
    )  # drugie wywołanie bez efektu


def test_wal_and_pragmas(db_conn):
    assert db_conn.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
    assert db_conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1


def test_create_backup_and_retention(tmp_home, db_conn):
    backups = os.path.join(tmp_home, "backups")
    created = []
    for _ in range(5):
        # stemple sekundowe — wymuś różne nazwy
        path = migrations.create_backup(db_conn, backups)
        assert path is not None
        created.append(path)
        time.sleep(1.05)
    files = sorted(os.listdir(backups))
    assert len(files) == migrations.BACKUP_KEEP  # retencja 3
    assert all(f.startswith("dongstack-") and f.endswith(".sqlite") for f in files)
    # najnowsze przetrwały
    assert os.path.basename(created[-1]) in files


def test_backup_is_valid_database(tmp_home, db_conn):
    from app.data.repository import DonghuaRepository
    from app.domain.models import Donghua

    repo = DonghuaRepository(db_conn)
    repo.insert(Donghua(title="Backup Check", total_episodes=10))
    backups = os.path.join(tmp_home, "backups")
    path = migrations.create_backup(db_conn, backups)
    assert path is not None
    bak = sqlite3.connect(path)
    try:
        n = bak.execute("SELECT count(*) FROM donghua").fetchone()[0]
        assert n == 1
    finally:
        bak.close()


def test_migration_from_newer_schema_raises(db_conn):
    db_conn.execute("PRAGMA user_version = 99")
    try:
        migrations.ensure_schema(db_conn)
        assert False, "oczekiwano DatabaseError"
    except sqlite3.DatabaseError:
        pass


def test_recover_if_corrupt_restores_backup(tmp_home):
    db_file = os.path.join(tmp_home, "corrupt.sqlite")
    backups = os.path.join(tmp_home, "backups")

    # 1) zdrowa baza + backup
    conn = open_connection(db_file)
    migrations.ensure_schema(conn)
    conn.execute("INSERT INTO donghua (title, added_at, updated_at) VALUES ('Ocalona','x','x')")
    conn.commit()
    migrations.create_backup(conn, backups)
    conn.close()

    # 2) uszkodzenie pliku
    with open(db_file, "wb") as fh:
        fh.write(b"TO NIE JEST SQLITE" * 100)
    for suffix in ("-wal", "-shm"):
        p = db_file + suffix
        if os.path.isfile(p):
            os.remove(p)

    msg = migrations.recover_if_corrupt(db_file, backups)
    assert msg is not None and "odtworzono" in msg

    conn2 = open_connection(db_file)
    try:
        rows = conn2.execute("SELECT title FROM donghua").fetchall()
        assert [r["title"] for r in rows] == ["Ocalona"]
        corrupt_files = [f for f in os.listdir(tmp_home) if ".corrupt-" in f]
        assert corrupt_files, "uszkodzony plik musi być zachowany do analizy"
    finally:
        conn2.close()


def test_recover_noop_on_healthy(db_conn, tmp_home):
    db_file = os.path.join(tmp_home, "test.sqlite")
    assert migrations.recover_if_corrupt(db_file, os.path.join(tmp_home, "backups")) is None
