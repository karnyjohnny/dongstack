"""app/main.py — entrypoint DongStack.

M3: pełne okablowanie warstw (specyfikacja §3.1):
    MainWindow ⇄ DashboardController ⇄ DbWorker(QThread) ⇄ SQLite
- GUI startuje ze skeletonem i NIGDY nie czeka synchronicznie na bazę (R1, §7.2),
- zapisy postępu koalescencjonowane w DbWorker (R10), ack/nack → rollback+SnackBar,
- single instance przez QLockFile, graceful shutdown (flush + wal_checkpoint).

Kolejność bootstrapu (budżet startu §7.2):
  1. ścieżki + .env, 2. config + logi z maskowaniem (R14),
  3. QApplication + theme + MainWindow (+skeleton), 4. worker+kontroler w tle.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import time
from typing import Any, Dict, List, Optional

from app import __version__
from app.core import paths
from app.core.config import ConfigService
from app.core.dotenv_lite import find_dotenv, load_dotenv_file
from app.core.logging_setup import get_logger, setup_logging

log = get_logger("main")

SNACK_INFO_MS = 4000


def bootstrap(stream_logs: bool = False) -> ConfigService:
    """Ładuje konfigurację i logowanie. Bezpieczne do wielokrotnego wywołania."""
    dotenv_path = find_dotenv()
    if dotenv_path:
        load_dotenv_file(dotenv_path)  # env ma najwyższy priorytet — nie nadpisujemy
    config = ConfigService()
    setup_logging(
        level_name=config.log_level,
        secret_provider=config.secret_values,
        stream=stream_logs,
    )
    log.info(
        "DongStack %s start (frozen=%s, py=%s)",
        __version__,
        paths.is_frozen(),
        sys.version.split()[0],
    )
    log.debug("konfiguracja: %r", config.masked_snapshot())
    return config


def init_database(config: ConfigService) -> Dict[str, Any]:
    """Otwiera/migruje bazę synchronicznie — WYŁĄCZNIE CLI/--selftest (R1)."""
    from app.data import migrations
    from app.data.connection import open_connection

    home = paths.app_data_dir()
    db_file = paths.db_path(home)
    message = migrations.recover_if_corrupt(db_file, paths.backups_dir(home))
    if message:
        log.warning("recovery bazy: %s", message)
    conn = open_connection(db_file)
    version = migrations.ensure_schema(conn, paths.backups_dir(home))
    return {
        "home": home,
        "db": db_file,
        "schema_version": version,
        "recovery_message": message,
        "conn": conn,
    }


# --------------------------------------------------------------------------- GUI
def _wire(window, controller) -> None:
    """MainWindow ⇄ DashboardController (GUI nie zna kontrolera bazy)."""
    window.statusFilterChanged.connect(controller.set_status_filter)
    window.localSearchChanged.connect(controller.set_search)
    window.sortChanged.connect(controller.set_sort)
    window.addClicked.connect(controller.on_add_clicked)
    window.episodeIncrementRequested.connect(controller.on_increment)
    window.episodeDecrementRequested.connect(controller.on_decrement)

    controller.itemsChanged.connect(window.set_items)
    controller.itemChanged.connect(window.update_item)
    controller.countsChanged.connect(window.set_counts)

    def _snack(text: str, action_label: str, callback) -> None:
        timeout = controller.snackbar_timeout_ms() if callback else SNACK_INFO_MS
        window.snackbar.show_message(text, action_label or None, callback, timeout)

    controller.snackRequested.connect(_snack)


def _build_network_stack(config: ConfigService):
    """Providerzy + MetadataService + NetworkWorker(QThread) — specyfikacja §5."""
    from PyQt5.QtCore import QThread

    from app.api.anilist_client import AnilistClient
    from app.api.circuit_breaker import CircuitBreaker
    from app.api.mal_client import MalClient
    from app.api.metadata_service import MetadataService
    from app.data.api_cache import ApiCache
    from app.data.connection import open_connection
    from app.data.cover_store import CoverStore
    from app.workers.network_worker import NetworkWorker

    providers = {}
    if config.has_client_id:
        try:
            providers["mal"] = MalClient(config.mal_client_id)
        except Exception as exc:  # noqa: BLE001 - błąd konfiguracji → fallback
            log.warning("MalClient niedostępny: %s", exc)
    providers["anilist"] = AnilistClient()

    service = MetadataService(
        providers=providers,
        preferred=config.preferred_provider,
        breakers={name: CircuitBreaker() for name in providers},
    )
    thread = QThread()
    worker = NetworkWorker(
        service,
        cache_factory=lambda: ApiCache(open_connection(paths.db_path(), readonly=True)),
        covers_factory=lambda: CoverStore(
            open_connection(paths.db_path(), readonly=True), paths.covers_dir()
        ),
    )
    worker.moveToThread(thread)
    thread.started.connect(worker.run_loop)
    return thread, worker, service


def run_gui(config: ConfigService, demo: bool = False) -> int:
    """Uruchamia okno główne z workerami bazy i sieci w osobnych wątkach (M3/M4)."""
    from PyQt5.QtCore import QLockFile, QMetaObject, Qt, QThread
    from PyQt5.QtWidgets import QApplication

    from app.controllers.add_controller import AddController
    from app.controllers.dashboard_controller import DashboardController
    from app.core.config import KEY_LIST_BACKEND
    from app.gui.add.add_dialog import AddDialog
    from app.gui.main_window import MainWindow
    from app.gui.theme import apply_theme
    from app.workers.db_worker import DbWorker

    lock = QLockFile(paths.lock_path())
    lock.setStaleLockTime(0)
    if not lock.tryLock(100):
        print("DongStack jest już uruchomiony (blokada: %s)." % paths.lock_path())
        return 0

    app = QApplication(sys.argv[:1])
    app.setApplicationName("DongStack")
    app.setApplicationVersion(__version__)
    app.setOrganizationName("karnyjohnny")
    apply_theme(app)

    window = MainWindow(
        animations_enabled=config.animations_enabled,
        backend_kind=config.get(KEY_LIST_BACKEND, "auto"),
    )
    window.show_skeleton(4)  # start bez pustego ekranu (Biblia §20)
    window.show()

    net_thread: Optional[QThread] = None
    net_worker = None
    db_worker = None
    if demo:
        from app.core.demo_data import demo_rows

        controller = DashboardController(worker=None)
        controller.load_demo(demo_rows(300))
        add_controller = AddController(network_worker=None, dashboard_controller=controller)
    else:
        db_thread = QThread(app)
        db_worker = DbWorker(paths.db_path(), paths.backups_dir(), covers_dir=paths.covers_dir())
        db_worker.moveToThread(db_thread)
        db_thread.started.connect(db_worker.loadLibrary)
        # UWAGA (bug produkcyjny r5): thread.start() DOPIERO po podłączeniu kontrolerów —
        # loadLibrary emituje libraryLoaded milisekundy po starcie wątku; emit bez
        # odbiorcy = utracone dane w GUI („pusty dashboard mimo wczytanej bazy”).

        net_thread, net_worker, _service = _build_network_stack(config)
        net_worker.cacheWriteRequested.connect(db_worker.saveCache)

        from app.core.config import KEY_LAST_FILTER, KEY_LAST_SORT
        from app.domain.models import SortMode

        try:
            sort0 = SortMode(config.get(KEY_LAST_SORT) or "updated")
        except ValueError:
            sort0 = SortMode.UPDATED
        controller = DashboardController(
            db_worker,
            initial_status=config.get(KEY_LAST_FILTER) or "watching",
            initial_sort=sort0,
        )
        add_controller = AddController(network_worker=net_worker, dashboard_controller=controller)
        add_controller.dbAddRequested.connect(db_worker.addDonghua)
        add_controller.editSaveRequested.connect(controller.on_advanced_save)
        add_controller.replaceLinksRequested.connect(db_worker.replaceLinks)
        add_controller.createUniverseRequested.connect(db_worker.createUniverse)
        add_controller.attachUniverseRequested.connect(db_worker.attachUniverse)
        db_worker.addSucceeded.connect(controller.on_add_completed)
        db_worker.addSucceeded.connect(add_controller.on_add_succeeded)
        db_worker.universeCreated.connect(add_controller.on_universe_created)
        net_worker.relatedFinished.connect(
            lambda rid, mal_id, rels: controller.register_relations(mal_id, rels)
        )
        net_worker.backfillFinished.connect(controller.on_backfill_cover)
        controller.backfillRequested.connect(net_worker.enqueue_backfill)
        controller.updateCoverKeyRequested.connect(db_worker.updateCoverKey)

        # start wątków DOPIERO TERAZ: wszystkie sygnały startowe mają odbiorców
        db_thread.start()
        net_thread.start()

        def _shutdown() -> None:
            try:
                net_worker.stop()
                net_thread.quit()
                net_thread.wait(1500)
                if db_thread.isRunning():
                    QMetaObject.invokeMethod(db_worker, "shutdown", Qt.BlockingQueuedConnection)
                db_thread.quit()
                db_thread.wait(2000)
            except RuntimeError:  # pragma: no cover - wyścig zamknięcia
                pass

        app.aboutToQuit.connect(_shutdown)

    _wire(window, controller)

    # start z pamiętanym filtrem: sidebar i tytuł sekcji muszą go odzwierciedlać
    window.sidebar.set_current(controller.status_filter)
    window.dashboard.set_section_title(controller.status_label())

    # QoL: pamiętamy ostatni filtr i sort w config.json (restart nie gubi kontekstu)
    from app.core.config import KEY_LAST_FILTER, KEY_LAST_SORT

    def _persist(key: str, value: str) -> None:
        try:
            config.set(key, value)
        except ValueError:
            pass

    window.sidebar.statusFilterChanged.connect(lambda st: _persist(KEY_LAST_FILTER, st))
    window.dashboard.sortChanged.connect(lambda mode: _persist(KEY_LAST_SORT, mode))

    def _show_snack_for(t, a, cb):
        _show_snack(window, add_controller, t, a, cb)

    add_controller.snackRequested.connect(_show_snack_for)

    # --- okładki (M5): koordynator LRU + worker sieciowy + zapis przez DbWorker -----
    from app.gui.cover_coordinator import CoverCoordinator

    coordinator = CoverCoordinator(
        window.dashboard.backend,
        net_worker,
    )
    controller.coversRequested.connect(coordinator.request_covers)
    if net_worker is not None:
        net_worker.coverReady.connect(coordinator.on_cover_ready)
        coordinator.saveCoverRequested.connect(db_worker.saveCover)

    # --- uniwersa na dashboardzie (M5, §6.7) -----------------------------------------
    window.dashboard.openDataDirRequested.connect(_open_data_dir)

    # --- Client ID MAL: first-run (§5.5) + menu Ustawień, live-attach bez restartu ---
    from PyQt5.QtWidgets import QDialog

    from app.core.config import KEY_CLIENT_ID, KEY_SKIP_CLIENT_ID
    from app.gui.settings_dialog import ClientIdDialog

    def _apply_client_id(cid: str) -> None:
        config.set(KEY_CLIENT_ID, cid)
        from app.api.circuit_breaker import CircuitBreaker
        from app.api.mal_client import MalClient

        if net_worker is not None:
            _service.attach_provider("mal", MalClient(cid), CircuitBreaker(), preferred=True)
        window.snackbar.show_message(
            "Zapisano Client ID — wyszukiwanie używa teraz oficjalnego API MAL.",
            "",
            None,
            SNACK_INFO_MS,
        )

    def _open_client_id_settings() -> None:
        dlg = ClientIdDialog(window, current_id=config.mal_client_id)
        if dlg.exec() == QDialog.Accepted and dlg.client_id:
            _apply_client_id(dlg.client_id)

    window.dashboard.settingsClientIdRequested.connect(_open_client_id_settings)

    if not demo and not config.has_client_id and not config.get_bool(KEY_SKIP_CLIENT_ID, False):
        dlg = ClientIdDialog(window)
        if dlg.exec() == QDialog.Accepted and dlg.client_id:
            _apply_client_id(dlg.client_id)
        else:
            try:
                config.set(KEY_SKIP_CLIENT_ID, "1")
            except ValueError:  # pragma: no cover - klucz poza whitelist
                pass
    window.dashboard.headerToggled.connect(controller.toggle_universe)
    window.dashboard.moveRequested.connect(controller.move_in_universe)
    window.detailsRequested.connect(controller.on_details)

    # --- AddDialog (leniwie, non-modal; Biblia §15/§24) ----------------------------
    # BUG-FIX r6: subscriber editRequestedFull musi istnieć OD STARTU — inaczej
    # edycja (LPM w kartę) milczy, dopóki użytkownik nie otworzy raz AddDialogu.
    dialog: Optional[AddDialog] = None

    def _ensure_dialog() -> AddDialog:
        nonlocal dialog
        if dialog is None:
            dialog = AddDialog(window)
            page = dialog.search_page
            page.textChanged.connect(add_controller.on_text_changed)
            page.retryRequested.connect(add_controller.retry_last)
            page.returnPressed.connect(add_controller.force_search)
            page.quickAddRequested.connect(add_controller.quick_add)
            page.advancedRequested.connect(dialog.open_advanced)
            # okładki wyników (M6-fix): wspólny LRU + kolejka LOW NetworkWorkera
            page.set_cover_requester(coordinator.request_pairs)
            coordinator.pixmapReady.connect(page.apply_cover)
            add_controller.addCompleted.connect(lambda d: page.mark_in_library(d.mal_id))
            dialog.advancedSaveRequested.connect(
                lambda item, form: add_controller.advanced_add(item, form)
            )
            dialog.advancedEditSaveRequested.connect(
                lambda d, form: add_controller.edit_save(d, form)
            )
            dialog.deleteRequested.connect(_delete_from_dialog)
            add_controller.stateChanged.connect(lambda s: _apply_search_state(dialog, s))
            add_controller.resultsReady.connect(
                lambda items, prov: page.show_results(
                    items, prov, set(controller.library_index().keys())
                )
            )
            add_controller.searchError.connect(lambda err: page.show_error(err.user_message()))
            controller.universesChanged.connect(dialog.set_universes)
        return dialog

    def _open_add_dialog() -> None:
        d = _ensure_dialog()
        d.set_universes(controller.universes())
        note = (
            ""
            if config.has_client_id
            else "Brak MAL Client ID — szukam w AniList (ID ustawisz później)."
        )
        d.search_page.show_idle(note)
        d.open()

    def _open_edit(d, links) -> None:
        dlg = _ensure_dialog()
        dlg.set_universes(controller.universes())  # rejestr zawsze świeży przy otwarciu
        dlg.open_advanced_edit(d, links)

    def _delete_from_dialog(donghua_id: int) -> None:
        # Undo zamiast Confirm (Biblia §9): soft-delete + SnackBar „Cofnij”
        controller.on_remove_requested(donghua_id)
        if dialog is not None:
            dialog.close()

    controller.addRequested.connect(_open_add_dialog)
    controller.editRequestedFull.connect(_open_edit)
    return int(app.exec_())


def _open_data_dir() -> None:
    """Uniwersalne otwarcie folderu danych (feedback M6-fix): QDesktopServices."""
    from PyQt5.QtCore import QUrl
    from PyQt5.QtGui import QDesktopServices  # UWAGA: QtGui, nie „QtDesktopServices”

    QDesktopServices.openUrl(QUrl.fromLocalFile(paths.app_data_dir()))


def _show_snack(window, controller, text: str, action_label: str, callback) -> None:
    timeout = controller.snackbar_timeout_ms() if callback else SNACK_INFO_MS
    window.snackbar.show_message(text, action_label or None, callback, timeout)


def _apply_search_state(dialog, state: str) -> None:
    page = dialog.search_page
    if state == "searching":
        page.show_searching()
    elif state == "idle":
        page.show_idle()
    elif state == "no_results":
        page.show_no_results(page.line_edit.text())
    # stany results/error ustawiane są przez resultsReady/searchError


def _counts_of(rows: List[Any]) -> Dict[str, int]:
    counts = {"all": len(rows), "watching": 0, "completed": 0, "planned": 0, "dropped": 0}
    for d in rows:
        key = d.status.value
        if key in counts:
            counts[key] += 1
    return counts


# ----------------------------------------------------------------------- selftest
def selftest() -> int:
    """--selftest: rdzeń danych + GUI offscreen (budżety §7.3). JSON na stdout, exit 0/1."""
    import tempfile

    t0 = time.time()
    report: Dict[str, Any] = {"app_version": __version__, "phase": "M4-api"}
    tmp = tempfile.mkdtemp(prefix="dongstack-selftest-")
    os.environ["DONGSTACK_HOME"] = tmp
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    try:
        config = bootstrap(stream_logs=False)
        report["provider"] = config.preferred_provider
        report["has_client_id"] = config.has_client_id

        info = init_database(config)
        conn = info["conn"]
        report["schema_version"] = info["schema_version"]
        report["db_init_ms"] = round((time.time() - t0) * 1000.0, 1)

        from app.core.demo_data import demo_rows
        from app.core.timeutil import utc_now_iso
        from app.data.repository import DonghuaRepository
        from app.domain.models import Status

        repo = DonghuaRepository(conn)
        t_ins = time.time()
        ids = [repo.insert(d) for d in demo_rows(300)]
        report["insert300_ms"] = round((time.time() - t_ins) * 1000.0, 1)

        t_upd = time.time()
        for i, did in enumerate(ids[:200]):
            repo.update_progress(did, i % 12, Status.WATCHING, utc_now_iso())
        report["update200_ms"] = round((time.time() - t_upd) * 1000.0, 1)
        report["rows_alive"] = len(repo.load_alive())
        conn.close()

        # --- faza GUI (offscreen): controller + backend listy ---------------------
        from PyQt5.QtWidgets import QApplication

        from app.controllers.dashboard_controller import DashboardController
        from app.gui.main_window import MainWindow
        from app.gui.theme import apply_theme

        app = QApplication.instance() or QApplication(["dongstack-selftest"])
        apply_theme(app)
        window = MainWindow(animations_enabled=False)
        controller = DashboardController(worker=None)
        _wire(window, controller)

        items = demo_rows(300)
        t_fill = time.time()
        controller.load_demo(items)
        app.processEvents()
        report["gui_fill300_ms"] = round((time.time() - t_fill) * 1000.0, 1)

        t_rebuild = time.time()
        controller.set_status_filter("all")
        app.processEvents()
        report["gui_rebuild300_ms"] = round((time.time() - t_rebuild) * 1000.0, 1)
        controller.set_status_filter("watching")
        app.processEvents()

        # gorąca ścieżka +1 (gate G2): p95 handlera kontrolera
        samples = []
        watching = [d for d in items if d.status.value == "watching"][:200]
        for d in watching:
            s = time.perf_counter()
            controller.on_increment(d.id)
            samples.append((time.perf_counter() - s) * 1000.0)
        app.processEvents()
        samples.sort()
        report["increment_p95_ms"] = round(samples[int(len(samples) * 0.95)], 3)

        report["threads"] = threading.active_count()
        report["total_ms"] = round((time.time() - t0) * 1000.0, 1)
        from app.data import migrations as _migrations

        ok = (
            report["rows_alive"] == 300
            and report["schema_version"] == _migrations.SCHEMA_VERSION
            and report["threads"] <= 3
            and report["increment_p95_ms"] <= 8.0
        )
        report["ok"] = ok
        # Windowed exe (console=False) nie ma stdout w konsoli użytkownika,
        # więc raport M7 ląduje ALSO w pliku obok exe / w DONGSTACK_HOME.
        out_path = os.environ.get("DONGSTACK_SELFTEST_OUT")
        if not out_path:
            if paths.is_frozen():
                # frozen: raport OBOK exe (bat/ps1 szukają %~dp1selftest-report.json);
                # DONGSTACK_HOME jest w selfteście nadpisywany tmp-em, więc nie może
                # wygrać z katalogiem exe (bug v1.0.0: raport ginął w tmp)
                base = os.path.dirname(sys.executable)
            else:
                base = os.environ.get("DONGSTACK_HOME") or os.getcwd()
            out_path = os.path.join(base, "selftest-report.json")
        try:
            with open(out_path, "w", encoding="utf-8") as fh:
                json.dump(report, fh, ensure_ascii=False, indent=2, sort_keys=True)
            print("selftest-report: %s" % out_path)
        except OSError:
            pass
        print(json.dumps(report, ensure_ascii=False, sort_keys=True))
        return 0 if ok else 1
    finally:
        os.environ.pop("DONGSTACK_HOME", None)
        _cleanup(tmp)


def _cleanup(directory: str) -> None:
    import shutil

    try:
        shutil.rmtree(directory, ignore_errors=True)
    except OSError:
        pass


def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="DongStack",
        description="DongStack — osobisty tracker donghua (Windows 7+).",
    )
    parser.add_argument("--version", action="version", version="DongStack %s" % __version__)
    parser.add_argument(
        "--selftest",
        action="store_true",
        help="self-test rdzenia + GUI (offscreen), JSON na stdout",
    )
    parser.add_argument(
        "--init-db", action="store_true", help="zainicjuj/zmigruj bazę i zakończ (diagnostyka)"
    )
    parser.add_argument(
        "--demo", action="store_true", help="uruchom GUI z 300 syntetycznymi pozycjami (bez zapisu)"
    )
    parser.add_argument("--verbose", action="store_true", help="logi również na stdout")
    args = parser.parse_args(argv)

    if args.selftest:
        return selftest()

    config = bootstrap(stream_logs=args.verbose)

    if args.init_db:
        info = init_database(config)
        info.pop("conn", None)
        print(json.dumps(info, ensure_ascii=False, indent=2))
        return 0

    return run_gui(config, demo=args.demo)


if __name__ == "__main__":
    sys.exit(main())
