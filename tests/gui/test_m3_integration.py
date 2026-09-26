"""Integracja M3 (offscreen): MainWindow + DashboardController + DbWorker(QThread).

Scenariusze akceptacyjne M3 (§14): klik `+` natychmiast aktualizuje wiersz,
zapis ląduje w bazie asynchronicznie; filtry/szukaj działają na żywo;
graceful shutdown (flush + checkpoint).
"""

from __future__ import annotations

import os
import sqlite3
import time

import pytest
from PyQt5.QtCore import QMetaObject, Qt, QThread
from PyQt5.QtTest import QTest

from app.controllers.dashboard_controller import DashboardController
from app.data.connection import open_connection
from app.data.repository import DonghuaRepository
from app.domain.models import Donghua, MediaType, Status
from app.gui.main_window import MainWindow
from app.main import _wire
from app.workers.db_worker import DbWorker


class Stack:
    def __init__(self, tmp_home, qapp):
        self.qapp = qapp
        self.db_path = os.path.join(tmp_home, "dongstack.sqlite")
        self.thread = QThread()
        self.worker = DbWorker(self.db_path, os.path.join(tmp_home, "backups"))
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.loadLibrary)
        self.controller = DashboardController(self.worker)
        self.window = MainWindow(animations_enabled=False)
        _wire(self.window, self.controller)
        self.window.show()

    def start(self):
        self.thread.start()

    def wait_rows(self, n, timeout_ms=4000):
        deadline = time.time() + timeout_ms / 1000.0
        while time.time() < deadline:
            self.qapp.processEvents()
            QTest.qWait(30)
            if self.window.dashboard.backend.count() >= n:
                return True
        return False

    def teardown(self):
        try:
            if self.thread.isRunning():
                QMetaObject.invokeMethod(self.worker, "shutdown", Qt.BlockingQueuedConnection)
            self.thread.quit()
            self.thread.wait(2000)
        except RuntimeError:
            pass
        self.window.hide()


@pytest.fixture()
def seeded(tmp_home):
    """Seed bazy PRZED startem workera (osobne, zamknięte połączenie)."""
    db_path = os.path.join(tmp_home, "dongstack.sqlite")
    from app.data import migrations

    conn = open_connection(db_path)
    migrations.ensure_schema(conn)
    repo = DonghuaRepository(conn)
    ids = []
    for i, (title, total, cur, status) in enumerate(
        [
            ("Doupo Cangqiong", 12, 5, Status.WATCHING),
            ("Doupo Cangqiong 2nd Season", 12, 12, Status.COMPLETED),
            ("Ling Long", 0, 3, Status.WATCHING),
            ("Fanren Xiu Xian Zhuan", 46, 0, Status.PLANNED),
        ]
    ):
        ids.append(
            repo.insert(
                Donghua(
                    title=title,
                    total_episodes=total,
                    current_episode=cur,
                    status=status,
                    media_type=MediaType.ONA,
                    start_year=2018 + i,
                    mal_id=40000 + i,
                )
            )
        )
    conn.close()
    return {"db_path": db_path, "ids": ids}


@pytest.fixture()
def stack(seeded, tmp_home, qapp):
    st = Stack(tmp_home, qapp)
    st.start()
    assert st.wait_rows(2), "biblioteka nie dotarła do widoku"
    yield st
    st.teardown()


def _row_of(stack, donghua_id):
    return stack.window.dashboard.backend.row_widget(donghua_id)


def test_library_loaded_into_watching_view(stack, seeded):
    # ekran startowy = "W trakcie" (2 pozycje watching)
    assert stack.window.dashboard.backend.count() == 2
    counts_badge = stack.window.sidebar._items["watching"]._badge.text()
    assert counts_badge == "2"


def test_plus_click_updates_row_and_db_async(stack, seeded):
    did = seeded["ids"][0]  # Doupo S1: 5/12 watching
    row = _row_of(stack, did)
    assert row is not None and "5/12" in row._episode.text()

    row._plus.click()  # klik w wątku GUI
    stack.qapp.processEvents()
    row = _row_of(stack, did)
    assert "6/12" in row._episode.text()  # NATYCHMIAST (optymistycznie)

    # zapis asynchroniczny: czekamy na flush 250 ms + ack
    deadline = time.time() + 3.0
    while time.time() < deadline:
        QTest.qWait(50)
        conn = sqlite3.connect(stack.db_path, timeout=2.0)
        try:
            cur = conn.execute("SELECT current_episode FROM donghua WHERE id=?", (did,)).fetchone()
        finally:
            conn.close()
        if cur and cur[0] == 6:
            break
    assert cur[0] == 6  # baza dogoniła UI


def test_auto_complete_and_undo_snackbar(stack, seeded):
    did = seeded["ids"][0]  # 5/12 → dobijamy do 12/12
    for _ in range(7):
        _row_of(stack, did)._plus.click()
        stack.qapp.processEvents()
    assert stack.window.snackbar.isVisible()
    assert "ukończone" in stack.window.snackbar._message.text()
    # Undo z paska przywraca watching + 11/12
    stack.window.snackbar._action.click()
    stack.qapp.processEvents()
    d = stack.controller.item(did)
    assert d.status == Status.WATCHING and d.current_episode == 11


def test_sidebar_filter_and_local_search(stack, seeded):
    stack.window.sidebar.set_current("all")
    stack.qapp.processEvents()
    assert stack.window.dashboard.backend.count() == 4

    stack.window.dashboard._search.setText("ling")
    stack.qapp.processEvents()
    assert stack.window.dashboard.backend.count() == 1

    stack.window.dashboard._search.setText("")
    stack.window.sidebar.set_current("planned")
    stack.qapp.processEvents()
    assert stack.window.dashboard.backend.count() == 1


def test_minus_disabled_states_in_view(stack, seeded):
    planned_id = seeded["ids"][3]  # 0/46 → minus disabled
    stack.window.sidebar.set_current("planned")
    stack.qapp.processEvents()
    row = _row_of(stack, planned_id)
    assert row._minus.isEnabled() is False
    assert row._plus.isEnabled() is True


def test_shutdown_flushes_pending(stack, seeded):
    did = seeded["ids"][2]  # Ling Long 3/? (total=0)
    _row_of(stack, did)._plus.click()
    stack.qapp.processEvents()  # pending w workerze, bez flusha
    stack.teardown()  # shutdown = flush + checkpoint
    conn = sqlite3.connect(stack.db_path, timeout=2.0)
    try:
        cur = conn.execute("SELECT current_episode FROM donghua WHERE id=?", (did,)).fetchone()
    finally:
        conn.close()
    assert cur[0] == 4
