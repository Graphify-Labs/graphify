from __future__ import annotations

import json
import re
from pathlib import Path

import networkx as nx
import pytest
from networkx.readwrite import json_graph

import graphify.__main__ as mainmod
import graphify.serve as serve_mod
from graphify.serve import (
    _bfs,
    _dfs,
    _format_resolution_error,
    _query_graph_text,
    _resolve_node,
    _source_display,
    _stage_candidates,
    _subgraph_to_text,
)


def _memory_graph() -> nx.Graph:
    graph = nx.Graph()
    graph.add_node(
        "code",
        label="CacheService",
        source_file="src/cache.py",
        source_location="L10-L30",
        community=0,
    )
    graph.add_node(
        "memory",
        label="Q: cache invalidation",
        source_file="graphify-out/memory/cache.md",
        source_location="L8",
        community=0,
    )
    graph.add_edge("code", "memory", relation="mentions", confidence="EXTRACTED")
    return graph


def test_query_excludes_saved_memory_by_default() -> None:
    text = _query_graph_text(_memory_graph(), "cache", depth=1)

    assert "NODE CacheService" in text
    assert "Q: cache invalidation" not in text


def test_query_includes_saved_memory_explicitly() -> None:
    text = _query_graph_text(_memory_graph(), "cache include:memory", depth=1)

    assert "Memory: included" in text
    assert "Q: cache invalidation" in text


def test_query_falls_back_to_memory_when_it_is_the_only_match() -> None:
    graph = _memory_graph()
    text = _query_graph_text(graph, "invalidation", depth=1)

    assert "Memory: fallback" in text
    assert "Q: cache invalidation" in text


def test_question_label_in_normal_docs_is_not_saved_memory() -> None:
    graph = _memory_graph()
    graph.add_node(
        "faq",
        label="Q: cache invalidation FAQ",
        source_file="docs/faq.md",
        source_location="L12",
        community=0,
    )

    text = _query_graph_text(graph, "cache invalidation FAQ", depth=1)

    assert "NODE Q: cache invalidation FAQ" in text
    assert "Q: cache invalidation [" not in text
    assert "Memory:" not in text


def _write_community_graph(tmp_path):
    graph = nx.Graph()
    graph.add_node(
        "route",
        label="RouteHandler",
        source_file="src/route.py",
        community=0,
        community_name="Embedded Runtime",
    )
    graph.add_node(
        "telemetry",
        label="TelemetrySample",
        source_file="src/telemetry.py",
        community=1,
        community_name="Embedded Telemetry",
    )
    path = tmp_path / "graph.json"
    path.write_text(json.dumps(json_graph.node_link_data(graph, edges="links")))
    return path


def test_adjacent_community_labels_override_embedded_names_and_match_folded(
    tmp_path,
) -> None:
    graph_path = _write_community_graph(tmp_path)
    (tmp_path / ".graphify_labels.json").write_text(json.dumps({
        "0": "Main Rúntime Orchestration",
        "1": "Telemetry Sampling",
    }))

    graph = serve_mod._load_graph(str(graph_path))
    text = _query_graph_text(
        graph,
        'RouteHandler community:"main runtime orchestration"',
        depth=1,
    )

    assert graph.nodes["route"]["community_name"] == "Main Rúntime Orchestration"
    assert "Filter: community:0 (Main Rúntime Orchestration)" in text
    assert "NODE RouteHandler" in text


def test_adjacent_community_labels_ignore_stale_extra_ids(tmp_path) -> None:
    graph_path = _write_community_graph(tmp_path)
    (tmp_path / ".graphify_labels.json").write_text(json.dumps({
        "0": "Current Runtime",
        "99": "Stale Removed Community",
    }))

    graph = serve_mod._load_graph(str(graph_path))

    assert "Filter: community:0 (Current Runtime)" in _query_graph_text(
        graph, "RouteHandler community:0"
    )
    assert "Unknown or ambiguous community" in _query_graph_text(
        graph, 'RouteHandler community:"Stale Removed Community"'
    )


