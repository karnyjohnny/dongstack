"""Testy TokenBucket: rate, burst, timeout — z fake clock (bez realnego spania)."""

from __future__ import annotations

import pytest

from app.api.rate_limiter import TokenBucket


class FakeClock:
    def __init__(self, start=1000.0):
        self.now = start
        self.slept = []

    def clock(self):
        return self.now

    def sleep(self, seconds):
        self.slept.append(seconds)
        self.now += seconds


def test_initial_capacity_allows_burst():
    fc = FakeClock()
    bucket = TokenBucket(rate_per_sec=1.0, capacity=2, clock=fc.clock, sleeper=fc.sleep)
    assert bucket.try_acquire()
    assert bucket.try_acquire()
    assert not bucket.try_acquire()  # burst wyczerpany


def test_refill_over_time():
    fc = FakeClock()
    bucket = TokenBucket(rate_per_sec=1.0, capacity=2, clock=fc.clock, sleeper=fc.sleep)
    bucket.try_acquire()
    bucket.try_acquire()
    fc.now += 0.5
    assert not bucket.try_acquire()  # pół żetonu to za mało
    fc.now += 0.6  # łącznie 1.1 s → 1 żeton
    assert bucket.try_acquire()


def test_acquire_blocks_until_token():
    fc = FakeClock()
    bucket = TokenBucket(rate_per_sec=1.0, capacity=1, clock=fc.clock, sleeper=fc.sleep)
    assert bucket.acquire()  # natychmiast (pełny kubełek)
    assert bucket.acquire(timeout=5.0)  # czeka ~1 s (przez sen zegar rusza)
    assert fc.slept and sum(fc.slept) >= 0.9


def test_acquire_timeout_returns_false():
    fc = FakeClock()
    bucket = TokenBucket(rate_per_sec=0.1, capacity=1, clock=fc.clock, sleeper=fc.sleep)
    assert bucket.acquire()  # capacity=1 → pierwsze natychmiast
    # odnowienie zajęłoby 10 s; timeout 0.5 s → False (sleeper rusza zegar)
    assert bucket.acquire(timeout=0.5) is False

    fc2 = FakeClock()
    advanced = {"t": 0.0}

    def sleeper(s):
        advanced["t"] += s
        fc2.now += s  # sleeper MUSI ruszać zegar (jak time.sleep)

    bucket2 = TokenBucket(rate_per_sec=0.01, capacity=1, clock=fc2.clock, sleeper=sleeper)
    assert bucket2.acquire()
    assert bucket2.acquire(timeout=1.0) is False
    assert advanced["t"] >= 0.5  # realnie odczekane w kawałkach


def test_wait_time_estimate():
    fc = FakeClock()
    bucket = TokenBucket(rate_per_sec=2.0, capacity=1, clock=fc.clock, sleeper=fc.sleep)
    assert bucket.wait_time() == 0.0
    bucket.try_acquire()
    wt = bucket.wait_time()
    assert 0.4 <= wt <= 0.51  # 1 żeton / 2 na sekundę


def test_rate_limit_guarantee_one_per_second():
    """Symulacja: 5 żądań przy rate=1/s, capacity=1 → łączny czas ≥ 4 s (rygor ≤1 req/s)."""
    fc = FakeClock()
    bucket = TokenBucket(rate_per_sec=1.0, capacity=1, clock=fc.clock, sleeper=fc.sleep)
    for _ in range(5):
        assert bucket.acquire(timeout=60)
    assert (fc.now - 1000.0) >= 3.9


def test_invalid_rate():
    with pytest.raises(ValueError):
        TokenBucket(rate_per_sec=0)
