"""Source-evidence contracts for ``graphify path`` output."""

from __future__ import annotations

import json

import graphify.__main__ as mainmod


def _write_graph(tmp_path, nodes: list[dict], links: list[dict]):
    graph_path = tmp_path / "graph.json"
    graph_path.write_text(
        json.dumps(
            {
                "directed": True,
                "multigraph": False,
                "graph": {},
                "nodes": nodes,
                "links": links,
            }
        ),
        encoding="utf-8",
    )
    return graph_path


def _run(monkeypatch, capsys, graph_path, source: str, target: str, *extra: str) -> str:
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)
    monkeypatch.setattr(
        mainmod.sys,
        "argv",
        [
            "graphify",
            "path",
            source,
            target,
            "--graph",
            str(graph_path),
            *extra,
        ],
    )
    mainmod.main()
    return capsys.readouterr().out


def _node(node_id: str, label: str, source_file=None, source_location=None) -> dict:
    data = {"id": node_id, "label": label}
    if source_file is not None:
        data["source_file"] = source_file
    if source_location is not None:
        data["source_location"] = source_location
    return data


def _link(source: str, target: str, relation="calls", confidence="EXTRACTED") -> dict:
    return {
        "source": source,
        "target": target,
        "relation": relation,
        "confidence": confidence,
    }


def test_one_hop_includes_source_and_target_file_line(monkeypatch, tmp_path, capsys):
    graph_path = _write_graph(
        tmp_path,
        [
            _node("start", "Start", "src/start.ts", "L10"),
            _node("embed", "Embed", "src/nim/embed.ts", "L42"),
        ],
        [_link("start", "embed")],
    )

    output = _run(monkeypatch, capsys, graph_path, "Start", "Embed")

    assert 'node[0] label="Start" source="src/start.ts:L10" id="start"' in output
    assert 'node[1] label="Embed" source="src/nim/embed.ts:L42" id="embed"' in output


def test_multi_hop_includes_source_proof_for_every_node(monkeypatch, tmp_path, capsys):
    graph_path = _write_graph(
        tmp_path,
        [
            _node("a", "Alpha", "src/a.py", "L1"),
            _node("b", "Bridge", "src/bridge.py", "L2"),
            _node("c", "Charlie", "src/c.py", "L3"),
        ],
        [_link("a", "b"), _link("b", "c", "returns", "INFERRED")],
    )

    output = _run(monkeypatch, capsys, graph_path, "Alpha", "Charlie")

    proof_lines = [line.strip() for line in output.splitlines() if line.strip().startswith("node[")]
    assert proof_lines == [
        'node[0] label="Alpha" source="src/a.py:L1" id="a"',
        'node[1] label="Bridge" source="src/bridge.py:L2" id="b"',
        'node[2] label="Charlie" source="src/c.py:L3" id="c"',
    ]


def test_missing_location_keeps_known_source_file(monkeypatch, tmp_path, capsys):
    graph_path = _write_graph(
        tmp_path,
        [_node("a", "Alpha", "src/a.py", "L1"), _node("embed", "Embed", "src/nim/embed.ts")],
        [_link("a", "embed")],
    )

    output = _run(monkeypatch, capsys, graph_path, "Alpha", "Embed")

    assert 'node[1] label="Embed" source="src/nim/embed.ts" id="embed"' in output


def test_missing_source_uses_honest_placeholder_and_node_id(monkeypatch, tmp_path, capsys):
    graph_path = _write_graph(
        tmp_path,
        [_node("a", "Alpha", "src/a.py", "L1"), _node("external", "External")],
        [_link("a", "external")],
    )

    output = _run(monkeypatch, capsys, graph_path, "Alpha", "External")

    assert 'node[1] label="External" source="<unknown>" id="external"' in output


def test_source_proof_preserves_relation_confidence_and_reverse_arrow(
    monkeypatch,
    tmp_path,
    capsys,
):
    graph_path = _write_graph(
        tmp_path,
        [_node("a", "Alpha", "src/a.py", "L1"), _node("b", "Beta", "src/b.py", "L2")],
        [_link("a", "b", "references", "INFERRED")],
    )

    output = _run(monkeypatch, capsys, graph_path, "Beta", "Alpha", "--undirected")

    assert "Beta <--references [INFERRED]-- Alpha" in output
    assert "Beta --references [INFERRED]--> Alpha" not in output


def test_source_proof_order_is_deterministic(monkeypatch, tmp_path, capsys):
    graph_path = _write_graph(
        tmp_path,
        [
            _node("start", "Start", "src/start.py", "L1"),
            _node("right", "Right", "src/right.py", "L2"),
            _node("left", "Left", "src/left.py", "L3"),
            _node("goal", "Goal", "src/goal.py", "L4"),
        ],
        [
            _link("start", "right"),
            _link("right", "goal"),
            _link("start", "left"),
            _link("left", "goal"),
        ],
    )

    first = _run(monkeypatch, capsys, graph_path, "Start", "Goal")
    second = _run(monkeypatch, capsys, graph_path, "Start", "Goal")

    assert first == second
    assert 'node[1] label="Left" source="src/left.py:L3" id="left"' in first
