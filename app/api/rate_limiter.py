"""app/api/rate_limiter.py — TokenBucket: lokalny throttling (specyfikacja §5.4).

Gwarancja: aplikacja NIGDY nie wyśle więcej niż `rate_per_sec` żądań na sekundę
do danego providera, niezależnie od liczby kliknięć użytkownika — to pierwsza
linia obrony przed HTTP 429 (rygor zadania).

Wywoływane wyłącznie z wątku NetworkWorker (blocking acquire); clock/sleeper
wstrzykiwalne → testy jednostkowe bez realnego czekania.
"""

from __future__ import annotations

import threading
import time
from typing import Callable, Optional


class TokenBucket:
    """Klasyczny token bucket: capacity pozwala na mały burst, rate na steady-state."""

    def __init__(
        self,
        rate_per_sec: float,
        capacity: int = 1,
        clock: Callable[[], float] = time.monotonic,
        sleeper: Optional[Callable[[float], None]] = None,
    ) -> None:
        if rate_per_sec <= 0:
            raise ValueError("rate_per_sec musi być > 0")
        self._rate = float(rate_per_sec)
        self._capacity = max(1, int(capacity))
        self._tokens = float(self._capacity)
        self._last = clock()
        self._clock = clock
        self._sleep = sleeper or time.sleep
        self._lock = threading.Lock()

    def _refill(self) -> None:
        now = self._clock()
        elapsed = max(0.0, now - self._last)
        if elapsed > 0:
            self._tokens = min(float(self._capacity), self._tokens + elapsed * self._rate)
            self._last = now

    def try_acquire(self, tokens: int = 1) -> bool:
        """Bez blokowania: True jeśli żetony dostępne (i pobrane)."""
        with self._lock:
            self._refill()
            if self._tokens >= tokens:
                self._tokens -= tokens
                return True
            return False

    def wait_time(self, tokens: int = 1) -> float:
        """Szacowany czas (s) do dostępności żetonów — do planowania kolejki."""
        with self._lock:
            self._refill()
            missing = tokens - self._tokens
            if missing <= 0:
                return 0.0
            return missing / self._rate

    def acquire(self, tokens: int = 1, timeout: Optional[float] = None) -> bool:
        """Blokujące pobranie żetonów. False tylko gdy timeout minął."""
        deadline = None if timeout is None else self._clock() + max(0.0, timeout)
        while True:
            with self._lock:
                self._refill()
                if self._tokens >= tokens:
                    self._tokens -= tokens
                    return True
                wait = (tokens - self._tokens) / self._rate
            if deadline is not None:
                remaining = deadline - self._clock()
                if remaining <= 0:
                    return False
                wait = min(wait, remaining)
            # mały floor, żeby nie kręcić busy-loopem na bardzo wysokim rate
            self._sleep(max(0.001, min(wait, 5.0)))
