"""Testy NetworkWorker (M4): kolejka, retry+backoff, cancel, cache-write, related."""

from __future__ import annotations

import time

from PyQt5.QtCore import QThread
from PyQt5.QtTest import QTest

from app.api.circuit_breaker import CircuitBreaker
from app.api.metadata_service import MetadataService
from app.api.retry import RetryPolicy
from app.core.errors import ApiError, ApiErrorKind
from app.domain.models import RelationType, SearchItem
from app.workers.network_worker import NetworkWorker

FAST = RetryPolicy(attempts=3, base_delay=0.02, factor=2.0, max_delay=0.1, jitter=0.0)


class FlakyProvider:
    name = "mal"

    def __init__(self, fail_times=0, error=None, items=None, relations=None):
        self.fail_times = fail_times
        self.error = error or ApiError(ApiErrorKind.RATE_LIMITED, "429", provider="mal")
        self.items = (
            items
            if items is not None
            else [SearchItem(provider="mal", ext_id=1, mal_id=1, title="Wynik")]
        )
        self.relations = relations if relations is not None else [(2, RelationType.SEQUEL)]
        self.calls = 0

    def search(self, query, limit=20):
        self.calls += 1
        if self.calls <= self.fail_times:
            raise self.error
        return self.items

    def related(self, mal_id):
        self.calls += 1
        if self.calls <= self.fail_times:
            raise self.error
        return self.relations


class WorkerHarness:
    def __init__(self, qapp, provider, cache_store=None):
        self.qapp = qapp
        service = MetadataService(
            providers={"mal": provider},
            breakers={"mal": CircuitBreaker()},
        )
        self.worker = NetworkWorker(service, policy=FAST)
        self.thread = QThread()
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run_loop)
        self.thread.start()
        self.events = []
        self.worker.searchFinished.connect(lambda r, i, p: self.events.append(("ok", r, i, p)))
        self.worker.searchFailed.connect(lambda r, e: self.events.append(("fail", r, e)))
        self.worker.relatedFinished.connect(lambda r, m, x: self.events.append(("rel", r, m, x)))
        self.worker.cacheWriteRequested.connect(
            lambda k, p, pay, t: self.events.append(("cache", k))
        )

    def wait_for(self, kind, timeout_ms=4000):
        deadline = time.time() + timeout_ms / 1000.0
        while time.time() < deadline:
            QTest.qWait(25)
            for ev in self.events:
                if ev[0] == kind:
                    return ev
        return None

    def teardown(self):
        self.worker.stop()
        self.thread.quit()
        self.thread.wait(1500)


def test_search_success_and_cache_write(qapp):
    h = WorkerHarness(qapp, FlakyProvider())
    try:
        h.worker.enqueue_search("doupo", 1)
        ev = h.wait_for("ok")
        assert ev is not None and ev[1] == 1 and ev[3] == "mal"
        cache_ev = h.wait_for("cache")
        assert cache_ev is not None and cache_ev[1].startswith("mal:search:doupo")
    finally:
        h.teardown()


def test_retry_on_429_then_success(qapp):
    provider = FlakyProvider(fail_times=2)
    h = WorkerHarness(qapp, provider)
    try:
        h.worker.enqueue_search("x", 5)
        ev = h.wait_for("ok", timeout_ms=6000)
        assert ev is not None and ev[1] == 5
        assert provider.calls == 3  # 2×429 + sukces (backoff FAST)
    finally:
        h.teardown()


def test_attempts_exhausted_emits_failure(qapp):
    provider = FlakyProvider(fail_times=99)
    h = WorkerHarness(qapp, provider)
    try:
        h.worker.enqueue_search("x", 9)
        ev = h.wait_for("fail", timeout_ms=6000)
        assert ev is not None and ev[1] == 9
        assert ev[2].kind == ApiErrorKind.RATE_LIMITED
        assert provider.calls == FAST.attempts
    finally:
        h.teardown()


def test_cancel_suppresses_emission(qapp):
    provider = FlakyProvider(fail_times=1)  # chwila na cancel przed processing
    h = WorkerHarness(qapp, provider)
    try:
        h.worker.enqueue_search("stare", 11)
        h.worker.cancel(11)
        h.worker.enqueue_search("nowe", 12)
        ev = h.wait_for("ok", timeout_ms=6000)
        assert ev is not None and ev[1] == 12  # tylko świeże żądanie
        kinds = [e for e in h.events if e[0] in ("ok", "fail")]
        assert all(e[1] != 11 for e in kinds)
    finally:
        h.teardown()


def test_related_flow(qapp):
    h = WorkerHarness(qapp, FlakyProvider())
    try:
        h.worker.enqueue_related(37176, 21)
        ev = h.wait_for("rel", timeout_ms=6000)
        assert ev is not None and ev[1] == 21 and ev[2] == 37176
        assert (2, RelationType.SEQUEL) in ev[3]
    finally:
        h.teardown()


def test_priority_search_before_related(qapp):
    """Search (HIGH) wyprzedza zaplanowany wcześniej related (LOW)."""
    provider = FlakyProvider()
    h = WorkerHarness(qapp, provider)
    try:
        h.worker.enqueue_related(1, 31)  # LOW w kolejce pierwszy
        h.worker.enqueue_search("pilne", 32)  # HIGH przeskakuje
        ev = h.wait_for("ok", timeout_ms=6000)
        assert ev is not None and ev[1] == 32
    finally:
        h.teardown()
