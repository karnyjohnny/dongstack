"""Selftest GUI w --selftest (budżety §7.3) — pełny przebieg M3 (wiring)."""

from __future__ import annotations

import json
import os

from app import main as main_mod


def test_selftest_m3_ok(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("DONGSTACK_HOME", raising=False)
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    code = main_mod.selftest()
    out = capsys.readouterr().out.strip()
    assert code == 0, out
    report = json.loads(out.splitlines()[-1])
    assert report["ok"] is True
    assert report["phase"] == "M4-api"
    assert 0 <= report["increment_p95_ms"] <= 8.0  # gate G2 (offscreen CI)
    assert report["rows_alive"] == 300
    assert report["threads"] <= 3
    for key in ("gui_fill300_ms", "gui_rebuild300_ms", "increment_p95_ms"):
        assert key in report and report[key] >= 0
    assert "DONGSTACK_HOME" not in os.environ
