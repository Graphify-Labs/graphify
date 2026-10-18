from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from graphify.verify import Violation, format_json, format_report, load_rules, verify_graph

PYTHON = sys.executable


def _run(args: list[str], cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [PYTHON, "-m", "graphify"] + args,
        cwd=cwd,
        capture_output=True,
        text=True,
    )


def _graph_fixture() -> dict:
    return {
        "nodes": [
            {"id": "a", "label": "A", "source_file": "graphify/extractors/go.py"},
            {"id": "b", "label": "B", "source_file": "graphify/cli.py"},
            {"id": "c", "label": "C", "source_file": "graphify/build.py"},
        ],
        "links": [
            {
                "source": "a",
                "target": "b",
                "relation": "imports",
                "source_location": "L10",
            },
            {
                "source": "a",
                "target": "c",
                "relation": "calls",
                "source_location": "L20",
            },
        ],
    }


def test_load_rules_from_wrapped_object(tmp_path: Path) -> None:
    rules_path = tmp_path / "rules.json"
    rules_path.write_text(
        json.dumps({"rules": [{"name": "no cli from extractors", "from": "graphify/extractors/*", "to": "graphify/cli.py"}]}),
        encoding="utf-8",
    )
    rules = load_rules(rules_path)
    assert rules == [
        {"name": "no cli from extractors", "from": "graphify/extractors/*", "to": "graphify/cli.py"}
    ]


def test_load_rules_from_bare_list(tmp_path: Path) -> None:
    rules_path = tmp_path / "rules.json"
    rules_path.write_text(
        json.dumps([{"from": "a/*", "to": "b/*"}]),
        encoding="utf-8",
    )
    rules = load_rules(rules_path)
    assert rules == [{"name": "a/* -> b/*", "from": "a/*", "to": "b/*"}]


def test_load_rules_rejects_missing_keys(tmp_path: Path) -> None:
    rules_path = tmp_path / "rules.json"
    rules_path.write_text(json.dumps({"rules": [{"from": "a/*"}]}), encoding="utf-8")
    with pytest.raises(ValueError):
        load_rules(rules_path)


def test_load_rules_rejects_missing_rules_key(tmp_path: Path) -> None:
    rules_path = tmp_path / "rules.json"
    rules_path.write_text(json.dumps({"other": []}), encoding="utf-8")
    with pytest.raises(ValueError):
        load_rules(rules_path)


def test_load_rules_rejects_non_list_rules_value(tmp_path: Path) -> None:
    rules_path = tmp_path / "rules.json"
    rules_path.write_text(json.dumps({"rules": "not-a-list"}), encoding="utf-8")
    with pytest.raises(ValueError):
        load_rules(rules_path)


def test_load_rules_rejects_non_dict_entry(tmp_path: Path) -> None:
    rules_path = tmp_path / "rules.json"
    rules_path.write_text(json.dumps({"rules": ["a/* -> b/*"]}), encoding="utf-8")
    with pytest.raises(ValueError):
        load_rules(rules_path)


def test_load_rules_rejects_non_string_patterns(tmp_path: Path) -> None:
    rules_path = tmp_path / "rules.json"
    for bad in ({"from": None, "to": "b/*"}, {"from": "a/*", "to": 5}, {"from": ["a/*"], "to": "b/*"}):
        rules_path.write_text(json.dumps({"rules": [bad]}), encoding="utf-8")
        with pytest.raises(ValueError):
            load_rules(rules_path)


def test_verify_graph_null_source_file_is_not_a_violation(tmp_path: Path) -> None:
    graph = {
        "nodes": [
            {"id": "a", "source_file": None},
            {"id": "b", "source_file": None},
            {"id": None, "source_file": "x.py"},
        ],
        "links": [
            {"source": "a", "target": "b", "relation": None},
            {"source": None, "target": "b"},
        ],
    }
    graph_path = tmp_path / "graph.json"
    graph_path.write_text(json.dumps(graph), encoding="utf-8")
    assert verify_graph(graph_path, [{"name": "r", "from": "*", "to": "*"}]) == []
    assert verify_graph(graph_path, [{"name": "r", "from": "None", "to": "None"}]) == []


