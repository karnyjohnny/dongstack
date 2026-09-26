#!/usr/bin/env python3
"""tools/generate_branding.py — generuje komplet ikon i logo DongStack (decyzja D7).

Wszystkie grafiki są RYSOWANE KODEM (wektorowe prymitywy Pillow), renderowane w 4×
supersamplingu i skalowane LANCZOS do docelowych rozmiarów — deterministyczne,
bez zewnętrznych assetów. Wyniki trafiają do app/resources/icons/ i są commitowane
(build exe NIE wymaga Pillow).

Paleta = warstwy dark mode ze specyfikacji (§29/§6.4 Biblii GUI):
    background #121212 | surface #1E1E1E | elevated #242424 | hover #2A2A2A
    border #303030/#444444 | text #E6E1E5/#A0A0A0 | accent #B39DDB/#9580BF

Użycie:  pip install -r requirements-tools.txt && python tools/generate_branding.py
Baseline składni: Python 3.8.
"""

from __future__ import annotations

import math
import os
from typing import Callable, List, Tuple

from PIL import Image, ImageDraw

SS = 4  # supersampling

# --- paleta -----------------------------------------------------------------
BG = "#1E1E1E"
BORDER = "#303030"
ACCENT = "#B39DDB"
ACCENT_MID = "#6E5E96"
ACCENT_LOW = "#3C3A45"
MUTED = "#A0A0A0"
ELEVATED = "#242424"
PLACEHOLDER_SHAPE = "#3A3A45"
PLACEHOLDER_SUN = "#4A4A55"
STATUS_COLORS = {
    "watching": "#7EA6D9",  # przygaszony niebieski
    "completed": "#8FBF8F",  # przygaszona zieleń
    "planned": "#93A0B4",  # szaro-błękitny
    "dropped": "#C98B8B",  # przygaszona czerwień
}

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.normpath(os.path.join(HERE, "..", "app", "resources", "icons"))


def _render(size: int, draw_fn: Callable[[ImageDraw.ImageDraw, float], None]) -> Image.Image:
    """Rysuje w supersamplingu (size*SS) i skaluje do `size` (LANCZOS)."""
    big = size * SS
    img = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    draw_fn(d, float(big))
    return img.resize((size, size), Image.LANCZOS)


def _rrect(
    d: ImageDraw.ImageDraw,
    box: Tuple[float, float, float, float],
    radius: float,
    fill=None,
    outline=None,
    width: int = 1,
) -> None:
    d.rounded_rectangle(box, radius=max(1.0, radius), fill=fill, outline=outline, width=width)


# --- ikony ------------------------------------------------------------------
def draw_app_logo(d: ImageDraw.ImageDraw, s: float) -> None:
    """Logo: 3 warstwy 'stack' (sezony ułożone w kolejności) na powierzchni karty."""
    m = s * 0.04
    _rrect(
        d, (m, m, s - m, s - m), s * 0.20, fill=BG, outline=BORDER, width=max(SS, int(s * 0.012))
    )
    heights = s * 0.135
    widths = [s * 0.44, s * 0.58, s * 0.72]
    colors = [ACCENT, ACCENT_MID, ACCENT_LOW]
    gap = s * 0.085
    total_h = 3 * heights + 2 * gap
    y0 = (s - total_h) / 2.0
    for i in range(3):
        w = widths[i]
        x0 = (s - w) / 2.0
        y = y0 + i * (heights + gap)
        _rrect(d, (x0, y, x0 + w, y + heights), heights / 2.0, fill=colors[i])


def draw_plus(d: ImageDraw.ImageDraw, s: float) -> None:
    _draw_plus_color(d, s, ACCENT)


def draw_plus_dark(d: ImageDraw.ImageDraw, s: float) -> None:
    """Wariant ciemny (+) dla FAB na akcentowym tle (#B39DDB)."""
    _draw_plus_color(d, s, "#17131F")


def _draw_plus_color(d: ImageDraw.ImageDraw, s: float, color: str) -> None:
    t = s * 0.155  # grubość belki
    L = s * 0.62  # długość belki
    c = s / 2.0
    _rrect(d, (c - L / 2, c - t / 2, c + L / 2, c + t / 2), t / 2, fill=color)
    _rrect(d, (c - t / 2, c - L / 2, c + t / 2, c + L / 2), t / 2, fill=color)


