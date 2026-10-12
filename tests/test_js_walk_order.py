"""_walk_js_tree: pre-order over the whole tree, bounded by its start node.

The JS/TS symbol-fact passes rely on walk order for fact order, and the
call-use pass walks function bodies as subtrees. Both must hold for the
TreeCursor walk exactly as they did for the ``.children`` stack walk.
"""

from graphify.extractors.resolution import _parse_js_tree, _walk_js_tree

SOURCE = """\
import { a, b as c } from "./dep.js";
export const x = a, y = c;
export class K extends Base {
  m() { return helper(a, () => b()); }
}
function outer() {
  const inner = () => { call1(); if (x) { call2(); } };
  return inner;
}
export { outer as default };
"""


def _span(node):
    return (node.type, node.start_byte, node.end_byte)


def _reference_preorder(node):
    out = [node]
    for child in node.children:
        out.extend(_reference_preorder(child))
    return out


def test_walk_is_children_preorder(tmp_path):
    path = tmp_path / "m.ts"
    path.write_text(SOURCE, encoding="utf-8")
    parsed = _parse_js_tree(path)
    assert parsed is not None
    _source, root = parsed
    assert [_span(n) for n in _walk_js_tree(root)] == [
        _span(n) for n in _reference_preorder(root)
    ]


def test_walk_from_any_node_stays_inside_its_subtree(tmp_path):
    """Start a walk at every node, including ones with later siblings, as
    _js_named_specifiers does with an import_statement or export_clause."""
    path = tmp_path / "m.ts"
    path.write_text(SOURCE, encoding="utf-8")
    parsed = _parse_js_tree(path)
    assert parsed is not None
    _source, root = parsed
    starts = _reference_preorder(root)
    assert any(n.next_sibling is not None and n.child_count for n in starts)
    for start in starts:
        assert [_span(n) for n in _walk_js_tree(start)] == [
            _span(n) for n in _reference_preorder(start)
        ]
