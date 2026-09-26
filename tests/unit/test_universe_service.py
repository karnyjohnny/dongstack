"""Testy UniverseSuggester (M4): join istniejącego uniwersum / create nowego / brak."""

from __future__ import annotations

from app.domain.models import Donghua, RelationType, Status, Universe
from app.services.universe_service import UniverseSuggester, _strip_season_suffix


def _d(did, mal, title, universe_id=None):
    return Donghua(id=did, mal_id=mal, title=title, status=Status.WATCHING, universe_id=universe_id)


def test_no_relation_in_library_no_suggestion():
    new = _d(10, 500, "Nowa Seria")
    rels = [(999, RelationType.SEQUEL)]  # 999 nie ma w bibliotece
    assert UniverseSuggester.suggest(new, rels, {999: None} if False else {}) is None
    lib = {777: _d(20, 777, "Inna")}
    assert UniverseSuggester.suggest(new, rels, lib) is None


def test_suggest_create_new_universe():
    new = _d(10, 37176, "Doupo Cangqiong 2nd Season")
    s1 = _d(20, 36491, "Doupo Cangqiong")
    rels = [(36491, RelationType.PREQUEL), (38436, RelationType.SEQUEL)]
    lib = {36491: s1}  # sequel jeszcze nie dodany
    sug = UniverseSuggester.suggest(new, rels, lib)
    assert sug is not None
    assert sug.universe_id is None  # nowe uniwersum
    assert sug.universe_name == "Doupo Cangqiong"
    assert sug.member_ids == (20,)
    assert sug.new_donghua_id == 10


def test_suggest_join_existing_universe():
    uni = Universe(id=5, name="Doupo Uniwersum")
    member = _d(20, 36491, "Doupo Cangqiong", universe_id=5)
    new = _d(10, 37176, "Doupo Cangqiong 2nd Season")
    sug = UniverseSuggester.suggest(new, [(36491, RelationType.PREQUEL)], {36491: member}, {5: uni})
    assert sug.universe_id == 5
    assert sug.universe_name == "Doupo Uniwersum"


def test_other_relations_ignored():
    new = _d(10, 100, "X")
    member = _d(20, 200, "Y")
    sug = UniverseSuggester.suggest(new, [(200, RelationType.OTHER)], {200: member})
    assert sug is None


def test_strip_season_suffix():
    assert _strip_season_suffix("Doupo Cangqiong 3rd Season") == "Doupo Cangqiong"
    assert _strip_season_suffix("Fanren Xiu Xian Zhuan 2nd Season") == "Fanren Xiu Xian Zhuan"
    assert _strip_season_suffix("斗破苍穹 第三季") == "斗破苍穹"
    assert _strip_season_suffix("Series II") == "Series"
    assert _strip_season_suffix("Solo Title") == "Solo Title"
