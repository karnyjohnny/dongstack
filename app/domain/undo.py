"""app/domain/undo.py — komendy Undo (Biblia §9–§10: Undo zamiast Confirm).

Model: lekki stos komend w pamięci kontrolera. Każda komenda niesie dane
potrzebne do odwrócenia operacji (old/new) oraz etykietę dla SnackBara.
Trwałość: tylko w pamięci sesji (Undo nie przeżywa restartu aplikacji —
świadoma decyzja: prostota > kompletność dla operacji odwracalnych).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class UndoCommand:
    """kind: episode | status | add | remove | universe_join | universe_leave | links"""

    kind: str
    payload: Dict[str, Any]
    label: str

    def get(self, key: str, default: Any = None) -> Any:
        return self.payload.get(key, default)


class UndoStack:
    """Bounded LIFO. Domyślnie 1 aktywna komenda na SnackBar (§6.2 Biblii)."""

    def __init__(self, maxlen: int = 8) -> None:
        self._maxlen = max(1, int(maxlen))
        self._items: List[UndoCommand] = []

    def push(self, cmd: UndoCommand) -> None:
        self._items.append(cmd)
        if len(self._items) > self._maxlen:
            self._items.pop(0)

    def pop(self) -> Optional[UndoCommand]:
        if not self._items:
            return None
        return self._items.pop()

    def peek(self) -> Optional[UndoCommand]:
        if not self._items:
            return None
        return self._items[-1]

    def clear(self) -> None:
        self._items = []

    def __len__(self) -> int:
        return len(self._items)

    def __bool__(self) -> bool:
        return bool(self._items)
