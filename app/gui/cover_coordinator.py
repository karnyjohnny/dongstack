"""app/gui/cover_coordinator.py — most okładek: NetworkWorker → widoki (M5/M6-fix).

- żądania okładek dla WIDOCZNYCH wierszy dashboardu ORAZ wierszy wyników AddDialog,
- QImage z workera → QPixmap WYŁĄCZNIE w wątku GUI (R3),
- WSPÓLNY bounded LRU 64 pixmap (jedna dekoda zasila dashboard i dialog) (§4.8),
- świeże bajty → zapis przez DbWorker.saveCover (R2); kolejne sesje czytają z dysku,
- dedupe: ten sam url nie leci dwa razy (in-flight + LRU).
"""

from __future__ import annotations

from collections import OrderedDict
from typing import Dict, Optional

from PyQt5.QtCore import QObject, pyqtSignal
from PyQt5.QtGui import QPixmap

from app.core.logging_setup import get_logger

log = get_logger("gui.covers")

LRU_LIMIT = 64  # §4.8: bounded cache pixmap (~1.6 MB)


class SharedPixmaps:
    """Wspólny LRU pixmap dla dashboardu i AddDialog."""

    def __init__(self, limit: int = LRU_LIMIT) -> None:
        self._items: OrderedDict[str, QPixmap] = OrderedDict()
        self._limit = limit

    def get(self, url: str) -> Optional[QPixmap]:
        pixmap = self._items.get(url)
        if pixmap is not None:
            self._items.move_to_end(url)
        return pixmap

    def put(self, url: str, pixmap: QPixmap) -> None:
        self._items[url] = pixmap
        self._items.move_to_end(url)
        while len(self._items) > self._limit:
            self._items.popitem(last=False)

    def snapshot(self):
        return list(self._items.items())

    def __len__(self) -> int:
        return len(self._items)


_SHARED = SharedPixmaps()


def shared_pixmaps() -> SharedPixmaps:
    return _SHARED


class CoverCoordinator(QObject):
    saveCoverRequested = pyqtSignal(str, str, object)  # key, url, bytes → DbWorker
    pixmapReady = pyqtSignal(str, object)  # url, QPixmap → dashboard + SearchPage

    def __init__(self, backend, network_worker, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._backend = backend
        self._net = network_worker
        self._pixmaps = shared_pixmaps()
        self._inflight = set()
        self._saved = set()
        self._url_by_id: Dict[int, str] = {}
        if network_worker is not None:
            network_worker.coverReady.connect(self.on_cover_ready)
            network_worker.coverFailed.connect(self._on_cover_failed)

    # --- wejście: widoczne pozycje dashboardu ------------------------------------------
    def request_covers(self, entries) -> None:
        self._url_by_id = {}
        pairs = []
        for entry in entries:
            url = getattr(entry, "cover_key", None)  # cover_key przechowuje URL (§4.8)
            did = getattr(entry, "id", None)
            if not url or did is None:
                continue
            self._url_by_id[did] = url
            cached = self._pixmaps.get(url)
            if cached is not None:
                row = self._backend.row_widget(did)
                if row is not None:
                    row.set_cover_pixmap(cached)
                continue
            pairs.append((url, getattr(entry, "mal_id", 0) or 0))
        self.request_pairs(pairs)

    # --- wejście: pary (url, mal_id) — AddDialog i fallback AniList ----------------------
    def request_pairs(self, pairs) -> None:
        if pairs:
            log.info(
                "okładki: zamawiam %d (pierwsza: %s, mal_id=%s)",
                len(pairs),
                pairs[0][0],
                pairs[0][1],
            )
        for url, mal_id in pairs:
            if url in self._inflight or self._pixmaps.get(url) is not None:
                continue
            self._inflight.add(url)
            if self._net is not None:
                self._net.enqueue_cover(url, mal_id)

    # --- powrót z workera (wątek GUI) ---------------------------------------------------
    def on_cover_ready(self, url: str, image, data) -> None:
        self._inflight.discard(url)
        pixmap = QPixmap.fromImage(image)  # R3: QPixmap tylko w GUI
        self._pixmaps.put(url, pixmap)
        self._backend.set_cover(url, pixmap)
        self.pixmapReady.emit(url, pixmap)
        if data is not None and url not in self._saved:
            # dedupe: ten sam url zapisujemy do cover_cache dokładnie raz na sesję
            self._saved.add(url)
            from app.data.cover_store import cover_key

            self.saveCoverRequested.emit(cover_key(url), url, data)

    def _on_cover_failed(self, url: str) -> None:
        self._inflight.discard(url)  # placeholder zostaje (§4.8)
