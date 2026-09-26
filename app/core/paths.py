"""app/core/paths.py — ścieżki zasobów i danych (świadome PyInstallera).

Zasady (specyfikacja §8.3, §4.1):
- resource_path(): identyczny układ w dev i w frozen bundle (datas → app/resources/…),
  jedyny branch to sys._MEIPASS.
- app_data_dir(): %LOCALAPPDATA%\\DongStack, z override DONGSTACK_HOME (tryb
  portable / testy). Katalogi pochodne tworzone leniwie.
"""

from __future__ import annotations

import os
import sys
from typing import Optional

APP_DIR_NAME = "DongStack"
ENV_HOME = "DONGSTACK_HOME"


def is_frozen() -> bool:
    """True gdy proces jest frozen przez PyInstaller (onedir i onefile)."""
    return bool(getattr(sys, "frozen", False))


def bundle_base() -> str:
    """Katalog bazowy zasobów: _MEIPASS (frozen) albo root repo (dev)."""
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        return str(meipass)
    # dev: <repo>/app/core/paths.py -> <repo>
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.dirname(os.path.dirname(here))


def resource_path(*rel: str) -> str:
    """Ścieżka do zasobu aplikacji, np. resource_path("styles", "base.qss").

    W frozen (onedir i onefile) zasoby leżą w <_MEIPASS>/app/resources/…,
    w dev w <repo>/app/resources/… — ten sam kod działa w obu trybach.
    """
    return os.path.join(bundle_base(), "app", "resources", *rel)


def icons_dir() -> str:
    return resource_path("icons")


def styles_dir() -> str:
    return resource_path("styles")


def app_data_dir(create: bool = True) -> str:
    """Katalog danych użytkownika (%LOCALAPPDATA%\\DongStack lub DONGSTACK_HOME)."""
    override = os.environ.get(ENV_HOME)
    if override:
        base = override
    else:
        local = os.environ.get("LOCALAPPDATA")
        if not local:
            # fallback (dev na innym OS / nietypowe środowisko)
            local = os.path.join(os.path.expanduser("~"), "AppData", "Local")
        base = os.path.join(local, APP_DIR_NAME)
    if create:
        _ensure_dirs(base)
    return base


def _ensure_dirs(base: str) -> None:
    for sub in ("", "covers", "logs", "backups"):
        d = os.path.join(base, sub) if sub else base
        if not os.path.isdir(d):
            try:
                os.makedirs(d)
            except OSError:
                # wyścig równoległego tworzenia — akceptowalny
                if not os.path.isdir(d):
                    raise


def db_path(home: Optional[str] = None) -> str:
    return os.path.join(home or app_data_dir(), "dongstack.sqlite")


def backups_dir(home: Optional[str] = None) -> str:
    return os.path.join(home or app_data_dir(), "backups")


def covers_dir(home: Optional[str] = None) -> str:
    return os.path.join(home or app_data_dir(), "covers")


def logs_dir(home: Optional[str] = None) -> str:
    return os.path.join(home or app_data_dir(), "logs")


def config_path(home: Optional[str] = None) -> str:
    return os.path.join(home or app_data_dir(), "config.json")


def lock_path(home: Optional[str] = None) -> str:
    return os.path.join(home or app_data_dir(), "dongstack.lock")
