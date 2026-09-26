"""app/gui/snackbar.py — SnackBar: overlay z Undo zamiast modalnych potwierdzeń.

Biblia GUI §9–§10, §39: krótki komunikat + opcjonalna akcja („Cofnij”), auto-hide
QTimer.singleShot (domyślnie 6 s), BRAK QMessageBox dla operacji odwracalnych.
Animacja wejścia: wyłącznie gdy config.animations_enabled (R9) — w M2 statycznie.
"""

from __future__ import annotations

from typing import Callable, Optional

from PyQt5.QtCore import QObject, Qt, QTimer, pyqtSignal
from PyQt5.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QWidget


class SnackBar(QFrame):
    """Overlay przy dolnej krawędzi rodzica (centrowany poziomo)."""

    actionTriggered = pyqtSignal()
    dismissed = pyqtSignal()

    DEFAULT_TIMEOUT_MS = 6000

    def __init__(self, parent: Optional[QWidget] = None, animations_enabled: bool = False) -> None:
        super().__init__(parent)
        self.setObjectName("snackBar")
        self._animations_enabled = animations_enabled
        self._callback: Optional[Callable[[], None]] = None

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 8, 8, 8)
        layout.setSpacing(6)

        self._message = QLabel(self)
        self._message.setObjectName("snackMessage")
        self._message.setTextFormat(Qt.PlainText)
        layout.addWidget(self._message, 1)

        self._action = QPushButton(self)
        self._action.setObjectName("snackAction")
        self._action.setCursor(Qt.PointingHandCursor)
        self._action.clicked.connect(self._on_action)
        layout.addWidget(self._action, 0)

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.hide_message)
        self.hide()

        if parent is not None:
            parent.installEventFilter(self)

    # --- API -----------------------------------------------------------------
    def show_message(
        self,
        text: str,
        action_label: Optional[str] = None,
        on_action: Optional[Callable[[], None]] = None,
        timeout_ms: int = DEFAULT_TIMEOUT_MS,
    ) -> None:
        self._message.setText(text)
        self._callback = on_action
        if action_label and on_action is not None:
            self._action.setText(action_label)
            self._action.show()
        else:
            self._action.hide()
        self.adjustSize()
        self.reposition()
        self.show()
        self.raise_()
        self._timer.start(max(500, int(timeout_ms)))

    def hide_message(self) -> None:
        if self._timer.isActive():
            self._timer.stop()
        if self.isVisible():
            self.hide()
            self.dismissed.emit()

    def reposition(self) -> None:
        parent = self.parentWidget()
        if parent is None:
            return
        margin = 16
        self.adjustSize()
        x = max(margin, (parent.width() - self.width()) // 2)
        y = parent.height() - self.height() - margin
        self.move(x, y)

    # --- wewnętrzne -----------------------------------------------------------
    def _on_action(self) -> None:
        cb = self._callback
        self._callback = None
        self.hide_message()
        if cb is not None:
            cb()
        self.actionTriggered.emit()

    def eventFilter(self, obj: QObject, event) -> bool:  # noqa: N802 (Qt API)
        from PyQt5.QtCore import QEvent

        parent_resized = obj is self.parentWidget()
        resize_or_show = event.type() in (QEvent.Resize, QEvent.Show)
        if parent_resized and resize_or_show and self.isVisible():
            self.reposition()
        return super().eventFilter(obj, event)
