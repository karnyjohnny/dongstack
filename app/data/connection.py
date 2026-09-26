"""app/data/connection.py — fabryka połączeń SQLite + PRAGMA (specyfikacja §4.2).

Zasada R2: połączenie jest tworzone i używane WYŁĄCZNIE w wątku DbWorker
(dlatego brak check_same_thread=False — sqlite3 samo pilnuje jednego wątku).
Wyjątek: testy jednostkowe i tryb --selftest (świadome, jednowątkowe).
"""

from __future__ import annotations

import sqlite3
from typing import List, Tuple

# Nazwy PRAGMA pochodzą z tej stałej listy (whitelist) — nigdy z danych wejściowych,
# więc interpolacja nazwy jest bezpieczna i nie narusza R13 (parametryzacja wartości).
PRAGMAS: List[Tuple[str, str]] = [
    ("journal_mode", "WAL"),  # zapis nie blokuje odczytu; crash-safe
    ("synchronous", "NORMAL"),  # optimum dla WAL na HDD 5400 rpm (§4.2)
    ("foreign_keys", "ON"),
    ("busy_timeout", "3000"),
    ("cache_size", "-4000"),  # 4 MB cache stron — kompromis dla 2 GB RAM
    ("temp_store", "FILE"),  # nie marnujemy RAM na tablice tymczasowe
    ("mmap_size", "0"),  # przewidywalność na Win7
]


def open_connection(path: str, readonly: bool = False) -> sqlite3.Connection:
    """Otwiera połączenie i ustawia PRAGMA. readonly=True → URI mode=ro (NetworkWorker)."""
    if readonly:
        uri = "file:%s?mode=ro" % path.replace("\\", "/").replace("?", "%3f")
        conn = sqlite3.connect(uri, uri=True, timeout=5.0)
    else:
        conn = sqlite3.connect(path, timeout=5.0)
    conn.row_factory = sqlite3.Row
    for name, value in PRAGMAS:
        if readonly and name in ("journal_mode", "synchronous"):
            continue  # w trybie ro nie ustawiamy trybu dziennika
        conn.execute("PRAGMA %s = %s" % (name, value))
    return conn
