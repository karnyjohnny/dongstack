"""app/workers/network_worker.py — NetworkWorker: JEDYNY wątek z requests (R1).

Topologia (specyfikacja §3.1, §5.4):
- kolejka priorytetowa (search = HIGH, related = LOW), FIFO w ramach priorytetu;
  jedno żyjące QThread, zero thread-per-request (Core 2 Duo!),
- TokenBucket per provider PRZED każdą próbą (MAL ≤1 req/s, AniList ≤0.4 req/s),
- retry: RetryPolicy (backoff + jitter + Retry-After) + CircuitBreaker per provider,
- request_id (R5): cancel(rid) pomija emisję nieaktualnych wyników; zero terminate (R4),
- cache: odczyt połączeniem read-only UTWORZONYM w wątku workera; zapis asynchronicznie
  sygnałem cacheWriteRequested → DbWorker.saveCache (§4.7).
"""

from __future__ import annotations

import itertools
import queue
import threading
from typing import Any, Dict, List, Optional, Tuple

from PyQt5.QtCore import QObject, pyqtSignal

from app.api.metadata_service import TTL_RELATED_S, TTL_SEARCH_S, MetadataService
from app.api.rate_limiter import TokenBucket
from app.api.retry import BackoffSleeper, RetryPolicy
from app.core.errors import ApiError, ApiErrorKind, status_to_kind
from app.core.logging_setup import get_logger
from app.data.api_cache import related_key, search_key

log = get_logger("worker.net")

PRIO_HIGH = 0
PRIO_LOW = 5

DEFAULT_BUCKETS = {"mal": (1.0, 2), "anilist": (0.4, 1)}  # (rate/s, capacity) §5.4


def _default_http_get(url: str) -> bytes:
    """Pobranie binariów okładki (CDN — poza rate-limitem API MAL)."""
    import requests

    try:
        resp = requests.get(
            url, timeout=(5.0, 10.0), headers={"User-Agent": "DongStack-covers/1.0"}
        )
    except requests.RequestException as exc:
        raise ApiError(ApiErrorKind.NETWORK, str(exc), provider="covers", cause=exc) from exc
    if resp.status_code != 200:
        raise ApiError(
            status_to_kind(resp.status_code),
            "cover HTTP %d" % resp.status_code,
            provider="covers",
            status=resp.status_code,
        )
    return resp.content


def _decode_scaled(data: bytes, max_w: int, max_h: int):
    """Dekodowanie ZE skalowaniem (QImageReader.setScaledSize) — oszczędność RAM (§4.8)."""
    from PyQt5.QtCore import QBuffer, QIODevice, QSize, Qt
    from PyQt5.QtGui import QImageReader

    buf = QBuffer()
    buf.setData(bytes(data))
    if not buf.open(QIODevice.ReadOnly):
        return None
    try:
        reader = QImageReader(buf)
        reader.setAutoTransform(True)
        size = reader.size()
        if size.isValid() and not size.isNull():
            reader.setScaledSize(size.scaled(QSize(max_w, max_h), Qt.KeepAspectRatio))
        image = reader.read()
    finally:
        buf.close()
    if image is None or image.isNull():
        return None
    return image


class _Task:
    __slots__ = ("kind", "rid", "args")

    def __init__(self, kind: str, rid: int, args: Tuple[Any, ...]) -> None:
        self.kind = kind
        self.rid = rid
        self.args = args


