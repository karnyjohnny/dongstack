"""Regresje bugów produkcyjnych z Windows (runda M6-fix, raport Właściciela).

1. AttributeError: 'AddController' object has no attribute 'snackbar_timeout_ms'
   → main._show_snack musi działać z OBYDWOMA kontrolerami.
2. „Zero reakcji” na Quick Add: snack crashował, a pozycja (Planowane) była
   niewidoczna na domyślnym filtrze „W trakcie” — feedback musi dotrzeć.
3. Advanced Add: zapis z statusem „W trakcie” musi być widoczny od razu.
4. Brak okładek w wynikach wyszukiwania → SearchPage zamawia i podstawia pixmaps.
"""

from __future__ import annotations

from PyQt5.QtGui import QColor, QPixmap

from app.controllers.add_controller import AddController
from app.controllers.dashboard_controller import DashboardController
from app.domain.models import Donghua, SearchItem, Status
from app.gui.add.search_page import SearchPage
from app.gui.cover_coordinator import shared_pixmaps
from app.main import _show_snack
from tests.gui.test_add_controller_m4 import FakeNet
from tests.unit.test_dashboard_controller import StubWorker


def _item(mal_id=777, title="Xian Ni", cover="https://cdn.example/x.jpg"):
    return SearchItem(
        provider="mal",
        ext_id=mal_id,
        mal_id=mal_id,
        title=title,
        total_episodes=180,
        year=2023,
        cover_url=cover,
    )


def test_show_snack_works_with_add_controller(qapp):
    """Regresja #1: _show_snack(add_controller) nie rzuca AttributeError."""
    from app.gui.main_window import MainWindow

    window = MainWindow(animations_enabled=False)
    window.show()
    add = AddController(network_worker=FakeNet())
    _show_snack(window, add, "Dodano „Xian Ni” do Planowanych", "Cofnij", lambda: None)
    qapp.processEvents()
    assert window.snackbar.isVisible()
    assert "Xian Ni" in window.snackbar._message.text()
    assert add.snackbar_timeout_ms() == 6000
    window.snackbar.hide_message()
    window.hide()


def test_quick_add_end_to_end_feedback(qapp):
    """Regresja #2: Quick Add → pozycja w bibliotece + snack z Undo (bez crasha)."""
    worker = StubWorker()
    dash = DashboardController(worker=worker)
    dash.on_library_loaded(
        [
            Donghua(id=1, mal_id=11, title="Inna", status=Status.WATCHING, total_episodes=12),
        ]
    )
    add = AddController(network_worker=FakeNet(), dashboard_controller=dash)
    snacks = []
    add.snackRequested.connect(lambda t, a, cb: snacks.append((t, a, cb)))
    add.dbAddRequested.connect(
        lambda d, rid: (dash.on_add_completed(d), add.on_add_succeeded(d, rid))
    )

    add.quick_add(_item())
    qapp.processEvents()

    assert snacks and "Dodano" in snacks[0][0] and snacks[0][1] == "Cofnij"
    # domyślny filtr "w trakcie" NIE pokazuje Planowanych — ale badge i stan tak:
    assert dash.counts()["planned"] == 1
    dash.set_status_filter("planned")
    assert any(d.mal_id == 777 for d in dash.visible_items())
    # snack z Undo działa end-to-end przez main._show_snack (regresja #1 w flow)
    from app.gui.main_window import MainWindow

    window = MainWindow(animations_enabled=False)
    window.show()
    _show_snack(window, add, *snacks[0])
    qapp.processEvents()
    assert window.snackbar.isVisible()
    window.snackbar._action.click()  # Undo dodania
    qapp.processEvents()
    assert dash.counts()["planned"] == 0
    window.hide()


def test_advanced_add_watching_visible_immediately(qapp):
    """Regresja #3: Advanced Add ze statusem watching widoczny na ekranie startowym."""
    worker = StubWorker()
    dash = DashboardController(worker=worker)
    dash.on_library_loaded([])
    add = AddController(network_worker=FakeNet(), dashboard_controller=dash)
    add.dbAddRequested.connect(
        lambda d, rid: (dash.on_add_completed(d), add.on_add_succeeded(d, rid))
    )

    form = {"status": Status.WATCHING, "episode": 100, "links": [], "universe": None}
    add.advanced_add(_item(mal_id=888, title="Xian Ni"), form)
    qapp.processEvents()

    assert dash.status_filter == "watching"  # ekran startowy
    visible = dash.visible_items()
    assert len(visible) == 1 and visible[0].current_episode == 100


def test_search_page_requests_and_applies_covers(qapp):
    """Regresja #4: wyniki wyszukiwania zamawiają i podstawiają okładki."""
    requested = []
    page = SearchPage()
    page.set_cover_requester(lambda pairs: requested.extend(pairs))
    url = "https://cdn.example/xian-ni.jpg"
    page.show_results([_item(cover=url)], "mal", set())
    qapp.processEvents()
    assert requested == [(url, 777)]  # para (url, mal_id) dla fallbacku AniList

    pm = QPixmap(48, 60)
    pm.fill(QColor(0xB3, 0x9D, 0xDB))
    page.apply_cover(url, pm)  # symuluje pixmapReady z koordynatora
    row = page._list.itemWidget(page._list.item(0))
    assert not row._cover.pixmap().isNull()

    # druga sesja wyników: wspólny LRU serwuje bez sieci
    shared_pixmaps().put(url, pm)
    requested.clear()
    page.show_results([_item(cover=url)], "mal", set())
    qapp.processEvents()
    assert requested == []  # zero duplikatów dekodowania
    row2 = page._list.itemWidget(page._list.item(0))
    assert not row2._cover.pixmap().isNull()


def test_mark_in_library_after_add(qapp):
    page = SearchPage()
    page.show_results([_item(mal_id=999)], "mal", set())
    qapp.processEvents()
    row = page._list.itemWidget(page._list.item(0))
    assert row._badge.isHidden() is True
    page.mark_in_library(999)
    assert row._badge.isHidden() is False
