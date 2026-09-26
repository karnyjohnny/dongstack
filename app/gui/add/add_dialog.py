"""app/gui/add/add_dialog.py — AddDialog: QDialog + QStackedWidget (Biblia §15, §25).

M5: SearchPage + AdvancedPage (status/odcinek/linki/uniwersum; tryb add i edycji).
Non-modal (`show()`, nie `exec_()`) — seryjne dodawanie bez zamykania (Biblia §24).
"""

from __future__ import annotations

from typing import Dict, List, Optional

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QKeySequence
from PyQt5.QtWidgets import (
    QApplication,
    QDialog,
    QLineEdit,
    QShortcut,
    QSpinBox,
    QStackedWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.domain.models import Donghua, SearchItem, StreamingLink, Universe
from app.gui.add.advanced_page import AdvancedPage
from app.gui.add.search_page import SearchPage
from app.gui.add.streaming_links import tag_from_url


class AddDialog(QDialog):
    advancedSaveRequested = pyqtSignal(object, object)  # SearchItem, form dict
    advancedEditSaveRequested = pyqtSignal(object, object)  # Donghua, form dict
    deleteRequested = pyqtSignal(int)  # donghua_id → soft-delete + Undo (Biblia §9)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("addDialog")
        self.setWindowTitle("Dodaj donghua")
        self.resize(640, 600)
        self.setModal(False)
        # Qt.Tool: pomocnicze okno ZAWSZE nad rodzicem (na Windows potrafiło
        # otwierać się za MainWindow = wrażenie „brak reakcji” po kliknięciu FAB)
        self.setWindowFlags(Qt.Tool | Qt.WindowCloseButtonHint)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.stack = QStackedWidget(self)
        self.search_page = SearchPage(self)
        self.advanced_page = AdvancedPage(self)
        self.stack.addWidget(self.search_page)  # index 0
        self.stack.addWidget(self.advanced_page)  # index 1
        layout.addWidget(self.stack)

        self.advanced_page.backRequested.connect(self.show_search)
        self.advanced_page.saveRequested.connect(self._on_advanced_save)
        self.advanced_page.deleteRequested.connect(self.deleteRequested)
        self._universes: Dict[int, Universe] = {}
        self._current_item: Optional[SearchItem] = None

        # QoL (feedback M6-fix r4): Ctrl+V z URL-em w schowku = nowy wiersz linku,
        # ale TYLKO gdy focus nie siedzi w polu edycji (wtedy zwykłe wklejenie).
        self._paste = QShortcut(QKeySequence("Ctrl+V"), self)
        self._paste.setContext(Qt.WindowShortcut)
        self._paste.activated.connect(self._on_paste_url)

    # --- API -----------------------------------------------------------------------
    def set_universes(self, universes: Dict[int, Universe]) -> None:
        self._universes = dict(universes)

    def show_search(self) -> None:
        self.stack.setCurrentIndex(0)

    def open(self) -> None:
        """Otwarcie = czyste pole + focus natychmiast (Biblia §16, feedback M6-fix)."""
        self.setWindowTitle("Dodaj donghua")
        self.show_search()
        self.search_page.line_edit.clear()  # reset poprzedniego zapytania i stanu
        self.search_page.show_idle()
        self.show()
        self.raise_()
        self.activateWindow()
        self.search_page.focus_input()

    def open_advanced(self, item: SearchItem) -> None:
        self.setWindowTitle("Dodaj donghua — opcje zaawansowane")
        self._current_item = item
        self.advanced_page.load_from_item(item, self._universes)
        self.stack.setCurrentIndex(1)

    def open_advanced_edit(self, d: Donghua, links: List[StreamingLink]) -> None:
        self.setWindowTitle("Edytuj: %s" % d.title)
        self.advanced_page.load_from_donghua(d, links, self._universes)
        self.stack.setCurrentIndex(1)
        self.show()
        self.raise_()

    @staticmethod
    def _url_like(text: str) -> bool:
        if not text:
            return False
        if text.startswith(("http://", "https://")):
            return True
        return bool(tag_from_url(text))

    def _on_paste_url(self) -> None:
        if self.stack.currentIndex() != 1:
            return  # linki istnieją tylko na AdvancedPage
        focus = QApplication.focusWidget()
        if isinstance(focus, (QLineEdit, QTextEdit, QSpinBox)):
            return  # zwykłe Ctrl+V w polu ma pierwszeństwo
        text = QApplication.clipboard().text().strip()
        if not self._url_like(text):
            return
        self.advanced_page.links.add_row(url=text)

    def _on_advanced_save(self) -> None:
        form = self.advanced_page.form()
        editing = form.pop("editing", None)
        if editing is not None:
            self.advancedEditSaveRequested.emit(editing, form)
            self.close()  # edycja: zapis kończy dialog (feedback M6-fix)
        else:
            self.advancedSaveRequested.emit(self._current_item, form)
            self.show_search()  # add: dialog zostaje do seryjnego dodawania (Biblia §24)

    def keyPressEvent(self, event) -> None:  # noqa: N802 (Qt API)
        # Esc: najpierw powrót z advanced, potem zamknięcie dialogu
        if event.key() == Qt.Key_Escape and self.stack.currentIndex() != 0:
            self.show_search()
            return
        super().keyPressEvent(event)
