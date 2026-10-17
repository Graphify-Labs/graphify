"""Tests for the issue-triage classifier (``tools/triage``).

The classifier must never invent a label and must fail open: any provider error,
timeout, or malformed reply yields no labels, so the workflow leaves the issue in
``status/need-triage``. These tests exercise the pure parse/normalise path with a
fake model, so they never touch the network.
"""
from __future__ import annotations

import json
import re
import sys
import urllib.error
from pathlib import Path

import pytest

# tests/ -> repo root is one parent up; put it on the path so tools.triage
# imports regardless of pytest's import mode (same as test_skillgen.py).
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.triage import classify, taxonomy  # noqa: E402

_TRIAGE_KNOBS = (
    "TRIAGE_API_KEY",
    "TRIAGE_PROVIDER",
    "TRIAGE_MODEL",
    "TRIAGE_BASE_URL",
    "TRIAGE_TIMEOUT",
    "TRIAGE_MAX_TOKENS",
)


def _clear_keys(monkeypatch):
    """Remove every provider key and TRIAGE_* knob so detection is deterministic."""
    for provider in classify.PROVIDERS.values():
        for name in provider.key_envs:
            monkeypatch.delenv(name, raising=False)
    for name in _TRIAGE_KNOBS:
        monkeypatch.delenv(name, raising=False)


def _issue(**overrides):
    issue = {"number": 1, "title": "Crash on parse", "body": "It crashes", "labels": []}
    issue.update(overrides)
    return issue


# -- config ---------------------------------------------------------------


def test_load_config_defaults_to_gemini_when_only_google_key_set(monkeypatch):
    _clear_keys(monkeypatch)
    monkeypatch.setenv("GOOGLE_API_KEY", "gk")
    cfg = classify.load_config()
    assert cfg is not None
    assert cfg.api_key == "gk"
    assert cfg.model == classify.DEFAULT_MODEL
    assert cfg.base_url == classify.DEFAULT_BASE_URL.rstrip("/")


def test_triage_api_key_wins_over_gemini(monkeypatch):
    _clear_keys(monkeypatch)
    monkeypatch.setenv("GEMINI_API_KEY", "gemini")
    monkeypatch.setenv("TRIAGE_API_KEY", "triage")
    assert classify.load_config().api_key == "triage"


def test_load_config_overridable(monkeypatch):
    _clear_keys(monkeypatch)
    monkeypatch.setenv("TRIAGE_API_KEY", "k")
    monkeypatch.setenv("TRIAGE_MODEL", "custom-model")
    monkeypatch.setenv("TRIAGE_BASE_URL", "https://example.test/v1/")
    cfg = classify.load_config()
    assert cfg.model == "custom-model"
    assert cfg.base_url == "https://example.test/v1"


def test_load_config_none_without_key(monkeypatch):
    _clear_keys(monkeypatch)
    assert classify.load_config() is None


def test_load_config_reads_max_tokens(monkeypatch):
    _clear_keys(monkeypatch)
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    assert classify.load_config().max_tokens == classify.MAX_TOKENS
    monkeypatch.setenv("TRIAGE_MAX_TOKENS", "4096")
    assert classify.load_config().max_tokens == 4096
    monkeypatch.setenv("TRIAGE_MAX_TOKENS", "not-a-number")
    assert classify.load_config().max_tokens == classify.MAX_TOKENS


def test_load_config_detects_openai(monkeypatch):
    _clear_keys(monkeypatch)
    monkeypatch.setenv("OPENAI_API_KEY", "ok")
    cfg = classify.load_config()
    assert cfg.provider == "openai"
    assert cfg.model == "gpt-4.1-mini"
    assert "api.openai.com" in cfg.base_url


def test_triage_provider_overrides_detection(monkeypatch):
    _clear_keys(monkeypatch)
    monkeypatch.setenv("OPENAI_API_KEY", "ok")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "dk")
    monkeypatch.setenv("TRIAGE_PROVIDER", "deepseek")
    assert classify.load_config().provider == "deepseek"


def test_load_candidates_splits_model_list(monkeypatch):
    _clear_keys(monkeypatch)
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    monkeypatch.setenv("TRIAGE_MODEL", "gemini-3.8-flash, gemini-2.5-flash")
    cands = classify.load_candidates()
    assert [c.model for c in cands] == ["gemini-3.8-flash", "gemini-2.5-flash"]
    assert all(c.provider == "gemini" for c in cands)


