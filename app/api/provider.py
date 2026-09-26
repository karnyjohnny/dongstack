"""app/api/provider.py — wspólny interfejs providerów metadanych (specyfikacja §5.0).

Kanon klucza zewnętrznego: mal_id (AniList dostarcza idMal). Providerzy rzucają
WYŁĄCZNIE ApiError — żadne surowe wyjątki sieciowe nie wychodzą na zewnątrz.
"""

from __future__ import annotations

from typing import List, Tuple

from app.domain.models import AnimeDetails, RelationType, SearchItem


class MetadataProvider:
    """ABC providera. Implementacje: MalClient, AnilistClient."""

    name = ""

    def search(self, query: str, limit: int = 20) -> List[SearchItem]:
        raise NotImplementedError

    def details(self, ext_id: int) -> AnimeDetails:
        raise NotImplementedError

    def related(self, mal_id: int) -> List[Tuple[int, RelationType]]:
        """Graf relacji (sequel/prequel/side_story…) — podstawa uniwersów (§4.9)."""
        raise NotImplementedError


def parse_year(raw) -> int | None:
    """'2018-03-03' → 2018; tolerancyjnie."""
    if not raw:
        return None
    text = str(raw)[:4]
    try:
        return int(text)
    except ValueError:
        return None
