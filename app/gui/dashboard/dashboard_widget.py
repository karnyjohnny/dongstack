"""app/gui/dashboard/dashboard_widget.py — ekran główny (Biblia §2, §12–§14).

topBar (tytuł sekcji + lokalne szukaj + sort) → separator → lista → FAB overlay.
FAB jest dzieckiem widgetu contentu i pozostaje widoczny podczas scrollowania
(Biblia §14) — nigdy wewnątrz przewijanej listy.
"""

from __future__ import annotations

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

# gate G3 (§7.4): powyżej progu lista malowana (delegate), poniżej — widgetowa
AUTO_BACKEND_THRESHOLD = 100

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
    addManualClicked = pyqtSignal()  # M9: PPM na FABie = ręczne dodawanie
    openDataDirRequested = pyqtSignal()  # Ustawienia → otwórz folder danych (M6-fix)
    settingsClientIdRequested = pyqtSignal()  # Ustawienia → Client ID MAL (§5.5)
    settingsUniversesRequested = pyqtSignal()  # Ustawienia → zarządzanie uniwersami (r11)
    # re-emitowane sygnały wierszy (kontroler podłącza się do dashboardu)
    episodeIncrementRequested = pyqtSignal(int)
    episodeDecrementRequested = pyqtSignal(int)
    editRequested = pyqtSignal(int)
    detailsRequested = pyqtSignal(int)
    moveRequested = pyqtSignal(int, int)

    def __init__(
        self, backend: ListBackend = None, parent: QWidget = None, backend_kind: str = "auto"
    ) -> None:
        super().__init__(parent)
        self._backend_kind = (
            backend_kind if backend_kind in ("auto", "widgets", "delegate") else "auto"
        )
        self._backend = backend or WidgetListBackend(self)
        self._connect_backend(self._backend)

        layout = QVBoxLayout(self)
        self._vlayout = layout
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
        uni_act = settings_menu.addAction("Uniwersa (przypisane sezony, usuwanie)…")
        uni_act.triggered.connect(lambda: self.settingsUniversesRequested.emit())
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
        self._add.setToolTip("Dodaj donghua (Ctrl+N)\nPPM: wpis ręczny (bez MAL/AniList)")
        self._add.setCursor(Qt.PointingHandCursor)
        self._add.clicked.connect(self.addClicked)
        # M9: prawy przycisk na FABie = manual add (feedback r7)
        self._add.setContextMenuPolicy(Qt.CustomContextMenu)
        self._add.customContextMenuRequested.connect(lambda _pos: self.addManualClicked.emit())
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

    def set_items(self, items) -> None:
        want = self._backend_kind
        if want == "auto":
            want = "delegate" if len(items) > AUTO_BACKEND_THRESHOLD else "widgets"
        if want != self._backend.BACKEND_NAME:
            self._swap_backend(want)
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

    def _connect_backend(self, b: ListBackend) -> None:
        b.incrementRequested.connect(self.episodeIncrementRequested)
        b.decrementRequested.connect(self.episodeDecrementRequested)
        b.editRequested.connect(self.editRequested)
        b.detailsRequested.connect(self.detailsRequested)
        b.moveRequested.connect(self.moveRequested)

    def _swap_backend(self, want: str) -> None:
        """Auto-swap gate G3: widgets <-> delegate bez dotykania kontrolera."""
        from app.gui.dashboard.delegate_backend import DelegateListBackend

        old_w = self._backend.widget()
        new_b = DelegateListBackend(self) if want == "delegate" else WidgetListBackend(self)
        self._connect_backend(new_b)
        idx = self._vlayout.indexOf(old_w)
        self._vlayout.removeWidget(old_w)
        old_w.setParent(None)
        old_w.deleteLater()
        self._vlayout.insertWidget(idx, new_b.widget(), 1)
        self._backend = new_b

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
