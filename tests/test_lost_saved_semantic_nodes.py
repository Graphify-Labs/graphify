"""_lost_saved_semantic_nodes: a semantic ghost deduplicated into its AST twin
(#1145 extended) is preserved, not lost."""
from __future__ import annotations

import json
from pathlib import Path

from graphify.build import _lost_saved_semantic_nodes, build_from_json
from graphify.export import to_json
from graphify.watch import _check_shrink


def _sem(node_id: str, label: str, sf: str) -> dict:
    return {
        "id": node_id,
        "label": label,
        "file_type": "code",
        "source_file": sf,
        "source_location": None,
        "_origin": "semantic",
    }


def _ast(node_id: str, label: str, sf: str) -> dict:
    return {
        "id": node_id,
        "label": label,
        "file_type": "code",
        "source_file": sf,
        "source_location": "L10",
        "_origin": "ast",
    }


def test_same_id_present_is_not_lost():
    saved = [_sem("foo_bar", "bar", "src/foo.py")]
    new = [_sem("foo_bar", "bar", "src/foo.py")]
    assert _lost_saved_semantic_nodes(saved, new) == []


def test_deduplicated_into_ast_node_is_not_lost():
    saved = [_sem("ghost_bar", "bar", "src/foo.py")]
    new = [_ast("foo_py_bar", "bar", "src/foo.py")]
    assert _lost_saved_semantic_nodes(saved, new) == []


def test_non_ast_replacement_is_not_excused():
    saved = [_sem("ghost_bar", "bar", "src/foo.py")]
    new = [_sem("other_bar", "bar", "src/foo.py")]
    lost = _lost_saved_semantic_nodes(saved, new)
    assert [n["id"] for n in lost] == ["ghost_bar"]


def test_ast_label_collision_is_not_excused():
    saved = [_sem("ghost_bar", "bar", "src/foo.py")]
    new = [
        _ast("foo_py_bar_1", "bar", "src/foo.py"),
        _ast("foo_py_bar_2", "bar", "src/foo.py"),
    ]
    lost = _lost_saved_semantic_nodes(saved, new)
    assert [n["id"] for n in lost] == ["ghost_bar"]


def test_ast_collision_after_normalization_is_not_excused():
    saved = [_sem("ghost_bar", "bar", "src/foo.py")]
    new = [
        _ast("foo_py_bar_1", "bar", "src/foo.py"),
        _ast("foo_py_bar_2", "bar", "src\\foo.py"),
    ]
    lost = _lost_saved_semantic_nodes(saved, new)
    assert [n["id"] for n in lost] == ["ghost_bar"]


def test_dedup_match_normalizes_source_file():
    saved = [_sem("ghost_bar", "bar", "src\\foo.py")]
    new = [_ast("foo_py_bar", "bar", "src/foo.py")]
    assert _lost_saved_semantic_nodes(saved, new) == []


def test_genuinely_lost_node_is_reported():
    saved = [_sem("ghost_bar", "bar", "src/foo.py")]
    new = [
        _ast("foo_py_baz", "baz", "src/foo.py"),
        _ast("other_py_bar", "bar", "src/other.py"),
    ]
    lost = _lost_saved_semantic_nodes(saved, new)
    assert [n["id"] for n in lost] == ["ghost_bar"]


def test_node_in_deleted_source_is_not_lost():
    saved = [_sem("ghost_bar", "bar", "src/foo.py")]
    assert _lost_saved_semantic_nodes(saved, [], {"src/foo.py"}) == []


def test_node_in_other_file_not_excused_by_deleted_source():
    saved = [_sem("ghost_bar", "bar", "src/foo.py")]
    lost = _lost_saved_semantic_nodes(saved, [], {"src/other.py"})
    assert [n["id"] for n in lost] == ["ghost_bar"]


def test_malformed_non_string_source_file_does_not_crash():
    # Truthy non-string source_file in new_nodes or saved_nodes must not raise AttributeError
    saved = [{"id": "s1", "label": "S1", "source_file": 123, "_origin": "semantic"}]
    new = [{"id": "n1", "label": "N1", "source_file": True}]
    lost = _lost_saved_semantic_nodes(saved, new)
    assert [n["id"] for n in lost] == ["s1"]


# --- end-to-end: the write paths that call the guard (#4389) ---


def _saved_graph(tmp_path: Path, sem: dict) -> tuple[Path, dict]:
    out = tmp_path / "graph.json"
    assert to_json(build_from_json({"nodes": [sem], "edges": []}), {}, str(out), force=True)
    return out, json.loads(out.read_text(encoding="utf-8"))


def _node_data(G) -> dict:
    return {"nodes": [{"id": nid, **attrs} for nid, attrs in G.nodes(data=True)], "links": []}


def test_to_json_writes_after_ghost_dedup(tmp_path):
    sem = _sem("src_models_user_ts_user", "User", "src/models/user.ts")
    out, _ = _saved_graph(tmp_path, sem)
    G = build_from_json({"nodes": [sem, _ast("user_user", "User", "src/models/user.ts")], "edges": []})
    assert list(G.nodes) == ["user_user"]  # ghost id folded into its AST twin
    assert to_json(G, {}, str(out)) is True


def test_to_json_still_refuses_genuine_loss(tmp_path, capsys):
    sem = _sem("src_models_user_ts_user", "User", "src/models/user.ts")
    out, _ = _saved_graph(tmp_path, sem)
    G = build_from_json({"nodes": [_ast("user_account", "Account", "src/models/user.ts")], "edges": []})
    assert to_json(G, {}, str(out)) is False
    assert "src_models_user_ts_user" in capsys.readouterr().err


def test_check_shrink_allows_ghost_dedup(tmp_path):
    sem = _sem("src_models_user_ts_user", "User", "src/models/user.ts")
    _, existing = _saved_graph(tmp_path, sem)
    G = build_from_json({"nodes": [sem, _ast("user_user", "User", "src/models/user.ts")], "edges": []})
    assert _check_shrink(force=False, existing_data=existing, new_data=_node_data(G)) is True
