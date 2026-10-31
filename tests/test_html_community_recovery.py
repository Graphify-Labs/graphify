"""REQ-QML-019 export recovers grouping without changing accepted source facts."""
import copy
import json
import re

import networkx as nx
import pytest

from graphify.export import to_html
from graphify.exporters.html_communities import prepare_html_communities


def public_graph():
    """Two tightly connected public groups have one observable aggregate link."""
    graph = nx.Graph()
    for prefix in ("a", "b"):
        members = [f"{prefix}{i}" for i in range(4)]
        for node in members:
            graph.add_node(node, label=node, source_file=f"{prefix}.py", file_type="code")
        for index, source in enumerate(members):
            for target in members[index + 1:]:
                graph.add_edge(source, target, relation="references", confidence="EXTRACTED")
    graph.add_edge("a0", "b0", relation="calls", confidence="EXTRACTED")
    return graph


def payload(path, key):
    match = re.search(r"const " + key + r" = (\[.*?\]);", path.read_text(encoding="utf-8"), re.S)
    assert match, f"actual HTML payload lacks {key}"
    return json.loads(match[1])


def invoke_export(monkeypatch, directory, *args):
    """Call the real CLI with isolated state; report its actual success/failure exit."""
    import sys
    from graphify.__main__ import main

    monkeypatch.chdir(directory)
    monkeypatch.setenv("GRAPHIFY_NO_AUTO_REFRESH", "1")
    monkeypatch.setenv("GRAPHIFY_NO_TIPS", "1")
    monkeypatch.setattr(sys, "argv", ["graphify", "export", "html", *args])
    try:
        main()
    except SystemExit as result:
        return result.code
    return 0


def saved_graph(directory, graph=None):
    """Persist real unclustered JSON with no analysis or label sidecar."""
    from graphify.export import to_json

    directory.mkdir(exist_ok=True)
    path = directory / "graph.json"
    assert to_json(public_graph() if graph is None else graph, {}, str(path))
    return path


@pytest.mark.parametrize("groups", [{}, {0: ["a0", "a1"], 1: ["b0"]}])
def test_req_qml019_ac01_large_export_recovers_complete_partition(tmp_path, groups):
    """A small explicit cap exercises the large-graph production branch offline."""
    graph = public_graph()
    before = copy.deepcopy((graph, groups))
    output = tmp_path / "graph.html"
    assert to_html(graph, groups, str(output), node_limit=3)
    nodes, edges, legend = (payload(output, key) for key in ("RAW_NODES", "RAW_EDGES", "LEGEND"))
    assert len(nodes) == 2 and len(edges) == 1
    assert sorted(entry["count"] for entry in legend) == [4, 4]
    assert sum(entry["count"] for entry in legend) == len(graph)
    assert {entry["label"] for entry in legend} == {"a0", "b0"}
    assert nx.utils.graphs_equal(graph, before[0]) and groups == before[1]
    initial = output.read_bytes()
    assert to_html(graph, groups, str(output), node_limit=3)
    assert output.read_bytes() == initial


def test_req_qml019_ac02_existing_groups_get_missing_labels(tmp_path):
    """Complete saved membership remains authoritative; only absent names recover."""
    graph = public_graph()
    groups = {7: [f"a{i}" for i in range(4)], 9: [f"b{i}" for i in range(4)]}
    labels = {7: "Chosen public title"}
    before = copy.deepcopy((graph, groups, labels))
    output = tmp_path / "graph.html"
    assert to_html(graph, groups, str(output), node_limit=3, community_labels=labels)
    legend = {entry["cid"]: entry for entry in payload(output, "LEGEND")}
    assert set(legend) == {7, 9}
    assert legend[7]["label"] == "Chosen public title" and legend[9]["label"] == "b0"
    assert sorted(entry["count"] for entry in legend.values()) == [4, 4]
    assert nx.utils.graphs_equal(graph, before[0]) and (groups, labels) == before[1:]


