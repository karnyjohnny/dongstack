"""Testy M5 GUI: pipeline okładek (worker→GUI→DbWorker), AdvancedPage, failover e2e."""

from __future__ import annotations

import os

from PyQt5.QtCore import QBuffer, QIODevice, QObject, QThread, pyqtSignal
from PyQt5.QtGui import QImage
from PyQt5.QtTest import QTest

from app.api.circuit_breaker import CircuitBreaker
from app.api.metadata_service import MetadataService
from app.api.retry import RetryPolicy
from app.core.errors import ApiError, ApiErrorKind
from app.data.connection import open_connection
from app.data.cover_store import CoverStore, cover_key
from app.domain.models import SearchItem, Status
from app.gui.add.add_dialog import AddDialog
from app.gui.add.advanced_page import AdvancedPage
from app.gui.cover_coordinator import CoverCoordinator
from app.gui.dashboard.list_backend import WidgetListBackend
from app.workers.network_worker import NetworkWorker

FAST = RetryPolicy(attempts=1, base_delay=0.01, max_delay=0.02, jitter=0.0)


def _png_bytes(w=8, h=10, color=(200, 100, 50)):
    img = QImage(w, h, QImage.Format_RGB32)
    img.fill(QImage(*color).pixel(0, 0) if False else img.pixel(0, 0))
    img.fill(0xFFC86432)
    buf = QBuffer()
    buf.open(QIODevice.WriteOnly)
    img.save(buf, "PNG")
    return bytes(buf.data())


class FakeNetCovers(QObject):
    """Mini-worker okładek: rejestruje enqueue, ma sygnały coverReady/Failed."""

    coverReady = pyqtSignal(str, object, object)
    coverFailed = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.enqueued = []

    def enqueue_cover(self, url, rid=0):
        self.enqueued.append(url)


def test_coordinator_lru_and_save_request(qapp, tmp_home):
    backend = WidgetListBackend()
    from app.domain.models import Donghua

    url = "https://cdn.example/cover1.jpg"
    d = Donghua(id=1, title="X", cover_key=url, status=Status.WATCHING)
    backend.set_items([d])

    net = FakeNetCovers()
    coord = CoverCoordinator(backend, net)
    saves = []
    coord.saveCoverRequested.connect(lambda k, u, b: saves.append((k, u, b)))

    coord.request_covers([d])
    assert net.enqueued == [url]
    coord.request_covers([d])  # in-flight: bez duplikatu
    assert len(net.enqueued) == 1

    img = QImage(36, 44, QImage.Format_RGB32)
    img.fill(0xFF112233)
    coord.on_cover_ready(url, img, b"BYTES")
    row = backend.row_widget(1)
    assert not row._cover.pixmap().isNull()  # QPixmap w wątku GUI (R3)
    assert saves and saves[0][0] == cover_key(url) and saves[0][2] == b"BYTES"

    # drugi request: z LRU, bez sieci
    coord.request_covers([d])
    assert len(net.enqueued) == 1


def test_worker_cover_from_disk_and_http(qapp, tmp_home):
    covers_dir = os.path.join(tmp_home, "covers")
    db_path = os.path.join(tmp_home, "c.sqlite")
    conn = open_connection(db_path)
    from app.data import migrations

    migrations.ensure_schema(conn)
    store_rw = CoverStore(conn, covers_dir)
    url_disk = "https://cdn.example/disk.jpg"
    store_rw.put(cover_key(url_disk), url_disk, _png_bytes())

    http_calls = []

    def fake_get(url):
        http_calls.append(url)
        return _png_bytes()

    service = MetadataService(providers={}, breakers={})
    worker = NetworkWorker(
        service,
        policy=FAST,
        covers_factory=lambda: CoverStore(open_connection(db_path, readonly=True), covers_dir),
        http_get=fake_get,
    )
    thread = QThread()
    worker.moveToThread(thread)
    thread.started.connect(worker.run_loop)
    events = []
    worker.coverReady.connect(lambda u, i, b: events.append((u, b)))
    thread.start()

    url_net = "https://cdn.example/net.jpg"
    worker.enqueue_cover(url_disk)
    worker.enqueue_cover(url_net)
    import time

    deadline = time.time() + 4
    while time.time() < deadline and len(events) < 2:
        QTest.qWait(50)
    worker.stop()
    thread.quit()
    thread.wait(1500)
    conn.close()

    got = {u: b for u, b in events}
    assert url_disk in got and got[url_disk] is None  # z dysku: bez bajtów
    assert url_net in got and got[url_net] == _png_bytes()  # z sieci: bajty do zapisu
    assert http_calls == [url_net]


