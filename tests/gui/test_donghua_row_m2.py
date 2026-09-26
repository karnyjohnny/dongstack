"""Testy DonghuaRow: wartości, sygnały +/-, stany disabled, elide tytułu."""

from __future__ import annotations

from PyQt5.QtCore import QSize, Qt
from PyQt5.QtTest import QTest

from app.domain.models import Donghua, MediaType, Status
from app.gui.dashboard.donghua_row import DonghuaRow


def _row_with(d):
    row = DonghuaRow()
    row.set_donghua(d)
    return row


def test_row_renders_values(qapp):
    d = Donghua(
        id=7,
        title="Doupo Cangqiong 3rd Season",
        total_episodes=12,
        current_episode=3,
        status=Status.WATCHING,
        media_type=MediaType.ONA,
        start_year=2019,
    )
    row = _row_with(d)
    assert row.donghua_id == 7
    assert "3/12" in row._episode.text()
    assert "ONA" in row._meta.text() and "2019" in row._meta.text()
    assert "w trakcie" in row._meta.text()
    assert row._progress.maximum() == 12 and row._progress.value() == 3
    assert row._minus.isEnabled() is True
    assert row._plus.isEnabled() is True


def test_plus_minus_signals(qapp, qtbot=None):
    d = Donghua(id=11, title="X", total_episodes=10, current_episode=4)
    row = _row_with(d)
    got = []
    row.episodeIncrementRequested.connect(lambda i: got.append(("+", i)))
    row.episodeDecrementRequested.connect(lambda i: got.append(("-", i)))
    row._plus.click()
    row._minus.click()
    qapp.processEvents()
    assert got == [("+", 11), ("-", 11)]


def test_minus_disabled_at_zero_and_plus_at_cap(qapp):
    zero = _row_with(Donghua(id=1, title="A", total_episodes=12, current_episode=0))
    assert zero._minus.isEnabled() is False
    cap = _row_with(Donghua(id=2, title="B", total_episodes=12, current_episode=12))
    assert cap._plus.isEnabled() is False
    assert cap._minus.isEnabled() is True


def test_unknown_total_shows_dash_and_empty_bar(qapp):
    row = _row_with(Donghua(id=3, title="C", total_episodes=0, current_episode=5))
    assert "5/—" in row._episode.text()
    assert row._progress.maximum() == 1


def test_update_values_is_cheap_path(qapp):
    d = Donghua(id=4, title="D", total_episodes=24, current_episode=1, status=Status.WATCHING)
    row = _row_with(d)
    d2 = d.with_episode(2, updated_at="t")
    row.update_values(d2)
    assert "2/24" in row._episode.text()
    assert row._progress.value() == 2


def test_title_elided_single_line(qapp):
    long_title = "Bardzo długi tytuł donghua " * 6
    row = _row_with(Donghua(id=5, title=long_title, total_episodes=1))
    row.resize(QSize(600, 96))
    qapp.processEvents()
    shown = row._title.text()
    assert shown.endswith("…") or len(shown) < len(long_title)
    assert "\n" not in shown


def test_details_signal_on_click(qapp):
    row = _row_with(Donghua(id=9, title="E", total_episodes=1))
    got = []
    row.detailsRequested.connect(got.append)
    QTest.mouseClick(row, Qt.LeftButton)
    qapp.processEvents()
    assert got == [9]
