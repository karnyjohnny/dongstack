"""Regresje rundy 4 feedbacku z Windows (M6-fix r4).

1. PPM na karcie = wyłącznie menu kontekstowe (bez okna edycji).
2. Kosz w edycji: soft-delete + SnackBar „Cofnij” (Undo zamiast Confirm).
3. „Dodaj link” zawsze na górze sekcji; wiersze pod spodem.
4. Ctrl+V z URL-em w schowku = nowy wiersz linku (gdy focus nie w polu).
5. Aspect ratio okładek 225/318 (57×80 karta, 44×62 wynik).
6. Fallback okładki: CDN MAL pada → CDN AniList po idMal.
"""

from __future__ import annotations

import time

from PyQt5.QtCore import Qt, QThread
from PyQt5.QtTest import QTest
from PyQt5.QtWidgets import QApplication

from app.api.metadata_service import MetadataService
from app.api.retry import RetryPolicy
from app.controllers.add_controller import AddController
from app.controllers.dashboard_controller import DashboardController
from app.core.errors import ApiError, ApiErrorKind
from app.domain.models import Donghua, SearchItem, Status
from app.gui.add.add_dialog import AddDialog
from app.gui.add.search_page import SearchPage
from app.gui.add.streaming_links import StreamingLinksWidget
from app.gui.dashboard.donghua_row import DonghuaRow
from app.workers.network_worker import NetworkWorker
from tests.gui.test_add_controller_m4 import FakeNet
from tests.unit.test_dashboard_controller import StubWorker


def _d(**kw):
    base = dict(id=1, mal_id=55, title="X", status=Status.WATCHING, total_episodes=12)
    base.update(kw)
    return Donghua(**base)


def test_right_click_does_not_open_edit(qapp):
    row = DonghuaRow()
    row.set_donghua(_d())
    got = []
    row.detailsRequested.connect(got.append)
    QTest.mouseClick(row, Qt.RightButton)
    qapp.processEvents()
    assert got == []  # PPM = tylko menu kontekstowe
    QTest.mouseClick(row, Qt.LeftButton)
    qapp.processEvents()
    assert got == [1]


def test_delete_button_only_in_edit_mode_and_flow(qapp):
    worker = StubWorker()
    dash = DashboardController(worker=worker)
    dash.on_library_loaded([_d(id=3, mal_id=77, title="Do usunięcia")])
    add = AddController(network_worker=FakeNet(), dashboard_controller=dash)

    dialog = AddDialog()
    dialog.advancedEditSaveRequested.connect(add.edit_save)
    dialog.deleteRequested.connect(dash.on_remove_requested)

    dialog.open_advanced(SearchItem(provider="mal", ext_id=1, mal_id=1, title="Nowa"))
    qapp.processEvents()
    assert dialog.advanced_page._delete.isHidden() is True  # add: bez kosza

    dialog.open_advanced_edit(dash.item(3), [])
    qapp.processEvents()
    assert dialog.advanced_page._delete.isHidden() is False  # edycja: kosz widoczny

    snacks = []
    dash.snackRequested.connect(lambda t, a, cb: snacks.append((t, a, cb)))
    dialog.advanced_page._delete.click()
    qapp.processEvents()
    assert dash.item(3) is None  # soft-delete z pamięci
    assert worker.deletes and worker.deletes[0][0] == 3
    assert snacks and "Usunięto" in snacks[0][0] and snacks[0][1] == "Cofnij"

    snacks[0][2]()  # Undo z SnackBara
    qapp.processEvents()
    assert dash.item(3) is not None  # przywrócone
    assert worker.restores and worker.restores[0][0] == 3


def test_add_link_button_pinned_top(qapp):
    w = StreamingLinksWidget()
    assert w._layout.itemAt(0).widget() is w._add  # przycisk zawsze pierwszy
    w.add_row(url="https://a.pl/1")
    w.add_row(url="https://b.pl/2")
    assert w._layout.itemAt(1).widget() is w._rows[0]
    assert w._layout.itemAt(2).widget() is w._rows[1]


def test_ctrl_v_pastes_url_as_link(qapp):
    dialog = AddDialog()
    dialog.open()
    dialog.open_advanced(
        SearchItem(provider="mal", ext_id=9, mal_id=9, title="T", total_episodes=10)
    )
    qapp.processEvents()
    cb = QApplication.clipboard()
    cb.setText("https://naszeanime.pl/anime/cang-yuan-tu")
    # focus poza polami edycji:
    dialog.advanced_page._title.setFocus()
    dialog._on_paste_url()
    qapp.processEvents()
    links = dialog.advanced_page.links.get_links()
    assert len(links) == 1 and links[0].tag == "naszeanime.pl"

    # focus w QLineEdit → zwykłe wklejenie, bez nowego wiersza
    edit = dialog.advanced_page.links._rows[0].url
    edit.setFocus()
    dialog._on_paste_url()
    qapp.processEvents()
    assert len(dialog.advanced_page.links.get_links()) == 1

    # tekst nie-URL w schowku → ignorowany
    dialog.advanced_page._title.setFocus()
    cb.setText("to nie jest adres")
    dialog._on_paste_url()
    assert len(dialog.advanced_page.links.get_links()) == 1


