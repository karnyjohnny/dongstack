"""app/gui/add/streaming_links.py — wiersze linków [TAG][URL] (feedback M6-fix).

Zamiast sztywnego comboboxa platform: dwa pola tekstowe. Po wklejeniu URL TAG
uzupełnia się NA ŻYWO z domeny (netloc), z możliwością ręcznej nadpisowni
(np. „reikoproject.blogspot.com” → ręcznie „reikoproject”).
"""

from __future__ import annotations

from typing import List
from urllib.parse import urlparse

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from app.domain.models import StreamingLink
from app.gui import theme


def tag_from_url(url: str) -> str:
    """https://naszeanime.pl/anime/x → naszeanime.pl (bez www.)."""
    try:
        netloc = urlparse(url.strip()).netloc or ""
    except ValueError:
        return ""
    if not netloc and "://" not in url:
        netloc = urlparse("//" + url.strip()).netloc or ""
    netloc = netloc.split("@")[-1].split(":")[0]
    if netloc.startswith("www."):
        netloc = netloc[4:]
    if " " in netloc or "." not in netloc:
        return ""  # to nie wygląda na domenę
    return netloc


class _LinkRow(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("streamingLinkRow")
        self._tag_manual = False
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 2, 0, 2)
        layout.setSpacing(6)

        self.tag = QLineEdit(self)
        self.tag.setPlaceholderText("TAG")
        self.tag.setFixedWidth(150)
        self.tag.textEdited.connect(self._on_tag_edited)
        layout.addWidget(self.tag)

        self.url = QLineEdit(self)
        self.url.setPlaceholderText("https://…")
        self.url.textChanged.connect(self._on_url_changed)
        layout.addWidget(self.url, 1)

        self.remove = QToolButton(self)
        self.remove.setIcon(theme.icon("remove"))
        self.remove.setToolTip("Usuń link")
        layout.addWidget(self.remove)

    def _on_tag_edited(self, _text: str) -> None:
        self._tag_manual = True

    def _on_url_changed(self, url: str) -> None:
        if self._tag_manual:
            return
        auto = tag_from_url(url)
        if auto:
            self.tag.blockSignals(True)
            self.tag.setText(auto)
            self.tag.blockSignals(False)


class StreamingLinksWidget(QWidget):
    """Dynamiczna lista linków + przycisk dodania (Biblia §28, wersja M6-fix)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(4)
        self._layout.setAlignment(Qt.AlignTop)
        self._rows: List[_LinkRow] = []
        # przycisk ZAWSZE na górze sekcji, w stałym miejscu (feedback UI M6-fix r4)
        self._add = QPushButton("Dodaj link", self)
        self._add.setFixedWidth(160)
        self._add.clicked.connect(lambda: self.add_row())
        self._layout.addWidget(self._add)

    def add_row(self, tag: str = "", url: str = "") -> None:
        row = _LinkRow(self)
        if tag:
            row.tag.setText(tag)
            row._tag_manual = True
        if url:
            row.url.setText(url)
            if not tag:
                row.tag.setText(tag_from_url(url))
        row.remove.clicked.connect(lambda _=False, r=row: self._remove(r))
        self._rows.append(row)
        self._layout.addWidget(row)  # wiersze od góry do dołu pod przyciskiem

    def _remove(self, row: _LinkRow) -> None:
        if row in self._rows:
            self._rows.remove(row)
            self._layout.removeWidget(row)
            row.setParent(None)
            row.deleteLater()

    def set_links(self, links: List[StreamingLink]) -> None:
        for row in list(self._rows):
            self._remove(row)
        for link in links:
            self.add_row(link.tag, link.url)

    def get_links(self) -> List[StreamingLink]:
        out: List[StreamingLink] = []
        for pos, row in enumerate(self._rows):
            url = row.url.text().strip()
            if not url:
                continue
            out.append(
                StreamingLink(
                    tag=row.tag.text().strip() or tag_from_url(url), url=url, position=pos
                )
            )
        return out