def test_load_rules_rejects_malformed_json(tmp_path: Path) -> None:
    rules_path = tmp_path / "rules.json"
    rules_path.write_text("{not valid json", encoding="utf-8")
    with pytest.raises(json.JSONDecodeError):
        load_rules(rules_path)


def test_load_rules_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_rules(tmp_path / "does-not-exist.json")


def test_load_rules_empty_list_is_valid(tmp_path: Path) -> None:
    rules_path = tmp_path / "rules.json"
    rules_path.write_text(json.dumps({"rules": []}), encoding="utf-8")
    assert load_rules(rules_path) == []


def test_verify_graph_flags_forbidden_edge_only(tmp_path: Path) -> None:
    graph_path = tmp_path / "graph.json"
    graph_path.write_text(json.dumps(_graph_fixture()), encoding="utf-8")

    rules = [{"name": "no cli from extractors", "from": "graphify/extractors/*", "to": "graphify/cli.py"}]
    violations = verify_graph(graph_path, rules)

    assert len(violations) == 1
    v = violations[0]
    assert isinstance(v, Violation)
    assert v.rule == "no cli from extractors"
    assert v.source == "a"
    assert v.target == "b"
    assert v.source_file == "graphify/extractors/go.py"
    assert v.target_file == "graphify/cli.py"
    assert v.source_location == "L10"


def test_verify_graph_clean_when_no_rule_matches(tmp_path: Path) -> None:
    graph_path = tmp_path / "graph.json"
    graph_path.write_text(json.dumps(_graph_fixture()), encoding="utf-8")

    rules = [{"name": "no db from extractors", "from": "graphify/extractors/*", "to": "graphify/db/*"}]
    violations = verify_graph(graph_path, rules)

    assert violations == []
    assert format_report(violations) == "Verify: OK - no forbidden dependencies found."


def test_verify_graph_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        verify_graph(tmp_path / "missing-graph.json", [{"name": "r", "from": "*", "to": "*"}])


def test_verify_graph_malformed_json_raises(tmp_path: Path) -> None:
    graph_path = tmp_path / "graph.json"
    graph_path.write_text("{not valid json", encoding="utf-8")
    with pytest.raises(json.JSONDecodeError):
        verify_graph(graph_path, [{"name": "r", "from": "*", "to": "*"}])


def test_verify_graph_no_rules_means_no_violations(tmp_path: Path) -> None:
    graph_path = tmp_path / "graph.json"
    graph_path.write_text(json.dumps(_graph_fixture()), encoding="utf-8")
    assert verify_graph(graph_path, []) == []


def test_verify_graph_empty_graph_is_clean(tmp_path: Path) -> None:
    graph_path = tmp_path / "graph.json"
    graph_path.write_text(json.dumps({"nodes": [], "links": []}), encoding="utf-8")
    rules = [{"name": "r", "from": "*", "to": "*"}]
    assert verify_graph(graph_path, rules) == []


def test_verify_graph_accepts_edges_key_instead_of_links(tmp_path: Path) -> None:
    graph = _graph_fixture()
    graph["edges"] = graph.pop("links")
    graph_path = tmp_path / "graph.json"
    graph_path.write_text(json.dumps(graph), encoding="utf-8")

    rules = [{"name": "no cli from extractors", "from": "graphify/extractors/*", "to": "graphify/cli.py"}]
    violations = verify_graph(graph_path, rules)
    assert len(violations) == 1


def test_verify_graph_skips_dangling_edges(tmp_path: Path) -> None:
    graph = {
        "nodes": [{"id": "a", "source_file": "graphify/extractors/go.py"}],
        "links": [
            {"source": "a", "target": "does-not-exist", "relation": "calls"},
            {"source": "does-not-exist", "target": "a", "relation": "calls"},
        ],
    }
    graph_path = tmp_path / "graph.json"
    graph_path.write_text(json.dumps(graph), encoding="utf-8")
    rules = [{"name": "r", "from": "*", "to": "*"}]
    assert verify_graph(graph_path, rules) == []


