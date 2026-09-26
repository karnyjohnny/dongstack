"""app/core/errors.py — taksonomia błędów API (specyfikacja §5.1/§5.4).

Jedna wspólna reprezentacja błędu dla wszystkich providerów (MAL, AniList),
z klasyfikacją decydującą o retry/backoff/failover.
"""

from __future__ import annotations

from enum import Enum
from typing import Optional


class ApiErrorKind(str, Enum):
    BAD_REQUEST = "bad_request"  # 400 — błąd parametrów/programistyczny, NIE retry
    AUTH = "auth"  # 401 — brak/zły Client ID, NIE retry (first-run flow)
    NOT_FOUND = "not_found"  # 404 — pozycja nie istnieje, NIE retry
    RATE_LIMITED = "rate_limited"  # 429 — retry z backoffem (+ Retry-After)
    THROTTLED_BAN = "throttled_ban"  # 403-HTML (specyfika MAL, F13) — długi cooldown + failover
    SERVER = "server"  # 5xx — retry z backoffem
    NETWORK = "network"  # timeout/brak łączności/DNS — retry z backoffem
    PARSE = "parse"  # odpowiedź 200, ale nieparsowalna — NIE retry
    PROVIDER = "provider"  # błąd wewnętrzny providera — retry ograniczony


RETRYABLE_KINDS = frozenset(
    {
        ApiErrorKind.RATE_LIMITED,
        ApiErrorKind.SERVER,
        ApiErrorKind.NETWORK,
        ApiErrorKind.THROTTLED_BAN,
    }
)


def status_to_kind(status: int, looks_like_html: bool = False) -> ApiErrorKind:
    """Mapowanie kodu HTTP → ApiErrorKind (tabela §5.1)."""
    if status == 400:
        return ApiErrorKind.BAD_REQUEST
    if status == 401:
        return ApiErrorKind.AUTH
    if status == 403:
        # MAL przy agresywnym throttlingu odpowiada 403 z generyczną stroną HTML (F13)
        return ApiErrorKind.THROTTLED_BAN if looks_like_html else ApiErrorKind.AUTH
    if status == 404:
        return ApiErrorKind.NOT_FOUND
    if status == 429:
        return ApiErrorKind.RATE_LIMITED
    if 500 <= status <= 599:
        return ApiErrorKind.SERVER
    return ApiErrorKind.PROVIDER


class ApiError(Exception):
    """Błąd warstwy API z pełnym kontekstem dla retry/failover/UI."""

    def __init__(
        self,
        kind: ApiErrorKind,
        message: str,
        provider: str = "",
        status: Optional[int] = None,
        retry_after: Optional[float] = None,
        cause: Optional[BaseException] = None,
    ) -> None:
        super().__init__(message)
        self.kind = kind
        self.message = message
        self.provider = provider
        self.status = status
        self.retry_after = retry_after
        self.cause = cause

    @property
    def retryable(self) -> bool:
        return self.kind in RETRYABLE_KINDS

    def __repr__(self) -> str:
        return "ApiError(kind=%r, provider=%r, status=%r, message=%r)" % (
            self.kind.value,
            self.provider,
            self.status,
            self.message,
        )

    def user_message(self) -> str:
        """Krótki, zorientowany na działanie komunikat UX (Biblia §49)."""
        mapping = {
            ApiErrorKind.AUTH: "Brak połączenia z MAL — sprawdź Client ID w ustawieniach.",
            ApiErrorKind.RATE_LIMITED: "MAL ogranicza zapytania — spróbuj za chwilę.",
            ApiErrorKind.THROTTLED_BAN: "MAL blokuje zapytania — przełączam na źródło awaryjne.",
            ApiErrorKind.SERVER: "Serwer MAL nie odpowiada — spróbuj ponownie.",
            ApiErrorKind.NETWORK: "Brak połączenia z internetem.",
            ApiErrorKind.NOT_FOUND: "Nie znaleziono tytułu.",
            ApiErrorKind.BAD_REQUEST: "Nie udało się wyszukać. Spróbuj ponownie.",
            ApiErrorKind.PARSE: "Nie udało się wyszukać. Spróbuj ponownie.",
            ApiErrorKind.PROVIDER: "Nie udało się wyszukać. Spróbuj ponownie.",
        }
        return mapping.get(self.kind, "Nie udało się wyszukać. Spróbuj ponownie.")
