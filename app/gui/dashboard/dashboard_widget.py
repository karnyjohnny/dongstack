"""app/gui/dashboard/dashboard_widget.py — ekran główny (Biblia §2, §12–§14).

topBar (tytuł sekcji + lokalne szukaj + sort) → separator → lista → FAB overlay.
FAB jest dzieckiem widgetu contentu i pozostaje widoczny podczas scrollowania
(Biblia §14) — nigdy wewnątrz przewijanej listy.
"""

from __future__ import annotations

from typing import List

from PyQt5.QtCore import QSize, Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QPushButton,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from app.domain.models import Donghua, SortMode
from app.gui import theme
from app.gui.dashboard.list_backend import ListBackend, WidgetListBackend

SORT_ACTIONS = [
    (SortMode.UPDATED.value, "Ostatnio aktualizowane"),
    (SortMode.ALPHA.value, "Alfabetycznie"),
    (SortMode.ADDED.value, "Data dodania"),
    (SortMode.PROGRESS.value, "Postęp"),
    (SortMode.WATCH_ORDER.value, "Uniwersa (kolejność oglądania)"),
]


class DashboardWidget(QWidget):
    """Content: topBar + lista + FAB + empty state."""

    localSearchChanged = pyqtSignal(str)
    sortChanged = pyqtSignal(str)
    addClicked = pyqtSignal()
    openDataDirRequested = pyqtSignal()  # Ustawienia → otwórz folder danych (M6-fix)
    settingsClientIdRequested = pyqtSignal()  # Ustawienia → Client ID MAL (§5.5)
    # re-emitowane sygnały wierszy (kontroler podłącza się do dashboardu)
    episodeIncrementRequested = pyqtSignal(int)
    episodeDecrementRequested = pyqtSignal(int)
    editRequested = pyqtSignal(int)
    detailsRequested = pyqtSignal(int)

    def __init__(self, backend: ListBackend = None, parent: QWidget = None) -> None:
        super().__init__(parent)
        self._backend = backend or WidgetListBackend(self)
        self._backend.rowCreated.connect(self._on_row_created)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(10)

        # --- topBar (Biblia §2.1) -------------------------------------------------
        top = QHBoxLayout()
        top.setSpacing(10)
        self._section = QLabel("W trakcie", self)
        self._section.setObjectName("sectionTitle")
        top.addWidget(self._section)
        top.addStretch(1)

        self._search = QLineEdit(self)
        self._search.setObjectName("localSearch")
        self._search.setPlaceholderText("Szukaj w bibliotece…")
        self._search.setClearButtonEnabled(True)
        self._search.addAction(theme.icon("search"), QLineEdit.LeadingPosition)
        self._search.setFixedWidth(260)
        self._search.textChanged.connect(self.localSearchChanged)
        top.addWidget(self._search)

        self._sort = QToolButton(self)
        self._sort.setObjectName("sortButton")
        self._sort.setIcon(theme.icon("sort"))
        self._sort.setToolTip("Sortowanie")
        self._sort.setPopupMode(QToolButton.InstantPopup)
        self._sort_menu = QMenu(self._sort)
        for key, label in SORT_ACTIONS:
            action = self._sort_menu.addAction(label)
            action.setData(key)
        self._sort_menu.triggered.connect(lambda a: self.sortChanged.emit(str(a.data())))
        self._sort.setMenu(self._sort_menu)
        top.addWidget(self._sort)

        self._settings = QToolButton(self)
        self._settings.setObjectName("settingsButton")
        self._settings.setIcon(theme.icon("settings"))
        self._settings.setToolTip("Ustawienia")
        self._settings.setPopupMode(QToolButton.InstantPopup)
        settings_menu = QMenu(self._settings)
        open_dir = settings_menu.addAction("Otwórz folder danych (baza, okładki, logi)")
        open_dir.triggered.connect(lambda: self.openDataDirRequested.emit())
        cid_act = settings_menu.addAction("Client ID MyAnimeList…")
        cid_act.triggered.connect(lambda: self.settingsClientIdRequested.emit())
        self._settings.setMenu(settings_menu)
        top.addWidget(self._settings)
        layout.addLayout(top)

        separator = QFrame(self)
        separator.setObjectName("separator")
        layout.addWidget(separator)

        # --- lista + empty state ----------------------------------------------------
        self._empty = QLabel(
            "Brak tytułów w tym widoku.\nKliknij  +  aby dodać pierwsze donghua.", self
        )
        self._empty.setObjectName("emptyHint")
        self._empty_note = ""
        self._empty.setAlignment(Qt.AlignCenter)
        self._empty.hide()
        layout.addWidget(self._empty)

        layout.addWidget(self._backend.widget(), 1)

        # --- FAB overlay (Biblia §14, §34) --------------------------------------------
        self._add = QPushButton(self)
        self._add.setObjectName("addButton")
        self._add.setIcon(theme.icon("add_dark"))
        self._add.setIconSize(QSize(24, 24))
        self._add.setToolTip("Dodaj donghua (Ctrl+N)")
        self._add.setCursor(Qt.PointingHandCursor)
        self._add.clicked.connect(self.addClicked)
        self._add.setParent(self)
        self._add.raise_()

        self._skeleton_visible = False

    # --- API ---------------------------------------------------------------------
    @property
    def backend(self) -> ListBackend:
        return self._backend

    @property
    def search_edit(self) -> QLineEdit:
        return self._search

    def set_section_title(self, title: str) -> None:
        self._section.setText(title)

    def set_items(self, items: List[Donghua]) -> None:
        self._skeleton_visible = False
        self._backend.set_items(items)
        self._sync_empty_state()

    def update_item(self, d: Donghua) -> None:
        self._backend.update_item(d)

    def remove_item(self, donghua_id: int) -> None:
        self._backend.remove_item(donghua_id)
        self._sync_empty_state()

    def show_skeleton(self, rows: int = 4) -> None:
        self._skeleton_visible = True
        self._backend.show_skeleton(rows)
        self._empty.hide()

    def focus_search(self) -> None:
        self._search.setFocus(Qt.ShortcutFocusReason)

    # --- wewnętrzne ------------------------------------------------------------------
    def set_empty_note(self, note: str) -> None:
        """Druga linia empty-state: ile pozycji czeka w innych statusach (QoL)."""
        self._empty_note = note or ""
        self._apply_empty_text()

    def _apply_empty_text(self) -> None:
        base = "Brak tytułów w tym widoku.\nKliknij  +  aby dodać pierwsze donghua."
        self._empty.setText(base + ("\n" + self._empty_note if self._empty_note else ""))

    def _sync_empty_state(self) -> None:
        empty = (not self._skeleton_visible) and self._backend.count() == 0
        self._apply_empty_text()
        self._empty.setVisible(empty)
        self._backend.widget().setVisible(not empty)

    def _on_row_created(self, row) -> None:
        row.episodeIncrementRequested.connect(self.episodeIncrementRequested)
        row.episodeDecrementRequested.connect(self.episodeDecrementRequested)
        row.editRequested.connect(self.editRequested)
        row.detailsRequested.connect(self.detailsRequested)

    def resizeEvent(self, event) -> None:  # noqa: N802 (Qt API)
        super().resizeEvent(event)
        margin = 18
        self._add.move(
            self.width() - self._add.width() - margin, self.height() - self._add.height() - margin
        )
        self._add.raise_()

    def showEvent(self, event) -> None:  # noqa: N802 (Qt API)
        super().showEvent(event)
        self._add.raise_()
