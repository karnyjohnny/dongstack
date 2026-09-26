"""app/gui/sidebar.py — stała nawigacja statusów (Biblia §1.2, §11, §31).

QListWidget#statusNavigation z własnymi NavItemWidget (ikona + label + badge).
Zero przebudów całego GUI przy zmianie filtra: emitujemy tylko statusFilterChanged.
"""

from __future__ import annotations

from typing import Dict, List, Tuple

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.gui import theme

SIDEBAR_WIDTH = 210

# (klucz statusu, etykieta PL, nazwa ikony)
NAV_ITEMS: List[Tuple[str, str, str]] = [
    ("all", "Wszystkie", "app"),
    ("watching", "W trakcie", "status_watching"),
    ("completed", "Obejrzane", "status_completed"),
    ("planned", "Planowane", "status_planned"),
    ("dropped", "Porzucone", "status_dropped"),
]


class NavItemWidget(QFrame):
    """Wiersz nawigacji: ikona + etykieta + dyskretny badge licznika (Biblia §1.2)."""

    def __init__(self, label: str, icon_name: str, parent: QWidget = None) -> None:
        super().__init__(parent)
        self.setObjectName("navItem")
        self.setProperty("active", False)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(10)

        self._icon = QLabel(self)
        self._icon.setFixedSize(16, 16)
        self._icon.setPixmap(theme.icon(icon_name).pixmap(16, 16))
        layout.addWidget(self._icon)

        self._label = QLabel(label, self)
        self._label.setObjectName("navLabel")
        layout.addWidget(self._label, 1)

        self._badge = QLabel("", self)
        self._badge.setObjectName("navBadge")
        self._badge.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        layout.addWidget(self._badge)
        self._active = False

    def set_count(self, count: int) -> None:
        self._badge.setText("" if count <= 0 else str(count))

    _ACTIVE_QSS = (
        "QFrame#navItem { background-color: #2A2A2A; border-radius: 8px; }"
        "QLabel#navLabel { color: #E6E1E5; }"
        "QLabel#navBadge { color: #B39DDB; }"
    )
    _INACTIVE_QSS = (
        "QFrame#navItem { background-color: transparent; border-radius: 8px; }"
        "QLabel#navLabel { color: #A0A0A0; }"
        "QLabel#navBadge { color: #707070; }"
    )

    def set_active(self, active: bool) -> None:
        """Stan aktywności bez unpolish/polish (burza repaintów = freeze na Win7/GMA).

        Inline stylesheet jest scoped do tego widgetu — koszt liczony w µs,
        a jawne update() zamyka temat „duchów” (starych podświetleń).
        """
        self._active = bool(active)
        self.setStyleSheet(self._ACTIVE_QSS if self._active else self._INACTIVE_QSS)
        self.update()
        self._label.update()
        self._badge.update()

    @property
    def is_active(self) -> bool:
        return getattr(self, "_active", False)


class SidebarWidget(QFrame):
    """Sidebar: logo + nawigacja statusów. Stała szerokość ustawiana w MainWindow."""

    statusFilterChanged = pyqtSignal(str)

    def __init__(self, parent: QWidget = None) -> None:
        super().__init__(parent)
        self.setObjectName("sidebar")
        self.setFixedWidth(SIDEBAR_WIDTH)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 12, 8, 12)
        layout.setSpacing(8)

        logo_row = QHBoxLayout()
        logo_row.setContentsMargins(6, 0, 6, 4)
        logo_row.setSpacing(8)
        logo_icon = QLabel(self)
        logo_icon.setFixedSize(24, 24)
        logo_icon.setPixmap(theme.icon("app").pixmap(24, 24))
        logo_row.addWidget(logo_icon)
        logo_text = QLabel("DongStack", self)
        logo_text.setObjectName("appLogoLabel")
        logo_row.addWidget(logo_text, 1)
        layout.addLayout(logo_row)

        separator = QFrame(self)
        separator.setObjectName("separator")
        layout.addWidget(separator)

        self._nav = QListWidget(self)
        self._nav.setObjectName("statusNavigation")
        self._nav.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._nav.setSpacing(2)
        self._items: Dict[str, NavItemWidget] = {}
        for key, label, icon_name in NAV_ITEMS:
            item = QListWidgetItem(self._nav)
            widget = NavItemWidget(label, icon_name, self._nav)
            item.setSizeHint(widget.sizeHint())
            self._nav.addItem(item)
            self._nav.setItemWidget(item, widget)
            self._items[key] = widget
        self._nav.currentRowChanged.connect(self._on_row_changed)
        layout.addWidget(self._nav, 1)

        self._keys: List[str] = [k for k, _, _ in NAV_ITEMS]
        self._nav.setCurrentRow(1)  # ekran startowy = "W trakcie" (Biblia §68.2)
        self._items["watching"].set_active(True)

    # --- API -------------------------------------------------------------------
    @property
    def current_status(self) -> str:
        row = self._nav.currentRow()
        if 0 <= row < len(self._keys):
            return self._keys[row]
        return "all"

    def set_current(self, status: str) -> None:
        if status in self._keys:
            self._nav.setCurrentRow(self._keys.index(status))

    def set_counts(self, counts: Dict[str, int]) -> None:
        """counts: {'watching': n, ..., 'all': n} — badge'e sidebara."""
        for key, widget in self._items.items():
            widget.set_count(int(counts.get(key, 0)))

    # --- sloty -------------------------------------------------------------------
    def _on_row_changed(self, row: int) -> None:
        for i, key in enumerate(self._keys):
            self._items[key].set_active(i == row)
        if 0 <= row < len(self._keys):
            self.statusFilterChanged.emit(self._keys[row])
