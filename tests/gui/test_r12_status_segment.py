"""Testy GUI r12 (feedback produkcyjny przed v1.3.0): czytelny segment statusu.

Zgłoszenie Właściciela: w dodawaniu/edycji wciśnięty przycisk statusu robił się
„ciemnoniebieski/fioletowy, kompletnie nieczytelny” niezależnie od statusu, a żądanie
brzmiało: zaznaczony = ramka + napis w kolorze statusu, wciśnięty = jaśniejsza ramka
(i tekst).

Root-cause (2 warstwy):
1. QSS nie definiował `:pressed` dla `#statusSegment` — QStyleSheetStyle na Windows
   oddawał stan wciśnięty natywnemu motywowi aero (ciemny niebiesko-fioletowy fill,
   wspólny dla wszystkich statusów).
2. Design `:checked` = pełny fill kolorem statusu + tekst `#14181C`; generyczny
   fallback (gdyby property `status` nie dopasowało) malował fioletowy akcent
   `#B39DDB`.

Kontrakt po fixie (drabinka na status):
- niezaznaczony: tło #242424, ramka stonowana, tekst jasny wariant statusu;
- zaznaczony: tło #2A2A2A, ramka 2px PEŁNYM kolorem statusu, tekst tym samym
  kolorem (bold), BEZ pełnego filla;
- wciśnięty (zaznaczony lub nie): tło #303030, ramka + tekst o stopień JAŚNIEJSZE.

Testy są pikselowe (grab() realnego widgetu z realnym QSS) — dokładnie ta metoda,
którą udowodniono bug i fix offscreen. r13: na CI (Windows offscreen) Qt nie ma
fontów systemowych, więc conftest ładuje vendoryzowane DejaVu (tests/fonts) —
FreeType rasteryzuje identycznie jak na Linuksie; testy glifów biorą fixture
`require_real_fonts` (skip tylko na wtyczce `minimal`, która nie ma bazy fontów).
"""

from __future__ import annotations

import math

from PyQt5.QtWidgets import QPushButton

from app.domain.models import Status
from app.gui.add.advanced_page import AdvancedPage
from app.gui.theme import load_stylesheet

# Drabinka kolorów statusu (spójna z dialogs.qss; single source of truth = QSS,
# tu wartości oczekiwane do porównań pikselowych).
MUTED = {  # ramka niezaznaczonego
    "watching": (0x3A, 0x4A, 0x5C),
    "completed": (0x3E, 0x4F, 0x3E),
    "planned": (0x40, 0x46, 0x4F),
    "dropped": (0x55, 0x40, 0x3F),
}
FULL = {  # ramka + tekst zaznaczonego („pełny kolor statusu”)
    "watching": (0x7E, 0xA6, 0xD9),
    "completed": (0x8F, 0xBF, 0x8F),
    "planned": (0x93, 0xA0, 0xB4),
    "dropped": (0xC9, 0x8B, 0x8B),
}
BRIGHT = {  # tekst niezaznaczonego oraz ramka + tekst wciśniętego
    "watching": (0xA9, 0xC4, 0xE4),
    "completed": (0xB7, 0xD8, 0xB7),
    "planned": (0xBC, 0xC6, 0xD4),
    "dropped": (0xE0, 0xB6, 0xB6),
}
ACCENT_PURPLE = (0xB3, 0x9D, 0xDB)  # zakazany na segmentach (feedback r12)


def _dist(a, b) -> float:
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))


def _lum(rgb) -> float:
    return 0.2126 * rgb[0] + 0.7152 * rgb[1] + 0.0722 * rgb[2]


def _img(qapp, page):
    page.show()
    qapp.processEvents()
    return page


def _grab(btn):
    return btn.grab().toImage()


def _px(img, x, y):
    c = img.pixelColor(x, y)
    return (c.red(), c.green(), c.blue())


