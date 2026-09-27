"""Testy r11: notatka własna (donghua.note) + „bezpieczne” usuwanie uniwersów.

QoL z feedbacku produkcyjnego (E5500, v1.2.1):
- notatka nad linkami streamingowymi (kolumna `note` ISTNIEJE od migracji v1,
  więc żadna nowa migracja nie była potrzebna — zero ryzyka dla danych),
- Ustawienia → Uniwersa: usunięcie uniwersum NIE kasuje sezonów, tylko czyści
  przynależność (FK ON DELETE SET NULL) + Undo przez odtworzenie i ponowne
  przypięcie tych samych id (Biblia §9).
"""

from __future__ import annotations

import dataclasses

from app.controllers.dashboard_controller import DashboardController
from app.data.repository import DonghuaRepository, UniverseRepository
from app.domain.models import Donghua, Status, Universe
from tests.unit.test_dashboard_controller import StubWorker


def _row(did: int, title: str, universe_id=None, order: int = 0, **kw) -> Donghua:
    return Donghua(
        id=did,
        mal_id=did,
        provider="mal",
        title=title,
        total_episodes=12,
        current_episode=0,
        status=Status.WATCHING,
        universe_id=universe_id,
        universe_order=order,
        **kw,
    )


# --------------------------------------------------------------------------- DANE
def test_note_roundtrip_in_repository(db_conn):
    repo = DonghuaRepository(db_conn)
    did = repo.insert(_row(0, "Douluo Dalu", note="na CDA numeracja = 52 + odc. sezonu"))
    assert repo.get(did).note == "na CDA numeracja = 52 + odc. sezonu"

    changed = dataclasses.replace(repo.get(did), note="S2 = odc. 28+")
    assert repo.update_full(changed) is True
    assert repo.get(did).note == "S2 = odc. 28+"


def test_note_is_optional_and_survives_progress_update(db_conn):
    repo = DonghuaRepository(db_conn)
    did = repo.insert(_row(0, "Bez notatki"))
    assert repo.get(did).note is None
    assert repo.update_progress(did, 4, Status.WATCHING) is True
    assert repo.get(did).current_episode == 4
    assert repo.get(did).note is None


def test_universe_delete_detaches_members_in_sql(db_conn):
    repo = DonghuaRepository(db_conn)
    universes = UniverseRepository(db_conn)
    uid = universes.create("Douluo Dalu", 123)
    # mal_id musi być różny per seria (insert() deduplikuje po mal_id — §4.6)
    ids = [
        repo.insert(_row(i + 1, "S%d" % i, universe_id=uid, order=(i + 1) * 10)) for i in range(3)
    ]

    assert universes.delete(uid) is True
    assert universes.list_all() == []
    for did in ids:  # sezony ŻYJĄ, tracą tylko przynależność
        stored = repo.get(did)
        assert stored is not None
        assert stored.universe_id is None
    assert len(repo.load_alive()) == 3


def test_universe_delete_of_missing_row_is_false(db_conn):
    assert UniverseRepository(db_conn).delete(9999) is False


# ------------------------------------------------------------------- KONTROLER
def _ctrl(rows, universes):
    w = StubWorker()
    c = DashboardController(worker=w)
    snacks = []
    c.snackRequested.connect(lambda t, a, cb: snacks.append((t, a)))
    c.on_universes_loaded(universes)
    c.on_library_loaded(rows)
    return c, w, snacks


def test_universe_counts_for_settings():
    uni = Universe(id=7, name="Douluo Dalu")
    rows = [
        _row(1, "S1", universe_id=7, order=10),
        _row(2, "S2", universe_id=7, order=20),
        _row(3, "Solo"),
    ]
    c, _w, _s = _ctrl(rows, [uni])
    assert c.universe_counts() == {7: 2}
    listed = c.universes_with_counts()
    assert [(u.id, n) for u, n in listed] == [(7, 2)]
    assert c.members_of(7) == [(1, 10), (2, 20)]


def test_delete_universe_detaches_and_reports():
    uni = Universe(id=7, name="Douluo Dalu", mal_anchor_id=123)
    rows = [_row(1, "S1", universe_id=7, order=10), _row(2, "S2", universe_id=7, order=20)]
    c, w, snacks = _ctrl(rows, [uni])

    c.request_delete_universe(7)

    assert c.universes() == {}  # rejestr wyczyszczony
    assert [d.universe_id for d in c.visible_items()] == [None, None]  # sezony zostały
    assert len(w.universe_deletes) == 1 and w.universe_deletes[0][0] == 7
    assert snacks and snacks[-1][0].startswith("Usunięto uniwersum „Douluo Dalu”")
    assert "2" in snacks[-1][0]


def test_delete_universe_undo_recreates_and_reattaches():
    uni = Universe(id=7, name="Douluo Dalu", mal_anchor_id=123)
    rows = [_row(1, "S1", universe_id=7, order=10), _row(2, "S2", universe_id=7, order=20)]
    c, w, _snacks = _ctrl(rows, [uni])
    c.set_status_filter("all")

    c.request_delete_universe(7)
    c.undo_last()

    assert len(w.universe_creates) == 1
    name, anchor, rid = w.universe_creates[0]
    assert name == "Douluo Dalu" and anchor == 123
    # ack z DbWorker: nowe id uniwersum + ponowne przypięcie tych samych sezonów
    c.on_universe_created(42, name, rid)
    assert sorted(mid for mid, _uid, _r in w.universe_attaches) == [1, 2]
    assert {d.id: d.universe_id for d in c.visible_items()} == {1: 42, 2: 42}
    assert c.universe_name(42) == "Douluo Dalu"


def test_delete_universe_nack_restores_previous_state():
    uni = Universe(id=7, name="Douluo Dalu")
    rows = [_row(1, "S1", universe_id=7, order=10)]
    c, w, snacks = _ctrl(rows, [uni])

    c.request_delete_universe(7)
    rid = w.universe_deletes[0][1]
    c._on_universe_delete_failed(7, rid, "disk I/O error")

    assert c.universe_name(7) == "Douluo Dalu"
    assert [d.universe_id for d in c.visible_items()] == [7]
    assert snacks[-1][0] == "Nie udało się usunąć uniwersum."


def test_universe_delete_ack_is_idempotent():
    """R5: ack bez żądania / powtórzony ack nie może wywrócić stanu ani rzucić."""
    uni = Universe(id=7, name="Douluo Dalu")
    c, _w, _snacks = _ctrl([_row(1, "S1", universe_id=7)], [uni])
    c.on_universe_deleted(7, 999999)  # bez wcześniejszego żądania
    assert c.universes() == {}  # rejestr i tak pusty (ack potwierdza fakt z bazy)
    c.on_universe_deleted(7, 999999)  # drugi raz = no-op, bez wyjątku


def test_delete_universe_without_worker_still_detaches():
    """Tryb --demo/testy bez workera: stan w pamięci spójny, Undo lokalne."""
    uni = Universe(id=7, name="Douluo Dalu")
    c = DashboardController(worker=None)
    c.on_universes_loaded([uni])
    c.on_library_loaded([_row(1, "S1", universe_id=7, order=10)])

    c.request_delete_universe(7)
    assert c.universes() == {}
    c.undo_last()
    assert c.universe_name(1) == "Douluo Dalu"
    assert [d.universe_id for d in c.visible_items()] == [1]
