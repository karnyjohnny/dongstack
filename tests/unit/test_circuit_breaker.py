"""Testy CircuitBreaker: próg, timeouty, half-open, specyfika THROTTLED_BAN."""

from __future__ import annotations

from app.api.circuit_breaker import BreakerState, CircuitBreaker
from app.core.errors import ApiError, ApiErrorKind


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


def _err(kind):
    return ApiError(kind, "x", provider="mal")


def test_starts_closed_and_allows():
    cb = CircuitBreaker(clock=FakeClock())
    assert cb.state == BreakerState.CLOSED
    assert cb.allow_request()


def test_opens_after_threshold():
    clk = FakeClock()
    cb = CircuitBreaker(threshold=3, reset_timeout=60.0, clock=clk)
    cb.record_failure(_err(ApiErrorKind.NETWORK))
    cb.record_failure(_err(ApiErrorKind.SERVER))
    assert cb.allow_request()
    cb.record_failure(_err(ApiErrorKind.NETWORK))
    assert cb.state == BreakerState.OPEN
    assert not cb.allow_request()


def test_half_open_after_timeout_and_closes_on_success():
    clk = FakeClock()
    cb = CircuitBreaker(threshold=2, reset_timeout=60.0, clock=clk)
    cb.record_failure(_err(ApiErrorKind.SERVER))
    cb.record_failure(_err(ApiErrorKind.SERVER))
    assert cb.state == BreakerState.OPEN
    clk.now += 61.0
    assert cb.state == BreakerState.HALF_OPEN
    assert cb.allow_request()
    cb.record_success()
    assert cb.state == BreakerState.CLOSED


def test_half_open_failure_reopens():
    clk = FakeClock()
    cb = CircuitBreaker(threshold=1, reset_timeout=10.0, clock=clk)
    cb.record_failure(_err(ApiErrorKind.SERVER))
    clk.now += 11.0
    assert cb.state == BreakerState.HALF_OPEN
    cb.record_failure(_err(ApiErrorKind.SERVER))
    assert cb.state == BreakerState.OPEN


def test_throttled_ban_uses_long_cooldown():
    clk = FakeClock()
    cb = CircuitBreaker(threshold=3, reset_timeout=60.0, ban_timeout=300.0, clock=clk)
    cb.record_failure(_err(ApiErrorKind.THROTTLED_BAN))  # pojedynczy ban → natychmiast OPEN
    assert cb.state == BreakerState.OPEN
    clk.now += 120.0
    assert cb.state == BreakerState.OPEN  # jeszcze nie (300 s)
    clk.now += 200.0
    assert cb.state == BreakerState.HALF_OPEN


def test_non_retryable_failures_do_not_trip():
    clk = FakeClock()
    cb = CircuitBreaker(threshold=2, clock=clk)
    for _ in range(5):
        cb.record_failure(_err(ApiErrorKind.BAD_REQUEST))
        cb.record_failure(_err(ApiErrorKind.NOT_FOUND))
    assert cb.state == BreakerState.CLOSED


def test_success_resets_counter():
    clk = FakeClock()
    cb = CircuitBreaker(threshold=3, clock=clk)
    cb.record_failure(_err(ApiErrorKind.NETWORK))
    cb.record_failure(_err(ApiErrorKind.NETWORK))
    cb.record_success()
    cb.record_failure(_err(ApiErrorKind.NETWORK))
    cb.record_failure(_err(ApiErrorKind.NETWORK))
    assert cb.state == BreakerState.CLOSED  # 2 z rzędu, nie 4


def test_seconds_until_retry():
    clk = FakeClock()
    cb = CircuitBreaker(threshold=1, reset_timeout=60.0, clock=clk)
    assert cb.seconds_until_retry() is None
    cb.record_failure(_err(ApiErrorKind.SERVER))
    remaining = cb.seconds_until_retry()
    assert remaining is not None and 59.0 <= remaining <= 60.0
