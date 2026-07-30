"""Unit tests for the embedded-engine auto-fallback in store._connect.

These mock the FalkorDB client so they run without a live server (and without
the embedded engine, which needs Python >= 3.12) — they verify the dispatch
logic only."""
from __future__ import annotations

import falkordb
import pytest

import graphify.store as st


class _FakeConn:
    def __init__(self, ok: bool):
        self._ok = ok

    def ping(self):
        if not self._ok:
            raise ConnectionError("Connection refused")
        return True


class _FakeDB:
    def __init__(self, ok: bool = True, **kwargs):
        self.connection = _FakeConn(ok)


def test_uses_server_when_reachable(monkeypatch):
    fake = _FakeDB(ok=True)
    monkeypatch.setattr(falkordb, "FalkorDB", lambda **kw: fake)
    monkeypatch.setattr(st, "_connect_lite", lambda dbfile: pytest.fail("must not fall back"))
    assert st._connect("falkordb://localhost:6379") is fake


def test_local_server_down_falls_back_to_lite(monkeypatch):
    sentinel = object()
    monkeypatch.setattr(falkordb, "FalkorDB", lambda **kw: _FakeDB(ok=False))
    monkeypatch.setattr(st, "_connect_lite", lambda dbfile: sentinel)
    assert st._connect("falkordb://localhost:6379") is sentinel


def test_remote_server_down_raises(monkeypatch):
    """A connection failure to an explicitly-configured remote host must surface,
    not silently switch to a local empty embedded DB."""
    monkeypatch.setattr(falkordb, "FalkorDB", lambda **kw: _FakeDB(ok=False))
    monkeypatch.setattr(st, "_connect_lite", lambda dbfile: pytest.fail("no fallback for remote"))
    with pytest.raises(ConnectionError):
        st._connect("falkordb://db.internal.example.com:6379")


def test_local_down_without_lite_gives_helpful_error(monkeypatch):
    def _no_lite(dbfile):
        raise ImportError("redislite not installed")

    monkeypatch.setattr(falkordb, "FalkorDB", lambda **kw: _FakeDB(ok=False))
    monkeypatch.setattr(st, "_connect_lite", _no_lite)
    with pytest.raises(ConnectionError) as exc:
        st._connect("falkordb://localhost:6379")
    assert "falkordblite" in str(exc.value)
