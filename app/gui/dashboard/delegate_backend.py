"""app/gui/dashboard/delegate_backend.py — DelegateListBackend (gate G3, §6.3/§7.4).

Pomiar M7 na E5500: rebuild 300 wierszy WidgetListBackend = 1689 ms (próg 150 ms)
→ Biblia §43 przewidziana ścieżka skalowania: QListView + QAbstractListModel
+ QStyledItemDelegate. Malowane są WYŁĄCZNIE widoczne wiersze (viewport), więc
koszt przebudowy nie zależy od rozmiaru biblioteki; `+/−` to hit-testy w
editorEvent zamiast prawdziwych QPushButton.

Kontrakt identyczny z WidgetListBackend (sygnały ListBackend) — kontroler
i koordynator okładek nie widzą różnicy.
"""

from __future__ import annotations

from typing import Dict, List

from PyQt5.QtCore import QAbstractListModel, QEvent, QModelIndex, QPointF, QRect, QSize, Qt
from PyQt5.QtGui import QColor, QPainter, QPen, QPolygonF
from PyQt5.QtWidgets import (
    QListView,
    QMenu,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QToolTip,
    QWidget,
)

from app.domain.models import DisplayHeader, Donghua
from app.gui import theme
from app.gui.dashboard.donghua_row import _STATUS_PL
from app.gui.dashboard.list_backend import ListBackend
from app.gui.dashboard.skeleton import ROW_HEIGHT
from app.gui.dashboard.universe_header import HEADER_HEIGHT

KIND_ROLE = Qt.UserRole + 1
DATA_ROLE = Qt.UserRole + 2

KIND_ITEM = "item"
KIND_HEADER = "header"
KIND_SKELETON = "skeleton"

_C_BG = QColor("#1E1E1E")
_C_BG_HOVER = QColor("#242424")
_C_BORDER = QColor("#303030")
_C_BORDER_HOVER = QColor("#444444")
_C_TEXT = QColor("#E6E1E5")
_C_TEXT2 = QColor("#A0A0A0")
_C_TEXT3 = QColor("#707070")
_C_ACCENT = QColor("#B39DDB")
_C_BAR_BG = QColor("#2A2A2A")
_C_BTN_BG = QColor("#242424")
_C_BTN_DIS = QColor("#1E1E1E")
_C_BTN_BORDER_DIS = QColor("#262626")
_C_SKELETON = QColor("#242424")


def button_rects(rect: QRect):
    """(minus, plus) — identyczne geometrie jak karta widgetowa (40×40)."""
    right = rect.right() - 12
    cy = rect.center().y()
    plus = QRect(right - 40, cy - 20, 40, 40)
    minus = QRect(right - 40 - 8 - 40, cy - 20, 40, 40)
    return minus, plus


def episode_rect(rect: QRect) -> QRect:
    _, plus = button_rects(rect)
    return QRect(rect.left() + 12 + 57 + 12, plus.top(), minus_width(rect), 40)


def minus_width(rect: QRect) -> int:
    minus, _ = button_rects(rect)
    return minus.left() - 12 - (rect.left() + 12 + 57 + 12)


