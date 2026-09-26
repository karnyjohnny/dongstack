"""Testy DashboardWidget + WidgetListBackend: fill/reuse/skeleton/empty/FAB."""

from __future__ import annotations

from PyQt5.QtTest import QTest

from app.core.demo_data import demo_rows
from app.gui.dashboard.dashboard_widget import DashboardWidget
from app.gui.dashboard.donghua_row import DonghuaRow


def test_set_items_and_count(qapp):
    dash = DashboardWidget()
    rows = demo_rows(300)
    dash.set_items(rows)
    qapp.processEvents()
    assert dash.backend.count() == 300
    assert dash._empty.isVisible() is False


def test_refill_replaces_rows_safely(qapp):
    dash = DashboardWidget()
    rows = demo_rows(50)
    dash.set_items(rows)
    first = dash.backend.row_widget(rows[0].id)
    assert isinstance(first, DonghuaRow)
    # ponowny fill: stare wiersze zwolnione (deleteLater), nowe działają, bez crasha
    dash.set_items(rows)
    qapp.processEvents()
    assert dash.backend.count() == 50
    again = dash.backend.row_widget(rows[0].id)
    assert again is not None and again is not first
    QTest.qWait(30)  # przetworzenie deleteLater
    qapp.processEvents()
    assert dash.backend.count() == 50


def test_update_item_updates_row_in_place(qapp):
    dash = DashboardWidget()
    rows = demo_rows(10)
    dash.set_items(rows)
    target = rows[0]
    new = target.with_episode(target.current_episode + 1, updated_at="t")
    dash.update_item(new)
    qapp.processEvents()
    row = dash.backend.row_widget(target.id)
    assert "%d/" % new.current_episode in row._episode.text()


def test_remove_item(qapp):
    dash = DashboardWidget()
    rows = demo_rows(5)
    dash.set_items(rows)
    dash.remove_item(rows[2].id)
    qapp.processEvents()
    assert dash.backend.count() == 4
    assert dash.backend.row_widget(rows[2].id) is None


def test_skeleton_then_empty_hint(qapp):
    dash = DashboardWidget()
    dash.show()
    qapp.processEvents()
    dash.show_skeleton(4)
    qapp.processEvents()
    assert dash.backend.count() == 4
    assert dash._empty.isVisible() is False
    dash.set_items([])
    qapp.processEvents()
    assert dash._empty.isVisible() is True
    assert dash.backend.count() == 0
    dash.hide()


def test_row_signals_reemitted(qapp):
    dash = DashboardWidget()
    rows = demo_rows(3)
    got = []
    dash.episodeIncrementRequested.connect(got.append)
    dash.set_items(rows)
    qapp.processEvents()
    row = dash.backend.row_widget(rows[1].id)
    row._plus.click()
    qapp.processEvents()
    assert got == [rows[1].id]


def test_fab_overlay_inside_bounds(qapp):
    dash = DashboardWidget()
    dash.resize(900, 600)
    dash.show()
    qapp.processEvents()
    fab = dash._add
    assert fab.isVisible()
    assert fab.x() + fab.width() <= dash.width()
    assert fab.y() + fab.height() <= dash.height()
    assert fab.width() >= 52 and fab.height() >= 52


def test_add_and_search_signals(qapp):
    dash = DashboardWidget()
    adds, searches = [], []
    dash.addClicked.connect(lambda: adds.append(1))
    dash.localSearchChanged.connect(searches.append)
    dash._add.click()
    dash._search.setText("doupo")
    qapp.processEvents()
    assert adds == [1]
    assert searches and searches[-1] == "doupo"