def test_advanced_page_form_roundtrip(qapp):
    page = AdvancedPage()
    item = SearchItem(
        provider="mal", ext_id=5, mal_id=5, title="Seria", total_episodes=24, year=2021
    )
    page.load_from_item(item, {})
    page._status_buttons[Status.WATCHING].click()
    page._episode.setValue(24)
    page.links.add_row(url="https://bilibili.com/1")
    form = page.form()
    assert form["status"] == Status.WATCHING
    assert form["episode"] == 24
    assert len(form["links"]) == 1
    assert form["universe"] is None
    assert form["editing"] is None


def test_advanced_page_episode_capped(qapp):
    page = AdvancedPage()
    item = SearchItem(provider="mal", ext_id=5, mal_id=5, title="S", total_episodes=12)
    page.load_from_item(item, {})
    page._episode.setValue(99)
    assert page.form()["episode"] == 12


def test_dialog_stack_switch_and_universe_new(qapp):
    dialog = AddDialog()
    item = SearchItem(provider="mal", ext_id=9, mal_id=9, title="U Series", total_episodes=10)
    dialog.open()
    dialog.open_advanced(item)
    qapp.processEvents()
    assert dialog.stack.currentIndex() == 1
    dialog.advanced_page._universe.setCurrentIndex(1)  # „— Utwórz nowe…”
    assert dialog.advanced_page._new_universe.isVisible()
    dialog.advanced_page._new_universe.setText("Moje Uni")
    forms = []
    dialog.advancedSaveRequested.connect(lambda i, f: forms.append((i, f)))
    dialog.advanced_page._save.click()
    qapp.processEvents()
    assert forms and forms[0][0] is item
    assert forms[0][1]["universe"] == ("new", "Moje Uni")
    assert dialog.stack.currentIndex() == 0  # powrót na search (Biblia §25)


def test_worker_failover_e2e(qapp):
    """MAL padnięty (breaker open) → wyszukiwanie przechodzi na AniList (worker-level)."""

    class MalDown:
        name = "mal"

        def search(self, q, limit=20):
            raise ApiError(ApiErrorKind.SERVER, "500", provider="mal")

        def related(self, mid):
            return []

    class AniUp:
        name = "anilist"

        def __init__(self):
            self.calls = 0

        def search(self, q, limit=20):
            self.calls += 1
            return [SearchItem(provider="anilist", ext_id=1, mal_id=11, title="Z Ani")]

        def related(self, mid):
            return []

    ani = AniUp()
    service = MetadataService(
        providers={"mal": MalDown(), "anilist": ani},
        preferred="mal",
        breakers={"mal": CircuitBreaker(threshold=1), "anilist": CircuitBreaker()},
    )
    worker = NetworkWorker(service, policy=FAST)
    thread = QThread()
    worker.moveToThread(thread)
    thread.started.connect(worker.run_loop)
    events = []
    worker.searchFinished.connect(lambda r, i, p: events.append((r, p)))
    thread.start()
    worker.enqueue_search("x", 1)
    worker.enqueue_search("y", 2)
    import time

    deadline = time.time() + 5
    while time.time() < deadline and len(events) < 2:
        QTest.qWait(50)
    worker.stop()
    thread.quit()
    thread.wait(1500)
    providers = [p for _, p in events]
    assert providers == ["anilist", "anilist"]  # breaker MAL open → bez prób MAL
    assert ani.calls == 2
