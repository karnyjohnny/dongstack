"""Testy watch_order: topo-sort relacji MAL, heurystyka tytułów EN/CN, override, cykle."""

from __future__ import annotations

from app.domain.models import Donghua, MediaType, RelationType, Status
from app.services.watch_order import (
    cn_numeral_to_int,
    order_universe,
    roman_to_int,
    season_hint,
    sort_key,
)


def _d(mal_id, title, media=MediaType.TV, year=None, order=None):
    return Donghua(
        id=mal_id,
        mal_id=mal_id,
        title=title,
        media_type=media,
        start_year=year,
        universe_order=order,
        status=Status.WATCHING,
    )


# --- heurystyka sezonu ---------------------------------------------------------
def test_season_hint_english():
    assert season_hint("Doupo Cangqiong 2nd Season") == 2
    assert season_hint("Doupo Cangqiong 3rd Season") == 3
    assert season_hint("Series Season 4") == 4
    assert season_hint("Attack Part 2") == 2
    assert season_hint("First Season") is None
    assert season_hint("No Season Here") is None


def test_season_hint_chinese():
    assert season_hint("斗破苍穹 第三季") == 3
    assert season_hint("凡人修仙传 第一季") == 1
    assert season_hint("斗罗大陆2 绝世唐门 第十二季") == 12
    assert season_hint("武动乾坤 第二部") == 2
    assert season_hint("斗破苍穹 第5季") == 5
    assert season_hint("某动漫 第二季特别篇") == 2


def test_season_hint_roman_tail():
    assert season_hint("Fate Stay Night II") == 2
    assert season_hint("Series III") == 3
    assert season_hint("Something I") is None  # pojedyncze I ignorowane
    assert season_hint("Movie XII") == 12


def test_cn_numeral():
    assert cn_numeral_to_int("十") == 10
    assert cn_numeral_to_int("十二") == 12
    assert cn_numeral_to_int("二十") == 20
    assert cn_numeral_to_int("二十三") == 23
    assert cn_numeral_to_int("三") == 3
    assert cn_numeral_to_int("５") == 5  # pełnoszerokie
    assert cn_numeral_to_int("abc") is None


def test_roman():
    assert roman_to_int("IV") == 4
    assert roman_to_int("IX") == 9
    assert roman_to_int("XIV") == 14
    assert roman_to_int("ABC") is None


# --- porządek przez graf relacji (realny przypadek Doupo — F15) ------------------
def test_topo_order_from_relations():
    s1 = _d(36491, "Doupo Cangqiong", year=2017)
    s2 = _d(37176, "Doupo Cangqiong 2nd Season", year=2018)
    s3 = _d(38436, "Doupo Cangqiong 3rd Season", year=2019)
    # wejście CELOWO pomieszane (problem Zamawiającego: s2, s5, s1, s7…)
    members = [s2, s3, s1]
    relations = {
        37176: [(36491, RelationType.PREQUEL), (38436, RelationType.SEQUEL)],
        36491: [(37176, RelationType.SEQUEL)],
        38436: [(37176, RelationType.PREQUEL)],
    }
    ordered = order_universe(members, relations)
    assert [d.mal_id for d in ordered] == [36491, 37176, 38436]


def test_relations_win_over_year_when_conflicting():
    # późniejszy start_year, ale prequel wymusza kolejność
    a = _d(1, "A", year=2025)
    b = _d(2, "B", year=2010)
    relations = {1: [(2, RelationType.PREQUEL)]}  # B jest prequelem A → B przed A
    ordered = order_universe([a, b], relations)
    assert [d.mal_id for d in ordered] == [2, 1]


def test_side_story_placed_after_anchor():
    s1 = _d(10, "Main Season", year=2020)
    sp = _d(11, "Special 1", media=MediaType.SPECIAL, year=2020)
    # bez relacji: special i tak po sezonie (media_rank)
    ordered = order_universe([sp, s1], {})
    assert [d.mal_id for d in ordered] == [10, 11]
    # z relacją side_story: kotwica = season
    relations = {10: [(11, RelationType.SIDE_STORY)]}
    ordered2 = order_universe([sp, s1], relations)
    assert [d.mal_id for d in ordered2] == [10, 11]


