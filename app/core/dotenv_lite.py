"""app/core/dotenv_lite.py — minimalny parser .env (bez zależności zewnętrznych).

Decyzja architektoniczna (§2.3): nie wprowadzamy python-dotenv — potrzebny jest
ułamek jego funkcjonalności, a każda zależność to koszt w freeze i łańcuchu dostaw.

Obsługa: komentarze (#), puste linie, prefix 'export ', wartości cytowane
(' " ) oraz niecytowane z komentarzem wewnętrznym (' #'). Bez interpolacji zmiennych.
"""

from __future__ import annotations

import os
import sys
from typing import Dict, List, Optional


def parse_dotenv(text: str) -> Dict[str, str]:
    """Parsuje treść pliku .env do słownika (klucz → wartość)."""
    out: Dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if not key:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]
        else:
            hash_pos = value.find(" #")
            if hash_pos >= 0:
                value = value[:hash_pos].rstrip()
        out[key] = value
    return out


def load_dotenv_file(path: str, override: bool = False) -> Dict[str, str]:
    """Wczytuje plik .env do os.environ (domyślnie NIE nadpisuje istniejących).

    Zwraca sparsowaną zawartość (pusty dict gdy plik nie istnieje / błąd odczytu).
    """
    loaded: Dict[str, str] = {}
    if not path or not os.path.isfile(path):
        return loaded
    try:
        with open(path, encoding="utf-8") as fh:
            loaded = parse_dotenv(fh.read())
    except OSError:
        return {}
    for k, v in loaded.items():
        if override or k not in os.environ:
            os.environ[k] = v
    return loaded


def find_dotenv(start_dir: Optional[str] = None) -> Optional[str]:
    """Szuka .env: CWD → katalog exe (frozen) → do 3 katalogów w górę (dev)."""
    candidates: List[str] = []
    cwd = start_dir or os.getcwd()
    candidates.append(os.path.join(cwd, ".env"))
    if getattr(sys, "frozen", False):
        candidates.append(os.path.join(os.path.dirname(str(sys.executable)), ".env"))
    parent = os.path.dirname(os.path.abspath(cwd))
    for _ in range(3):
        candidates.append(os.path.join(parent, ".env"))
        nxt = os.path.dirname(parent)
        if nxt == parent:
            break
        parent = nxt
    for cand in candidates:
        if os.path.isfile(cand):
            return cand
    return None