def test_cover_aspect_ratio_widgets(qapp):
    row = DonghuaRow()
    row.set_donghua(_d())
    assert (row._cover.width(), row._cover.height()) == (57, 80)  # 225/318
    from app.gui.add.mal_result_row import MalResultRow

    mrow = MalResultRow()
    mrow.set_item(SearchItem(provider="mal", ext_id=1, mal_id=1, title="T"))
    assert (mrow._cover.width(), mrow._cover.height()) == (44, 62)


def test_cover_fallback_to_anilist_cdn(qapp):
    """CDN MAL pada → okładka z CDN AniList (key cache pozostaje oryginalny URL)."""
    mal_url = "https://cdn.myanimelist.net/images/anime/x.jpg"
    ani_url = "https://s4.anilist.co/file/anilist.co/media/anime/cover/medium/x.jpg"

    from PyQt5.QtCore import QBuffer, QIODevice
    from PyQt5.QtGui import QImage

    img = QImage(30, 42, QImage.Format_RGB32)
    img.fill(0xFF336699)
    buf = QBuffer()
    buf.open(QIODevice.WriteOnly)
    img.save(buf, "PNG")
    png = bytes(buf.data())

    calls = []

    def fake_http(url):
        calls.append(url)
        if url == mal_url:
            raise ApiError(ApiErrorKind.NETWORK, "cdn zablokowany", provider="covers")
        return png

    class AniCovers:
        name = "anilist"

        def covers_for_mal(self, mal_id):
            return [ani_url]

        def search(self, q, limit=20):
            return []

        def related(self, mid):
            return []

    service = MetadataService(providers={"anilist": AniCovers()})
    worker = NetworkWorker(service, policy=RetryPolicy(attempts=1), http_get=fake_http)
    events = []
    worker.coverReady.connect(lambda u, i, b: events.append((u, b)))
    thread = QThread()
    worker.moveToThread(thread)
    thread.started.connect(worker.run_loop)
    thread.start()
    worker.enqueue_cover(mal_url, 55)
    deadline = time.time() + 4
    while time.time() < deadline and not events:
        QTest.qWait(50)
    worker.stop()
    thread.quit()
    thread.wait(1500)
    assert calls[:2] == [mal_url, ani_url]  # próba MAL, potem fallback
    assert events and events[0][0] == mal_url  # key = oryginalny URL
    assert events[0][1] == png  # świeże bajty do zapisu


def test_library_load_requests_covers(qapp):
    """Start aplikacji zamawia okładki widocznych pozycji (bug: brak po restarcie)."""
    worker = StubWorker()
    dash = DashboardController(worker=worker)
    got = []
    dash.coversRequested.connect(got.append)
    url = "https://cdn.myanimelist.net/images/anime/1.jpg"
    dash.on_library_loaded([_d(id=5, mal_id=50, cover_key=url)])
    assert got and any(getattr(e, "cover_key", None) == url for e in got[0])


def test_empty_note_points_to_other_statuses(qapp):
    from app.gui.main_window import MainWindow

    w = MainWindow(animations_enabled=False)
    w.show()
    w.set_items([])  # pusty widok "W trakcie"
    w.set_counts({"all": 3, "watching": 0, "completed": 0, "planned": 3, "dropped": 0})
    qapp.processEvents()
    hint = w.dashboard._empty.text()
    assert "innych statusach" in hint and "3" in hint
    w.hide()


def test_first_search_cancel_does_not_kill_covers(qapp):
    """Bug produkcyjny: cancel(0) z pierwszego wyszukiwania zabijał cover taski (rid=0)."""
    net = FakeNet()
    c = AddController(network_worker=net)
    c.on_text_changed("xian ni")
    QTest.qWait(600)
    qapp.processEvents()
    assert 0 not in net.cancelled  # rid 0 nigdy nie jest anulowany
    c.on_text_changed("xian ni movie")
    QTest.qWait(600)
    qapp.processEvents()
    assert net.cancelled == [1]  # anulowany tylko REALNY poprzedni rid


