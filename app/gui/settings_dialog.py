"""app/gui/settings_dialog.py — first-run / ustawienia MAL Client ID (specyfikacja §5.5).

Jedyny „formularz” poza AdvancedPage: pojawia się RAZ przy pierwszym starcie
(bez Client ID i bez zapisanego „pomiń”) oraz na żądanie z menu Ustawień.
Zapis = live-attach providera MAL bez restartu (MetadataService.attach_provider).
"""

from __future__ import annotations

from typing import Optional

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

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
