"""Testy DelegateListBackend i auto-swapu gate G3 (§6.3/§7.4) + regresja uniwersów w dialogu."""

from __future__ import annotations

import time

from PyQt5.QtCore import Qt
from PyQt5.QtTest import QTest

from app.controllers.dashboard_controller import DashboardController
from app.core.demo_data import demo_rows
from app.domain.models import Donghua, Status, Universe
from app.gui.add.add_dialog import AddDialog
from app.gui.dashboard.dashboard_widget import AUTO_BACKEND_THRESHOLD, DashboardWidget
from app.gui.dashboard.delegate_backend import DelegateListBackend, button_rects
from app.gui.dashboard.list_backend import WidgetListBackend


def test_delegate_set_items_and_count(qapp):
    b = DelegateListBackend()
    entries = demo_rows(300)
    t0 = time.perf_counter()
    b.set_items(entries)
    ms = (time.perf_counter() - t0) * 1000.0
    qapp.processEvents()
    assert b.count() == 300
    assert b.BACKEND_NAME == "delegate"
    assert ms < 100.0, "delegate set_items 300 = %.1f ms (ma być << widget)" % ms


def test_delegate_rebuild_is_cheap(qapp):
    b = DelegateListBackend()
    entries = demo_rows(300)
    b.set_items(entries)
    qapp.processEvents()
    t0 = time.perf_counter()
    for _ in range(5):
        b.set_items(list(reversed(entries)))
    ms = (time.perf_counter() - t0) * 1000.0 / 5.0
    qapp.processEvents()
    assert ms < 100.0, "delegate rebuild = %.1f ms (gate G3: 150 ms na E5500)" % ms


def test_delegate_plus_click_emits_increment(qapp):
    b = DelegateListBackend()
    b.widget().resize(900, 600)
    b.widget().show()
    entries = demo_rows(3)
    b.set_items(entries)
    qapp.processEvents()
    got = []
    b.incrementRequested.connect(got.append)
    index = b.model.index(0, 0)
    rect = b.widget().visualRect(index)
    minus, plus = button_rects(rect)
    QTest.mouseClick(b.widget().viewport(), Qt.LeftButton, Qt.NoModifier, plus.center())
    qapp.processEvents()
    assert got == [entries[0].id]
    b.widget().hide()


def test_delegate_minus_disabled_at_zero(qapp):
    b = DelegateListBackend()
    b.widget().resize(900, 600)
    b.widget().show()
    d = Donghua(id=9, title="Zero", total_episodes=12, current_episode=0, status=Status.PLANNED)
    b.set_items([d])
    qapp.processEvents()
    got = []
    b.decrementRequested.connect(got.append)
    index = b.model.index(0, 0)
    rect = b.widget().visualRect(index)
    minus, _plus = button_rects(rect)
    QTest.mouseClick(b.widget().viewport(), Qt.LeftButton, Qt.NoModifier, minus.center())
    qapp.processEvents()
    assert got == []  # 0/12: minus nieaktywny
    b.widget().hide()


def test_delegate_universe_hover_highlight(qapp):
    """M9: hover na karcie podświetla całe uniwersum (2 poziomy), bez nagłówków."""
    b = DelegateListBackend()
    b.widget().resize(900, 600)
    b.widget().show()
    d1 = Donghua(id=1, title="A S1", universe_id=7)
    d2 = Donghua(id=2, title="A S2", universe_id=7)
    d3 = Donghua(id=3, title="Solo", universe_id=None)
    b.set_items([d1, d2, d3])
    qapp.processEvents()
    assert b.count() == 3
    # hover na d1: d1=2 (kursor), d2=1 (to samo uniwersum), d3=0
    b.set_universe_hover(7, 1)
    assert b.hover_level(d1) == 2
    assert b.hover_level(d2) == 1
    assert b.hover_level(d3) == 0
    b.set_universe_hover(None, None)
    assert b.hover_level(d1) == 0
    # universe_at_pos: środek pierwszej karty
    rect = b.widget().visualRect(b.model.index(0, 0))
    assert b.universe_at_pos(rect.center()) == (7, 1)
    b.widget().hide()


def test_delegate_set_cover_stores_in_model(qapp):
    from PyQt5.QtGui import QColor, QPixmap

    b = DelegateListBackend()
    url = "https://cdn.example/c.jpg"
    d = Donghua(id=1, title="C", cover_key=url)
    b.set_items([d])
    pm = QPixmap(44, 62)
    pm.fill(QColor(0x11, 0x22, 0x33))
    b.set_cover(url, pm)
    assert b.model.cover_for(d) is pm


def test_dashboard_auto_swap_backends(qapp):
    dash = DashboardWidget(backend_kind="auto")
    dash.show()
    dash.set_items(demo_rows(5))
    qapp.processEvents()
    assert isinstance(dash.backend, WidgetListBackend)
    dash.set_items(demo_rows(AUTO_BACKEND_THRESHOLD + 20))
    qapp.processEvents()
    assert isinstance(dash.backend, DelegateListBackend)
    assert dash.backend.count() == AUTO_BACKEND_THRESHOLD + 20
    dash.set_items(demo_rows(5))
    qapp.processEvents()
    assert isinstance(dash.backend, WidgetListBackend)
    dash.hide()


def test_universes_loaded_reaches_dialog(qapp):
    """Regresja r6-fix: rejestr uniwersów dociera do comboboxa dialogu."""
    workerless = DashboardController(worker=None)
    workerless.on_universes_loaded([Universe(id=1, name="Shen Mu")])
    got = []
    workerless.universesChanged.connect(got.append)
    workerless.on_universes_loaded([Universe(id=1, name="Shen Mu"), Universe(id=2, name="Xian Ni")])
    assert got and len(got[-1]) == 2

    dialog = AddDialog()
    workerless.universesChanged.connect(dialog.set_universes)
    d = Donghua(id=1, mal_id=10, title="Shen Mu 2nd Season", universe_id=1)
    dialog.set_universes(workerless.universes())
    dialog.open_advanced_edit(d, [])
    names = [
        dialog.advanced_page._universe.itemText(i)
        for i in range(dialog.advanced_page._universe.count())
    ]
    assert "Shen Mu" in names and "Xian Ni" in names
    dialog.close()