def test_malformed_adjacent_community_labels_preserve_embedded_and_numeric(
    tmp_path,
) -> None:
    graph_path = _write_community_graph(tmp_path)
    (tmp_path / ".graphify_labels.json").write_text("{not-json")

    graph = serve_mod._load_graph(str(graph_path))
    text = _query_graph_text(graph, "RouteHandler community:0")

    assert graph.nodes["route"]["community_name"] == "Embedded Runtime"
    assert "Filter: community:0 (Embedded Runtime)" in text


def test_oversized_community_labels_are_rejected_before_open(
    monkeypatch, tmp_path
) -> None:
    graph_path = _write_community_graph(tmp_path)
    labels_path = tmp_path / ".graphify_labels.json"
    labels_path.write_bytes(b"x" * 65)
    monkeypatch.setattr(serve_mod, "_MAX_COMMUNITY_LABELS_BYTES", 64)
    original_open = Path.open

    def guarded_open(path, *args, **kwargs):
        if path == labels_path:
            raise AssertionError("oversized sidecar must not be opened")
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", guarded_open)

    assert serve_mod._load_adjacent_community_labels(graph_path) == {}


def test_oversized_community_labels_preserve_embedded_and_numeric(
    monkeypatch, tmp_path
) -> None:
    graph_path = _write_community_graph(tmp_path)
    (tmp_path / ".graphify_labels.json").write_text(json.dumps({
        "0": "Canonical Runtime Name That Exceeds The Patched Test Byte Cap",
    }))
    monkeypatch.setattr(serve_mod, "_MAX_COMMUNITY_LABELS_BYTES", 32)

    graph = serve_mod._load_graph(str(graph_path))
    text = _query_graph_text(graph, "RouteHandler community:0")

    assert graph.nodes["route"]["community_name"] == "Embedded Runtime"
    assert "Filter: community:0 (Embedded Runtime)" in text


def test_community_label_entry_cap_rejects_entire_artifact(
    monkeypatch, tmp_path
) -> None:
    graph_path = _write_community_graph(tmp_path)
    (tmp_path / ".graphify_labels.json").write_text(json.dumps({
        "0": "Canonical Runtime",
        "1": "Canonical Telemetry",
        "2": "Stale Extra",
    }))
    monkeypatch.setattr(serve_mod, "_MAX_COMMUNITY_LABEL_ENTRIES", 2)

    graph = serve_mod._load_graph(str(graph_path))

    assert graph.graph["_community_labels"] == {}
    assert graph.nodes["route"]["community_name"] == "Embedded Runtime"


@pytest.mark.parametrize(
    "payload",
    [
        [],
        {"0": 123},
        {"0": "Would Be Partial", "invalid": "Reject Everything"},
        {"labels": []},
        {"labels": {"0": "One"}, "communities": {"1": "Two"}},
        {"0": {"name": 123}},
        {"0": "x" * 1025},
    ],
)
def test_malformed_community_label_shapes_reject_entire_artifact(
    tmp_path, payload
) -> None:
    graph_path = _write_community_graph(tmp_path)
    (tmp_path / ".graphify_labels.json").write_text(json.dumps(payload))

    graph = serve_mod._load_graph(str(graph_path))

    assert graph.graph["_community_labels"] == {}
    assert graph.nodes["route"]["community_name"] == "Embedded Runtime"


def test_cli_query_uses_adjacent_named_community(
    monkeypatch, tmp_path, capsys
) -> None:
    graph_path = _write_community_graph(tmp_path)
    (tmp_path / ".graphify_labels.json").write_text(json.dumps({
        "0": "Main Runtime Orchestration",
        "1": "Telemetry Sampling",
    }))
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)
    monkeypatch.setattr(mainmod.sys, "argv", [
        "graphify",
        "query",
        'RouteHandler community:"Main Runtime Orchestration"',
        "--graph",
        str(graph_path),
    ])

    mainmod.main()

    assert "Filter: community:0 (Main Runtime Orchestration)" in capsys.readouterr().out


