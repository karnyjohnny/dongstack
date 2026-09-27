"""app/gui/dashboard/donghua_row.py — karta pozycji biblioteki (Biblia §4–§7).

Kontrakt: wiersz WYŁĄCZNIE emituje zdarzenia; o bazie decyduje kontroler (R1, Biblia §7).
Krytyczna ścieżka `+1` (§6.2 specyfikacji): update_values() dotyka jedynie
setText/setValue istniejących widgetów — bez przebudowy wiersza i bez re-layoutu listy.
"""

from __future__ import annotations

from typing import Optional

from PyQt5.QtCore import QRect, QSize, Qt, pyqtSignal
from PyQt5.QtGui import QColor, QPainter, QPixmap
from PyQt5.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.domain.models import Donghua, Status
from app.gui import theme
from app.gui.dashboard.skeleton import ROW_HEIGHT

_STATUS_PL = {
    Status.WATCHING.value: "w trakcie",
    Status.COMPLETED.value: "obejrzane",
    Status.PLANNED.value: "planowane",
    Status.DROPPED.value: "porzucone",
}

# M9 (§6.7): dwupoziomowe podświetlenie uniwersum hoverem.
# poziom 1 = reszta uniwersum pod kursorem (słaby tint + ćwierć-kryty pasek),
# poziom 2 = karta pod kursorem (mocniejszy tint + pełny pasek akcentu).
_HL_TINT = {1: QColor(179, 157, 219, 14), 2: QColor(179, 157, 219, 26)}
_HL_BAR = {1: QColor(179, 157, 219, 90), 2: QColor(179, 157, 219, 210)}