def test_load_candidates_mixes_providers_and_drops_keyless(monkeypatch):
    _clear_keys(monkeypatch)
    monkeypatch.setenv("OPENAI_API_KEY", "ok")
    monkeypatch.setenv(
        "TRIAGE_MODEL", "openai:gpt-4.1-mini,gemini:gemini-2.5-flash,ollama:qwen2.5-coder:7b"
    )
    cands = classify.load_candidates()
    # gemini and ollama have no key here -> only the openai candidate survives
    assert [(c.provider, c.model) for c in cands] == [("openai", "gpt-4.1-mini")]


def test_load_candidates_dedupes(monkeypatch):
    _clear_keys(monkeypatch)
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    monkeypatch.setenv("TRIAGE_MODEL", "gemini-2.5-flash,gemini-2.5-flash")
    assert len(classify.load_candidates()) == 1


def test_ollama_colon_model_is_not_treated_as_a_provider(monkeypatch):
    _clear_keys(monkeypatch)
    monkeypatch.setenv("TRIAGE_PROVIDER", "ollama")
    monkeypatch.setenv("OLLAMA_API_KEY", "x")
    monkeypatch.setenv("TRIAGE_MODEL", "qwen2.5-coder:7b")
    cands = classify.load_candidates()
    assert [(c.provider, c.model) for c in cands] == [("ollama", "qwen2.5-coder:7b")]


def test_main_falls_back_to_next_model(monkeypatch, capsys):
    _clear_keys(monkeypatch)
    monkeypatch.setenv("TRIAGE_API_KEY", "k")
    monkeypatch.setenv("TRIAGE_MODEL", "model-a,model-b")
    monkeypatch.setenv("ISSUE_JSON", json.dumps(_issue()))

    def fake(cfg, messages):
        if cfg.model == "model-a":
            raise RuntimeError("429")
        return '{"area": ["area/cli"], "kind": "kind/bug"}'

    monkeypatch.setattr(classify, "call_model", fake)
    assert classify.main() == 0
    payload = json.loads(capsys.readouterr().out.strip())
    assert payload["action"] == "triaged"
    assert payload["model"] == "model-b"
    assert payload["area"] == ["area/cli"]


def test_main_skips_when_all_candidates_fail(monkeypatch, capsys):
    _clear_keys(monkeypatch)
    monkeypatch.setenv("TRIAGE_API_KEY", "k")
    monkeypatch.setenv("TRIAGE_MODEL", "model-a,model-b")
    monkeypatch.setenv("ISSUE_JSON", json.dumps(_issue()))

    def boom(cfg, messages):
        raise RuntimeError("down")

    monkeypatch.setattr(classify, "call_model", boom)
    assert classify.main() == 0
    payload = json.loads(capsys.readouterr().out.strip())
    assert payload["action"] == "skipped"


# -- allowlist enforcement ------------------------------------------------


def test_normalise_drops_unknown_labels():
    out = classify.normalise({"area": ["area/extract", "area/nonsense"], "kind": "kind/bug"})
    assert out["area"] == ["area/extract"]
    assert out["kind"] == "kind/bug"


def test_normalise_defaults_when_nothing_usable():
    out = classify.normalise({})
    assert out["area"] == ["area/other"]
    assert out["kind"] == "kind/other"
    assert out["good_first_issue"] is False
    assert out["confidence"] == "low"


def test_normalise_caps_areas_at_two():
    out = classify.normalise({"area": ["area/extract", "area/build", "area/cli"]})
    assert out["area"] == ["area/extract", "area/build"]


def test_normalise_accepts_single_area_string():
    out = classify.normalise({"area": "area/query", "kind": "kind/question"})
    assert out["area"] == ["area/query"]


def test_normalise_dedupes_areas():
    out = classify.normalise({"area": ["area/cli", "area/cli"]})
    assert out["area"] == ["area/cli"]


def test_normalise_non_string_kind_does_not_raise():
    # A list/set/dict here used to raise TypeError on the frozenset membership and
    # escape fail-open (regression guard).
    for bad in (["kind/bug"], {"kind/bug"}, 5, None):
        out = classify.normalise({"kind": bad, "area": ["area/cli"]})
        assert out["kind"] == "kind/other"
        assert out["area"] == ["area/cli"]


def test_good_first_issue_requires_real_boolean():
    assert classify.normalise({"good_first_issue": "true"})["good_first_issue"] is False
    assert classify.normalise({"good_first_issue": True})["good_first_issue"] is True


def test_gfi_reason_is_trimmed_and_capped():
    out = classify.normalise({"good_first_issue": True, "gfi_reason": "  " + "x" * 500})
    assert len(out["gfi_reason"]) == classify.MAX_REASON_CHARS


