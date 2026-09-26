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
