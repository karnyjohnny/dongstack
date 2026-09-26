"""Testy AddDialog/SearchPage (M4): stany, skeleton, wiersze wyników, duplikaty."""

from __future__ import annotations

from PyQt5.QtTest import QTest

from app.controllers.add_controller import AddController
from app.domain.models import SearchItem
from app.gui.add.add_dialog import AddDialog
from tests.gui.test_add_controller_m4 import FakeNet


def _items():
    return [
        SearchItem(
            provider="mal",
            ext_id=1,
            mal_id=1,
            title="Doupo Cangqiong",
            total_episodes=12,
            year=2017,
        ),
        SearchItem(
            provider="mal",
            ext_id=2,
            mal_id=2,
            title="Doupo 2nd Season",
            total_episodes=12,
            year=2018,
        ),
    ]


def _dialog_with_controller(qapp, library_mal_ids=()):
    net = FakeNet()
    c = AddController(network_worker=net)
    dialog = AddDialog()
    page = dialog.search_page
    page.textChanged.connect(c.on_text_changed)
    page.retryRequested.connect(c.retry_last)
    page.quickAddRequested.connect(c.quick_add)
    page.advancedRequested.connect(dialog.open_advanced)

    def _state(st):
        if st == "searching":
            page.show_searching()
        elif st == "idle":
            page.show_idle()

    c.stateChanged.connect(_state)
    c.resultsReady.connect(lambda items, prov: page.show_results(items, prov, set(library_mal_ids)))
    c.searchError.connect(lambda e: page.show_error(e.user_message()))
    return dialog, page, c, net


def test_dialog_opens_on_search_page(qapp):
    dialog, page, c, net = _dialog_with_controller(qapp)
    dialog.open()
    qapp.processEvents()
    assert dialog.stack.currentIndex() == 0
    assert dialog.isVisible()
    dialog.close()


def test_searching_shows_static_skeleton(qapp):
    dialog, page, c, net = _dialog_with_controller(qapp)
    dialog.open()
    page.show_searching()
    qapp.processEvents()
    assert page._list.count() == 4
    dialog.close()


def test_results_rows_and_duplicate_badge(qapp):
    dialog, page, c, net = _dialog_with_controller(qapp, library_mal_ids=(1,))
    dialog.open()
    page.show_results(_items(), "mal", {1})
    qapp.processEvents()
    assert page._list.count() == 2
    row0 = page._list.itemWidget(page._list.item(0))
    row1 = page._list.itemWidget(page._list.item(1))
    assert row0._badge.isVisible() is True  # mal_id=1 już w bibliotece
    assert row1._badge.isVisible() is False
    assert "2017" in row0._meta.text()
    dialog.close()


def test_quick_add_click_emits(qapp):
    dialog, page, c, net = _dialog_with_controller(qapp)
    adds = []
    c.dbAddRequested.connect(lambda d, rid: adds.append(d))
    dialog.open()
    page.show_results(_items(), "mal", set())
    qapp.processEvents()
    row = page._list.itemWidget(page._list.item(1))
    row._add.click()
    qapp.processEvents()
    assert adds and adds[0].mal_id == 2
    dialog.close()


def test_error_state_keeps_query_and_retry(qapp):
    dialog, page, c, net = _dialog_with_controller(qapp)
    dialog.open()
    page.line_edit.setText("doupo")
    page.show_error("Brak połączenia z internetem.")
    qapp.processEvents()
    assert page.line_edit.text() == "doupo"  # błąd nie niszczy zapytania (Biblia §20)
    assert page._retry.isVisible()
    page._retry.click()
    qapp.processEvents()
    QTest.qWait(600)  # debounce retry_last
    assert len(net.searches) >= 1
    dialog.close()


def test_no_results_state(qapp):
    dialog, page, c, net = _dialog_with_controller(qapp)
    dialog.open()
    page.line_edit.setText("zzzz")
    page.show_no_results("zzzz")
    qapp.processEvents()
    assert "Nie znaleziono" in page._hint.text()
    dialog.close()


def test_skeleton_to_each_state_no_crash(qapp):
    """Regresja buga produkcyjnego M6: removeItemWidget(item), nie widget.

    Kazdy przejazd skeleton -> inny stan czysci liste ze skeletonami —
    poprzednio TypeError na pierwszym przejsciu skeleton -> wyniki.
    """
    dialog, page, c, net = _dialog_with_controller(qapp)
    dialog.open()
    transitions = (
        page.show_idle,
        lambda: page.show_results(_items(), "mal", set()),
        lambda: page.show_no_results("zzz"),
        lambda: page.show_error("Brak polaczenia z internetem."),
    )
    for go in transitions:
        page.show_searching()
        qapp.processEvents()
        assert page._list.count() == 4  # 4 statyczne skeletony
        go()
        qapp.processEvents()  # deleteLater skeletonow
    assert page._list.count() == 0
    dialog.close()


def test_user_flow_typing_skeleton_then_results(qapp):
    """Flow uzytkownika 1:1: klik + -> wpisz tekst -> skeleton -> wyniki (bez crasha)."""
    dialog, page, c, net = _dialog_with_controller(qapp)
    dialog.open()
    c.on_text_changed("doupo")
    QTest.qWait(600)  # debounce 450 ms -> SEARCHING -> skeleton
    qapp.processEvents()
    assert c.state == "searching"
    assert page._list.count() == 4
    rid = net.searches[-1][1]
    net.searchFinished.emit(rid, _items(), "mal")  # siec wraca -> RESULTS
    qapp.processEvents()
    assert page._list.count() == 2  # skeletony zwolnione, wyniki w liscie
    row = page._list.itemWidget(page._list.item(0))
    assert "Doupo" in row._title.text()
    dialog.close()
