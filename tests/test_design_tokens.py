from __future__ import annotations

from pathlib import Path

import networkx as nx

from graphify.affected import DEFAULT_AFFECTED_RELATIONS, affected_nodes
from graphify.extract import extract, _file_node_id


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_cross_file_var_reference_binds_to_its_definition(tmp_path: Path):
    """A stylesheet's own `var(--brand)` reference resolved locally, but a
    reference from a DIFFERENT file had no definition node in scope and was
    left pointing at the raw token name instead of the file that declares it."""
    tokens = _write(tmp_path / "tokens.css", ":root {\n  --brand: #123456;\n}\n")
    user = _write(tmp_path / "button.css", ".button {\n  color: var(--brand);\n}\n")

    result = extract([tokens, user], cache_root=tmp_path)

    token_node = next(n for n in result["nodes"] if n["label"] == "--brand")
    uses_token_edges = {
        (e["source"], e["target"]) for e in result["edges"] if e["relation"] == "uses_token"
    }
    assert (_file_node_id(Path("button.css")), token_node["id"]) in uses_token_edges


def test_uses_token_is_traversed_by_affected():
    """Emitting the edge is only half the fix: while `uses_token` was absent
    from DEFAULT_AFFECTED_RELATIONS, a design-token change could not find the
    files that consume it via blast-radius traversal."""
    assert "uses_token" in DEFAULT_AFFECTED_RELATIONS

    g = nx.DiGraph()
    g.add_node("button.css", label="button.css")
    g.add_node("--brand", label="--brand")
    g.add_edge("button.css", "--brand", relation="uses_token")
    hits = affected_nodes(g, "--brand", depth=1)
    assert any(h.node_id == "button.css" for h in hits)
