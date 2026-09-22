from __future__ import annotations

import json

import pytest

from graphify import missing_impact as mi


def _graph():
    return {
        "nodes": [
            {"id": "a", "label": "a.py", "source_file": "pkg/a.py", "community": 1},
            {"id": "b", "label": "b.py", "source_file": "pkg/b.py", "community": 1},
            {"id": "c", "label": "c.py", "source_file": "pkg/c.py", "community": 2},
            {"id": "test", "label": "test_a.py", "source_file": "tests/test_a.py", "community": 1},
            {"id": "same", "label": "helper()", "source_file": "pkg/a.py", "community": 1},
        ],
        "links": [
            {"source": "a", "target": "b", "relation": "calls"},
            {"source": "b", "target": "c", "relation": "imports"},
            {"source": "same", "target": "a", "relation": "references"},
        ],
    }


def test_projection_is_deterministic_and_excludes_within_file_edges():
    first, second = mi.project_graph(_graph()), mi.project_graph(_graph())
    assert first == second
    assert {(r["source"], r["target"]) for r in first["relations"]} == {("pkg/a.py", "pkg/b.py"), ("pkg/b.py", "pkg/c.py")}


def test_candidates_cover_direct_two_hop_parent_and_community_and_exclude_seed():
    projection = mi.project_graph(_graph())
    rows = mi.candidates(projection, ["pkg/a.py"])
    by_path = {row["path"]: row for row in rows}
    assert "pkg/a.py" not in by_path
    assert by_path["pkg/b.py"]["distance"] == 1
    assert by_path["pkg/c.py"]["distance"] == 2
    assert by_path["tests/test_a.py"]["community_overlap"] == ["1"]
    assert [row["structural_rank"] for row in rows] == list(range(1, len(rows) + 1))


def test_payload_is_candidate_bound_and_has_no_structural_scores_or_source():
    projection = mi.project_graph(_graph())
    payload = mi.jev_payload("fix thing", projection, ["pkg/a.py"], mi.candidates(projection, ["pkg/a.py"]))
    encoded = json.dumps(payload, sort_keys=True)
    assert payload["model"] == "jev-latest"
    assert "baseline_score" not in encoded
    assert "raw source" not in encoded
    assert set(payload["questions"]) == {mi._question_id(row["path"]) for row in mi.candidates(projection, ["pkg/a.py"])}
    assert all(question["candidate_path"] in question["instructions"] for question in payload["questions"].values())


def test_git_discovery_includes_staged_unstaged_untracked_but_not_ignored(tmp_path):
    import subprocess
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    (tmp_path / ".gitignore").write_text("ignored.py\n")
    (tmp_path / "staged.py").write_text("x")
    subprocess.run(["git", "-C", str(tmp_path), "add", ".gitignore", "staged.py"], check=True)
    (tmp_path / "unstaged.py").write_text("x")
    (tmp_path / "untracked.py").write_text("x")
    (tmp_path / "ignored.py").write_text("x")
    active, deleted = mi.discover_git_changes(tmp_path)
    assert {"staged.py", "unstaged.py", "untracked.py"} <= set(active)
    assert "ignored.py" not in active
    assert deleted == []


def test_run_offline_is_deterministic_and_never_calls_jev(tmp_path, monkeypatch, capsys):
    root, out = tmp_path / "repo", tmp_path / "repo" / "graphify-out"
    out.mkdir(parents=True); (out / "graph.json").write_text(json.dumps(_graph()))
    monkeypatch.setattr(mi, "call_typesafe", lambda *_: pytest.fail("network called"))
    mi.run(["--task", "fix", "--repo", str(root), "--changed", "pkg/a.py", "--json", "--top", "2"])
    value = json.loads(capsys.readouterr().out)
    assert value["live"] is False
    assert len(value["candidates"]) == 2
    assert all(row["jev_noul"] is None and row["semantic_rank"] is None for row in value["candidates"])


def test_live_uses_one_request_and_sorts_semantics(tmp_path, monkeypatch, capsys):
    root, out = tmp_path / "repo", tmp_path / "repo" / "graphify-out"
    out.mkdir(parents=True); (out / "graph.json").write_text(json.dumps(_graph()))
    calls = []
    def fake(payload, _key):
        calls.append(payload)
        answers = {key: {"type": "noul", "noul": .5 if value["candidate_path"] == "pkg/b.py" else .9} for key, value in payload["questions"].items()}
        return {"model": "jev-test", "usage": {"input_tokens": 1}, "answers": answers}
    monkeypatch.setenv("TYPESAFE_API_KEY", "test-key")
    monkeypatch.setattr(mi, "call_typesafe", fake)
    mi.run(["--task", "fix", "--repo", str(root), "--changed", "pkg/a.py", "--live", "--json"])
    value = json.loads(capsys.readouterr().out)
    assert len(calls) == 1
    assert value["candidates"][0]["jev_noul"] == .9
    assert all(row["provenance"] == "JEV_INFERRED" for row in value["candidates"])


def test_no_represented_seeds_makes_no_live_call(tmp_path, monkeypatch, capsys):
    root, out = tmp_path / "repo", tmp_path / "repo" / "graphify-out"
    out.mkdir(parents=True); (out / "graph.json").write_text(json.dumps(_graph()))
    monkeypatch.setattr(mi, "call_typesafe", lambda *_: pytest.fail("network called"))
    mi.run(["--task", "fix", "--repo", str(root), "--changed", "docs/nope.md", "--live", "--json"])
    assert json.loads(capsys.readouterr().out)["status"] == "NO_GRAPH_REPRESENTED_SEEDS"
