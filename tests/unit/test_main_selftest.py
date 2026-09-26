"""Test entrypointu M1: --selftest (rdzeń danych) i --init-db w izolowanym HOME."""

from __future__ import annotations

import json
import os

from app import main as main_mod


def test_selftest_returns_zero_and_report(tmp_path, monkeypatch, capsys):
    # selftest sam ustawia DONGSTACK_HOME na katalog tymczasowy
    monkeypatch.delenv("DONGSTACK_HOME", raising=False)
    code = main_mod.selftest()
    out = capsys.readouterr().out.strip()
    assert code == 0, out
    from app.data import migrations

    report = json.loads(out.splitlines()[-1])
    assert report["ok"] is True
    assert report["rows_alive"] == 300
    assert report["schema_version"] == migrations.SCHEMA_VERSION
    assert report["threads"] <= 3  # R7: rdzeń nie tworzy dodatkowych wątków
    assert "insert300_ms" in report and "update200_ms" in report
    # po selfteście env posprzątany
    assert "DONGSTACK_HOME" not in os.environ


def test_init_db_cli(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("DONGSTACK_HOME", str(tmp_path))
    code = main_mod.main(["--init-db"])
    assert code == 0
    out = capsys.readouterr().out
    from app.data import migrations

    info = json.loads(out)
    assert info["schema_version"] == migrations.SCHEMA_VERSION
    assert os.path.isfile(os.path.join(str(tmp_path), "dongstack.sqlite"))
    # idempotencja: drugie uruchomienie bez migracji
    code2 = main_mod.main(["--init-db"])
    assert code2 == 0


def test_default_mode_delegates_to_gui(tmp_path, monkeypatch, capsys):
    """Tryb domyślny (M2+) = run_gui; test bez uruchamiania pętli zdarzeń."""
    monkeypatch.setenv("DONGSTACK_HOME", str(tmp_path))
    calls = {}

    def fake_run_gui(config, demo=False):
        calls["demo"] = demo
        calls["provider"] = config.preferred_provider
        return 0

    monkeypatch.setattr(main_mod, "run_gui", fake_run_gui)
    code = main_mod.main([])
    assert code == 0
    assert calls == {"demo": False, "provider": "mal"}

    code_demo = main_mod.main(["--demo"])
    assert code_demo == 0
    assert calls["demo"] is True


def test_version_flag(capsys):
    import pytest

    from app import __version__

    with pytest.raises(SystemExit) as exc:
        main_mod.main(["--version"])
    assert exc.value.code == 0
    assert __version__ in capsys.readouterr().out
