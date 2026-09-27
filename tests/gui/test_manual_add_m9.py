"""Testy M9: ręczne dodawanie donghua (PPM na FABie) — dialog, kontroler, repo."""

from __future__ import annotations

import sqlite3

from app.controllers.add_controller import AddController
from app.data.migrations import ensure_schema
from app.data.repository import DonghuaRepository
from app.domain.models import Donghua, MediaType, Status, Universe
from app.gui.add.add_dialog import AddDialog


def _conn():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    ensure_schema(conn)
    return conn


def test_manual_dialog_form_and_validation(qapp):
    dlg = AddDialog()
    dlg.set_universes({1: Universe(id=1, name="Douluo Dalu")})
    dlg.open_manual()
    qapp.processEvents()
    page = dlg.advanced_page
    assert dlg.stack.currentIndex() == 1
    assert page.manual_mode() is True
    assert page._back.isHidden() and page._delete.isHidden()
    assert page._manual_box.isVisible()

    # pusty tytuł = zapis wstrzymany
    fired = []
    page.saveRequested.connect(lambda: fired.append(1))
    page._on_save()
    assert fired == []

    # wypełnienie formularza
    page._m_title.setText("Xiuluo Wushen 3")
    page._m_year.setValue(2027)
    page._m_cover.setText("https://cdn.example/sw3.jpg")
    page._total.setValue(0)
    page._status_buttons[Status.PLANNED].click()
    form = page.form()
    assert form["manual"] is True
    assert form["title"] == "Xiuluo Wushen 3"
    assert form["start_year"] == 2027
    assert form["cover_url"] == "https://cdn.example/sw3.jpg"
    assert form["media_type"] == MediaType.UNKNOWN
    assert form["editing"] is None
    page._on_save()
    assert fired == [1]
    dlg.close()


def test_manual_save_signal_closes_dialog(qapp):
    dlg = AddDialog()
    got = []
    dlg.manualSaveRequested.connect(got.append)
    dlg.open_manual()
    dlg.advanced_page._m_title.setText("Shen Mu 3")
    dlg._on_advanced_save()
    qapp.processEvents()
    assert len(got) == 1 and got[0]["title"] == "Shen Mu 3"
    assert not dlg.isVisible()


def test_manual_add_controller_builds_manual_donghua(qapp):
    got = []
    ac = AddController(network_worker=None, dashboard_controller=None)
    ac.dbAddRequested.connect(lambda d, rid: got.append((d, rid)))
    ac.manual_add(
        {
            "manual": True,
            "title": "Xiuluo Wushen 3",
            "title_alt": "修罗武神3",
            "start_year": 2027,
            "media_type": MediaType.ONA,
            "cover_url": "https://cdn.example/sw3.jpg",
            "status": Status.PLANNED,
            "total": 0,
            "episode": 0,
            "links": [],
            "universe": None,
        }
    )
    assert len(got) == 1
    d, _rid = got[0]
    assert d.mal_id is None and d.provider == "manual"
    assert d.title == "Xiuluo Wushen 3" and d.title_alt == "修罗武神3"
    assert d.media_type == MediaType.ONA and d.start_year == 2027
    assert d.cover_key == "https://cdn.example/sw3.jpg"  # cover_key = URL (§4.8)
    assert d.status == Status.PLANNED and d.current_episode == 0
    # pusty tytuł = brak emisji
    before = len(got)
    ac.manual_add({"manual": True, "title": "   "})
    assert len(got) == before


def test_edit_save_manual_updates_title_and_cover(qapp):
    ac = AddController(network_worker=None, dashboard_controller=None)
    got = []
    ac.editSaveRequested.connect(lambda d, links: got.append((d, links)))
    d = Donghua(
        id=5,
        mal_id=None,
        provider="manual",
        title="Stary tytuł",
        cover_key="https://old.example/a.jpg",
        status=Status.PLANNED,
    )
    ac.edit_save(
        d,
        {
            "manual": True,
            "title": "Nowy tytuł",
            "title_alt": None,
            "start_year": 2028,
            "media_type": MediaType.MOVIE,
            "cover_url": "https://new.example/b.jpg",
            "status": Status.WATCHING,
            "total": 12,
            "episode": 3,
            "links": [],
            "universe": None,
        },
    )
    assert len(got) == 1
    updated, _links = got[0]
    assert updated.title == "Nowy tytuł"
    assert updated.cover_key == "https://new.example/b.jpg"
    assert updated.start_year == 2028 and updated.media_type == MediaType.MOVIE
    assert updated.current_episode == 3 and updated.status == Status.WATCHING


def test_repository_manual_roundtrip():
    conn = _conn()
    repo = DonghuaRepository(conn)
    from app.core.timeutil import utc_now_iso

    now = utc_now_iso()
    d1 = Donghua(
        mal_id=None,
        provider="manual",
        title="Xiuluo Wushen 3",
        status=Status.PLANNED,
        cover_key="https://cdn.example/sw3.jpg",
        added_at=now,
        updated_at=now,
    )
    d2 = Donghua(
        mal_id=None, provider="manual", title="Xiuluo Wushen 3", added_at=now, updated_at=now
    )
    id1 = repo.insert(d1)
    id2 = repo.insert(d2)  # ten sam tytuł ręczny ×2 = OK (brak UNIQUE na title)
    assert id1 != id2
    alive = repo.load_alive()
    assert len(alive) == 2
    stored = repo.get(id1)
    assert stored.provider == "manual" and stored.mal_id is None
    assert stored.cover_key == "https://cdn.example/sw3.jpg"
    conn.close()


def test_dialog_edit_manual_shows_cover_field(qapp):
    dlg = AddDialog()
    d = Donghua(
        id=9,
        mal_id=None,
        provider="manual",
        title="Ręczna",
        cover_key="https://cdn.example/m.jpg",
        status=Status.PLANNED,
    )
    dlg.open_advanced_edit(d, [])
    qapp.processEvents()
    page = dlg.advanced_page
    assert page.manual_mode() is True
    assert page._m_title.text() == "Ręczna"
    assert page._m_cover.text() == "https://cdn.example/m.jpg"
    assert page._back.isHidden()
    # edycja pozycji z MAL: bez pola ręcznego
    d_mal = Donghua(id=10, mal_id=77, provider="mal", title="MAL-owa", status=Status.WATCHING)
    dlg.open_advanced_edit(d_mal, [])
    qapp.processEvents()
    assert page.manual_mode() is False
    assert page._title.isVisible()
    dlg.close()