@pytest.mark.parametrize("invalid", [
    {}, {0: ["a0"]}, {0: ["a0", "a0"]}, {0: ["foreign"]},
    {0: []}, {"bad": ["a0"]}, {True: ["a0"]}, {0: [["unhashable"]]},
])
def test_req_qml019_ac01_invalid_saved_membership_is_rebuilt_without_stale_names(invalid):
    """Missing, stale, duplicate or malformed membership must not omit source nodes."""
    graph = public_graph()
    labels = {0: "Stale previous partition", 44: "Foreign label"}
    before = copy.deepcopy((graph, invalid, labels))
    groups, names = prepare_html_communities(graph, invalid, labels, recover_missing=True)
    flattened = [node for members in groups.values() for node in members]
    assert set(flattened) == set(graph) and len(flattened) == len(graph)
    assert set(names) == set(groups) and set(names.values()) == {"a0", "b0"}
    assert nx.utils.graphs_equal(graph, before[0]) and (invalid, labels) == before[1:]


def test_req_qml019_ac02_small_partial_groups_keep_membership_and_fill_actual_names(monkeypatch):
    """A full-node view must not incur new clustering or add a foreign legend entry."""
    graph = public_graph()
    groups = {7: ["a0"], 9: ["b0"], 12: ["foreign"], 14: []}
    supplied = {7: "Chosen public title", 9: " ", 45: "Stale label-only group"}
    before = copy.deepcopy((graph, groups, supplied))

    def forbidden(_):
        pytest.fail("small partial grouping must not be clustered")

    monkeypatch.setattr("graphify.exporters.html_communities.cluster", forbidden)
    result, labels = prepare_html_communities(graph, groups, supplied, recover_missing=False)
    assert result == groups and result is not groups and result[7] is not groups[7]
    assert labels == {7: "Chosen public title", 9: "b0"}
    assert nx.utils.graphs_equal(graph, before[0]) and (groups, supplied) == before[1:]


def test_req_qml019_ac02_valid_partition_and_names_are_authoritative(monkeypatch):
    """Complete membership is copied without renumbering or a replacement clustering pass."""
    graph = public_graph()
    groups = {7: [f"a{i}" for i in range(4)], 9: [f"b{i}" for i in range(4)]}
    supplied = {7: "Chosen <title>", 9: "Second title", 88: "Stale foreign group"}

    def forbidden(_):
        pytest.fail("valid complete grouping must not be clustered")

    monkeypatch.setattr("graphify.exporters.html_communities.cluster", forbidden)
    result, labels = prepare_html_communities(graph, groups, supplied, recover_missing=True)
    assert result == groups and result[9] is not groups[9]
    assert labels == {7: "Chosen <title>", 9: "Second title"}
    assert labels is not supplied


def test_req_qml019_ac02_empty_graph_does_not_invoke_clustering_or_labeling(monkeypatch):
    """No accepted nodes means no recovered groups, names or unnecessary backend work."""
    def forbidden(*_):
        pytest.fail("empty graph must not require clustering or naming")

    monkeypatch.setattr("graphify.exporters.html_communities.cluster", forbidden)
    monkeypatch.setattr("graphify.exporters.html_communities.label_communities_by_hub", forbidden)
    assert prepare_html_communities(nx.Graph(), {0: ["foreign"]}, {0: "old"}, recover_missing=True) == ({}, {})


