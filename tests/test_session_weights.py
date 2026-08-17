"""Experiential god-node weighting from a session memory layer (opt-in).

GRAPHIFY_SESSION_WEIGHTS gates the feature: unset means no network call and
pure structural ranking. When enabled, per-file observation history from the
memory layer annotates god nodes and re-ranks them by
degree * (1 + ln(1 + observations)); an unreachable server degrades to the
structural ranking without failing the build.
"""
import io
import json
import urllib.error

import pytest

from graphify.session_weights import (
    apply_experiential_weights,
    fetch_file_activity,
    session_weights_base_url,
)


# --- session_weights_base_url ---

def test_disabled_by_default(monkeypatch):
    monkeypatch.delenv("GRAPHIFY_SESSION_WEIGHTS", raising=False)
    assert session_weights_base_url() is None


def test_off_values_disable(monkeypatch):
    for off in ["0", "false", "off", ""]:
        monkeypatch.setenv("GRAPHIFY_SESSION_WEIGHTS", off)
        assert session_weights_base_url() is None


def test_enabled_with_default_url(monkeypatch):
    monkeypatch.setenv("GRAPHIFY_SESSION_WEIGHTS", "1")
    assert session_weights_base_url() == "http://localhost:3111"


def test_enabled_with_explicit_url(monkeypatch):
    monkeypatch.setenv("GRAPHIFY_SESSION_WEIGHTS", "http://memory:4000/")
    assert session_weights_base_url() == "http://memory:4000"


# --- fetch_file_activity ---

class _FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def test_fetch_parses_observation_history(monkeypatch):
    body = {
        "files": [
            {
                "file": "src/auth.ts",
                "observations": [
                    {"sessionId": "s1"},
                    {"sessionId": "s1"},
                    {"sessionId": "s2"},
                ],
            },
            {"file": "src/db.ts", "observations": []},
        ]
    }

    captured = {}

    def fake_urlopen(req, timeout=None):
        captured["url"] = req.full_url
        captured["payload"] = json.loads(req.data.decode("utf-8"))
        return _FakeResponse(json.dumps(body).encode("utf-8"))

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    activity = fetch_file_activity(["src/auth.ts", "src/db.ts"], "http://localhost:3111")

    assert captured["url"] == "http://localhost:3111/agentmemory/file-context"
    assert captured["payload"] == {"files": ["src/auth.ts", "src/db.ts"]}
    # a file with no observations carries no signal and is omitted
    assert activity == {"src/auth.ts": {"observations": 3, "sessions": 2}}


def test_fetch_degrades_to_empty_on_connection_error(monkeypatch, capsys):
    def fake_urlopen(req, timeout=None):
        raise urllib.error.URLError("connection refused")

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    assert fetch_file_activity(["a.py"], "http://localhost:3111") == {}
    assert "session weights unavailable" in capsys.readouterr().err


def test_fetch_degrades_to_empty_on_malformed_body(monkeypatch):
    def fake_urlopen(req, timeout=None):
        return _FakeResponse(b"not json")

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    assert fetch_file_activity(["a.py"], "http://localhost:3111") == {}


def test_fetch_no_files_makes_no_request(monkeypatch):
    def fake_urlopen(req, timeout=None):  # pragma: no cover - must not run
        raise AssertionError("network call with no files")

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    assert fetch_file_activity([], "http://localhost:3111") == {}


# --- apply_experiential_weights ---

def _gods():
    return [
        {"id": "n1", "label": "Router", "degree": 20},
        {"id": "n2", "label": "AuthService", "degree": 18},
        {"id": "n3", "label": "Logger", "degree": 17},
    ]


def test_no_activity_keeps_structural_order():
    gods = _gods()
    assert apply_experiential_weights(gods, {"n1": "a.py"}, {}) is gods


def test_worked_on_node_outranks_same_tier_structural_hub():
    node_files = {"n1": "router.py", "n2": "auth.py", "n3": "logger.py"}
    activity = {"auth.py": {"observations": 12, "sessions": 3}}
    ranked = apply_experiential_weights(_gods(), node_files, activity)
    # 18 * (1 + ln 13) beats 20 * 1: the debugged file wins.
    assert ranked[0]["label"] == "AuthService"
    assert ranked[0]["observations"] == 12
    assert ranked[0]["sessions"] == 3
    # untouched nodes keep structural relative order
    assert [n["label"] for n in ranked[1:]] == ["Router", "Logger"]


def test_input_list_is_not_mutated():
    gods = _gods()
    node_files = {"n2": "auth.py"}
    activity = {"auth.py": {"observations": 5, "sessions": 2}}
    apply_experiential_weights(gods, node_files, activity)
    assert "observations" not in gods[1]
