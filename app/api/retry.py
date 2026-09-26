"""app/api/retry.py — exponential backoff z jitterem + Retry-After (specyfikacja §5.4).

Polityka domyślna (MAL/AniList):
    delay(n) = min(base * factor^n, max_delay) * (1 ± jitter)
    jeśli Retry-After obecny → delay = max(delay_backoff, min(retry_after, max_delay))
    attempts = 4, base = 1.0 s, factor = 2, max_delay = 60 s, jitter = 0.2

Czysta logika (bez sieci, bez Qt) — clock/random wstrzykiwalne w testach.
"""

from __future__ import annotations

import random
import time
from dataclasses import dataclass
from typing import Callable, Optional

from app.core.errors import ApiError, ApiErrorKind


@dataclass(frozen=True)
class RetryPolicy:
    attempts: int = 4  # łączna liczba PRÓB (1 start + 3 retry) — patrz should_retry
    base_delay: float = 1.0
    factor: float = 2.0
    max_delay: float = 60.0
    jitter: float = 0.2  # ±20%
    ban_cooldown: float = 300.0  # THROTTLED_BAN (403-HTML MAL) — długi cooldown (§5.1)

    def delay_for(
        self,
        attempt: int,
        retry_after: Optional[float] = None,
        kind: Optional[ApiErrorKind] = None,
        rand: Callable[[], float] = random.random,
    ) -> float:
        """Opóźnienie przed próbą nr `attempt` (0-based: 0 = pierwszy retry)."""
        attempt = max(0, int(attempt))
        raw = min(self.base_delay * (self.factor**attempt), self.max_delay)
        spread = raw * self.jitter
        jittered = raw + spread * (rand() * 2.0 - 1.0)
        delay = max(0.0, jittered)
        if kind == ApiErrorKind.THROTTLED_BAN:
            delay = max(delay, self.ban_cooldown)
        if retry_after is not None and retry_after > 0:
            delay = max(delay, min(float(retry_after), self.max_delay))
        return min(delay, max(self.max_delay, self.ban_cooldown))

    def should_retry(self, err: ApiError, attempts_done: int) -> bool:
        """attempts_done = liczba wykonanych prób (start=1)."""
        if not err.retryable:
            return False
        return attempts_done < self.attempts


class BackoffSleeper:
    """Wykonawca opóźnień w wątku workera (prerywalny kooperacyjnie przez should_stop)."""

    def __init__(
        self,
        sleep: Callable[[float], None] = time.sleep,
        should_stop: Optional[Callable[[], bool]] = None,
    ) -> None:
        self._sleep = sleep
        self._should_stop = should_stop or (lambda: False)

    def sleep(self, seconds: float) -> bool:
        """Śpi w kawałkach ≤0.5 s; zwraca False jeśli zażądano stopu."""
        remaining = max(0.0, float(seconds))
        while remaining > 0:
            if self._should_stop():
                return False
            chunk = min(0.5, remaining)
            self._sleep(chunk)
            remaining -= chunk
        return not self._should_stop()