@pytest.mark.parametrize("invalid", [{}, {0: ["a0"]}, {0: list("foreign")}, {"bad": ["a0"]}])
def test_req_qml019_ac03_invalid_computed_partition_preserves_output_and_recovers(tmp_path, monkeypatch, invalid):
    """Reject bad clustering at the actual writer seam, preserve old HTML, then retry."""
    graph = public_graph()
    old_groups, old_labels = {}, {0: "Old grouping name"}
    before = copy.deepcopy((graph, old_groups, old_labels))
    output = tmp_path / "graph.html"
    output.write_bytes(b"previous valid HTML artifact")
    from graphify.exporters import html_communities as preparation

    with monkeypatch.context() as scoped:
        scoped.setattr(preparation, "cluster", lambda _: invalid)
        with pytest.raises(ValueError, match="^HTML_GROUPING_INVALID:"):
            to_html(graph, old_groups, str(output), community_labels=old_labels, node_limit=3)
    assert output.read_bytes() == b"previous valid HTML artifact"
    assert nx.utils.graphs_equal(graph, before[0]) and (old_groups, old_labels) == before[1:]
    assert to_html(graph, old_groups, str(output), community_labels=old_labels, node_limit=3)
    assert sum(item["count"] for item in payload(output, "LEGEND")) == len(graph)
    assert {item["label"] for item in payload(output, "LEGEND")} == {"a0", "b0"}


def test_req_qml019_ac03_clustering_exception_is_bounded_and_original_graph_is_unchanged(tmp_path, monkeypatch):
    """A failing cluster operates on a copy and cannot replace the prior durable HTML."""
    graph = public_graph()
    graph.nodes["a0"]["attributes"] = {"public": {"keep": True}}
    before = copy.deepcopy(graph)
    output = tmp_path / "graph.html"
    output.write_bytes(b"previous valid HTML artifact")

    def failing(copy_graph):
        copy_graph.nodes["a0"]["label"] = "changed in clustering view"
        copy_graph.remove_node("b0")
        raise RuntimeError("sensitive provider response must not appear in diagnostic")

    monkeypatch.setattr("graphify.exporters.html_communities.cluster", failing)
    with pytest.raises(ValueError, match="^HTML_GROUPING_INVALID:") as error:
        to_html(graph, {}, str(output), node_limit=3)
    assert "sensitive provider" not in str(error.value)
    assert nx.utils.graphs_equal(graph, before)
    assert output.read_bytes() == b"previous valid HTML artifact"


def test_req_qml019_ac01_cli_exports_unclustered_saved_graph_without_sidecars(tmp_path, monkeypatch):
    """Actual export with a small cap recovers null community attributes without editing graph.json."""
    output = tmp_path / "graphify-out"
    graph_path = saved_graph(output)
    before = graph_path.read_bytes()
    assert invoke_export(monkeypatch, tmp_path, "--node-limit", "3") == 0
    assert graph_path.read_bytes() == before
    legend = payload(output / "graph.html", "LEGEND")
    assert len(legend) == 2 and sorted(item["count"] for item in legend) == [4, 4]
    assert not (output / ".graphify_analysis.json").exists()


def test_req_qml019_ac03_cli_unavailable_view_retains_prior_outputs_and_retries(tmp_path, monkeypatch, capsys):
    """A saved one-group view rejects aggregation; correcting only its sidecar permits retry."""
    output = tmp_path / "graphify-out"
    graph_path = saved_graph(output)
    sidecar, html = output / ".graphify_analysis.json", output / "graph.html"
    sidecar.write_text(json.dumps({"communities": {0: list(public_graph())}}), encoding="utf-8")
    html.write_bytes(b"prior valid HTML")
    before = {path: path.read_bytes() for path in (graph_path, sidecar, html)}
    assert invoke_export(monkeypatch, tmp_path, "--node-limit", "3") == 1
    stdout, stderr = capsys.readouterr()
    assert "HTML_VIEW_UNAVAILABLE" in stderr and "graph.html written" not in stdout
    assert all(path.read_bytes() == value for path, value in before.items())
    groups = {0: [f"a{i}" for i in range(4)], 1: [f"b{i}" for i in range(4)]}
    sidecar.write_text(json.dumps({"communities": groups}), encoding="utf-8")
    corrected = sidecar.read_bytes()
    assert invoke_export(monkeypatch, tmp_path, "--node-limit", "3") == 0
    assert graph_path.read_bytes() == before[graph_path] and sidecar.read_bytes() == corrected
    assert sorted(item["count"] for item in payload(html, "LEGEND")) == [4, 4]


