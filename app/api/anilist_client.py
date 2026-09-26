"""app/api/anilist_client.py — provider awaryjny AniList GraphQL (specyfikacja §5.2).

Bez uwierzytelnienia; limit 30 req/min (stan zdegradowany) → TokenBucket 0.4/s.
UWAGA: błędy GraphQL przychodzą też przy HTTP 200 (errors[]) — parser zawsze
sprawdza `errors`; 429 niesie Retry-After i X-RateLimit-*.
"""

from __future__ import annotations

from typing import List, Optional, Tuple

import requests

from app import REPO_URL, __version__
from app.api.provider import MetadataProvider
from app.core.errors import ApiError, ApiErrorKind, status_to_kind
from app.domain.models import (
    AnimeDetails,
    RelationType,
    SearchItem,
    normalize_media_type,
    normalize_relation_type,
)

ENDPOINT = "https://graphql.anilist.co"
USER_AGENT = "DongStack/%s (+%s)" % (__version__, REPO_URL)

SEARCH_QUERY = """
query ($q: String, $per: Int) {
  Page(page: 1, perPage: $per) {
    media(search: $q, type: ANIME, sort: SEARCH_MATCH) {
      id idMal
      title { romaji english native }
      episodes status seasonYear format averageScore
      coverImage { medium large }
    }
  }
}
"""

COVER_QUERY = """
query ($malId: Int) {
  Media(idMal: $malId) {
    coverImage { medium large }
  }
}
"""

RELATED_QUERY = """
query ($id: Int) {
  Media(id: $id) {
    relations { edges { relationType node { id idMal } } }
  }
}
"""


class AnilistClient(MetadataProvider):
    name = "anilist"

    def __init__(
        self, session: Optional[requests.Session] = None, timeout: Tuple[float, float] = (5.0, 10.0)
    ) -> None:
        self._session = session if session is not None else requests.Session()
        self._timeout = timeout

    # --- HTTP ------------------------------------------------------------------
    def _post(self, query: str, variables: dict) -> dict:
        try:
            resp = self._session.post(
                ENDPOINT,
                json={"query": query, "variables": variables},
                headers={"Content-Type": "application/json", "User-Agent": USER_AGENT},
                timeout=self._timeout,
            )
        except requests.RequestException as exc:
            raise ApiError(ApiErrorKind.NETWORK, str(exc), provider=self.name, cause=exc) from exc

        retry_after = None
        raw_ra = getattr(resp, "headers", {}).get("Retry-After")
        if raw_ra:
            try:
                retry_after = float(raw_ra)
            except ValueError:
                retry_after = None

        if resp.status_code != 200:
            raise ApiError(
                status_to_kind(resp.status_code),
                "AniList HTTP %d" % resp.status_code,
                provider=self.name,
                status=resp.status_code,
                retry_after=retry_after,
            )
        try:
            body = resp.json()
        except ValueError as exc:
            raise ApiError(
                ApiErrorKind.PARSE, "nieparsowalny JSON", provider=self.name, cause=exc
            ) from exc
        errors = body.get("errors") or []
        if errors:
            err_status = None
            for err in errors:
                st = (err or {}).get("status")
                if st:
                    err_status = int(st)
                    break
            if err_status == 429:
                raise ApiError(
                    ApiErrorKind.RATE_LIMITED,
                    "AniList rate limit",
                    provider=self.name,
                    status=429,
                    retry_after=retry_after,
                )
            raise ApiError(
                ApiErrorKind.PROVIDER,
                str(errors[0].get("message", "GraphQL error"))[:120],
                provider=self.name,
            )
        return body.get("data") or {}

    # --- API ---------------------------------------------------------------------
    def search(self, query: str, limit: int = 20) -> List[SearchItem]:
        data = self._post(SEARCH_QUERY, {"q": query, "per": max(1, min(int(limit), 50))})
        out: List[SearchItem] = []
        for media in (data.get("Page") or {}).get("media", []) or []:
            item = self._media_to_item(media)
            if item is not None:
                out.append(item)
        return out

    def details(self, ext_id: int) -> AnimeDetails:
        data = self._post(RELATED_QUERY, {"id": int(ext_id)})
        media = data.get("Media") or {}
        item = SearchItem(provider="anilist", ext_id=int(ext_id), mal_id=None, title="")
        return AnimeDetails(item=item, relations=self._parse_relations(media))

    def covers_for_mal(self, mal_id: int) -> List[str]:
        """Zapasowe URL-e okładki (CDN AniList, inny host niż MAL) dla mal_id."""
        data = self._post(COVER_QUERY, {"malId": int(mal_id)})
        cover = ((data.get("Media") or {}).get("coverImage")) or {}
        return [u for u in (cover.get("medium"), cover.get("large")) if u]

    def related(self, mal_id: int) -> List[Tuple[int, RelationType]]:
        """UWAGA: AniList kluczuje własnym id — wywołujący mapuje mal_id→anilist_id."""
        data = self._post(RELATED_QUERY, {"id": int(mal_id)})
        return self._parse_relations(data.get("Media") or {})

    # --- parsowanie -----------------------------------------------------------------
    @staticmethod
    def _media_to_item(media: dict) -> Optional[SearchItem]:
        if not media or "id" not in media:
            return None
        titles = media.get("title") or {}
        primary = titles.get("english") or titles.get("romaji") or ""
        alt = titles.get("native") or (titles.get("romaji") if titles.get("english") else None)
        cover = media.get("coverImage") or {}
        score = media.get("averageScore")
        id_mal = media.get("idMal")
        return SearchItem(
            provider="anilist",
            ext_id=int(media["id"]),
            mal_id=int(id_mal) if id_mal else None,
            title=primary,
            title_alt=alt,
            cover_url=cover.get("medium") or cover.get("large"),
            total_episodes=int(media.get("episodes") or 0),
            year=media.get("seasonYear"),
            media_type=normalize_media_type(media.get("format")),
            mean_score=(float(score) / 10.0) if score else None,
        )

    @staticmethod
    def _parse_relations(media: dict) -> List[Tuple[int, RelationType]]:
        out: List[Tuple[int, RelationType]] = []
        edges = ((media.get("relations") or {}).get("edges", [])) or []
        for edge in edges:
            node = edge.get("node") or {}
            id_mal = node.get("idMal")
            if not id_mal:
                continue  # graf uniwersów jest mal_id-centryczny (§5.0)
            out.append((int(id_mal), normalize_relation_type(edge.get("relationType"))))
        return out
