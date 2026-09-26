"""app/core/config.py — ConfigService: warstwowa konfiguracja + maskowanie sekretów.

Priorytet źródeł (specyfikacja §5.3, §12):
    1. zmienne środowiskowe (os.environ — w tym wartości załadowane z .env),
    2. config.json w katalogu danych (%LOCALAPPDATA%\\DongStack),
    3. wartości domyślne.

Rygory (R14):
- sekrety (klucze *_SECRET) NIGDY nie są utrwalane w config.json,
- repr() i logi maskują sekrety (secret_values() zasila SecretsFilter),
- Client Secret w v1 nie jest w ogóle potrzebny (publiczne endpointy MAL — F9).
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional

from app.core import paths

# Klucze konfiguracyjne (nazwy zgodne z treścią zadania / .env.example)
KEY_CLIENT_ID = "MAL_CLIENT_ID"
KEY_CLIENT_SECRET = "MAL_CLIENT_SECRET"  # tylko v2/OAuth2; nigdy utrwalany
KEY_PROVIDER = "DONGSTACK_PREFERRED_PROVIDER"  # "mal" | "anilist"
KEY_LOG_LEVEL = "DONGSTACK_LOG_LEVEL"
KEY_ANIMATIONS = "DONGSTACK_ANIMATIONS"  # "0"/"1" (R9: domyślnie wyłączone)
KEY_LAST_FILTER = "DONGSTACK_LAST_FILTER"  # pamiętany filtr statusów (QoL)
KEY_LAST_SORT = "DONGSTACK_LAST_SORT"  # pamiętany sort (QoL)
KEY_SKIP_CLIENT_ID = "DONGSTACK_SKIP_CLIENT_ID"  # „pomiń” z first-run (§5.5)

SECRET_KEYS = frozenset({KEY_CLIENT_SECRET})

# Klucze utrwalane w config.json (whitelist — sekretów nie ma i nie będzie)
_PERSISTABLE = frozenset(
    {
        KEY_CLIENT_ID,
        KEY_PROVIDER,
        KEY_LOG_LEVEL,
        KEY_ANIMATIONS,
        KEY_LAST_FILTER,
        KEY_LAST_SORT,
        KEY_SKIP_CLIENT_ID,
    }
)

_DEFAULTS: Dict[str, str] = {
    KEY_PROVIDER: "mal",
    KEY_LOG_LEVEL: "INFO",
    KEY_ANIMATIONS: "0",
}

_VALID_PROVIDERS = ("mal", "anilist")


def _mask(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 4:
        return "***"
    return value[:2] + "***" + value[-2:]


class ConfigService:
    """Warstwowa konfiguracja aplikacji. Tworzona raz w bootstrapie (main.py)."""

    def __init__(
        self, config_file: Optional[str] = None, env: Optional[Dict[str, str]] = None
    ) -> None:
        self._env: Dict[str, str] = dict(env) if env is not None else None  # type: ignore[assignment]
        self._config_file = config_file or paths.config_path()
        self._file_cfg: Dict[str, Any] = self._load_file()

    # --- odczyt -------------------------------------------------------------
    def _environ(self) -> Dict[str, str]:
        return self._env if self._env is not None else os.environ

    def get(self, key: str, default: Optional[str] = None) -> Optional[str]:
        env_val = self._environ().get(key)
        if env_val is not None and env_val != "":
            return env_val
        file_val = self._file_cfg.get(key)
        if file_val is not None and file_val != "":
            return str(file_val)
        if default is not None:
            return default
        return _DEFAULTS.get(key)

    def get_bool(self, key: str, default: bool = False) -> bool:
        raw = self.get(key)
        if raw is None:
            return default
        return str(raw).strip().lower() in ("1", "true", "yes", "on")

    @property
    def mal_client_id(self) -> str:
        return self.get(KEY_CLIENT_ID, "") or ""

    @property
    def has_client_id(self) -> bool:
        return bool(self.mal_client_id.strip())

    @property
    def preferred_provider(self) -> str:
        prov = (self.get(KEY_PROVIDER, "mal") or "mal").strip().lower()
        return prov if prov in _VALID_PROVIDERS else "mal"

    @property
    def animations_enabled(self) -> bool:
        return self.get_bool(KEY_ANIMATIONS, False)

    @property
    def log_level(self) -> str:
        return (self.get(KEY_LOG_LEVEL, "INFO") or "INFO").strip().upper()

    # --- zapis (tylko whitelist, bez sekretów) --------------------------------
    def set(self, key: str, value: str) -> None:
        if key in SECRET_KEYS:
            raise ValueError("Odmowa utrwalenia sekretu w config.json (R14/§12): %s" % key)
        if key not in _PERSISTABLE:
            raise ValueError("Klucz nieutrwalalny: %s" % key)
        self._file_cfg[key] = value
        self._save_file()

    def _load_file(self) -> Dict[str, Any]:
        try:
            with open(self._config_file, encoding="utf-8") as fh:
                data = json.load(fh)
            if isinstance(data, dict):
                # obrona: gdyby ktoś ręcznie wpisał sekret do pliku — nie używamy go
                return {k: v for k, v in data.items() if k not in SECRET_KEYS}
        except (OSError, ValueError):
            pass
        return {}

    def _save_file(self) -> None:
        tmp = self._config_file + ".tmp"
        try:
            parent = os.path.dirname(self._config_file)
            if parent and not os.path.isdir(parent):
                os.makedirs(parent)
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(self._file_cfg, fh, indent=2, sort_keys=True)
            os.replace(tmp, self._config_file)
        except OSError:
            # brak zapisu nie może wywracać aplikacji — wartość zostaje w pamięci
            try:
                if os.path.isfile(tmp):
                    os.remove(tmp)
            except OSError:
                pass

    # --- maskowanie (R14) -----------------------------------------------------
    def secret_values(self) -> List[str]:
        """Niepuste wartości sekretów (z env) — do filtrowania logów."""
        out: List[str] = []
        for key in sorted(SECRET_KEYS):
            val = self._environ().get(key, "")
            if val and len(val) >= 4:
                out.append(val)
        return out

    def masked_snapshot(self) -> Dict[str, str]:
        """Zrzut konfiguracji do logów — sekrety zamaskowane."""
        snap: Dict[str, str] = {}
        for key in sorted(_PERSISTABLE | SECRET_KEYS):
            val = self.get(key, "")
            snap[key] = _mask(val) if (key in SECRET_KEYS and val) else (val or "")
        return snap

    def __repr__(self) -> str:
        return "ConfigService(%r)" % (self.masked_snapshot(),)
