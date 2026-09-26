"""app/gui/add/search_page.py — strona wyszukiwania AddDialog (Biblia §16, §20).

Stany: IDLE / SEARCHING (skeleton) / RESULTS / NO_RESULTS / ERROR.
Błąd NIE niszczy wpisanego zapytania; „Spróbuj ponownie” powtarza ostatnie.
"""

from __future__ import annotations

from typing import List

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QFrame,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.domain.models import SearchItem
from app.gui import theme
from app.gui.add.mal_result_row import MalResultRow
from app.gui.dashboard.skeleton import SkeletonRow

ROW_H = 76


class SearchPage(QWidget):
    textChanged = pyqtSignal(str)
    quickAddRequested = pyqtSignal(object)  # SearchItem
    advancedRequested = pyqtSignal(object)  # SearchItem (przycisk ⋮)
    retryRequested = pyqtSignal()
    returnPressed = pyqtSignal()  # Enter: szukaj natychmiast (feedback M6-fix)

    def __init__(self, parent: QWidget = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 12)
        layout.setSpacing(10)

        self._edit = QLineEdit(self)
        self._edit.setObjectName("malSearch")
        self._edit.setPlaceholderText("Szukaj tytułu donghua (MAL / AniList)…")
        self._edit.setClearButtonEnabled(True)
        self._edit.addAction(theme.icon("search"), QLineEdit.LeadingPosition)
        self._edit.textChanged.connect(self.textChanged)
        self._edit.returnPressed.connect(self.returnPressed)
        layout.addWidget(self._edit)

        self._hint = QLabel("Wpisz tytuł…", self)
        self._hint.setObjectName("searchHint")
        layout.addWidget(self._hint)

        sep = QFrame(self)
        sep.setObjectName("separator")
        layout.addWidget(sep)

        self._list = QListWidget(self)
        self._list.setObjectName("malResults")
        self._list.setUniformItemSizes(True)
        self._list.setSpacing(6)
        self._list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._list.setVerticalScrollMode(QListWidget.ScrollPerPixel)
        self._list.setSelectionMode(QListWidget.NoSelection)
        layout.addWidget(self._list, 1)

        self._cover_rows: dict = {}
        self._result_rows: list = []
        self._cover_requester = None

        self._retry = QPushButton("Spróbuj ponownie", self)
        self._retry.hide()
        self._retry.clicked.connect(self.retryRequested)
        layout.addWidget(self._retry, 0, Qt.AlignCenter)

    # --- API stanów (Biblia §20) ------------------------------------------------------
    @property
    def line_edit(self) -> QLineEdit:
        return self._edit

    def focus_input(self) -> None:
        self._edit.setFocus(Qt.OtherFocusReason)

    def _clear_list(self) -> None:
        """Zwalnia wiersze/skeletony BEZ wycieku i bez crasha.

        UWAGA (bug produkcyjny v1.0.0): QApplication dialogu potrafi dostarczyć
        okładkę PO przebudowie listy — mapa _cover_rows musi być czyszczona
        razem z wierszami, inaczej apply_cover dotyka usuniętych QLabel
        (RuntimeError: wrapped C/C++ object of type QLabel has been deleted).
        Kolejność: removeItemWidget(item) → setParent(None) → deleteLater.
        """
        for i in reversed(range(self._list.count())):
            item = self._list.item(i)
            if item is None:
                continue
            w = self._list.itemWidget(item)
            self._list.removeItemWidget(item)
            if w is not None:
                w.setParent(None)
                w.deleteLater()
        self._list.clear()
        self._cover_rows.clear()
        self._result_rows = []

    def show_idle(self, provider_note: str = "") -> None:
        self._clear_list()
        self._retry.hide()
        self._hint.show()
        self._hint.setText(provider_note or "Wpisz tytuł…")

    def show_searching(self) -> None:
        self._clear_list()
        self._retry.hide()
        self._hint.show()
        self._hint.setText("Szukam…")
        for _ in range(4):  # skeleton STATYCZNY (R9)
            item = QListWidgetItem(self._list)
            from PyQt5.QtCore import QSize

            item.setSizeHint(QSize(0, ROW_H))
            item.setFlags(Qt.NoItemFlags)
            self._list.addItem(item)
            self._list.setItemWidget(item, SkeletonRow(self._list))

    def show_results(self, items: List[SearchItem], provider: str, in_library: set) -> None:
        self._clear_list()
        self._retry.hide()
        self._hint.show()
        self._hint.setText("Źródło: %s · %d wyników" % (provider.upper(), len(items)))
        from PyQt5.QtCore import QSize

        from app.gui.cover_coordinator import shared_pixmaps

        cache = shared_pixmaps()
        self._cover_rows = {}
        self._result_rows = []
        missing = []
        for it in items:
            row = MalResultRow(self._list)
            row.set_item(it)
            key = it.mal_id if it.mal_id is not None else (provider, it.ext_id)
            row.set_in_library(key in in_library)
            row.quickAddRequested.connect(self.quickAddRequested)
            row.advancedRequested.connect(self.advancedRequested)
            item = QListWidgetItem(self._list)
            item.setSizeHint(QSize(0, ROW_H))
            item.setFlags(Qt.NoItemFlags)
            self._list.addItem(item)
            self._list.setItemWidget(item, row)
            self._result_rows.append(row)
            url = it.cover_url
            if url:
                cached = cache.get(url)
                if cached is not None:
                    row.set_cover_pixmap(cached)
                else:
                    self._cover_rows.setdefault(url, []).append(row)
                    missing.append((url, it.mal_id or 0))
        if missing and self._cover_requester is not None:
            self._cover_requester(missing)

    # --- okładki i duplikaty (M6-fix) ---------------------------------------------------
    def set_cover_requester(self, callback) -> None:
        """callback(urls) → CoverCoordinator.request_urls (zamówienie LOW w workerze)."""
        self._cover_requester = callback

    def apply_cover(self, url: str, pixmap) -> None:
        """Odporna na martwe wiersze: spóźniona okładka nie może crashować (v1.0.1)."""
        alive = []
        for row in self._cover_rows.get(url, ()):
            try:
                row.set_cover_pixmap(pixmap)
                alive.append(row)
            except RuntimeError:
                continue  # wiersz usunięty przez przebudowę listy — porzuć ref
        if alive:
            self._cover_rows[url] = alive
        else:
            self._cover_rows.pop(url, None)

    def mark_in_library(self, mal_id) -> None:
        """Po Quick/Advanced Add: badge „✓ Już w bibliotece" bez ponownego szukania."""
        if mal_id is None:
            return
        for row in self._result_rows:
            if row._item is not None and row._item.mal_id == mal_id:
                row.set_in_library(True)

    def show_no_results(self, query: str) -> None:
        self._clear_list()
        self._retry.hide()
        self._hint.show()
        self._hint.setText("Nie znaleziono tytułów dla „%s”" % query)

    def show_error(self, message: str) -> None:
        self._clear_list()
        self._hint.show()
        self._hint.setText(message)
        self._retry.show()