def test_cli_unknown_community_filter_exits_two_with_resolvable_suggestion(
    monkeypatch, tmp_path, capsys
) -> None:
    graph_path = _write_community_graph(tmp_path)
    (tmp_path / ".graphify_labels.json").write_text(json.dumps({
        "0": "Main Runtime Orchestration",
        "1": "Telemetry Sampling",
    }))
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)
    monkeypatch.setattr(mainmod.sys, "argv", [
        "graphify",
        "query",
        "RouteHandler community:MainRuntim",
        "--graph",
        str(graph_path),
    ])

    with pytest.raises(SystemExit) as exc_info:
        mainmod.main()

    error = capsys.readouterr().err
    assert exc_info.value.code == 2
    assert "Error: Unknown or ambiguous community filter" in error
    assert "community:0" in error


def test_cli_ambiguous_god_filter_exits_two_with_exact_id_suggestions(
    monkeypatch, tmp_path, capsys
) -> None:
    graph = nx.Graph()
    graph.add_node("router_a", label="Router", source_file="src/a.py", community=0)
    graph.add_node("router_b", label="Router", source_file="src/b.py", community=0)
    graph.add_node("route", label="RouteHandler", source_file="src/route.py", community=0)
    graph.add_edges_from([("router_a", "route"), ("router_b", "route")])
    graph_path = tmp_path / "graph.json"
    graph_path.write_text(json.dumps(json_graph.node_link_data(graph, edges="links")))
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)
    monkeypatch.setattr(mainmod.sys, "argv", [
        "graphify",
        "query",
        "RouteHandler god:Router",
        "--graph",
        str(graph_path),
    ])

    with pytest.raises(SystemExit) as exc_info:
        mainmod.main()

    error = capsys.readouterr().err
    assert exc_info.value.code == 2
    assert "Error: Ambiguous god filter 'Router'." in error
    assert "god:router_a" in error
    assert "god:router_b" in error


@pytest.mark.parametrize(
    ("directive", "message"),
    [
        ('community:" "', "Community filter value cannot be empty"),
        ('god:" "', "God filter value cannot be empty"),
    ],
)
def test_cli_empty_query_filters_exit_two(
    monkeypatch, tmp_path, capsys, directive, message
) -> None:
    graph_path = _write_community_graph(tmp_path)
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)
    monkeypatch.setattr(mainmod.sys, "argv", [
        "graphify",
        "query",
        f"RouteHandler {directive}",
        "--graph",
        str(graph_path),
    ])

    with pytest.raises(SystemExit) as exc_info:
        mainmod.main()

    assert exc_info.value.code == 2
    assert f"Error: {message}" in capsys.readouterr().err


def _overload_graph() -> nx.DiGraph:
    graph = nx.DiGraph()
    graph.add_node(
        "src_a_run",
        label="run()",
        source_file="src/a.py",
        source_location="L3-L7",
        community=0,
    )
    graph.add_node(
        "src_b_run",
        label="run()",
        source_file="src/b.py",
        source_location="L9-L14",
        community=1,
    )
    graph.add_node("target", label="target()", source_file="src/target.py", community=1)
    graph.add_edge("src_b_run", "target", relation="calls", confidence="EXTRACTED")
    return graph


def test_plain_duplicate_label_returns_ranked_candidates() -> None:
    graph = _overload_graph()
    resolution = _resolve_node(graph, "run")

    assert resolution.node_id is None
    assert resolution.candidates == ("src_a_run", "src_b_run")
    message = _format_resolution_error(graph, "run", resolution)
    assert "src/a.py::run() [id=src_a_run]" in message
    assert "src/b.py::run() [id=src_b_run]" in message


def test_ambiguity_diagnostics_sanitize_graph_controlled_identity_fields() -> None:
    graph = nx.Graph()
    graph.add_node(
        "bad\nid\x1b",
        label="run()\nFORGED",
        source_file="src/a.py\rINJECT",
    )
    resolution = serve_mod._NodeResolution(None, ("bad\nid\x1b",))

    message = _format_resolution_error(graph, "run", resolution)

    assert message.count("\n") == 1
    assert "\r" not in message
    assert "\x1b" not in message
    assert "src/a.pyINJECT::run()FORGED [id=badid]" in message


