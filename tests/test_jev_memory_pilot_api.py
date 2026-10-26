"""The Jev boundary is fully mocked: these tests never make a paid request."""

import json
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from tools.jev_memory_pilot_api import call_jev, decide_once, make_request, parse_answers


@pytest.fixture
def source_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "source"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    (repo / "handler.py").write_text("def handle_request(): return 1\n")
    subprocess.run(["git", "add", "handler.py"], cwd=repo, check=True)
    subprocess.run(
        ["git", "-c", "user.name=Test", "-c", "user.email=test@example.invalid",
         "commit", "-qm", "source"], cwd=repo, check=True,
    )
    return repo


def test_make_request_uses_committed_excerpt_and_allowlisted_observation(source_repo):
    candidates = [{"node_id": "handler.py::handle_request", "label": "handle_request",
                   "type": "function", "source_file": "handler.py", "source_location": "L1"},
                  {"node_id": "bad", "label": "bad", "type": "function",
                   "source_file": "../secret.py", "source_location": "L1"}]
    observations = [{"id": "o1", "summary": "Redacted synthetic observation.",
                     "private_extra": "canary-must-not-leak", "source_ref": "synthetic-o1"}]
    (source_repo / "handler.py").write_text("PRIVATE_WORKTREE_TEXT\n")
    payload, pair_map = make_request(source_repo, "Where is the handler?", candidates, observations)
    encoded = json.dumps(payload)
    assert pair_map == {"p000": ("handler.py::handle_request", "o1")}
    assert payload["state"]["nodes"][0]["excerpt"] == "def handle_request(): return 1"
    assert "PRIVATE_WORKTREE_TEXT" not in encoded
    assert "canary-must-not-leak" not in encoded
    assert "../secret.py" not in encoded
    assert len(payload["questions"]) == 1
    with pytest.raises(ValueError, match="duplicate"):
        make_request(source_repo, "Where?", candidates[:1] * 2, observations)
    with pytest.raises(ValueError, match="invalid"):
        make_request(source_repo, "Where?", candidates[:1], [{"id": "o1", "summary": None}])


def test_call_jev_makes_one_request_and_never_retries():
    payload = {"model": "typesafe/jev-1.14", "state": {}, "questions": {"p000": {"type": "choice"}}}
    with patch("urllib.request.urlopen", side_effect=TimeoutError) as post:
        with pytest.raises(TimeoutError):
            call_jev(payload, "test-key")
    assert post.call_count == 1
    with patch("urllib.request.urlopen") as post:
        with pytest.raises(ValueError, match="24 KiB"):
            call_jev({**payload, "state": {"large": "x" * 25_000}}, "test-key")
    post.assert_not_called()


def test_parse_answers_requires_exact_complete_typed_response():
    pair_map = {"p000": ("node", "obs")}
    valid = {"answers": {"p000": {"type": "choice", "choice": "relevant",
                                  "probabilities": {"relevant": 0.9, "unrelated": 0.08,
                                                    "insufficient_evidence": 0.02}}},
             "usage": {"cost": 0.00001}, "model": "typesafe/jev-1.14-20261001"}
    assert parse_answers(valid, pair_map) == {("node", "obs"): {
        "choice": "relevant", "probability": 0.9,
    }}
    variants = [
        {**valid, "answers": {}},
        {**valid, "answers": {**valid["answers"], "extra": valid["answers"]["p000"]}},
        {**valid, "usage": {}},
        {**valid, "answers": {"p000": {**valid["answers"]["p000"], "type": "score"}}},
        {**valid, "answers": {"p000": {**valid["answers"]["p000"],
                                       "probabilities": {"relevant": 1.2, "unrelated": 0,
                                                         "insufficient_evidence": 0}}}},
    ]
    for response in variants:
        with pytest.raises(ValueError):
            parse_answers(response, pair_map)


def test_optional_call_is_off_by_default_and_fails_closed():
    payload = {"model": "typesafe/jev-1.14", "state": {}, "questions": {"p000": {}}}
    pair_map = {"p000": ("node", "obs")}
    with patch("tools.jev_memory_pilot_api.call_jev") as post:
        assert decide_once(payload, pair_map, live=False) == ({}, None, None)
        assert decide_once(payload, {}, live=True, approved=True, max_requests=1,
                           api_key="test-key") == ({}, None, None)
        post.assert_not_called()
        with pytest.raises(ValueError, match="approval flag"):
            decide_once(payload, pair_map, live=True, api_key="test-key")
        post.side_effect = TimeoutError
        assert decide_once(payload, pair_map, live=True, approved=True, max_requests=1,
                           api_key="test-key") == ({}, None, None)
        assert post.call_count == 1
