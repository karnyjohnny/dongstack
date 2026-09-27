"""app/gui/settings_dialog.py — first-run / ustawienia MAL Client ID (specyfikacja §5.5).

Jedyny „formularz” poza AdvancedPage: pojawia się RAZ przy pierwszym starcie
(bez Client ID i bez zapisanego „pomiń”) oraz na żądanie z menu Ustawień.
Zapis = live-attach providera MAL bez restartu (MetadataService.attach_provider).
"""

from __future__ import annotations

from typing import Optional

from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QTabWidget,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.gui import theme as _theme

HOWTO_TEXT = (
    "<b>DongStack domyślnie szuka w oficjalnym API MyAnimeList.</b><br>"
    "Client ID jest darmowy i zajmuje ~2 minuty:<br>"
    "1. Zaloguj się na myanimelist.net<br>"
    "2. Account Settings → API → Create ID (typ: web)<br>"
    "3. Wklej poniżej samo <b>Client ID</b> (Client Secret nie jest potrzebny)."
)
SKIP_TEXT = (
    "Możesz też pominąć — wyszukiwanie przejdzie na źródło awaryjne AniList "
    "(bez rejestracji). Client ID ustawisz później w menu ⚙ Ustawienia."
)


class ClientIdDialog(QDialog):
    """Modal settings-dialog: Zapisz (=Accepted) / Pomiń (=Rejected)."""

    def __init__(self, parent: Optional[QWidget] = None, current_id: str = "") -> None:
        super().__init__(parent)
        self.setObjectName("clientIdDialog")
        self.setWindowTitle("DongStack — Client ID MyAnimeList")
        self.setModal(True)
        self.resize(460, 320)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 14)
        layout.setSpacing(10)

        howto = QLabel(HOWTO_TEXT, self)
        howto.setWordWrap(True)
        howto.setTextFormat(Qt.RichText)
        layout.addWidget(howto)

        self._edit = QLineEdit(self)
        self._edit.setObjectName("malClientIdEdit")
        self._edit.setPlaceholderText("np. 2342aaac3213esac31232c2")
        self._edit.setText(current_id or "")
        self._edit.setEchoMode(QLineEdit.Normal)  # Client ID nie jest sekretem (§12)
        layout.addWidget(self._edit)

        skip = QLabel(SKIP_TEXT, self)
        skip.setWordWrap(True)
        skip.setObjectName("metaLabel")
        layout.addWidget(skip)

        buttons = QDialogButtonBox(self)
        self._save = QPushButton("Zapisz i używaj MAL", self)
        self._save.setObjectName("quickAddButton")
        self._save.setDefault(True)
        self._save.setEnabled(bool(current_id))
        self._edit.textChanged.connect(lambda t: self._save.setEnabled(bool(t.strip())))
        buttons.addButton(self._save, QDialogButtonBox.AcceptRole)
        self._skip = QPushButton("Pomiń (AniList)", self)
        buttons.addButton(self._skip, QDialogButtonBox.RejectRole)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    # --- API -----------------------------------------------------------------------
    @property
    def client_id(self) -> str:
        return self._edit.text().strip()

    def showEvent(self, event) -> None:  # noqa: N802 (Qt API)
        super().showEvent(event)
        self._edit.setFocus(Qt.OtherFocusReason)


UNIVERSES_HELP = (
    "Usunięcie uniwersum <b>nie usuwa sezonów</b> — tracą tylko przynależność "
    "(pole „Uniwersum” w edycji zostaje wyczyszczone). Akcję można cofnąć."
)


