"""conftest testów GUI: QApplication offscreen + theme (sesyjnie, bez pytest-qt)."""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="session")
def qapp():
    from PyQt5.QtWidgets import QApplication

    from app.gui.theme import apply_theme

    app = QApplication.instance() or QApplication(["dongstack-tests"])
    apply_theme(app)
    yield app


@pytest.fixture()
def process_events(qapp):
    def _flush():
        qapp.processEvents()

    return _flush
