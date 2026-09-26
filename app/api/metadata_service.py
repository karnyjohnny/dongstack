"""app/api/metadata_service.py — fasada providerów (specyfikacja §5.0, §4.7).

Polityka:
- cache-first (TTL: search 6 h, related 7 dni); przestarzałe wpisy serwowane tylko
  jako graceful degradation przy błędzie providera (allow_stale),
- failover: provider preferowany (domyślnie MAL, D7-rozszerzenie) → drugi provider,
  gdy breaker OTWARTY lub błędy retryable wyczerpane,
- bucket rate-limitu pobierany PRZED każdą próbą providera (callback bucket_for),
- cache przechowuje JSON znormalizowanych modeli (stabilny contract parsera).
"""

from __future__ import annotations

import json
from dataclasses import asdict
from typing import Callable, Dict, List, Optional, Tuple

from app.core.errors import ApiError, ApiErrorKind
from app.core.logging_setup import get_logger
from app.data.api_cache import details_key, related_key, search_key
from app.domain.models import RelationType, SearchItem

log = get_logger("api.service")

TTL_SEARCH_S = 6 * 3600
TTL_RELATED_S = 7 * 86400
TTL_DETAILS_S = 7 * 86400


class SearchOutcome:
    __slots__ = ("items", "provider", "from_cache", "fresh")

    def __init__(self, items, provider, from_cache, fresh):
        self.items = items
        self.provider = provider
        self.from_cache = from_cache
        self.fresh = fresh


