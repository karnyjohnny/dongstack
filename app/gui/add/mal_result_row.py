"""app/gui/add/mal_result_row.py — wiersz wyniku wyszukiwania (Biblia §22–§24).

Metadane pierwszego poziomu: rok · typ · liczba odcinków. Bez rankingu/synopsis/
gatunków (poziom 2). Duplikat: badge „✓ Już w bibliotece” + przygaszone tło,
ale dodawanie NIEZABLOKOWANE (Biblia §23).
"""

from __future__ import annotations

from typing import Optional

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from app.domain.models import SearchItem
from app.gui import theme


class MalResultRow(QFrame):
    quickAddRequested = pyqtSignal(object)  # SearchItem
    advancedRequested = pyqtSignal(object)  # SearchItem

    def __init__(self, parent: QWidget = None) -> None:
        super().__init__(parent)
        self.setObjectName("malResultCard")
        self.setFixedHeight(76)
        self._item: Optional[SearchItem] = None

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(10)

        self._cover = QLabel(self)
        self._cover.setObjectName("coverLabel")
        self._cover.setFixedSize(44, 62)  # ratio 225/318 (feedback UI)
        self._cover.setAlignment(Qt.AlignCenter)
        self._cover.setPixmap(theme.icon("cover_placeholder").pixmap(44, 62))
        layout.addWidget(self._cover)

        info = QVBoxLayout()
        info.setContentsMargins(0, 0, 0, 0)
        info.setSpacing(3)
        self._title = QLabel(self)
        self._title.setObjectName("titleLabel")
        info.addWidget(self._title)
        self._alt = QLabel(self)
        self._alt.setObjectName("metaLabel")
        info.addWidget(self._alt)
        self._meta = QLabel(self)
        self._meta.setObjectName("metaLabel")
        info.addWidget(self._meta)
        wrapper = QWidget(self)
        wrapper.setLayout(info)
        wrapper.setStyleSheet("background: transparent;")
        layout.addWidget(wrapper, 1)

        self._badge = QLabel("✓ Już w bibliotece", self)
        self._badge.setObjectName("inLibraryBadge")
        self._badge.hide()
        layout.addWidget(self._badge)

        self._advanced = QToolButton(self)
        self._advanced.setObjectName("advancedButton")
        self._advanced.setIcon(theme.icon("more"))
        self._advanced.setToolTip("Opcje zaawansowane (status, odcinek, linki, uniwersum)")
        self._advanced.setCursor(Qt.PointingHandCursor)
        self._advanced.clicked.connect(self._on_advanced)
        layout.addWidget(self._advanced)

        self._add = QPushButton(self)
        self._add.setObjectName("quickAddButton")
        self._add.setIcon(theme.icon("add"))
        self._add.setToolTip("Dodaj (Planowane, odcinek 0)")
        self._add.setCursor(Qt.PointingHandCursor)
        self._add.clicked.connect(self._on_add)
        layout.addWidget(self._add)

    # --- API ---------------------------------------------------------------------
    def set_item(self, item: SearchItem) -> None:
        self._item = item
        self._title.setText(item.title)
        self._alt.setText(item.title_alt or "")
        self._alt.setVisible(bool(item.title_alt))
        meta = []
        if item.year:
            meta.append(str(item.year))
        if item.media_type and item.media_type.value != "unknown":
            meta.append(item.media_type.value.upper())
        meta.append("%d odc." % item.total_episodes if item.total_episodes else "??? odc.")
        self._meta.setText(" · ".join(meta))

    def set_cover_pixmap(self, pixmap) -> None:
        """Pixmap tworzony WYŁĄCZNIE w wątku GUI (R3); None → placeholder."""
        if pixmap is None or pixmap.isNull():
            self._cover.setPixmap(theme.icon("cover_placeholder").pixmap(44, 62))
        else:
            self._cover.setPixmap(
                pixmap.scaled(44, 62, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            )

    def set_in_library(self, in_library: bool) -> None:
        self.setProperty("inLibrary", bool(in_library))
        self._badge.setVisible(bool(in_library))
        style = self.style()
        style.unpolish(self)
        style.polish(self)

    def _on_add(self) -> None:
        if self._item is not None:
            self.quickAddRequested.emit(self._item)

    def _on_advanced(self) -> None:
        if self._item is not None:
            self.advancedRequested.emit(self._item)
