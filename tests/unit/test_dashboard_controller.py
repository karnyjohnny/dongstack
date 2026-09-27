"""Testy DashboardController (M3): optymistyczny update, rollback, Undo, filtry."""

from __future__ import annotations

import time

from PyQt5.QtCore import QObject, pyqtSignal, pyqtSlot

from app.controllers.dashboard_controller import DashboardController
from app.core.demo_data import demo_rows
from app.domain.models import Donghua, Status


class StubWorker(QObject):
    """Zapisuje komendy synchronicznie (ten sam wątek) + pozwala symulować ack/nack."""

    libraryLoaded = pyqtSignal(list)
    universesLoaded = pyqtSignal(list)
    universeCreated = pyqtSignal(int, str, int)
    universeAttached = pyqtSignal(int, int, int)
    universeDeleted = pyqtSignal(int, int)  # r11: usuwanie uniwersów z Ustawień
    universeDeleteFailed = pyqtSignal(int, int, str)
    linksLoaded = pyqtSignal(dict)
    fullSaved = pyqtSignal(object, int)
    fullFailed = pyqtSignal(int, int, str)
    saveSucceeded = pyqtSignal(int, int)
    saveFailed = pyqtSignal(int, int, str)

    def __init__(self):
        super().__init__()
        self.saves = []  # (id, episode, status, rid)
        self.deletes = []
        self.restores = []
        self.fulls = []  # (donghua, links, rid)
        self.orders = []  # (id, order, rid)
        self.universe_deletes = []  # (universe_id, rid) — r11
        self.universe_creates = []  # (name, anchor, rid) — r11
        self.universe_attaches = []  # (donghua_id, universe_id, rid) — r11

    @pyqtSlot(int, int, str, int)
    def saveEpisode(self, did, ep, status, rid):
        self.saves.append((did, ep, status, rid))

    @pyqtSlot(int, int)
    def softDelete(self, did, rid):
        self.deletes.append((did, rid))

    @pyqtSlot(int, int)
    def restore(self, did, rid):
        self.restores.append((did, rid))

    @pyqtSlot(object, object, int)
    def saveFull(self, d, links, rid):
        self.fulls.append((d, list(links), rid))

    @pyqtSlot(int, int, int)
    def saveUniverseOrder(self, did, order, rid):
        self.orders.append((did, order, rid))

    @pyqtSlot(int, int)
    def deleteUniverse(self, uid, rid):
        self.universe_deletes.append((int(uid), int(rid)))

    @pyqtSlot(str, object, int)
    def createUniverse(self, name, anchor, rid):
        self.universe_creates.append((str(name), anchor, int(rid)))

    @pyqtSlot(int, int, int)
    def attachUniverse(self, did, uid, rid):
        self.universe_attaches.append((int(did), int(uid), int(rid)))


def _controller(rows=None, worker="stub"):
    w = StubWorker() if worker == "stub" else worker
    c = DashboardController(worker=w)
    c.on_library_loaded(rows if rows is not None else demo_rows(20))
    return c, w


def _snacks(c):
    out = []
    c.snackRequested.connect(lambda t, a, cb: out.append((t, a, cb)))
    return out


def test_initial_state_watching_and_counts():
    c, _ = _controller()
    assert c.status_filter == "watching"
    counts = c.counts()
    assert counts["all"] == 20
    visible = c.visible_items()
    assert all(d.status == Status.WATCHING for d in visible)


def test_increment_optimistic_and_save_dispatch():
    c, w = _controller()
    target = c.visible_items()[0]
    got = []
    c.itemChanged.connect(got.append)
    c.on_increment(target.id)
    assert got and got[0].current_episode == target.current_episode + 1
    assert c.item(target.id).current_episode == target.current_episode + 1
    assert len(w.saves) == 1
    assert w.saves[0][0] == target.id and w.saves[0][1] == target.current_episode + 1


def test_increment_at_cap_is_noop():
    rows = [
        Donghua(id=1, title="Cap", total_episodes=12, current_episode=12, status=Status.COMPLETED)
    ]
    c, w = _controller(rows=rows)
    got = []
    c.itemChanged.connect(got.append)
    c.on_increment(1)
    assert got == []
    assert w.saves == []


def test_decrement_from_completed_returns_to_watching():
    rows = [
        Donghua(id=1, title="Cap", total_episodes=12, current_episode=12, status=Status.COMPLETED)
    ]
    c, w = _controller(rows=rows)
    c.on_decrement(1)
    d = c.item(1)
    assert d.current_episode == 11
    assert d.status == Status.WATCHING
    assert w.saves[-1][2] == "watching"


