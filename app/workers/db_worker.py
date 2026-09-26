"""app/workers/db_worker.py — DbWorker: JEDYNY właściciel połączenia SQLite (R2).

Topologia (specyfikacja §3.1, §4.6):
- worker żyje w osobnym QThread (singleton sesyjny, R6), połączenie tworzone
  W tym wątku (check_same_thread domyślne),
- komendy przychodzą sygnałami (kolejkowane między wątkami),
- KOALESCENCJA zapisów postępu (R10): kliknięcia szybsze niż 250 ms dla tego
  samego id scalają się do jednego UPDATE/fsync; operacje nieprogresowe
  (add/remove/restore) wykonują się natychmiast,
- ack/nack: saveSucceeded / saveFailed(id, request_id, msg) → kontroler
  potwierdza stan lub robi rollback optymistyczny + SnackBar (Biblia §9),
- start: recovery + migracje + load biblioteki (GUI pokazuje w tym czasie skeleton),
- zamknięcie: flush → wal_checkpoint(TRUNCATE) → close (BlockingQueuedConnection).

Zero Qt w warstwie danych; zero SQL poza repository (R13).
"""

from __future__ import annotations

import sqlite3
import threading
from typing import Any, Callable, Dict, List, Optional

from PyQt5.QtCore import QObject, QTimer, pyqtSignal, pyqtSlot

from app.core.logging_setup import get_logger
from app.core.timeutil import utc_now_iso
from app.data import migrations
from app.data.connection import open_connection
from app.data.repository import DonghuaRepository, LinksRepository, UniverseRepository
from app.domain.models import Donghua, Status

log = get_logger("worker.db")

COALESCE_MS = 250  # okno scalania zapisów postępu (R10, §4.6)