def test_verify_graph_skips_nodes_without_source_file(tmp_path: Path) -> None:
    graph = {
        "nodes": [
            {"id": "a"},  # no source_file at all
            {"id": "b", "source_file": ""},  # empty source_file
        ],
        "links": [{"source": "a", "target": "b", "relation": "calls"}],
    }
    graph_path = tmp_path / "graph.json"
    graph_path.write_text(json.dumps(graph), encoding="utf-8")
    rules = [{"name": "r", "from": "*", "to": "*"}]
    assert verify_graph(graph_path, rules) == []


def test_verify_graph_ignores_non_dict_edges_and_nodes(tmp_path: Path) -> None:
    graph = {
        "nodes": [
            {"id": "a", "source_file": "graphify/extractors/go.py"},
            "not-a-node",
            None,
        ],
        "links": [
            "not-an-edge",
            None,
            {"source": "a", "target": "a", "relation": "self"},
        ],
    }
    graph_path = tmp_path / "graph.json"
    graph_path.write_text(json.dumps(graph), encoding="utf-8")
    rules = [{"name": "self loop", "from": "graphify/extractors/*", "to": "graphify/extractors/*"}]
    violations = verify_graph(graph_path, rules)
    assert len(violations) == 1
    assert violations[0].source == violations[0].target == "a"


def test_verify_graph_matches_subdirectories_with_star_glob(tmp_path: Path) -> None:
    """fnmatch's '*' matches '/' too, so 'extractors/*' also matches nested paths
    like 'extractors/sub/go.py' - this is intentional (whole-subtree matching)."""
    graph = {
        "nodes": [
            {"id": "a", "source_file": "graphify/extractors/sub/go.py"},
            {"id": "b", "source_file": "graphify/cli.py"},
        ],
        "links": [{"source": "a", "target": "b", "relation": "imports"}],
    }
    graph_path = tmp_path / "graph.json"
    graph_path.write_text(json.dumps(graph), encoding="utf-8")
    rules = [{"name": "r", "from": "graphify/extractors/*", "to": "graphify/cli.py"}]
    assert len(verify_graph(graph_path, rules)) == 1


def test_verify_graph_multiple_rules_on_same_edge_each_report(tmp_path: Path) -> None:
    graph_path = tmp_path / "graph.json"
    graph_path.write_text(json.dumps(_graph_fixture()), encoding="utf-8")
    rules = [
        {"name": "rule one", "from": "graphify/extractors/*", "to": "graphify/cli.py"},
        {"name": "rule two", "from": "graphify/*", "to": "graphify/cli.py"},
    ]
    violations = verify_graph(graph_path, rules)
    assert {v.rule for v in violations} == {"rule one", "rule two"}


def test_format_report_lists_violations() -> None:
    violations = [
        Violation(
            rule="no cli from extractors",
            source="a",
            target="b",
            source_file="graphify/extractors/go.py",
            target_file="graphify/cli.py",
            relation="imports",
            source_location="L10",
        )
    ]
    report = format_report(violations)
    assert "1 violation(s) found" in report
    assert "no cli from extractors" in report
    assert "graphify/extractors/go.py" in report


def test_cli_verify_requires_rules_flag(tmp_path: Path) -> None:
    result = _run(["verify"], cwd=tmp_path)
    assert result.returncode == 1
    assert "Usage: graphify verify" in result.stderr


def test_cli_verify_dangling_rules_flag(tmp_path: Path) -> None:
    result = _run(["verify", "--rules"], cwd=tmp_path)
    assert result.returncode == 1
    assert "--rules requires a path" in result.stderr


def test_cli_verify_dangling_graph_flag(tmp_path: Path) -> None:
    result = _run(["verify", "--rules", "r.json", "--graph"], cwd=tmp_path)
    assert result.returncode == 1
    assert "--graph requires a path" in result.stderr


def test_cli_verify_no_args_shows_usage(tmp_path: Path) -> None:
    result = _run(["verify"], cwd=tmp_path)
    assert result.returncode == 1
    assert "Usage: graphify verify" in result.stderr


