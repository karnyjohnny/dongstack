"""Testy LOGIKI pliku packaging/dongstack.spec (M6) — bez realnego freezera.

Sandbox deweloperski (Linux, statyczny CPython) nie może zbudować binarki —
PyInstaller na Linuksie wymaga interpretera z libpython shared (udokumentowane
w packaging/RELEASE_RUNBOOK.md). Prawdziwy gate freeze'a siedzi w CI (windows-2022,
job freeze-smoke w ci.yml oraz build w release.yml). Tutaj walidujemy LOGIKĘ specu:
datas, excludes, filtr translacji/pluginów Qt (_keep) i gałęzie onedir/onefile —
uruchamiając spec jako kod z zaślepkami Analysis/PYZ/EXE/COLLECT.
"""

from __future__ import annotations

import os

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SPEC = os.path.join(ROOT, "packaging", "dongstack.spec")

# syntetyczne ścieżki binariów Qt (układ jak w wheelach PyQt5-Qt5)
_BINARIES = [
    ("PyQt5/Qt5/plugins/platforms/qwindows.dll", "x", "BINARY"),
    ("PyQt5/Qt5/plugins/platforms/qoffscreen.dll", "x", "BINARY"),
    ("PyQt5/Qt5/plugins/imageformats/qjpeg.dll", "x", "BINARY"),
    ("PyQt5/Qt5/plugins/imageformats/qsvg.dll", "x", "BINARY"),
    ("PyQt5/Qt5/plugins/sqldrivers/qsqlite.dll", "x", "BINARY"),
    ("PyQt5/Qt5/translations/qt_en.qm", "x", "DATA"),
    ("PyQt5/Qt5/translations/qt_pl.qm", "x", "DATA"),
    ("PyQt5/Qt5/translations/qt_fr.qm", "x", "DATA"),
    ("vcruntime140.dll", "x", "BINARY"),
]


class _Captures:
    def __init__(self):
        self.analysis_kwargs = None
        self.datas_after = None
        self.binaries_after = None
        self.exe_kwargs = None
        self.exe_args = None
        self.collect_called = False
        self.onefile = None


def _run_spec(monkeypatch, onefile: bool) -> _Captures:
    monkeypatch.setenv("DHT_ONEFILE", "1" if onefile else "0")
    cap = _Captures()

    class Analysis:
        def __init__(self, scripts, **kwargs):
            cap.analysis_kwargs = kwargs
            cap.analysis_kwargs["_scripts"] = scripts
            self.scripts = scripts
            self.pure = "PURE"
            self.zipfiles = []
            self.binaries = list(_BINARIES)
            self.datas = [
                (
                    os.path.join(ROOT, "app", "resources", "styles"),
                    os.path.join("app", "resources", "styles"),
                ),
                (
                    os.path.join(ROOT, "app", "resources", "icons"),
                    os.path.join("app", "resources", "icons"),
                ),
                ("PyQt5/Qt5/translations/qt_fr.qm", "PyQt5/Qt5/translations"),
            ]

    class PYZ:
        def __init__(self, pure):
            self.pure = pure

    class EXE:
        def __init__(self, pyz, scripts, *args, **kwargs):
            cap.exe_kwargs = kwargs
            cap.exe_args = args
            cap.onefile = any(isinstance(a, list) for a in args)

    class COLLECT:
        def __init__(self, *args, **kwargs):
            cap.collect_called = True

    env = {
        "SPECPATH": os.path.join(ROOT, "packaging"),
        "Analysis": Analysis,
        "PYZ": PYZ,
        "EXE": EXE,
        "COLLECT": COLLECT,
    }
    with open(SPEC, encoding="utf-8") as fh:
        source = fh.read()
    exec(compile(source, SPEC, "exec"), env)
    # spec nadpisuje a.datas/a.binaries przefiltrowane przez _keep — czytamy wynik wprost
    analysis = env["a"]
    cap.binaries_after = list(analysis.binaries)
    cap.datas_after = list(analysis.datas)
    return cap


def test_spec_entrypoint_and_resources(monkeypatch):
    cap = _run_spec(monkeypatch, onefile=False)
    scripts = cap.analysis_kwargs.pop("_scripts")
    assert scripts == [os.path.join(ROOT, "app", "main.py")]
    dests = {d[1] for d in cap.analysis_kwargs["datas"]}
    assert dests == {
        os.path.join("app", "resources", "styles"),
        os.path.join("app", "resources", "icons"),
    }
    hidden = cap.analysis_kwargs["hiddenimports"]
    assert hidden[0] == "sqlite3"
    # leniwe importy main.py muszą być domknięte jawnie (bug CI z M6)
    for mod in (
        "app.data",
        "app.data.migrations",
        "app.gui.main_window",
        "app.workers.db_worker",
        "app.workers.network_worker",
    ):
        assert mod in hidden, mod


def test_spec_excludes_qt_and_dev_noise(monkeypatch):
    cap = _run_spec(monkeypatch, onefile=False)
    ex = set(cap.analysis_kwargs["excludes"])
    for banned in (
        "PyQt5.QtSvg",
        "PyQt5.QtNetwork",
        "PyQt5.QtWebEngineCore",
        "PyQt5.QtQml",
        "tkinter",
        "pytest",
        "pip",
        "PIL",
    ):
        assert banned in ex


def test_keep_filter_translations_and_plugins(monkeypatch):
    cap = _run_spec(monkeypatch, onefile=False)
    names = [b[0] for b in cap.binaries_after]
    assert "PyQt5/Qt5/translations/qt_fr.qm" not in names  # tylko en/pl
    assert "PyQt5/Qt5/translations/qt_en.qm" in names
    assert "PyQt5/Qt5/translations/qt_pl.qm" in names
    assert "PyQt5/Qt5/plugins/sqldrivers/qsqlite.dll" not in names  # SQL robimy stdlib
    assert "PyQt5/Qt5/plugins/imageformats/qsvg.dll" not in names  # QtSvg wykluczony
    assert "PyQt5/Qt5/plugins/imageformats/qjpeg.dll" in names  # okładki JPEG
    assert "PyQt5/Qt5/plugins/platforms/qwindows.dll" in names
    assert "vcruntime140.dll" in names  # nie-plugin zostaje
    datas = [d[0] for d in cap.datas_after]
    assert not any("qt_fr.qm" in d for d in datas)


def test_spec_hard_rules_upx_console(monkeypatch):
    cap = _run_spec(monkeypatch, onefile=False)
    assert cap.exe_kwargs["upx"] is False  # §8.2: UPX off (Qt/AV/CPU)
    assert cap.exe_kwargs["console"] is False  # windowed bootloader
    assert cap.exe_kwargs["name"] == "DongStack"


def test_spec_onedir_vs_onefile_branch(monkeypatch):
    cap_dir = _run_spec(monkeypatch, onefile=False)
    assert cap_dir.collect_called is True
    assert cap_dir.exe_kwargs.get("exclude_binaries") is True

    cap_file = _run_spec(monkeypatch, onefile=True)
    assert cap_file.collect_called is False
    assert cap_file.exe_kwargs.get("exclude_binaries") is not True
    assert cap_file.onefile is True  # binaries/datas w EXE