def test_confidence_must_be_known_value():
    assert classify.normalise({"confidence": "certain"})["confidence"] == "low"
    assert classify.normalise({"confidence": "high"})["confidence"] == "high"


# -- reply parsing --------------------------------------------------------


def test_parse_reply_tolerates_code_fences():
    out = classify.parse_reply('```json\n{"area": ["area/cli"], "kind": "kind/feature"}\n```')
    assert out["area"] == ["area/cli"]
    assert out["kind"] == "kind/feature"


def test_parse_reply_extracts_object_from_prose():
    out = classify.parse_reply('Sure: {"area": ["area/docs"], "kind": "kind/docs"} done')
    assert out["area"] == ["area/docs"]


def test_parse_reply_takes_first_of_two_objects():
    out = classify.parse_reply('{"area": ["area/cli"], "kind": "kind/bug"} {"x": 1}')
    assert out["area"] == ["area/cli"]
    assert out["kind"] == "kind/bug"


@pytest.mark.parametrize("reply", ["", "not json", "[]", "{broken", "null"])
def test_parse_reply_none_on_bad_output(reply):
    assert classify.parse_reply(reply) is None


# -- classify_issue -------------------------------------------------------


def test_classify_issue_uses_model_result():
    out = classify.classify_issue(
        _issue(), lambda _i: json.dumps({"area": ["area/query"], "kind": "kind/bug"})
    )
    assert out["area"] == ["area/query"]
    assert out["kind"] == "kind/bug"


def test_classify_issue_fails_open_on_model_error():
    def boom(_i):
        raise RuntimeError("network down")

    assert classify.classify_issue(_issue(), boom) is None


class _FakeResponse:
    """Minimal stand-in for urllib's response context manager."""

    def __init__(self, payload: dict):
        self._body = json.dumps(payload).encode("utf-8")

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False


def test_call_model_posts_and_parses(monkeypatch):
    captured = {}

    def fake_urlopen(request, timeout=None):
        captured["url"] = request.full_url
        captured["auth"] = request.get_header("Authorization")
        captured["body"] = json.loads(request.data.decode("utf-8"))
        content = '{"area": ["area/cli"], "kind": "kind/feature"}'
        return _FakeResponse({"choices": [{"message": {"content": content}}]})

    monkeypatch.setattr(classify.urllib.request, "urlopen", fake_urlopen)
    cfg = classify.Config(
        base_url="https://example.test/v1", model="m", api_key="k", timeout=5, max_tokens=512
    )
    out = classify.classify_issue(
        _issue(), lambda i: classify.call_model(cfg, classify.build_messages(i))
    )
    assert out["area"] == ["area/cli"]
    assert out["kind"] == "kind/feature"
    assert captured["url"] == "https://example.test/v1/chat/completions"
    assert captured["auth"] == "Bearer k"
    assert captured["body"]["model"] == "m"
    assert captured["body"]["max_tokens"] == 512


def test_build_messages_includes_allowlist_and_definition():
    system = classify.build_messages(_issue())[0]["content"]
    assert "area/extract" in system
    assert "kind/bug" in system
    assert taxonomy.GFI_DEFINITION in system


def test_slim_issue_truncates_body_and_extracts_labels():
    out = classify._slim_issue(_issue(body="x" * 10000, labels=[{"name": "bug"}]))
    assert len(out["body"]) == classify.MAX_BODY_CHARS
    assert out["labels"] == ["bug"]


# -- taxonomy -------------------------------------------------------------


def test_managed_labels_are_namespaced_and_unique():
    names = [label.name for label in taxonomy.all_managed_labels()]
    assert len(names) == len(set(names))
    assert all("/" in name for name in names)


def test_model_selectable_sets_match_taxonomy():
    assert taxonomy.MODEL_SELECTABLE_AREA == {label.name for label in taxonomy.AREAS}
    assert taxonomy.MODEL_SELECTABLE_KIND == {label.name for label in taxonomy.KINDS}


# -- CLI contract ---------------------------------------------------------


def test_main_skips_without_key_and_exits_zero(monkeypatch, capsys):
    _clear_keys(monkeypatch)
    monkeypatch.setenv("ISSUE_JSON", json.dumps(_issue()))
    assert classify.main() == 0
    payload = json.loads(capsys.readouterr().out.strip())
    assert payload["action"] == "skipped"


def test_main_emits_single_json_object(monkeypatch, capsys):
    _clear_keys(monkeypatch)
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    monkeypatch.setenv("ISSUE_JSON", json.dumps(_issue()))
    monkeypatch.setattr(
        classify,
        "call_model",
        lambda _cfg, _messages: '{"area": ["area/cli"], "kind": "kind/feature"}',
    )
    assert classify.main() == 0
    out = capsys.readouterr().out.strip()
    assert out.count("\n") == 0
    payload = json.loads(out)
    assert payload["action"] == "triaged"
    assert payload["area"] == ["area/cli"]


