"""r11: notatka własna + progres przy nieznanym totalu — plumbing formularz → model → SQL.

Uwaga: kolumna `donghua.note` istnieje OD migracji v1 (model i repository ją
obsługują od początku), więc QoL „notatnik” nie wymagał nowej migracji — zero
ryzyka dla istniejących baz użytkownika. Brakowało wyłącznie pola w UI.
"""

from __future__ import annotations

import dataclasses

from app.controllers.add_controller import AddController
from app.data.repository import DonghuaRepository
from app.domain.models import Donghua, MediaType, SearchItem, Status


def _item(total=0) -> SearchItem:
    return SearchItem(
        provider="mal",
        ext_id=11,
        mal_id=11,
        title="Douluo Dalu",
        title_alt="Soul Land",
        total_episodes=total,
        year=2018,
        media_type=MediaType.ONA,
    )


def _form(**kw) -> dict:
    base = dict(status=Status.WATCHING, episode=0, total=0, links=[], universe=None, note=None)
    base.update(kw)
    return base


def _donghua(**kw) -> Donghua:
    base = dict(
        id=5,
        mal_id=7,
        provider="mal",
        title="T",
        total_episodes=0,
        current_episode=0,
        status=Status.PLANNED,
        note="stara notatka",
    )
    base.update(kw)
    return Donghua(**base)


def test_advanced_add_carries_note_and_progress_without_total(qapp):
    ac = AddController()
    got = []
    ac.dbAddRequested.connect(lambda d, rid: got.append(d))
    ac.advanced_add(_item(total=0), _form(episode=3, note="na CDA numeracja = 52 + odc."))
    assert len(got) == 1
    assert got[0].note == "na CDA numeracja = 52 + odc."
    # BUG r11: total=0 nie może zerować postępu wpisanego w formularzu
    assert got[0].total_episodes == 0
    assert got[0].current_episode == 3
    assert got[0].title_alt == "Soul Land"  # alt z providera ląduje w bazie


def test_manual_add_carries_note(qapp):
    ac = AddController()
    got = []
    ac.dbAddRequested.connect(lambda d, rid: got.append(d))
    ac.manual_add(_form(title="Xiuluo Wushen 3", episode=40, note="S2 = 28+", manual=True))
    assert got[0].note == "S2 = 28+"
    assert got[0].current_episode == 40 and got[0].total_episodes == 0
    assert got[0].provider == "manual" and got[0].mal_id is None


def test_edit_save_updates_note_and_progress_without_total(qapp):
    ac = AddController()
    got = []
    ac.editSaveRequested.connect(lambda d, links: got.append(d))
    ac.edit_save(_donghua(), _form(episode=4, note="  S2 startuje od 28  "))
    assert got[0].current_episode == 4
    assert got[0].note == "S2 startuje od 28"  # formularz zwraca już przycięty tekst


def test_edit_save_clears_note_when_field_emptied(qapp):
    ac = AddController()
    got = []
    ac.editSaveRequested.connect(lambda d, links: got.append(d))
    ac.edit_save(_donghua(), _form(note=None))
    assert got[0].note is None


def test_edit_save_without_note_key_keeps_existing(qapp):
    """Starsze ścieżki (np. quick-add/shortcut) nie wysyłają klucza „note”."""
    ac = AddController()
    got = []
    ac.editSaveRequested.connect(lambda d, links: got.append(d))
    form = _form()
    form.pop("note")
    ac.edit_save(_donghua(), form)
    assert got[0].note == "stara notatka"


def test_episode_over_total_is_clamped_only_when_total_known(qapp):
    ac = AddController()
    got = []
    ac.dbAddRequested.connect(lambda d, rid: got.append(d))
    ac.advanced_add(_item(total=12), _form(episode=99, total=12))
    assert got[0].current_episode == 12  # znany total = twardy limit
    ac.advanced_add(_item(total=0), _form(episode=99, total=0))
    assert got[1].current_episode == 99  # nieznany total = brak limitu (r11)


def test_note_and_alt_persist_in_sqlite(db_conn):
    repo = DonghuaRepository(db_conn)
    did = repo.insert(_donghua(id=0, mal_id=77, note="CDA: 52 + odc.", title_alt="Soul Land II"))
    stored = repo.get(did)
    assert stored.note == "CDA: 52 + odc."
    assert stored.title_alt == "Soul Land II"

    assert repo.update_full(dataclasses.replace(stored, note=None)) is True
    assert repo.get(did).note is None
    assert repo.get(did).title_alt == "Soul Land II"  # czyszczenie noty nie rusza reszty
