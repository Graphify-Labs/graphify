"""A node label can never break out of the embedded <script> block (#4124).

Node data is serialized to JSON and embedded inside a <script> element. Escaping
only `</` is not enough: an unclosed `<!--` in one label followed by a later
`<script` drives the HTML tokenizer into script-data-double-escaped state, where
the real `</script>` no longer closes the tag — the rest of the page is swallowed
and graph.html renders blank. Escaping every `<` as \\u003c closes all three
breakout sequences (`<!--`, `<script`, `</script`) while labels still render,
since `<` round-trips through JSON.parse.
"""
from __future__ import annotations

import json

import networkx as nx

from graphify.exporters.html import to_html
from graphify.tree_html import emit_html

DANGEROUS = [
    "foo <!-- bar components the panel",   # unclosed comment opener
    "code:vue (<script setup>)",           # script opener
    "end </script> tail",                  # explicit closer
]


def _no_breakout(html: str) -> None:
    # No label-originated raw breakout sequence survives in the document.
    assert "<!--" not in html
    assert "<script setup" not in html
    assert "</script> tail" not in html
    # The escaped form is what carries the label through instead.
    assert "\\u003c" in html


def test_to_html_labels_cannot_break_out_of_script(tmp_path) -> None:
    G = nx.Graph()
    for i, lbl in enumerate(DANGEROUS):
        G.add_node(f"n{i}", label=lbl, file_type="code", source_file=f"f{i}.py")
    G.add_edge("n0", "n1", relation="imports")
    out = tmp_path / "graph.html"
    assert to_html(G, {0: list(G.nodes)}, str(out)) is True
    html = out.read_text(encoding="utf-8")
    _no_breakout(html)
    # Exactly the page's own <script> elements survive — no label minted an extra one.
    assert html.count("<script") == html.count("</script")


def test_tree_html_labels_cannot_break_out_of_script() -> None:
    tree = {
        "name": "root",
        "children": [{"name": lbl, "children": []} for lbl in DANGEROUS],
    }
    html = emit_html(tree, title="t", header="h")
    _no_breakout(html)


def test_clean_labels_round_trip_unchanged(tmp_path) -> None:
    """A label with no `<` is untouched, and a `<`-bearing label still decodes
    back to the original text."""
    G = nx.Graph()
    G.add_node("a", label="plain_label", file_type="code", source_file="a.py")
    G.add_node("b", label="Vector<T>", file_type="code", source_file="b.ts")
    G.add_edge("a", "b", relation="imports")
    out = tmp_path / "graph.html"
    to_html(G, {0: ["a", "b"]}, str(out))
    html = out.read_text(encoding="utf-8")
    assert "plain_label" in html
    # the escaped generic type decodes back to the original
    assert json.loads('"Vector\\u003cT>"') == "Vector<T>"
    assert "Vector\\u003cT>" in html
