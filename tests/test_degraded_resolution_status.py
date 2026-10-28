from __future__ import annotations

import json
from pathlib import Path

import networkx as nx

from graphify.build import build, build_from_json, build_merge, merge_raw_extraction
from graphify.diagnostics import diagnose_extraction, format_diagnostic_json, format_diagnostic_report
from graphify.export import to_json
from graphify.extract import extract
from graphify.report import generate
from graphify.resolver_registry import LanguageResolver, run_language_resolvers


FAILURE = {
    "resolver": "python_member_calls",
    "suffixes": [".py"],
    "error": "RuntimeError: resolver blew up",
}


def _node(nid: str, source_file: str) -> dict:
    return {
        "id": nid,
        "label": Path(source_file).name,
        "file_type": "code",
        "source_file": source_file,
        "source_location": "L1",
        "_origin": "ast",
    }


def _graph_payload(*, degraded=None) -> dict:
    payload = {
        "directed": False,
        "nodes": [_node("a", "a.py")],
        "links": [],
        "graph": {},
    }
    if degraded is not None:
        payload["graph"]["degraded_passes"] = degraded
        payload["degraded_passes"] = degraded
    return payload


def test_registry_records_failure_and_success_without_stopping_later_passes() -> None:
    statuses: list[dict] = []
    ran: list[str] = []

    def boom(*_args):
        raise RuntimeError("token=AKIAIOSFODNN7EXAMPLE resolver blew up")

    def after(*_args):
        ran.append("after")

    resolvers = [
        LanguageResolver("boom", frozenset({".py"}), boom),
        LanguageResolver("after", frozenset({".py"}), after),
    ]
    run_language_resolvers(
        [Path("a.py")], [], [], [], resolvers=resolvers, status=statuses
    )

    assert ran == ["after"]
    assert statuses[0]["resolver"] == "boom"
    assert statuses[0]["status"] == "failed"
    assert statuses[0]["suffixes"] == [".py"]
    assert "AKIAIOSFODNN7EXAMPLE" not in statuses[0]["error"]
    assert "[redacted]" in statuses[0]["error"]
    assert statuses[1] == {
        "resolver": "after",
        "status": "ok",
        "suffixes": [".py"],
    }


def test_build_from_json_carries_degraded_passes_into_graph_metadata() -> None:
    G = build_from_json({
        "nodes": [_node("a", "a.py")],
        "edges": [],
        "degraded_passes": [FAILURE],
    })
    assert G.graph["degraded_passes"] == [FAILURE]


def test_build_combines_and_deduplicates_degraded_passes() -> None:
    G = build([
        {"nodes": [_node("a", "a.py")], "edges": [], "degraded_passes": [FAILURE]},
        {"nodes": [_node("b", "b.py")], "edges": [], "degraded_passes": [FAILURE]},
    ], dedup=False)
    assert G.graph["degraded_passes"] == [FAILURE]


def test_to_json_persists_degraded_passes_in_top_level_and_graph_metadata(tmp_path: Path) -> None:
    G = nx.Graph()
    G.add_node("a", label="a.py", file_type="code", source_file="a.py")
    G.graph["degraded_passes"] = [FAILURE]
    out = tmp_path / "graph.json"

    assert to_json(G, {}, str(out), force=True)
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["degraded_passes"] == [FAILURE]
    assert data["graph"]["degraded_passes"] == [FAILURE]


def test_diagnose_surfaces_degraded_passes_from_graph_metadata() -> None:
    summary = diagnose_extraction(_graph_payload(degraded=[FAILURE]))
    report = format_diagnostic_report(summary)
    payload = format_diagnostic_json(summary)

    assert summary["degraded_pass_count"] == 1
    assert summary["degraded_passes"] == [FAILURE]
    assert "degraded_resolution_passes: 1" in report
    assert "python_member_calls" in report
    assert payload["degraded_passes"] == [FAILURE]


def test_graph_report_warns_when_resolution_passes_failed() -> None:
    G = nx.Graph()
    G.add_node("a", label="a()", file_type="code", source_file="a.py")
    G.graph["degraded_passes"] = [FAILURE]
    report = generate(
        G,
        {0: ["a"]},
        {0: 1.0},
        {0: "Core"},
        [],
        [],
        {"total_files": 1, "total_words": 10},
        {"input": 0, "output": 0},
        ".",
        min_community_size=1,
    )

    assert "## Graph Health" in report
    assert "1 resolution pass failed" in report
    assert "python_member_calls" in report
    assert ".py" in report


def test_build_merge_preserves_unrelated_failure_and_successful_rerun_clears_it(tmp_path: Path) -> None:
    graph_path = tmp_path / "graph.json"
    graph_path.write_text(json.dumps(_graph_payload(degraded=[FAILURE])), encoding="utf-8")

    unrelated = {
        "nodes": [_node("b", "b.js")],
        "edges": [],
        "extracted_sources": [str(tmp_path / "b.js")],
        "_successful_resolution_passes": ["typescript_member_calls"],
    }
    (tmp_path / "b.js").write_text("export function b() {}\n", encoding="utf-8")
    G = build_merge([unrelated], graph_path, root=tmp_path, dedup=False)
    assert G.graph["degraded_passes"] == [FAILURE]

    recovered = {
        "nodes": [],
        "edges": [],
        "_successful_resolution_passes": ["python_member_calls"],
    }
    G2 = build_merge([recovered], graph_path, root=tmp_path, dedup=False)
    assert "degraded_passes" not in G2.graph


def test_merge_raw_extraction_preserves_and_clears_degraded_status(tmp_path: Path) -> None:
    graph_path = tmp_path / "graph.json"
    graph_path.write_text(json.dumps(_graph_payload(degraded=[FAILURE])), encoding="utf-8")

    unrelated = {
        "nodes": [],
        "edges": [],
        "_successful_resolution_passes": ["typescript_member_calls"],
    }
    merged = merge_raw_extraction(unrelated, graph_path, root=tmp_path)
    assert merged["degraded_passes"] == [FAILURE]

    recovered = {
        "nodes": [],
        "edges": [],
        "_successful_resolution_passes": ["python_member_calls"],
    }
    merged2 = merge_raw_extraction(recovered, graph_path, root=tmp_path)
    assert "degraded_passes" not in merged2



def test_extract_records_handwired_resolver_failure(monkeypatch, tmp_path: Path) -> None:
    source = tmp_path / "app.py"
    source.write_text("def app():\n    return 1\n", encoding="utf-8")

    def boom(*_args, **_kwargs):
        raise RuntimeError("cross-file import resolver failed")

    monkeypatch.setattr("graphify.extract._resolve_cross_file_imports", boom)
    result = extract(
        [source],
        root=tmp_path,
        cache_root=tmp_path,
        parallel=False,
    )

    failures = {item["resolver"]: item for item in result["degraded_passes"]}
    assert failures["python_cross_file_imports"]["suffixes"] == [".py"]
    assert failures["python_cross_file_imports"]["error"].startswith("RuntimeError:")
    assert "python_cross_file_imports" not in result["_successful_resolution_passes"]



def test_extract_does_not_clear_c_include_failure_on_non_c_scan(tmp_path: Path) -> None:
    source = tmp_path / "app.py"
    source.write_text("def app():\n    return 1\n", encoding="utf-8")
    result = extract(
        [source],
        root=tmp_path,
        cache_root=tmp_path,
        parallel=False,
    )

    assert "c_include_resolution" not in result.get(
        "_successful_resolution_passes", []
    )