class DonghuaRow(QFrame):
    """Karta: [okładka] [tytuł/meta/postęp] [licznik − +]. Wysokość stała 96 px."""

    episodeIncrementRequested = pyqtSignal(int)
    episodeDecrementRequested = pyqtSignal(int)
    editRequested = pyqtSignal(int)
    detailsRequested = pyqtSignal(int)
    moveRequested = pyqtSignal(int, int)  # donghua_id, delta (±1) w uniwersum
    hoverStateChanged = pyqtSignal(int, bool)  # donghua_id, kursor wewnątrz?

    def __init__(self, parent: QWidget = None) -> None:
        super().__init__(parent)
        self.setObjectName("donghuaCard")
        self.setFixedHeight(ROW_HEIGHT)
        self._donghua_id: int = 0
        self._full_title: str = ""
        self._universe_id_flag: bool = False
        self._universe_id = None  # M9: do podświetlenia hover
        self._hl = 0  # M9: poziom podświetlenia uniwersum (0/1/2)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(12)

        # --- okładka (72×88, placeholder gdy brak — Biblia §5.2) ----------------
        self._cover = QLabel(self)
        self._cover.setObjectName("coverLabel")
        self._cover.setFixedSize(57, 80)  # ratio 225/318 (feedback UI)
        self._cover.setAlignment(Qt.AlignCenter)
        self._cover.setPixmap(theme.icon("cover_placeholder").pixmap(57, 80))
        layout.addWidget(self._cover)

        # --- info: tytuł (1 linia, elide) / meta / postęp -----------------------
        info = QVBoxLayout()
        info.setContentsMargins(0, 2, 0, 2)
        info.setSpacing(4)

        self._title = QLabel(self)
        self._title.setObjectName("titleLabel")
        info.addWidget(self._title)

        self._meta = QLabel(self)
        self._meta.setObjectName("metaLabel")
        info.addWidget(self._meta)

        self._progress = QProgressBar(self)
        self._progress.setObjectName("progressBar")
        self._progress.setTextVisible(False)
        self._progress.setRange(0, 1)
        self._progress.setValue(0)
        info.addWidget(self._progress)
        info.addStretch(1)

        info_wrapper = QWidget(self)
        info_wrapper.setLayout(info)
        info_wrapper.setStyleSheet("background: transparent;")
        layout.addWidget(info_wrapper, 1)

        # --- akcje: licznik + [−] [+] zawsze widoczne (Biblia §6, §52) -----------
        actions = QHBoxLayout()
        actions.setSpacing(8)

        self._episode = QLabel(self)
        self._episode.setObjectName("episodeLabel")
        self._episode.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        actions.addWidget(self._episode)

        self._minus = QPushButton(self)
        self._minus.setObjectName("minusButton")
        self._minus.setIcon(theme.icon("remove"))
        self._minus.setIconSize(QSize(20, 20))
        self._minus.setToolTip("Cofnij odcinek")
        self._minus.setCursor(Qt.PointingHandCursor)
        self._minus.clicked.connect(self._on_minus)
        actions.addWidget(self._minus)

        self._plus = QPushButton(self)
        self._plus.setObjectName("plusButton")
        self._plus.setIcon(theme.icon("add"))
        self._plus.setIconSize(QSize(20, 20))
        self._plus.setToolTip("Dodaj odcinek")
        self._plus.setCursor(Qt.PointingHandCursor)
        self._plus.clicked.connect(self._on_plus)
        actions.addWidget(self._plus)

        layout.addLayout(actions)

        # menu kontekstowe: ręczna kolejność w uniwersum (§4.9.1 pkt 2)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._context_menu)

    def _context_menu(self, pos) -> None:
        from PyQt5.QtWidgets import QMenu

        menu = QMenu(self)
        up = menu.addAction("Przesuń wyżej w uniwersum")
        down = menu.addAction("Przesuń niżej w uniwersum")
        has_universe = self._universe_id_flag
        up.setEnabled(has_universe)
        down.setEnabled(has_universe)
        chosen = menu.exec_(self.mapToGlobal(pos))
        if chosen is up:
            self.moveRequested.emit(self._donghua_id, -1)
        elif chosen is down:
            self.moveRequested.emit(self._donghua_id, +1)

    # --- API -------------------------------------------------------------------
    @property
    def donghua_id(self) -> int:
        return self._donghua_id

    @property
    def universe_id(self):
        return self._universe_id

    @property
    def universe_hl(self) -> int:
        return self._hl

    def set_universe_hl(self, level: int) -> None:
        """M9: 0=brak, 1=to samo uniwersum co hover, 2=karta pod kursorem."""
        level = max(0, min(2, int(level)))
        if level != self._hl:
            self._hl = level
            self.update()  # tylko repaint karty (bez re-layoutu listy)

    def set_donghua(self, d: Donghua) -> None:
        """Pełne zasilenie (tworzenie wiersza / zmiana zawartości)."""
        self._donghua_id = d.id
        self._cover_url = d.cover_key
        self._universe_id_flag = d.universe_id is not None
        self._universe_id = d.universe_id
        self._full_title = d.title
        self._title.setText(d.title)
        self._meta.setText(self._meta_text(d))
        self._episode.setText(self._episode_text(d))
        self._apply_progress(d)
        self._apply_buttons(d)
        self._relide_title()

    def update_values(self, d: Donghua) -> None:
        """TANIA aktualizacja ścieżki `+1` (§6.2): wyłącznie istniejące widgety."""
        self._donghua_id = d.id
        if d.title != self._full_title:
            self._full_title = d.title
            self._relide_title()
        self._meta.setText(self._meta_text(d))
        self._episode.setText(self._episode_text(d))
        self._apply_progress(d)
        self._apply_buttons(d)

    def set_cover_pixmap(self, pixmap: Optional[QPixmap]) -> None:
        """Pixmap tworzony WYŁĄCZNIE w wątku GUI (R3); None → placeholder."""
        if pixmap is None or pixmap.isNull():
            self._cover.setPixmap(theme.icon("cover_placeholder").pixmap(57, 80))
        else:
            self._cover.setPixmap(
                pixmap.scaled(57, 80, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            )

    # --- wewnętrzne ---------------------------------------------------------------
    @staticmethod
    def _meta_text(d: Donghua) -> str:
        parts = []
        if d.media_type and d.media_type.value != "unknown":
            parts.append(d.media_type.value.upper())
        if d.start_year:
            parts.append(str(d.start_year))
        parts.append(_STATUS_PL.get(d.status.value, d.status.value))
        return " · ".join(parts)

    @staticmethod
    def _episode_text(d: Donghua) -> str:
        if d.total_episodes > 0:
            return "%d/%d" % (d.current_episode, d.total_episodes)
        return "%d/—" % d.current_episode

    def _apply_progress(self, d: Donghua) -> None:
        if d.total_episodes > 0:
            self._progress.setRange(0, d.total_episodes)
            self._progress.setValue(max(0, min(d.current_episode, d.total_episodes)))
        else:
            self._progress.setRange(0, 1)
            self._progress.setValue(0)

    def _apply_buttons(self, d: Donghua) -> None:
        self._minus.setEnabled(d.current_episode > 0)
        at_cap = d.total_episodes > 0 and d.current_episode >= d.total_episodes
        self._plus.setEnabled(not at_cap)

    def _relide_title(self) -> None:
        """Tytuł: dokładnie 1 linia z ElideRight (Biblia §5.1)."""
        fm = self._title.fontMetrics()
        width = self._title.width() if self._title.width() > 20 else 320
        self._title.setText(fm.elidedText(self._full_title, Qt.ElideRight, width))

    def resizeEvent(self, event) -> None:  # noqa: N802 (Qt API)
        super().resizeEvent(event)
        self._relide_title()

    def enterEvent(self, event) -> None:  # noqa: N802 (Qt API)
        if self._donghua_id:
            self.hoverStateChanged.emit(self._donghua_id, True)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802 (Qt API)
        if self._donghua_id:
            self.hoverStateChanged.emit(self._donghua_id, False)
        super().leaveEvent(event)

    def paintEvent(self, event) -> None:  # noqa: N802 (Qt API)
        super().paintEvent(event)  # QSS tło/border karty
        if not self._hl:
            return
        # M9: tint całego uniwersum + pasek akcentu przy lewej krawędzi.
        # Malowane PO tle QSS, POD widgetami potomnymi (cover/labelki/przyciski).
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setPen(Qt.NoPen)
        painter.setBrush(_HL_TINT[self._hl])
        painter.drawRoundedRect(self.rect().adjusted(1, 1, -1, -1), 10, 10)
        painter.setBrush(_HL_BAR[self._hl])
        painter.drawRoundedRect(QRect(1, 10, 3, self.height() - 20), 1, 1)
        painter.end()

    def mousePressEvent(self, event) -> None:  # noqa: N802 (Qt API)
        # klik w kartę (poza przyciskami) = szczegóły/edycja (Biblia §7); M3/M5 podłączy dialog
        if event.button() == Qt.LeftButton and self._donghua_id:
            self.detailsRequested.emit(self._donghua_id)
        super().mousePressEvent(event)

    def _on_plus(self) -> None:
        if self._donghua_id:
            self.episodeIncrementRequested.emit(self._donghua_id)

    def _on_minus(self) -> None:
        if self._donghua_id:
            self.episodeDecrementRequested.emit(self._donghua_id)
