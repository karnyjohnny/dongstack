"""app/core/timeutil.py — znaczniki czasu UTC (ISO-8601 z milisekundami).

Wszystkie timestampy w bazie są UTC w formacie 'YYYY-MM-DDTHH:MM:SS.mmmZ' —
spójne sortowanie leksykalne, brak zależności od strefy czasowej (Win7).
"""

from __future__ import annotations

from datetime import datetime, timezone


def utc_now_iso() -> str:
    """np. '2026-09-26T18:30:00.123Z'."""
    now = datetime.now(timezone.utc)
    return now.strftime("%Y-%m-%dT%H:%M:%S.") + "%03dZ" % (now.microsecond // 1000)


def utc_now_epoch() -> int:
    """Unix epoch (sekundy, UTC) — do tabel cache."""
    return int(datetime.now(timezone.utc).timestamp())
