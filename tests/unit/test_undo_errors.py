"""Testy UndoStack + klasyfikacja błędów ApiError."""

from __future__ import annotations

from app.core.errors import ApiError, ApiErrorKind, status_to_kind
from app.domain.undo import UndoCommand, UndoStack


def test_undo_push_pop_lifo():
    stack = UndoStack()
    c1 = UndoCommand(kind="episode", payload={"id": 1, "old": 5, "new": 6}, label="Cofnij +1")
    c2 = UndoCommand(kind="add", payload={"id": 2}, label="Cofnij dodanie")
    stack.push(c1)
    stack.push(c2)
    assert len(stack) == 2
    assert stack.pop() is c2
    assert stack.peek() is c1
    assert stack.pop() is c1
    assert stack.pop() is None
    assert not stack


def test_undo_bounded():
    stack = UndoStack(maxlen=2)
    for i in range(5):
        stack.push(UndoCommand(kind="episode", payload={"i": i}, label=str(i)))
    assert len(stack) == 2
    assert stack.pop().payload["i"] == 4
    assert stack.pop().payload["i"] == 3


def test_undo_clear():
    stack = UndoStack()
    stack.push(UndoCommand(kind="remove", payload={}, label="x"))
    stack.clear()
    assert len(stack) == 0


def test_undo_command_get():
    cmd = UndoCommand(kind="status", payload={"old": "watching", "new": "completed"}, label="l")
    assert cmd.get("old") == "watching"
    assert cmd.get("missing", "def") == "def"


# --- klasyfikacja błędów (§5.1) -------------------------------------------------
def test_status_to_kind():
    assert status_to_kind(400) == ApiErrorKind.BAD_REQUEST
    assert status_to_kind(401) == ApiErrorKind.AUTH
    assert status_to_kind(403, looks_like_html=False) == ApiErrorKind.AUTH
    assert status_to_kind(403, looks_like_html=True) == ApiErrorKind.THROTTLED_BAN  # F13
    assert status_to_kind(404) == ApiErrorKind.NOT_FOUND
    assert status_to_kind(429) == ApiErrorKind.RATE_LIMITED
    assert status_to_kind(500) == ApiErrorKind.SERVER
    assert status_to_kind(503) == ApiErrorKind.SERVER
    assert status_to_kind(418) == ApiErrorKind.PROVIDER


def test_apierror_retryable_and_user_message():
    e429 = ApiError(ApiErrorKind.RATE_LIMITED, "slow down", provider="mal", status=429)
    assert e429.retryable
    assert "chwilę" in e429.user_message()
    e400 = ApiError(ApiErrorKind.BAD_REQUEST, "bad", provider="mal", status=400)
    assert not e400.retryable
    assert "Error 400" not in e400.user_message()  # Biblia §49: brak kodów w UX
    assert "Exception" not in e400.user_message()
    assert "400" not in e400.user_message()


def test_apierror_repr_no_secret_leak():
    e = ApiError(ApiErrorKind.AUTH, "unauthorized", provider="mal", status=401)
    r = repr(e)
    assert "unauthorized" in r and "mal" in r