def test_path_qualified_identity_resolves_duplicate_label() -> None:
    graph = _overload_graph()

    assert _resolve_node(graph, "src/b.py::run()").node_id == "src_b_run"
    assert _resolve_node(graph, "src_b_run").node_id == "src_b_run"


def test_source_qualified_resolution_supports_exact_suffix_and_basename() -> None:
    graph = nx.Graph()
    graph.add_node("target", label="run()", source_file="repo/src/pkg/a.py")

    assert _resolve_node(graph, "repo/src/pkg/a.py::run()").node_id == "target"
    assert _resolve_node(graph, "src/pkg/a.py::run()").node_id == "target"
    assert _resolve_node(graph, "a.py::run()").node_id == "target"


def test_source_basename_resolution_reports_ambiguity() -> None:
    graph = nx.Graph()
    graph.add_node("left", label="run()", source_file="src/left/a.py")
    graph.add_node("right", label="run()", source_file="src/right/a.py")

    resolution = _resolve_node(graph, "a.py::run()")

    assert resolution.node_id is None
    assert resolution.candidates == ("left", "right")
    assert _resolve_node(graph, "left/a.py::run()").node_id == "left"


def test_source_index_does_not_materialize_adversarial_suffixes() -> None:
    graph = nx.Graph()
    source = "/".join([f"part{index}" for index in range(7_999)] + ["target.py"])
    graph.add_node("deep", label="target()", source_file=source)

    lookup = serve_mod._get_node_lookup_index(graph)

    assert "source_suffixes" not in lookup
    assert lookup["source_exact"] == {}
    assert lookup["source_basenames"] == {"target.py": ["deep"]}
    assert sum(len(index) for index in (
        lookup["source_exact"], lookup["source_basenames"]
    )) == 1
    assert sum(
        len(key)
        for index in (lookup["source_exact"], lookup["source_basenames"])
        for key in index
    ) == len("target.py")


@pytest.mark.parametrize(
    "source_query",
    [
        "a" * 256,
        "/".join(["a"] * 257),
        "a" * 4097,
    ],
)
def test_source_qualified_resolution_rejects_unbounded_queries(
    source_query: str,
) -> None:
    graph = nx.Graph()
    graph.add_node("target", label="run()", source_file="src/a.py")

    assert _resolve_node(graph, f"{source_query}::run()").node_id is None


def test_plain_overload_prefix_does_not_pick_equal_score_arbitrarily() -> None:
    graph = nx.Graph()
    graph.add_node("int", label="run(int)", source_file="src/int.py")
    graph.add_node("str", label="run(str)", source_file="src/str.py")

    resolution = _resolve_node(graph, "run")

    assert resolution.node_id is None
    assert resolution.candidates == ("int", "str")


def _write_graph(tmp_path, graph: nx.Graph):
    path = tmp_path / "graph.json"
    path.write_text(json.dumps(json_graph.node_link_data(graph, edges="links")))
    return path


def test_cli_explain_uses_shared_ambiguity_safe_resolver(
    monkeypatch, tmp_path, capsys
) -> None:
    graph_path = _write_graph(tmp_path, _overload_graph())
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)
    monkeypatch.setattr(
        mainmod.sys,
        "argv",
        ["graphify", "explain", "run", "--graph", str(graph_path)],
    )

    with pytest.raises(SystemExit) as exc_info:
        mainmod.main()

    assert exc_info.value.code == 2
    assert _format_resolution_error(
        _overload_graph(), "run", _resolve_node(_overload_graph(), "run")
    ) in capsys.readouterr().err


def test_cli_ambiguity_diagnostics_strip_control_characters(
    monkeypatch, tmp_path, capsys
) -> None:
    graph = nx.DiGraph()
    graph.add_node(
        "a_run\nid",
        label="run()\nFORGED",
        source_file="src/a.py\rINJECT",
    )
    graph.add_node(
        "b_run\x1bid",
        label="run()\x00SECOND",
        source_file="src/b.py\nSPOOF",
    )
    graph_path = _write_graph(tmp_path, graph)
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)
    monkeypatch.setattr(
        mainmod.sys,
        "argv",
        ["graphify", "explain", "run", "--graph", str(graph_path)],
    )

    with pytest.raises(SystemExit) as exc_info:
        mainmod.main()
    output = capsys.readouterr().err

    assert exc_info.value.code == 2
    assert "\r" not in output
    assert "\x00" not in output
    assert "\x1b" not in output
    assert "src/a.pyINJECT::run()FORGED [id=a_runid]" in output
    assert "src/b.pySPOOF::run()SECOND [id=b_runid]" in output


