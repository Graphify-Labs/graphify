"""`import('…')` in plain .ts/.js must produce exactly one edge per fact (#2575).

tree-sitter models ``await import('x')`` as a ``call_expression``, not an
``import_statement``, so the specifier only reaches the graph when the call
walk visits it. Two holes remained: module-scope dynamic imports (no function
body is ever walked for them) and calls inside NESTED named functions (the
function boundary in walk_calls descended into arrow/function-expression
closures but returned at a nested ``function_declaration``). The fixes are a
regex rescue pass for plain JS/TS (mirroring the Svelte/Astro/Vue ones) plus
descending the boundary into nested named declarations — deduped so an
AST-captured dynamic import (already a ``deferred`` ``imports_from`` edge) is
not restated as a second ``dynamic_import`` edge.
"""
from __future__ import annotations

import json
from pathlib import Path

import networkx as nx

from graphify.affected import DEFAULT_AFFECTED_RELATIONS, affected_nodes
from graphify.extract import _file_node_id, extract


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _edges_to(result: dict, target: str, *relations: str) -> list[dict]:
    tgt = _file_node_id(Path(target))
    rels = relations or ("dynamic_import", "imports_from")
    return [e for e in result["edges"]
            if e["target"] == tgt and e["relation"] in rels]


def test_nested_named_function_dynamic_import_edges(tmp_path: Path):
    """#2575: the reported case — `await import()` inside a nested named
    function produced no edge at all (the boundary returned before the call
    walk could see it)."""
    _write(tmp_path / "src/dep.ts", "export const dep = 1\n")
    importer = _write(
        tmp_path / "src/page.ts",
        "export function outer() {\n"
        "    async function inner() {\n"
        "        const { dep } = await import('./dep')\n"
        "        return dep\n"
        "    }\n"
        "    return inner\n"
        "}\n",
    )

    result = extract([tmp_path / "src/dep.ts", importer], root=tmp_path)

    assert _edges_to(result, "src/dep.ts"), "nested dynamic import produced no edge"


def test_doubly_nested_dynamic_import_edges(tmp_path: Path):
    _write(tmp_path / "src/dep.ts", "export const dep = 1\n")
    importer = _write(
        tmp_path / "src/page.ts",
        "export function a() {\n"
        "    function b() {\n"
        "        async function c() {\n"
        "            return await import('./dep')\n"
        "        }\n"
        "        return c\n"
        "    }\n"
        "    return b\n"
        "}\n",
    )

    result = extract([tmp_path / "src/dep.ts", importer], root=tmp_path)

    assert _edges_to(result, "src/dep.ts"), "doubly nested dynamic import lost"


def test_module_scope_dynamic_import_edges(tmp_path: Path):
    """Module scope is outside every walked function body, so only the rescue
    pass can see it."""
    _write(tmp_path / "src/dep.ts", "export const dep = 1\n")
    importer = _write(
        tmp_path / "src/boot.ts",
        "const { dep } = await import('./dep')\n"
        "export const booted = dep\n",
    )

    result = extract([tmp_path / "src/dep.ts", importer], root=tmp_path)

    edges = _edges_to(result, "src/dep.ts")
    assert edges, "module-scope dynamic import produced no edge"
    assert any(e["relation"] == "dynamic_import" for e in edges)


def test_ast_captured_dynamic_import_still_gets_a_file_level_edge(tmp_path: Path):
    """One import() inside a function, two granularities — #2584.

    This test used to assert `len(edges) == 1`, on the reasoning that the rescue would be
    restating what the AST pass had already said. The two edges are not the same statement:
    the AST pass anchors on `caller_nid`, which is the enclosing FUNCTION when the import()
    is written inside one, while the rescue anchors on the FILE. Only the second is a fact
    `affected` can walk, since it traverses file to file.

    Suppressing it cost real recall: on a ~700-file TS repo `affected --depth 3` returned 39
    of 49 truly affected files, precision 1.00, and more depth did not help — a dead end, not
    a depth limit. The reverse walk reached the enclosing function and stopped there, because
    the only edge pointing at it is `contains`, deliberately not in
    DEFAULT_AFFECTED_RELATIONS.

    The dedupe is still right, just keyed wrong: it now matches on (source file, target)
    rather than target alone, so the genuinely redundant case — a module-scope import(),
    where `caller_nid` IS the file node — still collapses to one edge. That case is pinned
    by `test_module_scope_dynamic_import_is_still_one_fact` below.
    """
    _write(tmp_path / "src/dep.ts", "export const dep = 1\n")
    importer = _write(
        tmp_path / "src/page.ts",
        "export async function load() {\n"
        "    const { dep } = await import('./dep')\n"
        "    return dep\n"
        "}\n",
    )

    result = extract([tmp_path / "src/dep.ts", importer], root=tmp_path)

    edges = _edges_to(result, "src/dep.ts")
    page = _file_node_id(Path("src/page.ts"))

    # The precise fact: which function defers the load. `explain` reads this one.
    symbol_level = [e for e in edges if e["source"] != page]
    assert symbol_level, f"lost the call-site edge — got {edges}"
    assert symbol_level[0]["relation"] == "imports_from"
    assert symbol_level[0].get("deferred") is True

    # The traversable fact: this file depends on that module. `affected` reads this one.
    file_level = [e for e in edges if e["source"] == page]
    assert file_level, f"no file-level edge — `affected` cannot traverse this: {edges}"
    assert file_level[0]["relation"] == "dynamic_import"


