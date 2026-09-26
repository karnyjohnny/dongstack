"""app/gui/main_window.py — QMainWindow: sidebar + content (Biblia §1, §67).

Jeden stabilny kontekst okna; dodawanie/edycja to moduły uruchamiane z niego.
Shortcuty (Biblia §47): Ctrl+F lokalne szukaj, Ctrl+N dodawanie, Esc zamyka overlay.
"""

from __future__ import annotations

from typing import Dict, List

from PyQt5.QtCore import pyqtSignal
from PyQt5.QtGui import QKeySequence
from PyQt5.QtWidgets import (
    QHBoxLayout,
    QMainWindow,
    QShortcut,
    QWidget,
)

from app import __version__
from app.domain.models import Donghua
from app.gui.dashboard.dashboard_widget import DashboardWidget
from app.gui.sidebar import SidebarWidget
from app.gui.snackbar import SnackBar
from app.gui.theme import STATUS_LABELS


class MainWindow(QMainWindow):
    """Okno główne: [sidebar 210px | dashboard]. SnackBar jako overlay contentu."""

    # sygnały zbiorcze dla kontrolerów (M3)
    statusFilterChanged = pyqtSignal(str)
    localSearchChanged = pyqtSignal(str)
    sortChanged = pyqtSignal(str)
    addClicked = pyqtSignal()
    episodeIncrementRequested = pyqtSignal(int)
    episodeDecrementRequested = pyqtSignal(int)
    editRequested = pyqtSignal(int)
    detailsRequested = pyqtSignal(int)

    def __init__(self, animations_enabled: bool = False, parent: QWidget = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("DongStack %s" % __version__)
        self.setMinimumSize(960, 600)
        self.resize(1180, 720)

        central = QWidget(self)
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.sidebar = SidebarWidget(central)
        root.addWidget(self.sidebar)

        self.dashboard = DashboardWidget(parent=central)
        root.addWidget(self.dashboard, 1)

        self.setCentralWidget(central)

        self.snackbar = SnackBar(central, animations_enabled=animations_enabled)

        # --- przewiązania sygnałów -------------------------------------------------
        self.sidebar.statusFilterChanged.connect(self._on_status_filter)
        self.dashboard.localSearchChanged.connect(self.localSearchChanged)
        self.dashboard.sortChanged.connect(self.sortChanged)
        self.dashboard.addClicked.connect(self.addClicked)
        self.dashboard.episodeIncrementRequested.connect(self.episodeIncrementRequested)
        self.dashboard.episodeDecrementRequested.connect(self.episodeDecrementRequested)
        self.dashboard.editRequested.connect(self.editRequested)
        self.dashboard.detailsRequested.connect(self.detailsRequested)

        # --- shortcuty (Biblia §47) ---------------------------------------------------
        QShortcut(QKeySequence("Ctrl+F"), self, activated=self.dashboard.focus_search)
        QShortcut(QKeySequence("Ctrl+N"), self, activated=lambda: self.addClicked.emit())
        QShortcut(QKeySequence("Esc"), self, activated=self._on_escape)

    # --- API dla kontrolerów (M3) --------------------------------------------------
    def set_counts(self, counts: Dict[str, int]) -> None:
        self.sidebar.set_counts(counts)
        # QoL: pusty widok podpowiada, ile pozycji czeka w innych statusach
        current = self.sidebar.current_status
        others = sum(v for k, v in counts.items() if k != current and k != "all")
        self.dashboard.set_empty_note(
            "Masz %d pozycji w innych statusach — zerknij na sidebar." % others if others else ""
        )

    def set_items(self, items: List[Donghua]) -> None:
        self.dashboard.set_items(items)

    def update_item(self, d: Donghua) -> None:
        self.dashboard.update_item(d)

    def show_skeleton(self, rows: int = 4) -> None:
        self.dashboard.show_skeleton(rows)

    # --- sloty ----------------------------------------------------------------------
    def _on_status_filter(self, status: str) -> None:
        self.dashboard.set_section_title(STATUS_LABELS.get(status, "Wszystkie"))
        self.statusFilterChanged.emit(status)

    def _on_escape(self) -> None:
        if self.snackbar.isVisible():
            self.snackbar.hide_message()
        elif self.dashboard.search_edit.hasFocus():
            self.dashboard.search_edit.clearFocus()

    def resizeEvent(self, event) -> None:  # noqa: N802 (Qt API)
        super().resizeEvent(event)
        if self.snackbar is not None and self.snackbar.isVisible():
            self.snackbar.reposition()