def test_cli_path_accepts_shared_path_qualified_identity(
    monkeypatch, tmp_path, capsys
) -> None:
    graph_path = _write_graph(tmp_path, _overload_graph())
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)
    monkeypatch.setattr(
        mainmod.sys,
        "argv",
        [
            "graphify",
            "path",
            "src/b.py::run()",
            "target",
            "--graph",
            str(graph_path),
        ],
    )

    mainmod.main()

    assert "run() --calls [EXTRACTED]--> target()" in capsys.readouterr().out


def test_cli_path_ambiguous_endpoint_exits_usage_error(
    monkeypatch, tmp_path, capsys
) -> None:
    graph_path = _write_graph(tmp_path, _overload_graph())
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)
    monkeypatch.setattr(
        mainmod.sys,
        "argv",
        ["graphify", "path", "run", "target", "--graph", str(graph_path)],
    )

    with pytest.raises(SystemExit) as exc_info:
        mainmod.main()

    assert exc_info.value.code == 2
    assert "Ambiguous source 'run'" in capsys.readouterr().err


def test_staged_candidates_retain_cross_community_global_quota() -> None:
    graph = nx.Graph()
    scored = []
    for index, community in enumerate((0, 0, 1, 1, 2, 3)):
        nid = f"n{index}"
        graph.add_node(
            nid,
            label=f"cache_{index}",
            source_file=f"src/cache_{index}.py",
            community=community,
        )
        scored.append((100.0 - index, nid))

    staged, metadata = _stage_candidates(
        graph, scored, "cache", limit=5, global_quota=1
    )
    selected = {nid for _, nid in staged}

    assert metadata["communities"] == [0, 1]
    assert metadata["global"] == 1
    assert selected & {"n4", "n5"}
    assert len(staged) == 5


@pytest.mark.parametrize(
    ("source_file", "expected_scope"),
    [("docs/exact.md", "docs"), ("tests/test_exact.py", "tests")],
)
def test_staging_never_drops_global_exact_cross_scope_match(
    source_file: str, expected_scope: str
) -> None:
    graph = nx.Graph()
    graph.add_node("exact", label="ExactTarget", source_file=source_file, community=9)
    for index in range(10):
        graph.add_node(
            f"code_{index}",
            label=f"TargetHelper{index}",
            source_file=f"src/helper_{index}.py",
            community=0,
        )
    scored = [(1000.0, "exact")] + [
        (100.0 - index, f"code_{index}") for index in range(10)
    ]

    staged, metadata = _stage_candidates(
        graph, scored, "target", limit=2, global_quota=1
    )

    assert staged[0] == (1000.0, "exact")
    assert "exact" in {nid for _, nid in staged}
    assert expected_scope in metadata["scopes"]


def _filtered_graph() -> nx.Graph:
    graph = nx.Graph()
    graph.add_node(
        "router",
        label="RequestRouter",
        source_file="src/router.py",
        source_location="L10-L40",
        community=0,
        community_name="Backend Flow",
    )
    for index in range(4):
        graph.add_node(
            f"route_{index}",
            label=f"RouteHandler{index}",
            source_file=f"src/route_{index}.py",
            community=0,
            community_name="Backend Flow",
        )
        graph.add_edge("router", f"route_{index}", relation="calls")
    graph.add_node(
        "ui",
        label="RouteHandlerUI",
        source_file="web/ui.py",
        community=1,
        community_name="Frontend",
    )
    return graph


def test_community_filter_scopes_candidates_and_traversal() -> None:
    text = _query_graph_text(
        _filtered_graph(), 'RouteHandler community:"Backend Flow"', depth=2
    )

    assert "Filter: community:0 (Backend Flow)" in text
    assert "RouteHandler0" in text
    assert "RouteHandlerUI" not in text


