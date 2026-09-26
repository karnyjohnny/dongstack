"""Testy modeli domenowych: frozen, with_episode (auto-statusy), normalizacje."""

from __future__ import annotations

import dataclasses

import pytest

from app.domain.models import (
    Donghua,
    MediaType,
    RelationType,
    SearchItem,
    Status,
    normalize_media_type,
    normalize_relation_type,
)


def test_donghua_is_frozen():
    d = Donghua(title="X")
    with pytest.raises(dataclasses.FrozenInstanceError):
        d.current_episode = 5  # type: ignore[misc]


def test_clamped_episode():
    d = Donghua(title="X", total_episodes=12, current_episode=5)
    assert d.clamped_episode(20) == 12
    assert d.clamped_episode(-3) == 0
    infinite = Donghua(title="Y", total_episodes=0)
    assert infinite.clamped_episode(999) == 999  # emisja w toku — bez capu


def test_with_episode_auto_completion():
    d = Donghua(title="X", total_episodes=12, current_episode=11, status=Status.WATCHING)
    d2 = d.with_episode(12, updated_at="t")
    assert d2.status == Status.COMPLETED  # Biblia §10: auto-ukończenie
    assert d2.current_episode == 12
    # oryginał nietknięty (frozen)
    assert d.status == Status.WATCHING and d.current_episode == 11


def test_with_episode_completed_back_to_watching():
    d = Donghua(title="X", total_episodes=12, current_episode=12, status=Status.COMPLETED)
    d2 = d.with_episode(11, updated_at="t")
    assert d2.status == Status.WATCHING  # decrement z "obejrzane" wraca do "w trakcie"


def test_with_episode_planned_to_watching():
    d = Donghua(title="X", total_episodes=12, current_episode=0, status=Status.PLANNED)
    d2 = d.with_episode(1, updated_at="t")
    assert d2.status == Status.WATCHING


def test_with_episode_no_auto_status_when_unknown_total():
    d = Donghua(title="X", total_episodes=0, current_episode=0, status=Status.WATCHING)
    d2 = d.with_episode(5, updated_at="t")
    assert d2.status == Status.WATCHING


def test_progress_ratio():
    assert Donghua(title="a", total_episodes=24, current_episode=12).progress_ratio == 0.5
    assert Donghua(title="a", total_episodes=0, current_episode=5).progress_ratio == 0.0
    assert Donghua(title="a", total_episodes=12, current_episode=12).progress_ratio == 1.0


def test_is_finished():
    assert Donghua(title="a", total_episodes=12, current_episode=12).is_finished
    assert not Donghua(title="a", total_episodes=0, current_episode=3).is_finished


def test_normalize_media_type():
    assert normalize_media_type("tv") == MediaType.TV
    assert normalize_media_type("TV_SHORT") == MediaType.TV
    assert normalize_media_type("ona") == MediaType.ONA
    assert normalize_media_type("OVA") == MediaType.OVA
    assert normalize_media_type("movie") == MediaType.MOVIE
    assert normalize_media_type(None) == MediaType.UNKNOWN
    assert normalize_media_type("cos_dziwnego") == MediaType.UNKNOWN


def test_normalize_relation_type():
    assert normalize_relation_type("sequel") == RelationType.SEQUEL
    assert normalize_relation_type("side_story") == RelationType.SIDE_STORY
    assert normalize_relation_type("SIDE STORY") == RelationType.SIDE_STORY
    assert normalize_relation_type("SPIN_OFF") == RelationType.SIDE_STORY  # AniList
    assert normalize_relation_type(None) == RelationType.OTHER


def test_status_values():
    assert Status.values() == ["watching", "completed", "planned", "dropped"]


def test_search_item_minimal():
    si = SearchItem(provider="mal", ext_id=37176, mal_id=37176, title="Doupo 2nd Season")
    assert si.total_episodes == 0
    assert si.media_type == MediaType.UNKNOWN
