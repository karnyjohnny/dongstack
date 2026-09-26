"""app/gui/dashboard/universe_header.py — nagłówek grupy uniwersum (§6.7).

Nieinteraktywny wiersz listy (poza kliknięciem = collapse): nazwa + badge postępu
zbiorczego + strzałka. Zero dodatkowych layoutów ponad płaską listę (budżet G3).
"""

from __future__ import annotations

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import QFrame, QHBoxLayout, QLabel, QWidget

from app.gui import theme

HEADER_HEIGHT = 34


class UniverseHeaderRow(QFrame):
    toggled = pyqtSignal(int)  # universe_id

    def __init__(
        self,
        universe_id: int,
        name: str,
        badge: str,
        collapsed: bool = False,
        parent: QWidget = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("universeHeader")
        self.setFixedHeight(HEADER_HEIGHT)
        self._universe_id = universe_id
        self._collapsed = collapsed
        self.setCursor(Qt.PointingHandCursor)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 4, 10, 4)
        layout.setSpacing(8)

        self._arrow = QLabel(self)
        self._arrow.setFixedSize(12, 12)
        layout.addWidget(self._arrow)

        icon = QLabel(self)
        icon.setFixedSize(14, 14)
        icon.setPixmap(theme.icon("link").pixmap(14, 14))
        layout.addWidget(icon)

        self._name = QLabel(name, self)
        self._name.setObjectName("universeTitle")
        layout.addWidget(self._name, 1)

        self._badge = QLabel(badge, self)
        self._badge.setObjectName("universeBadge")
        layout.addWidget(self._badge)

        self._apply_arrow()

    @property
    def universe_id(self) -> int:
        return self._universe_id

    def set_collapsed(self, collapsed: bool) -> None:
        self._collapsed = collapsed
        self._apply_arrow()

    def _apply_arrow(self) -> None:
        self._arrow.setText("▸" if self._collapsed else "▾")

    def mousePressEvent(self, event) -> None:  # noqa: N802 (Qt API)
        self.toggled.emit(self._universe_id)
        super().mousePressEvent(event)