def test_cli_verify_unknown_option(tmp_path: Path) -> None:
    result = _run(["verify", "--rules", "rules.json", "--bogus"], cwd=tmp_path)
    assert result.returncode == 1
    assert "unknown verify option" in result.stderr


def test_cli_verify_missing_rules_file(tmp_path: Path) -> None:
    graph_path = tmp_path / "graph.json"
    graph_path.write_text(json.dumps(_graph_fixture()), encoding="utf-8")
    result = _run(["verify", "--rules", "nope.json", "--graph", str(graph_path)], cwd=tmp_path)
    assert result.returncode == 1
    assert "error:" in result.stderr


def test_cli_verify_missing_graph_file(tmp_path: Path) -> None:
    rules_path = tmp_path / "rules.json"
    rules_path.write_text(json.dumps({"rules": [{"from": "*", "to": "*"}]}), encoding="utf-8")
    result = _run(["verify", "--rules", str(rules_path), "--graph", "nope.json"], cwd=tmp_path)
    assert result.returncode == 1
    assert "error:" in result.stderr


def test_cli_verify_exits_zero_when_clean(tmp_path: Path) -> None:
    graph_path = tmp_path / "graph.json"
    graph_path.write_text(json.dumps(_graph_fixture()), encoding="utf-8")
    rules_path = tmp_path / "rules.json"
    rules_path.write_text(
        json.dumps({"rules": [{"from": "nonexistent/*", "to": "graphify/cli.py"}]}),
        encoding="utf-8",
    )
    result = _run(
        ["verify", "--rules", str(rules_path), "--graph", str(graph_path)], cwd=tmp_path
    )
    assert result.returncode == 0
    assert "OK" in result.stdout


def test_cli_verify_exits_one_on_violation(tmp_path: Path) -> None:
    graph_path = tmp_path / "graph.json"
    graph_path.write_text(json.dumps(_graph_fixture()), encoding="utf-8")
    rules_path = tmp_path / "rules.json"
    rules_path.write_text(
        json.dumps({"rules": [{"from": "graphify/extractors/*", "to": "graphify/cli.py"}]}),
        encoding="utf-8",
    )
    result = _run(
        ["verify", "--rules", str(rules_path), "--graph", str(graph_path)], cwd=tmp_path
    )
    assert result.returncode == 1
    assert "violation(s) found" in result.stdout


def test_cli_verify_json_flag_emits_valid_json(tmp_path: Path) -> None:
    graph_path = tmp_path / "graph.json"
    graph_path.write_text(json.dumps(_graph_fixture()), encoding="utf-8")
    rules_path = tmp_path / "rules.json"
    rules_path.write_text(
        json.dumps({"rules": [{"from": "graphify/extractors/*", "to": "graphify/cli.py"}]}),
        encoding="utf-8",
    )
    result = _run(
        ["verify", "--rules", str(rules_path), "--graph", str(graph_path), "--json"],
        cwd=tmp_path,
    )
    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert payload["violation_count"] == 1


def test_cli_verify_uses_default_graph_path_when_omitted(tmp_path: Path) -> None:
    out_dir = tmp_path / "graphify-out"
    out_dir.mkdir()
    (out_dir / "graph.json").write_text(json.dumps(_graph_fixture()), encoding="utf-8")
    rules_path = tmp_path / "rules.json"
    rules_path.write_text(
        json.dumps({"rules": [{"from": "graphify/extractors/*", "to": "graphify/cli.py"}]}),
        encoding="utf-8",
    )
    result = _run(["verify", "--rules", str(rules_path)], cwd=tmp_path)
    assert result.returncode == 1
    assert "violation(s) found" in result.stdout


def test_format_json_round_trips() -> None:
    violations = [
        Violation(
            rule="r",
            source="a",
            target="b",
            source_file="x.py",
            target_file="y.py",
            relation="calls",
            source_location="L1",
        )
    ]
    payload = format_json(violations)
    assert payload["ok"] is False
    assert payload["violation_count"] == 1
    assert payload["violations"][0]["rule"] == "r"

    empty_payload = format_json([])
    assert empty_payload["ok"] is True
    assert empty_payload["violation_count"] == 0
