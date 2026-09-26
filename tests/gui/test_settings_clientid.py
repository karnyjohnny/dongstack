"""Testy first-run / ustawień Client ID MAL (§5.5) i live-attach providera."""

from __future__ import annotations

from PyQt5.QtWidgets import QDialog

from app.api.metadata_service import MetadataService
from app.core.config import KEY_SKIP_CLIENT_ID, ConfigService
from app.core.errors import ApiError, ApiErrorKind
from app.domain.models import SearchItem
from app.gui.dashboard.dashboard_widget import DashboardWidget
from app.gui.settings_dialog import ClientIdDialog


class FakeProv:
    def __init__(self, name):
        self.name = name
        self.calls = 0

    def search(self, q, limit=20):
        self.calls += 1
        return [SearchItem(provider=self.name, ext_id=1, mal_id=1, title=self.name)]

    def related(self, mid):
        return []

    def details(self, mid):
        raise ApiError(ApiErrorKind.NOT_FOUND, "x", provider=self.name)


def test_dialog_save_disabled_until_text(qapp):
    dlg = ClientIdDialog()
    assert dlg._save.isEnabled() is False
    dlg._edit.setText("abc123")
    assert dlg._save.isEnabled() is True
    assert dlg.client_id == "abc123"
    dlg._edit.setText("   ")
    assert dlg._save.isEnabled() is False


def test_dialog_prefill_and_accept(qapp):
    dlg = ClientIdDialog(current_id="istniejacy-id")
    assert dlg._edit.text() == "istniejacy-id"
    dlg.accept()
    assert dlg.result() == QDialog.Accepted


def test_service_attach_provider_switches_preferred():
    ani = FakeProv("anilist")
    svc = MetadataService(providers={"anilist": ani})
    assert svc.search("x").items[0].provider == "anilist"
    mal = FakeProv("mal")
    svc.attach_provider("mal", mal, breaker=None, preferred=True)
    out = svc.search("x")
    assert out.provider == "mal" and mal.calls == 1 and ani.calls == 1


def test_settings_menu_emits_client_id_signal(qapp):
    dash = DashboardWidget()
    got = []
    dash.settingsClientIdRequested.connect(lambda: got.append(1))
    actions = dash._settings.menu().actions()
    cid = [a for a in actions if "Client ID" in a.text()]
    assert cid, "brak akcji Client ID w menu Ustawień"
    cid[0].trigger()
    qapp.processEvents()
    assert got == [1]


def test_skip_client_id_persistable(tmp_path):
    cfg = ConfigService(config_file=str(tmp_path / "c.json"), env={})
    cfg.set(KEY_SKIP_CLIENT_ID, "1")
    cfg2 = ConfigService(config_file=str(tmp_path / "c.json"), env={})
    assert cfg2.get_bool(KEY_SKIP_CLIENT_ID, False) is True
