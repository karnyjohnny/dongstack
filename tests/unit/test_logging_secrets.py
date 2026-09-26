"""Testy logowania: SecretsFilter maskuje sekrety PRZED zapisem (R14, §12)."""

from __future__ import annotations

import logging
import os

from app.core.logging_setup import LOGGER_NAME, SecretsFilter, setup_logging

SECRET = "TESTSECRET000111222333444555666777888990aabbcc"  # fake (§12)


def test_secrets_filter_masks_message():
    records = []

    class Capture(logging.Handler):
        def emit(self, record):
            records.append(self.format(record))

    logger = logging.getLogger("test.secrets.filter")
    logger.handlers.clear()
    logger.propagate = False
    handler = Capture()
    handler.addFilter(SecretsFilter(lambda: [SECRET]))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)

    logger.info("client secret=%s użyty w żądaniu", SECRET)
    logger.info("czysta wiadomość bez sekretu")

    assert len(records) == 2
    assert SECRET not in records[0]
    assert "***" in records[0]
    assert "czysta wiadomość" in records[1]


def test_setup_logging_writes_masked_file(tmp_path, monkeypatch):
    monkeypatch.setenv("DONGSTACK_HOME", str(tmp_path))
    logger = setup_logging(level_name="DEBUG", secret_provider=lambda: [SECRET])
    logger.info("próba wycieku: %s", SECRET)
    for h in logger.handlers:
        h.flush()
    log_file = os.path.join(str(tmp_path), "logs", "dongstack.log")
    assert os.path.isfile(log_file)
    with open(log_file, encoding="utf-8") as fh:
        content = fh.read()
    assert SECRET not in content
    assert "***" in content


def test_setup_logging_idempotent(tmp_path, monkeypatch):
    monkeypatch.setenv("DONGSTACK_HOME", str(tmp_path))
    setup_logging(secret_provider=lambda: [])
    logger = setup_logging(secret_provider=lambda: [])
    assert logger.name == LOGGER_NAME
    # brak duplikatów handlerów po dwukrotnym wywołaniu
    assert len(logger.handlers) == 1
