"""app/api/mal_client.py — klient oficjalnego MAL API v2 (specyfikacja §5.1).

Uwierzytelnianie danych publicznych: nagłówek X-MAL-CLIENT-ID (F9) —
Client Secret NIE jest potrzebny w v1 (rygor §12).
Zweryfikowane live 2026-09-26: search/details/ranking/related_anime,
limit≤100 (limit=1500 → HTTP 400), schemat data[].node + paging.next.
"""

from __future__ import annotations

from typing import List, Optional, Tuple

import requests

from app import REPO_URL, __version__
from app.api.provider import MetadataProvider, parse_year
from app.core.errors import ApiError, ApiErrorKind, status_to_kind
from app.domain.models import (
    AnimeDetails,
    RelationType,
    SearchItem,
    normalize_media_type,
    normalize_relation_type,
)

BASE_URL = "https://api.myanimelist.net/v2"
LIMIT_MAX = 100  # zweryfikowane: 1500 → 400 bad_request; trzymamy margines
SEARCH_FIELDS = (
    "id,title,alternative_titles,main_picture,num_episodes,mean,media_type,start_date,status"
)
RELATED_FIELDS = "id,title,related_anime"
USER_AGENT = "DongStack/%s (+%s)" % (__version__, REPO_URL)


class MalClient(MetadataProvider):
    name = "mal"

    def __init__(
        self,
        client_id: str,
        session: Optional[requests.Session] = None,
        timeout: Tuple[float, float] = (5.0, 10.0),
    ) -> None:
        if not client_id or not str(client_id).strip():
            raise ApiError(ApiErrorKind.AUTH, "brak MAL_CLIENT_ID", provider=self.name)
        self._client_id = str(client_id).strip()
        self._session = session if session is not None else requests.Session()
        self._timeout = timeout
        self._headers = {
            "X-MAL-CLIENT-ID": self._client_id,
            "User-Agent": USER_AGENT,
            "Accept": "application/json",
        }

    # --- HTTP -------------------------------------------------------------------
    def _get_json(self, path: str, params: dict) -> dict:
        try:
            resp = self._session.get(
                BASE_URL + path, params=params, headers=self._headers, timeout=self._timeout
            )
        except requests.RequestException as exc:
            raise ApiError(ApiErrorKind.NETWORK, str(exc), provider=self.name, cause=exc) from exc
        return self._unwrap(resp)

    def _unwrap(self, resp) -> dict:
        if resp.status_code == 200:
            try:
                return resp.json()
            except ValueError as exc:
                raise ApiError(
                    ApiErrorKind.PARSE, "nieparsowalny JSON", provider=self.name, cause=exc
                ) from exc
        ctype = getattr(resp, "headers", {}).get("Content-Type", "") or ""
        looks_html = "text/html" in ctype.lower()
        retry_after = None
        raw_ra = getattr(resp, "headers", {}).get("Retry-After")
        if raw_ra:
            try:
                retry_after = float(raw_ra)
            except ValueError:
                retry_after = None
        raise ApiError(
            status_to_kind(resp.status_code, looks_like_html=looks_html),
            "MAL HTTP %d" % resp.status_code,
            provider=self.name,
            status=resp.status_code,
            retry_after=retry_after,
        )

    # --- API ---------------------------------------------------------------------
    def search(self, query: str, limit: int = 20) -> List[SearchItem]:
        limit = max(1, min(int(limit), LIMIT_MAX))
        data = self._get_json("/anime", {"q": query, "limit": limit, "fields": SEARCH_FIELDS})
        out: List[SearchItem] = []
        for entry in data.get("data", []) or []:
            node = entry.get("node") or {}
            item = self._node_to_item(node)
            if item is not None:
                out.append(item)
        return out

    def details(self, ext_id: int) -> AnimeDetails:
        data = self._get_json(
            "/anime/%d" % int(ext_id), {"fields": SEARCH_FIELDS + ",synopsis,genres,related_anime"}
        )
        item = self._node_to_item(data)
        if item is None:
            raise ApiError(ApiErrorKind.PARSE, "pusty node szczegółów", provider=self.name)
        return AnimeDetails(
            item=item,
            synopsis=data.get("synopsis"),
            genres=tuple(g.get("name", "") for g in data.get("genres", []) or []),
            air_status=data.get("status"),
            relations=self._parse_relations(data),
        )

    def related(self, mal_id: int) -> List[Tuple[int, RelationType]]:
        data = self._get_json("/anime/%d" % int(mal_id), {"fields": RELATED_FIELDS})
        return self._parse_relations(data)

    # --- parsowanie -----------------------------------------------------------------
    @staticmethod
    def _node_to_item(node: dict) -> Optional[SearchItem]:
        if not node or "id" not in node:
            return None
        pictures = node.get("main_picture") or {}
        alt = None
        alts = node.get("alternative_titles") or {}
        alt = alts.get("en") or alts.get("ja") or None
        mean = node.get("mean")
        return SearchItem(
            provider="mal",
            ext_id=int(node["id"]),
            mal_id=int(node["id"]),
            title=node.get("title") or "",
            title_alt=alt,
            cover_url=pictures.get("medium") or pictures.get("large"),
            total_episodes=int(node.get("num_episodes") or 0),
            year=parse_year(node.get("start_date")),
            media_type=normalize_media_type(node.get("media_type")),
            mean_score=float(mean) if mean is not None else None,
        )

    @staticmethod
    def _parse_relations(data: dict) -> List[Tuple[int, RelationType]]:
        out: List[Tuple[int, RelationType]] = []
        for rel in data.get("related_anime", []) or []:
            node = rel.get("node") or {}
            rid = node.get("id")
            if rid is None:
                continue
            out.append((int(rid), normalize_relation_type(rel.get("relation_type"))))
        return out
