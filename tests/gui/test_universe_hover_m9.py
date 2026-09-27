"""Testy M9 (GUI): dwupoziomowe podświetlenie uniwersum w WidgetListBackend + karcie."""

from __future__ import annotations

from PyQt5.QtCore import QEvent, Qt
from PyQt5.QtTest import QTest

from app.domain.models import Donghua, Status
from app.gui.dashboard.dashboard_widget import DashboardWidget
from app.gui.dashboard.donghua_row import DonghuaRow
from app.gui.dashboard.list_backend import WidgetListBackend


def _rows():
    return [
        Donghua(id=1, title="A S1", universe_id=7, status=Status.WATCHING),
        Donghua(id=2, title="A S2", universe_id=7, status=Status.WATCHING),
        Donghua(id=3, title="Solo", universe_id=None, status=Status.WATCHING),
    ]


def test_widget_backend_hover_levels(qapp):
    b = WidgetListBackend()
    b.widget().resize(900, 600)
    b.widget().show()
    b.set_items(_rows())
    qapp.processEvents()
    b.set_universe_hover(7, 1)
    assert b.row_widget(1).universe_hl == 2
    assert b.row_widget(2).universe_hl == 1
    assert b.row_widget(3).universe_hl == 0
    b.set_universe_hover(None, None)
    assert b.row_widget(1).universe_hl == 0
    assert b.row_widget(2).universe_hl == 0
    # universe_at_pos po geometrii listy
    item = b._list.item(0)
    rect = b._list.visualItemRect(item)
    assert b.universe_at_pos(rect.center()) == (7, 1)
    b.widget().hide()


def test_row_enter_leave_emits_hover(qapp):
    row = DonghuaRow()
    row.set_donghua(Donghua(id=11, title="X", universe_id=3))
    got = []
    row.hoverStateChanged.connect(lambda did, inside: got.append((did, inside)))
    row.enterEvent(QEvent(QEvent.Enter))
    row.leaveEvent(QEvent(QEvent.Leave))
    assert got == [(11, True), (11, False)]
    assert row.universe_id == 3


def test_row_hover_paints_without_crash(qapp):
    row = DonghuaRow()
    row.resize(700, 96)
    row.set_donghua(Donghua(id=12, title="Y", universe_id=3))
    row.set_universe_hl(2)
    row.show()
    row.repaint()
    qapp.processEvents()
    assert row.universe_hl == 2
    row.hide()


def test_fab_right_click_emits_manual(qapp):
    """M9: PPM na FABie = addManualClicked (LPM nadal = wyszukiwarka).

    QTest.mouseClick nie syntetyzuje natywnego WM_CONTEXTMENU, więc wysyłamy
    QContextMenuEvent(Mouse) — dokładnie to dostaje widget przy PPM na Windows.
    """
    from PyQt5.QtGui import QContextMenuEvent
    from PyQt5.QtWidgets import QApplication

    dash = DashboardWidget()
    dash.show()
    got = []
    left = []
    dash.addManualClicked.connect(lambda: got.append(1))
    dash.addClicked.connect(lambda: left.append(1))
    ev = QContextMenuEvent(QContextMenuEvent.Mouse, dash._add.rect().center())
    QApplication.sendEvent(dash._add, ev)
    qapp.processEvents()
    QTest.mouseClick(dash._add, Qt.LeftButton)
    qapp.processEvents()
    assert got == [1] and left == [1]
    dash.hide()
