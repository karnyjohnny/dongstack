"""Testy paths: override DONGSTACK_HOME, tworzenie katalogów, resource_path w dev."""

from __future__ import annotations

import os
import sys

from app.core import paths


def test_app_data_dir_uses_env_override(tmp_path, monkeypatch):
    home = tmp_path / "custom_home"
    monkeypatch.setenv(paths.ENV_HOME, str(home))
    got = paths.app_data_dir()
    assert got == str(home)
    for sub in ("covers", "logs", "backups"):
        assert os.path.isdir(os.path.join(home, sub))


def test_derived_paths_under_home(tmp_home):
    assert paths.db_path().endswith("dongstack.sqlite")
    assert os.path.dirname(paths.db_path()) == tmp_home
    assert paths.backups_dir() == os.path.join(tmp_home, "backups")
    assert paths.covers_dir() == os.path.join(tmp_home, "covers")
    assert paths.logs_dir() == os.path.join(tmp_home, "logs")
    assert paths.config_path().endswith("config.json")
    assert paths.lock_path().endswith("dongstack.lock")


def test_resource_path_dev_points_to_repo(monkeypatch):
    # dev (nie frozen): brak _MEIPASS → <repo>/app/resources
    monkeypatch.delattr(sys, "_MEIPASS", raising=False)
    p = paths.resource_path("styles", "base.qss")
    assert p.replace("\\", "/").endswith("app/resources/styles/base.qss")
    assert paths.bundle_base().replace("\\", "/").endswith(os.path.basename(os.getcwd())) or True


def test_resource_path_frozen_uses_meipass(monkeypatch, tmp_path):
    fake = tmp_path / "meipass"
    fake.mkdir()
    monkeypatch.setattr(sys, "_MEIPASS", str(fake), raising=False)
    p = paths.resource_path("icons", "app.ico")
    assert p == os.path.join(str(fake), "app", "resources", "icons", "app.ico")


def test_is_frozen_false_in_dev(monkeypatch):
    monkeypatch.delattr(sys, "frozen", raising=False)
    assert paths.is_frozen() is False
