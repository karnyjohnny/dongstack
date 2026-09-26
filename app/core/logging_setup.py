"""app/core/logging_setup.py — logowanie z rotacją i filtrem maskującym sekrety.

Rygory (§12, R14):
- RotatingFileHandler 3×1 MB w %LOCALAPPDATA%\\DongStack\\logs\\dongstack.log,
- SecretsFilter: każda wartość sekretu z konfiguracji jest zamieniana na '***'
  PRZED zapisem (nie polegamy na dyscyplinie wywołań logujących),
- brak logów na stderr w trybie windowed (frozen exe nie ma konsoli).
"""

from __future__ import annotations

import logging
import logging.handlers
import os
from typing import Callable, List, Optional

from app.core import paths

LOGGER_NAME = "dongstack"
LOG_FILE = "dongstack.log"
MAX_BYTES = 1_000_000
BACKUP_COUNT = 3
_MIN_SECRET_LEN = 4

_LEVELS = {
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "WARNING": logging.WARNING,
    "ERROR": logging.ERROR,
    "CRITICAL": logging.CRITICAL,
}


class SecretsFilter(logging.Filter):
    """Podmienia znane sekrety na '***' w sformatowanej wiadomości rekordu."""

    def __init__(self, secret_provider: Optional[Callable[[], List[str]]] = None) -> None:
        super().__init__()
        self._provider = secret_provider or (lambda: [])

    def filter(self, record: logging.LogRecord) -> bool:
        secrets = [s for s in self._provider() if s and len(s) >= _MIN_SECRET_LEN]
        if secrets:
            try:
                text = record.getMessage()
            except Exception:  # noqa: BLE001 - uszkodzony rekord nie może zatrzymać logu
                return True
            changed = False
            for sec in secrets:
                if sec in text:
                    text = text.replace(sec, "***")
                    changed = True
            if changed:
                record.msg = text
                record.args = ()
        return True


def setup_logging(
    level_name: str = "INFO",
    log_dir: Optional[str] = None,
    secret_provider: Optional[Callable[[], List[str]]] = None,
    stream: bool = False,
) -> logging.Logger:
    """Konfiguruje logger 'dongstack' (idempotentnie) i zwraca go."""
    logger = logging.getLogger(LOGGER_NAME)
    level = _LEVELS.get((level_name or "INFO").upper(), logging.INFO)
    logger.setLevel(level)
    logger.propagate = False

    # idempotentność: usuń stare handlery przy ponownym wywołaniu (testy, restart)
    for h in list(logger.handlers):
        logger.removeHandler(h)
        try:
            h.close()
        except Exception:  # noqa: BLE001
            pass

    fmt = logging.Formatter(
        "%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    secrets_filter = SecretsFilter(secret_provider)

    try:
        target_dir = log_dir or paths.logs_dir()
        if not os.path.isdir(target_dir):
            os.makedirs(target_dir)
        file_handler: logging.Handler = logging.handlers.RotatingFileHandler(
            os.path.join(target_dir, LOG_FILE),
            maxBytes=MAX_BYTES,
            backupCount=BACKUP_COUNT,
            encoding="utf-8",
        )
        file_handler.setFormatter(fmt)
        file_handler.addFilter(secrets_filter)
        logger.addHandler(file_handler)
    except OSError:
        # brak możliwości pisania logów nie może blokować startu aplikacji
        pass

    if stream:
        sh = logging.StreamHandler()
        sh.setFormatter(fmt)
        sh.addFilter(secrets_filter)
        logger.addHandler(sh)

    return logger


def get_logger(suffix: str = "") -> logging.Logger:
    """Logger podrzędny, np. get_logger('api.mal') → 'dongstack.api.mal'."""
    if suffix:
        return logging.getLogger(LOGGER_NAME + "." + suffix)
    return logging.getLogger(LOGGER_NAME)
