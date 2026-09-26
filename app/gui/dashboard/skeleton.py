"""app/gui/dashboard/skeleton.py — placeholder ładowania bez pustego ekranu.

Biblia §21, §38 + rygor 18 zadania: skeleton DOMYŚLNIE STATYCZNY (lekki rendering
> efektowna animacja). Bloki dokładnie jeden poziom jaśniejsze od powierzchni karty.
"""

from __future__ import annotations

from PyQt5.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

ROW_HEIGHT = 96  # wspólna wysokość wiersza listy (uniformItemSizes, §6.3)


class SkeletonRow(QFrame):
    """Statyczny szkielet karty donghua: [cover] + 3 bloki tekstu + kółko akcji."""

    def __init__(self, parent: QWidget = None) -> None:
        super().__init__(parent)
        self.setObjectName("donghuaSkeleton")
        self.setFixedHeight(ROW_HEIGHT)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(12)

        cover = QFrame(self)
        cover.setObjectName("skeletonBlock")
        cover.setFixedSize(57, 80)  # ratio 225/318
        layout.addWidget(cover)

        info = QVBoxLayout()
        info.setSpacing(8)
        title = QFrame(self)
        title.setObjectName("skeletonBlock")
        title.setFixedHeight(14)
        title.setMinimumWidth(220)
        info.addWidget(title)
        meta = QFrame(self)
        meta.setObjectName("skeletonBlock")
        meta.setFixedHeight(10)
        meta.setMinimumWidth(140)
        info.addWidget(meta)
        progress = QFrame(self)
        progress.setObjectName("skeletonBlock")
        progress.setFixedHeight(4)
        progress.setMinimumWidth(180)
        info.addWidget(progress)
        info.addStretch(1)
        wrapper = QWidget(self)
        wrapper.setLayout(info)
        wrapper.setStyleSheet("background: transparent;")
        layout.addWidget(wrapper, 1)

        action = QFrame(self)
        action.setObjectName("skeletonBlock")
        action.setFixedSize(40, 40)
        layout.addWidget(action)

        # etykieta-niewidka dla dostępności (screen readery)
        self._a11y = QLabel("Wczytywanie…", self)
        self._a11y.hide()
