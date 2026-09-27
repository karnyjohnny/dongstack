"""Testy M9: płaska lista uniwersów (§6.7 po redesignie) — bez zwijanych nagłówków.

Regresja buga produkcyjnego r7: nagłówki grup (34 px) wymieszane z kartami
(96 px) w QListWidget.uniformItemSizes → rozjazd layoutu (luki/nakładanie).
M9: ZAWSZE płaska lista kart; bloki uniwersów obok siebie + hover-highlight.
"""

from __future__ import annotations

from app.controllers.dashboard_controller import DashboardController
from app.domain.models import Donghua, MediaType, SortMode, Status
from tests.unit.test_dashboard_controller import StubWorker


def _ctrl(rows, universes=None):
    w = StubWorker()
    c = DashboardController(worker=w)
    c.on_library_loaded(rows)
    c.on_universes_loaded(universes or [])
    return c, w


def _d(did, mal, title, uni=None, order=None, updated=None):
    stamp = updated if updated is not None else ("2026-01-0%dT00:00:00.000Z" % did)
    return Donghua(
        id=did,
        mal_id=mal,
        title=title,
        universe_id=uni,
        universe_order=order,
        start_year=2020,
        media_type=MediaType.TV,
        status=Status.WATCHING,
        total_episodes=12,
        current_episode=1,
        updated_at=stamp,
    )


def _rows():
    return [
        _d(1, 101, "A S1", uni=1, order=10, updated="2026-01-01T00:00:00.000Z"),
        _d(2, 102, "A S2", uni=1, order=20, updated="2026-01-02T00:00:00.000Z"),
        _d(3, 201, "B S1", uni=2, order=10, updated="2026-02-05T00:00:00.000Z"),
        _d(4, None, "Zhe Tian", uni=None, updated="2026-03-01T00:00:00.000Z"),
    ]


def test_watch_order_is_flat_and_contiguous():
    c, _w = _ctrl(_rows())
    c.set_sort(SortMode.WATCH_ORDER.value)
    entries = c.visible_entries()
    assert all(isinstance(e, Donghua) for e in entries), "M9: zero nagłówków grup"
    ids = [e.id for e in entries]
    assert ids == [3, 1, 2, 4]  # blok B (świeższy), blok A (watch order), free na końcu


def test_other_sorts_stay_flat():
    c, _w = _ctrl(_rows())
    for mode in (SortMode.UPDATED, SortMode.ALPHA, SortMode.ADDED, SortMode.PROGRESS):
        c.set_sort(mode.value)
        assert all(isinstance(e, Donghua) for e in c.visible_entries())


def test_collapse_api_usuniete():
    c, _w = _ctrl(_rows())
    assert not hasattr(c, "toggle_universe"), "M9: collapse zlikwidowany (bug r7)"
    assert not hasattr(c, "_collapsed")


def test_move_in_universe_still_reorders():
    c, _w = _ctrl(_rows())
    c.set_sort(SortMode.WATCH_ORDER.value)
    c.move_in_universe(1, +1)  # A S1 w dół → A S2, A S1
    ids = [e.id for e in c.visible_entries()]
    assert ids == [3, 2, 1, 4]


def test_universe_blocks_survive_status_filter():
    rows = _rows() + [_d(5, 103, "A S3", uni=1, order=30, updated="2026-01-03T00:00:00.000Z")]
    rows[4] = rows[4].with_episode(12, "2026-01-03T00:00:00.000Z")  # A S3 = completed
    c, _w = _ctrl(rows)
    c.set_status_filter("watching")
    c.set_sort(SortMode.WATCH_ORDER.value)
    ids = [e.id for e in c.visible_entries()]
    assert 5 not in ids and ids.index(1) < ids.index(2)
