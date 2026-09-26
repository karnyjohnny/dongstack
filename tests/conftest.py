"""Wspólny conftest: repo root na sys.path + fixture'y katalogów tymczasowych."""

from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import pytest  # noqa: E402


@pytest.fixture()
def tmp_home(tmp_path, monkeypatch):
    """Izolowany DONGSTACK_HOME (katalog danych aplikacji) per test."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("DONGSTACK_HOME", str(home))
    return str(home)


@pytest.fixture()
def db_conn(tmp_home):
    """Połączenie SQLite ze świeżym schematem v1 (bez plików repo)."""
    from app.data import migrations
    from app.data.connection import open_connection

    conn = open_connection(os.path.join(tmp_home, "test.sqlite"))
    migrations.ensure_schema(conn)
    yield conn
    conn.close()
