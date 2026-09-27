"""app/controllers/dashboard_controller.py — stan biblioteki i ścieżka `+1` (M3).

Zasady (specyfikacja §3.1, §6.2, Biblia §8–§12):
- biblioteka trzymana W PAMIĘCI kontrolera (load raz, asynchronicznie z DbWorker);
  filtry/sort/lokalne szukanie operują na liście w pamięci w wątku GUI (Biblia §13),
- OPTYMISTYCZNY update: klik `+` mutuje stan i widok natychmiast (<8 ms, gate G2);
  zapis idzie kolejką do DbWorker; ack potwierdza, nack robi ROLLBACK do ostatniego
  potwierdzonego stanu + SnackBar „Nie udało się zapisać zmiany.” (Biblia §9),
- auto-ukończenie (Biblia §10): watching→completed przy max + SnackBar z Undo,
- Undo zamiast Confirm: stos komend (domain.undo), 1 aktywna akcja na SnackBar,
- request_id (R5): stale ack/nack (starszy request_id dla id) są ignorowane,
- GUI nie zna SQL ani modeli zapisu: widok subskrybuje sygnały kontrolera.
"""

from __future__ import annotations

import dataclasses
import time
from typing import Dict, List, Optional

from PyQt5.QtCore import QObject, pyqtSignal

from app.core.logging_setup import get_logger
from app.core.timeutil import utc_now_iso
from app.domain.models import Donghua, SortMode, Status, Universe
from app.domain.undo import UndoCommand, UndoStack
from app.gui.theme import STATUS_LABELS

log = get_logger("controller.dashboard")

UNDO_SNACKBAR_MS = 6000


