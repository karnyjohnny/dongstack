"""Testy M5: grupowanie uniwersów (§6.7), override'y, edycja z rollbackiem."""

from __future__ import annotations

import dataclasses

from app.controllers.dashboard_controller import DashboardController
from app.domain.models import (
    DisplayHeader,
    Donghua,
    RelationType,
    SortMode,
    Status,
    Universe,
)
from tests.unit.test_dashboard_controller import StubWorker


def _ctrl(rows, universes=None):
    w = StubWorker()
    c = DashboardController(worker=w)
    c.on_library_loaded(rows)
    c.on_universes_loaded(universes or [])
    return c, w


def _d(did, mal, title, uni=None, order=None, year=2020, media=None, updated=None):
    from app.domain.models import MediaType

    stamp = updated if updated is not None else ("2026-01-0%dT00:00:00.000Z" % did)
    return Donghua(
        id=did,
        mal_id=mal,
        title=title,
        universe_id=uni,
        universe_order=order,
        start_year=year,
        media_type=media or MediaType.TV,
        status=Status.WATCHING,
        total_episodes=12,
        current_episode=1,
        updated_at=stamp,
    )


def test_flat_mode_has_no_headers():
    c, _ = _ctrl([_d(1, 10, "A"), _d(2, 20, "B", uni=5)], [Universe(id=5, name="U")])
    entries = c.visible_entries()
    assert all(isinstance(e, Donghua) for e in entries)


def test_grouping_puts_header_and_watch_order():
    s1 = _d(1, 100, "Uni", year=2018, updated="2026-01-01T00:00:00.000Z")
    s2 = _d(2, 200, "Uni 2nd Season", year=2019, uni=5, updated="2026-01-02T00:00:00.000Z")
    s1 = dataclasses.replace(s1, universe_id=5)
    free = _d(3, 300, "Solo", updated="2026-01-09T00:00:00.000Z")
    c, _ = _ctrl([s2, s1, free], [Universe(id=5, name="Uniwersum X")])
    c.register_relations(200, [(100, RelationType.PREQUEL)])  # S1 przed S2
    c.set_sort(SortMode.WATCH_ORDER.value)
    entries = c.visible_entries()
    assert isinstance(entries[0], DisplayHeader)
    assert entries[0].name == "Uniwersum X"
    assert entries[0].collapsed is False
    body = [e for e in entries[1:3]]
    assert [e.mal_id for e in body] == [100, 200]  # watch_order z relacji
    assert entries[3].id == free.id  # poza uniwersum na końcu


def test_collapse_hides_members():
    a = _d(1, 100, "A", uni=5)
    b = _d(2, 200, "B", uni=5)
    c, _ = _ctrl([a, b], [Universe(id=5, name="U")])
    c.set_sort(SortMode.WATCH_ORDER.value)
    assert len(c.visible_entries()) == 3  # header + 2
    c.toggle_universe(5)
    entries = c.visible_entries()
    assert len(entries) == 1 and entries[0].collapsed is True
    c.toggle_universe(5)
    assert len(c.visible_entries()) == 3


def test_universe_badge_counts():
    a = dataclasses.replace(_d(1, 100, "A", uni=5), current_episode=3)
    b = dataclasses.replace(_d(2, 200, "B", uni=5), current_episode=7)
    c, _ = _ctrl([a, b], [Universe(id=5, name="U")])
    c.set_sort(SortMode.WATCH_ORDER.value)
    header = c.visible_entries()[0]
    assert "2 tytułów" in header.badge and "10/24 ep." in header.badge


def test_move_in_universe_sets_orders_and_saves():
    a = _d(1, 100, "A", uni=5, year=2018)
    b = _d(2, 200, "B", uni=5, year=2019)
    c, w = _ctrl([a, b], [Universe(id=5, name="U")])
    c.set_sort(SortMode.WATCH_ORDER.value)
    c.move_in_universe(2, -1)  # B przed A
    entries = [e for e in c.visible_entries() if isinstance(e, Donghua)]
    assert [e.id for e in entries] == [2, 1]
    assert w.orders, "override zapisany przez workera"
    assert c.item(2).universe_order < c.item(1).universe_order


def test_edit_save_optimistic_and_rollback():
    d = _d(1, 100, "A")
    c, w = _ctrl([d])
    edited = dataclasses.replace(d, current_episode=9, status=Status.COMPLETED)
    c.on_advanced_save(edited, [])
    assert c.item(1).current_episode == 9  # optymistycznie
    rid = w.fulls[0][2]
    snacks = []
    c.snackRequested.connect(lambda t, a, cb: snacks.append(t))
    c._on_full_fail(1, rid, "boom")
    assert c.item(1).current_episode == 1  # rollback do confirmed
    assert snacks and "Nie udało się zapisać" in snacks[0]


def test_edit_save_ok_confirms():
    d = _d(1, 100, "A")
    c, w = _ctrl([d])
    edited = dataclasses.replace(d, current_episode=4)
    c.on_advanced_save(edited, [])
    rid = w.fulls[0][2]
    c._on_full_ok(edited, rid)
    c._on_full_fail(1, rid, "stale")  # po ack brak rollbacku
    assert c.item(1).current_episode == 4
