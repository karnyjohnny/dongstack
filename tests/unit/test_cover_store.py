"""Testy CoverStore: deterministyczne klucze, sharding, zapis/odczyt, remove."""

from __future__ import annotations

import os

from app.data.cover_store import DEFAULT_SIZE_TAG, CoverStore, cover_key

FAKE_JPEG = b"\xff\xd8\xff\xe0FAKEJPEGDATA"


def test_key_deterministic_and_size_sensitive():
    url = "https://cdn.myanimelist.net/images/anime/1283/90230.jpg"
    k1 = cover_key(url)
    assert k1 == cover_key(url, DEFAULT_SIZE_TAG)
    assert k1 != cover_key(url, "72x88")
    assert k1 != cover_key(url + "x")


def test_put_get_has_sharding(db_conn, tmp_home):
    covers = os.path.join(tmp_home, "covers")
    store = CoverStore(db_conn, covers)
    url = "https://cdn.myanimelist.net/images/x.jpg"
    key = cover_key(url)
    path = store.put(key, url, FAKE_JPEG)
    assert store.has(key)
    assert store.get_bytes(key) == FAKE_JPEG
    assert store.count() == 1
    # sharding: podkatalog = pierwsze 2 znaki klucza
    assert os.path.basename(os.path.dirname(path)) == key[:2]
    assert path == store.path_for(key)


def test_put_overwrites_atomically(db_conn, tmp_home):
    store = CoverStore(db_conn, os.path.join(tmp_home, "covers"))
    key = cover_key("https://example.com/a.jpg")
    store.put(key, "https://example.com/a.jpg", FAKE_JPEG)
    store.put(key, "https://example.com/a.jpg", FAKE_JPEG + b"v2")
    assert store.get_bytes(key) == FAKE_JPEG + b"v2"
    assert store.count() == 1


def test_get_missing_returns_none(db_conn, tmp_home):
    store = CoverStore(db_conn, os.path.join(tmp_home, "covers"))
    assert store.get_bytes(cover_key("https://example.com/missing.jpg")) is None
    assert store.has(cover_key("https://example.com/missing.jpg")) is False


def test_remove(db_conn, tmp_home):
    store = CoverStore(db_conn, os.path.join(tmp_home, "covers"))
    key = cover_key("https://example.com/rm.jpg")
    store.put(key, "https://example.com/rm.jpg", FAKE_JPEG)
    store.remove(key)
    assert store.has(key) is False
    assert store.count() == 0