class SettingsDialog(QDialog):
    """⚙ Ustawienia (r11): Client ID MAL + bezpieczne zarządzanie uniwersami.

    Uniwersa: lista z liczbą sezonów, „Usuń wybrane” = DELETE + FK ON DELETE SET NULL
    (sezony zostają w bibliotece). Undo siedzi w stopce dialogu, bo SnackBar jest
    przykryty oknem modalnym — Biblia §9 (Undo zamiast Confirm) nadal obowiązuje.
    """

    clientIdChanged = pyqtSignal(str)
    deleteUniverseRequested = pyqtSignal(int)  # universe_id
    undoRequested = pyqtSignal()

    UNDO_MS = 8000

    def __init__(
        self,
        parent: Optional[QWidget] = None,
        client_id: str = "",
        universes=None,
        tab: int = 0,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("settingsDialog")
        self.setWindowTitle("DongStack — Ustawienia")
        self.setModal(True)
        self.resize(520, 430)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 12)
        layout.setSpacing(10)

        self._tabs = QTabWidget(self)
        self._tabs.addTab(self._build_api_tab(client_id or ""), "MAL API")
        self._tabs.addTab(self._build_universes_tab(list(universes or [])), "Uniwersa")
        self._tabs.setCurrentIndex(max(0, min(self._tabs.count() - 1, int(tab))))
        layout.addWidget(self._tabs, 1)

        # --- stopka: komunikat + Cofnij + Zamknij -----------------------------------
        footer = QHBoxLayout()
        footer.setSpacing(8)
        self._status = QLabel("", self)
        self._status.setObjectName("metaLabel")
        self._status.setWordWrap(True)
        footer.addWidget(self._status, 1)
        self._undo = QPushButton("Cofnij", self)
        self._undo.setCursor(Qt.PointingHandCursor)
        self._undo.hide()
        self._undo.clicked.connect(self._on_undo)
        footer.addWidget(self._undo)
        self._close = QPushButton("Zamknij", self)
        self._close.setObjectName("quickAddButton")
        self._close.clicked.connect(self.accept)
        footer.addWidget(self._close)
        layout.addLayout(footer)

        self._undo_timer = QTimer(self)
        self._undo_timer.setSingleShot(True)
        self._undo_timer.setInterval(self.UNDO_MS)
        self._undo_timer.timeout.connect(self._hide_undo)

    # --- zakładka: MAL API -----------------------------------------------------------
    def _build_api_tab(self, client_id: str) -> QWidget:
        page = QWidget(self)
        layout = QVBoxLayout(page)
        layout.setContentsMargins(4, 12, 4, 4)
        layout.setSpacing(10)

        howto = QLabel(HOWTO_TEXT, page)
        howto.setWordWrap(True)
        howto.setTextFormat(Qt.RichText)
        layout.addWidget(howto)

        self._cid = QLineEdit(page)
        self._cid.setObjectName("malClientIdEdit")
        self._cid.setPlaceholderText("np. 2342aaac3213esac31232c2")
        self._cid.setText(client_id)
        self._cid.setEchoMode(QLineEdit.Normal)  # Client ID nie jest sekretem (§12)
        layout.addWidget(self._cid)

        note = QLabel(SKIP_TEXT, page)
        note.setWordWrap(True)
        note.setObjectName("metaLabel")
        layout.addWidget(note)

        save = QPushButton("Zapisz i używaj MAL", page)
        save.setObjectName("quickAddButton")
        save.setCursor(Qt.PointingHandCursor)
        save.clicked.connect(self._on_save_client_id)
        layout.addWidget(save, 0, Qt.AlignLeft)
        layout.addStretch(1)
        return page

    def _on_save_client_id(self) -> None:
        cid = self._cid.text().strip()
        if not cid:
            self._set_status("Podaj Client ID (albo zostaw puste i używaj AniList).")
            return
        self.clientIdChanged.emit(cid)
        self._set_status("Zapisano Client ID — wyszukiwanie używa oficjalnego API MAL.")

    # --- zakładka: Uniwersa ----------------------------------------------------------
    def _build_universes_tab(self, universes) -> QWidget:
        page = QWidget(self)
        layout = QVBoxLayout(page)
        layout.setContentsMargins(4, 12, 4, 4)
        layout.setSpacing(10)

        help_label = QLabel(UNIVERSES_HELP, page)
        help_label.setObjectName("metaLabel")
        help_label.setWordWrap(True)
        help_label.setTextFormat(Qt.RichText)
        layout.addWidget(help_label)

        self._tree = QTreeWidget(page)
        self._tree.setObjectName("universesTree")
        self._tree.setHeaderLabels(["Uniwersum", "Sezony"])
        self._tree.setRootIsDecorated(False)
        self._tree.setSelectionMode(QAbstractItemView.SingleSelection)
        self._tree.setUniformRowHeights(True)
        self._tree.header().setStretchLastSection(False)
        self._tree.header().setSectionResizeMode(0, QHeaderView.Stretch)
        self._tree.header().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self._tree.setColumnCount(2)
        self._tree.itemSelectionChanged.connect(self._on_selection_changed)
        layout.addWidget(self._tree, 1)

        self._empty_universes = QLabel(
            "Brak uniwersów. Tworzysz je przy dodawaniu/edycji serii (pole „Uniwersum”).", page
        )
        self._empty_universes.setObjectName("metaLabel")
        self._empty_universes.setWordWrap(True)
        layout.addWidget(self._empty_universes)

        row = QHBoxLayout()
        row.addStretch(1)
        self._delete_universe = QPushButton("Usuń wybrane", page)
        self._delete_universe.setObjectName("deleteButton")
        self._delete_universe.setIcon(_theme.icon("trash"))
        self._delete_universe.setCursor(Qt.PointingHandCursor)
        self._delete_universe.setToolTip(
            "Usuwa uniwersum; przypisane sezony zostają w bibliotece (można cofnąć)"
        )
        self._delete_universe.clicked.connect(self._on_delete_universe)
        row.addWidget(self._delete_universe)
        layout.addLayout(row)

        self.set_universes(universes)
        return page

    def set_universes(self, universes) -> None:
        """universes: List[(Universe, liczba_sezonów)] — odświeżenie listy (r11)."""
        rows = list(universes or [])
        self._tree.clear()
        for uni, count in rows:
            item = QTreeWidgetItem([str(getattr(uni, "name", "") or ""), str(int(count))])
            item.setData(0, Qt.UserRole, int(getattr(uni, "id", 0) or 0))
            item.setTextAlignment(1, Qt.AlignRight | Qt.AlignVCenter)
            item.setToolTip(1, "Przypisane sezony: %d" % int(count))
            self._tree.addTopLevelItem(item)
        self._empty_universes.setVisible(not rows)
        self._delete_universe.setEnabled(False)

    def _on_selection_changed(self) -> None:
        self._delete_universe.setEnabled(self._tree.currentItem() is not None)

    def _on_delete_universe(self) -> None:
        item = self._tree.currentItem()
        if item is None:
            return
        uid = int(item.data(0, Qt.UserRole) or 0)
        name = item.text(0)
        count = item.text(1)
        idx = self._tree.indexOfTopLevelItem(item)
        if idx >= 0:
            self._tree.takeTopLevelItem(idx)  # widok reaguje od razu (Biblia §9)
        self._empty_universes.setVisible(self._tree.topLevelItemCount() == 0)
        self._delete_universe.setEnabled(False)
        self.deleteUniverseRequested.emit(uid)
        self._set_status(
            "Usunięto „%s” (%s). Sezony zostają w bibliotece bez uniwersum." % (name, count),
            undo=True,
        )

    def _on_undo(self) -> None:
        self._hide_undo()
        self.undoRequested.emit()
        self._set_status("Przywrócono uniwersum wraz z przypisanymi sezonami.")

    # --- pomocnicze ------------------------------------------------------------------
    def _set_status(self, text: str, undo: bool = False) -> None:
        self._status.setText(text)
        self._undo.setVisible(undo)
        if undo:
            self._undo_timer.start()
        else:
            self._undo_timer.stop()

    def _hide_undo(self) -> None:
        self._undo_timer.stop()
        self._undo.hide()

    def show_api_tab(self) -> None:
        self._tabs.setCurrentIndex(0)

    def show_universes_tab(self) -> None:
        self._tabs.setCurrentIndex(1)