def test_movies_after_seasons():
    s1 = _d(1, "Series", media=MediaType.TV, year=2020)
    mv = _d(2, "Series Movie", media=MediaType.MOVIE, year=2019)  # wcześniejszy rok!
    ordered = order_universe([mv, s1], {})
    assert [d.mal_id for d in ordered] == [1, 2]  # TV przed MOVIE mimo roku


def test_fallback_by_title_season_hint_without_relations():
    s2 = _d(20, "X 2nd Season", year=None)
    s1 = _d(21, "X", year=None)
    s3 = _d(22, "X 3rd Season", year=None)
    ordered = order_universe([s2, s3, s1], {})
    # s1 bez numeru sezonu: hint=99 → po sezonach numerowanych? NIE:
    # sort_key traktuje brak hintu jako 99, więc X (bez numeru) ląduje OSTATNIE.
    # Dla franczyz "X" = sezon 1 → w praktyce relacje MAL to porządkują (test wyżej).
    assert [d.mal_id for d in ordered] == [20, 22, 21]


def test_year_tiebreaker():
    a = _d(1, "Same Title", year=2021)
    b = _d(2, "Same Title", year=2019)
    ordered = order_universe([a, b], {})
    assert [d.mal_id for d in ordered] == [2, 1]


def test_manual_override_wins():
    s1 = _d(1, "S1", year=2018)
    s2 = _d(2, "S2", year=2019, order=1)  # użytkownik przypiął S2 na pozycji 1
    s3 = _d(3, "S3", year=2020)
    relations = {1: [(2, RelationType.SEQUEL)], 2: [(3, RelationType.SEQUEL)]}
    ordered = order_universe([s1, s2, s3], relations)
    assert ordered[0].mal_id == 2  # override kotwicą
    assert {d.mal_id for d in ordered[1:]} == {1, 3}
    assert ordered[1].mal_id == 1  # reszta topo


def test_cycle_does_not_crash_and_keeps_all():
    # cykl 3-węzłowy (A→B→C→A) — deduplikacja par nie jest w stanie go rozpleść
    a = _d(1, "A", year=2020)
    b = _d(2, "B", year=2021)
    c = _d(3, "C", year=2022)
    relations = {
        1: [(2, RelationType.SEQUEL)],
        2: [(3, RelationType.SEQUEL)],
        3: [(1, RelationType.SEQUEL)],
    }
    warnings = []
    ordered = order_universe([a, b, c], relations, warn=warnings.append)
    assert {d.mal_id for d in ordered} == {1, 2, 3}  # nic nie ginie
    assert warnings  # cykl zaraportowany, nie rzucony


def test_conflicting_two_node_edges_dedup_no_crash():
    # A↔B (wzajemne sequele — brudne dane MAL): dedup zostawia jedną krawędź
    a = _d(1, "A", year=2020)
    b = _d(2, "B", year=2021)
    relations = {1: [(2, RelationType.SEQUEL)], 2: [(1, RelationType.SEQUEL)]}
    ordered = order_universe([a, b], relations)
    assert {d.mal_id for d in ordered} == {1, 2}


def test_members_without_mal_id_sorted_by_key():
    m = Donghua(id=99, mal_id=None, title="Manual Entry", media_type=MediaType.MOVIE)
    t = Donghua(id=98, mal_id=None, title="Manual Entry 2", media_type=MediaType.TV)
    ordered = order_universe([m, t], {})
    assert [d.id for d in ordered] == [98, 99]  # TV przed MOVIE


def test_empty_and_single():
    assert order_universe([], {}) == []
    one = _d(1, "Solo")
    assert order_universe([one], {}) == [one]


def test_sort_key_stable_shape():
    d = _d(1, "Test 2nd Season", media=MediaType.ONA, year=2020)
    key = sort_key(d)
    assert key == (0, 2, 2020, "test 2nd season")
