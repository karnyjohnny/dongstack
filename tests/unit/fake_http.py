"""Fake sesja requests do testów klientów API (bez sieci, bez zależności `responses`)."""

from __future__ import annotations

import json


class FakeResponse:
    def __init__(self, status=200, body=None, headers=None, text_body=None):
        self.status_code = status
        self._body = body
        self.headers = headers or {"Content-Type": "application/json"}
        self._text = text_body

    def json(self):
        if self._text is not None:
            raise ValueError("not json")
        return self._body

    @property
    def text(self):
        return self._text or json.dumps(self._body or {})


class FakeSession:
    """Rejestruje wywołania i zwraca zaplanowane odpowiedzi (kolejka lub callable)."""

    def __init__(self, plan=None):
        self.calls = []  # (method, url, kwargs)
        self._plan = plan or []
        self._idx = 0

    def _next(self, method, url, kwargs):
        self.calls.append((method, url, kwargs))
        if callable(self._plan):
            return self._plan(method, url, kwargs, len(self.calls) - 1)
        if self._idx < len(self._plan):
            resp = self._plan[self._idx]
            self._idx += 1
            return resp
        raise AssertionError(
            "niezaplanowane wywołanie #%d: %s %s" % (len(self.calls) - 1, method, url)
        )

    def get(self, url, **kwargs):
        return self._next("GET", url, kwargs)

    def post(self, url, **kwargs):
        return self._next("POST", url, kwargs)
