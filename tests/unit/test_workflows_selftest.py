"""R16 (v1.2.1): statyczna higiena workflowów CI przy selfteście frozen exe.

Historia (r10): oba gate'y M9 padły nie z winy aplikacji, a skryptu:

* ci.yml — `& dist-smoke\\...\\DongStack.exe --selftest` dla exe *windowed*
  (GUI subsystem) NIE czeka na zakończenie procesu: `$LASTEXITCODE` był pusty,
  a `Test-Path` raportu odpalał się zanim exe zdążył go zapisać (raport istniał
  — krok `upload` go znalazł).
* release.yml — `& $exe --selftest | Tee-Object $out`, przy jednoczesnym
  `DONGSTACK_SELFTEST_OUT=$out`: dwóch zapisujących ten sam plik, a stdout exe
  zaczyna się od `selftest-report: …` → `ConvertFrom-Json: Unexpected character
  … : s`.

Testy poniżej pilnują, żeby te wzorce nie wróciły.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

WORKFLOWS = {
    "ci": Path(__file__).resolve().parents[2] / ".github" / "workflows" / "ci.yml",
    "release": Path(__file__).resolve().parents[2] / ".github" / "workflows" / "release.yml",
}

START_PROCESS_RE = re.compile(r"Start-Process\b[^\n]*")


def _text(name: str) -> str:
    path = WORKFLOWS[name]
    assert path.is_file(), f"brak workflowa: {path}"
    return path.read_text(encoding="utf-8")


def _selftest_blocks(text: str) -> list:
    """Kroki workflowa, które odpalają exe z `--selftest` (gate M9)."""
    return [c for c in re.split(r"\n(?=      - name: )", text) if "--selftest" in c]


@pytest.mark.parametrize("name", sorted(WORKFLOWS))
def test_no_bare_ampersand_launch(name: str) -> None:
    """Zakaz `& exe --selftest` (windowed app nie jest czekany przez PowerShell)."""
    for block in _selftest_blocks(_text(name)):
        for line in block.splitlines():
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            assert not re.search(r"&\s*\$?\S*--selftest", stripped), (
                f"{name}: uruchomienie przez '&' nie czeka na windowed exe — "
                "użyj Start-Process -Wait -PassThru (R16)"
            )
            assert not re.search(r"&\s*\$exe\b", stripped), (
                f"{name}: '& $exe' bez pipeline nie czeka (R16)"
            )


@pytest.mark.parametrize("name", sorted(WORKFLOWS))
def test_uses_start_process_wait_passthru(name: str) -> None:
    """Każde odpalenie exe z --selftest musi czekać i brać kod z $p.ExitCode."""
    blocks = _selftest_blocks(_text(name))
    assert blocks, f"{name}: brak kroku selftest (oczekiwany gate M9)"
    for block in blocks:
        launch = [ln for ln in block.splitlines() if "Start-Process" in ln and "--selftest" in ln]
        assert launch, f"{name}: brak `Start-Process … --selftest` (R16)"
        line = launch[0]
        for flag in ("-NoNewWindow", "-Wait", "-PassThru"):
            assert flag in line, f"{name}: Start-Process bez {flag} (R16)"
        assert re.search(r"\$p\s*=\s*Start-Process", line), (
            f"{name}: wynik Start-Process nieprzypisany"
        )
        assert ".ExitCode" in block, f"{name}: kod wyjścia musi pochodzić z $p.ExitCode (R16)"


@pytest.mark.parametrize("name", sorted(WORKFLOWS))
def test_report_not_parsed_from_stdout(name: str) -> None:
    """Raport czytamy z pliku; stdout windowed exe nie jest źródłem prawdy.

    Dodatkowo: `Tee-Object` nie może celować w tę samą ścieżkę co
    `DONGSTACK_SELFTEST_OUT` (wyścig dwóch zapisujących — bug release.yml v1.2.0).
    """
    for block in _selftest_blocks(_text(name)):
        tee_targets = set(re.findall(r"Tee-Object\s+([^\s|]+)", block))
        report_vars = set(re.findall(r"DONGSTACK_SELFTEST_OUT\s*=\s*([^\s]+)", block))
        assert not (tee_targets & report_vars), (
            f"{name}: Tee-Object pisze do pliku raportu ({tee_targets & report_vars}) — "
            "ConvertFrom-Json dostanie 'selftest-report: …' zamiast JSON (R16)"
        )
        assert "ConvertFrom-Json" in block, f"{name}: gate M9 musi parsować raport JSON"
        # gate: kod wyjscia 0 ORAZ ok == true
        assert re.search(r"\$code\s*-ne\s*0", block), f"{name}: gate bez sprawdzenia kodu wyjścia"
        assert re.search(r"\$report\.ok\s*-ne\s*\$true", block), (
            f"{name}: gate bez sprawdzenia report.ok"
        )


def test_ci_report_path_is_explicit_env() -> None:
    """ci.yml: ścieżka raportu ustawiona jawnie (determinizm, nie 'obok exe')."""
    text = _text("ci")
    assert "DONGSTACK_SELFTEST_OUT" in text
    step = next(b for b in _selftest_blocks(text) if "dist-smoke" in b)
    # single-quoted (w double-quoted YAML "\\D" = nieznany escape -> blad parsera)
    assert re.search(
        r"DONGSTACK_SELFTEST_OUT:\s*['\"]?dist-smoke\\DongStack\\selftest-report\.json", text
    ), "ci.yml: oczekiwany jawny env DONGSTACK_SELFTEST_OUT dla smoke"
    assert "$rp = $env:DONGSTACK_SELFTEST_OUT" in step


def test_release_report_uses_matrix_names() -> None:
    """release.yml: raport per (arch × package), artefakt `selftest-*.json`."""
    text = _text("release")
    assert re.search(
        r"selftest-\$\{\{\s*matrix\.arch\s*\}\}-\$\{\{\s*matrix\.package\s*\}\}\.json", text
    )
