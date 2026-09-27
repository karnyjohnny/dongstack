#!/usr/bin/env python3
"""tools/make_screenshots.py — zrzuty okna (offscreen) do README/docs.

Użycie:  QT_QPA_PLATFORM=offscreen python tools/make_screenshots.py
Wynik:   docs/screenshots/dashboard.png, docs/screenshots/universes.png
Baseline składni: Python 3.8. Bez sieci i bez zapisu do bazy (dane demo).
"""

from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("DONGSTACK_HOME", os.path.join(ROOT, ".tmp-screenshot-home"))


def _build_stack():
    from PyQt5.QtWidgets import QApplication

    from app.controllers.dashboard_controller import DashboardController
    from app.gui.main_window import MainWindow
    from app.gui.theme import apply_theme
    from app.main import _wire

    app = QApplication.instance() or QApplication(["dongstack-screenshots"])
    apply_theme(app)
    controller = DashboardController(worker=None)
    window = MainWindow(animations_enabled=False)
    _wire(window, controller)
    return app, controller, window


def _shot(window, name: str, out_dir: str):
    from PyQt5.QtWidgets import QApplication

    window.resize(1180, 720)
    window.show()
    app = QApplication.instance()
    app.processEvents()
    window.snackbar.reposition()
    app.processEvents()
    pixmap = window.grab()
    target = os.path.join(out_dir, name)
    ok = pixmap.save(target, "PNG")
    print("screenshot: %s (%dx%d) ok=%s" % (target, pixmap.width(), pixmap.height(), ok))
    return ok


def main() -> int:
    from app.core.demo_data import demo_rows
    from app.domain.models import RelationType, SortMode, Universe

    out_dir = os.path.join(ROOT, "docs", "screenshots")
    if not os.path.isdir(out_dir):
        os.makedirs(out_dir)

    app, controller, window = _build_stack()
    rows = demo_rows(40)
    controller.load_demo(rows)
    window.snackbar.show_message(
        "Dodano „Doupo Cangqiong 3rd Season” do Planowanych",
        action_label="Cofnij",
        on_action=lambda: None,
        timeout_ms=10**9,
    )
    ok1 = _shot(window, "dashboard.png", out_dir)
    window.snackbar.hide_message()

    # --- uniwersa: grupowanie w kolejności oglądania (§6.7) ---
    import dataclasses

    uni_rows = []
    for i, d in enumerate(rows):
        if i < 4:
            d = dataclasses.replace(d, universe_id=1)
        elif i < 7:
            d = dataclasses.replace(d, universe_id=2)
        uni_rows.append(d)
    controller.on_universes_loaded(
        [
            Universe(id=1, name="Doupo Cangqiong"),
            Universe(id=2, name="Fanren Xiu Xian Zhuan"),
        ]
    )
    controller.on_library_loaded(uni_rows)
    controller.register_relations(30001, [(30000, RelationType.PREQUEL)])
    controller.register_relations(30002, [(30001, RelationType.PREQUEL)])
    controller.register_relations(30005, [(30004, RelationType.PREQUEL)])
    window.sidebar.set_current("all")
    window.dashboard.set_section_title("Wszystkie")
    controller.set_sort(SortMode.WATCH_ORDER.value)
    # M9: pokaż dwupoziomowe podświetlenie uniwersum (hover) na zrzucie
    first = next(d for d in uni_rows if d.universe_id == 1)
    window.dashboard.backend.set_universe_hover(1, first.id)
    app.processEvents()
    ok2 = _shot(window, "universes.png", out_dir)
    return 0 if (ok1 and ok2) else 1


if __name__ == "__main__":
    sys.exit(main())