def draw_minus(d: ImageDraw.ImageDraw, s: float) -> None:
    t = s * 0.155
    L = s * 0.62
    c = s / 2.0
    _rrect(d, (c - L / 2, c - t / 2, c + L / 2, c + t / 2), t / 2, fill=MUTED)


def draw_more(d: ImageDraw.ImageDraw, s: float) -> None:
    r = s * 0.085
    c = s / 2.0
    for dy in (-s * 0.26, 0.0, s * 0.26):
        d.ellipse((c - r, c + dy - r, c + r, c + dy + r), fill=MUTED)


def draw_search(d: ImageDraw.ImageDraw, s: float) -> None:
    w = max(SS * 2, int(s * 0.10))
    cx, cy, r = s * 0.43, s * 0.43, s * 0.26
    d.ellipse((cx - r, cy - r, cx + r, cy + r), outline=MUTED, width=w)
    ang = math.radians(45)
    x1 = cx + r * math.cos(ang)
    y1 = cy + r * math.sin(ang)
    x2 = s * 0.82
    y2 = s * 0.82
    d.line((x1, y1, x2, y2), fill=MUTED, width=int(w * 1.25))
    d.ellipse((x2 - w * 0.6, y2 - w * 0.6, x2 + w * 0.6, y2 + w * 0.6), fill=MUTED)


def draw_sort(d: ImageDraw.ImageDraw, s: float) -> None:
    t = s * 0.095
    x0 = s * 0.16
    widths = [s * 0.68, s * 0.50, s * 0.32]
    ys = [s * 0.26, s * 0.48, s * 0.70]
    for w, y in zip(widths, ys):
        _rrect(d, (x0, y, x0 + w, y + t), t / 2, fill=MUTED)


def draw_link(d: ImageDraw.ImageDraw, s: float) -> None:
    """Dwa zazębione ogniwa (uniwersum/franczyza)."""
    w = max(SS * 2, int(s * 0.10))
    h = s * 0.34
    y0 = (s - h) / 2.0
    r = h / 2.0
    x1 = s * 0.10
    x2 = s * 0.42
    span = s * 0.48
    d.rounded_rectangle((x1, y0, x1 + span, y0 + h), radius=r, outline=ACCENT, width=w)
    d.rounded_rectangle((x2, y0, x2 + span, y0 + h), radius=r, outline=MUTED, width=w)
    # iluzja zazębienia: nadrysuj prawy łuk pierwszego ogniwa nad drugim
    bbox = (x1 + span - 2 * r, y0 - w, x1 + span + 2 * w, y0 + h + w)
    d.arc(bbox, start=-70, end=70, fill=ACCENT, width=w)


def draw_undo(d: ImageDraw.ImageDraw, s: float) -> None:
    w = max(SS * 2, int(s * 0.10))
    cx, cy, r = s * 0.52, s * 0.52, s * 0.28
    d.arc((cx - r, cy - r, cx + r, cy + r), start=150, end=30, fill=MUTED, width=w)
    # grot strzałki (lewo-dół)
    ax = cx + r * math.cos(math.radians(150))
    ay = cy - r * math.sin(math.radians(150))
    t = s * 0.13
    d.polygon([(ax - t * 1.3, ay), (ax + t * 0.6, ay - t), (ax + t * 0.6, ay + t)], fill=MUTED)


def draw_settings(d: ImageDraw.ImageDraw, s: float) -> None:
    """Koło zębate (Ustawienia): 8 zębów + pierścień."""
    import math as _m

    color = MUTED
    c = s / 2.0
    r_disc = s * 0.24
    r_teeth = s * 0.36
    teeth = 8
    for i in range(teeth):
        ang = 2 * _m.pi * i / teeth
        w = s * 0.09
        pts = []
        for da, rr in ((-0.16, r_teeth), (0.16, r_teeth), (0.10, r_disc), (-0.10, r_disc)):
            pts.append((c + rr * _m.cos(ang + da), c + rr * _m.sin(ang + da)))
        d.polygon(pts, fill=color)
    d.ellipse((c - r_disc, c - r_disc, c + r_disc, c + r_disc), fill=color)
    hole = s * 0.11
    d.ellipse((c - hole, c - hole, c + hole, c + hole), fill=(0, 0, 0, 0))


