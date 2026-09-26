"""Testy ConfigService: warstwy (env > plik > default), maskowanie sekretów (R14)."""

from __future__ import annotations

import json

import pytest

from app.core.config import (
    KEY_ANIMATIONS,
    KEY_CLIENT_ID,
    KEY_CLIENT_SECRET,
    KEY_PROVIDER,
    ConfigService,
)


@pytest.fixture()
def cfg_file(tmp_path):
    return str(tmp_path / "config.json")


def test_env_wins_over_file(cfg_file):
    with open(cfg_file, "w", encoding="utf-8") as fh:
        json.dump({KEY_CLIENT_ID: "z_pliku"}, fh)
    cfg = ConfigService(config_file=cfg_file, env={KEY_CLIENT_ID: "z_env"})
    assert cfg.mal_client_id == "z_env"


def test_file_used_when_env_missing(cfg_file):
    with open(cfg_file, "w", encoding="utf-8") as fh:
        json.dump({KEY_CLIENT_ID: "z_pliku"}, fh)
    cfg = ConfigService(config_file=cfg_file, env={})
    assert cfg.mal_client_id == "z_pliku"
    assert cfg.has_client_id


def test_defaults(cfg_file):
    cfg = ConfigService(config_file=cfg_file, env={})
    assert cfg.preferred_provider == "mal"
    assert cfg.log_level == "INFO"
    assert cfg.animations_enabled is False  # R9: animacje domyślnie WYŁĄCZONE
    assert cfg.has_client_id is False


def test_set_persists_client_id(cfg_file):
    cfg = ConfigService(config_file=cfg_file, env={})
    cfg.set(KEY_CLIENT_ID, "nowy_id")
    with open(cfg_file, encoding="utf-8") as fh:
        data = json.load(fh)
    assert data[KEY_CLIENT_ID] == "nowy_id"
    # i jest widoczny po przeładowaniu
    cfg2 = ConfigService(config_file=cfg_file, env={})
    assert cfg2.mal_client_id == "nowy_id"


def test_set_refuses_secret(cfg_file):
    cfg = ConfigService(config_file=cfg_file, env={})
    with pytest.raises(ValueError):
        cfg.set(KEY_CLIENT_SECRET, "c0ffee")


def test_secret_in_file_is_ignored(cfg_file):
    # nawet gdyby ktoś ręcznie wpisał sekret do config.json — nie używamy go
    with open(cfg_file, "w", encoding="utf-8") as fh:
        json.dump({KEY_CLIENT_SECRET: "wpisany_recznie"}, fh)
    cfg = ConfigService(config_file=cfg_file, env={})
    assert cfg.get(KEY_CLIENT_SECRET) is None


def test_masked_snapshot_and_repr(cfg_file):
    cfg = ConfigService(
        config_file=cfg_file,
        env={
            KEY_CLIENT_ID: "TESTCLIENTID000111222333444555",
            KEY_CLIENT_SECRET: "TESTSECRET000111222333444555666777888990aa",
        },
    )
    snap = cfg.masked_snapshot()
    assert "TESTSECRET000111222333444555666777888990aa" not in json.dumps(snap)
    assert snap[KEY_CLIENT_SECRET].startswith("TE") and snap[KEY_CLIENT_SECRET].endswith("aa")
    assert "TESTSECRET000111222333444555666777888990aa" not in repr(cfg)


def test_secret_values_for_log_filter(cfg_file):
    cfg = ConfigService(config_file=cfg_file, env={KEY_CLIENT_SECRET: "tajny_secret_123"})
    assert cfg.secret_values() == ["tajny_secret_123"]


def test_provider_validation(cfg_file):
    cfg = ConfigService(config_file=cfg_file, env={KEY_PROVIDER: "jikan"})  # Jikan wykluczony (F11)
    assert cfg.preferred_provider == "mal"
    cfg2 = ConfigService(config_file=cfg_file, env={KEY_PROVIDER: "anilist"})
    assert cfg2.preferred_provider == "anilist"


def test_animations_flag(cfg_file):
    cfg = ConfigService(config_file=cfg_file, env={KEY_ANIMATIONS: "1"})
    assert cfg.animations_enabled is True