class _Model(QAbstractListModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._entries: List[object] = []
        self._covers: Dict[str, object] = {}

    # --- QAbstractListModel ---
    def rowCount(self, parent=None):
        if parent is not None and parent.isValid():
            return 0
        return len(self._entries)

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        entry = self._entries[index.row()]
        if role == KIND_ROLE:
            if entry is None:
                return KIND_SKELETON
            return KIND_HEADER if isinstance(entry, DisplayHeader) else KIND_ITEM
        if role == DATA_ROLE:
            return entry
        return None

    def flags(self, index):
        base = super().flags(index)
        if self.data(index, KIND_ROLE) != KIND_ITEM:
            return Qt.NoItemFlags
        return base | Qt.ItemIsSelectable

    # --- mutacje ---
    def set_entries(self, entries: List[object]) -> None:
        self.beginResetModel()
        self._entries = list(entries)
        self.endResetModel()

    def update(self, d: Donghua) -> None:
        for i, e in enumerate(self._entries):
            if isinstance(e, Donghua) and e.id == d.id:
                self._entries[i] = d
                idx = self.index(i, 0)
                self.dataChanged.emit(idx, idx, (Qt.DisplayRole,))
                return

    def remove(self, donghua_id: int) -> None:
        for i, e in enumerate(self._entries):
            if isinstance(e, Donghua) and e.id == donghua_id:
                self.beginRemoveRows(QModelIndex(), i, i)
                del self._entries[i]
                self.endRemoveRows()
                return

    def entry_at(self, row: int):
        if 0 <= row < len(self._entries):
            return self._entries[row]
        return None

    def set_cover(self, url: str, pixmap) -> None:
        self._covers[url] = pixmap
        for i, e in enumerate(self._entries):
            if isinstance(e, Donghua) and e.cover_key == url:
                idx = self.index(i, 0)
                self.dataChanged.emit(idx, idx, (Qt.DecorationRole,))

    def cover_for(self, d: Donghua):
        if d.cover_key:
            return self._covers.get(d.cover_key)
        return None


class CardDelegate(QStyledItemDelegate):
    def __init__(self, backend, parent=None):
        super().__init__(parent)
        self._backend = backend
        self._placeholder = theme.icon("cover_placeholder").pixmap(57, 80)
        self._add_px = theme.icon("add").pixmap(20, 20)
        self._remove_px = theme.icon("remove").pixmap(20, 20)
        self._link_px = theme.icon("link").pixmap(14, 14)

    # --- geometria pomocnicza ---
    @staticmethod
    def _card(rect: QRect) -> QRect:
        return rect.adjusted(0, 3, 0, -3)

    def sizeHint(self, option, index):
        kind = index.data(KIND_ROLE)
        if kind == KIND_HEADER:
            return QSize(0, HEADER_HEIGHT)
        return QSize(0, ROW_HEIGHT)

    # --- malowanie ---
    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex):
        kind = index.data(KIND_ROLE)
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, True)
        rect = self._card(option.rect)
        if kind == KIND_SKELETON:
            self._paint_skeleton(painter, rect)
        elif kind == KIND_HEADER:
            self._paint_header(painter, rect, index.data(DATA_ROLE))
        else:
            self._paint_card(painter, option, rect, index.data(DATA_ROLE))
        painter.restore()

    def _paint_skeleton(self, painter: QPainter, rect: QRect) -> None:
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor("#1E1E1E"))
        painter.drawRoundedRect(rect, 10, 10)
        painter.setBrush(_C_SKELETON)
        painter.drawRoundedRect(QRect(rect.left() + 12, rect.top() + 8, 57, 80), 6, 6)
        x = rect.left() + 12 + 57 + 12
        painter.drawRoundedRect(QRect(x, rect.top() + 12, 220, 14), 5, 5)
        painter.drawRoundedRect(QRect(x, rect.top() + 34, 140, 10), 5, 5)
        painter.drawRoundedRect(QRect(x, rect.bottom() - 20, 180, 4), 2, 2)
        minus, plus = button_rects(rect)
        painter.drawRoundedRect(plus, 20, 20)

    def _paint_header(self, painter: QPainter, rect: QRect, h: DisplayHeader) -> None:
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(_C_TEXT2))
        x = rect.left() + 10
        cy = rect.center().y()
        if h.collapsed:  # strzałka w prawo
            painter.drawPolygon(
                QPolygonF([QPointF(x, cy - 5), QPointF(x + 8, cy), QPointF(x, cy + 5)])
            )
        else:  # strzałka w dół
            painter.drawPolygon(
                QPolygonF([QPointF(x, cy - 3), QPointF(x + 8, cy - 3), QPointF(x + 4, cy + 4)])
            )
        x += 16
        painter.drawPixmap(x, rect.center().y() - 7, self._link_px)
        x += 20
        font = painter.font()
        font.setPixelSize(12)
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(QPen(_C_TEXT2))
        painter.drawText(
            QRect(x, rect.top(), rect.width() - x - 180, rect.height()),
            Qt.AlignVCenter | Qt.AlignLeft,
            h.name,
        )
        painter.setPen(QPen(_C_TEXT3))
        font.setBold(False)
        painter.setFont(font)
        painter.drawText(
            QRect(rect.left(), rect.top(), rect.width() - 16, rect.height()),
            Qt.AlignVCenter | Qt.AlignRight,
            h.badge,
        )

    def _paint_card(
        self, painter: QPainter, option: QStyleOptionViewItem, rect: QRect, d: Donghua
    ) -> None:
        hover = bool(option.state & QStyle.State_MouseOver)
        selected = bool(option.state & QStyle.State_Selected)
        if hover or selected:
            bg, border = _C_BG_HOVER, _C_BORDER_HOVER
        else:
            bg, border = _C_BG, _C_BORDER
        painter.setBrush(bg)
        painter.setPen(QPen(border, 1))
        painter.drawRoundedRect(rect, 10, 10)

        # okładka
        cover_rect = QRect(rect.left() + 12, rect.center().y() - 40, 57, 80)
        pm = self._backend_model_cover(d)
        if pm is not None and not pm.isNull():
            scaled = pm.scaled(57, 80, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            painter.drawPixmap(cover_rect.center() - scaled.rect().center(), scaled)
        else:
            scaled = self._placeholder
            painter.drawPixmap(cover_rect.topLeft(), scaled)

        minus, plus = button_rects(rect)
        text_left = cover_rect.right() + 12
        text_right = minus.left() - 12

        # tytuł (1 linia, elide)
        font = painter.font()
        font.setPixelSize(14)
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(QPen(_C_TEXT))
        title_rect = QRect(text_left, rect.top() + 10, text_right - text_left, 20)
        painter.drawText(
            title_rect,
            Qt.AlignVCenter | Qt.AlignLeft,
            painter.fontMetrics().elidedText(d.title, Qt.ElideRight, title_rect.width()),
        )
        # meta
        font.setPixelSize(11)
        font.setBold(False)
        painter.setFont(font)
        painter.setPen(QPen(_C_TEXT2))
        meta = self._meta_text(d)
        meta_rect = QRect(text_left, title_rect.bottom() + 2, text_right - text_left, 16)
        painter.drawText(
            meta_rect,
            Qt.AlignVCenter | Qt.AlignLeft,
            painter.fontMetrics().elidedText(meta, Qt.ElideRight, meta_rect.width()),
        )
        # progress
        bar = QRect(text_left, rect.bottom() - 18, text_right - text_left, 4)
        painter.setPen(Qt.NoPen)
        painter.setBrush(_C_BAR_BG)
        painter.drawRoundedRect(bar, 2, 2)
        if d.total_episodes > 0:
            ratio = max(0.0, min(1.0, d.current_episode / float(d.total_episodes)))
            w = int(bar.width() * ratio)
            if w > 0:
                painter.setBrush(_C_ACCENT)
                painter.drawRoundedRect(QRect(bar.left(), bar.top(), w, bar.height()), 2, 2)

        # licznik
        font.setPixelSize(14)
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(QPen(_C_TEXT))
        counter = (
            "%d/%d" % (d.current_episode, d.total_episodes)
            if d.total_episodes > 0
            else "%d/—" % d.current_episode
        )
        counter_rect = QRect(minus.left() - 12 - 90, plus.top(), 90, 40)
        painter.drawText(counter_rect, Qt.AlignVCenter | Qt.AlignRight, counter)

        # przyciski − / +
        for btn_rect, px, enabled in (
            (minus, self._remove_px, d.current_episode > 0),
            (
                plus,
                self._add_px,
                not (d.total_episodes > 0 and d.current_episode >= d.total_episodes),
            ),
        ):
            painter.setPen(QPen(border if enabled else _C_BTN_BORDER_DIS, 1))
            painter.setBrush(_C_BTN_BG if enabled else _C_BTN_DIS)
            painter.drawRoundedRect(btn_rect, 20, 20)
            if not enabled:
                painter.setOpacity(0.4)
            painter.drawPixmap(btn_rect.center() - px.rect().center(), px)
            painter.setOpacity(1.0)

    def _meta_text(self, d: Donghua) -> str:
        parts = []
        if d.media_type and d.media_type.value != "unknown":
            parts.append(d.media_type.value.upper())
        if d.start_year:
            parts.append(str(d.start_year))
        parts.append(_STATUS_PL.get(d.status.value, d.status.value))
        return " · ".join(parts)

    def _backend_model_cover(self, d: Donghua):
        model = self._backend.model
        return model.cover_for(d)

    # --- interakcje ---
    def editorEvent(self, event, model, option, index):
        if index.data(KIND_ROLE) == KIND_HEADER:
            if event.type() == QEvent.MouseButtonRelease:
                h = index.data(DATA_ROLE)
                self._backend.headerToggled.emit(h.universe_id)
                return True
            return False
        if index.data(KIND_ROLE) != KIND_ITEM:
            return False
        d = index.data(DATA_ROLE)
        rect = self._card(option.rect)
        minus, plus = button_rects(rect)
        pos = event.position().toPoint() if hasattr(event, "position") else event.pos()
        if event.type() == QEvent.MouseButtonRelease:
            if plus.contains(pos):
                if not (d.total_episodes > 0 and d.current_episode >= d.total_episodes):
                    self._backend.incrementRequested.emit(d.id)
                return True
            if minus.contains(pos):
                if d.current_episode > 0:
                    self._backend.decrementRequested.emit(d.id)
                return True
            return False
        if event.type() == QEvent.MouseButtonDblClick:
            self._backend.detailsRequested.emit(d.id)
            return True
        if event.type() == QEvent.ToolTip:
            if plus.contains(pos):
                QToolTip.showText(event.globalPos(), "Dodaj odcinek")
                return True
            if minus.contains(pos):
                QToolTip.showText(event.globalPos(), "Cofnij odcinek")
                return True
        return super().editorEvent(event, model, option, index)


class DelegateListBackend(ListBackend):
    """QListView + model + delegate: koszt przebudowy niezależny od rozmiaru biblioteki."""

    BACKEND_NAME = "delegate"

    def __init__(self, parent: QWidget = None) -> None:
        super().__init__(parent)
        self.model = _Model(self)
        self._view = QListView(parent)
        self._view.setObjectName("donghuaList")
        self._view.setModel(self.model)
        self._delegate = CardDelegate(self, self._view)
        self._view.setItemDelegate(self._delegate)
        self._view.setSpacing(6)
        self._view.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._view.setVerticalScrollMode(QListView.ScrollPerPixel)
        self._view.setSelectionMode(QListView.SingleSelection)
        self._view.setContentsMargins(8, 8, 8, 8)
        self._view.setContextMenuPolicy(Qt.CustomContextMenu)
        self._view.customContextMenuRequested.connect(self._context_menu)

    # --- API ListBackend ---
    def widget(self) -> QWidget:
        return self._view

    def set_items(self, entries) -> None:
        from app.gui.cover_coordinator import shared_pixmaps

        for url, pm in shared_pixmaps().snapshot():
            self.model._covers.setdefault(url, pm)
        self.model.set_entries(list(entries))

    def update_item(self, d: Donghua) -> None:
        self.model.update(d)

    def remove_item(self, donghua_id: int) -> None:
        self.model.remove(donghua_id)

    def count(self) -> int:
        return sum(
            1
            for i in range(self.model.rowCount())
            if self.model.entry_at(i) is not None
            and not isinstance(self.model.entry_at(i), DisplayHeader)
        )

    def clear(self) -> None:
        self.model.set_entries([])

    def show_skeleton(self, rows: int = 4) -> None:
        self.model.set_entries([None] * max(1, rows))

    def set_cover(self, url: str, pixmap) -> None:
        self.model.set_cover(url, pixmap)

    def row_widget(self, donghua_id: int):
        return None  # brak widgetów wierszy — delegate maluje wszystko

    # --- menu kontekstowe (uniwersa) ---
    def _context_menu(self, pos) -> None:
        index = self._view.indexAt(pos)
        if not index.isValid() or index.data(KIND_ROLE) != KIND_ITEM:
            return
        d = index.data(DATA_ROLE)
        menu = QMenu(self._view)
        up = menu.addAction("Przesuń wyżej w uniwersum")
        down = menu.addAction("Przesuń niżej w uniwersum")
        has = d.universe_id is not None
        up.setEnabled(has)
        down.setEnabled(has)
        chosen = menu.exec_(self._view.viewport().mapToGlobal(pos))
        if chosen is up:
            self.moveRequested.emit(d.id, -1)
        elif chosen is down:
            self.moveRequested.emit(d.id, +1)