# -- sync_labels ----------------------------------------------------------


def test_sync_labels_requires_token(monkeypatch):
    from tools.triage import sync_labels

    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GH_TOKEN", raising=False)
    monkeypatch.setenv("GITHUB_REPOSITORY", "o/r")
    assert sync_labels.main() == 1


def test_sync_labels_creates_updates_and_skips(monkeypatch):
    from tools.triage import sync_labels

    keep = taxonomy.STATUS[1]  # a label that already matches: must be left alone
    existing = {
        keep.name: {"name": keep.name, "color": keep.color, "description": keep.description},
        taxonomy.STATUS[0].name: {
            "name": taxonomy.STATUS[0].name,
            "color": "000000",
            "description": "stale",
        },
    }
    calls = []
    monkeypatch.setattr(sync_labels, "_existing_labels", lambda api, repo, token: existing)
    monkeypatch.setattr(
        sync_labels, "_request", lambda url, token, method="GET", body=None: calls.append(method)
    )
    monkeypatch.setenv("GITHUB_TOKEN", "t")
    monkeypatch.setenv("GITHUB_REPOSITORY", "o/r")
    monkeypatch.delenv("GITHUB_API_URL", raising=False)
    assert sync_labels.main() == 0
    assert "POST" in calls  # everything not yet present
    assert "PATCH" in calls  # the stale one


def test_sync_labels_tolerates_http_conflict(monkeypatch):
    from tools.triage import sync_labels

    monkeypatch.setattr(sync_labels, "_existing_labels", lambda api, repo, token: {})

    def conflict(url, token, method="GET", body=None):
        raise urllib.error.HTTPError(url, 422, "exists", {}, None)

    monkeypatch.setattr(sync_labels, "_request", conflict)
    monkeypatch.setenv("GITHUB_TOKEN", "t")
    monkeypatch.setenv("GITHUB_REPOSITORY", "o/r")
    monkeypatch.delenv("GITHUB_API_URL", raising=False)
    assert sync_labels.main() == 0


def test_sync_labels_reraises_real_failure(monkeypatch):
    from tools.triage import sync_labels

    monkeypatch.setattr(sync_labels, "_existing_labels", lambda api, repo, token: {})

    def forbidden(url, token, method="GET", body=None):
        raise urllib.error.HTTPError(url, 403, "forbidden", {}, None)

    monkeypatch.setattr(sync_labels, "_request", forbidden)
    monkeypatch.setenv("GITHUB_TOKEN", "t")
    monkeypatch.setenv("GITHUB_REPOSITORY", "o/r")
    monkeypatch.delenv("GITHUB_API_URL", raising=False)
    with pytest.raises(urllib.error.HTTPError):
        sync_labels.main()


# -- workflow / taxonomy consistency --------------------------------------


def test_workflow_status_labels_match_taxonomy():
    """The workflow references status/ labels by literal; a taxonomy rename must
    not silently leave the workflow using a name that no longer exists."""
    text = (REPO_ROOT / ".github" / "workflows" / "issue-triage.yml").read_text(
        encoding="utf-8"
    )
    referenced = set(re.findall(r"status/[a-z0-9-]+", text))
    assert referenced  # sanity: we actually found some
    assert referenced <= set(taxonomy.STATUS_NAMES)


# -- TypeSafe System One / Jev --------------------------------------------


def test_load_config_detects_typesafe(monkeypatch):
    _clear_keys(monkeypatch)
    monkeypatch.setenv("TYPESAFE_API_KEY", "tk")
    cfg = classify.load_config()
    assert cfg.provider == "typesafe"
    assert cfg.model == "jev-latest"
    assert cfg.base_url == "https://api.typesafe.ai"


def test_jev_api_key_alias(monkeypatch):
    _clear_keys(monkeypatch)
    monkeypatch.setenv("JEV_API_KEY", "tk")
    assert classify.load_config().provider == "typesafe"


def test_build_systemone_questions_uses_allowlist():
    questions = classify.build_systemone_questions()
    assert questions["kind"]["type"] == "choice"
    assert set(questions["kind"]["criteria"]) == set(taxonomy.MODEL_SELECTABLE_KIND)
    assert questions["area"]["type"] == "choice"
    assert set(questions["area"]["criteria"]) == set(taxonomy.MODEL_SELECTABLE_AREA)
    assert set(questions["area_secondary"]["criteria"]) == set(
        taxonomy.MODEL_SELECTABLE_AREA
    ) | {"none"}
    assert questions["good_first_issue"]["type"] == "noul"
    assert taxonomy.GFI_DEFINITION in questions["good_first_issue"]["instructions"]


