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

from PyQt5.QtCore import QAbstractListModel, QEvent, QModelIndex, QRect, QSize, Qt
from PyQt5.QtGui import QColor, QPainter, QPen
from PyQt5.QtWidgets import (
    QListView,
    QMenu,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QToolTip,
    QWidget,
)

from app.domain.models import Donghua
from app.gui import theme
from app.gui.dashboard.donghua_row import _HL_BAR, _HL_TINT, _STATUS_PL
from app.gui.dashboard.list_backend import ListBackend
from app.gui.dashboard.skeleton import ROW_HEIGHT

KIND_ROLE = Qt.UserRole + 1
DATA_ROLE = Qt.UserRole + 2

KIND_ITEM = "item"
KIND_SKELETON = "skeleton"

_C_BG = QColor("#1E1E1E")
_C_BG_HOVER = QColor("#242424")
_C_BORDER = QColor("#303030")
_C_BORDER_HOVER = QColor("#444444")
_C_TEXT = QColor("#E6E1E5")
_C_TEXT2 = QColor("#A0A0A0")
_C_TEXT3 = QColor("#707070")
_C_ALT = QColor("#8A8A8A")  # r11: tytuł alternatywny (spójnie z QLabel#altLabel)
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
            return KIND_ITEM
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


def card_text_rects(rect: QRect, text_left: int, text_right: int, has_alt: bool) -> dict:
    """Geometria linii tekstowych karty (r11: doszła linia tytułu alternatywnego).

    Funkcja czysta — dokładnie te same prostokąty, które maluje CardDelegate,
    więc testy mogą weryfikować układ bez analizy pikseli. Odpowiednik layoutu
    widgetowej DonghuaRow (tytuł / alt / meta / pasek postępu).
    """
    width = max(0, int(text_right) - int(text_left))
    title = QRect(text_left, rect.top() + 9, width, 18)
    alt = QRect(text_left, title.bottom() + 1, width, 13) if has_alt else None
    anchor = alt if alt is not None else title
    meta = QRect(text_left, anchor.bottom() + 1, width, 14)
    bar = QRect(text_left, rect.bottom() - 18, width, 4)
    return {"title": title, "alt": alt, "meta": meta, "bar": bar}


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
        return QSize(0, ROW_HEIGHT)  # M9: jednolita wysokość (bug r7: mix sizeHint)

    # --- malowanie ---
    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex):
        kind = index.data(KIND_ROLE)
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, True)
        rect = self._card(option.rect)
        if kind == KIND_SKELETON:
            self._paint_skeleton(painter, rect)
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
        # M9: dwupoziomowe podświetlenie uniwersum (spójne z kartą widgetową)
        hl = self._backend.hover_level(d)
        if hl:
            painter.setPen(Qt.NoPen)
            painter.setBrush(_HL_TINT[hl])
            painter.drawRoundedRect(rect.adjusted(1, 1, -1, -1), 10, 10)
            painter.setBrush(_HL_BAR[hl])
            painter.drawRoundedRect(
                QRect(rect.left() + 1, rect.top() + 10, 3, rect.height() - 20), 1, 1
            )

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
        rects = card_text_rects(rect, text_left, text_right, bool((d.title_alt or "").strip()))
        title_rect = rects["title"]
        painter.drawText(
            title_rect,
            Qt.AlignVCenter | Qt.AlignLeft,
            painter.fontMetrics().elidedText(d.title, Qt.ElideRight, title_rect.width()),
        )
        # QoL r11: tytuł alternatywny (mniejsza czcionka, jak w karcie widgetowej)
        alt_rect = rects["alt"]
        if alt_rect is not None:
            font.setPixelSize(10)
            font.setBold(False)
            painter.setFont(font)
            painter.setPen(QPen(_C_ALT))
            painter.drawText(
                alt_rect,
                Qt.AlignVCenter | Qt.AlignLeft,
                painter.fontMetrics().elidedText(
                    (d.title_alt or "").strip(), Qt.ElideRight, alt_rect.width()
                ),
            )
        # meta
        font.setPixelSize(11)
        font.setBold(False)
        painter.setFont(font)
        painter.setPen(QPen(_C_TEXT2))
        meta = self._meta_text(d)
        meta_rect = rects["meta"]
        painter.drawText(
            meta_rect,
            Qt.AlignVCenter | Qt.AlignLeft,
            painter.fontMetrics().elidedText(meta, Qt.ElideRight, meta_rect.width()),
        )
        # progress
        bar = rects["bar"]
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
        # M9: hover → podświetlenie całego uniwersum (mousemove na viewporcie)
        self._hover_uni = None
        self._hover_id = None
        self._view.setMouseTracking(True)
        self._view.viewport().setMouseTracking(True)
        self._view.viewport().installEventFilter(self)

    # --- podświetlenie uniwersum (M9, §6.7) ---------------------------------------
    def hover_level(self, d: Donghua) -> int:
        if self._hover_uni is not None and d.universe_id == self._hover_uni:
            return 2 if d.id == self._hover_id else 1
        return 0

    def set_universe_hover(self, universe_id, donghua_id) -> None:
        universe_id = int(universe_id) if universe_id is not None else None
        donghua_id = int(donghua_id) if donghua_id is not None else None
        if (universe_id, donghua_id) == (self._hover_uni, self._hover_id):
            return
        self._hover_uni, self._hover_id = universe_id, donghua_id
        self._view.viewport().update()  # repaint wyłącznie widocznych kart

    def universe_at_pos(self, pos):
        index = self._view.indexAt(pos)
        if not index.isValid():
            return None, None
        entry = self.model.entry_at(index.row())
        if isinstance(entry, Donghua):
            return entry.universe_id, entry.id
        return None, None

    def eventFilter(self, obj, event):  # noqa: N802 (Qt API)
        etype = event.type()
        if etype == QEvent.MouseMove:
            uid, did = self.universe_at_pos(event.pos())
            self.set_universe_hover(uid, did)
        elif etype == QEvent.Leave:
            self.set_universe_hover(None, None)
        return False

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
        return sum(1 for i in range(self.model.rowCount()) if self.model.entry_at(i) is not None)

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
