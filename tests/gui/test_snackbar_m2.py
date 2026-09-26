"""Testy SnackBar: komunikat, akcja Undo, auto-hide (Biblia §9–§10)."""

from __future__ import annotations

from PyQt5.QtTest import QTest

from app.gui.snackbar import SnackBar


def test_show_message_and_autoshide(qapp):
    sb = SnackBar(None)
    sb.show_message("Dodano „X” do Planowanych", timeout_ms=300)
    qapp.processEvents()
    assert sb.isVisible()
    assert "Dodano" in sb._message.text()
    QTest.qWait(750)  # timeout 300 ms jest clampowany do min. 500 ms (UX)
    qapp.processEvents()
    assert sb.isVisible() is False


def test_action_callback_and_hide(qapp):
    sb = SnackBar(None)
    calls = []
    sb.show_message(
        "Oznaczono jako ukończone",
        action_label="Cofnij",
        on_action=lambda: calls.append(1),
        timeout_ms=5000,
    )
    qapp.processEvents()
    assert sb._action.isVisible()
    assert sb._action.text() == "Cofnij"
    sb._action.click()
    qapp.processEvents()
    assert calls == [1]
    assert sb.isVisible() is False


def test_no_action_button_without_callback(qapp):
    sb = SnackBar(None)
    sb.show_message("Nie udało się zapisać zmiany.")
    qapp.processEvents()
    assert sb._action.isVisible() is False


def test_reposition_within_parent(qapp):
    from PyQt5.QtWidgets import QWidget

    parent = QWidget()
    parent.resize(800, 600)
    sb = SnackBar(parent)
    sb.show_message("test")
    parent.show()
    qapp.processEvents()
    assert sb.x() >= 0 and sb.y() + sb.height() <= parent.height()