def test_module_scope_dynamic_import_is_still_one_fact(tmp_path: Path):
    """At module scope `caller_nid` IS the file node, so the rescue is genuinely redundant.

    This is the half of the old dedupe that was always correct, kept as its own test so a
    future change cannot quietly restore double-counting here while fixing #2584.
    """
    _write(tmp_path / "src/dep.ts", "export const dep = 1\n")
    importer = _write(
        tmp_path / "src/boot2.ts",
        "const { dep } = await import('./dep')\nexport const booted = dep\n",
    )

    result = extract([tmp_path / "src/dep.ts", importer], root=tmp_path)

    assert len(_edges_to(result, "src/dep.ts")) == 1


def test_static_import_alongside_dynamic_is_untouched(tmp_path: Path):
    """The rescue pass must not disturb the AST pass it runs beside."""
    _write(tmp_path / "src/a.ts", "export const a = 1\n")
    _write(tmp_path / "src/b.ts", "export const b = 2\n")
    importer = _write(
        tmp_path / "src/main.ts",
        "import { a } from './a'\n"
        "export const later = async () => a + (await import('./b')).b\n",
    )

    result = extract(
        [tmp_path / "src/a.ts", tmp_path / "src/b.ts", importer], root=tmp_path
    )

    a_edges = _edges_to(result, "src/a.ts", "imports_from")
    assert a_edges and not any(e.get("deferred") for e in a_edges)

    # The point of this test is the STATIC edge above: the rescue must leave it alone, and
    # in particular must not mark it deferred. The dynamic side is asserted only for the
    # property that concerns this test — every edge to b.ts is flagged as deferred one way
    # or another, so no arrow into b.ts can be mistaken for a static dependency. Its COUNT
    # is #2584's subject, pinned in test_ast_captured_dynamic_import_still_gets_a_file_level_edge.
    b_edges = _edges_to(result, "src/b.ts")
    assert b_edges
    assert all(e.get("deferred") or e["relation"] == "dynamic_import" for e in b_edges)


def test_tsconfig_aliased_dynamic_import_edges(tmp_path: Path):
    _write(
        tmp_path / "tsconfig.json",
        json.dumps({"compilerOptions": {"baseUrl": ".", "paths": {"@/*": ["./src/*"]}}}),
    )
    _write(tmp_path / "src/agent/runner.ts", "export const run = () => 1\n")
    importer = _write(
        tmp_path / "src/boot.ts",
        "export const runner = await import('@/agent/runner')\n",
    )

    result = extract([tmp_path / "src/agent/runner.ts", importer], root=tmp_path)

    assert _edges_to(result, "src/agent/runner.ts")


def test_template_literal_specifier_without_substitution(tmp_path: Path):
    """A backtick specifier with no `${` is as static as a quoted one — the
    AST path already resolved it, the rescue must too."""
    _write(tmp_path / "src/dep.ts", "export const dep = 1\n")
    importer = _write(
        tmp_path / "src/boot.ts",
        "export const dep = await import(`./dep`)\n",
    )

    result = extract([tmp_path / "src/dep.ts", importer], root=tmp_path)

    assert _edges_to(result, "src/dep.ts")


def test_identifier_ending_in_import_is_not_matched(tmp_path: Path):
    """`fooimport('./x')` is a call to `fooimport`, not a dynamic import."""
    _write(tmp_path / "src/x.ts", "export const x = 1\n")
    importer = _write(
        tmp_path / "src/caller.ts",
        "declare function fooimport(s: string): unknown\n"
        "export const r = fooimport('./x')\n",
    )

    result = extract([tmp_path / "src/x.ts", importer], root=tmp_path)

    assert not _edges_to(result, "src/x.ts")


def test_line_commented_dynamic_import_is_not_matched(tmp_path: Path):
    _write(tmp_path / "src/x.ts", "export const x = 1\n")
    importer = _write(
        tmp_path / "src/caller.ts",
        "// const { x } = await import('./x')\n"
        "export const r = 1\n",
    )

    result = extract([tmp_path / "src/x.ts", importer], root=tmp_path)

    assert not _edges_to(result, "src/x.ts")


def test_nested_named_function_calls_resolve(tmp_path: Path):
    """ordinary calls inside a nested named function attribute to that inner function now that #2653 emits nested nodes."""
    f = _write(
        tmp_path / "src/mod.ts",
        "export function helper() { return 1 }\n"
        "export function outer() {\n"
        "    function inner() { return helper() }\n"
        "    return inner\n"
        "}\n",
    )

    result = extract([f], root=tmp_path)

    by_id = {n["id"]: n["label"].rstrip("()") for n in result["nodes"]}
    calls = {(by_id.get(e["source"]), by_id.get(e["target"]))
             for e in result["edges"] if e["relation"] == "calls"}
    contains = {(by_id.get(e["source"]), by_id.get(e["target"]))
                for e in result["edges"] if e["relation"] == "contains"}
    assert ("inner", "helper") in calls, f"calls found: {calls}"
    assert ("outer", "inner") in contains, f"contains found: {contains}"


def test_dynamic_import_is_traversed_by_affected():
    """Emitting the edge is only half the fix: while `dynamic_import` was
    absent from DEFAULT_AFFECTED_RELATIONS, every dynamic edge stayed invisible
    to blast-radius traversal — including the ones the Svelte/Astro/Vue rescue
    passes had been emitting all along."""
    assert "dynamic_import" in DEFAULT_AFFECTED_RELATIONS

    g = nx.DiGraph()
    g.add_node("importer", label="importer.ts")
    g.add_node("dep", label="dep.ts")
    g.add_edge("importer", "dep", relation="dynamic_import")
    hits = affected_nodes(g, "dep", depth=1)
    assert any(h.node_id == "importer" for h in hits)