def _border_px(img):
    """Piksel ramki: środek górnej krawędzi (poza promieniem zaokrąglenia)."""
    return _px(img, img.width() // 2, 0)


def _interior_near(img, rgb, tol=30) -> int:
    """Liczba pikseli WEWNĄTRZ przycisku (bez ramki) bliskich `rgb` — dowód na
    kolor tekstu niezależnie od fontu/antialiasingu."""
    n = 0
    for y in range(4, img.height() - 4):
        for x in range(4, img.width() - 4):
            if _dist(_px(img, x, y), rgb) <= tol:
                n += 1
    return n


def _fill_px(img):
    """Tło wewnątrz przycisku: dolny pasek pod tekstem, z dala od ramki."""
    return _px(img, img.width() // 2, img.height() - 4)


def _page_with(qapp, status: Status, *, checked: bool, down: bool):
    page = AdvancedPage()
    _img(qapp, page)
    btn = page._status_buttons[status]
    if checked:
        btn.setChecked(True)
    btn.setDown(down)
    qapp.processEvents()
    return page, btn


# ------------------------------------------------------- stan: niezaznaczony
def test_unchecked_muted_border_and_bright_text(qapp, require_real_fonts):
    for st in Status:
        page, btn = _page_with(qapp, st, checked=False, down=False)
        img = _grab(btn)
        assert _dist(_border_px(img), MUTED[st.value]) <= 10, st
        assert _dist(_fill_px(img), (0x24, 0x24, 0x24)) <= 8, st
        assert _interior_near(img, BRIGHT[st.value]) >= 4, st  # tekst = jasny wariant
        page.close()


# ------------------------------------------------------- stan: zaznaczony
def test_checked_border_and_text_in_full_status_color(qapp, require_real_fonts):
    """Sedno feedbacku r12: zaznaczony ma ramkę I napis w kolorze statusu."""
    for st in Status:
        page, btn = _page_with(qapp, st, checked=True, down=False)
        img = _grab(btn)
        b = _border_px(img)
        assert _dist(b, FULL[st.value]) <= 10, st
        # tekst w pełnym kolorze statusu (bold) — wewnątrz, nie tylko ramka:
        assert _interior_near(img, FULL[st.value]) >= 4, st
        page.close()


def test_checked_has_no_full_status_fill(qapp):
    """Stary design (fill #7EA6D9/#8FBF8F/… + tekst #14181C) = nieczytelny na Win7.
    Zaznaczony przycisk musi zostać CIEMNY (tło #2A2A2A), bez saturacji kolorem."""
    for st in Status:
        page, btn = _page_with(qapp, st, checked=True, down=False)
        img = _grab(btn)
        fill = _fill_px(img)
        assert _lum(fill) < 90, (st, fill)  # ciemne tło, nie fill statusem (lum ≥152)
        assert _dist(fill, FULL[st.value]) > 60, st
        page.close()


# ------------------------------------------------------- stan: wciśnięty
def test_pressed_lightens_border_and_text(qapp, require_real_fonts):
    """Wciśnięty (checked lub nie) = ramka + tekst JAŚNIEJSZE o stopień (BRIGHT).
    Eksplicytne reguły :pressed/:checked:pressed usuwają natywny aero-fill z Win7."""
    for checked in (False, True):
        for st in Status:
            page_rest, btn_rest = _page_with(qapp, st, checked=checked, down=False)
            img_rest = _grab(btn_rest)
            page, btn = _page_with(qapp, st, checked=checked, down=True)
            img = _grab(btn)
            b = _border_px(img)
            assert _dist(b, BRIGHT[st.value]) <= 10, (st, checked, b)
            assert _lum(b) > _lum(_border_px(img_rest)) + 20, (st, checked)
            assert _interior_near(img, BRIGHT[st.value]) >= 4, (st, checked)  # tekst
            assert _dist(_fill_px(img), (0x30, 0x30, 0x30)) <= 8, (st, checked)
            page_rest.close()
            page.close()


# ------------------------------------------------------- fallback generyczny
def test_generic_checked_fallback_is_neutral_not_purple(qapp):
    """Gdyby property `status` kiedykolwiek nie dopasowało, generyczny :checked
    nie może malować fioletowego akcentu #B39DDB (część skargi r12)."""
    page = AdvancedPage()  # tylko jako dawca app-stylesheetu przez qapp fixture
    page.show()
    qapp.processEvents()
    btn = QPushButton("fallback", page)
    btn.setObjectName("statusSegment")  # bez setProperty("status", …)
    btn.setCheckable(True)
    btn.setChecked(True)
    btn.resize(140, 36)
    qapp.processEvents()
    img = _grab(btn)
    assert _dist(_border_px(img), ACCENT_PURPLE) > 40
    assert _lum(_fill_px(img)) < 90  # dalej ciemne tło
    page.close()


# ------------------------------------------------------- root-cause: wyciek stylesheetu
def test_scroll_viewport_has_no_selectorless_stylesheet(qapp):
    """Root-cause r12: `viewport().setStyleSheet("background:transparent;")` działa
    jak `* { background: transparent }` na wszystkich potomków (Qt conflict
    resolution: bliższy stylesheet wygrywa z app-QSS bez względu na specyficzność).
    Formularz w QScrollArea tracił tła pól, a segmenty statusu — regułę background,
    przez co QStyleSheetStyle oddawał checked/pressed natywnemu motywowi Windows
    (ciemnoniebieski/fioletowy aero-fill, „niezależnie od statusu")."""
    page = AdvancedPage()
    _img(qapp, page)
    assert page._scroll.viewport().styleSheet() == ""
    assert page._scroll.viewport().autoFillBackground() is False
    # pole wewnątrz scrolla renderuje OPAKOWANE tło z app-QSS (dowód braku wycieku):
    img = _grab(page._episode)
    fill = _px(img, img.width() // 2, img.height() // 2)
    assert img.pixelColor(img.width() // 2, img.height() // 2).alpha() == 255
    assert _lum(fill) > 20  # tło spinboksa (#242424), nie przezroczystość/karta dialogu
    page.close()


# ------------------------------------------------------- kontrakt statyczny QSS
def test_qss_defines_explicit_pressed_rules_for_every_status():
    """Bez jawnych :pressed QStyleSheetStyle na Windows oddaje rysowanie natywnemu
    motywowi (root-cause „ciemnoniebieski/fioletowy” z feedbacku)."""
    css = load_stylesheet(refresh=True)
    for st in Status.values():
        assert f'statusSegment[status="{st}"]:pressed' in css, st
        assert f'statusSegment[status="{st}"]:checked:pressed' in css, st
        assert f'statusSegment[status="{st}"]:checked' in css, st


def test_qss_status_segment_rules_have_no_purple_and_no_dark_text_on_fill():
    css = load_stylesheet(refresh=True)
    for line in css.splitlines():
        if "statusSegment" in line:
            assert "#B39DDB" not in line  # fioletowy akcent zakazany na segmentach
            assert "#14181C" not in line  # stary nieczytelny tekst na fillu
