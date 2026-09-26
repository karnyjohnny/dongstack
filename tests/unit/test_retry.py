"""Testy retry: backoff wykładniczy, jitter w granicach, Retry-After, ban cooldown."""

from __future__ import annotations

from app.api.retry import BackoffSleeper, RetryPolicy
from app.core.errors import ApiError, ApiErrorKind


def _err(kind, retry_after=None):
    return ApiError(kind, "x", provider="mal", retry_after=retry_after)


def test_exponential_growth_midpoint():
    p = RetryPolicy(jitter=0.0)
    assert p.delay_for(0) == 1.0
    assert p.delay_for(1) == 2.0
    assert p.delay_for(2) == 4.0
    assert p.delay_for(3) == 8.0


def test_max_delay_cap():
    p = RetryPolicy(jitter=0.0, max_delay=60.0)
    assert p.delay_for(10) == 60.0


def test_jitter_within_bounds():
    p = RetryPolicy(jitter=0.2)
    for attempt in range(4):
        base = min(1.0 * (2.0**attempt), 60.0)
        for rand in (0.0, 0.5, 1.0):
            d = p.delay_for(attempt, rand=lambda r=rand: r)
            assert base * 0.8 - 1e-9 <= d <= base * 1.2 + 1e-9


def test_retry_after_wins_when_larger():
    p = RetryPolicy(jitter=0.0)
    d = p.delay_for(0, retry_after=17.0)
    assert d == 17.0
    # ale jest capped do max_delay
    d2 = p.delay_for(0, retry_after=9999.0)
    assert d2 == 60.0


def test_retry_after_ignored_when_smaller_than_backoff():
    p = RetryPolicy(jitter=0.0)
    d = p.delay_for(3, retry_after=0.5)  # backoff 8 s > 0.5
    assert d == 8.0


def test_ban_cooldown_for_throttled_ban():
    p = RetryPolicy(jitter=0.0, ban_cooldown=300.0)
    d = p.delay_for(0, kind=ApiErrorKind.THROTTLED_BAN)
    assert d == 300.0


def test_should_retry_matrix():
    p = RetryPolicy(attempts=4)
    assert p.should_retry(_err(ApiErrorKind.RATE_LIMITED), 1)
    assert p.should_retry(_err(ApiErrorKind.SERVER), 3)
    assert p.should_retry(_err(ApiErrorKind.NETWORK), 3)
    assert not p.should_retry(_err(ApiErrorKind.RATE_LIMITED), 4)  # próby wyczerpane
    assert not p.should_retry(_err(ApiErrorKind.BAD_REQUEST), 1)  # niere trybowalne
    assert not p.should_retry(_err(ApiErrorKind.AUTH), 1)
    assert not p.should_retry(_err(ApiErrorKind.NOT_FOUND), 1)
    assert not p.should_retry(_err(ApiErrorKind.PARSE), 1)


def test_backoff_sleeper_stops_on_request():
    calls = []
    stop = {"flag": False}

    def fake_sleep(s):
        calls.append(s)
        if len(calls) >= 3:
            stop["flag"] = True

    sleeper = BackoffSleeper(sleep=fake_sleep, should_stop=lambda: stop["flag"])
    ok = sleeper.sleep(10.0)
    assert ok is False  # przerwane kooperacyjnie (R4: brak terminate)
    assert len(calls) >= 3
    assert all(c <= 0.5 for c in calls)


def test_backoff_sleeper_completes():
    total = []
    sleeper = BackoffSleeper(sleep=lambda s: total.append(s))
    assert sleeper.sleep(1.2) is True
    assert abs(sum(total) - 1.2) < 1e-9