def test_god_filter_scopes_to_hub_neighborhood() -> None:
    text = _query_graph_text(_filtered_graph(), "RouteHandler god:RequestRouter", depth=2)

    assert "Filter: god:RequestRouter" in text
    assert "RouteHandler0" in text
    assert "RouteHandlerUI" not in text


def test_unknown_filters_return_suggestions() -> None:
    community = _query_graph_text(_filtered_graph(), "route community:Backnd")
    god = _query_graph_text(_filtered_graph(), "route god:RequestRuter")

    assert community.startswith("Error: Unknown or ambiguous community filter")
    assert "community:0" in community
    assert god.startswith("Error: Unknown god filter")
    assert "god:router" in god


@pytest.mark.parametrize(
    ("question", "message"),
    [
        ('route community:" "', "Community filter value cannot be empty"),
        ('route community:""', "Community filter value cannot be empty"),
        ("route community:", "Community filter value cannot be empty"),
        ('route god:" "', "God filter value cannot be empty"),
        ('route god:""', "God filter value cannot be empty"),
        ("route god:", "God filter value cannot be empty"),
    ],
)
def test_empty_filters_return_diagnostics(question: str, message: str) -> None:
    text = _query_graph_text(_filtered_graph(), question)

    assert text.startswith(f"Error: {message}")


def test_community_suggestion_is_copy_paste_resolvable() -> None:
    graph = _filtered_graph()
    error = _query_graph_text(graph, "route community:Backnd")
    suggestion = re.search(r"community:[^, .]+", error)

    assert suggestion is not None
    resolved = _query_graph_text(graph, f"route {suggestion.group(0)}")
    assert not resolved.startswith("Error:")
    assert "Filter: community:0 (Backend Flow)" in resolved


def test_filter_diagnostics_sanitize_community_and_god_labels() -> None:
    graph = _filtered_graph()
    graph.nodes["router"]["label"] = "RequestRouter\nFORGED\x1b"
    graph.nodes["router"]["community_name"] = "Backend\rINJECT"
    for index in range(4):
        graph.nodes[f"route_{index}"]["community_name"] = "Backend\rINJECT"

    community = _query_graph_text(graph, 'route community:"Backend\rINJECT"')
    god = _query_graph_text(graph, 'route god:"RequestRouter\nFORGED\x1b"')

    assert "\r" not in community and "INJECT" in community
    assert "\x1b" not in god
    assert "Filter: god:RequestRouterFORGED" in god


def test_god_filter_resolves_exact_candidate_ranked_after_fifty() -> None:
    graph = nx.Graph()
    node_ids = [f"god{index}" for index in range(60)]
    for index, nid in enumerate(node_ids):
        graph.add_node(
            nid,
            label=f"God{index}",
            source_file=f"src/entity_{index}.py",
            community=0,
        )
    for index, nid in enumerate(node_ids):
        graph.add_edge(nid, node_ids[(index + 1) % len(node_ids)])

    text = _query_graph_text(graph, "God55 god:god55", depth=1)

    assert not text.startswith("Error:")
    assert "Filter: god:God55" in text


def test_traversal_stops_at_node_budget_before_rendering() -> None:
    graph = nx.path_graph([f"n{index}" for index in range(200)])
    for nid in graph:
        graph.nodes[nid].update(label=f"node_{nid}", source_file=f"src/{nid}.py")

    visited, _ = _bfs(graph, ["n0"], depth=199, max_nodes=7)
    text = _query_graph_text(graph, "node", depth=50, token_budget=120)

    assert len(visited) == 7
    header = text.splitlines()[0]
    assert "5 nodes found (budget cap 5)" in header


def _insertion_order_graph(reverse: bool) -> nx.Graph:
    graph = nx.Graph()
    nodes = ["start", "alpha", "beta", "gamma", "alpha_child"]
    for nid in reversed(nodes) if reverse else nodes:
        graph.add_node(nid, label=nid, source_file=f"src/{nid}.py", community=0)
    edges = [
        ("start", "alpha"),
        ("start", "beta"),
        ("start", "gamma"),
        ("alpha", "alpha_child"),
        ("alpha", "beta"),
    ]
    for source, target in reversed(edges) if reverse else edges:
        graph.add_edge(source, target, relation="calls", confidence="EXTRACTED")
    return graph