def test_typesafe_decision_maps_answers():
    response = {
        "model": "jev-1.13.0",
        "answers": {
            "kind": {"type": "choice", "choice": "kind/bug", "confidence": 0.9},
            "area": {"type": "choice", "choice": "area/extract", "confidence": 0.8},
            "area_secondary": {"type": "choice", "choice": "area/build", "confidence": 0.7},
            "good_first_issue": {"type": "noul", "noul": 0.2},
        },
        "usage": {"input_tokens": 300, "output_tokens": 20},
    }
    out = classify.typesafe_decision(response)
    assert out["area"] == ["area/extract", "area/build"]
    assert out["kind"] == "kind/bug"
    assert out["good_first_issue"] is False
    assert out["confidence"] == "high"  # min(0.9, 0.8)


def test_typesafe_decision_defaults_and_none_secondary():
    response = {
        "answers": {
            "kind": {"choice": "kind/nonsense"},
            "area": {"choice": "area/nonsense"},
            "area_secondary": {"choice": "none"},
            "good_first_issue": {"noul": 0.9},
        }
    }
    out = classify.typesafe_decision(response)
    assert out["area"] == ["area/other"]
    assert out["kind"] == "kind/other"
    assert out["good_first_issue"] is True
    assert out["confidence"] == "low"


def test_typesafe_decision_drops_duplicate_secondary():
    response = {
        "answers": {
            "kind": {"choice": "kind/bug"},
            "area": {"choice": "area/cli"},
            "area_secondary": {"choice": "area/cli"},
            "good_first_issue": {"noul": 0.0},
        }
    }
    assert classify.typesafe_decision(response)["area"] == ["area/cli"]


@pytest.mark.parametrize("bad", [{}, {"answers": None}, {"answers": []}, "x", None])
def test_typesafe_decision_garbage_returns_none(bad):
    assert classify.typesafe_decision(bad) is None


def test_classify_with_config_dispatches_typesafe(monkeypatch):
    captured = {}

    def fake(config, issue):
        captured["provider"] = config.provider
        return {
            "answers": {
                "kind": {"choice": "kind/feature"},
                "area": {"choice": "area/cli"},
                "area_secondary": {"choice": "none"},
                "good_first_issue": {"noul": 0.0},
            }
        }

    monkeypatch.setattr(classify, "call_typesafe", fake)
    cfg = classify.Config(
        base_url="https://api.typesafe.ai",
        model="jev-latest",
        api_key="k",
        timeout=30,
        max_tokens=0,
        provider="typesafe",
    )
    out = classify.classify_with_config(_issue(), cfg)
    assert captured["provider"] == "typesafe"
    assert out["kind"] == "kind/feature"
    assert out["area"] == ["area/cli"]


def test_classify_with_config_typesafe_fails_open(monkeypatch):
    def boom(config, issue):
        raise RuntimeError("529 overloaded")

    monkeypatch.setattr(classify, "call_typesafe", boom)
    cfg = classify.Config(
        base_url="https://api.typesafe.ai",
        model="jev-latest",
        api_key="k",
        timeout=30,
        max_tokens=0,
        provider="typesafe",
    )
    assert classify.classify_with_config(_issue(), cfg) is None


def test_call_typesafe_posts_expected_request(monkeypatch):
    captured = {}

    def fake_urlopen(request, timeout=None):
        captured["url"] = request.full_url
        captured["auth"] = request.get_header("Authorization")
        captured["body"] = json.loads(request.data.decode("utf-8"))
        return _FakeResponse({"answers": {"kind": {"choice": "kind/bug"}}})

    monkeypatch.setattr(classify.urllib.request, "urlopen", fake_urlopen)
    cfg = classify.Config(
        base_url="https://api.typesafe.ai",
        model="jev-latest",
        api_key="k",
        timeout=30,
        max_tokens=0,
        provider="typesafe",
    )
    classify.call_typesafe(cfg, _issue(title="Crash on parse"))
    assert captured["url"] == "https://api.typesafe.ai/v1/systemone"
    assert captured["auth"] == "Bearer k"
    assert captured["body"]["model"] == "jev-latest"
    assert captured["body"]["state"]["issue"]["title"] == "Crash on parse"
    assert captured["body"]["questions"]["kind"]["type"] == "choice"

