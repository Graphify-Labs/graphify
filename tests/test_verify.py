from __future__ import annotations

import json
from pathlib import Path

import pytest

from graphify.verify import Violation, format_json, format_report, load_rules, verify_graph


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
