"""app/gui/theme.py — ładowanie QSS, paleta, ikony z zestawów PNG (specyfikacja §6.4).

Zasady wydajnościowe (R9, §6.4.1):
- QSS parsowany RAZ przy starcie (sklejone pliki), zero ponownych parse'ów w runtime,
- brak QGraphicsEffect / gradientów / animowanych stylów — flat dark mode,
- ikony z PNG w docelowych rozmiarach (blit bitmapy; brak QtSvg na GMA 4500MHD),
- font systemowy Segoe UI (obecny w Win7) — brak fontów w bundle.
"""

from __future__ import annotations

from typing import Dict, Optional

from PyQt5.QtGui import QFont, QIcon
from PyQt5.QtWidgets import QApplication

from app.core.paths import icons_dir, styles_dir
from app.domain.models import Status

STYLE_FILES = ("base.qss", "sidebar.qss", "cards.qss", "dialogs.qss", "snackbar.qss")
ICON_SIZES = (16, 20, 24, 32)
FONT_FAMILY = "Segoe UI"
FONT_SIZE_PT = 9

# Paleta referencyjna (single source of truth dla testów statycznych QSS i dokumentacji)
PALETTE: Dict[str, str] = {
    "background": "#121212",
    "sidebar": "#181818",
    "surface": "#1E1E1E",
    "elevated": "#242424",
    "hover": "#2A2A2A",
    "border": "#303030",
    "border_hover": "#444444",
    "text_primary": "#E6E1E5",
    "text_secondary": "#A0A0A0",
    "text_muted": "#707070",
    "accent": "#B39DDB",
    "accent_hover": "#C5B3E8",
    "accent_pressed": "#9580BF",
}

STATUS_LABELS: Dict[str, str] = {
    "all": "Wszystkie",
    Status.WATCHING.value: "W trakcie",
    Status.COMPLETED.value: "Obejrzane",
    Status.PLANNED.value: "Planowane",
    Status.DROPPED.value: "Porzucone",
}

STATUS_ICON_NAMES: Dict[str, str] = {
    Status.WATCHING.value: "status_watching",
    Status.COMPLETED.value: "status_completed",
    Status.PLANNED.value: "status_planned",
    Status.DROPPED.value: "status_dropped",
}

_stylesheet_cache: Optional[str] = None
_icon_cache: Dict[str, QIcon] = {}


def load_stylesheet(refresh: bool = False) -> str:
    """Skleja pliki QSS w jeden arkusz (parse RAZ przy starcie)."""
    global _stylesheet_cache
    if _stylesheet_cache is not None and not refresh:
        return _stylesheet_cache
    parts = []
    for name in STYLE_FILES:
        path = "%s/%s" % (styles_dir(), name)
        try:
            with open(path, encoding="utf-8") as fh:
                parts.append(fh.read())
        except OSError:
            # brak pliku stylu nie może wywrócić aplikacji (np. okrojony bundle)
            continue
    _stylesheet_cache = "\n".join(parts)
    return _stylesheet_cache


def icon(name: str) -> QIcon:
    """QIcon z zestawu PNG <name>_<size>.png (16/20/24/32) — cache globalny."""
    cached = _icon_cache.get(name)
    if cached is not None:
        return cached
    qicon = QIcon()
    base = icons_dir()
    for size in ICON_SIZES:
        qicon.addFile("%s/%s_%d.png" % (base, name, size))
    if qicon.isNull():
        # graceful degradation: pusta ikona zamiast crasha (test/offscreen bez assetów)
        qicon = QIcon()
    _icon_cache[name] = qicon
    return qicon


def apply_theme(app: QApplication) -> None:
    """Ustawia arkusz, font i atrybuty aplikacji (wywołać RAZ przed show())."""
    app.setStyleSheet(load_stylesheet())
    font = QFont(FONT_FAMILY)
    font.setPixelSize(13)
    app.setFont(font)
    app.setWindowIcon(icon("app"))
