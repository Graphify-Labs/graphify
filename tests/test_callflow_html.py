import json
import subprocess
import sys
from pathlib import Path

from graphify.callflow_html import derive_sections_from_communities, write_callflow_html


def _make_graphify_out(tmp_path: Path) -> Path:
    out = tmp_path / "graphify-out"
    out.mkdir()
    graph = {
        "directed": False,
        "multigraph": False,
        "graph": {},
        "nodes": [
            {"id": "api", "label": "ApiClient", "source_file": "src/api.py", "file_type": "code", "community": 0},
            {"id": "run", "label": "run()", "source_file": "src/main.py", "file_type": "code", "community": 0},
            {"id": "export", "label": "write_html()", "source_file": "src/export.py", "file_type": "code", "community": 1},
            {"id": "evil", "label": "<script>alert(1)</script>", "source_file": "src/evil.py", "file_type": "code", "community": 1},
        ],
        "links": [
            {"source": "run", "target": "api", "relation": "calls", "confidence": "EXTRACTED", "confidence_score": 1.0},
            {"source": "api", "target": "export", "relation": "uses", "confidence": "EXTRACTED", "confidence_score": 1.0},
            {"source": "export", "target": "evil", "relation": "calls", "confidence": "EXTRACTED", "confidence_score": 1.0},
        ],
        "hyperedges": [],
        "built_at_commit": "abcdef123456",
    }
    (out / "graph.json").write_text(json.dumps(graph), encoding="utf-8")
    (out / ".graphify_labels.json").write_text(
        json.dumps({"0": "Runtime", "1": "Export"}),
        encoding="utf-8",
    )
    (out / "GRAPH_REPORT.md").write_text(
        "\n".join(
            [
                "# Graph Report - sample",
                "",
                "## Summary",
                "- 3 nodes · 2 edges · 1 communities detected",
                "",
                "## God Nodes (most connected - your core abstractions)",
                "1. `Transformer` - 2 edges",
            ]
        ),
        encoding="utf-8",
    )
    return out


def test_write_callflow_html_creates_file_and_uses_report(tmp_path):
    out = _make_graphify_out(tmp_path)

    html_path = write_callflow_html(
        tmp_path,
        output="graphify-out/callflow.html",
        max_sections=4,
    )

    assert html_path == out / "callflow.html"
    content = html_path.read_text(encoding="utf-8")
    assert "mermaid" in content
    assert "Graph Report Highlights" in content
    assert "Transformer" in content
    assert "ApiClient" in content
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in content
    assert "<script>alert(1)</script>" not in content


def test_export_callflow_html_cli_creates_file(tmp_path):
    _make_graphify_out(tmp_path)

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "graphify",
            "export",
            "callflow-html",
            "--output",
            "graphify-out/from-cli.html",
            "--max-sections",
            "4",
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    html_path = tmp_path / "graphify-out" / "from-cli.html"
    assert html_path.exists()
    assert "callflow HTML written" in result.stdout


