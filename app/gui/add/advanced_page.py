"""app/gui/add/advanced_page.py — Advanced Add / edycja (Biblia §25–§28, §6.7).

QFormLayout: segmentowy wybór statusu (QButtonGroup, 4×QPushButton checkable),
QSpinBox odcinka (0..total), StreamingLinksWidget, wybór uniwersum
(istniejące / „Utwórz nowe…” / „Brak”), pasek akcji Wstecz/Zapisz.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from app.domain.models import Donghua, SearchItem, Status, StreamingLink, Universe
from app.gui import theme as _theme
from app.gui.add.streaming_links import StreamingLinksWidget

_STATUS_ORDER = [Status.WATCHING, Status.COMPLETED, Status.PLANNED, Status.DROPPED]
_STATUS_PL = {
    Status.WATCHING: "W trakcie",
    Status.COMPLETED: "Obejrzane",
    Status.PLANNED: "Planowane",
    Status.DROPPED: "Porzucone",
}
NEW_UNIVERSE = "__new__"
NO_UNIVERSE = "__none__"


class AdvancedPage(QWidget):
    backRequested = pyqtSignal()
    saveRequested = pyqtSignal()
    deleteRequested = pyqtSignal(int)  # donghua_id (tylko tryb edycji)

    def __init__(self, parent: QWidget = None) -> None:
        super().__init__(parent)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 16, 16, 12)
        outer.setSpacing(12)

        self._title = QLabel("", self)
        self._title.setObjectName("advancedTitle")
        self._title.setWordWrap(True)
        outer.addWidget(self._title)

        form = QFormLayout()
        form.setSpacing(10)

        # --- status: segmentowy wybór (Biblia §26) ---
        status_row = QWidget(self)
        status_layout = QHBoxLayout(status_row)
        status_layout.setContentsMargins(0, 0, 0, 0)
        status_layout.setSpacing(6)
        self._status_group = QButtonGroup(status_row)
        self._status_group.setExclusive(True)
        self._status_buttons = {}
        for status in _STATUS_ORDER:
            btn = QPushButton(_STATUS_PL[status], status_row)
            btn.setObjectName("statusSegment")
            btn.setProperty("status", status.value)  # QSS: kolor jak kropka statusu
            btn.setCheckable(True)
            btn.setCursor(Qt.PointingHandCursor)
            self._status_group.addButton(btn)
            self._status_buttons[status] = btn
            status_layout.addWidget(btn)
        form.addRow("Status", status_row)

        # --- odcinek (Biblia §27) ---
        self._episode = QSpinBox(self)
        self._episode.setRange(0, 0)
        self._episode.setFixedWidth(90)
        form.addRow("Aktualny odcinek", self._episode)

        # --- liczba odcinków (feedback M6-fix): MAL bywa ?? / emisja w toku ---
        self._total = QSpinBox(self)
        self._total.setRange(0, 9999)
        self._total.setSpecialValueText("nieznane / w emisji")
        self._total.setFixedWidth(130)
        self._total.setToolTip("0 = nieznane lub seria w trakcie emisji")
        form.addRow("Liczba odcinków", self._total)

        # --- uniwersum (§6.7) ---
        self._universe = QComboBox(self)
        self._universe.addItem("Brak", NO_UNIVERSE)
        self._universe.addItem("— Utwórz nowe…", NEW_UNIVERSE)
        form.addRow("Uniwersum", self._universe)
        self._new_universe = QLineEdit(self)
        self._new_universe.setPlaceholderText("Nazwa uniwersum (franczyzy)…")
        self._new_universe.hide()
        self._new_universe.textChanged.connect(self._on_new_universe_text)
        form.addRow("", self._new_universe)
        self._universe.currentIndexChanged.connect(self._on_universe_index)

        outer.addLayout(form)

        # --- linki streamingowe (Biblia §28) ---
        links_label = QLabel("Linki streamingowe  [TAG] [URL]", self)
        links_label.setObjectName("metaLabel")
        outer.addWidget(links_label)
        self.links = StreamingLinksWidget(self)
        outer.addWidget(self.links, 0)
        outer.addStretch(1)  # reszta luzu NA DOLE: sekcje trzymają się góry

        # --- akcje ---
        actions = QHBoxLayout()
        self._delete = QPushButton("Usuń", self)
        self._delete.setObjectName("deleteButton")
        self._delete.setIcon(_theme.icon("trash"))
        self._delete.setToolTip("Usuń z biblioteki (Cofnij dostępne w SnackBarze)")
        self._delete.setCursor(Qt.PointingHandCursor)
        self._delete.hide()  # widoczny tylko w trybie edycji
        self._delete.clicked.connect(self._on_delete)
        actions.addWidget(self._delete)
        actions.addStretch(1)
        self._back = QPushButton("Wstecz", self)
        self._back.clicked.connect(self._on_back)
        actions.addWidget(self._back)
        self._save = QPushButton("Zapisz", self)
        self._save.setObjectName("quickAddButton")
        self._save.clicked.connect(self._on_save)
        actions.addWidget(self._save)
        outer.addLayout(actions)

    # --- ładowanie -------------------------------------------------------------------
    def load_from_item(self, item: SearchItem, universes: Dict[int, Universe]) -> None:
        self._editing: Optional[Donghua] = None
        self._delete.hide()
        self._title.setText(item.title)
        self._episode.setMaximum(max(0, item.total_episodes))
        self._episode.setValue(0)
        self._total.setValue(max(0, item.total_episodes))
        self._set_status(Status.PLANNED)
        self.links.set_links([])
        self._load_universes(universes, None)

    def load_from_donghua(
        self, d: Donghua, links: List[StreamingLink], universes: Dict[int, Universe]
    ) -> None:
        self._editing = d
        self._delete.show()
        self._title.setText(d.title)
        self._episode.setMaximum(max(0, d.total_episodes))
        self._episode.setValue(d.current_episode)
        self._total.setValue(max(0, d.total_episodes))
        self._set_status(d.status)
        self.links.set_links(links)
        self._load_universes(universes, d.universe_id)

    def _load_universes(self, universes: Dict[int, Universe], current: Optional[int]) -> None:
        self._universe.blockSignals(True)
        while self._universe.count() > 2:
            self._universe.removeItem(2)
        for uid in sorted(universes, key=lambda u: universes[u].name.lower()):
            self._universe.addItem(universes[uid].name, uid)
        target = 0
        if current is not None:
            idx = self._universe.findData(current)
            target = idx if idx >= 0 else 0
        self._universe.setCurrentIndex(target)
        self._universe.blockSignals(False)
        self._new_universe.hide()

    # --- formularz ---------------------------------------------------------------------
    def form(self) -> dict:
        status = next(s for s, b in self._status_buttons.items() if b.isChecked())
        data = self._universe.currentData()
        if data == NEW_UNIVERSE:
            universe = ("new", self._new_universe.text().strip() or "Nowe uniwersum")
        elif data == NO_UNIVERSE or data is None:
            universe = None
        else:
            universe = ("existing", int(data))
        total = self._total.value()
        episode = self._episode.value()
        if total > 0:
            episode = min(episode, total)
        return {
            "status": status,
            "episode": episode,
            "total": total,
            "links": self.links.get_links(),
            "universe": universe,
            "editing": self._editing,
        }

    # --- sloty ---------------------------------------------------------------------------
    def _set_status(self, status: Status) -> None:
        for s, btn in self._status_buttons.items():
            btn.setChecked(s == status)

    def _on_universe_index(self, _idx: int) -> None:
        self._new_universe.setVisible(self._universe.currentData() == NEW_UNIVERSE)

    def _on_new_universe_text(self, _text: str) -> None:
        pass  # walidacja przy zapisie (pusta → nazwa domyślna)

    def _on_back(self) -> None:
        self.backRequested.emit()

    def _on_delete(self) -> None:
        if self._editing is not None:
            self.deleteRequested.emit(self._editing.id)

    def _on_save(self) -> None:
        self.saveRequested.emit()
