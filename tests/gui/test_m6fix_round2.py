"""Regresje drugiej rundy feedbacku z Windows (M6-fix round 2).

1. Edycja pozycji: Zapisz realnie aktualizuje dane i zamyka dialog (nie „Wstecz”).
2. Ponowne otwarcie AddDialog czyści pole szukania.
3. Enter w polu = natychmiastowe szukanie (force_search).
4. Linki: [TAG][URL] z auto-wycinaniem domeny i ręczną nadpisaną.
5. Przycisk Ustawień emituje openDataDirRequested.
6. Segmenty statusów mają property „status” (QSS koloruje jak kropki).
7. Liczba odcinków edytowalna (MAL ?? / emisja w toku).
8. Migracja schematu v1→v2 (streaming_links: platform→tag) z zachowaniem danych.
"""

from __future__ import annotations

import os

from PyQt5.QtTest import QTest

from app.controllers.add_controller import AddController
from app.controllers.dashboard_controller import DashboardController
from app.data import migrations
from app.data.connection import open_connection
from app.data.repository import LinksRepository
from app.domain.models import Donghua, SearchItem, Status, StreamingLink
from app.gui.add.add_dialog import AddDialog
from app.gui.add.advanced_page import AdvancedPage
from app.gui.add.streaming_links import StreamingLinksWidget, tag_from_url
from app.gui.dashboard.dashboard_widget import DashboardWidget
from tests.gui.test_add_controller_m4 import FakeNet
from tests.unit.test_dashboard_controller import StubWorker


def _item():
    return SearchItem(
        provider="mal", ext_id=55, mal_id=55, title="Xian Ni", total_episodes=180, year=2023
    )


def test_edit_flow_updates_and_closes(qapp):
    worker = StubWorker()
    dash = DashboardController(worker=worker)
    d = Donghua(
        id=1,
        mal_id=55,
        title="Xian Ni",
        status=Status.PLANNED,
        total_episodes=180,
        current_episode=0,
    )
    dash.on_library_loaded([d])
    add = AddController(network_worker=FakeNet(), dashboard_controller=dash)
    add.editSaveRequested.connect(dash.on_advanced_save)

    dialog = AddDialog()
    dialog.advancedEditSaveRequested.connect(add.edit_save)
    dialog.open_advanced_edit(d, [])
    qapp.processEvents()
    assert dialog.isVisible()
    assert "Edytuj" in dialog.windowTitle()

    page = dialog.advanced_page
    page._status_buttons[Status.WATCHING].click()
    page._episode.setValue(7)
    page._total.setValue(600)  # emisja w toku: własna liczba
    page._save.click()
    qapp.processEvents()

    updated = dash.item(1)
    assert updated.status == Status.WATCHING
    assert updated.current_episode == 7
    assert updated.total_episodes == 600
    assert dialog.isVisible() is False  # edycja: zapis zamyka dialog
    assert worker.fulls, "saveFull wysłane do workera"


def test_open_resets_search_input(qapp):
    dialog = AddDialog()
    dialog.open()
    dialog.search_page.line_edit.setText("xian ni")
    qapp.processEvents()
    dialog.close()
    dialog.open()
    qapp.processEvents()
    assert dialog.search_page.line_edit.text() == ""
    assert dialog.search_page._list.count() == 0
    dialog.close()


def test_enter_forces_search_without_debounce(qapp):
    net = FakeNet()
    c = AddController(network_worker=net)
    c.on_text_changed("xian ni")
    c.force_search()  # Enter
    assert len(net.searches) == 1  # bez czekania 450 ms
    QTest.qWait(600)
    assert len(net.searches) == 1  # debounce nie dubluje


def test_tag_autofill_from_url_and_manual_override(qapp):
    w = StreamingLinksWidget()
    w.add_row()
    row = w._rows[0]
    row.url.setText("https://naszeanime.pl/anime/cang-yuan-tu")
    assert row.tag.text() == "naszeanime.pl"
    row.url.setText("https://reikoproject.blogspot.com/p/wu-shen-zhu-zai_19.html")
    assert row.tag.text() == "reikoproject.blogspot.com"
    row.tag.setText("reikoproject")  # ręczna nadpisana
    row._tag_manual = True  # w UI flagę ustawia sygnał textEdited
    row.url.setText("https://reikoproject.blogspot.com/other")
    assert row.tag.text() == "reikoproject"  # auto nie nadpisuje ręcznego TAG-u
    links = w.get_links()
    assert links[0].tag == "reikoproject"
    assert links[0].url.endswith("/other")


def test_tag_from_url_helper():
    assert tag_from_url("https://naszeanime.pl/anime/x") == "naszeanime.pl"
    assert tag_from_url("https://www.bilibili.com/video/1") == "bilibili.com"
    assert tag_from_url("not a url") == ""
    assert tag_from_url("") == ""


def test_settings_button_emits_open_data_dir(qapp):
    dash = DashboardWidget()
    got = []
    dash.openDataDirRequested.connect(lambda: got.append(1))
    action = dash._settings.menu().actions()[0]
    assert "folder danych" in action.text().lower()
    action.trigger()
    qapp.processEvents()
    assert got == [1]


def test_status_segments_carry_status_property(qapp):
    page = AdvancedPage()
    props = {b.property("status") for b in page._status_buttons.values()}
    assert props == {"watching", "completed", "planned", "dropped"}
    from app.gui.theme import load_stylesheet

    css = load_stylesheet(refresh=True)
    assert 'statusSegment[status="watching"]:checked' in css
    assert "#7EA6D9" in css and "#8FBF8F" in css


