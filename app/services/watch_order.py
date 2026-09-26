"""app/services/watch_order.py — kolejność oglądania uniwersum (specyfikacja §4.9.2).

Czysta funkcjonalność (bez Qt/SQL) — w pełni testowalna jednostkowo.

Priorytety źródeł prawdy:
  1. graf relacji MAL related_anime (twarde krawędzie: sequel/prequel),
  2. ręczny override (Donghua.universe_order),
  3. heurystyka tytułu (sezon EN/CN/rymskie) — tie-breaker i fallback,
  4. metadane: media_rank → start_year → tytuł.

Cykle twarde nigdy nie rzucają wyjątków — pozostałości dokładane wg klucza (log WARN).
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional, Sequence, Tuple

from app.domain.models import Donghua, MediaType, RelationType

# Rangowanie typów mediów: sezony → filmy → OVA/specjały → muzyka (§4.9.1)
MEDIA_RANK: Dict[MediaType, int] = {
    MediaType.TV: 0,
    MediaType.ONA: 0,
    MediaType.MOVIE: 1,
    MediaType.OVA: 2,
    MediaType.SPECIAL: 2,
    MediaType.MUSIC: 3,
    MediaType.UNKNOWN: 1,
}

_HARD_AFTER = {RelationType.SEQUEL}  # A ma sequel B  ⇒ A przed B
_HARD_BEFORE = {RelationType.PREQUEL}  # A ma prequel B ⇒ B przed A
_SOFT_AFTER = {
    RelationType.SIDE_STORY,
    RelationType.SUMMARY,
    RelationType.FULL_STORY,
    RelationType.ALTERNATIVE_VERSION,
}

# --- heurystyka sezonu w tytule -------------------------------------------------
_CN_DIGITS = {
    "零": 0,
    "一": 1,
    "二": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
}

_RE_SEASON_EN = re.compile(
    r"(?:\b(\d+)(?:st|nd|rd|th)\s+season\b)|(?:\bseason\s+(\d+)\b)|(?:\bpart\s+(\d+)\b)",
    re.IGNORECASE,
)
_RE_SEASON_CN = re.compile(r"第\s*([0-9０-９一二三四五六七八九十]+)\s*[季部篇章]")
_RE_ROMAN_TAIL = re.compile(r"\b([IVX]{2,5})\s*$")
_ROMAN_VALUES = {"I": 1, "V": 5, "X": 10}


def cn_numeral_to_int(text: str) -> Optional[int]:
    """Liczebniki chińskie do 99 (一…九十九) oraz cyfry (w tym pełnoszerokie)."""
    t = (text or "").strip()
    if not t:
        return None
    # cyfry ASCII / pełnoszerokie
    normalized = t.translate(str.maketrans("０１２３４５６７８９", "0123456789"))
    if normalized.isdigit():
        return int(normalized)
    if "十" in t:
        left, _, right = t.partition("十")
        tens = _CN_DIGITS.get(left, 1) if left else 1
        ones = _CN_DIGITS.get(right, 0) if right else 0
        if left and left not in _CN_DIGITS:
            return None
        if right and right not in _CN_DIGITS:
            return None
        return tens * 10 + ones
    if len(t) == 1 and t in _CN_DIGITS:
        return _CN_DIGITS[t]
    return None


def roman_to_int(text: str) -> Optional[int]:
    """Prosty parser rzymski (I–XXXIX) dla sufiksów tytułów."""
    t = (text or "").strip().upper()
    if not t or not all(ch in _ROMAN_VALUES for ch in t):
        return None
    total = 0
    prev = 0
    for ch in reversed(t):
        val = _ROMAN_VALUES[ch]
        if val < prev:
            total -= val
        else:
            total += val
            prev = val
    return total if 1 <= total <= 39 else None


def season_hint(title: str) -> Optional[int]:
    """Numer sezonu z tytułu (EN/CN/rymskie) albo None."""
    if not title:
        return None
    m = _RE_SEASON_EN.search(title)
    if m:
        for grp in m.groups():
            if grp:
                try:
                    return int(grp)
                except ValueError:
                    pass
    m = _RE_SEASON_CN.search(title)
    if m:
        num = cn_numeral_to_int(m.group(1))
        if num is not None and num > 0:
            return num
    m = _RE_ROMAN_TAIL.search(title.strip())
    if m:
        num = roman_to_int(m.group(1))
        if num is not None and num > 1:  # "I" w tytułach bywa literą — ignoruj 1
            return num
    return None


# --- klucz porządku --------------------------------------------------------------
def sort_key(d: Donghua) -> Tuple[int, int, int, str]:
    hint = season_hint(d.title)
    return (
        MEDIA_RANK.get(d.media_type, 1),
        hint if hint is not None else 99,
        d.start_year if d.start_year else 9999,
        (d.title or "").lower(),
    )


def _build_edges(
    members_by_mal: Dict[int, Donghua],
    relations: Dict[int, List[Tuple[int, RelationType]]],
) -> Tuple[List[Tuple[int, int]], List[Tuple[int, int]]]:
    """Z grafu relacji MAL tworzy krawędzie (hard, soft) między obecnymi członkami.

    Znormalizowany kierunek: (wcześniejszy_mal_id, późniejszy_mal_id).
    """
    hard: List[Tuple[int, int]] = []
    soft: List[Tuple[int, int]] = []
    seen_hard = set()
    seen_soft = set()
    for mal_id, rels in relations.items():
        if mal_id not in members_by_mal:
            continue
        for other_id, rel in rels:
            if other_id not in members_by_mal or other_id == mal_id:
                continue
            pair_hard: Optional[Tuple[int, int]] = None
            pair_soft: Optional[Tuple[int, int]] = None
            if rel in _HARD_AFTER:  # mal_id → sequel(other)
                pair_hard = (mal_id, other_id)
            elif rel in _HARD_BEFORE:  # mal_id → prequel(other): other przed mal_id
                pair_hard = (other_id, mal_id)
            elif rel == RelationType.PARENT_STORY:
                # "parent_story" z perspektywy side-story: other = historia nadrzędna
                pair_soft = (other_id, mal_id)
            elif rel in _SOFT_AFTER:
                pair_soft = (mal_id, other_id)
            if pair_hard is not None:
                key = tuple(sorted(pair_hard))
                if key not in seen_hard:
                    seen_hard.add(key)
                    hard.append(pair_hard)
            if pair_soft is not None:
                key = tuple(sorted(pair_soft))
                if key not in seen_soft:
                    seen_soft.add(key)
                    soft.append(pair_soft)
    return hard, soft


def _topo_with_priority(
    nodes: List[Donghua], edges: List[Tuple[int, int]]
) -> Tuple[List[Donghua], List[Donghua]]:
    """Kahn z tie-breakerem sort_key; zwraca (uporządkowane, pozostałości z cykli)."""
    by_mal = {d.mal_id: d for d in nodes if d.mal_id is not None}
    no_mal = [d for d in nodes if d.mal_id is None]

    indeg: Dict[int, int] = {mid: 0 for mid in by_mal}
    outgoing: Dict[int, List[int]] = {mid: [] for mid in by_mal}
    for a, b in edges:
        if a in by_mal and b in by_mal and a != b:
            outgoing[a].append(b)
            indeg[b] += 1

    ready = sorted(
        [mid for mid, deg in indeg.items() if deg == 0], key=lambda mid: sort_key(by_mal[mid])
    )
    ordered: List[Donghua] = []
    while ready:
        cur = ready.pop(0)
        ordered.append(by_mal[cur])
        newly = []
        for nxt in outgoing[cur]:
            indeg[nxt] -= 1
            if indeg[nxt] == 0:
                newly.append(nxt)
        if newly:
            ready.extend(newly)
            ready.sort(key=lambda mid: sort_key(by_mal[mid]))

    leftover_mids = [mid for mid, deg in indeg.items() if deg > 0]
    leftovers = sorted((by_mal[mid] for mid in leftover_mids), key=sort_key)
    # pozycje bez mal_id dokładamy wg klucza (nie uczestniczą w grafie)
    tail = sorted(no_mal, key=sort_key)
    return ordered + tail, leftovers


def _apply_soft_edges(
    ordered: List[Donghua], soft: List[Tuple[int, int]], by_mal: Dict[int, Donghua]
) -> List[Donghua]:
    """Przesuwa elementy soft-zależne ZA ich kotwicę, jeśli obecnie są przed nią."""
    pos_of = {}
    for i, d in enumerate(ordered):
        if d.mal_id is not None:
            pos_of[d.mal_id] = i
    result = list(ordered)
    for a, b in soft:
        if a not in pos_of or b not in pos_of:
            continue
        ia = result.index(by_mal[a]) if by_mal[a] in result else -1
        ib = result.index(by_mal[b]) if by_mal[b] in result else -1
        if ia < 0 or ib < 0 or ib > ia:
            continue
        item = result.pop(ib)
        ia = result.index(by_mal[a])
        result.insert(ia + 1, item)
    return result


def order_universe(
    members: Sequence[Donghua],
    relations: Optional[Dict[int, List[Tuple[int, RelationType]]]] = None,
    warn=None,
) -> List[Donghua]:
    """Zwraca członków uniwersum w kolejności oglądania (§4.9.2).

    members:    pozycje biblioteki należące do jednego uniwersum,
    relations:  mal_id → [(powiązany mal_id, RelationType)] (z related_anime),
    warn:       opcjonalny callable(str) na cykl/ anomalie (log).
    """
    items: List[Donghua] = list(members)
    if not items:
        return []

    overridden = sorted(
        [d for d in items if d.universe_order is not None],
        key=lambda d: (d.universe_order or 0, sort_key(d)),
    )
    auto = [d for d in items if d.universe_order is None]
    if not auto:
        return overridden

    members_by_mal: Dict[int, Donghua] = {}
    for d in auto:
        if d.mal_id is not None:
            members_by_mal[d.mal_id] = d

    rel_map: Dict[int, List[Tuple[int, RelationType]]] = relations or {}
    hard, soft = _build_edges(members_by_mal, rel_map)

    ordered, leftovers = _topo_with_priority(auto, hard)
    if leftovers and warn is not None:
        warn(
            "watch_order: wykryto cykl w relacjach twardych — "
            "%d pozycji dołożonych wg metadanych" % len(leftovers)
        )
        ordered = ordered + leftovers

    by_mal = {d.mal_id: d for d in ordered if d.mal_id is not None}
    ordered = _apply_soft_edges(ordered, soft, by_mal)

    return overridden + ordered
