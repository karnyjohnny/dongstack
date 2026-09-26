"""app/services/universe_service.py — auto-sugestie uniwersów (specyfikacja §5.6).

Czysta logika (bez Qt/SQL): po dodaniu pozycji z mal_id pobieramy graf
`related_anime` i sprawdzamy, czy którykolwiek powiązany mal_id jest już
w bibliotece. Jeżeli tak — proponujemy połączenie w uniwersum:
- istniejące uniwersum członka (join), albo
- nowe uniwersum dla pary/grupy (create).
Sugestia NIGDY nie blokuje Quick Add (§5.6.1) — wywoływana asynchronicznie.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from app.domain.models import Donghua, RelationType, Universe

# relacje, które uznajemy za "tę samą franczyzę" (§4.9.1)
_UNIVERSE_RELATIONS = frozenset(
    {
        RelationType.SEQUEL,
        RelationType.PREQUEL,
        RelationType.SIDE_STORY,
        RelationType.PARENT_STORY,
        RelationType.SUMMARY,
        RelationType.FULL_STORY,
        RelationType.ALTERNATIVE_VERSION,
    }
)


@dataclass(frozen=True)
class UniverseSuggestion:
    new_donghua_id: int
    new_title: str
    universe_id: Optional[int]  # None = trzeba utworzyć nowe
    universe_name: str
    member_ids: Tuple[int, ...]  # istniejące pozycje biblioteki (bez nowej)


def _strip_season_suffix(title: str) -> str:
    """'Doupo Cangqiong 3rd Season' → 'Doupo Cangqiong' (heurystyka nazwy uniwersum)."""
    import re

    t = (title or "").strip()
    t = re.sub(
        r"\s+(?:\d+(?:st|nd|rd|th)\s+season|season\s+\d+|part\s+\d+)$", "", t, flags=re.IGNORECASE
    )
    t = re.sub(r"\s+第\s*[0-9一二三四五六七八九十]+\s*[季部篇章].*$", "", t)
    t = re.sub(r"\s+[IVX]{2,5}$", "", t.strip())
    return t.strip() or (title or "").strip()


class UniverseSuggester:
    """Decyzyjny rdzeń sugestii; wywoływany w NetworkWorker po `related`."""

    @staticmethod
    def suggest(
        new_item: Donghua,
        relations: List[Tuple[int, RelationType]],
        library_by_mal: Dict[int, Donghua],
        universes: Optional[Dict[int, Universe]] = None,
    ) -> Optional[UniverseSuggestion]:
        universes = universes or {}
        if new_item.mal_id is None:
            return None
        members: List[Donghua] = []
        seen = set()
        for mal_id, rel in relations:
            if rel not in _UNIVERSE_RELATIONS:
                continue
            if mal_id == new_item.mal_id or mal_id in seen:
                continue
            member = library_by_mal.get(mal_id)
            if member is None or member.id == new_item.id:
                continue
            seen.add(mal_id)
            members.append(member)
        if not members:
            return None

        universe_id: Optional[int] = None
        universe_name = ""
        for member in members:
            if member.universe_id is not None:
                universe_id = member.universe_id
                uni = universes.get(universe_id)
                universe_name = uni.name if uni is not None else ""
                break
        if not universe_name:
            universe_name = _strip_season_suffix(members[0].title)
        return UniverseSuggestion(
            new_donghua_id=new_item.id,
            new_title=new_item.title,
            universe_id=universe_id,
            universe_name=universe_name,
            member_ids=tuple(m.id for m in members),
        )