def draw_trash(d: ImageDraw.ImageDraw, s: float) -> None:
    """Kosz (usuwanie): pokrywa + korpus z pionowymi liniami, kolor ostrzegawczy."""
    c = "#E0B6B6"
    # pokrywa
    lid_w = s * 0.52
    lid_h = s * 0.09
    d.rounded_rectangle(
        (s / 2 - lid_w / 2, s * 0.20, s / 2 + lid_w / 2, s * 0.20 + lid_h), radius=lid_h / 2, fill=c
    )
    knob_w = s * 0.16
    knob_h = s * 0.07
    d.rounded_rectangle(
        (s / 2 - knob_w / 2, s * 0.14, s / 2 + knob_w / 2, s * 0.14 + knob_h),
        radius=knob_h / 2,
        fill=c,
    )
    # korpus
    body_x0, body_x1 = s * 0.28, s * 0.72
    body_y0, body_y1 = s * 0.34, s * 0.84
    d.rounded_rectangle((body_x0, body_y0, body_x1, body_y1), radius=s * 0.07, fill=c)
    # pionowe linie (transparentne)
    for fx in (0.42, 0.5, 0.58):
        d.rounded_rectangle(
            (s * fx - s * 0.02, s * 0.42, s * fx + s * 0.02, s * 0.76),
            radius=s * 0.02,
            fill=(0, 0, 0, 0),
        )


def draw_status(color: str) -> Callable[[ImageDraw.ImageDraw, float], None]:
    def _fn(d: ImageDraw.ImageDraw, s: float) -> None:
        r = s * 0.34
        c = s / 2.0
        d.ellipse((c - r, c - r, c + r, c + r), fill=color)

    return _fn


def draw_cover_placeholder(d: ImageDraw.ImageDraw, s: float) -> None:
    _rrect(d, (0, 0, s, s), s * 0.10, fill=ELEVATED)
    sun = s * 0.10
    d.ellipse((s * 0.62, s * 0.18, s * 0.62 + sun, s * 0.18 + sun), fill=PLACEHOLDER_SUN)
    d.polygon(
        [
            (s * 0.10, s * 0.82),
            (s * 0.42, s * 0.44),
            (s * 0.62, s * 0.68),
            (s * 0.74, s * 0.56),
            (s * 0.90, s * 0.82),
        ],
        fill=PLACEHOLDER_SHAPE,
    )


# --- eksport ----------------------------------------------------------------
GLYPH_SIZES = [16, 20, 24, 32]
STATUS_SIZES = [8, 12, 16]
PLACEHOLDER_SIZES = [72, 144]
ICO_SIZES = [(16, 16), (20, 20), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]


def export_set(
    name: str, fn: Callable[[ImageDraw.ImageDraw, float], None], sizes: List[int]
) -> int:
    n = 0
    for size in sizes:
        img = _render(size, fn)
        img.save(os.path.join(OUT_DIR, "%s_%d.png" % (name, size)), "PNG", optimize=True)
        n += 1
    return n


def main() -> int:
    if not os.path.isdir(OUT_DIR):
        os.makedirs(OUT_DIR)
    count = 0
    count += export_set("app", draw_app_logo, [16, 20, 24, 32, 64, 128, 256])
    count += export_set("add", draw_plus, GLYPH_SIZES)
    count += export_set("add_dark", draw_plus_dark, GLYPH_SIZES)
    count += export_set("remove", draw_minus, GLYPH_SIZES)
    count += export_set("more", draw_more, GLYPH_SIZES)
    count += export_set("search", draw_search, GLYPH_SIZES)
    count += export_set("sort", draw_sort, GLYPH_SIZES)
    count += export_set("settings", draw_settings, GLYPH_SIZES)
    count += export_set("trash", draw_trash, GLYPH_SIZES)
    count += export_set("link", draw_link, GLYPH_SIZES)
    count += export_set("undo", draw_undo, GLYPH_SIZES)
    for status, color in STATUS_COLORS.items():
        count += export_set("status_%s" % status, draw_status(color), STATUS_SIZES)
    count += export_set("cover_placeholder", draw_cover_placeholder, PLACEHOLDER_SIZES)

    # logo_256.png (README) + app.ico (wielorozmiarowe)
    logo = _render(256, draw_app_logo)
    logo.save(os.path.join(OUT_DIR, "logo_256.png"), "PNG", optimize=True)
    logo.save(os.path.join(OUT_DIR, "app.ico"), format="ICO", sizes=ICO_SIZES)
    count += 2

    print("wygenerowano %d plików w %s" % (count, OUT_DIR))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
