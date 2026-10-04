"""Tests for graphify.jev_decide — the JEV (TypeSafe System One) decision layer.

All tests mock the HTTP layer; none hit the network. The fail-open contract is
the core guarantee: JEV unavailable (no key / timeout / bad payload) must never
block or change the deterministic heuristic path.
"""
import json
from unittest import mock

import pytest

from graphify import jev_decide as jd


def _payload(answers, model="jev-1.13.0", usage=None):
    return {"model": model, "answers": answers, "usage": usage or {"input_tokens": 10, "output_tokens": 5}}


# ── primitives ────────────────────────────────────────────────────────────────


def test_noul_parses_probability(monkeypatch):
    monkeypatch.setenv("TYPESAFE_API_KEY", "test-key")
    with mock.patch("urllib.request.urlopen") as m:
        m.return_value.__enter__ = lambda s: mock.Mock(
            read=lambda: json.dumps(_payload({"noul": {"type": "noul", "noul": 0.9}})).encode()
        )
        m.return_value.__exit__ = lambda *a: None
        assert jd.jev_noul("state", "question?") == 0.9


def test_noul_missing_key_returns_none(monkeypatch):
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    assert jd.jev_noul("state", "question?") is None


def test_noul_timeout_returns_none(monkeypatch):
    monkeypatch.setenv("TYPESAFE_API_KEY", "test-key")
    with mock.patch("urllib.request.urlopen", side_effect=TimeoutError("slow")):
        assert jd.jev_noul("state", "question?") is None


def test_noul_http_error_returns_none(monkeypatch):
    monkeypatch.setenv("TYPESAFE_API_KEY", "test-key")
    import urllib.error
    with mock.patch("urllib.request.urlopen", side_effect=urllib.error.URLError("down")):
        assert jd.jev_noul("state", "question?") is None


def test_noul_bad_json_returns_none(monkeypatch):
    monkeypatch.setenv("TYPESAFE_API_KEY", "test-key")
    with mock.patch("urllib.request.urlopen") as m:
        m.return_value.__enter__ = lambda s: mock.Mock(read=lambda: b"not json")
        m.return_value.__exit__ = lambda *a: None
        assert jd.jev_noul("state", "question?") is None


def test_choice_parses_confidence(monkeypatch):
    monkeypatch.setenv("TYPESAFE_API_KEY", "test-key")
    with mock.patch("urllib.request.urlopen") as m:
        m.return_value.__enter__ = lambda s: mock.Mock(
            read=lambda: json.dumps(_payload({
                "route": {"type": "choice", "choice": "keep", "confidence": 0.9,
                          "probabilities": {"keep": 0.9, "drop": 0.1}},
            })).encode()
        )
        m.return_value.__exit__ = lambda *a: None
        out = jd.jev_choice("state", "pick", {"keep": "yes", "drop": "no"}, qid="route")
        assert out["choice"] == "keep"
        assert out["confidence"] == 0.9


def test_score_parses_weighted_value(monkeypatch):
    monkeypatch.setenv("TYPESAFE_API_KEY", "test-key")
    with mock.patch("urllib.request.urlopen") as m:
        m.return_value.__enter__ = lambda s: mock.Mock(
            read=lambda: json.dumps(_payload({
                "q": {"type": "score", "score": 1.84, "confidence": 0.76,
                      "legend": {"0": "low", "1": "mid", "2": "high"},
                      "probabilities": {"0": 0.04, "1": 0.09, "2": 0.87}},
            })).encode()
        )
        m.return_value.__exit__ = lambda *a: None
        out = jd.jev_score("state", "rate", ["low", "mid", "high"], qid="q")
        assert out["score"] == 1.84
        assert out["confidence"] == 0.76


# ── action lines ──────────────────────────────────────────────────────────────


def test_decide_keep_threshold():
    assert jd.decide_keep(0.8) is True          # p > 0.75
    assert jd.decide_keep(0.74) is False         # p <= 0.75
    assert jd.decide_keep(0.8, conf=0.9) is True
    assert jd.decide_keep(0.8, conf=0.5) is None  # low confidence → fall back
    assert jd.decide_keep(None) is None           # unavailable → fall back


def test_score_positive_threshold():
    assert jd.score_positive(1.8, conf=0.9) is True
    assert jd.score_positive(1.0, conf=0.9) is False
    assert jd.score_positive(1.8, conf=0.3) is None
    assert jd.score_positive(None) is None


# ── decision-point wrappers (metadata out, fail-open) ─────────────────────────