def test_cover_task_survives_cancel_zero(qapp):
    """Cover z rid=None dochodzi nawet po cancel(0) (stary bug)."""
    import time as _time

    from PyQt5.QtCore import QBuffer, QIODevice, QThread
    from PyQt5.QtGui import QImage

    img = QImage(20, 28, QImage.Format_RGB32)
    img.fill(0xFF224466)
    buf = QBuffer()
    buf.open(QIODevice.WriteOnly)
    img.save(buf, "PNG")
    png = bytes(buf.data())

    service = MetadataService(providers={})
    worker = NetworkWorker(service, policy=RetryPolicy(attempts=1), http_get=lambda url: png)
    worker.cancel(0)  # symulacja starego buga
    events = []
    worker.coverReady.connect(lambda u, i, b: events.append(u))
    thread = QThread()
    worker.moveToThread(thread)
    thread.started.connect(worker.run_loop)
    thread.start()
    worker.enqueue_cover("https://cdn.example/a.jpg", 55)
    deadline = _time.time() + 4
    while _time.time() < deadline and not events:
        QTest.qWait(50)
    worker.stop()
    thread.quit()
    thread.wait(1500)
    assert events == ["https://cdn.example/a.jpg"]


def test_quick_add_duplicate_informs_instead_of_pseudo_add(qapp):
    """Feedback r5: quick-add żyjącego duplikatu nie udaje dodawania."""
    worker = StubWorker()
    dash = DashboardController(worker=worker)
    dash.on_library_loaded([_d(id=1, mal_id=55809, title="Xian Ni", status=Status.COMPLETED)])
    add = AddController(network_worker=FakeNet(), dashboard_controller=dash)
    snacks = []
    add.snackRequested.connect(lambda t, a, cb: snacks.append((t, a, cb)))
    adds = []
    add.dbAddRequested.connect(lambda d, rid: adds.append(d))

    add.quick_add(SearchItem(provider="mal", ext_id=55809, mal_id=55809, title="Xian Ni"))
    qapp.processEvents()
    assert adds == []  # zero zapisu do bazy
    assert snacks and "już jest w bibliotece" in snacks[0][0]
    assert "Obejrzane" in snacks[0][0]


def test_last_filter_persisted_and_restored(qapp, tmp_home):
    """Restart nie gubi kontekstu: filtr/sort zapisane w config.json (QoL r5)."""
    from app.core.config import KEY_LAST_FILTER, KEY_LAST_SORT, ConfigService

    cfg = ConfigService(config_file=os.path.join(tmp_home, "config.json"), env={})
    cfg.set(KEY_LAST_FILTER, "planned")
    cfg.set(KEY_LAST_SORT, "alpha")

    worker = StubWorker()
    dash = DashboardController(
        worker,
        initial_status=cfg.get(KEY_LAST_FILTER) or "watching",
        initial_sort=SortMode(cfg.get(KEY_LAST_SORT) or "updated"),
    )
    assert dash.status_filter == "planned"
    assert dash.sort_mode == SortMode.ALPHA


import os  # noqa: E402  (dla tmp_home w teście wyżej)

from app.domain.models import SortMode  # noqa: E402


def test_sidebar_reflects_restored_filter(qapp):
    from app.gui.main_window import MainWindow

    worker = StubWorker()
    dash = DashboardController(worker, initial_status="planned")
    window = MainWindow(animations_enabled=False)
    from app.main import _wire

    _wire(window, dash)
    window.sidebar.set_current(dash.status_filter)
    window.dashboard.set_section_title(dash.status_label())
    qapp.processEvents()
    assert window.sidebar.current_status == "planned"
    assert window.dashboard._section.text() == "Planowane"
    window.hide()


def test_late_cover_after_rebuild_does_not_crash(qapp):
    """Crash produkcyjny v1.0.0: okładka dostarczona PO przebudowie listy.

    Stare wiersze są deleteLater-owane; apply_cover musi przeżyć martwe QLabel
    (RuntimeError: wrapped C/C++ object of type QLabel has been deleted).
    """
    from PyQt5.QtGui import QColor, QPixmap

    page = SearchPage()
    url = "https://cdn.example/late.jpg"
    page.show_results(
        [SearchItem(provider="mal", ext_id=1, mal_id=1, title="A", cover_url=url)],
        "mal",
        set(),
    )
    qapp.processEvents()
    page.show_searching()  # przebudowa: stare wiersze -> deleteLater
    qapp.processEvents()  # Qt faktycznie usuwa obiekty C++
    pm = QPixmap(44, 62)
    pm.fill(QColor(0xB3, 0x9D, 0xDB))
    page.apply_cover(url, pm)  # przed fixem: RuntimeError / crash okna
    # mapa martwych referencji wyczyszczona
    assert page._cover_rows.get(url) in (None, [])
    # nowa lista nadal przyjmuje okładki
    page.show_results(
        [SearchItem(provider="mal", ext_id=2, mal_id=2, title="B", cover_url=url)],
        "mal",
        set(),
    )
    qapp.processEvents()
    page.apply_cover(url, pm)
    row = page._list.itemWidget(page._list.item(0))
    assert not row._cover.pixmap().isNull()