def test_export_callflow_html_cli_accepts_positional_graph_path(tmp_path):
    _make_graphify_out(tmp_path)
    external_out = tmp_path / "GitNexus" / "graphify-out"
    external_out.mkdir(parents=True)
    graph = {
        "directed": False,
        "multigraph": False,
        "graph": {},
        "nodes": [
            {"id": "external", "label": "ExternalOnly", "source_file": "src/external.py", "file_type": "code", "community": 0},
            {"id": "writer", "label": "write_external()", "source_file": "src/writer.py", "file_type": "code", "community": 1},
        ],
        "links": [
            {"source": "external", "target": "writer", "relation": "calls", "confidence": "EXTRACTED", "confidence_score": 1.0},
        ],
        "hyperedges": [],
    }
    (external_out / "graph.json").write_text(json.dumps(graph), encoding="utf-8")
    (external_out / ".graphify_labels.json").write_text(json.dumps({"0": "External Runtime", "1": "External Export"}), encoding="utf-8")
    (external_out / "GRAPH_REPORT.md").write_text(
        "\n".join(
            [
                "# Graph Report - external",
                "",
                "## Summary",
                "- 2 nodes · 1 edges · 2 communities detected",
                "",
                "## God Nodes (most connected - your core abstractions)",
                "1. `ExternalGod` - 1 edges",
            ]
        ),
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "graphify",
            "export",
            "callflow-html",
            str(external_out / "graph.json"),
            "--output",
            "positional.html",
            "--max-sections",
            "4",
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    html = (tmp_path / "positional.html").read_text(encoding="utf-8")
    assert "ExternalOnly" in html
    assert "ExternalGod" in html
    assert "ApiClient" not in html
    assert "Transformer" not in html


def test_derive_sections_groups_by_architecture_keywords():
    nodes = [
        {"id": "extract_py", "label": "extract_python", "source_file": "graphify/extract.py", "community": 0},
        {"id": "extract_js", "label": "extract_js", "source_file": "graphify/extract.py", "community": 0},
        {"id": "to_html", "label": "to_html", "source_file": "graphify/export.py", "community": 1},
        {"id": "test_html", "label": "test_export_html", "source_file": "tests/test_export.py", "community": 2},
    ]

    sections = derive_sections_from_communities(nodes, {}, "en", 6)
    ids = {section["id"] for section in sections}

    assert "extract-pipeline" in ids
    assert "outputs-docs" in ids
    assert "tests-fixtures" in ids


def test_load_graph_rejects_oversized_file(monkeypatch, tmp_path):
    """#F4: callflow_html.load_graph must refuse to read a graph.json that
    exceeds the size cap (SystemExit via translated ValueError)."""
    import pytest
    from graphify.callflow_html import load_graph

    graph_path = tmp_path / "graph.json"
    graph_path.write_text(
        json.dumps({"nodes": [], "links": []}),
        encoding="utf-8",
    )
    monkeypatch.setattr("graphify.security._MAX_GRAPH_FILE_BYTES", 8)
    with pytest.raises(SystemExit) as excinfo:
        load_graph(graph_path)
    assert "exceeds" in str(excinfo.value)


def _write_graph(tmp_path: Path, nodes: list, links: list) -> Path:
    graph_path = tmp_path / "graph.json"
    graph_path.write_text(
        json.dumps(
            {
                "directed": False,
                "multigraph": False,
                "graph": {},
                "nodes": nodes,
                "links": links,
                "hyperedges": [],
            }
        ),
        encoding="utf-8",
    )
    return graph_path


def test_load_graph_preserves_edge_direction(tmp_path):
    """#1174/#2487: graph.json is written with "directed": false, so the
    node-link parser must be told otherwise or networkx returns an undirected
    Graph and caller->callee orientation becomes arbitrary."""
    from graphify.callflow_html import generate_call_table_rows, load_graph

    # Callee node inserted first: an undirected round-trip deterministically
    # yields the flipped (api, run) arc, so this fails without the forced
    # directed load.
    graph_path = _write_graph(
        tmp_path,
        nodes=[
            {"id": "api", "label": "ApiClient", "source_file": "src/api.py", "file_type": "code", "community": 0},
            {"id": "run", "label": "run()", "source_file": "src/main.py", "file_type": "code", "community": 0},
        ],
        links=[
            {"source": "run", "target": "api", "relation": "calls", "confidence": "EXTRACTED", "confidence_score": 1.0},
        ],
    )
    nodes, edges, _hyper, _meta = load_graph(graph_path)

    directed = {(e["source"], e["target"]) for e in edges}
    assert ("run", "api") in directed
    assert ("api", "run") not in directed, "edge direction was lost (undirected load)"

    api_node = [n for n in nodes if n["id"] == "api"]
    rows = generate_call_table_rows(api_node, edges, "en", edges, nodes)
    assert "run()" in rows, "api's Caller column should list run()"
    assert "External entry" not in rows
    assert "No direct outbound edge" in rows, "api has no callees"


def test_load_graph_legacy_markers_override_arc_order(tmp_path):
    """Legacy graph.json files carry _src/_tgt markers on each link; they must
    override the stored arc even under the forced-directed load."""
    from graphify.callflow_html import generate_call_table_rows, load_graph

    graph_path = _write_graph(
        tmp_path,
        nodes=[
            {"id": "A", "label": "alpha()", "source_file": "src/a.py", "file_type": "code", "community": 0},
            {"id": "B", "label": "beta()", "source_file": "src/b.py", "file_type": "code", "community": 0},
        ],
        links=[
            {"source": "B", "target": "A", "_src": "A", "_tgt": "B", "relation": "calls", "confidence": "EXTRACTED", "confidence_score": 1.0},
        ],
    )
    nodes, edges, _hyper, _meta = load_graph(graph_path)

    assert len(edges) == 1
    assert (edges[0]["source"], edges[0]["target"]) == ("A", "B")

    b_node = [n for n in nodes if n["id"] == "B"]
    rows = generate_call_table_rows(b_node, edges, "en", edges, nodes)
    assert "alpha()" in rows, "B's Caller column should list alpha()"
    assert "External entry" not in rows


def test_call_table_counts_indirect_call_relation():
    """indirect_call edges are real callers (affected.py's relation set); a
    node reached only via indirect_call must not be an "External entry"."""
    from graphify.callflow_html import generate_call_table_rows

    nodes = [
        {"id": "A", "label": "alpha()", "source_file": "src/a.py", "file_type": "code"},
        {"id": "B", "label": "beta()", "source_file": "src/b.py", "file_type": "code"},
    ]
    edges = [{"source": "A", "target": "B", "relation": "indirect_call"}]

    rows = generate_call_table_rows([nodes[1]], edges, "en", edges, nodes)
    assert "External entry" not in rows
    assert "alpha()" in rows, "indirect caller should appear in the Caller column"


def test_load_graph_preserves_parallel_edges(tmp_path):
    """Forcing multigraph keeps parallel edges between the same endpoints, and
    the caller set still dedupes so the table does not double-count."""
    from graphify.callflow_html import generate_call_table_rows, load_graph

    graph_path = _write_graph(
        tmp_path,
        nodes=[
            {"id": "A", "label": "alpha()", "source_file": "src/a.py", "file_type": "code", "community": 0},
            {"id": "B", "label": "beta()", "source_file": "src/b.py", "file_type": "code", "community": 0},
        ],
        links=[
            {"source": "A", "target": "B", "relation": "calls", "confidence": "EXTRACTED", "confidence_score": 1.0},
            {"source": "A", "target": "B", "relation": "references", "confidence": "EXTRACTED", "confidence_score": 1.0},
        ],
    )
    nodes, edges, _hyper, _meta = load_graph(graph_path)

    parallel = [e for e in edges if (e["source"], e["target"]) == ("A", "B")]
    assert len(parallel) == 2, "parallel edges were collapsed (multigraph forcing lost)"
    assert {e["relation"] for e in parallel} == {"calls", "references"}

    b_node = [n for n in nodes if n["id"] == "B"]
    rows = generate_call_table_rows(b_node, edges, "en", edges, nodes)
    assert rows.count("alpha()") == 1, "caller set should dedupe parallel edges"


def test_call_table_caller_column_sees_other_sections(tmp_path):
    """A node called from a different section is not an "External entry".

    ``export`` is used by ``api``, which lives in another community. Computing
    the Caller column from section-local edges alone mislabels it an entry
    point -- a whole-graph claim made from partial data.
    """
    from graphify.callflow_html import generate_call_table_rows, load_graph

    out = _make_graphify_out(tmp_path)
    nodes, edges, _hyper, _meta = load_graph(out / "graph.json")
    export_node = [n for n in nodes if n["id"] == "export"]

    rows = generate_call_table_rows(export_node, [], "en", edges, nodes)
    assert "External entry" not in rows
    assert "ApiClient" in rows, "cross-section caller should render as a label"


def test_call_table_rows_without_whole_graph_params_unchanged(tmp_path):
    """The new all_edges/all_nodes params default to None, so existing
    three-argument callers keep the previous section-local behaviour."""
    from graphify.callflow_html import generate_call_table_rows, load_graph

    out = _make_graphify_out(tmp_path)
    nodes, edges, _hyper, _meta = load_graph(out / "graph.json")
    section_nodes = [n for n in nodes if n["community"] == 0]
    section_ids = {n["id"] for n in section_nodes}
    section_edges = [e for e in edges if e["source"] in section_ids and e["target"] in section_ids]

    legacy = generate_call_table_rows(section_nodes, section_edges, "en")
    # Section-local fixture: the whole graph *is* the section, so the new
    # path must be byte-identical to the legacy three-argument call.
    explicit = generate_call_table_rows(section_nodes, section_edges, "en", section_edges, section_nodes)
    assert legacy == explicit

    # And without the params, out-of-section callers stay invisible (the old
    # semantics other call sites may rely on).
    export_node = [n for n in nodes if n["id"] == "export"]
    assert "External entry" in generate_call_table_rows(export_node, section_edges, "en")
