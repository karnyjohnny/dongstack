"""Testy MainWindow (offscreen): struktura, sygnały zbiorcze, skeleton→dane, grab."""

from __future__ import annotations

from app.core.demo_data import demo_rows
from app.gui.main_window import MainWindow


def _window():
    w = MainWindow(animations_enabled=False)
    return w


def test_window_builds_with_sidebar_and_dashboard(qapp):
    w = _window()
    assert w.sidebar is not None and w.dashboard is not None
    assert w.windowTitle().startswith("DongStack")
    assert w.minimumWidth() <= 960


def test_status_filter_updates_section_title(qapp):
    w = _window()
    got = []
    w.statusFilterChanged.connect(got.append)
    w.sidebar.set_current("planned")
    qapp.processEvents()
    assert got == ["planned"]
    assert w.dashboard._section.text() == "Planowane"


def test_set_items_and_counts(qapp):
    w = _window()
    rows = demo_rows(120)
    w.set_items(rows)
    w.set_counts({"all": 120, "watching": 40, "completed": 40, "planned": 30, "dropped": 10})
    qapp.processEvents()
    assert w.dashboard.backend.count() == 120
    assert w.sidebar._items["all"]._badge.text() == "120"


def test_skeleton_start_then_data(qapp):
    w = _window()
    w.show_skeleton(4)
    qapp.processEvents()
    assert w.dashboard.backend.count() == 4
    w.set_items(demo_rows(20))
    qapp.processEvents()
    assert w.dashboard.backend.count() == 20


def test_window_grab_produces_pixmap(qapp):
    """Smoke renderujący: okno daje się zrasteryzować (podstawa screenshotów)."""
    w = _window()
    w.set_items(demo_rows(30))
    w.show()
    qapp.processEvents()
    pix = w.grab()
    assert not pix.isNull()
    assert pix.width() >= 900
    w.hide()


def test_snackbar_attached(qapp):
    w = _window()
    w.show()
    qapp.processEvents()
    w.snackbar.show_message("test")
    qapp.processEvents()
    assert w.snackbar.isVisible()
    w.snackbar.hide_message()
    w.hide()