@pytest.mark.parametrize("traversal", [_bfs, _dfs])
def test_budgeted_traversal_is_independent_of_insertion_order(traversal) -> None:
    forward = _insertion_order_graph(False)
    reverse = _insertion_order_graph(True)

    forward_nodes, forward_edges = traversal(forward, ["start"], depth=3, max_nodes=3)
    reverse_nodes, reverse_edges = traversal(reverse, ["start"], depth=3, max_nodes=3)

    assert forward_nodes == reverse_nodes
    assert forward_edges == reverse_edges


def test_budgeted_bfs_retains_edges_between_selected_nodes() -> None:
    graph = _insertion_order_graph(False)

    nodes, edges = _bfs(graph, ["start"], depth=2, max_nodes=3)

    assert nodes == {"start", "alpha", "beta"}
    assert ("alpha", "beta") in edges


def test_query_output_is_independent_of_insertion_order() -> None:
    forward = _query_graph_text(
        _insertion_order_graph(False), "start", depth=3, token_budget=100
    )
    reverse = _query_graph_text(
        _insertion_order_graph(True), "start", depth=3, token_budget=100
    )

    assert forward == reverse


def test_resolver_reuses_graph_scoped_lookup_index(monkeypatch) -> None:
    graph = nx.Graph()
    for index in range(200):
        graph.add_node(
            f"node_{index}",
            label=f"Target{index}",
            source_file=f"src/target_{index}.py",
        )
    calls = 0
    original = serve_mod._bounded_source_basename

    def counted_basename(value):
        nonlocal calls
        calls += 1
        return original(value)

    monkeypatch.setattr(serve_mod, "_bounded_source_basename", counted_basename)

    assert _resolve_node(graph, "src/target_199.py::Target199").node_id == "node_199"
    first_scan_calls = calls
    assert _resolve_node(graph, "src/target_198.py::Target198").node_id == "node_198"

    assert first_scan_calls == len(graph)
    assert calls == first_scan_calls


def test_default_memory_exclusion_reuses_cached_classification(monkeypatch) -> None:
    graph = nx.Graph()
    for index in range(200):
        graph.add_node(
            f"node_{index}",
            label=f"CacheTarget{index}",
            source_file=f"src/cache_{index}.py",
            community=0,
        )
    graph.add_node(
        "memory",
        label="Q: cache target",
        source_file="graphify-out/memory/cache.md",
        community=0,
    )
    calls = 0
    original = serve_mod._is_memory_node

    def counted_memory(data):
        nonlocal calls
        calls += 1
        return original(data)

    monkeypatch.setattr(serve_mod, "_is_memory_node", counted_memory)

    _query_graph_text(graph, "CacheTarget199", depth=1)
    first_scan_calls = calls
    _query_graph_text(graph, "CacheTarget198", depth=1)

    assert first_scan_calls == len(graph)
    assert calls == first_scan_calls


def test_source_rendering_preserves_spans_and_marks_unowned_nodes() -> None:
    graph = nx.Graph()
    graph.add_node(
        "owned",
        label="owned",
        source_file="src/owned.py",
        source_location="L10-L30",
    )
    graph.add_node("file_only", label="file", source_file="docs/guide.md")
    graph.add_node(
        "external",
        label="ExternalType",
        source_file="",
        source_location="",
        origin_file="src/consumer.py",
    )
    graph.add_node("concept", label="Architecture", source_file="")

    text = _subgraph_to_text(graph, set(graph), [], token_budget=500)

    assert "src=src/owned.py loc=L10-L30" in text
    assert "src=docs/guide.md loc=file-only" in text
    assert "src=external/reference loc=unowned; origin=src/consumer.py" in text
    assert "NODE Architecture [src=unowned loc=no-source" in text
    assert _source_display(graph.nodes["file_only"]) == "docs/guide.md (file only)"
    assert "unowned" in _source_display(graph.nodes["external"])
