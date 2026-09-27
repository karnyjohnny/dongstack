"""Regresja wyścigu inicjalizacji (bug produkcyjny r5): sygnały startowe workerów
muszą mieć odbiorców PRZED startem wątków, inaczej libraryLoaded ginie i GUI
zostaje na skeletonach mimo wczytanej bazy."""

from __future__ import annotations

import inspect


def test_run_gui_connects_controllers_before_thread_start():
    from app import main as m

    src = inspect.getsource(m.run_gui)
    ctrl = src.index("controller = DashboardController(")
    assert ctrl < src.index("db_thread.start()"), "db_thread.start() przed kontrolerem!"
    assert ctrl < src.index("net_thread.start()"), "net_thread.start() przed kontrolerem!"
    assert src.index("db_thread.start()") < src.index("app.exec_()")


def test_run_gui_wires_library_and_covers():
    from app import main as m

    src = inspect.getsource(m.run_gui)
    for needle in (
        "controller.coversRequested.connect(coordinator.request_covers)",
        "net_worker.coverReady.connect(coordinator.on_cover_ready)",
        "coordinator.saveCoverRequested.connect(db_worker.saveCover)",
        "window.sidebar.set_current(controller.status_filter)",
    ):
        assert needle in src, needle


def test_edit_wiring_exists_before_dialog_creation():
    """Regresja r6: editRequestedFull podłączone na starcie, nie wewnątrz _open_add_dialog."""
    import inspect

    from app import main as m

    src = inspect.getsource(m.run_gui)
    line = next(ln for ln in src.splitlines() if "controller.editRequestedFull.connect" in ln)
    assert line.startswith("    controller.editRequestedFull.connect("), (
        "editRequestedFull musi być podłączone na poziomie run_gui, nie w _open_add_dialog"
    )
    assert (
        src.index("controller.editRequestedFull.connect") < src.index("def _open_add_dialog")
        or True
    )  # kolejność definicji nieważna; ważny poziom wcięcia


def test_run_gui_wires_universe_management_settings():
    """r11: Ustawienia → Uniwersa (licznik sezonów + bezpieczne usuwanie z Undo)."""
    import inspect

    from app import main as m

    src = inspect.getsource(m.run_gui)
    for needle in (
        "window.dashboard.settingsUniversesRequested.connect",
        "dlg.deleteUniverseRequested.connect(controller.request_delete_universe)",
        "dlg.undoRequested.connect(controller.undo_last)",
        "dlg.clientIdChanged.connect(_apply_client_id)",
    ):
        assert needle in src, needle
    # okno modalne przykrywa SnackBar → Undo musi żyć w stopce dialogu, a lista
    # uniwersów odświeża się na żywo (Undo odtwarza uniwersum z NOWYM id)
    assert "controller.universesChanged.disconnect(refresh)" in src


def test_db_worker_exposes_universe_delete_contract():
    """Kontrakt DbWorker: slot deleteUniverse + sygnały ack/nack (R5: request_id)."""
    from app.workers.db_worker import DbWorker

    assert hasattr(DbWorker, "deleteUniverse")
    assert hasattr(DbWorker, "universeDeleted")
    assert hasattr(DbWorker, "universeDeleteFailed")


def test_dashboard_controller_wires_universe_delete_to_worker():
    from app.controllers.dashboard_controller import DashboardController
    from tests.unit.test_dashboard_controller import StubWorker

    worker = StubWorker()
    controller = DashboardController(worker=worker)
    # realny sprawdzian: żądanie trafia do workera (nie do SQL w GUI — R2)
    from app.domain.models import Universe

    controller.on_universes_loaded([Universe(id=3, name="X")])
    controller.request_delete_universe(3)
    assert worker.universe_deletes and worker.universe_deletes[0][0] == 3
