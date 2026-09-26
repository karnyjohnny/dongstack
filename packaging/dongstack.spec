# -*- mode: python ; coding: utf-8 -*-
# DongStack — plik PyInstaller (specyfikacja §8.2)
#
# UWAGA: katalog nazywa się `packaging/`, bo nazwa `build/` jest wyłączona
# z persistence snapshotów środowiska deweloperskiego (kolizja nazw).
#
# Build onedir (REKOMENDOWANY na docelowy sprzęt):
#   python -m PyInstaller packaging/dongstack.spec --noconfirm
# Build onefile (portable):
#   Windows:  set DHT_ONEFILE=1 && python -m PyInstaller packaging/dongstack.spec --noconfirm
#   POSIX:    DHT_ONEFILE=1 python -m PyInstaller packaging/dongstack.spec --noconfirm
#
# Zmienne dostarczone przez PyInstaller: SPECPATH (katalog tego pliku).
import os

from PyInstaller.utils.hooks import collect_submodules

ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))

APP_NAME = "DongStack"
ENTRY = os.path.join(ROOT, "app", "main.py")
ICON = os.path.join(ROOT, "app", "resources", "icons", "app.ico")
VERSION_RC = os.path.join(SPECPATH, "version_info.txt")
ONEFILE = os.environ.get("DHT_ONEFILE", "0") == "1"

# --- Zasoby (QSS, ikony PNG) pakowane do wnętrza binarium -------------------
# Układ w bundle: <_MEIPASS>/app/resources/{styles,icons} — 1:1 z repo,
# dzięki temu app/core/paths.py:resource_path() działa bez rozgałęzień.
datas = []
for sub in ("styles", "icons"):
    src = os.path.join(ROOT, "app", "resources", sub)
    if os.path.isdir(src):
        datas.append((src, os.path.join("app", "resources", sub)))

# --- Moduły WYKLUCZONE (rozmiar + RAM; specyfikacja §8.2) --------------------
excludes = [
    # Python dev/runtime noise
    "tkinter", "_tkinter", "pydoc_data", "doctest", "pdb",
    "pytest", "pip", "setuptools", "wheel", "ruff", "responses", "PIL",
    # Nieużywane moduły PyQt5 (poziom Python; ich DLL-e nie zostaną wciągnięte)
    "PyQt5.QtWebEngineCore", "PyQt5.QtWebEngineWidgets", "PyQt5.QtWebChannel",
    "PyQt5.QtWebSockets", "PyQt5.QtQml", "PyQt5.QtQuick", "PyQt5.QtQuickWidgets",
    "PyQt5.Qt3DCore", "PyQt5.Qt3DRender", "PyQt5.QtBluetooth", "PyQt5.QtNfc",
    "PyQt5.QtPositioning", "PyQt5.QtLocation", "PyQt5.QtMultimedia",
    "PyQt5.QtMultimediaWidgets", "PyQt5.QtSerialPort", "PyQt5.QtSerialBus",
    "PyQt5.QtSql", "PyQt5.QtCharts", "PyQt5.QtDataVisualization",
    "PyQt5.QtNetwork",       # HTTP wyłącznie przez requests (worker sieciowy)
    "PyQt5.QtSvg",           # ikony jako PNG (§6.4.3)
    "PyQt5.QtTest", "PyQt5.QtDesigner", "PyQt5.QtHelp", "PyQt5.QtPrintSupport",
    "PyQt5.QtOpenGL", "PyQt5.QtXml", "PyQt5.QtXmlPatterns",
]

a = Analysis(
    [ENTRY],
    pathex=[ROOT],
    binaries=[],
    datas=datas,
    # Leniwe importy wewnątrz funkcji (app.data/app.gui/app.workers w main.py) bywają
    # pomijane przez analizę — collect_submodules("app") domyka pakiet w PYZ (bug CI M6).
    hiddenimports=["sqlite3"] + collect_submodules("app"),
    hookspath=[],
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
)

# --- Czystka assetów Qt: translacje (zostaw en/pl) i zbędne pluginy ----------
_KEEP_PLUGIN_FAMILIES = ("platforms", "styles", "imageformats")
_KEEP_IMAGEFORMATS = ("qjpeg", "qico", "qgif")


def _keep(path):
    p = str(path).replace("\\", "/").lower()
    if "/translations/" in p or p.endswith(".qm"):
        return ("qt_en" in p) or ("qt_pl" in p)
    if "/plugins/" in p:
        parts = p.split("/")
        if "plugins" not in parts:
            return True
        i = parts.index("plugins")
        family = parts[i + 1] if i + 1 < len(parts) else ""
        if family not in _KEEP_PLUGIN_FAMILIES:
            return False
        if family == "imageformats":
            return any(k in p for k in _KEEP_IMAGEFORMATS)
    return True


a.datas = [d for d in a.datas if _keep(d[0])]
a.binaries = [b for b in a.binaries if _keep(b[0])]

pyz = PYZ(a.pure)

_exe_kwargs = dict(
    name=APP_NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,            # BEZWZGLĘDNIE off: UPX uszkadza DLL-e Qt + flagi AV na Win7
    console=False,        # windowed bootloader — brak czarnego okna cmd
    disable_windowed_traceback=False,
)
if os.path.isfile(ICON):
    _exe_kwargs["icon"] = ICON
if os.path.isfile(VERSION_RC):
    _exe_kwargs["version"] = VERSION_RC

if ONEFILE:
    exe = EXE(pyz, a.scripts, a.binaries, a.datas, a.zipfiles, **_exe_kwargs)
else:
    exe = EXE(pyz, a.scripts, exclude_binaries=True, **_exe_kwargs)
    coll = COLLECT(
        exe,
        a.binaries,
        a.datas,
        strip=False,
        upx=False,
        name=APP_NAME,
    )
