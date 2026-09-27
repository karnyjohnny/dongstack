"""app/gui/add/advanced_page.py — Advanced Add / edycja (Biblia §25–§28, §6.7).

QFormLayout: segmentowy wybór statusu (QButtonGroup, 4×QPushButton checkable),
QSpinBox odcinka, liczba odcinków (0 = „—”, emisja w toku), notatka użytkownika,
StreamingLinksWidget, wybór uniwersum (istniejące / „Utwórz nowe…” / „Brak”),
pasek akcji Wstecz/Zapisz.

Feedback r11 (E5500, mały ekran 1366×768):
- FIX: cała sekcja pól + linków siedzi w QScrollArea, więc +10 linków (albo
  notatka) nie wypycha okna poza ekran; pasek akcji zostaje PRZYPNIĘTY na dole,
- BUG: gdy total_episodes = 0 (MAL/AniList: „??” albo sezon jeszcze nie wyszedł)
  sufit spinboksa odcinka był 0 → nie dało się wpisać postępu, a wczytana
  wartość z bazy była clampowana do 0 („w dashboard rośnie, w edycji dalej 0”).
  Teraz 0 = brak limitu (sufit EPISODE_OPEN_CEILING),
- QoL: tytuł alternatywny pod tytułem (jak w wynikach wyszukiwania) + notatka
  („numeracja na CDA = 52 + odcinek sezonu” itp.) nad linkami streamingowymi.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from app.domain.models import (
    Donghua,
    MediaType,
    SearchItem,
    Status,
    StreamingLink,
    Universe,
)
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

# r11: total_episodes == 0 znaczy „nieznane / w emisji” — progres wtedy NIE ma
# limitu (użytkownik wie lepiej niż baza). Sufit techniczny spinboksa:
EPISODE_OPEN_CEILING = 9999

# M9: wybór typu we wpisie ręcznym (PPM na FABie)
_MEDIA_CHOICES = [
    ("Nieznany", MediaType.UNKNOWN),
    ("TV", MediaType.TV),
    ("ONA", MediaType.ONA),
    ("OVA", MediaType.OVA),
    ("Film", MediaType.MOVIE),
    ("Special", MediaType.SPECIAL),
    ("Music", MediaType.MUSIC),
]


class AdvancedPage(QWidget):
    backRequested = pyqtSignal()
    saveRequested = pyqtSignal()
    deleteRequested = pyqtSignal(int)  # donghua_id (tylko tryb edycji)
    coverPreviewRequested = pyqtSignal(str)  # M9: url okładki do podglądu (worker!)

    def __init__(self, parent: QWidget = None) -> None:
        super().__init__(parent)
        self._manual = False  # jawna flaga trybu (nie zależymy od isVisible — r11)
        self._editing: Optional[Donghua] = None
        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 16, 16, 12)
        outer.setSpacing(10)

        # --- nagłówek: PRZYPNIĘTY (poza scrollem), żeby tytuł był zawsze widoczny ---
        self._title = QLabel("", self)
        self._title.setObjectName("advancedTitle")
        self._title.setWordWrap(True)
        outer.addWidget(self._title)

        # QoL r11: tytuł alternatywny pod tytułem (mniejsza czcionka, jak w wynikach)
        self._alt_title = QLabel("", self)
        self._alt_title.setObjectName("altLabel")
        self._alt_title.setWordWrap(True)
        self._alt_title.hide()
        outer.addWidget(self._alt_title)

        # --- FIX r11: reszta formularza w QScrollArea (mały ekran + dużo linków) ----
        self._scroll = QScrollArea(self)
        self._scroll.setObjectName("advancedScroll")
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._scroll.setStyleSheet("QScrollArea#advancedScroll{background:transparent;}")
        # FIX r12: NIE ustawiamy stylesheetu bez selektora na viewporcie!
        # `viewport().setStyleSheet("background:transparent;")` w Qt działa jak
        # `* { background: transparent }` na WSZYSTKICH potomków (konflikt resolution:
        # stylesheet bliższy widgetowi wygrywa z app-QSS bez względu na specyficzność)
        # → pola formularza traciły tła z QSS, a QPushButton#statusSegment regułę
        # background → QStyleSheetStyle oddawał rysowanie natywnemu motywowi Windows
        # (aero: ciemnoniebieski/fioletowy fill checked/pressed — feedback r12).
        # Viewport QScrollArea i tak nie wypełnia tła sam z siebie.
        self._scroll.viewport().setAutoFillBackground(False)
        self._scroll.setMinimumHeight(220)
        inner = QWidget(self._scroll)
        inner.setObjectName("advancedInner")
        inner.setStyleSheet("QWidget#advancedInner{background:transparent;}")
        self._inner = QVBoxLayout(inner)
        self._inner.setContentsMargins(0, 0, 4, 0)
        self._inner.setSpacing(12)
        self._scroll.setWidget(inner)
        outer.addWidget(self._scroll, 1)

        # --- M9: pola wpisu ręcznego (PPM na FABie); ukryte poza trybem manual ---
        self._manual_box = QWidget(inner)
        mform = QFormLayout(self._manual_box)
        mform.setContentsMargins(0, 0, 0, 0)
        mform.setSpacing(10)
        self._m_title = QLineEdit(self._manual_box)
        self._m_title.setPlaceholderText("Nazwa serii (wymagana)")
        self._m_title.textChanged.connect(lambda _t: self._m_title.setStyleSheet(""))
        mform.addRow("Tytuł *", self._m_title)
        self._m_title_alt = QLineEdit(self._manual_box)
        self._m_title_alt.setPlaceholderText("Opcjonalnie: tytuł oryginalny / alt")
        mform.addRow("Tytuł alt.", self._m_title_alt)
        self._m_year = QSpinBox(self._manual_box)
        self._m_year.setRange(0, 2100)
        self._m_year.setSpecialValueText("brak")
        self._m_year.setFixedWidth(90)
        mform.addRow("Rok", self._m_year)
        self._m_media = QComboBox(self._manual_box)
        for label, value in _MEDIA_CHOICES:
            self._m_media.addItem(label, value)
        mform.addRow("Typ", self._m_media)
        cover_row = QWidget(self._manual_box)
        cover_layout = QHBoxLayout(cover_row)
        cover_layout.setContentsMargins(0, 0, 0, 0)
        cover_layout.setSpacing(8)
        self._m_cover = QLineEdit(cover_row)
        self._m_cover.setPlaceholderText("https://… (jpg/png) — podgląd pobierze worker")
        self._m_cover.textChanged.connect(self._on_cover_text)
        cover_layout.addWidget(self._m_cover, 1)
        self._cover_preview = QLabel(cover_row)
        self._cover_preview.setObjectName("coverLabel")
        self._cover_preview.setFixedSize(57, 80)
        self._cover_preview.setAlignment(Qt.AlignCenter)
        self._cover_preview.setPixmap(_theme.icon("cover_placeholder").pixmap(57, 80))
        cover_layout.addWidget(self._cover_preview)
        mform.addRow("Okładka URL", cover_row)
        self._manual_box.hide()
        self._inner.addWidget(self._manual_box)
        self._cover_requester = None  # fn(pairs) → CoverCoordinator.request_pairs (R1/R3)
        self._cover_debounce = QTimer(self)
        self._cover_debounce.setSingleShot(True)
        self._cover_debounce.setInterval(600)
        self._cover_debounce.timeout.connect(self._request_cover_preview)

        form = QFormLayout()
        form.setSpacing(10)

        # --- status: segmentowy wybór (Biblia §26) ---
        status_row = QWidget(inner)
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
            status_layout.addWidget(btn, 1)  # r12: równe szerokości (bold nie rusza geometrii)
        form.addRow("Status", status_row)

        # --- odcinek (Biblia §27) ---
        self._episode = QSpinBox(inner)
        self._episode.setRange(0, EPISODE_OPEN_CEILING)  # r11: 0 odcinków ≠ blokada
        self._episode.setFixedWidth(90)
        form.addRow("Aktualny odcinek", self._episode)

        # --- liczba odcinków (feedback M6-fix): MAL bywa ?? / emisja w toku ---
        self._total = QSpinBox(inner)
        self._total.setRange(0, 9999)
        self._total.setSpecialValueText("—")  # r11: krótko i spójnie z dashboardem
        self._total.setFixedWidth(130)
        self._total.setToolTip("„—” = liczba odcinków nieznana lub seria w emisji")
        self._total.valueChanged.connect(self._on_total_changed)
        form.addRow("Liczba odcinków", self._total)

        # --- uniwersum (§6.7) ---
        self._universe = QComboBox(inner)
        self._universe.addItem("Brak", NO_UNIVERSE)
        self._universe.addItem("— Utwórz nowe…", NEW_UNIVERSE)
        form.addRow("Uniwersum", self._universe)
        self._new_universe = QLineEdit(inner)
        self._new_universe.setPlaceholderText("Nazwa uniwersum (franczyzy)…")
        self._new_universe.hide()
        self._new_universe.textChanged.connect(self._on_new_universe_text)
        form.addRow("", self._new_universe)
        self._universe.currentIndexChanged.connect(self._on_universe_index)

        self._inner.addLayout(form)

        # --- QoL r11: notatka własna (nad linkami); kolumna donghua.note istnieje od v1
        note_label = QLabel("Notatka (dla siebie — np. numeracja odcinków na stronie)", inner)
        note_label.setObjectName("metaLabel")
        self._inner.addWidget(note_label)
        self._note = QPlainTextEdit(inner)
        self._note.setObjectName("noteEdit")
        self._note.setPlaceholderText(
            "np. „na CDA numeracja = 52 + nr odcinka tego sezonu”; pole opcjonalne"
        )
        self._note.setFixedHeight(64)
        self._note.setTabChangesFocus(True)  # Tab wychodzi z pola (nie wstawia tabulatora)
        self._inner.addWidget(self._note)

        # --- linki streamingowe (Biblia §28) ---
        links_label = QLabel("Linki streamingowe  [TAG] [URL]", inner)
        links_label.setObjectName("metaLabel")
        self._inner.addWidget(links_label)
        self.links = StreamingLinksWidget(inner)
        self._inner.addWidget(self.links, 0)
        self._inner.addStretch(1)  # reszta luzu NA DOLE: sekcje trzymają się góry

        # --- akcje: PRZYPNIĘTE pod scrollem (zawsze widoczne, FIX r11) ---
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
        self._editing = None
        self._manual = False
        self._delete.hide()
        self._back.show()
        self._manual_box.hide()
        self._title.show()
        self._title.setText(item.title)
        self._set_alt_title(item.title_alt)
        total = max(0, int(item.total_episodes or 0))
        self._total.setValue(total)
        self._set_episode_ceiling(total)
        self._episode.setValue(0)
        self._set_status(Status.PLANNED)
        self._note.setPlainText("")
        self.links.set_links([])
        self._load_universes(universes, None)
        self._scroll_to_top()

    def load_from_donghua(
        self, d: Donghua, links: List[StreamingLink], universes: Dict[int, Universe]
    ) -> None:
        self._editing = d
        self._delete.show()
        manual = (d.provider or "manual") == "manual"
        self._manual = manual
        self._back.setVisible(not manual)  # M9: ręczna edycja nie ma „wstecz” do szukajki
        self._manual_box.setVisible(manual)
        self._title.setVisible(not manual)
        if manual:  # M9: ręczny wpis — tytuł/rok/typ/okładka edytowalne
            self._m_title.setText(d.title)
            self._m_title_alt.setText(d.title_alt or "")
            self._m_year.setValue(int(d.start_year or 0))
            idx = self._m_media.findData(d.media_type)
            self._m_media.setCurrentIndex(max(0, idx))
            self._m_cover.setText(d.cover_key or "")
            self._set_cover_preview(d.cover_key)
        self._title.setText(d.title)
        # alt tytuł: w trybie ręcznym edytowalny w polu _m_title_alt (bez duplikatu)
        self._set_alt_title(None if manual else d.title_alt)
        total = max(0, int(d.total_episodes or 0))
        self._total.setValue(total)
        self._set_episode_ceiling(total)  # PRZED setValue — inaczej clamp do 0 (bug r11)
        self._episode.setValue(max(0, int(d.current_episode or 0)))
        self._set_status(d.status)
        self._note.setPlainText(d.note or "")
        self.links.set_links(links)
        self._load_universes(universes, d.universe_id)
        self._scroll_to_top()

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

    # --- r11: sufit odcinka + alt tytuł + notatka -----------------------------------
    def _set_episode_ceiling(self, total: int) -> None:
        """total > 0 = twardy limit; total == 0 = „nieznane” → limit techniczny."""
        ceiling = int(total) if int(total) > 0 else EPISODE_OPEN_CEILING
        self._episode.setMaximum(ceiling)
        self._episode.setToolTip(
            "" if ceiling != EPISODE_OPEN_CEILING else "Liczba odcinków nieznana — brak limitu"
        )

    def _on_total_changed(self, value: int) -> None:
        self._set_episode_ceiling(int(value))
        if int(value) > 0 and self._episode.value() > int(value):
            self._episode.setValue(int(value))

    def _set_alt_title(self, text) -> None:
        text = str(text).strip() if text else ""
        if text:
            self._alt_title.setText(text)
            self._alt_title.show()
        else:
            self._alt_title.clear()
            self._alt_title.hide()

    def note_text(self) -> str:
        return self._note.toPlainText().strip()

    def _scroll_to_top(self) -> None:
        self._scroll.verticalScrollBar().setValue(0)

    # --- M9: tryb ręczny + podgląd okładki ------------------------------------------
    def set_cover_requester(self, fn) -> None:
        """fn(pairs: List[(url, mal_id)]) — kolejka LOW NetworkWorkera (R1: nie w GUI)."""
        self._cover_requester = fn

    def apply_cover_preview(self, url: str, pixmap) -> None:
        if url != self._m_cover.text().strip():
            return  # odpowiedź dla innego urla (R5-ish: ignoruj stare podglądy)
        self._set_cover_preview(url, pixmap)

    def _set_cover_preview(self, url, pixmap=None) -> None:
        if pixmap is None and url:
            from app.gui.cover_coordinator import shared_pixmaps

            pixmap = shared_pixmaps().get(str(url))
        if pixmap is None or pixmap.isNull():
            self._cover_preview.setPixmap(_theme.icon("cover_placeholder").pixmap(57, 80))
        else:
            self._cover_preview.setPixmap(
                pixmap.scaled(57, 80, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            )

    def _on_cover_text(self, _text: str) -> None:
        self._cover_preview.setPixmap(_theme.icon("cover_placeholder").pixmap(57, 80))
        self._cover_debounce.start()

    def _request_cover_preview(self) -> None:
        url = self._m_cover.text().strip()
        if url.startswith(("http://", "https://")):
            self.coverPreviewRequested.emit(url)
            if self._cover_requester is not None:
                self._cover_requester([(url, 0)])

    def load_manual(self, universes: Dict[int, Universe]) -> None:
        """M9: czysty formularz ręczny (seria bez strony na MAL/AniList)."""
        self._editing = None
        self._manual = True
        self._delete.hide()
        self._back.hide()  # nie ma wyszukiwarki „w tyle” — Esc zamyka dialog
        self._manual_box.show()
        self._title.hide()
        self._set_alt_title(None)
        self._m_title.setText("")
        self._m_title_alt.setText("")
        self._m_year.setValue(0)
        self._m_media.setCurrentIndex(0)
        self._m_cover.setText("")
        self._cover_preview.setPixmap(_theme.icon("cover_placeholder").pixmap(57, 80))
        self._total.setValue(0)
        self._set_episode_ceiling(0)
        self._episode.setValue(0)
        self._set_status(Status.PLANNED)
        self._note.setPlainText("")
        self.links.set_links([])
        self._load_universes(universes, None)
        self._scroll_to_top()

    def manual_mode(self) -> bool:
        return self._manual

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
        manual = self.manual_mode()
        return {
            "status": status,
            "episode": episode,
            "total": total,
            "links": self.links.get_links(),
            "universe": universe,
            "editing": self._editing,
            "manual": manual,
            "note": self.note_text() or None,
            "title": self._m_title.text().strip() if manual else "",
            "title_alt": (self._m_title_alt.text().strip() or None) if manual else None,
            "start_year": (self._m_year.value() or None) if manual else None,
            "media_type": self._m_media.currentData() if manual else None,
            "cover_url": (self._m_cover.text().strip() or None) if manual else None,
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
        # M9: ręczny wpis bez tytułu = zapis wstrzymany + czerwona ramka (Biblia §26)
        if self.manual_mode() and not self._m_title.text().strip():
            self._m_title.setStyleSheet("border: 1px solid #C62828;")
            self._m_title.setFocus()
            return
        self.saveRequested.emit()