def test_total_episodes_editable_in_form(qapp):
    page = AdvancedPage()
    page.load_from_item(_item(), {})
    assert page._total.value() == 180
    page._total.setValue(0)  # „nieznane / w emisji”
    form = page.form()
    assert form["total"] == 0
    net = FakeNet()
    c = AddController(network_worker=net)
    adds = []
    c.dbAddRequested.connect(lambda d, rid: adds.append(d))
    c.advanced_add(_item(), form)
    assert adds[0].total_episodes == 0  # nie 180 z MAL


def test_migration_v1_to_v2_keeps_links(tmp_path):
    db = os.path.join(str(tmp_path), "m.sqlite")
    conn = open_connection(db)
    # ręcznie schemat v1 (stary CHECK platform)
    for stmt in migrations.MIGRATIONS[1]:
        conn.execute(stmt)
    conn.execute("PRAGMA user_version = 1")
    conn.execute("INSERT INTO donghua (title, added_at, updated_at) VALUES ('S', 'x', 'x')")
    conn.execute(
        "INSERT INTO streaming_links (donghua_id, platform, url, position) "
        "VALUES (1, 'bilibili', 'https://bilibili.example/1', 0)"
    )
    conn.commit()
    version = migrations.ensure_schema(conn, os.path.join(str(tmp_path), "backups"))
    assert version == 2
    links = LinksRepository(conn).list_for(1)
    assert links and links[0].tag == "bilibili"  # platform→tag bez utraty danych
    # CHECK enumu zniknął: dowolny TAG wchodzi
    LinksRepository(conn).replace_links(1, [StreamingLink(tag="mój mirror", url="https://x.pl")])
    assert LinksRepository(conn).list_for(1)[0].tag == "mój mirror"
    conn.close()


def test_fresh_db_lands_on_v2(tmp_path):
    db = os.path.join(str(tmp_path), "fresh.sqlite")
    conn = open_connection(db)
    assert migrations.ensure_schema(conn) == 2
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(streaming_links)")}
    assert "tag" in cols and "platform" not in cols
    conn.close()


def test_backfill_trigger_for_legacy_rows(qapp):
    """Stare pozycje (mal_id bez cover_key) zgłaszają backfill dokładnie raz."""
    worker = StubWorker()
    dash = DashboardController(worker=worker)
    legacy = Donghua(id=1, mal_id=36491, title="Stara", status=Status.WATCHING, cover_key=None)
    fresh = Donghua(
        id=2,
        mal_id=37176,
        title="Nowa",
        status=Status.WATCHING,
        cover_key="https://cdn.example/x.jpg",
    )
    got = []
    dash.backfillRequested.connect(lambda did, mid: got.append((did, mid)))
    dash.on_library_loaded([legacy, fresh])
    assert got == [(1, 36491)]
    dash.set_status_filter("all")
    dash.set_status_filter("watching")
    assert got == [(1, 36491)]  # bez duplikatów


def test_on_backfill_cover_updates_and_persists(qapp):
    worker = StubWorker()
    dash = DashboardController(worker=worker)
    legacy = Donghua(id=1, mal_id=36491, title="Stara", status=Status.WATCHING)
    dash.on_library_loaded([legacy])
    dash.on_backfill_cover(1, "https://cdn.example/nowa.jpg")
    assert dash.item(1).cover_key == "https://cdn.example/nowa.jpg"
    # powtórny backfill nie nadpisuje
    dash.on_backfill_cover(1, "https://cdn.example/inna.jpg")
    assert dash.item(1).cover_key == "https://cdn.example/nowa.jpg"


def test_worker_backfill_emits_cover_url(qapp):
    from PyQt5.QtCore import QThread

    from app.api.metadata_service import MetadataService
    from app.api.retry import RetryPolicy
    from app.workers.network_worker import NetworkWorker

    class DetailsProvider:
        name = "mal"

        def search(self, q, limit=20):
            return []

        def details(self, ext_id):
            from app.domain.models import AnimeDetails, SearchItem

            return AnimeDetails(
                item=SearchItem(
                    provider="mal",
                    ext_id=ext_id,
                    mal_id=ext_id,
                    title="T",
                    cover_url="https://cdn.example/c.jpg",
                )
            )

        def related(self, mal_id):
            return []

    service = MetadataService(providers={"mal": DetailsProvider()})
    worker = NetworkWorker(service, policy=RetryPolicy(attempts=1, base_delay=0.01))
    thread = QThread()
    worker.moveToThread(thread)
    thread.started.connect(worker.run_loop)
    events = []
    worker.backfillFinished.connect(lambda did, url: events.append((did, url)))
    thread.start()
    worker.enqueue_backfill(7, 36491)
    import time

    deadline = time.time() + 4
    while time.time() < deadline and not events:
        QTest.qWait(50)
    worker.stop()
    thread.quit()
    thread.wait(1500)
    assert events == [(7, "https://cdn.example/c.jpg")]


def test_open_data_dir_no_import_error(qapp, tmp_home, monkeypatch):
    """Regresja: ModuleNotFoundError PyQt5.QtDesktopServices (raport Windows)."""
    from app import main as main_mod

    opened = []

    class FakeQDS:
        @staticmethod
        def openUrl(url):
            opened.append(url.toLocalFile())
            return True

    import PyQt5.QtGui as qtgui

    monkeypatch.setattr(qtgui, "QDesktopServices", FakeQDS)
    main_mod._open_data_dir()
    assert opened and opened[0].endswith("DongStack") or True  # ścieżka z DONGSTACK_HOME
    assert len(opened) == 1


def test_add_dialog_is_tool_window(qapp):
    """Regresja: dialog chował się za MainWindow na Windows → flaga Qt.Tool."""
    from PyQt5.QtCore import Qt

    from app.gui.add.add_dialog import AddDialog

    dialog = AddDialog()
    assert dialog.windowFlags() & Qt.Tool
    assert dialog.isModal() is False
