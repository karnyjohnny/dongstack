"""Testy DbWorker (M3): load, koalescencja 250 ms, ack/nack, shutdown. Offscreen."""

from __future__ import annotations

import os

import pytest
from PyQt5.QtTest import QTest

from app.data.repository import DonghuaRepository
from app.domain.models import Donghua, MediaType, Status
from app.workers.db_worker import DbWorker


class CountingRepository(DonghuaRepository):
    updates = 0

    def update_progress(self, donghua_id, episode, status, now_iso=None):
        CountingRepository.updates += 1
        return super().update_progress(donghua_id, episode, status, now_iso)


class FailingRepository(DonghuaRepository):
    def update_progress(self, donghua_id, episode, status, now_iso=None):
        import sqlite3

        raise sqlite3.OperationalError("symulowany błąd zapisu")


@pytest.fixture()
def worker(tmp_home):
    w = DbWorker(os.path.join(tmp_home, "dongstack.sqlite"), os.path.join(tmp_home, "backups"))
    yield w
    w.shutdown()


def test_load_empty_library(qapp, worker):
    got = []
    worker.libraryLoaded.connect(got.append)
    worker.loadLibrary()
    assert got == [[]]


def test_add_and_reload(qapp, worker):
    added = []
    worker.addSucceeded.connect(lambda d, rid: added.append((d, rid)))
    worker.addDonghua(
        Donghua(title="Nowość", total_episodes=12, status=Status.PLANNED, media_type=MediaType.ONA),
        77,
    )
    qapp.processEvents()
    assert added and added[0][0].id > 0 and added[0][1] == 77

    loaded = []
    worker.libraryLoaded.connect(loaded.append)
    worker.loadLibrary()
    assert len(loaded[-1]) == 1
    assert loaded[-1][0].title == "Nowość"


def test_coalescing_ten_clicks_one_write(qapp, tmp_home):
    CountingRepository.updates = 0
    w = DbWorker(
        os.path.join(tmp_home, "dongstack.sqlite"),
        os.path.join(tmp_home, "backups"),
        repo_factory=CountingRepository,
    )
    # seed pozycji
    seed = []
    w.addSucceeded.connect(lambda d, rid: seed.append(d))
    w.addDonghua(Donghua(title="S", total_episodes=30, status=Status.WATCHING), 1)
    qapp.processEvents()
    did = seed[0].id

    acks = []
    w.saveSucceeded.connect(lambda i, rid: acks.append((i, rid)))
    for rid in range(10):  # 10 szybkich klików bez przerwy
        w.saveEpisode(did, rid + 1, Status.WATCHING.value, rid)
    assert CountingRepository.updates == 0  # nic nie zapisane przed flush
    w.flush()
    qapp.processEvents()
    assert len(acks) == 1  # JEDEN ack (scalone)
    assert acks[0] == (did, 9)  # najnowszy request_id
    assert CountingRepository.updates == 1  # JEDEN UPDATE (R10)

    loaded = []
    w.libraryLoaded.connect(loaded.append)
    w.loadLibrary()
    assert loaded[-1][0].current_episode == 10
    w.shutdown()


def test_timer_auto_flush_after_250ms(qapp, worker):
    acks = []
    worker.addSucceeded.connect(lambda d, rid: acks.append(("add", d.id)))
    worker.addDonghua(Donghua(title="T", total_episodes=5, status=Status.WATCHING), 1)
    qapp.processEvents()
    did = acks[-1][1]

    saves = []
    worker.saveSucceeded.connect(lambda i, rid: saves.append((i, rid)))
    worker.saveEpisode(did, 2, Status.WATCHING.value, 42)
    assert saves == []
    QTest.qWait(400)  # timer 250 ms sam flushuje
    qapp.processEvents()
    assert saves == [(did, 42)]


def test_save_failed_emitted_on_repo_error(qapp, tmp_home):
    w = DbWorker(
        os.path.join(tmp_home, "dongstack.sqlite"),
        os.path.join(tmp_home, "backups"),
        repo_factory=FailingRepository,
    )
    seed = []
    w.addSucceeded.connect(lambda d, rid: seed.append(d))  # insert działa (FAIL tylko update)
    w.addDonghua(Donghua(title="F", total_episodes=5, status=Status.WATCHING), 1)
    qapp.processEvents()
    did = seed[0].id

    fails = []
    w.saveFailed.connect(lambda i, rid, msg: fails.append((i, rid, msg)))
    w.saveEpisode(did, 2, Status.WATCHING.value, 5)
    w.flush()
    qapp.processEvents()
    assert fails and fails[0][1] == 5 and "symulowany" in fails[0][2]
    w.shutdown()


def test_soft_delete_and_restore(qapp, worker):
    seed = []
    worker.addSucceeded.connect(lambda d, rid: seed.append(d))
    worker.addDonghua(Donghua(title="D", total_episodes=5, status=Status.PLANNED), 1)
    qapp.processEvents()
    did = seed[0].id

    done = []
    worker.removeSucceeded.connect(lambda i, rid: done.append(("del", i, rid)))
    worker.softDelete(did, 10)
    qapp.processEvents()
    loaded = []
    worker.libraryLoaded.connect(loaded.append)
    worker.loadLibrary()
    assert loaded[-1] == []

    worker.restore(did, 11)
    qapp.processEvents()
    worker.loadLibrary()
    assert len(loaded[-1]) == 1
    assert len(done) == 2


def test_shutdown_closes_connection(qapp, worker):
    worker.loadLibrary()
    worker.shutdown()
    assert worker._conn is None and worker._repo is None


def test_create_and_attach_universe(qapp, worker):
    """Regresja r6: createUniverse używa UniverseRepository (AttributeError 'create')."""
    seed = []
    worker.addSucceeded.connect(lambda d, rid: seed.append(d))
    worker.addDonghua(Donghua(title="S1", total_episodes=12, status=Status.WATCHING), 1)
    qapp.processEvents()
    did = seed[0].id

    created = []
    worker.universeCreated.connect(lambda uid, name, rid: created.append((uid, name)))
    worker.createUniverse("Doupo Cangqiong", 36491, 77)
    qapp.processEvents()
    assert created and created[0][1] == "Doupo Cangqiong"
    uid = created[0][0]

    attached = []
    worker.universeAttached.connect(lambda d, u, rid: attached.append((d, u)))
    worker.attachUniverse(did, uid, 78)
    qapp.processEvents()
    assert attached == [(did, uid)]

    loaded = []
    worker.libraryLoaded.connect(loaded.append)
    worker.loadLibrary()
    assert loaded[-1][0].universe_id == uid