class MetadataService:
    def __init__(
        self,
        providers: Dict[str, object],
        cache_get: Optional[Callable[[str, bool], Optional[Tuple[str, bool]]]] = None,
        cache_set: Optional[Callable[[str, str, str, int], None]] = None,
        preferred: str = "mal",
        breakers: Optional[Dict[str, object]] = None,
        bucket_for: Optional[Callable[[str], object]] = None,
    ) -> None:
        self._providers = providers
        self._cache_get = cache_get or (lambda key, allow_stale: None)
        self._cache_set = cache_set or (lambda key, provider, payload, ttl: None)
        self._preferred = preferred if preferred in providers else next(iter(providers), None)
        self._breakers = breakers or {}
        self._bucket_for = bucket_for

    @property
    def preferred(self) -> Optional[str]:
        return self._preferred

    def providers(self) -> Dict[str, object]:
        return dict(self._providers)

    def attach_provider(
        self, name: str, provider: object, breaker: Optional[object] = None, preferred: bool = True
    ) -> None:
        """Dołącza providera w locie (first-run Client ID bez restartu, §5.5)."""
        self._providers[name] = provider
        if breaker is not None:
            self._breakers[name] = breaker
        if preferred:
            self._preferred = name

    def _order(self) -> List[str]:
        names = list(self._providers.keys())
        if self._preferred in names:
            names.remove(self._preferred)
            names.insert(0, self._preferred)
        return names

    def _breaker_allows(self, name: str) -> bool:
        breaker = self._breakers.get(name)
        return breaker.allow_request() if breaker is not None else True

    def _acquire(self, name: str) -> None:
        if self._bucket_for is not None:
            bucket = self._bucket_for(name)
            if bucket is not None:
                bucket.acquire(timeout=30.0)

    # --- wyszukiwanie ------------------------------------------------------------
    def search(self, query: str, limit: int = 20) -> SearchOutcome:
        last_err: Optional[ApiError] = None
        for name in self._order():
            key = search_key(name, query, limit)
            hit = self._cache_get(key, True)
            if hit is not None:
                parsed = self._items_from_json(hit[0])
                if parsed is not None and hit[1]:
                    return SearchOutcome(parsed, name, True, True)
            if not self._breaker_allows(name):
                continue
            try:
                self._acquire(name)
                items = self._providers[name].search(query, limit)
            except ApiError as exc:
                last_err = exc
                self._record(name, exc)
                continue
            breaker = self._breakers.get(name)
            if breaker is not None:
                breaker.record_success()
            self._cache_set(key, name, self._items_to_json(items), TTL_SEARCH_S)
            return SearchOutcome(items, name, False, True)

        # wszystkie próby nieudane → graceful degradation ze stale cache (§4.7)
        for name in self._order():
            hit = self._cache_get(search_key(name, query, limit), True)
            if hit is not None:
                items = self._items_from_json(hit[0])
                if items is not None:
                    log.info("serwuję stale cache dla zapytania %r", query)
                    return SearchOutcome(items, name, True, False)
        if last_err is not None:
            raise last_err
        raise ApiError(ApiErrorKind.PROVIDER, "brak dostępnego providera", provider="")

    # --- szczegóły (backfill okładek, M6-fix) -----------------------------------------
    def details(self, ext_id: int):
        key = details_key(self.preferred or next(iter(self._providers)), ext_id)
        hit = self._cache_get(key, True)
        if hit is not None and hit[1]:
            parsed = self._items_from_json(hit[0])
            if parsed:
                return parsed[0]
        last_err: Optional[ApiError] = None
        for name in self._order():
            if not self._breaker_allows(name):
                continue
            try:
                self._acquire(name)
                det = self._providers[name].details(ext_id)
            except ApiError as exc:
                last_err = exc
                self._record(name, exc)
                continue
            breaker = self._breakers.get(name)
            if breaker is not None:
                breaker.record_success()
            self._cache_set(key, name, self._items_to_json([det.item]), TTL_DETAILS_S)
            return det.item
        if hit is not None:
            parsed = self._items_from_json(hit[0])
            if parsed:
                return parsed[0]
        if last_err is not None:
            raise last_err
        raise ApiError(ApiErrorKind.PROVIDER, "details niedostępne", provider="")

    # --- relacje (uniwersa) ---------------------------------------------------------
    def related(self, mal_id: int) -> List[Tuple[int, RelationType]]:
        key = related_key(mal_id)
        hit = self._cache_get(key, True)
        stale: Optional[List[Tuple[int, RelationType]]] = None
        if hit is not None:
            parsed = self._relations_from_json(hit[0])
            if parsed is not None:
                if hit[1]:
                    return parsed
                stale = parsed
        for name in self._order():
            if not self._breaker_allows(name):
                continue
            provider = self._providers[name]
            try:
                self._acquire(name)
                rels = provider.related(mal_id)
            except ApiError as exc:
                self._record(name, exc)
                continue
            breaker = self._breakers.get(name)
            if breaker is not None:
                breaker.record_success()
            self._cache_set(key, name, self._relations_to_json(rels), TTL_RELATED_S)
            return rels
        if stale is not None:
            return stale
        raise ApiError(ApiErrorKind.PROVIDER, "related niedostępne", provider="")

    # --- pomocnicze -------------------------------------------------------------------
    def _record(self, name: str, exc: ApiError) -> None:
        breaker = self._breakers.get(name)
        if breaker is not None:
            breaker.record_failure(exc)
        log.warning("provider %s: %r", name, exc)

    @staticmethod
    def _items_to_json(items: List[SearchItem]) -> str:
        payload = []
        for it in items:
            d = asdict(it)
            d["media_type"] = it.media_type.value
            payload.append(d)
        return json.dumps(payload, ensure_ascii=False)

    @staticmethod
    def _items_from_json(payload: str) -> Optional[List[SearchItem]]:
        try:
            raw = json.loads(payload)
        except ValueError:
            return None
        out: List[SearchItem] = []
        for d in raw:
            try:
                d = dict(d)
                d["media_type"] = _media_type_from_value(d.get("media_type"))
                out.append(SearchItem(**d))
            except (TypeError, ValueError):
                continue
        return out

    @staticmethod
    def _relations_to_json(rels) -> str:
        return json.dumps([[mid, rel.value] for mid, rel in rels])

    @staticmethod
    def _relations_from_json(payload: str) -> Optional[List[Tuple[int, RelationType]]]:
        try:
            raw = json.loads(payload)
        except ValueError:
            return None
        out = []
        for pair in raw:
            try:
                out.append((int(pair[0]), RelationType(pair[1])))
            except (ValueError, IndexError):
                continue
        return out


def _media_type_from_value(value):
    from app.domain.models import MediaType

    try:
        return MediaType(value)
    except ValueError:
        return MediaType.UNKNOWN
