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

from app.domain.models import DisplayHeader, Donghua
from app.gui.dashboard.donghua_row import DonghuaRow
from app.gui.dashboard.skeleton import ROW_HEIGHT, SkeletonRow
from app.gui.dashboard.universe_header import HEADER_HEIGHT, UniverseHeaderRow


class ListBackend(QObject):
    """Interfejs backendu listy + sygnały rowCreated/headerToggled."""

    rowCreated = pyqtSignal(object)
    headerToggled = pyqtSignal(int)

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


class WidgetListBackend(ListBackend):
    """QListWidget + custom row widget; uniformItemSizes, stała wysokość wiersza."""

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
        self._header_items: Dict[int, QListWidgetItem] = {}

    # --- API -------------------------------------------------------------------
    def widget(self) -> QWidget:
        return self._list

    def set_items(self, items) -> None:
        """items: List[Donghua | DisplayHeader] — display-model z nagłówkami (§6.7)."""
        self._purge_rows()
        self._list.setUpdatesEnabled(False)
        try:
            for entry in items:
                if isinstance(entry, DisplayHeader):
                    row = UniverseHeaderRow(
                        entry.universe_id, entry.name, entry.badge, entry.collapsed, self._list
                    )
                    row.toggled.connect(self.headerToggled)
                    flags = Qt.NoItemFlags  # nieinteraktywny wiersz (Biblia: bez hover-only)
                else:
                    row = DonghuaRow(self._list)
                    self.rowCreated.emit(row)
                    row.set_donghua(entry)
                    flags = Qt.ItemIsSelectable | Qt.ItemIsEnabled
                    self._rows[entry.id] = row
                item = QListWidgetItem(self._list)
                item.setSizeHint(
                    QSize(0, HEADER_HEIGHT if isinstance(entry, DisplayHeader) else ROW_HEIGHT)
                )
                item.setFlags(flags)
                self._list.addItem(item)
                self._list.setItemWidget(item, row)
                if isinstance(entry, DisplayHeader):
                    self._header_items[entry.universe_id] = item
                else:
                    self._items[entry.id] = item
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
        self._header_items.clear()
