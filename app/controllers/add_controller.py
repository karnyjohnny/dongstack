"""app/controllers/add_controller.py — wyszukiwarka MAL/AniList + Quick Add (M4).

Biblia §15–§24 + specyfikacja §5:
- debounce 450 ms (min. 2 znaki), jedno żądanie na „ciszę” klawiatury,
- stany: IDLE / SEARCHING / RESULTS / NO_RESULTS / ERROR (sygnał stateChanged),
- request_id (R5): stara odpowiedź NIE nadpisuje nowszej; cancel w workerze,
- Quick Add = Planowane + odcinek 0, ZERO formularza; dialog zostaje otwarty
  do seryjnego dodawania (Biblia §24),
- duplikaty: badge „✓ Już w bibliotece”, dodawanie NIEZABLOKOWANE (Biblia §23),
- uniwersa (§5.6): po zapisie dodanej pozycji — LENIWE related_anime (priorytet LOW)
  i sugestia połączenia przez SnackBar; sugestie NIE opóźniają Quick Add.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from PyQt5.QtCore import QObject, QTimer, pyqtSignal

from app.core.logging_setup import get_logger
from app.core.timeutil import utc_now_iso
from app.domain.models import Donghua, SearchItem, Status
from app.gui.theme import STATUS_LABELS as _STATUS_PL
from app.services.universe_service import UniverseSuggester, UniverseSuggestion

log = get_logger("controller.add")


@dataclass(frozen=True)
class _CreateRequest:
    """Żądanie utworzenia uniwersum z jawną listą członków (advanced add)."""

    name: str
    member_ids: Tuple[int, ...]


DEBOUNCE_MS = 450  # Biblia §17
MIN_QUERY_LEN = 2
SEARCH_LIMIT = 20
UNDO_SNACKBAR_MS = 6000


class AddController(QObject):
    """Koordynuje SearchPage ⇄ NetworkWorker  DbWorker (przez sygnały main)."""

    stateChanged = pyqtSignal(str)  # idle|searching|results|no_results|error
    resultsReady = pyqtSignal(list, str)  # items, provider
    searchError = pyqtSignal(object)  # ApiError
    dbAddRequested = pyqtSignal(object, int)  # Donghua, request_id (→ DbWorker)
    replaceLinksRequested = pyqtSignal(int, object, int)  # donghua_id, linki, rid
    editSaveRequested = pyqtSignal(object, object)  # Donghua, linki → DashboardController
    createUniverseRequested = pyqtSignal(str, object, int)  # name, anchor, rid
    attachUniverseRequested = pyqtSignal(int, int, int)  # donghua_id, universe_id, rid
    snackRequested = pyqtSignal(str, str, object)
    addCompleted = pyqtSignal(object)  # zapisana Donghua

    def __init__(
        self, network_worker=None, dashboard_controller=None, parent: Optional[QObject] = None
    ) -> None:
        super().__init__(parent)
        self._net = network_worker
        self._dash = dashboard_controller
        self._rid = 0
        self._last_query = ""
        self._state = "idle"
        self._pending_related: Dict[int, int] = {}  # rid_related → donghua_id
        self._pending_suggest: Dict[int, Donghua] = {}  # rid_related → dodana Donghua
        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(DEBOUNCE_MS)
        self._debounce.timeout.connect(self._fire_search)
        self._pending_create: Dict[int, object] = {}  # rid → UniverseSuggestion|_CreateRequest
        self._pending_links: Dict[int, tuple] = {}  # rid_add → (links, universe_choice)
        if self._net is not None:
            self._net.searchFinished.connect(self.on_search_finished)
            self._net.searchFailed.connect(self.on_search_failed)
            self._net.relatedFinished.connect(self.on_related_finished)

    # --- wejście z UI ----------------------------------------------------------------
    def on_text_changed(self, text: str) -> None:
        self._last_query = (text or "").strip()
        if len(self._last_query) < MIN_QUERY_LEN:
            self._debounce.stop()
            self._set_state("idle")
            return
        self._debounce.start()  # restart debounce (Biblia §17)

    def retry_last(self) -> None:
        if self._last_query:
            self._fire_search()

    def force_search(self) -> None:
        """Enter w polu szukania: natychmiastowe żądanie bez czekania na debounce."""
        self._debounce.stop()
        self._fire_search()

    def _fire_search(self) -> None:
        if not self._last_query:
            return
        prev = self._rid
        self._rid += 1
        if self._net is not None:
            if prev > 0:
                self._net.cancel(prev)  # wyłącznie REALNE starsze rid (R5)
            self._net.enqueue_search(self._last_query, self._rid, SEARCH_LIMIT)
        self._set_state("searching")

    # --- wyniki ------------------------------------------------------------------------
    def on_search_finished(self, rid: int, items: List[SearchItem], provider: str) -> None:
        if rid != self._rid:
            return  # stale odpowiedź (R5)
        if not items:
            self._set_state("no_results")
            self.resultsReady.emit([], provider)
            return
        self._set_state("results")
        self.resultsReady.emit(items, provider)

    def on_search_failed(self, rid: int, err) -> None:
        if rid != self._rid:
            return
        self._set_state("error")
        self.searchError.emit(err)

    def _set_state(self, state: str) -> None:
        if state != self._state:
            self._state = state
            self.stateChanged.emit(state)

    @property
    def state(self) -> str:
        return self._state

    # --- Quick Add (Biblia §24) -----------------------------------------------------------
    def quick_add(self, item: SearchItem) -> None:
        """Biblia §24: Planowane + odcinek 0, zero formularza.

        Feedback M6-fix r5: quick-add pozycji JUŻ żyjącej w bibliotece nie udaje
        dodawania — informuje i odsyła do edycji; świadome nadpisanie zostaje w ⋮.
        """
        if self._dash is not None and item.mal_id is not None:
            existing = self._dash.library_index().get(item.mal_id)
            if existing is not None:
                label = _STATUS_PL.get(existing.status.value, existing.status.value)
                self.snackRequested.emit(
                    "„%s” już jest w bibliotece (%s). Kliknij kartę, aby edytować."
                    % (existing.title, label),
                    "",
                    None,
                )
                return
        self._add_item(
            item, {"status": Status.PLANNED, "episode": 0, "links": [], "universe": None}
        )

    def advanced_add(self, item: SearchItem, form: dict) -> None:
        """Advanced Add (Biblia §25–§28): status/odcinek/linki/uniwersum z formularza."""
        self._add_item(item, form)

    def edit_save(self, d: Donghua, form: dict) -> None:
        """Zapis edycji istniejącej pozycji (AdvancedPage w trybie edycji)."""
        import dataclasses as _dc

        from app.core.timeutil import utc_now_iso as _now

        total = int(form["total"]) if form.get("total") is not None else int(d.total_episodes or 0)
        episode = int(form.get("episode") or d.current_episode)
        episode = max(0, min(episode, total)) if total > 0 else max(0, episode)
        updated = _dc.replace(
            d,
            status=form.get("status") or d.status,
            total_episodes=total,
            current_episode=episode,
            updated_at=_now(),
        )
        links = list(form.get("links") or [])
        self.editSaveRequested.emit(updated, links)
        universe = form.get("universe")
        if universe is not None:
            kind, value = universe
            if kind == "existing":
                self._rid += 1
                self.attachUniverseRequested.emit(updated.id, int(value), self._rid)
            elif kind == "new":
                self._rid += 1
                rid_create = self._rid
                self._pending_create[rid_create] = _CreateRequest(
                    name=str(value), member_ids=(updated.id,)
                )
                self.createUniverseRequested.emit(str(value), updated.mal_id, rid_create)
        if links:
            self._rid += 1
            self.replaceLinksRequested.emit(updated.id, links, self._rid)

    def _add_item(self, item: SearchItem, form: dict) -> None:
        now = utc_now_iso()
        links = list(form.get("links") or [])
        # feedback M6-fix: liczba odcinków edytowalna (MAL: ?? / emisja w toku)
        total = (
            int(form["total"]) if form.get("total") is not None else int(item.total_episodes or 0)
        )
        episode = int(form.get("episode") or 0)
        if total > 0:
            episode = max(0, min(episode, total))
        d = Donghua(
            mal_id=item.mal_id,
            anilist_id=item.ext_id if item.provider == "anilist" and item.mal_id is None else None,
            provider=item.provider,
            title=item.title,
            title_alt=item.title_alt,
            total_episodes=total,
            current_episode=episode,
            status=form.get("status") or Status.PLANNED,
            media_type=item.media_type,
            start_year=item.year,
            cover_key=item.cover_url,  # cover_key przechowuje URL (§4.8, M5)
            added_at=now,
            updated_at=now,
        )
        self._rid += 1
        self._pending_links[self._rid] = (links, form.get("universe"))
        self.dbAddRequested.emit(d, self._rid)

    def on_add_succeeded(self, stored: Donghua, rid: int) -> None:
        self.addCompleted.emit(stored)
        self.snackRequested.emit(
            "Dodano „%s” (%s)" % (stored.title, _STATUS_PL.get(stored.status.value, "")),
            "Cofnij",
            lambda: self._undo_add(stored),
        )
        links, universe_choice = self._pending_links.pop(rid, ([], None))
        if links:
            self._rid += 1
            self.replaceLinksRequested.emit(stored.id, links, self._rid)
        if universe_choice is not None:
            kind, value = universe_choice
            if kind == "existing":
                self._rid += 1
                self.attachUniverseRequested.emit(stored.id, int(value), self._rid)
            elif kind == "new":
                self._rid += 1
                rid_create = self._rid
                self._pending_create[rid_create] = _CreateRequest(
                    name=str(value), member_ids=(stored.id,)
                )
                self.createUniverseRequested.emit(str(value), stored.mal_id, rid_create)
        if stored.mal_id is not None and self._net is not None:
            self._rid += 1
            rid_rel = self._rid
            self._pending_related[rid_rel] = stored.id
            self._pending_suggest[rid_rel] = stored
            self._net.enqueue_related(stored.mal_id, rid_rel)  # LOW, po zapisie (§5.6)

    def _undo_add(self, stored: Donghua) -> None:
        self._rid += 1
        if self._dash is not None:
            self._dash.on_remove_requested(stored.id)

    # --- uniwersa (§5.6) -------------------------------------------------------------------
    def on_related_finished(self, rid: int, mal_id: int, relations: list) -> None:
        stored = self._pending_suggest.pop(rid, None)
        self._pending_related.pop(rid, None)
        if stored is None or self._dash is None:
            return
        suggestion = UniverseSuggester.suggest(
            stored, relations, self._dash.library_index(), self._dash.universes()
        )
        if suggestion is None:
            return
        label = "Połączyć „%s” z uniwersum „%s”?" % (suggestion.new_title, suggestion.universe_name)
        self.snackRequested.emit(label, "Połącz", lambda: self.accept_suggestion(suggestion))

    def accept_suggestion(self, suggestion: UniverseSuggestion) -> None:
        if suggestion.universe_id is not None:
            self._rid += 1
            self.attachUniverseRequested.emit(
                suggestion.new_donghua_id, suggestion.universe_id, self._rid
            )
            return
        self._rid += 1
        rid_create = self._rid
        self._pending_create[rid_create] = suggestion
        self.createUniverseRequested.emit(suggestion.universe_name, None, rid_create)

    def on_universe_created(self, universe_id: int, name: str, rid: int) -> None:
        pending = self._pending_create.pop(rid, None)
        if pending is None:
            return
        if isinstance(pending, UniverseSuggestion):
            member_ids = (pending.new_donghua_id,) + tuple(pending.member_ids)
        else:
            member_ids = tuple(pending.member_ids)
        for donghua_id in member_ids:
            self._rid += 1
            self.attachUniverseRequested.emit(donghua_id, universe_id, self._rid)

    def snackbar_timeout_ms(self) -> int:
        """Spójne API z DashboardController dla main._show_snack (bug produkcyjny M6)."""
        return UNDO_SNACKBAR_MS
