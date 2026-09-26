"""app/domain/models.py — niemutowalne modele domenowe (frozen dataclasses).

Zasady (specyfikacja §3.1, §16):
- obiekty przekazywane sygnałami Qt między wątkami są NIEMUTOWALNE (frozen),
- baseline składni Python 3.8: typing.List/Optional/…, zero `X | Y`,
- GUI nie zna SQL; modele nie znają Qt (poza QImage w sygnaturach workerów).
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
from typing import Dict, List, Optional, Tuple


class Status(str, Enum):
    WATCHING = "watching"
    COMPLETED = "completed"
    PLANNED = "planned"
    DROPPED = "dropped"

    @classmethod
    def values(cls) -> List[str]:
        return [s.value for s in cls]


class MediaType(str, Enum):
    TV = "tv"
    ONA = "ona"
    OVA = "ova"
    MOVIE = "movie"
    SPECIAL = "special"
    MUSIC = "music"
    UNKNOWN = "unknown"


_MEDIA_ALIASES: Dict[str, MediaType] = {
    "tv": MediaType.TV,
    "tv_short": MediaType.TV,  # AniList TV_SHORT
    "tv special": MediaType.SPECIAL,
    "ona": MediaType.ONA,
    "web": MediaType.ONA,  # AniList WEB → odpowiednik ONA
    "ova": MediaType.OVA,
    "special": MediaType.SPECIAL,
    "movie": MediaType.MOVIE,
    "music": MediaType.MUSIC,
    "cm": MediaType.SPECIAL,  # AniList CM (commercial) → special
    "pv": MediaType.SPECIAL,  # AniList PV → special
}


def normalize_media_type(raw: Optional[str]) -> MediaType:
    """Normalizacja MAL/AniList → MediaType (tolerancyjna, nie rzuca wyjątków)."""
    if not raw:
        return MediaType.UNKNOWN
    key = str(raw).strip().lower().replace("-", "_")
    return _MEDIA_ALIASES.get(key, MediaType.UNKNOWN)


class RelationType(str, Enum):
    """Relacje MAL related_anime (zweryfikowane live — F15)."""

    SEQUEL = "sequel"
    PREQUEL = "prequel"
    SIDE_STORY = "side_story"
    PARENT_STORY = "parent_story"
    SUMMARY = "summary"
    ALTERNATIVE_VERSION = "alternative_version"
    FULL_STORY = "full_story"
    OTHER = "other"


_RELATION_ALIASES: Dict[str, RelationType] = {
    "sequel": RelationType.SEQUEL,
    "prequel": RelationType.PREQUEL,
    "side story": RelationType.SIDE_STORY,
    "side_story": RelationType.SIDE_STORY,
    "parent story": RelationType.PARENT_STORY,
    "parent_story": RelationType.PARENT_STORY,
    "summary": RelationType.SUMMARY,
    "alternative version": RelationType.ALTERNATIVE_VERSION,
    "alternative_version": RelationType.ALTERNATIVE_VERSION,
    "full story": RelationType.FULL_STORY,
    "full_story": RelationType.FULL_STORY,
    # AniList ( GraphQL enum, lower-case po normalizacji)
    "adaptation": RelationType.ALTERNATIVE_VERSION,
    "spin_off": RelationType.SIDE_STORY,
    "alternative": RelationType.ALTERNATIVE_VERSION,
    "character": RelationType.OTHER,
    "other": RelationType.OTHER,
}


def normalize_relation_type(raw: Optional[str]) -> RelationType:
    if not raw:
        return RelationType.OTHER
    key = str(raw).strip().lower().replace("-", "_")
    return _RELATION_ALIASES.get(key, RelationType.OTHER)


class SortMode(str, Enum):
    UPDATED = "updated"  # domyślne (Biblia §12)
    ALPHA = "alpha"
    ADDED = "added"
    PROGRESS = "progress"
    WATCH_ORDER = "watch_order"  # grupowanie uniwersów (§6.7)


@dataclass(frozen=True)
class Donghua:
    """Pozycja biblioteki. Niemutowalna — zmiany przez dataclasses.replace()."""

    id: int = 0
    mal_id: Optional[int] = None
    anilist_id: Optional[int] = None
    provider: str = "manual"  # mal | anilist | manual
    title: str = ""
    title_alt: Optional[str] = None
    total_episodes: int = 0  # 0 = nieznane / w emisji
    current_episode: int = 0
    status: Status = Status.PLANNED
    score: Optional[int] = None
    media_type: MediaType = MediaType.UNKNOWN
    start_year: Optional[int] = None
    cover_key: Optional[str] = None
    universe_id: Optional[int] = None
    universe_order: Optional[int] = None
    note: Optional[str] = None
    added_at: str = ""
    updated_at: str = ""
    deleted_at: Optional[str] = None

    # --- pochodne -----------------------------------------------------------
    @property
    def progress_ratio(self) -> float:
        if self.total_episodes <= 0:
            return 0.0
        return max(0.0, min(1.0, float(self.current_episode) / float(self.total_episodes)))

    @property
    def is_finished(self) -> bool:
        return self.total_episodes > 0 and self.current_episode >= self.total_episodes

    # --- operacje (zwracają NOWE obiekty) ------------------------------------
    def clamped_episode(self, episode: int) -> int:
        ep = max(0, int(episode))
        if self.total_episodes > 0:
            ep = min(ep, self.total_episodes)
        return ep

    def with_episode(self, episode: int, updated_at: str) -> Donghua:
        """Zmiana odcinka + auto-statusy (Biblia §10):
        watching + max → completed; planned + >0 → watching; completed + poniżej max → watching.
        """
        ep = self.clamped_episode(episode)
        status = self.status
        if status == Status.WATCHING and self.total_episodes > 0 and ep >= self.total_episodes:
            status = Status.COMPLETED
        elif status == Status.COMPLETED and self.total_episodes > 0 and ep < self.total_episodes:
            status = Status.WATCHING
        if status == Status.PLANNED and ep > 0:
            status = Status.WATCHING
        return replace(self, current_episode=ep, status=status, updated_at=updated_at)

    def with_status(self, status: Status, updated_at: str) -> Donghua:
        return replace(self, status=status, updated_at=updated_at)


@dataclass(frozen=True)
class StreamingLink:
    """Link streamingowy: TAG (etykieta/domena) + URL — wolna treść (feedback M6-fix).

    TAG domyślnie auto-wycinany z domeny URL (netloc), edytowalny ręcznie.
    """

    id: int = 0
    donghua_id: int = 0
    tag: str = ""
    url: str = ""
    label: Optional[str] = None
    position: int = 0


@dataclass(frozen=True)
class SearchItem:
    """Znormalizowany wynik wyszukiwania (MAL lub AniList) — wspólny mianownik §5.0."""

    provider: str  # "mal" | "anilist"
    ext_id: int  # id w systemie providera
    mal_id: Optional[int]  # kanoniczny klucz (AniList: idMal)
    title: str
    title_alt: Optional[str] = None
    cover_url: Optional[str] = None
    total_episodes: int = 0
    year: Optional[int] = None
    media_type: MediaType = MediaType.UNKNOWN
    mean_score: Optional[float] = None


@dataclass(frozen=True)
class AnimeDetails:
    """Szczegóły pozycji + graf relacji (related_anime — podstawa uniwersów §4.9)."""

    item: SearchItem
    synopsis: Optional[str] = None
    genres: Tuple[str, ...] = ()
    air_status: Optional[str] = None
    relations: Tuple[Tuple[int, RelationType], ...] = ()  # (mal_id, relacja)


@dataclass(frozen=True)
class Universe:
    """Franczyza/uniwersum — grupa serii uporządkowanych watch_order (§4.9)."""

    id: int = 0
    name: str = ""
    mal_anchor_id: Optional[int] = None
    created_at: str = ""


@dataclass(frozen=True)
class DisplayHeader:
    """Nagłówek grupy uniwersum na liście głównej (§6.7) — wpis display-modelu."""

    universe_id: int
    name: str
    badge: str
    collapsed: bool = False
