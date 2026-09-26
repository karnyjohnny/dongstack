"""Testy theme: QSS zgodny z rygorami §6.4.1 (flat, bez efektów GPU), ikony PNG."""

from __future__ import annotations

import re

from app.gui import theme


def test_stylesheet_loads_and_merges_all_layers(qapp):
    css = theme.load_stylesheet(refresh=True)
    for token in ("#121212", "#1E1E1E", "#242424", "#2A2A2A", "#B39DDB", "#E6E1E5"):
        assert token in css, "brak koloru palety: %s" % token
    assert "donghuaCard" in css and "statusNavigation" in css and "snackBar" in css


def _strip_css_comments(css: str) -> str:
    return re.sub(r"/\*.*?\*/", "", css, flags=re.DOTALL)


def test_stylesheet_without_gpu_effects(qapp):
    """Rygor §6.4.1: zero blur/drop-shadow/gradientów/animowanych stylów (bez komentarzy)."""
    css = _strip_css_comments(theme.load_stylesheet(refresh=True)).lower()
    assert "blur" not in css
    assert "dropshadow" not in css
    assert "gradient" not in css
    assert "qgraphicseffect" not in css


def test_icons_exist_for_all_used_names(qapp):
    for name in (
        "add",
        "remove",
        "more",
        "search",
        "sort",
        "link",
        "undo",
        "app",
        "cover_placeholder",
        "status_watching",
        "status_completed",
        "status_planned",
        "status_dropped",
    ):
        icon = theme.icon(name)
        assert not icon.isNull(), "brak ikony: %s" % name


def test_apply_theme_sets_stylesheet(qapp):
    theme.apply_theme(qapp)
    assert "#121212" in qapp.styleSheet()
    assert qapp.font().pixelSize() == 13


def test_status_labels_polish():
    assert theme.STATUS_LABELS["watching"] == "W trakcie"
    assert theme.STATUS_LABELS["all"] == "Wszystkie"
