"""Testy repozytoriów: CRUD, soft-delete, linki (transakcyjność), uniwersa, liczniki."""

from __future__ import annotations

from app.core.timeutil import utc_now_iso
from app.data.repository import DonghuaRepository, LinksRepository, UniverseRepository
from app.domain.models import Donghua, MediaType, Status, StreamingLink


def _mk(title, **kw):
    base = dict(total_episodes=12, status=Status.PLANNED, media_type=MediaType.TV)
    base.update(kw)
    return Donghua(title=title, **base)


def test_insert_and_load(db_conn):
    repo = DonghuaRepository(db_conn)
    did = repo.insert(_mk("Doupo Cangqiong", mal_id=36491, status=Status.WATCHING))
    assert did > 0
    got = repo.get(did)
    assert got is not None
    assert got.title == "Doupo Cangqiong"
    assert got.mal_id == 36491
    assert got.status == Status.WATCHING
    assert got.added_at and got.updated_at
    alive = repo.load_alive()
    assert [d.id for d in alive] == [did]


def test_mal_id_unique(db_conn):
    repo = DonghuaRepository(db_conn)
    repo.insert(_mk("A", mal_id=1))
    try:
        repo.insert(_mk("B", mal_id=1))
        assert False, "oczekiwano IntegrityError (mal_id UNIQUE)"
    except Exception as exc:  # sqlite3.IntegrityError
        assert "UNIQUE" in str(exc) or "unique" in str(exc).lower()


def test_update_progress_and_status_enum(db_conn):
    repo = DonghuaRepository(db_conn)
    did = repo.insert(_mk("S", status=Status.WATCHING))
    assert repo.update_progress(did, 5, Status.WATCHING, utc_now_iso())
    got = repo.get(did)
    assert got.current_episode == 5
    assert got.status == Status.WATCHING


def test_counts_by_status(db_conn):
    repo = DonghuaRepository(db_conn)
    repo.insert(_mk("a", status=Status.WATCHING))
    repo.insert(_mk("b", status=Status.WATCHING))
    repo.insert(_mk("c", status=Status.COMPLETED))
    counts = repo.counts_by_status()
    assert counts["watching"] == 2
    assert counts["completed"] == 1
    assert counts["planned"] == 0
    assert counts["dropped"] == 0


def test_soft_delete_restore_purge(db_conn):
    repo = DonghuaRepository(db_conn)
    did = repo.insert(_mk("Do usunięcia"))
    assert repo.soft_delete(did)
    assert repo.get(did) is None
    assert repo.counts_by_status()["planned"] == 0
    # restore (Undo)
    assert repo.restore(did)
    assert repo.get(did) is not None
    # ponowne soft delete + purge po oknie Undo
    repo.soft_delete(did, "2026-01-01T00:00:00.000Z")
    purged = repo.purge_deleted("2026-06-01T00:00:00.000Z")
    assert purged == 1
    assert repo.restore(did) is False


def test_links_replace_is_transactional_and_cascades(db_conn):
    repo = DonghuaRepository(db_conn)
    links_repo = LinksRepository(db_conn)
    did = repo.insert(_mk("Z linkami"))
    links_repo.replace_links(
        did,
        [
            StreamingLink(tag="bilibili", url="https://bilibili.example/1"),
            StreamingLink(tag="iqiyi", url="https://iqiyi.example/2", label="alt"),
        ],
    )
    got = links_repo.list_for(did)
    assert len(got) == 2
    assert got[0].tag == "bilibili"
    assert got[1].label == "alt"
    assert [lnk.position for lnk in got] == [0, 1]

    # podmiana kompletna
    links_repo.replace_links(did, [StreamingLink(tag="youtube", url="https://yt.example")])
    assert len(links_repo.list_for(did)) == 1

    # cascade przy twardym purge
    repo.soft_delete(did)
    repo.purge_deleted("9999-01-01T00:00:00.000Z")
    assert links_repo.list_for(did) == []
    assert links_repo.list_all().get(did) is None


def test_universes_crud_and_fk_set_null(db_conn):
    repo = DonghuaRepository(db_conn)
    uni = UniverseRepository(db_conn)
    d1 = repo.insert(_mk("S1", mal_id=36491))
    d2 = repo.insert(_mk("S2", mal_id=37176))

    uid = uni.create("Doupo Cangqiong", mal_anchor_id=36491)
    assert uid > 0
    # ta sama nazwa (case-insensitive) → istniejące id, brak duplikatu
    assert uni.create("doupo cangqiong") == uid

    repo.set_universe(d1, uid, 1)
    repo.set_universe(d2, uid, 2)
    members = repo.list_by_universe(uid)
    assert [m.id for m in members] == [d1, d2]  # wg universe_order

    assert uni.rename(uid, "Battle Through the Heavens")
    assert uni.get(uid).name == "Battle Through the Heavens"

    # usunięcie uniwersum NIE kasuje pozycji — FK SET NULL
    assert uni.delete(uid)
    assert repo.get(d1) is not None
    assert repo.get(d1).universe_id is None
    assert repo.get(d2).universe_id is None


def test_get_by_mal_id(db_conn):
    repo = DonghuaRepository(db_conn)
    repo.insert(_mk("Qin Shi Mingyue", mal_id=2565))
    got = repo.get_by_mal_id(2565)
    assert got is not None and got.title == "Qin Shi Mingyue"
    assert repo.get_by_mal_id(9999) is None


def test_readd_after_soft_delete_revives_row(db_conn):
    """Bug produkcyjny: UNIQUE(mal_id) blokował ponowne dodanie po usunięciu."""
    repo = DonghuaRepository(db_conn)
    first = repo.insert(_mk("Xian Ni", mal_id=55809, total_episodes=180))
    assert repo.soft_delete(first)
    # ponowne dodanie tej samej serii: REVIVE, nie INSERT i nie wyjątek
    again = repo.insert(_mk("Xian Ni (nowe meta)", mal_id=55809, total_episodes=190))
    assert again == first
    got = repo.get(first)
    assert got is not None and got.deleted_at is None
    assert got.title == "Xian Ni (nowe meta)" and got.total_episodes == 190
    assert repo.counts_by_status()["planned"] == 1


def test_insert_duplicate_alive_returns_existing(db_conn):
    repo = DonghuaRepository(db_conn)
    first = repo.insert(_mk("A", mal_id=1, total_episodes=10))
    second = repo.insert(_mk("A kopiuj", mal_id=1, total_episodes=99))
    assert second == first
    got = repo.get(first)
    assert got.title == "A" and got.total_episodes == 10  # żywy duplikat nie nadpisuje
