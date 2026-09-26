"""Testy dotenv_lite: parsowanie i ładowanie .env (bez nadpisywania env)."""

from __future__ import annotations

import os

from app.core.dotenv_lite import find_dotenv, load_dotenv_file, parse_dotenv


def test_parse_basic():
    text = (
        "# komentarz\n"
        "\n"
        "MAL_CLIENT_ID=abc123\n"
        "MAL_CLIENT_SECRET = 'sekret z spacjami'\n"
        'QUOTED="podwojny cudzyslow"\n'
        "export EXPORTED=1\n"
        "INLINE=wartosc # komentarz w linii\n"
        "EMPTY=\n"
        "BEZ_ZNAKU_ROWNOSCI\n"
    )
    parsed = parse_dotenv(text)
    assert parsed["MAL_CLIENT_ID"] == "abc123"
    assert parsed["MAL_CLIENT_SECRET"] == "sekret z spacjami"
    assert parsed["QUOTED"] == "podwojny cudzyslow"
    assert parsed["EXPORTED"] == "1"
    assert parsed["INLINE"] == "wartosc"
    assert parsed["EMPTY"] == ""
    assert "BEZ_ZNAKU_ROWNOSCI" not in parsed


def test_parse_hash_w_hashem_wewnatrz_cytatu():
    parsed = parse_dotenv('SECRET="ab#cd"\n')
    assert parsed["SECRET"] == "ab#cd"


def test_load_does_not_override_env(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text("DONGSTACK_TEST_KEY=z_pliku\nDONGSTACK_TEST_KEY2=drugi\n", encoding="utf-8")
    monkeypatch.setenv("DONGSTACK_TEST_KEY", "z_env")
    monkeypatch.delenv("DONGSTACK_TEST_KEY2", raising=False)

    loaded = load_dotenv_file(str(env_file))
    assert loaded == {"DONGSTACK_TEST_KEY": "z_pliku", "DONGSTACK_TEST_KEY2": "drugi"}
    # env wygrywa z plikiem (priorytet warstw — specyfikacja §5.3)
    assert os.environ["DONGSTACK_TEST_KEY"] == "z_env"
    assert os.environ["DONGSTACK_TEST_KEY2"] == "drugi"


def test_load_missing_file_returns_empty(tmp_path):
    assert load_dotenv_file(str(tmp_path / "nie_ma.env")) == {}


def test_find_dotenv_in_cwd(tmp_path, monkeypatch):
    (tmp_path / ".env").write_text("X=1", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    found = find_dotenv()
    assert found is not None and found.endswith(".env")
