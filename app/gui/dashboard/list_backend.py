"""app/gui/dashboard/list_backend.py — abstrakcja listy głównej (specyfikacja §6.3).

v1: WidgetListBackend = QListWidget + setItemWidget(DonghuaRow) (Biblia §3.1).

Uwłaszczenie widgetów (Qt): setItemWidget przekazuje własność widokowi, a podmiana
widgetu na indeksie robi deleteLater starego — dlatego NIE pulujemy wierszy między
przebudowami. Przebudowa (zmiana filtra/sortu) = takeItem + setParent(None) +
deleteLater starego wiersza i stworzenie nowych. GORĄCA ŚCIEŻKA `+1` NIGDY nie
przebudowuje listy: update_item() aktualizuje istniejący wiersz w miejscu (§6.2).
Gate G3: jeżeli rebuild 300 wierszy >150 ms na E5500 → DelegateListBackend
(QListView + QStyledItemDelegate, Biblia §43) pod tym samym interfejsem.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from PyQt5.QtCore import QObject, QSize, Qt, pyqtSignal
from PyQt5.QtWidgets import QListWidget, QListWidgetItem, QWidget

from app.domain.models import Donghua
from app.gui.cover_coordinator import shared_pixmaps
from app.gui.dashboard.donghua_row import DonghuaRow
from app.gui.dashboard.skeleton import ROW_HEIGHT, SkeletonRow


class ListBackend(QObject):
    """Interfejs backendu listy + jednolite sygnały zdarzeń wiersza/nagłówka."""

    BACKEND_NAME = "base"

    rowCreated = pyqtSignal(object)
    moveRequested = pyqtSignal(int, int)
    incrementRequested = pyqtSignal(int)
    decrementRequested = pyqtSignal(int)
    detailsRequested = pyqtSignal(int)
    editRequested = pyqtSignal(int)

    def set_cover(self, url: str, pixmap) -> None:
        raise NotImplementedError

    def widget(self) -> QWidget:
        raise NotImplementedError

    def set_items(self, items: List[Donghua]) -> None:
        raise NotImplementedError

    def update_item(self, d: Donghua) -> None:
        raise NotImplementedError

    def remove_item(self, donghua_id: int) -> None:
        raise NotImplementedError

    def count(self) -> int:
        raise NotImplementedError

    def clear(self) -> None:
        raise NotImplementedError

    def show_skeleton(self, rows: int = 4) -> None:
        raise NotImplementedError

    # --- podświetlenie uniwersum (M9, §6.7) --------------------------------------
    def set_universe_hover(self, universe_id, donghua_id) -> None:
        """(universe_id, donghua_id) pod kursorem; None czyści podświetlenie."""

    def universe_at_pos(self, pos):
        """(universe_id, donghua_id) karty pod punktem viewportu; (None, None)."""
        return None, None


class WidgetListBackend(ListBackend):
    """QListWidget + custom row widget; uniformItemSizes, stała wysokość wiersza."""

    BACKEND_NAME = "widgets"

    def __init__(self, parent: QWidget = None) -> None:
        super().__init__(parent)
        self._list = QListWidget(parent)
        self._list.setObjectName("donghuaList")
        self._list.setUniformItemSizes(True)  # §6.3: stała wysokość wiersza
        self._list.setSpacing(6)
        self._list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._list.setVerticalScrollMode(QListWidget.ScrollPerPixel)
        self._list.setSelectionMode(QListWidget.SingleSelection)
        self._list.setContentsMargins(8, 8, 8, 8)
        self._rows: Dict[int, DonghuaRow] = {}
        self._items: Dict[int, QListWidgetItem] = {}
        self._hover_uni = None
        self._hover_id = None

    # --- API -------------------------------------------------------------------
    def widget(self) -> QWidget:
        return self._list

    def set_items(self, items) -> None:
        """items: List[Donghua] — M9: wyłącznie karty (jednolita wysokość wiersza)."""
        self._purge_rows()
        self._hover_uni = None
        self._hover_id = None
        self._list.setUpdatesEnabled(False)
        try:
            for entry in items:
                row = DonghuaRow(self._list)
                self.rowCreated.emit(row)
                row.episodeIncrementRequested.connect(self.incrementRequested)
                row.episodeDecrementRequested.connect(self.decrementRequested)
                row.detailsRequested.connect(self.detailsRequested)
                row.editRequested.connect(self.editRequested)
                row.moveRequested.connect(self.moveRequested)
                row.hoverStateChanged.connect(self._on_row_hover)
                row.set_donghua(entry)
                if entry.cover_key:
                    cached = shared_pixmaps().get(entry.cover_key)
                    if cached is not None:
                        row.set_cover_pixmap(cached)
                item = QListWidgetItem(self._list)
                item.setSizeHint(QSize(0, ROW_HEIGHT))
                item.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
                self._list.addItem(item)
                self._list.setItemWidget(item, row)
                self._items[entry.id] = item
                self._rows[entry.id] = row
        finally:
            self._list.setUpdatesEnabled(True)

    def update_item(self, d: Donghua) -> None:
        row = self._rows.get(d.id)
        if row is not None:
            row.update_values(d)  # tania ścieżka `+1`: bez przebudowy listy (§6.2)

    def remove_item(self, donghua_id: int) -> None:
        item = self._items.pop(donghua_id, None)
        row = self._rows.pop(donghua_id, None)
        if item is not None:
            idx = self._list.row(item)
            if idx >= 0:
                self._list.takeItem(idx)
            del item
        if row is not None:
            row.setParent(None)
            row.deleteLater()

    def count(self) -> int:
        return self._list.count()

    def clear(self) -> None:
        self._purge_rows()

    def show_skeleton(self, rows: int = 4) -> None:
        self._purge_rows()
        for _ in range(max(1, rows)):
            item = QListWidgetItem(self._list)
            item.setSizeHint(QSize(0, ROW_HEIGHT))
            item.setFlags(Qt.NoItemFlags)
            self._list.addItem(item)
            self._list.setItemWidget(item, SkeletonRow(self._list))

    def row_widget(self, donghua_id: int) -> Optional[DonghuaRow]:
        return self._rows.get(donghua_id)

    def set_cover(self, url: str, pixmap) -> None:
        for row in self._rows.values():
            if getattr(row, "_cover_url", None) == url:
                row.set_cover_pixmap(pixmap)

    # --- podświetlenie uniwersum (M9, §6.7) ---------------------------------------
    def _on_row_hover(self, donghua_id: int, inside: bool) -> None:
        row = self._rows.get(donghua_id)
        if row is None:
            return
        if inside:
            self.set_universe_hover(row.universe_id, donghua_id)
        else:
            self.set_universe_hover(None, None)

    def set_universe_hover(self, universe_id, donghua_id) -> None:
        universe_id = int(universe_id) if universe_id is not None else None
        donghua_id = int(donghua_id) if donghua_id is not None else None
        if (universe_id, donghua_id) == (self._hover_uni, self._hover_id):
            return
        self._hover_uni, self._hover_id = universe_id, donghua_id
        for did, row in self._rows.items():
            level = 0
            if universe_id is not None and row.universe_id == universe_id:
                level = 2 if did == donghua_id else 1
            if row.universe_hl != level:
                row.set_universe_hl(level)

    def universe_at_pos(self, pos):
        item = self._list.itemAt(pos)
        if item is None:
            return None, None
        row = self._list.itemWidget(item)
        if isinstance(row, DonghuaRow):
            return row.universe_id, row.donghua_id
        return None, None

    # --- wewnętrzne ---------------------------------------------------------------
    def _purge_rows(self) -> None:
        """Usuwa itemy z listy i poprawnie zwalnia stare wiersze/skeletony."""
        for i in reversed(range(self._list.count())):
            item = self._list.item(i)
            if item is None:
                continue
            w = self._list.itemWidget(item)
            self._list.takeItem(i)
            if w is not None:
                w.setParent(None)
                w.deleteLater()
        self._list.clear()
        self._rows.clear()
        self._items.clear()
