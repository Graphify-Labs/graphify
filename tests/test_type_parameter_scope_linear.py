"""The Kotlin, Swift, Scala and C++ type-parameter scope walks stay linear.

Each `_*_type_parameters_in_scope` collected the generic parameters visible
from a type reference by reading `children` of every ancestor. The file root
and a type body have one child per declaration, so every reference cost
O(declarations) and a long file was quadratic: on upstream/v8 4,000 one-field
types took 4-9 s per file. Only the node kinds whose children can hold a
type-parameter list are read now (from each grammar's node-types.json), plus
ERROR, where a misparse can leave one; the collected names are unchanged.
"""
from __future__ import annotations

import gc
import importlib
import time

import pytest

import graphify.extractors.engine as engine

CASES = {
    "kotlin": ("tree_sitter_kotlin", "_kotlin_type_parameters_in_scope",
               lambda i: f"fun f{i}(a: C{i}) {{}}\n"),
    "swift": ("tree_sitter_swift", "_swift_type_parameters_in_scope",
              lambda i: f"struct S{i} {{ var a: S{i}? }}\n"),
    "scala": ("tree_sitter_scala", "_scala_type_parameters_in_scope",
              lambda i: f"class C{i} {{ val a: C{i} = null }}\n"),
    "cpp": ("tree_sitter_cpp", "_cpp_type_parameters_in_scope",
            lambda i: f"struct S{i} {{ S{i}* a; }};\n"),
}


@pytest.mark.parametrize("case", sorted(CASES))
def test_the_scope_walk_scales_linearly_with_sibling_declarations(case: str):
    """Doubling the declarations must not roughly quadruple the walk's time.

    Times the walk alone, from every type name, in CPU time with GC off
    and the best of three runs, as test_ts_normalizer_scales_linearly_on_large_files
    does: linear work doubles (~2x), quadratic work quadruples (~4x).
    """
    module, fn_name, line = CASES[case]
    if importlib.util.find_spec(module) is None:
        pytest.skip(f"{module} not installed")
    import tree_sitter

    grammar = importlib.import_module(module)
    parser = tree_sitter.Parser(tree_sitter.Language(grammar.language()))
    walk = getattr(engine, fn_name)

    def refs(n: int) -> tuple[bytes, list]:
        source = "".join(line(i) for i in range(n)).encode()
        out, stack = [], [parser.parse(source).root_node]
        while stack:
            node = stack.pop()
            stack.extend(node.children)
            # Kotlin names a type with an `identifier` inside `user_type`.
            if node.type == "type_identifier" or (
                    node.type == "identifier" and node.parent.type == "user_type"):
                out.append(node)
        return source, out

    def timed(source: bytes, nodes: list) -> float:
        gc_was_enabled = gc.isenabled()
        gc.disable()
        try:
            start = time.process_time()
            for node in nodes:
                walk(node, source)
            return time.process_time() - start
        finally:
            if gc_was_enabled:
                gc.enable()

    small_input, large_input = refs(4000), refs(8000)
    timed(*refs(200))
    small = min(timed(*small_input) for _ in range(3))
    large = min(timed(*large_input) for _ in range(3))
    assert large < small * 3.5, (
        f"scaling looks super-linear: {small:.4f}s -> {large:.4f}s "
        f"({large / small:.1f}x for 2x input)"
    )


def test_type_parameters_left_under_an_error_node_are_still_in_scope():
    """An unclosed generic type misparses, and its `type_parameters` end up as
    a child of an ERROR node; `Element` must stay a local name there too."""
    pytest.importorskip("tree_sitter_swift")
    import tree_sitter
    import tree_sitter_swift

    parser = tree_sitter.Parser(tree_sitter.Language(tree_sitter_swift.language()))
    source = b"public struct Box<Element>: P {\n    public func get() -> Observable<Element> {\n"
    root = parser.parse(source).root_node
    holder = next(c for c in root.children if any(g.type == "type_parameters" for g in c.children))
    assert holder.type == "ERROR"
    uses = [n for n in _descendants(root) if n.type == "type_identifier"
            and n.text == b"Element" and n.start_point[0] == 1]
    assert len(uses) == 1
    assert "Element" in engine._swift_type_parameters_in_scope(uses[0], source)


def _descendants(node):
    stack = [node]
    while stack:
        node = stack.pop()
        yield node
        stack.extend(node.children)
