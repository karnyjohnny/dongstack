"""LIVE test pipeline'u okładek na PRAWDZIWYM API/CDN (opt-in, §10).

Uruchomienie: RUN_LIVE_API_TESTS=1 MAL_CLIENT_ID=<id> pytest tests/live -m live
Scenariusz: MAL search → cover_url z odpowiedzi → NetworkWorker (prawdziwy HTTP)
→ QImage zdekodowane + bajty do zapisu. Drugi scenariusz: fallback AniList
(południowe CDN) dla tego samego mal_id.
"""

from __future__ import annotations

import os
import time

import pytest
from PyQt5.QtCore import QThread
from PyQt5.QtTest import QTest

from app.api.anilist_client import AnilistClient
from app.api.mal_client import MalClient
from app.api.metadata_service import MetadataService
from app.api.retry import RetryPolicy
from app.workers.network_worker import NetworkWorker

pytestmark = pytest.mark.live

CLIENT_ID = os.environ.get("MAL_CLIENT_ID", "")
RUN = os.environ.get("RUN_LIVE_API_TESTS", "") == "1"

pytestmark = [
    pytestmark,
    pytest.mark.skipif(
        not (RUN and CLIENT_ID), reason="live: wymaga RUN_LIVE_API_TESTS=1 + MAL_CLIENT_ID"
    ),
]


def _wait(events, n=1, timeout=15.0):
    deadline = time.time() + timeout
    while time.time() < deadline and len(events) < n:
        QTest.qWait(100)
    return len(events) >= n


def test_live_cover_pipeline_mal_cdn(qapp):
    client = MalClient(CLIENT_ID)
    items = client.search("doupo cangqiong", limit=1)
    assert items and items[0].cover_url
    time.sleep(1.2)

    service = MetadataService(providers={"mal": client, "anilist": AnilistClient()})
    worker = NetworkWorker(service, policy=RetryPolicy(attempts=2, base_delay=0.5))
    events = []
    worker.coverReady.connect(lambda u, i, b: events.append((u, i, b)))
    thread = QThread()
    worker.moveToThread(thread)
    thread.started.connect(worker.run_loop)
    thread.start()
    worker.enqueue_cover(items[0].cover_url, items[0].mal_id)
    ok = _wait(events)
    worker.stop()
    thread.quit()
    thread.wait(2000)
    assert ok, "okładka z CDN MAL nie przyszła (live)"
    url, image, data = events[0]
    assert url == items[0].cover_url
    assert not image.isNull() and image.width() <= 120 and image.height() <= 170
    assert data and len(data) > 500


def test_live_cover_fallback_anilist(qapp):
    """Symulacja zablokowanego CDN MAL: http_get rzuca dla hosta MAL, AniList ratuje."""
    client = MalClient(CLIENT_ID)
    items = client.search("fanren xiu xian zhuan", limit=1)
    assert items and items[0].mal_id
    time.sleep(1.2)
    mal_url = items[0].cover_url

    from app.core.errors import ApiError, ApiErrorKind

    def blocked_mal_cdn(url):
        if "myanimelist.net" in url:
            raise ApiError(ApiErrorKind.NETWORK, "symulowana blokada CDN", provider="covers")
        import requests

        resp = requests.get(url, timeout=(5.0, 10.0))
        if resp.status_code != 200:
            raise ApiError(
                ApiErrorKind.NETWORK,
                "http %d" % resp.status_code,
                provider="covers",
                status=resp.status_code,
            )
        return resp.content

    service = MetadataService(providers={"mal": client, "anilist": AnilistClient()})
    worker = NetworkWorker(service, policy=RetryPolicy(attempts=1), http_get=blocked_mal_cdn)
    events = []
    worker.coverReady.connect(lambda u, i, b: events.append((u, i, b)))
    thread = QThread()
    worker.moveToThread(thread)
    thread.started.connect(worker.run_loop)
    thread.start()
    worker.enqueue_cover(mal_url, items[0].mal_id)
    ok = _wait(events)
    worker.stop()
    thread.quit()
    thread.wait(2000)
    assert ok, "fallback AniList nie dostarczył okładki (live)"
    assert events[0][0] == mal_url  # klucz cache = oryginalny URL MAL
    assert not events[0][1].isNull()
