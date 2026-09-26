"""Testy AddController (M4): debounce, stale-rid, quick add, sugestia uniwersum."""

from __future__ import annotations

from PyQt5.QtCore import QObject, pyqtSignal
from PyQt5.QtTest import QTest

from app.controllers.add_controller import AddController
from app.domain.models import Donghua, RelationType, SearchItem, Status


class FakeNet(QObject):
    searchFinished = pyqtSignal(int, list, str)
    searchFailed = pyqtSignal(int, object)
    relatedFinished = pyqtSignal(int, int, list)

    def __init__(self):
        super().__init__()
        self.searches = []  # (query, rid, limit)
        self.related = []  # (mal_id, rid)
        self.cancelled = []

    def enqueue_search(self, query, rid, limit=20):
        self.searches.append((query, rid, limit))

    def enqueue_related(self, mal_id, rid):
        self.related.append((mal_id, rid))

    def cancel(self, rid):
        self.cancelled.append(rid)


class FakeDash(QObject):
    def __init__(self, library=None, universes=None):
        super().__init__()
        self._lib = library or {}
        self._uni = universes or {}
        self.removed = []

    def library_index(self):
        return self._lib

    def universes(self):
        return self._uni

    def on_remove_requested(self, donghua_id):
        self.removed.append(donghua_id)


def _item(mal_id=37176, title="Doupo Cangqiong 2nd Season"):
    return SearchItem(
        provider="mal", ext_id=mal_id, mal_id=mal_id, title=title, total_episodes=12, year=2018
    )


def test_debounce_collapses_typing(qapp):
    net = FakeNet()
    c = AddController(network_worker=net)
    c.on_text_changed("d")
    c.on_text_changed("do")
    c.on_text_changed("doupo")
    QTest.qWait(650)
    qapp.processEvents()
    assert len(net.searches) == 1  # jedno żądanie na serię keystroke'ów
    assert net.searches[0][0] == "doupo"


def test_min_length_and_idle(qapp):
    net = FakeNet()
    c = AddController(network_worker=net)
    c.on_text_changed("d")
    QTest.qWait(600)
    assert net.searches == []
    assert c.state == "idle"


def test_stale_results_ignored(qapp):
    net = FakeNet()
    c = AddController(network_worker=net)
    got = []
    c.resultsReady.connect(lambda items, p: got.append(items))
    c.on_search_finished(999, [_item()], "mal")  # rid spoza sesji
    assert got == []
    c.on_text_changed("doupo")
    QTest.qWait(600)
    rid = net.searches[-1][1]
    c.on_search_finished(rid, [_item()], "mal")
    assert len(got) == 1


def test_error_state_and_retry(qapp):
    net = FakeNet()
    c = AddController(network_worker=net)
    states = []
    c.stateChanged.connect(states.append)
    c.on_text_changed("doupo")
    QTest.qWait(600)
    assert "searching" in states
    rid = net.searches[-1][1]
    from app.core.errors import ApiError, ApiErrorKind

    c.on_search_failed(rid, ApiError(ApiErrorKind.NETWORK, "offline", provider="mal"))
    assert c.state == "error"
    c.retry_last()
    assert len(net.searches) == 2


def test_quick_add_payload(qapp):
    net = FakeNet()
    c = AddController(network_worker=net)
    adds = []
    c.dbAddRequested.connect(lambda d, rid: adds.append(d))
    c.quick_add(_item())
    d = adds[0]
    assert d.status == Status.PLANNED and d.current_episode == 0  # Biblia §24
    assert d.mal_id == 37176 and d.total_episodes == 12
    assert d.provider == "mal"


def test_add_success_triggers_related_and_suggestion(qapp):
    net = FakeNet()
    s1 = Donghua(id=50, mal_id=36491, title="Doupo Cangqiong", status=Status.COMPLETED)
    dash = FakeDash(library={36491: s1})
    c = AddController(network_worker=net, dashboard_controller=dash)
    snacks = []
    c.snackRequested.connect(lambda t, a, cb: snacks.append((t, a, cb)))

    stored = Donghua(id=77, mal_id=37176, title="Doupo Cangqiong 2nd Season", status=Status.PLANNED)
    c.on_add_succeeded(stored, 1)
    assert snacks and "Dodano" in snacks[0][0] and snacks[0][1] == "Cofnij"
    assert len(net.related) == 1  # leniwe related PO zapisie (§5.6)
    rid_rel = net.related[0][1]

    c.on_related_finished(rid_rel, 37176, [(36491, RelationType.PREQUEL)])
    assert len(snacks) == 2 and "Połączyć" in snacks[1][0]

    creates = []
    attaches = []
    c.createUniverseRequested.connect(lambda n, a, r: creates.append((n, r)))
    c.attachUniverseRequested.connect(lambda d, u, r: attaches.append((d, u)))
    snacks[1][2]()  # klik „Połącz”
    assert creates and creates[0][0] == "Doupo Cangqiong"
    rid_create = creates[0][1]
    c.on_universe_created(9, "Doupo Cangqiong", rid_create)
    assert sorted(a[0] for a in attaches) == [50, 77]  # nowa + członek w uniwersum


def test_undo_add_removes_via_dashboard(qapp):
    net = FakeNet()
    dash = FakeDash()
    c = AddController(network_worker=net, dashboard_controller=dash)
    snacks = []
    c.snackRequested.connect(lambda t, a, cb: snacks.append((t, a, cb)))
    stored = Donghua(id=77, mal_id=1, title="X", status=Status.PLANNED)
    c.on_add_succeeded(stored, 1)
    snacks[0][2]()  # „Cofnij”
    assert dash.removed == [77]
