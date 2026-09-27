"""conftest testów GUI: QApplication offscreen + theme (sesyjnie, bez pytest-qt).

r13 (CI windows-2022): wtyczka offscreen na Windows nie enumeruje fontów
systemowych, a PyQt5 ≥ 5.15 nie dołącza własnych (logi CI: "QFontDatabase:
Cannot find font directory .../Qt5/lib/fonts") → Qt rasteryzuje fallbackiem
"box": puste glify (testy pikselowe tekstu r11/r12 dostawały 0 ink) i metryki
~1 em/znak (elide 'Soul Lan…' w karcie).

Fix (wyłącznie testowy — aplikacja zostaje przy systemowym Segoe UI, §6.4):
1. `_load_test_fonts()` — vendoryzowane DejaVu (tests/fonts/, licencja
   Bitstream Vera) przez QFontDatabase.addApplicationFont; FreeType daje
   identyczne piksele na Windows i Linuksie.
2. `_patch_theme_fonts(app)` — gdy "Segoe UI" nie istnieje w bazie fontów,
   rodzina w app-QSS (`QWidget { font-family: "Segoe UI" }`) i app-foncie
   jest JAWNIE wymieniona na "DejaVu Sans". Sam fallback po nazwie rodziny
   nie wystarczy: font nie istnieje → box-engine niezależnie od app-fontów.

Na maszynach z Segoe UI (Win7 właściciela) patch NIE zachodzi — zero zmian.
Uwaga: wtyczka `minimal` nie ma bazy fontów wcale (addApplicationFont → -1);
ładowanie jest wtedy tolerancyjne, a testy wymagające GLIFÓW biorą fixture
`require_real_fonts`, który w takim środowisku robi skip z jasnym powodem.
CI używa offscreen (Windows: QBasicFontDatabase + app-fonty działają).
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

_FONTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir, "fonts")
_TEST_FONTS = ("DejaVuSans.ttf", "DejaVuSans-Bold.ttf")
_FALLBACK_FAMILY = "DejaVu Sans"


def _load_test_fonts() -> None:
    from PyQt5.QtGui import QFontDatabase

    for name in _TEST_FONTS:
        path = os.path.join(_FONTS_DIR, name)
        if os.path.exists(path):
            QFontDatabase.addApplicationFont(path)  # -1 = brak bazy fontów (minimal)


def _patch_theme_fonts(app) -> None:
    from PyQt5.QtGui import QFont, QFontDatabase

    from app.gui.theme import FONT_FAMILY, load_stylesheet

    families = QFontDatabase().families()
    if FONT_FAMILY in families or _FALLBACK_FAMILY not in families:
        return  # Segoe UI obecny (Win7) albo nie ma czym zastąpić (minimal)
    app.setStyleSheet(load_stylesheet().replace('"%s"' % FONT_FAMILY, '"%s"' % _FALLBACK_FAMILY))
    font = QFont(app.font())
    font.setFamily(_FALLBACK_FAMILY)
    app.setFont(font)


def styled_font_advance(text: str, pixel_size: int) -> int:
    """Szerokość `text` w foncie, który REALNIE dostają widgety (rodzina z QSS).

    Kanarek środowiska: fallback „box” daje ~1 em/znak ('Soul Land II' w 10 px
    ≈ 120 px), realny font ≈ 55–75 px.
    """
    from PyQt5.QtGui import QFont, QFontMetrics
    from PyQt5.QtWidgets import QLabel

    probe = QLabel(text)
    probe.ensurePolished()  # app-QSS → QFont(family) faktycznie używany w testach
    font = QFont(probe.font())
    font.setPixelSize(pixel_size)
    advance = QFontMetrics(font).horizontalAdvance(text)
    probe.deleteLater()
    return advance


def real_font_advance() -> int:
    return styled_font_advance("Soul Land II", 10)


@pytest.fixture(scope="session")
def qapp():
    from PyQt5.QtWidgets import QApplication

    from app.gui.theme import apply_theme

    app = QApplication.instance() or QApplication(["dongstack-tests"])
    _load_test_fonts()
    apply_theme(app)
    _patch_theme_fonts(app)
    yield app


@pytest.fixture()
def require_real_fonts(qapp):
    """Skip dla testów GLIFÓW (ink/kolor tekstu/elide) w środowiskach bez fontów."""
    from PyQt5.QtGui import QGuiApplication

    advance = real_font_advance()
    if not 30 < advance < 95:
        pytest.skip(
            "brak realnych fontów (platform=%s, advance=%d px ≈ fallback box) — "
            "testy glifów wymagają DejaVu z tests/fonts" % (QGuiApplication.platformName(), advance)
        )
    return advance


@pytest.fixture()
def process_events(qapp):
    def _flush():
        qapp.processEvents()

    return _flush