def test_auto_complete_snack_with_undo():
    rows = [
        Donghua(id=1, title="Finał", total_episodes=3, current_episode=2, status=Status.WATCHING)
    ]
    c, w = _controller(rows=rows)
    snacks = _snacks(c)
    c.on_increment(1)
    assert c.item(1).status == Status.COMPLETED
    assert snacks and "ukończone" in snacks[0][0] and snacks[0][1] == "Cofnij"
    # Undo przywraca watching + 2/3 i wysyła zapis
    snacks[0][2]()
    d = c.item(1)
    assert d.status == Status.WATCHING and d.current_episode == 2
    assert w.saves[-1] == (1, 2, "watching", w.saves[-1][3])


def test_rollback_on_save_fail():
    c, w = _controller()
    target = c.visible_items()[0]
    before = target.current_episode
    c.on_increment(target.id)
    assert c.item(target.id).current_episode == before + 1
    rid = w.saves[-1][3]
    snacks = _snacks(c)
    w.saveFailed.emit(target.id, rid, "sqlite disk I/O error")
    assert c.item(target.id).current_episode == before  # ROLLBACK
    assert snacks and "Nie udało się zapisać" in snacks[0][0]


def test_stale_nack_ignored():
    c, w = _controller()
    target = c.visible_items()[0]
    c.on_increment(target.id)  # rid 1
    c.on_increment(target.id)  # rid 2
    rid1 = w.saves[0][3]
    value_now = c.item(target.id).current_episode
    w.saveFailed.emit(target.id, rid1, "stale")
    assert c.item(target.id).current_episode == value_now  # brak rollbacku


def test_save_ok_confirms_and_late_fail_is_ignored():
    c, w = _controller()
    target = c.visible_items()[0]
    c.on_increment(target.id)
    rid = w.saves[-1][3]
    w.saveSucceeded.emit(target.id, rid)
    snacks = _snacks(c)
    w.saveFailed.emit(target.id, rid, "po ack")
    assert snacks == []  # po ack brak rollbacku


def test_undo_two_increments():
    rows = [Donghua(id=1, title="U", total_episodes=10, current_episode=0, status=Status.PLANNED)]
    c, w = _controller(rows=rows)
    c.on_increment(1)  # 1, watching
    c.on_increment(1)  # 2
    c.undo_last()
    d = c.item(1)
    assert d.current_episode == 1 and d.status == Status.WATCHING


def test_filters_search_sort():
    rows = [
        Donghua(id=1, title="Alpha", status=Status.WATCHING, updated_at="2026-01-03T00:00:00.000Z"),
        Donghua(id=2, title="Beta", status=Status.PLANNED, updated_at="2026-01-02T00:00:00.000Z"),
        Donghua(
            id=3,
            title="Gamma Watchingish",
            status=Status.COMPLETED,
            updated_at="2026-01-01T00:00:00.000Z",
        ),
    ]
    c, _ = _controller(rows=rows)
    c.set_status_filter("all")
    assert [d.id for d in c.visible_items()] == [1, 2, 3]  # updated desc
    c.set_search("beta")
    assert [d.id for d in c.visible_items()] == [2]
    c.set_search("")
    c.set_sort("alpha")
    assert [d.id for d in c.visible_items()] == [1, 2, 3]
    c.set_sort("added")
    assert len(c.visible_items()) == 3
    c.set_status_filter("completed")
    assert [d.id for d in c.visible_items()] == [3]
    c.set_sort("nieznany-sort")  # ignorowane, bez crasha
    assert c.sort_mode.value == "added"


def test_search_matches_title_alt():
    rows = [
        Donghua(id=1, title="Doupo", title_alt="Battle Through the Heavens", status=Status.WATCHING)
    ]
    c, _ = _controller(rows=rows)
    c.set_status_filter("all")
    c.set_search("battle through")
    assert [d.id for d in c.visible_items()] == [1]


def test_gate_g2_increment_p95_under_8ms():
    c, w = _controller(rows=demo_rows(300))
    c.set_status_filter("all")
    ids = [
        d.id
        for d in c.visible_items()
        if d.total_episodes == 0 or d.current_episode < d.total_episodes
    ][:200]
    samples = []
    for did in ids:
        t0 = time.perf_counter()
        c.on_increment(did)
        samples.append((time.perf_counter() - t0) * 1000.0)
    samples.sort()
    p95 = samples[int(len(samples) * 0.95)]
    assert p95 <= 8.0, "gate G2: p95 handlera +1 = %.3f ms" % p95
