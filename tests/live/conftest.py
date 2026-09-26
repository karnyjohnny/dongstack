"""conftest testów LIVE: QApplication offscreen (worker sieciowy potrzebuje pętli)."""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="session")
def qapp():
    from PyQt5.QtWidgets import QApplication

    app = QApplication.instance() or QApplication(["dongstack-live"])
    yield app