class DbWorker(QObject):
    """Worker bazy danych. Sloty wywoływane wyłącznie przez kolejkę zdarzeń wątku."""

    # --- wyniki → GUI/kontroler -------------------------------------------------
    libraryLoaded = pyqtSignal(list)  # List[Donghua]
    universesLoaded = pyqtSignal(list)  # List[Universe]
    saveSucceeded = pyqtSignal(int, int)  # donghua_id, request_id
    saveFailed = pyqtSignal(int, int, str)  # donghua_id, request_id, message
    addSucceeded = pyqtSignal(object, int)  # Donghua (z id), request_id
    addFailed = pyqtSignal(int, str)  # request_id, message
    removeSucceeded = pyqtSignal(int, int)  # donghua_id, request_id
    removeFailed = pyqtSignal(int, int, str)  # donghua_id, request_id, message
    universeCreated = pyqtSignal(int, str, int)  # universe_id, name, request_id
    universeAttached = pyqtSignal(int, int, int)  # donghua_id, universe_id, request_id
    coverSaved = pyqtSignal(str)  # url
    fullSaved = pyqtSignal(object, int)  # Donghua, request_id
    fullFailed = pyqtSignal(int, int, str)  # donghua_id, request_id, message
    linksLoaded = pyqtSignal(dict)  # donghua_id -> List[StreamingLink]

    def __init__(
        self,
        db_path: str,
        backups_dir: str,
        covers_dir: Optional[str] = None,
        repo_factory: Optional[Callable[[sqlite3.Connection], Any]] = None,
        parent: Optional[QObject] = None,
    ) -> None:
        super().__init__(parent)
        self._db_path = db_path
        self._backups_dir = backups_dir
        self._covers_dir = covers_dir
        self._repo_factory = repo_factory or DonghuaRepository
        self._conn: Optional[sqlite3.Connection] = None
        self._repo: Optional[DonghuaRepository] = None
        self._links: Optional[LinksRepository] = None
        self._universes: Optional[UniverseRepository] = None
        # pending: donghua_id -> [episode, status_value, request_id]
        self._pending: Dict[int, List[Any]] = {}
        self._flush_scheduled = False
        self._owner_ident: Optional[int] = None  # wątek, w którym otwarto połączenie (R2)

    # --- cykl życia ---------------------------------------------------------------
    def _ensure_open(self) -> DonghuaRepository:
        if self._repo is None:
            message = migrations.recover_if_corrupt(self._db_path, self._backups_dir)
            if message:
                log.warning("recovery bazy: %s", message)
            self._conn = open_connection(self._db_path)
            migrations.ensure_schema(self._conn, self._backups_dir)
            self._repo = self._repo_factory(self._conn)
            self._links = LinksRepository(self._conn)
            self._universes = UniverseRepository(self._conn)
            self._owner_ident = threading.get_ident()
        return self._repo

    @pyqtSlot()
    def loadLibrary(self) -> None:
        """Start: migracje + load żywych pozycji (slot wywoływany przez thread.started)."""
        try:
            repo = self._ensure_open()
            rows = repo.load_alive()
            universes = self._universes.list_all()
        except sqlite3.Error as exc:  # pragma: no cover - obrona startu
            log.error("load biblioteki nieudany: %s", exc)
            rows = []
            universes = []
        log.info("biblioteka wczytana: %d pozycji, %d uniwersów", len(rows), len(universes))
        self.libraryLoaded.emit(rows)
        self.universesLoaded.emit(universes)
        try:
            self.linksLoaded.emit(self._links.list_all())
        except sqlite3.Error:  # pragma: no cover
            self.linksLoaded.emit({})

    @pyqtSlot()
    def shutdown(self) -> None:
        """Flush + checkpoint + close. Wywoływać BlockingQueuedConnection z main."""
        self._flush()
        if self._conn is not None:
            try:
                self._conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                self._conn.close()
            except sqlite3.Error as exc:  # pragma: no cover
                log.warning("błąd zamknięcia bazy: %s", exc)
            self._conn = None
            self._repo = None

    # --- komendy (sloty) ------------------------------------------------------------
    @pyqtSlot(int, int, str, int)
    def saveEpisode(self, donghua_id: int, episode: int, status: str, request_id: int) -> None:
        """Zapis postępu z koalescencją 250 ms per id (R10).

        Koalescencja bez timera-QTimer jako członka obiektu: singleShot tworzony
        jest w wątku WYWOŁANIA (zawsze wątek workera w produkcji), co eliminuje
        pułapki afiliacji timera między wątkami.
        """
        had_pending = bool(self._pending)
        self._pending[int(donghua_id)] = [int(episode), str(status), int(request_id)]
        if not had_pending and not self._flush_scheduled:
            self._flush_scheduled = True
            QTimer.singleShot(COALESCE_MS, self._flush_scheduled_run)

    @pyqtSlot(object, int)
    def addDonghua(self, d: Donghua, request_id: int) -> None:
        try:
            repo = self._ensure_open()
            new_id = repo.insert(d)
            stored = repo.get(new_id)
            self.addSucceeded.emit(stored if stored is not None else d, int(request_id))
        except sqlite3.Error as exc:
            log.error("add nieudane: %s", exc)
            self.addFailed.emit(int(request_id), str(exc))

    @pyqtSlot(int, int)
    def softDelete(self, donghua_id: int, request_id: int) -> None:
        try:
            repo = self._ensure_open()
            repo.soft_delete(int(donghua_id), utc_now_iso())
            self.removeSucceeded.emit(int(donghua_id), int(request_id))
        except sqlite3.Error as exc:
            log.error("remove nieudane: %s", exc)
            self.removeFailed.emit(int(donghua_id), int(request_id), str(exc))

    @pyqtSlot(int, int)
    def restore(self, donghua_id: int, request_id: int) -> None:
        try:
            repo = self._ensure_open()
            repo.restore(int(donghua_id))
            self.removeSucceeded.emit(int(donghua_id), int(request_id))
        except sqlite3.Error as exc:  # pragma: no cover
            log.error("restore nieudane: %s", exc)
            self.removeFailed.emit(int(donghua_id), int(request_id), str(exc))

    @pyqtSlot()
    def flush(self) -> None:
        """Wymusza zapis pending (używane też przez shutdown)."""
        self._flush()

    # --- cache API (§4.7): zapis wyłącznie tutaj (R2) ---------------------------------
    @pyqtSlot(str, str, str, int)
    def saveCache(self, key: str, provider: str, payload: str, ttl_s: int) -> None:
        try:
            from app.data.api_cache import ApiCache

            self._ensure_open()
            ApiCache(self._conn).set(key, provider, payload, ttl_s)
        except sqlite3.Error as exc:  # pragma: no cover - cache nie może psuć flow
            log.warning("zapis cache nieudany: %s", exc)

    # --- uniwersa (§4.9.3) ---------------------------------------------------------------
    @pyqtSlot(str, object, int)
    def createUniverse(self, name: str, anchor_mal_id: object, request_id: int) -> None:
        try:
            self._ensure_open()
            # create() siedzi w UniverseRepository (self._universes), NIE w DonghuaRepository
            uid = self._universes.create(name, anchor_mal_id)
            self.universeCreated.emit(uid, name, int(request_id))
        except (sqlite3.Error, ValueError) as exc:
            log.error("createUniverse nieudane: %s", exc)

    @pyqtSlot(int, int, int)
    def attachUniverse(self, donghua_id: int, universe_id: int, request_id: int) -> None:
        try:
            repo = self._ensure_open()
            repo.set_universe(int(donghua_id), int(universe_id))
            self.universeAttached.emit(int(donghua_id), int(universe_id), int(request_id))
        except sqlite3.Error as exc:
            log.error("attachUniverse nieudane: %s", exc)

    @pyqtSlot(int, int, int)
    def saveUniverseOrder(self, donghua_id: int, order: int, request_id: int) -> None:
        """Ręczny override kolejności w uniwersum (§4.9.1 pkt 2)."""
        try:
            repo = self._ensure_open()
            d = repo.get(int(donghua_id))
            if d is not None:
                repo.set_universe(int(donghua_id), d.universe_id, int(order))
            self.universeAttached.emit(int(donghua_id), d.universe_id if d else -1, int(request_id))
        except sqlite3.Error as exc:
            log.error("saveUniverseOrder nieudane: %s", exc)

    @pyqtSlot(int, str, int)
    def updateCoverKey(self, donghua_id: int, cover_key: str, request_id: int) -> None:
        try:
            self._ensure_open()
            with self._conn:
                self._conn.execute(
                    "UPDATE donghua SET cover_key = ? WHERE id = ?",
                    (cover_key, int(donghua_id)),
                )
        except sqlite3.Error as exc:
            log.warning("updateCoverKey nieudane: %s", exc)

    # --- okładki (§4.8): plik+indeks zapisywane WYŁĄCZNIE tutaj (R2) -------------------
    @pyqtSlot(str, str, object)
    def saveCover(self, key: str, url: str, data: object) -> None:
        try:
            from app.data.cover_store import CoverStore

            self._ensure_open()
            store = CoverStore(self._conn, self._covers_dir or "")
            store.put(key, url, bytes(data))
            log.info("cover_cache: zapis %s (%d B)", key[:12], len(bytes(data)))
            self.coverSaved.emit(url)
        except (OSError, sqlite3.Error) as exc:
            log.warning("zapis okładki nieudany: %s", exc)

    # --- pełny zapis (AdvancedPage / edycja, M5) -----------------------------------------
    @pyqtSlot(int, object, int)
    def replaceLinks(self, donghua_id: int, links: object, request_id: int) -> None:
        try:
            self._ensure_open()
            with self._conn:
                self._links.replace_links(int(donghua_id), list(links))
        except sqlite3.Error as exc:
            log.error("replaceLinks nieudane: %s", exc)

    @pyqtSlot(object, object, int)
    def saveFull(self, d: object, links: object, request_id: int) -> None:
        """update_full + replace_links w JEDNEJ transakcji (rygor 12 zadania)."""
        try:
            repo = self._ensure_open()
            with self._conn:
                repo.update_full(d)
                self._links.replace_links(d.id, list(links))
            self.fullSaved.emit(d, int(request_id))
        except sqlite3.Error as exc:
            log.error("saveFull nieudane: %s", exc)
            self.fullFailed.emit(d.id if hasattr(d, "id") else -1, int(request_id), str(exc))

    # --- wewnętrzne -------------------------------------------------------------------
    def _flush_scheduled_run(self) -> None:
        self._flush_scheduled = False
        self._flush()

    def _flush(self) -> None:
        self._flush_scheduled = False
        if not self._pending:
            return
        if self._conn is not None and threading.get_ident() != self._owner_ident:
            # obrona R2: zapis poza wątkiem właściciela połączenia jest błędem topologii
            log.critical("flush poza wątkiem bazy — pomijam (topologia R2)")
            return
        batch = dict(self._pending)
        self._pending.clear()
        try:
            repo = self._ensure_open()
        except sqlite3.Error as exc:  # pragma: no cover
            for donghua_id, (_, _, rid) in batch.items():
                self.saveFailed.emit(donghua_id, rid, str(exc))
            return
        for donghua_id, (episode, status_value, rid) in batch.items():
            try:
                repo.update_progress(donghua_id, episode, Status(status_value), utc_now_iso())
                self.saveSucceeded.emit(donghua_id, rid)
            except (sqlite3.Error, ValueError) as exc:
                log.error("zapis postępu %d nieudany: %s", donghua_id, exc)
                self.saveFailed.emit(donghua_id, rid, str(exc))