@pytest.mark.parametrize("failure", ["grouping", "replace"])
def test_req_qml019_ac03_cli_failure_has_no_false_write_and_preserves_prior_html(tmp_path, monkeypatch, capsys, failure):
    """Fail the clustering algorithm or real atomic replacement; the CLI must exit nonzero."""
    import os
    from pathlib import Path
    from graphify.exporters import html_communities

    output = tmp_path / "graphify-out"
    graph_path = saved_graph(output)
    html = output / "graph.html"
    html.write_bytes(b"prior valid HTML")
    before = graph_path.read_bytes()
    if failure == "grouping":
        original_cluster = html_communities.cluster
        monkeypatch.setattr("graphify.exporters.html_communities.cluster", lambda _: {})
    else:
        replace = os.replace

        def fail_replace(source, destination):
            if Path(destination) == html:
                raise OSError("injected real replacement failure")
            return replace(source, destination)

        monkeypatch.setattr(os, "replace", fail_replace)
    assert invoke_export(monkeypatch, tmp_path, "--node-limit", "3") == 1
    stdout, stderr = capsys.readouterr()
    code = "HTML_GROUPING_INVALID" if failure == "grouping" else "HTML_VIEW_FAILED"
    assert code in stderr and "graph.html written" not in stdout
    assert html.read_bytes() == b"prior valid HTML" and graph_path.read_bytes() == before
    if failure == "grouping":
        monkeypatch.setattr(html_communities, "cluster", original_cluster)
    else:
        monkeypatch.setattr(os, "replace", replace)
    assert invoke_export(monkeypatch, tmp_path, "--node-limit", "3") == 0
    assert graph_path.read_bytes() == before
    assert sorted(item["count"] for item in payload(html, "LEGEND")) == [4, 4]


def test_req_qml019_ac03_isolate_partition_over_hard_cap_is_not_published(tmp_path, monkeypatch, capsys):
    """Recovery may produce too many groups; that remains a bounded-view failure."""
    graph = nx.Graph()
    graph.add_nodes_from((f"isolated-{i}", {"label": f"Public node {i}"}) for i in range(5001))
    output = tmp_path / "graphify-out"
    path = saved_graph(output, graph)
    html = output / "graph.html"
    html.write_bytes(b"prior valid HTML")
    before = path.read_bytes()
    assert invoke_export(monkeypatch, tmp_path) == 1
    stdout, stderr = capsys.readouterr()
    assert "HTML_VIEW_FAILED" in stderr and "graph.html written" not in stdout
    assert html.read_bytes() == b"prior valid HTML" and path.read_bytes() == before


def test_req_qml019_ac01_explicit_graph_uses_adjacent_analysis_not_malformed_cwd_sidecar(tmp_path, monkeypatch):
    """A custom graph's complete saved partition is authoritative over unrelated cwd data."""
    path = saved_graph(tmp_path / "custom")
    cwd_output = tmp_path / "graphify-out"
    cwd_output.mkdir()
    (cwd_output / ".graphify_analysis.json").write_text("malformed unrelated JSON", encoding="utf-8")
    groups = {7: ["a0", "a1", "b0", "b1"], 9: ["a2", "a3", "b2", "b3"]}
    sidecar = path.parent / ".graphify_analysis.json"
    sidecar.write_text(json.dumps({"communities": groups}), encoding="utf-8")
    (path.parent / ".graphify_labels.json").write_text(json.dumps({7: "Chosen first", 9: "Chosen second"}), encoding="utf-8")
    before = path.read_bytes(), sidecar.read_bytes()
    assert invoke_export(monkeypatch, tmp_path, "--graph", str(path), "--node-limit", "3") == 0
    legend = payload(path.parent / "graph.html", "LEGEND")
    assert {entry["label"] for entry in legend} == {"Chosen first", "Chosen second"}
    assert sorted(entry["count"] for entry in legend) == [4, 4]
    assert (path.read_bytes(), sidecar.read_bytes()) == before