def test_judge_surprise_keep_positive(monkeypatch):
    monkeypatch.setenv("TYPESAFE_API_KEY", "test-key")
    with mock.patch("urllib.request.urlopen") as m:
        m.return_value.__enter__ = lambda s: mock.Mock(
            read=lambda: json.dumps(_payload({"noul": {"type": "noul", "noul": 0.91}})).encode()
        )
        m.return_value.__exit__ = lambda *a: None
        assert jd.judge_surprise_keep("auth_service", "billing_service", "calls",
                                      "cross-repo edge") is True


def test_judge_surprise_keep_negative(monkeypatch):
    monkeypatch.setenv("TYPESAFE_API_KEY", "test-key")
    with mock.patch("urllib.request.urlopen") as m:
        m.return_value.__enter__ = lambda s: mock.Mock(
            read=lambda: json.dumps(_payload({"noul": {"type": "noul", "noul": 0.2}})).encode()
        )
        m.return_value.__exit__ = lambda *a: None
        assert jd.judge_surprise_keep("a", "b", "calls", "why") is False


def test_judge_surprise_keep_fail_open(monkeypatch):
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    assert jd.judge_surprise_keep("a", "b", "calls", "why") is None


def test_judge_question_value(monkeypatch):
    monkeypatch.setenv("TYPESAFE_API_KEY", "test-key")
    with mock.patch("urllib.request.urlopen") as m:
        m.return_value.__enter__ = lambda s: mock.Mock(
            read=lambda: json.dumps(_payload({
                "score": {"type": "score", "score": 1.9, "confidence": 0.95,
                          "legend": {"0": "low", "1": "mid", "2": "high"},
                          "probabilities": {"0": 0.0, "1": 0.1, "2": 0.9}},
            })).encode()
        )
        m.return_value.__exit__ = lambda *a: None
        assert jd.judge_question_value("ambiguous_edge", "Q?", "why") is True


def test_judge_dedup_same(monkeypatch):
    monkeypatch.setenv("TYPESAFE_API_KEY", "test-key")
    with mock.patch("urllib.request.urlopen") as m:
        m.return_value.__enter__ = lambda s: mock.Mock(
            read=lambda: json.dumps(_payload({"noul": {"type": "noul", "noul": 0.98}})).encode()
        )
        m.return_value.__exit__ = lambda *a: None
        assert jd.judge_dedup_same("User Profile", "user_profile", "a.py", "b.py") is True


def test_judge_label_quality(monkeypatch):
    monkeypatch.setenv("TYPESAFE_API_KEY", "test-key")
    with mock.patch("urllib.request.urlopen") as m:
        m.return_value.__enter__ = lambda s: mock.Mock(
            read=lambda: json.dumps(_payload({
                "score": {"type": "score", "score": 0.3, "confidence": 0.9,
                          "legend": {"0": "bad", "1": "ok", "2": "good"},
                          "probabilities": {"0": 0.8, "1": 0.15, "2": 0.05}},
            })).encode()
        )
        m.return_value.__exit__ = lambda *a: None
        assert jd.judge_label_quality(["auth_service"], "wrong name") is False


def test_judge_god_noise(monkeypatch):
    monkeypatch.setenv("TYPESAFE_API_KEY", "test-key")
    with mock.patch("urllib.request.urlopen") as m:
        m.return_value.__enter__ = lambda s: mock.Mock(
            read=lambda: json.dumps(_payload({"noul": {"type": "noul", "noul": 0.99}})).encode()
        )
        m.return_value.__exit__ = lambda *a: None
        assert jd.judge_god_noise("str", "x.py") is True


def test_available_probe(monkeypatch):
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    assert jd.available() is False
    monkeypatch.setenv("TYPESAFE_API_KEY", "k")
    assert jd.available() is True


def test_request_payload_shape(monkeypatch):
    """The wire payload must be the documented System One shape."""
    monkeypatch.setenv("TYPESAFE_API_KEY", "test-key")
    seen = {}
    with mock.patch("urllib.request.urlopen") as m:
        def side(req, **kw):
            seen["body"] = json.loads(req.data)
            seen["auth"] = req.headers.get("Authorization", "")
            m_ = mock.Mock()
            m_.__enter__ = lambda s: m_
            m_.read = lambda: json.dumps(_payload({"noul": {"type": "noul", "noul": 0.5}})).encode()
            m_.__exit__ = lambda *a: None
            return m_
        m.side_effect = side
        jd.jev_noul("my state", "is it x?")
    assert seen["body"]["model"] == jd.DEFAULT_MODEL
    assert seen["body"]["state"] == "my state"
    assert seen["body"]["questions"]["noul"]["type"] == "noul"
    assert seen["body"]["questions"]["noul"]["instructions"] == "is it x?"
    assert seen["auth"] == "Bearer test-key"