class NetworkWorker(QObject):
    """Worker sieciowy. Pętla żyje w osobnym QThread (thread.started → run_loop)."""

    searchFinished = pyqtSignal(int, list, str)  # rid, items, provider
    searchFailed = pyqtSignal(int, object)  # rid, ApiError
    relatedFinished = pyqtSignal(int, int, list)  # rid, mal_id, relations
    relatedFailed = pyqtSignal(int, int, object)  # rid, mal_id, ApiError
    coverReady = pyqtSignal(str, object, object)  # url, QImage, bytes|None
    coverFailed = pyqtSignal(str)  # url
    backfillFinished = pyqtSignal(int, str)  # donghua_id, cover_url
    cacheWriteRequested = pyqtSignal(str, str, str, int)  # → DbWorker.saveCache

    def __init__(
        self,
        service: MetadataService,
        policy: Optional[RetryPolicy] = None,
        cache_factory=None,
        covers_factory=None,
        http_get=None,
        buckets: Optional[Dict[str, TokenBucket]] = None,
        parent: Optional[QObject] = None,
    ) -> None:
        super().__init__(parent)
        self._service = service
        self._policy = policy or RetryPolicy()
        self._cache_factory = cache_factory  # callable() -> ApiCache (w tym wątku)
        self._covers_factory = covers_factory  # callable() -> CoverStore (ro, w wątku)
        self._http_get = http_get or _default_http_get
        self._cache = None
        self._covers = None
        self._buckets = buckets or {
            name: TokenBucket(rate, cap) for name, (rate, cap) in DEFAULT_BUCKETS.items()
        }
        self._queue: queue.PriorityQueue = queue.PriorityQueue()
        self._seq = itertools.count()
        self._stop = threading.Event()
        self._cancelled = set()
        self._lock = threading.Lock()
        # serwis throttlinguje każdą próbę providera naszymi bucketami (§5.4)
        self._service._bucket_for = self._bucket_for
        # cache serwisu deleguje do proxy workera (read-only conn w wątku workera)
        self._service._cache_get = self.cache_get
        self._service._cache_set = self.cache_set

    # --- kolejka (wywoływana z wątku GUI — queue.Queue jest thread-safe) ---------
    def enqueue_search(self, query: str, rid: int, limit: int = 20) -> None:
        self._queue.put((PRIO_HIGH, next(self._seq), _Task("search", rid, (query, limit))))

    def enqueue_related(self, mal_id: int, rid: int) -> None:
        self._queue.put((PRIO_LOW, next(self._seq), _Task("related", rid, (int(mal_id),))))

    def enqueue_backfill(self, donghua_id: int, mal_id: int) -> None:
        """Stare pozycje bez cover_key: dociągnij URL okładki z details (LOW)."""
        self._queue.put(
            (PRIO_LOW, next(self._seq), _Task("backfill", None, (int(donghua_id), int(mal_id))))
        )

    def enqueue_cover(self, url: str, mal_id: int = 0) -> None:
        """Okładki: priorytet LOW, bez token bucketa (CDN, nie API MAL).

        mal_id umożliwia fallback: gdy CDN MAL milczy (hosts/AV/blokada sieci),
        ciągniemy okładkę z CDN AniList dla tej samej pozycji.
        """
        # rid=None: okładki NIE podlegają cancel() wyszukiwań (bug produkcyjny:
        # pierwsze szukanie wołało cancel(0), a cover taski miały rid=0 => ginęły)
        self._queue.put((PRIO_LOW, next(self._seq), _Task("cover", None, (str(url), int(mal_id)))))

    def cancel(self, rid: int) -> None:
        with self._lock:
            self._cancelled.add(int(rid))

    def stop(self) -> None:
        self._stop.set()
        self._queue.put((PRIO_HIGH, next(self._seq), _Task("stop", -1, ())))

    # --- proxy cache (używane przez MetadataService) --------------------------------
    def cache_get(self, key: str, allow_stale: bool = False):
        if self._cache is None:
            return None
        return self._cache.get(key, allow_stale=allow_stale)

    def cache_set(self, key: str, provider: str, payload: str, ttl_s: int) -> None:
        """Zapis cache idzie przez DbWorker (§4.7) — sygnał międzywątkowy."""
        self.cacheWriteRequested.emit(key, provider, payload, int(ttl_s))

    # --- pętla (wątek workera) ------------------------------------------------------
    def run_loop(self) -> None:
        if self._cache_factory is not None and self._cache is None:
            try:
                self._cache = self._cache_factory()
            except Exception as exc:  # noqa: BLE001 - brak cache nie zabija sieci
                log.warning("cache read-only niedostępny: %s", exc)
        if self._covers_factory is not None and self._covers is None:
            try:
                self._covers = self._covers_factory()
            except Exception as exc:  # noqa: BLE001
                log.warning("cover store read-only niedostępny: %s", exc)
        while not self._stop.is_set():
            try:
                _, _, task = self._queue.get(timeout=0.25)
            except queue.Empty:
                continue
            if task.kind == "stop":
                break
            if self._is_cancelled(task.rid):
                continue
            log.debug("task z kolejki: %s (rid=%s)", task.kind, task.rid)
            try:
                self._process(task)
            except Exception as exc:  # noqa: BLE001 - worker nie może umrzeć cicho (R12)
                log.error("task %s rid=%d: %r", task.kind, task.rid, exc)

    def _process(self, task: _Task) -> None:
        if task.kind == "search":
            query, limit = task.args
            result, err = self._with_retry(lambda: self._service.search(query, limit), task.rid)
            if err is not None:
                if not self._is_cancelled(task.rid):
                    self.searchFailed.emit(task.rid, err)
                return
            self._write_cache_search(query, limit, result)
            if not self._is_cancelled(task.rid):
                self.searchFinished.emit(task.rid, result.items, result.provider)
        elif task.kind == "related":
            mal_id = task.args[0]
            rels, err = self._with_retry(lambda: self._service.related(mal_id), task.rid)
            if err is not None:
                if not self._is_cancelled(task.rid):
                    self.relatedFailed.emit(task.rid, mal_id, err)
                return
            self._write_cache_related(mal_id, rels)
            if not self._is_cancelled(task.rid):
                self.relatedFinished.emit(task.rid, mal_id, rels)
        elif task.kind == "cover":
            self._process_cover(task)
        elif task.kind == "backfill":
            self._process_backfill(task)

    # --- okładki (§4.8, aspect 225/318) ------------------------------------------------
    def _process_cover(self, task: _Task) -> None:
        url, mal_id = task.args
        log.debug("cover: start %s (mal_id=%s)", url, mal_id)
        from app.data.cover_store import cover_key

        key = cover_key(url)
        data: Optional[bytes] = None
        from_disk = False
        source = ""
        if self._covers is not None and self._covers.has(key):
            data = self._covers.get_bytes(key)
            if data is not None:
                from_disk = True
                source = "dysk"
        if data is None:
            data = self._try_http(url)
            source = "cdn-mal"
        if data is None and mal_id:
            for alt in self._anilist_covers(mal_id):
                data = self._try_http(alt)
                if data is not None:
                    source = "cdn-anilist"
                    break
        if data is None:
            log.warning("okładka OSTATECZNIE niedostępna: %s (mal_id=%s)", url, mal_id)
            if not self._is_cancelled(task.rid):
                self.coverFailed.emit(url)
            return
        image = _decode_scaled(data, 120, 170)  # ratio 225/318 (feedback UI)
        if image is None:
            log.warning("okładka niedekodowalna (%d B) %s", len(data), url)
            if not self._is_cancelled(task.rid):
                self.coverFailed.emit(url)
            return
        log.debug("okładka OK %s (%d B, źródło=%s)", url, len(data), source)
        if not self._is_cancelled(task.rid):
            # QImage (nie QPixmap!) — konwersja w wątku GUI (R3)
            self.coverReady.emit(url, image, None if from_disk else data)

    def _try_http(self, url: str) -> Optional[bytes]:
        try:
            return self._http_get(url)
        except ApiError as exc:
            log.warning(
                "okładka HTTP niedostępna %s: %s (status=%s)",
                url,
                exc.kind.value,
                exc.status,
            )
            return None

    def _anilist_covers(self, mal_id: int) -> List[str]:
        provider = self._service.providers().get("anilist")
        getter = getattr(provider, "covers_for_mal", None)
        if getter is None:
            return []
        try:
            return getter(mal_id)
        except ApiError as exc:
            log.info("fallback okładki AniList niedostępny (mal=%s): %s", mal_id, exc.kind.value)
            return []

    def _process_backfill(self, task: _Task) -> None:
        donghua_id, mal_id = task.args
        try:
            item = self._service.details(mal_id)
        except ApiError as exc:
            log.info("backfill okładki %d: %s", mal_id, exc.kind.value)
            return
        if item is not None and item.cover_url:
            self.backfillFinished.emit(donghua_id, item.cover_url)

    # --- retry/backoff (§5.4) -----------------------------------------------------------
    def _with_retry(self, fn, rid: int):
        """Zwraca (wynik, None) albo (None, ApiError) po wyczerpaniu polityki."""
        sleeper = BackoffSleeper(should_stop=self._stop.is_set)
        attempts = 0
        while True:
            attempts += 1
            try:
                return fn(), None
            except ApiError as exc:
                if self._is_cancelled(rid):
                    return None, exc
                if not self._policy.should_retry(exc, attempts):
                    log.info("rid=%d wyczerpane próby: %r", rid, exc)
                    return None, exc
                delay = self._policy.delay_for(
                    attempts - 1, retry_after=exc.retry_after, kind=exc.kind
                )
                log.info("rid=%d retry #%d za %.1fs (%s)", rid, attempts, delay, exc.kind.value)
                if not sleeper.sleep(delay):
                    return None, exc

    # --- cache write -------------------------------------------------------------------------
    def _write_cache_search(self, query: str, limit: int, outcome) -> None:
        if outcome.from_cache:
            return
        payload = self._service._items_to_json(outcome.items)
        self.cacheWriteRequested.emit(
            search_key(outcome.provider, query, limit), outcome.provider, payload, TTL_SEARCH_S
        )

    def _write_cache_related(self, mal_id: int, rels) -> None:
        payload = self._service._relations_to_json(rels)
        provider = self._service.preferred or "mal"
        self.cacheWriteRequested.emit(related_key(mal_id), provider, payload, TTL_RELATED_S)

    # --- pomocnicze -------------------------------------------------------------------------
    def _bucket_for(self, name: str) -> Optional[TokenBucket]:
        return self._buckets.get(name)

    def _is_cancelled(self, rid) -> bool:
        if rid is None:
            return False  # taski bez request_id (okładki/backfill) żyją zawsze
        with self._lock:
            return rid in self._cancelled
