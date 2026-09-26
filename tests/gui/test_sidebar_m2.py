"""Testy SidebarWidget: 5 wpisów, sygnał filtra, badge'e, ekran startowy 'W trakcie'."""

from __future__ import annotations

from app.gui.sidebar import NAV_ITEMS, SidebarWidget


def test_five_nav_items_and_start_status(qapp):
    sb = SidebarWidget()
    assert len(NAV_ITEMS) == 5
    assert sb.current_status == "watching"  # Biblia §68.2: start = "W trakcie"


def test_filter_signal_on_selection(qapp):
    sb = SidebarWidget()
    got = []
    sb.statusFilterChanged.connect(got.append)
    sb.set_current("completed")
    qapp.processEvents()
    assert got == ["completed"]
    assert sb.current_status == "completed"


def test_counts_badges(qapp):
    sb = SidebarWidget()
    sb.set_counts({"all": 42, "watching": 7, "completed": 20, "planned": 12, "dropped": 3})
    assert sb._items["all"]._badge.text() == "42"
    assert sb._items["watching"]._badge.text() == "7"
    sb.set_counts({"all": 0, "watching": 0, "completed": 0, "planned": 0, "dropped": 0})
    assert sb._items["all"]._badge.text() == ""  # zero = dyskretnie pusto


def test_active_flag_follows_selection(qapp):
    sb = SidebarWidget()
    sb.set_current("planned")
    qapp.processEvents()
    assert sb._items["planned"].is_active is True
    assert sb._items["watching"].is_active is False
    # inline stylesheet zamiast property+polish (regresja freeze na Win7)
    assert "#2A2A2A" in sb._items["planned"].styleSheet()
    assert "#2A2A2A" not in sb._items["watching"].styleSheet()


def test_sidebar_fixed_width(qapp):
    sb = SidebarWidget()
    assert sb.width() == 210 or sb.maximumWidth() == 210
