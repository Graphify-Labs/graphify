"""Exercise caller evidence through the CLI against a real extracted graph."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

import pytest


def _graphify(cwd, *args):
    env = {
        **os.environ,
        "PYTHONPATH": str(Path(__file__).resolve().parents[1]),
        "PYTHONIOENCODING": "utf-8",
        "GRAPHIFY_OUT": "graphify-out",
        "GRAPHIFY_QUERY_LOG_DISABLE": "1",
    }
    return subprocess.run(
        [sys.executable, "-m", "graphify", *args],
        cwd=cwd, env=env, capture_output=True, text=True, encoding="utf-8", timeout=60,
    )


@pytest.fixture
def project(tmp_path):
    (tmp_path / "target.py").write_text(
        "def downstream(value):\n    return value\n\n"
        "def handle_request(value):\n    return downstream(value)\n",
        encoding="utf-8",
    )
    (tmp_path / "entry.py").write_text(
        "from target import handle_request\n\n"
        "def public_route(enabled, payload):\n"
        "    if enabled:\n"
        "        return handle_request(\n"
        "            payload,\n"
        "        )\n\n"
        "def other_route(payload):\n"
        "    return handle_request(payload)\n",
        encoding="utf-8",
    )
    result = _graphify(tmp_path, "update", ".", "--no-cluster")
    assert result.returncode == 0, result.stderr
    assert (tmp_path / "graphify-out" / "manifest.json").is_file()
    return tmp_path


def _query(project, *args):
    return _graphify(project, "query", "Who calls `handle_request`, and under what condition?", "--evidence", *args)


def test_evidence_returns_inbound_sites_with_multiline_call_and_guard(project):
    result = _query(project)
    assert result.returncode == 0, result.stderr
    assert "Direct callers of handle_request()" in result.stdout
    assert "public_route() [EXTRACTED] at entry.py:5" in result.stdout
    assert "other_route() [EXTRACTED] at entry.py:10" in result.stdout
    assert "4 |     if enabled:" in result.stdout
    assert "7 |         )" in result.stdout
    assert "downstream" not in result.stdout

    regular = _graphify(project, "query", "who calls handle_request")
    assert regular.returncode == 0, regular.stderr
    assert "EDGE public_route() --calls" in regular.stdout
    assert "if enabled:" not in regular.stdout


def test_evidence_keeps_citations_before_spending_budget_on_excerpts(project):
    result = _query(project, "--budget", "45")
    assert result.returncode == 0, result.stderr
    assert len(result.stdout) <= 45 * 3
    assert "at entry.py:5" in result.stdout
    assert "at entry.py:10" in result.stdout
    assert "Source excerpt" not in result.stdout


def test_evidence_keeps_a_fitting_citation_under_a_tight_budget(project):
    result = _query(project, "--budget", "35")
    assert result.returncode == 0, result.stderr
    assert len(result.stdout) <= 35 * 3
    assert "at entry.py:5" in result.stdout
    assert "at entry.py:10" not in result.stdout
    assert "omitted" in result.stdout


def test_evidence_skips_a_citation_that_cannot_fit(tmp_path):
    long_name = "first_" + "a" * 120
    (tmp_path / "calls.go").write_text(
        "package routes\nfunc target() {}\n"
        f"func {long_name}() {{ target() }}\n"
        "func second() { target() }\n",
        encoding="utf-8",
    )
    rebuilt = _graphify(tmp_path, "update", ".", "--no-cluster")
    assert rebuilt.returncode == 0, rebuilt.stderr

    result = _graphify(tmp_path, "query", "who calls target?", "--evidence", "--budget", "35")
    assert result.returncode == 0, result.stderr
    assert len(result.stdout) <= 105
    assert "second() [EXTRACTED] at calls.go:4" in result.stdout
    assert long_name not in result.stdout
    assert "omitted" in result.stdout


def test_evidence_keeps_source_context_when_callers_exceed_budget(project):
    tests = project / "tests"
    tests.mkdir()
    (tests / "test_routes.py").write_text(
        "from target import handle_request\n\n" + "\n".join(
            f"def test_caller_{i}():\n    return handle_request({i})\n" for i in range(40)
        ),
        encoding="utf-8",
    )
    rebuilt = _graphify(project, "update", ".", "--no-cluster")
    assert rebuilt.returncode == 0, rebuilt.stderr
    result = _query(project, "--budget", "240")
    assert result.returncode == 0, result.stderr
    assert len(result.stdout) <= 240 * 3
    assert "at entry.py:5" in result.stdout
    assert "4 |     if enabled:" in result.stdout
    assert "Additional callers omitted by the output budget." in result.stdout


@pytest.mark.parametrize("extension", ["go", "py"])
def test_evidence_spends_budget_on_citations_when_no_excerpts_are_available(tmp_path, extension):
    if extension == "go":
        source = "package routes\nfunc target() {}\n" + "".join(
            f"func route_{i:02d}() {{ target() }}\n" for i in range(40)
        )
    else:
        source = "def target(): pass\n" + "".join(
            f"def route_{i:02d}():\n    target()\n" for i in range(40)
        )
    (tmp_path / f"calls.{extension}").write_text(source, encoding="utf-8")
    rebuilt = _graphify(tmp_path, "update", ".", "--no-cluster")
    assert rebuilt.returncode == 0, rebuilt.stderr
    if extension == "py":
        (tmp_path / "graphify-out" / "manifest.json").unlink()

    result = _graphify(tmp_path, "query", "who calls target?", "--evidence", "--budget", "200")
    assert result.returncode == 0, result.stderr
    assert len(result.stdout) <= 600
    assert result.stdout.count(f" [EXTRACTED] at calls.{extension}:") >= 13
    assert "Additional callers omitted by the output budget." in result.stdout
    assert "Source excerpt" not in result.stdout


def test_evidence_keeps_distinct_callers_on_the_same_line(tmp_path):
    (tmp_path / "calls.js").write_text(
        "function target() {} function alpha() { target(); } function beta() { target(); }\n",
        encoding="utf-8",
    )
    rebuilt = _graphify(tmp_path, "update", ".", "--no-cluster")
    assert rebuilt.returncode == 0, rebuilt.stderr

    result = _graphify(tmp_path, "query", "who calls target?", "--evidence")
    assert result.returncode == 0, result.stderr
    assert "alpha() [EXTRACTED] at calls.js:1" in result.stdout
    assert "beta() [EXTRACTED] at calls.js:1" in result.stdout


@pytest.mark.parametrize("change", ["modified", "deleted", "outside symlink", "missing manifest"])
def test_evidence_falls_back_to_citation_when_source_cannot_be_verified(project, change):
    caller = project / "entry.py"
    if change == "modified":
        caller.write_text(caller.read_text(encoding="utf-8").replace("if enabled:", "if not enabled:"), encoding="utf-8")
    elif change == "deleted":
        caller.unlink()
    elif change == "outside symlink":
        outside = project.parent / "outside.py"
        outside.write_bytes(caller.read_bytes())
        caller.unlink()
        try:
            caller.symlink_to(outside)
        except OSError as exc:
            pytest.skip(f"symlinks unavailable: {exc}")
    else:
        (project / "graphify-out" / "manifest.json").unlink()

    result = _query(project)
    assert result.returncode == 0, result.stderr
    assert "at entry.py:5" in result.stdout
    assert "Excerpt unavailable. Check the source directly." in result.stdout
    assert "if enabled:" not in result.stdout
    assert "if not enabled:" not in result.stdout


def test_evidence_keeps_distinct_calls_and_ignores_unverified_graph_locations(project):
    entry = project / "entry.py"
    entry.write_text(
        entry.read_text(encoding="utf-8").replace(
            "    return handle_request(payload)\n",
            "    value = handle_request(payload)\n    return handle_request(value)\n",
        ),
        encoding="utf-8",
    )
    rebuilt = _graphify(project, "update", ".", "--no-cluster")
    assert rebuilt.returncode == 0, rebuilt.stderr
    graph = project / "graphify-out" / "graph.json"
    data = json.loads(graph.read_text(encoding="utf-8"))
    edges = data["edges"] if "edges" in data else data["links"]
    valid = next(e for e in edges if e.get("source_location") == "L10" and e.get("relation") == "calls")
    # The extractor can consolidate same-caller edges. Exercise graphs that
    # already retain multiple positions, including the legacy reversed order.
    second = dict(valid, source_location="L11", source=valid["target"], target=valid["source"])
    second.update(_src=valid["source"], _tgt=valid["target"])
    edges.append(second)
    edges.append(dict(valid, source_location="L4"))
    graph.write_text(json.dumps(data), encoding="utf-8")

    result = _query(project)
    assert result.returncode == 0, result.stderr
    assert "at entry.py:4\n  Excerpt unavailable." in result.stdout
    assert "at entry.py:10\n  Source excerpt" in result.stdout
    assert "at entry.py:11\n  Source excerpt" in result.stdout


def test_evidence_treats_unrecognized_confidence_as_unknown(project):
    graph = project / "graphify-out" / "graph.json"
    data = json.loads(graph.read_text(encoding="utf-8"))
    edges = data["edges"] if "edges" in data else data["links"]
    calls = [e for e in edges if e.get("source_location") == "L5" and e.get("relation") == "calls"]
    assert calls
    for call in calls:
        call["confidence"] = "LEGACY_A"
        edges.append(dict(call, confidence="LEGACY_B"))
    graph.write_text(json.dumps(data), encoding="utf-8")

    result = _query(project)
    assert result.returncode == 0, result.stderr
    assert result.stdout.count("public_route() [UNKNOWN] at entry.py:5") == 1
    assert "LEGACY_" not in result.stdout


def test_evidence_returns_after_refreshing_the_index(project):
    entry = project / "entry.py"
    entry.write_text(
        entry.read_text(encoding="utf-8").replace("if enabled:", "if not enabled:"),
        encoding="utf-8",
    )
    rebuilt = _graphify(project, "update", ".", "--no-cluster")
    assert rebuilt.returncode == 0, rebuilt.stderr
    result = _query(project)
    assert result.returncode == 0, result.stderr
    assert "4 |     if not enabled:" in result.stdout


def test_evidence_does_not_read_source_from_another_checkout(project, tmp_path_factory):
    other_checkout = tmp_path_factory.mktemp("other-checkout")
    result = _graphify(
        other_checkout, "query", "who calls handle_request?", "--evidence",
        "--graph", str(project / "graphify-out" / "graph.json"),
    )
    assert result.returncode == 0, result.stderr
    assert "at entry.py:5" in result.stdout
    assert "if enabled:" not in result.stdout
    assert "Source excerpt" not in result.stdout


def test_evidence_redacts_credential_shaped_content(project):
    entry = project / "entry.py"
    value = "A" * 24
    entry.write_text(
        entry.read_text(encoding="utf-8").replace(
            "return handle_request(payload)", f"return handle_request(payload)  # Bearer {value}",
        ),
        encoding="utf-8",
    )
    rebuilt = _graphify(project, "update", ".", "--no-cluster")
    assert rebuilt.returncode == 0, rebuilt.stderr
    result = _query(project)
    assert result.returncode == 0, result.stderr
    assert "Bearer [redacted]" in result.stdout
    assert value not in result.stdout


def test_evidence_respects_ambiguous_names_and_qualified_seeds(project):
    (project / "other.py").write_text("def handle_request(value):\n    return value\n", encoding="utf-8")
    rebuilt = _graphify(project, "update", ".", "--no-cluster")
    assert rebuilt.returncode == 0, rebuilt.stderr

    ambiguous = _query(project)
    assert ambiguous.returncode == 3
    assert "Ambiguous:" in ambiguous.stderr
    qualified = _query(project, "--seed", "target.py::handle_request")
    assert qualified.returncode == 0, qualified.stderr
    assert "at entry.py:5" in qualified.stdout


def test_evidence_rejects_unsupported_question(project):
    result = _graphify(project, "query", "explain this architecture", "--evidence")
    assert result.returncode == 1
    assert 'expects "who calls <symbol>?"' in result.stderr


def test_evidence_does_not_guess_a_partially_matching_symbol(project):
    result = _graphify(project, "query", "who calls handle_reques?", "--evidence")
    assert result.returncode == 4
    assert "No unique node match" in result.stderr
