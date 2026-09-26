"""app/api/circuit_breaker.py — wyłącznik obwodu per provider (specyfikacja §5.4).

Stany: CLOSED → (3 kolejne retryable porażki) → OPEN 60 s → HALF_OPEN (1 próba)
       → sukces: CLOSED / porażka: OPEN.
THROTTLED_BAN (403-HTML MAL, F13): OPEN na 300 s (ban_cooldown z RetryPolicy).

Clock wstrzykiwalny — testy bez czekania.
"""

from __future__ import annotations

import time
from enum import Enum
from typing import Callable, Optional

from app.core.errors import ApiError, ApiErrorKind


class BreakerState(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreaker:
    def __init__(
        self,
        threshold: int = 3,
        reset_timeout: float = 60.0,
        ban_timeout: float = 300.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._threshold = max(1, int(threshold))
        self._reset_timeout = float(reset_timeout)
        self._ban_timeout = float(ban_timeout)
        self._clock = clock
        self._state = BreakerState.CLOSED
        self._failures = 0
        self._opened_at = 0.0
        self._open_until = 0.0

    @property
    def state(self) -> BreakerState:
        self._maybe_half_open()
        return self._state

    def allow_request(self) -> bool:
        """True jeśli żądanie może zostać wysłane (zamknięty lub pół-otwarty)."""
        self._maybe_half_open()
        return self._state in (BreakerState.CLOSED, BreakerState.HALF_OPEN)

    def record_success(self) -> None:
        self._failures = 0
        self._state = BreakerState.CLOSED

    def record_failure(self, err: ApiError) -> None:
        if not err.retryable:
            # błędy typu 400/404/parse nie świadczą o awarii providera
            return
        self._failures += 1
        cooldown = (
            self._ban_timeout if err.kind == ApiErrorKind.THROTTLED_BAN else self._reset_timeout
        )
        if err.kind == ApiErrorKind.THROTTLED_BAN or self._failures >= self._threshold:
            self._trip(cooldown)

    def _trip(self, cooldown: float) -> None:
        self._state = BreakerState.OPEN
        self._opened_at = self._clock()
        self._open_until = self._opened_at + max(0.0, cooldown)

    def _maybe_half_open(self) -> None:
        if self._state == BreakerState.OPEN and self._clock() >= self._open_until:
            self._state = BreakerState.HALF_OPEN

    def seconds_until_retry(self) -> Optional[float]:
        if self._state == BreakerState.OPEN:
            return max(0.0, self._open_until - self._clock())
        return None