class DashboardController(QObject):
    """Mediator między MainWindow a DbWorker (bez Qt-widgetów w środku)."""

    # --- do widoku ------------------------------------------------------------------
    itemsChanged = pyqtSignal(list)  # pełna wymiana widocznej listy
    itemChanged = pyqtSignal(object)  # aktualizacja 1 wiersza (Donghua)
    countsChanged = pyqtSignal(dict)  # badge'e sidebara
    universesChanged = pyqtSignal(dict)  # rejestr uniwersów (M5: grupowanie)
    coversRequested = pyqtSignal(list)  # widoczne wpisy → CoverCoordinator
    editRequestedFull = pyqtSignal(object, object)  # Donghua + linki → AdvancedPage (edycja)
    snackRequested = pyqtSignal(str, str, object)  # tekst, etykieta akcji, callback|None
    addRequested = pyqtSignal()  # M4: otwarcie AddDialog

    # --- do DbWorker (połączenia kolejkuje Qt — różne wątki) --------------------------
    saveEpisodeRequested = pyqtSignal(int, int, str, int)  # id, episode, status, rid
    softDeleteRequested = pyqtSignal(int, int)
    restoreRequested = pyqtSignal(int, int)
    saveFullRequested = pyqtSignal(object, object, int)  # Donghua, linki, rid
    saveUniverseOrderRequested = pyqtSignal(int, int, int)  # id, order, rid
    updateCoverKeyRequested = pyqtSignal(int, str, int)  # id, cover_url, rid
    backfillRequested = pyqtSignal(int, int)  # donghua_id, mal_id

    def __init__(
        self,
        worker: Optional[QObject] = None,
        parent: Optional[QObject] = None,
        initial_status: str = "watching",
        initial_sort: SortMode = SortMode.UPDATED,
    ) -> None:
        super().__init__(parent)
        self._items: Dict[int, Donghua] = {}  # stan bieżący (optymistyczny)
        self._confirmed: Dict[int, Donghua] = {}  # ostatni stan potwierdzony przez DB
        self._inflight: Dict[int, int] = {}  # id → najnowszy request_id
        self._seq = 0
        self._undo = UndoStack()
        # start: pamiętany filtr (QoL) lub „W trakcie” przy pierwszym uruchomieniu
        self._status = initial_status if initial_status in STATUS_LABELS else "watching"
        self._text = ""
        self._sort = initial_sort
        self._universes: Dict[int, Universe] = {}
        self._backfill_done = set()  # id bez cover_key już zgłoszone
        self._relations: Dict[int, list] = {}  # mal_id → relacje (sesja, §4.9)
        self._links: Dict[int, list] = {}  # donghua_id → List[StreamingLink]
        self._worker = worker
        if worker is not None:
            worker.libraryLoaded.connect(self.on_library_loaded)
            worker.universesLoaded.connect(self.on_universes_loaded)
            worker.universeCreated.connect(self.on_universe_created)
            worker.universeAttached.connect(self.on_universe_attached)
            worker.linksLoaded.connect(self.on_links_loaded)
            worker.fullSaved.connect(self._on_full_ok)
            worker.fullFailed.connect(self._on_full_fail)
            worker.saveSucceeded.connect(self._on_save_ok)
            worker.saveFailed.connect(self._on_save_fail)
            self.saveEpisodeRequested.connect(worker.saveEpisode)
            self.softDeleteRequested.connect(worker.softDelete)
            self.restoreRequested.connect(worker.restore)
            self.saveFullRequested.connect(worker.saveFull)
            self.saveUniverseOrderRequested.connect(worker.saveUniverseOrder)

    # ================================================================== LOAD / DEMO
    def on_library_loaded(self, rows: List[Donghua]) -> None:
        self._items = {d.id: d for d in rows}
        self._confirmed = dict(self._items)
        self._refresh()
        self.countsChanged.emit(self.counts())

    def on_universes_loaded(self, universes) -> None:
        self._universes = {u.id: u for u in universes}
        self.universesChanged.emit(dict(self._universes))

    def on_universe_created(self, universe_id: int, name: str, request_id: int) -> None:
        self._universes[universe_id] = Universe(id=universe_id, name=name, created_at=utc_now_iso())
        self.universesChanged.emit(dict(self._universes))

    def on_universe_attached(self, donghua_id: int, universe_id: int, request_id: int) -> None:
        current = self._items.get(donghua_id)
        if current is not None and current.universe_id != universe_id:
            updated = dataclasses.replace(current, universe_id=universe_id)
            self._items[donghua_id] = updated
            self._confirmed[donghua_id] = updated
            self.itemChanged.emit(updated)
            self._refresh()

    # --- indeksy dla UniverseService / AddController (§5.6) -------------------------
    def library_index(self) -> Dict[int, Donghua]:
        """mal_id → Donghua (tylko pozycje z mal_id; O(1) dla sugestii uniwersów)."""
        return {d.mal_id: d for d in self._items.values() if d.mal_id is not None}

    def universes(self) -> Dict[int, Universe]:
        return dict(self._universes)

    def universe_name(self, universe_id: int) -> str:
        uni = self._universes.get(universe_id)
        return uni.name if uni is not None else ""

    def load_demo(self, rows: List[Donghua]) -> None:
        """Tryb --demo / testy: dane w pamięci bez workera bazy."""
        self.on_library_loaded(rows)

    def on_add_completed(self, stored) -> None:
        """Zapisana pozycja trafia do stanu w pamięci (badge duplikatów, indeks MAL)."""
        self._items[stored.id] = stored
        self._confirmed[stored.id] = stored
        self._refresh()
        self.countsChanged.emit(self.counts())

    def on_links_loaded(self, links: Dict[int, list]) -> None:
        self._links = dict(links)

    def links_for(self, donghua_id: int) -> list:
        return list(self._links.get(donghua_id, []))

    def register_relations(self, mal_id: int, relations: list) -> None:
        """Graf relacji z related_anime (sesja) — wejście watch_order (§4.9)."""
        self._relations[int(mal_id)] = list(relations)

    # ================================================================== STAN WIDOKU
    @property
    def status_filter(self) -> str:
        return self._status

    @property
    def sort_mode(self) -> SortMode:
        return self._sort

    def counts(self) -> Dict[str, int]:
        counts = {"all": 0, "watching": 0, "completed": 0, "planned": 0, "dropped": 0}
        for d in self._items.values():
            counts["all"] += 1
            key = d.status.value
            if key in counts:
                counts[key] += 1
        return counts

    def visible_items(self) -> List[Donghua]:
        text = self._text.strip().lower()
        out: List[Donghua] = []
        for d in self._items.values():
            if self._status != "all" and d.status.value != self._status:
                continue
            if text and text not in d.title.lower() and text not in (d.title_alt or "").lower():
                continue
            out.append(d)
        out.sort(key=self._sort_key, reverse=self._sort_reverse())
        return out

    def _sort_reverse(self) -> bool:
        return self._sort in (
            SortMode.UPDATED,
            SortMode.ADDED,
            SortMode.PROGRESS,
            SortMode.WATCH_ORDER,
        )

    def _sort_key(self, d: Donghua):
        if self._sort == SortMode.ALPHA:
            return (d.title or "").lower()
        if self._sort == SortMode.ADDED:
            return d.added_at
        if self._sort == SortMode.PROGRESS:
            return (d.progress_ratio, d.updated_at)
        # UPDATED oraz WATCH_ORDER (grupowanie uniwersów dochodzi w M5, §6.7)
        return d.updated_at

    def set_status_filter(self, status: str) -> None:
        if status == self._status:
            return
        self._status = status
        self._refresh()

    def set_search(self, text: str) -> None:
        self._text = text or ""
        self._refresh()

    def set_sort(self, mode: str) -> None:
        try:
            self._sort = SortMode(mode)
        except ValueError:
            return
        self._refresh()

    def _refresh(self) -> None:
        entries = self.visible_entries()
        self.itemsChanged.emit(entries)
        visible = [e for e in entries if isinstance(e, Donghua)]
        self.coversRequested.emit(visible)
        # backfill okładek dla starych pozycji (mal_id jest, cover_key brak)
        for d in visible:
            if d.mal_id is not None and not d.cover_key and d.id not in self._backfill_done:
                self._backfill_done.add(d.id)
                self.backfillRequested.emit(d.id, d.mal_id)

    def on_backfill_cover(self, donghua_id: int, cover_url: str) -> None:
        current = self._items.get(donghua_id)
        if current is None or current.cover_key:
            return
        updated = dataclasses.replace(current, cover_key=cover_url)
        self._items[donghua_id] = updated
        self._confirmed[donghua_id] = updated
        if self._worker is not None:
            self.updateCoverKeyRequested.emit(donghua_id, cover_url, self._next_rid())
        self.coversRequested.emit([updated])

    # ================================================================== UNIWERSA (§6.7 M9)
    def visible_entries(self) -> list:
        """Display-model M9: ZAWSZE płaska lista kart (bez zwijanych nagłówków).

        Feedback produkcyjny r7: nagłówki grup o innej wysokości niż karta
        + QListWidget.uniformItemSizes = rozjazd layoutu (luki/nakładanie).
        Sort WATCH_ORDER: bloki uniwersów stoją obok siebie (watch order
        wewnątrz bloku), potem tytuły bez uniwersum; przynależność pokazuje
        dwupoziomowe podświetlenie hover (kursor = mocne, reszta uniwersum = słabe).
        """
        visible = self.visible_items()
        if self._sort != SortMode.WATCH_ORDER:
            return visible
        by_uni: Dict[int, List[Donghua]] = {}
        free: List[Donghua] = []
        for d in visible:
            if d.universe_id is not None:
                by_uni.setdefault(d.universe_id, []).append(d)
            else:
                free.append(d)
        entries: list = []
        ordered_unis = sorted(
            by_uni.items(),
            key=lambda kv: max(m.updated_at for m in kv[1]),
            reverse=True,
        )
        for _uid, members in ordered_unis:
            entries.extend(self._order_universe(members))
        entries.extend(free)
        return entries

    def _order_universe(self, members: List[Donghua]) -> List[Donghua]:
        from app.services.watch_order import order_universe

        ids = {m.mal_id for m in members if m.mal_id is not None}
        relations = {
            mid: [(other, rel) for other, rel in rels if other in ids]
            for mid, rels in self._relations.items()
            if mid in ids
        }
        return order_universe(members, relations, warn=log.warning)

    def move_in_universe(self, donghua_id: int, delta: int) -> None:
        """Ręczny override kolejności (↑/↓ w menu kontekstowym wiersza)."""
        current = self._items.get(donghua_id)
        if current is None or current.universe_id is None:
            return
        members = [d for d in self._items.values() if d.universe_id == current.universe_id]
        ordered = self._order_universe(members)
        ids = [m.id for m in ordered]
        if donghua_id not in ids:
            return
        idx = ids.index(donghua_id)
        target = idx + delta
        if target < 0 or target >= len(ids):
            return
        ids[idx], ids[target] = ids[target], ids[idx]
        by_id = {m.id: m for m in members}
        for pos, mid in enumerate(ids):
            order = (pos + 1) * 10
            replaced = dataclasses.replace(by_id[mid], universe_order=order)
            self._items[mid] = replaced
            self._confirmed[mid] = replaced
            if self._worker is not None:
                self.saveUniverseOrderRequested.emit(mid, order, self._next_rid())
        self._refresh()

    # ================================================================== EDYCJA (AdvancedPage)
    def on_details(self, donghua_id: int) -> None:
        current = self._items.get(donghua_id)
        if current is not None:
            self.editRequestedFull.emit(current, self.links_for(donghua_id))

    def on_advanced_save(self, d: Donghua, links: list) -> None:
        """Optymistyczny pełny zapis (edycja / advanced add istniejącej pozycji)."""
        self._items[d.id] = d
        self._links[d.id] = list(links)
        rid = self._next_rid()
        self._inflight[d.id] = rid
        self._refresh()
        self.countsChanged.emit(self.counts())
        if self._worker is not None:
            self.saveFullRequested.emit(d, list(links), rid)

    def _on_full_ok(self, d, rid: int) -> None:
        if self._inflight.get(d.id) == rid:
            self._confirmed[d.id] = d
            self._inflight.pop(d.id, None)

    def _on_full_fail(self, donghua_id: int, rid: int, message: str) -> None:
        if self._inflight.get(donghua_id) != rid:
            return
        self._inflight.pop(donghua_id, None)
        confirmed = self._confirmed.get(donghua_id)
        if confirmed is not None and self._items.get(donghua_id) != confirmed:
            self._items[donghua_id] = confirmed
            self._refresh()
        log.warning("rollback saveFull id=%d: %s", donghua_id, message)
        self.snackRequested.emit("Nie udało się zapisać zmiany.", "", None)

    # ================================================================== ŚCIEŻKA `+1`
    def on_increment(self, donghua_id: int) -> None:
        self._apply_episode_delta(donghua_id, +1)

    def on_decrement(self, donghua_id: int) -> None:
        self._apply_episode_delta(donghua_id, -1)

    def _apply_episode_delta(self, donghua_id: int, delta: int) -> None:
        current = self._items.get(donghua_id)
        if current is None:
            return
        target = current.current_episode + delta
        if target < 0 or (current.total_episodes > 0 and target > current.total_episodes):
            return  # przyciski i tak są disabled — obrona przed skrótami/kolejką
        new = current.with_episode(target, utc_now_iso())
        if new == current:
            return
        completed_now = new.status == Status.COMPLETED and current.status != Status.COMPLETED
        self._items[donghua_id] = new
        rid = self._next_rid()
        self._inflight[donghua_id] = rid
        self._undo.push(
            UndoCommand(
                kind="episode",
                payload={"id": donghua_id, "prev": current, "new": new},
                label="Cofnij",
            )
        )
        self.itemChanged.emit(new)
        self.countsChanged.emit(self.counts())
        if completed_now:
            self.snackRequested.emit(
                "Oznaczono „%s” jako ukończone" % new.title,
                "Cofnij",
                self.undo_last,
            )
        if self._worker is not None:
            self.saveEpisodeRequested.emit(donghua_id, new.current_episode, new.status.value, rid)

    # ================================================================== ACK / NACK
    def _next_rid(self) -> int:
        self._seq += 1
        return self._seq

    def _on_save_ok(self, donghua_id: int, request_id: int) -> None:
        if self._inflight.get(donghua_id) != request_id:
            return  # stale ack (R5)
        current = self._items.get(donghua_id)
        if current is not None:
            self._confirmed[donghua_id] = current
        self._inflight.pop(donghua_id, None)

    def _on_save_fail(self, donghua_id: int, request_id: int, message: str) -> None:
        if self._inflight.get(donghua_id) != request_id:
            return  # stale nack (R5)
        self._inflight.pop(donghua_id, None)
        confirmed = self._confirmed.get(donghua_id)
        if confirmed is None:
            return
        rolled = self._items.get(donghua_id)
        if rolled is not None and rolled != confirmed:
            self._items[donghua_id] = confirmed
            self.itemChanged.emit(confirmed)
            self.countsChanged.emit(self.counts())
        log.warning("rollback zapisu id=%d: %s", donghua_id, message)
        self.snackRequested.emit("Nie udało się zapisać zmiany.", "", None)

    # ================================================================== REMOVE (Undo add)
    def on_remove_requested(self, donghua_id: int) -> None:
        """Optymistyczne usunięcie (soft-delete w DB; Undo przywraca)."""
        current = self._items.pop(int(donghua_id), None)
        if current is None:
            return
        self._confirmed.pop(int(donghua_id), None)
        self._inflight.pop(int(donghua_id), None)
        self._undo.push(UndoCommand(kind="remove", payload={"prev": current}, label="Cofnij"))
        self._refresh()
        self.countsChanged.emit(self.counts())
        self.snackRequested.emit(
            "Usunięto „%s” z biblioteki" % current.title, "Cofnij", self.undo_last
        )
        if self._worker is not None:
            self.softDeleteRequested.emit(int(donghua_id), self._next_rid())

    # ================================================================== UNDO
    def undo_last(self) -> None:
        cmd = self._undo.pop()
        if cmd is None:
            return
        if cmd.kind == "remove":
            prev = cmd.get("prev")
            if prev is None:
                return
            self._items[prev.id] = prev
            self._confirmed[prev.id] = prev
            self._refresh()
            self.countsChanged.emit(self.counts())
            if self._worker is not None:
                self.restoreRequested.emit(prev.id, self._next_rid())
            return
        if cmd.kind == "episode":
            prev = cmd.get("prev")
            if prev is None or prev.id not in self._items:
                return
            self._items[prev.id] = prev
            rid = self._next_rid()
            self._inflight[prev.id] = rid
            self.itemChanged.emit(prev)
            self.countsChanged.emit(self.counts())
            if self._worker is not None:
                self.saveEpisodeRequested.emit(
                    prev.id, prev.current_episode, prev.status.value, rid
                )

    # ================================================================== RESZTA ZDARZEŃ
    def on_add_clicked(self) -> None:
        self.addRequested.emit()  # M4: MainWindow otwiera AddDialog

    def shutdown(self) -> None:
        self._undo.clear()

    # ================================================================== POMOCNICZE
    def item(self, donghua_id: int) -> Optional[Donghua]:
        return self._items.get(donghua_id)

    def snackbar_timeout_ms(self) -> int:
        return UNDO_SNACKBAR_MS

    def status_label(self) -> str:
        return STATUS_LABELS.get(self._status, "Wszystkie")

    @staticmethod
    def perf_now() -> float:
        """Do pomiarów gate G2 w testach (p95 handlera `+1`)."""
        return time.perf_counter()
