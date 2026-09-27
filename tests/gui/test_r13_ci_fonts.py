"""Regresja r13: fonty testowe (CI windows-2022 + QT_QPA_PLATFORM=offscreen).

Runner GitHuba nie daje Qt żadnej bazy fontów: wtyczka offscreen na Windows
NIE enumeruje fontów systemowych, a PyQt5 ≥ 5.15 nie dołącza własnych katalogów
`Qt5/lib/fonts` (logi CI: "QFontDatabase: Cannot find font directory …"). Qt
rasteryzuje wtedy fallbackiem „box”: PUSTE glify (testy pikselowe tekstu r11/r12
dostawały 0 ink) i rozdęte metryki ~1 em/znak (elide 'Soul Lan…' w karcie).

Fix (conftest): vendoryzowane DejaVu (tests/fonts/, licencja Bitstream Vera)
+ jawna podmiana rodziny w app-QSS/app-foncie, gdy "Segoe UI" nie istnieje.
FreeType rasteryzuje identycznie na Windows i Linuksie → piksele deterministyczne.

Te asercje to kanarek: na offscreen (CI) MUSZĄ przejść — gdyby ładowanie fontów
przestało działać, wyłożą się tutaj z jasnym komunikatem, zamiast cicho
skipować/zerować ink w testach r11/r12. Skip tylko na wtyczce `minimal`,
która fizycznie nie ma bazy fontów (addApplicationFont → -1).
"""

from __future__ import annotations

import pytest

from tests.gui.conftest import styled_font_advance


def _skip_if_minimal() -> None:
    from PyQt5.QtGui import QGuiApplication

    if QGuiApplication.platformName() == "minimal":
        pytest.skip("minimal: brak bazy fontów (nullptr) — środowisko debugowe, CI=offscreen")


def test_vendored_dejavu_is_registered(qapp):
    _skip_if_minimal()
    from PyQt5.QtGui import QFontDatabase

    fams = QFontDatabase().families()
    assert "DejaVu Sans" in fams, "tests/fonts nie załadowane (conftest._load_test_fonts)"
    assert "Bold" in QFontDatabase().styles("DejaVu Sans"), (
        "brak wariantu Bold (DejaVuSans-Bold.ttf)"
    )


def test_widget_font_metrics_are_real_not_box_fallback(qapp):
    """Metryki fallbacka „box” to ~1 em na znak (12 znaków × 10 px ≈ 120 px).
    Realny font (DejaVu/Segoe UI) rysuje 'Soul Land II' w ~55–75 px przy 10 px.
    Dokładnie ta różnica sfalsyfikowała elide w teście r11 na CI ('Soul Lan…').
    Mierzymy font, który faktycznie dostają widgety (rodzina z app-QSS) — nie
    goły QFont('Segoe UI'), który na fontconfigu i tak spadłby na substytut."""
    _skip_if_minimal()
    advance = styled_font_advance("Soul Land II", 10)
    assert 30 < advance < 95, "metryki widgetów wyglądają na fallback box: %d px" % advance

    advance13 = styled_font_advance("w trakcie", 13)
    assert 30 < advance13 < 130, "jw. dla 13 px: %d px" % advance13
