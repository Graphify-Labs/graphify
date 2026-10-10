from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from graphify.build import build_from_json
from graphify.export import to_json
from graphify.extract import _file_node_id, _file_stem, _make_id, extract


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _extract_for(paths: list[Path], root: Path):
    return extract(paths, cache_root=root)


def _unresolved_reexport_id(path: Path) -> str:
    identity = path.as_posix()
    salt = hashlib.sha1(identity.encode("utf-8")).hexdigest()[:12]  # nosec
    return _make_id("unresolved_reexport", _file_stem(path), salt)


def _has_edge(result: dict, source: str, target: str, relation: str = "imports_from") -> bool:
    expected = (_file_node_id(Path(source)), _file_node_id(Path(target)), relation)
    actual = {
        (edge["source"], edge["target"], edge["relation"])
        for edge in result["edges"]
    }
    return expected in actual


def _has_symbol_edge(
    result: dict,
    source: str,
    target_file: str,
    symbol: str,
    relation: str = "imports",
) -> bool:
    expected = (_file_node_id(Path(source)), _make_id(_file_stem(Path(target_file)), symbol), relation)
    actual = {
        (edge["source"], edge["target"], edge["relation"])
        for edge in result["edges"]
    }
    return expected in actual


def _has_symbol_to_symbol_edge(
    result: dict,
    source_file: str,
    source_symbol: str,
    target_file: str,
    target_symbol: str,
    relation: str,
) -> bool:
    expected = (
        _make_id(_file_stem(Path(source_file)), source_symbol),
        _make_id(_file_stem(Path(target_file)), target_symbol),
        relation,
    )
    actual = {
        (edge["source"], edge["target"], edge["relation"])
        for edge in result["edges"]
    }
    return expected in actual


def _has_no_symbol_to_symbol_edge(
    result: dict,
    source_file: str,
    source_symbol: str,
    target_file: str,
    target_symbol: str,
    relation: str,
) -> bool:
    return not _has_symbol_to_symbol_edge(
        result,
        source_file,
        source_symbol,
        target_file,
        target_symbol,
        relation,
    )


def test_ts_bare_relative_import_resolves_existing_ts_file(tmp_path: Path):
    target = _write(tmp_path / "src/lib/foo.ts", "export const foo = 1\n")
    importer = _write(
        tmp_path / "src/lib/page.ts",
        "import { foo } from './foo'\nconsole.log(foo)\n",
    )

    result = _extract_for([target, importer], tmp_path)

    assert _has_edge(result, "src/lib/page.ts", "src/lib/foo.ts")


def test_ts_directory_import_resolves_index_ts(tmp_path: Path):
    target = _write(tmp_path / "src/lib/server/queue/index.ts", "export const queue = 1\n")
    importer = _write(
        tmp_path / "src/lib/page.ts",
        "import { queue } from './server/queue'\nconsole.log(queue)\n",
    )

    result = _extract_for([target, importer], tmp_path)

    assert _has_edge(result, "src/lib/page.ts", "src/lib/server/queue/index.ts")


@pytest.mark.parametrize(
    ("specifier", "target_path"),
    [
        ("./missing", None),
        ("./directory", "directory/index.d.ts"),
        ("./type", "type.d.ts"),
    ],
)
@pytest.mark.parametrize(
    "statement",
    [
        "export * from {specifier!r}\n",
        "export * as values from {specifier!r}\n",
        "export {{ Value }} from {specifier!r}\n",
    ],
)
def test_unresolved_ts_reexport_ids_are_portable_across_checkout_paths(
    tmp_path: Path,
    specifier: str,
    target_path: str | None,
    statement: str,
):
    def build(checkout: Path) -> dict:
        root = tmp_path / checkout
        if target_path is not None:
            _write(root / target_path, "export interface Value { id: string }\n")
        barrel = _write(root / "index.ts", statement.format(specifier=specifier))

        result = _extract_for([barrel], root)
        projection = {
            "nodes": result["nodes"],
            "edges": result["edges"],
        }
        serialized = json.dumps(projection, sort_keys=True)
        assert str(root) not in serialized
        assert _make_id(str(root)) not in serialized

        expected_target = _unresolved_reexport_id(Path(specifier.removeprefix("./")))
        reexport_targets = {
            edge["target"]
            for edge in result["edges"]
            if edge["relation"] == "re_exports"
        }
        assert expected_target in reexport_targets
        return projection

    first = build(Path("checkout-a"))
    second = build(Path("nested/checkout-b"))

    assert first == second


def test_unresolved_ts_reexport_does_not_bind_a_colliding_context_node(tmp_path: Path):
    root = tmp_path / "repo"
    barrel = _write(root / "index.ts", "export * from './a-b/x'\n")
    context_node = {
        "id": _file_node_id(Path("a/b/x.ts")),
        "label": "x.ts",
        "file_type": "code",
        "source_file": "a/b/x.ts",
        "source_location": "L1",
        "_origin": "ast",
    }

    result = extract(
        [barrel],
        cache_root=root,
        root=root,
        parallel=False,
        resolution_context_nodes=[context_node],
    )

    target = next(
        edge["target"]
        for edge in result["edges"]
        if edge["relation"] == "re_exports"
    )
    assert target == _unresolved_reexport_id(Path("a-b/x"))
    assert target != context_node["id"]


def test_unresolved_ts_reexport_external_stub_is_portable(tmp_path: Path):
    root = tmp_path / "checkout"
    barrel = _write(root / "index.ts", "export * from './missing'\n")
    result = _extract_for([barrel], root)
    graph = build_from_json(result, root=root)
    output = tmp_path / "graph.json"

    assert to_json(graph, {}, str(output), force=True)

    payload = json.loads(output.read_text(encoding="utf-8"))
    expected_id = _unresolved_reexport_id(Path("missing"))
    stub = next(node for node in payload["nodes"] if node["id"] == expected_id)
    assert stub["external"] is True
    assert stub["label"] == expected_id
    assert stub["norm_label"] == expected_id
    assert any(edge["target"] == expected_id for edge in payload["links"])
    serialized = json.dumps(payload, sort_keys=True)
    assert str(root) not in serialized
    assert _make_id(str(root)) not in serialized


def test_ts_named_reexport_alias_from_index_resolves_imported_symbol_to_origin(tmp_path: Path):
    target = _write(tmp_path / "src/lib/foo.ts", "export class InternalFoo { id = '' }\n")
    barrel = _write(
        tmp_path / "src/lib/index.ts",
        "export { InternalFoo as Foo } from './foo'\n",
    )
    consumer = _write(
        tmp_path / "src/routes/page.ts",
        "import type { Foo } from '../lib/index'\nexport type X = Foo\n",
    )

    result = _extract_for([target, barrel, consumer], tmp_path)

    assert _has_edge(result, "src/lib/index.ts", "src/lib/foo.ts", "re_exports")
    assert _has_symbol_edge(
        result,
        "src/routes/page.ts",
        "src/lib/foo.ts",
        "InternalFoo",
    )


@pytest.mark.parametrize("reverse", [False, True])
def test_re_export_survives_for_both_files_whose_ids_collide(tmp_path: Path, reverse: bool):
    """`a-b/x.ts` and `a/b/x.ts` both normalize to `a_b_x`. Each re-exports the
    same module, so each must keep its own re_exports edge whatever the order the
    files are processed in; the second one used to be deduped as a copy of the
    first before the colliding ids were split."""
    util = _write(tmp_path / "lib/util.ts", "export function helper() { return 1; }\n")
    dashed = _write(tmp_path / "a-b/x.ts", "export * from '../lib/util'\n")
    nested = _write(tmp_path / "a/b/x.ts", "export * from '../../lib/util'\n")
    paths = [util, dashed, nested]

    result = _extract_for(list(reversed(paths)) if reverse else paths, tmp_path)

    by_id = {node["id"]: node for node in result["nodes"]}
    re_exporters = sorted(
        Path(by_id[edge["source"]]["source_file"]).as_posix()
        for edge in result["edges"]
        if edge["relation"] == "re_exports" and edge["target"] == _file_node_id(Path("lib/util.ts"))
    )
    assert re_exporters == ["a-b/x.ts", "a/b/x.ts"]


def test_ts_export_star_from_index_resolves_imported_symbol_to_origin(tmp_path: Path):
    target = _write(tmp_path / "src/lib/foo.ts", "export class Foo { id = '' }\n")
    barrel = _write(tmp_path / "src/lib/index.ts", "export * from './foo'\n")
    consumer = _write(
        tmp_path / "src/routes/page.ts",
        "import type { Foo } from '../lib/index'\nexport type X = Foo\n",
    )

    result = _extract_for([target, barrel, consumer], tmp_path)

    assert _has_edge(result, "src/lib/index.ts", "src/lib/foo.ts", "re_exports")
    assert _has_symbol_edge(result, "src/routes/page.ts", "src/lib/foo.ts", "Foo")


def test_ts_export_star_skips_same_named_interface_method_and_binds_the_function(tmp_path: Path):
    # #3436: `export *` can only forward top-level bindings. When the first
    # star target declares an interface with a METHOD of the same bare name as a
    # function exported by a later star target, the imported name must bind to
    # the function, and the call must land on it -- not on the method node.
    types = _write(
        tmp_path / "packages/domain/src/types.ts",
        "export interface Rule {\n  code: string\n  evaluate(ctx: number): string | null\n}\n",
    )
    engine = _write(
        tmp_path / "packages/domain/src/engine.ts",
        "import type { Rule } from './types.js'\n\n"
        "export function evaluate(rules: readonly Rule[], ctx: number): string[] {\n"
        "  return rules.map((rule) => rule.evaluate(ctx)).filter((f) => f !== null)\n"
        "}\n",
    )
    barrel = _write(
        tmp_path / "packages/domain/src/index.ts",
        "export * from './types.js'\nexport * from './engine.js'\n",
    )
    consumer = _write(
        tmp_path / "packages/api/src/cache.ts",
        "import { evaluate } from '../../domain/src/index.js'\n"
        "import type { Rule } from '../../domain/src/index.js'\n\n"
        "export function warm(rules: readonly Rule[]): string[] {\n"
        "  return evaluate(rules, 1)\n"
        "}\n",
    )

    result = _extract_for([types, engine, barrel, consumer], tmp_path)

    assert _has_symbol_edge(
        result, "packages/api/src/cache.ts", "packages/domain/src/engine.ts", "evaluate"
    )
    assert _has_symbol_to_symbol_edge(
        result,
        "packages/api/src/cache.ts",
        "warm",
        "packages/domain/src/engine.ts",
        "evaluate",
        "calls",
    )
    assert _has_no_symbol_to_symbol_edge(
        result,
        "packages/api/src/cache.ts",
        "warm",
        "packages/domain/src/types.ts",
        "rule_evaluate",
        "calls",
    )


@pytest.mark.parametrize("suffix", ["ts", "js"])
def test_js_namespace_reexport_import_targets_real_binding(
    tmp_path: Path,
    monkeypatch,
    suffix: str,
):
    monkeypatch.chdir(tmp_path)
    target = _write(Path(f"src/lib/foo.{suffix}"), "export class Foo { id = '' }\n")
    barrel = _write(Path(f"src/lib/index.{suffix}"), "export * as ns from './foo'\n")
    consumer = _write(
        Path(f"src/routes/page.{suffix}"),
        "import { ns } from '../lib/index'\nexport const use = () => ns.Foo\n",
    )

    result = _extract_for([target, barrel, consumer], Path("."))

    namespace_id = _make_id(_file_stem(Path(f"src/lib/index.{suffix}")), "ns")
    node_ids = {node["id"] for node in result["nodes"]}
    assert namespace_id in node_ids
    assert _has_symbol_edge(
        result,
        f"src/routes/page.{suffix}",
        f"src/lib/index.{suffix}",
        "ns",
    )
    assert _has_edge(
        result,
        f"src/lib/index.{suffix}",
        f"src/lib/foo.{suffix}",
        "re_exports",
    )
    assert (
        _file_node_id(Path(f"src/lib/index.{suffix}")),
        namespace_id,
        "contains",
    ) in {
        (edge["source"], edge["target"], edge["relation"])
        for edge in result["edges"]
    }
    assert not [
        edge
        for edge in result["edges"]
        if edge["source"] not in node_ids or edge["target"] not in node_ids
    ]


def test_ts_reexport_cycle_resolves_symbol_from_non_cycle_branch(tmp_path: Path):
    target = _write(tmp_path / "src/lib/foo.ts", "export class Foo { id = '' }\n")
    first = _write(
        tmp_path / "src/lib/first.ts",
        "export * from './second'\nexport * from './foo'\n",
    )
    second = _write(tmp_path / "src/lib/second.ts", "export * from './first'\n")
    consumer = _write(
        tmp_path / "src/routes/page.ts",
        "import type { Foo } from '../lib/first'\nexport type X = Foo\n",
    )

    result = _extract_for([target, first, second, consumer], tmp_path)

    assert _has_symbol_edge(result, "src/routes/page.ts", "src/lib/foo.ts", "Foo")


def test_ts_reexport_chain_beyond_sixteen_hops_resolves_origin(tmp_path: Path):
    target = _write(tmp_path / "src/lib/foo.ts", "export class Foo { id = '' }\n")
    barrels: list[Path] = []
    previous = "foo"
    for index in range(20):
        barrel = _write(
            tmp_path / f"src/lib/barrel_{index}.ts",
            f"export * from './{previous}'\n",
        )
        barrels.append(barrel)
        previous = f"barrel_{index}"
    consumer = _write(
        tmp_path / "src/routes/page.ts",
        "import type { Foo } from '../lib/barrel_19'\nexport type X = Foo\n",
    )

    result = extract([target, *barrels, consumer], cache_root=tmp_path, parallel=False)

    assert _has_symbol_edge(result, "src/routes/page.ts", "src/lib/foo.ts", "Foo")


def test_ts_import_alias_then_reexport_alias_resolves_imported_symbol_to_origin(tmp_path: Path):
    target = _write(tmp_path / "src/lib/foo.ts", "export class Foo { id = '' }\n")
    barrel = _write(
        tmp_path / "src/lib/index.ts",
        "import type { Foo as LocalFoo } from './foo'\nexport type { LocalFoo as PublicFoo }\n",
    )
    consumer = _write(
        tmp_path / "src/routes/page.ts",
        "import type { PublicFoo } from '../lib/index'\nexport type X = PublicFoo\n",
    )

    result = _extract_for([target, barrel, consumer], tmp_path)

    assert _has_edge(result, "src/lib/index.ts", "src/lib/foo.ts", "re_exports")
    assert _has_symbol_edge(result, "src/routes/page.ts", "src/lib/foo.ts", "Foo")


def test_ts_import_from_index_then_exported_type_alias_resolves_to_origin_symbol(tmp_path: Path):
    target = _write(tmp_path / "src/lib/foo.ts", "export class Foo { id = '' }\n")
    barrel = _write(tmp_path / "src/lib/index.ts", "export { Foo } from './foo'\n")
    consumer = _write(
        tmp_path / "src/routes/page.ts",
        "import type { Foo } from '../lib/index'\nexport type X = Foo\n",
    )

    result = _extract_for([target, barrel, consumer], tmp_path)

    assert _has_edge(result, "src/lib/index.ts", "src/lib/foo.ts", "re_exports")
    assert _has_symbol_edge(result, "src/routes/page.ts", "src/lib/foo.ts", "Foo")


def test_ts_reexported_interface_resolves_imported_symbol_to_origin(tmp_path: Path):
    target = _write(tmp_path / "src/lib/foo.ts", "export interface Foo { id: string }\n")
    barrel = _write(tmp_path / "src/lib/index.ts", "export type { Foo } from './foo'\n")
    consumer = _write(
        tmp_path / "src/routes/page.ts",
        "import type { Foo } from '../lib/index'\nexport type X = Foo\n",
    )

    result = _extract_for([target, barrel, consumer], tmp_path)

    assert _has_edge(result, "src/lib/index.ts", "src/lib/foo.ts", "re_exports")
    assert _has_symbol_edge(result, "src/routes/page.ts", "src/lib/foo.ts", "Foo")


def test_ts_reexported_type_alias_resolves_imported_symbol_to_origin(tmp_path: Path):
    target = _write(tmp_path / "src/lib/foo.ts", "export type Foo = { id: string }\n")
    barrel = _write(tmp_path / "src/lib/index.ts", "export type { Foo } from './foo'\n")
    consumer = _write(
        tmp_path / "src/routes/page.ts",
        "import type { Foo } from '../lib/index'\nexport type X = Foo\n",
    )

    result = _extract_for([target, barrel, consumer], tmp_path)

    assert _has_edge(result, "src/lib/index.ts", "src/lib/foo.ts", "re_exports")
    assert _has_symbol_edge(result, "src/routes/page.ts", "src/lib/foo.ts", "Foo")


def test_ts_reexported_abstract_class_resolves_imported_symbol_to_origin(tmp_path: Path):
    target = _write(tmp_path / "src/lib/foo.ts", "export abstract class Foo { abstract run(): void }\n")
    barrel = _write(tmp_path / "src/lib/index.ts", "export { Foo } from './foo'\n")
    consumer = _write(
        tmp_path / "src/routes/page.ts",
        "import { Foo } from '../lib/index'\nclass Impl extends Foo { run() {} }\n",
    )

    result = _extract_for([target, barrel, consumer], tmp_path)

    assert _has_edge(result, "src/lib/index.ts", "src/lib/foo.ts", "re_exports")
    assert _has_symbol_edge(result, "src/routes/page.ts", "src/lib/foo.ts", "Foo")


def test_ts_const_alias_reexport_resolves_imported_symbol_to_origin(tmp_path: Path):
    target = _write(tmp_path / "src/lib/foo.ts", "export class Foo { id = '' }\n")
    barrel = _write(
        tmp_path / "src/lib/index.ts",
        "import { Foo } from './foo'\nexport const PublicFoo = Foo\n",
    )
    consumer = _write(
        tmp_path / "src/routes/page.ts",
        "import { PublicFoo } from '../lib/index'\nnew PublicFoo()\n",
    )

    result = _extract_for([target, barrel, consumer], tmp_path)

    assert _has_edge(result, "src/lib/index.ts", "src/lib/foo.ts", "re_exports")
    assert _has_symbol_edge(result, "src/routes/page.ts", "src/lib/foo.ts", "Foo")


def test_ts_local_const_alias_then_named_reexport_resolves_imported_symbol_to_origin(tmp_path: Path):
    target = _write(tmp_path / "src/lib/foo.ts", "export function makeFoo() { return {} }\n")
    barrel = _write(
        tmp_path / "src/lib/index.ts",
        "import { makeFoo } from './foo'\nconst PublicFactory = makeFoo\nexport { PublicFactory }\n",
    )
    consumer = _write(
        tmp_path / "src/routes/page.ts",
        "import { PublicFactory } from '../lib/index'\nPublicFactory()\n",
    )

    result = _extract_for([target, barrel, consumer], tmp_path)

    assert _has_edge(result, "src/lib/index.ts", "src/lib/foo.ts", "re_exports")
    assert _has_symbol_edge(result, "src/routes/page.ts", "src/lib/foo.ts", "makeFoo")


def test_ts_arrow_function_call_through_barrel_targets_origin_symbol(tmp_path: Path):
    target = _write(tmp_path / "src/lib/foo.ts", "export function Foo() { return 1 }\n")
    unrelated = _write(tmp_path / "src/other/foo.ts", "export function Foo() { return 2 }\n")
    barrel = _write(tmp_path / "src/lib/index.ts", "export { Foo } from './foo'\n")
    consumer = _write(
        tmp_path / "src/routes/page.ts",
        "import { Foo } from '../lib/index'\nconst X = () => Foo()\n",
    )

    result = _extract_for([target, unrelated, barrel, consumer], tmp_path)

    assert _has_symbol_to_symbol_edge(
        result,
        "src/routes/page.ts",
        "X",
        "src/lib/foo.ts",
        "Foo",
        "calls",
    )


def test_ts_import_alias_does_not_affect_same_named_local_symbol_when_unused(tmp_path: Path):
    target = _write(tmp_path / "src/lib/foo.ts", "export function Foo() { return 1 }\n")
    barrel = _write(tmp_path / "src/lib/index.ts", "export { Foo } from './foo'\n")
    consumer = _write(
        tmp_path / "src/routes/page.ts",
        "import { Foo as Bar } from '../lib/index'\nconst Foo = () => {}\n",
    )

    result = _extract_for([target, barrel, consumer], tmp_path)

    assert _has_no_symbol_to_symbol_edge(
        result,
        "src/routes/page.ts",
        "Foo",
        "src/lib/foo.ts",
        "Foo",
        "calls",
    )


def test_ts_import_alias_call_from_same_named_local_symbol_targets_origin(tmp_path: Path):
    target = _write(tmp_path / "src/lib/foo.ts", "export function Foo() { return 1 }\n")
    barrel = _write(tmp_path / "src/lib/index.ts", "export { Foo } from './foo'\n")
    consumer = _write(
        tmp_path / "src/routes/page.ts",
        "import { Foo as Bar } from '../lib/index'\nconst Foo = () => Bar()\n",
    )

    result = _extract_for([target, barrel, consumer], tmp_path)

    assert _has_symbol_to_symbol_edge(
        result,
        "src/routes/page.ts",
        "Foo",
        "src/lib/foo.ts",
        "Foo",
        "calls",
    )


def test_svelte_rune_import_resolves_svelte_ts_file(tmp_path: Path):
    target = _write(tmp_path / "src/lib/hooks/is-mobile.svelte.ts", "export const isMobile = true\n")
    importer = _write(
        tmp_path / "src/routes/page.ts",
        "import { isMobile } from '../lib/hooks/is-mobile.svelte'\nconsole.log(isMobile)\n",
    )

    result = _extract_for([target, importer], tmp_path)

    assert _has_edge(result, "src/routes/page.ts", "src/lib/hooks/is-mobile.svelte.ts")


def test_ts_dynamic_import_does_not_create_phantom_cycle(tmp_path: Path):
    # A deferred `import('./x')` is not a static import: it must be emitted as a
    # `dynamic_import` edge (like the Svelte/Astro/Vue emitters), not
    # `imports_from`. Otherwise two files that reference each other via one static
    # import + one dynamic import are reported as a phantom circular dependency.
    # Regression test for #1241.
    import networkx as nx

    from graphify.analyze import find_import_cycles

    actions = _write(
        tmp_path / "actions.ts",
        'export function doThing() {}\n'
        'export async function lazy() {\n'
        '  const m = await import("./modal");\n'
        '  return m.openModal();\n'
        '}\n',
    )
    modal = _write(
        tmp_path / "modal.ts",
        'import { doThing } from "./actions";\n'
        'export function openModal() { doThing(); }\n',
    )

    result = _extract_for([actions, modal], tmp_path)

    # The deferred import() edge stays in the graph as an `imports_from` edge
    # marked `deferred` (the dependency remains visible); the real static import
    # (modal.ts -> actions.ts) is unaffected.
    deferred = [edge for edge in result["edges"] if edge.get("deferred")]
    assert deferred and all(edge["relation"] == "imports_from" for edge in deferred)
    assert _has_edge(result, "modal.ts", "actions.ts", "imports_from")

    # End to end: the deferred import must not manufacture a file cycle.
    graph = nx.DiGraph()
    for node in result["nodes"]:
        graph.add_node(node["id"], **{k: v for k, v in node.items() if k != "id"})
    for edge in result["edges"]:
        graph.add_edge(
            edge["source"],
            edge["target"],
            **{k: v for k, v in edge.items() if k not in ("source", "target")},
        )
    assert find_import_cycles(graph) == []


def test_tsconfig_alias_import_resolves_existing_ts_file(tmp_path: Path):
    _write(
        tmp_path / "tsconfig.json",
        json.dumps({"compilerOptions": {"baseUrl": ".", "paths": {"$lib/*": ["src/lib/*"]}}}),
    )
    target = _write(tmp_path / "src/lib/types/type-helpers.ts", "export type Helper = string\n")
    importer = _write(
        tmp_path / "src/routes/page.ts",
        "import type { Helper } from '$lib/types/type-helpers'\nconst value: Helper = 'x'\n",
    )

    result = _extract_for([target, importer], tmp_path)

    assert _has_edge(result, "src/routes/page.ts", "src/lib/types/type-helpers.ts")


def test_tsconfig_alias_with_subdirectory_baseurl_resolves_existing_ts_file(tmp_path: Path):
    # `paths` are resolved relative to `baseUrl`, which is commonly a
    # subdirectory in monorepo / NestJS layouts (baseUrl "./src").
    # Regression: baseUrl was ignored, so "@services/*": ["services/*"] with
    # baseUrl "./src" resolved to <root>/services instead of <root>/src/services,
    # and every aliased import edge was silently dropped.
    _write(
        tmp_path / "tsconfig.json",
        json.dumps({"compilerOptions": {"baseUrl": "./src", "paths": {"@services/*": ["services/*"]}}}),
    )
    target = _write(tmp_path / "src/services/foo/index.ts", "export class Foo { id = '' }\n")
    importer = _write(
        tmp_path / "src/routes/page.ts",
        "import { Foo } from '@services/foo'\nnew Foo()\n",
    )

    result = _extract_for([target, importer], tmp_path)

    assert _has_edge(result, "src/routes/page.ts", "src/services/foo/index.ts")


def test_tsconfig_array_extends_alias_resolves_existing_ts_file(tmp_path: Path):
    # TypeScript 5.0 allows `extends` as an array; later entries override
    # earlier ones. The `paths` alias is inherited from the second parent.
    # Regression: an array `extends` previously raised
    # `AttributeError: 'list' object has no attribute 'startswith'`, which
    # _safe_extract turned into a skip of every file using the alias.
    _write(tmp_path / "tsconfig.base.json", json.dumps({"compilerOptions": {"strict": True}}))
    _write(
        tmp_path / "tsconfig.paths.json",
        json.dumps({"compilerOptions": {"baseUrl": ".", "paths": {"$lib/*": ["src/lib/*"]}}}),
    )
    _write(
        tmp_path / "tsconfig.json",
        json.dumps({"extends": ["./tsconfig.base.json", "./tsconfig.paths.json"]}),
    )
    target = _write(tmp_path / "src/lib/types/type-helpers.ts", "export type Helper = string\n")
    importer = _write(
        tmp_path / "src/routes/page.ts",
        "import type { Helper } from '$lib/types/type-helpers'\nconst value: Helper = 'x'\n",
    )

    result = _extract_for([target, importer], tmp_path)

    assert _has_edge(result, "src/routes/page.ts", "src/lib/types/type-helpers.ts")


def test_default_import_resolves_to_default_exported_class(tmp_path: Path):
    target = _write(tmp_path / "src/lib/foo.ts", "export default class Foo { id = '' }\n")
    importer = _write(
        tmp_path / "src/routes/page.ts",
        "import Foo from '../lib/foo'\nnew Foo()\n",
    )

    result = _extract_for([target, importer], tmp_path)

    assert _has_symbol_edge(result, "src/routes/page.ts", "src/lib/foo.ts", "Foo")


def test_default_import_with_renamed_binding_resolves_to_origin(tmp_path: Path):
    # The local binding may differ from the exported symbol name; the edge must
    # still target the origin symbol, not the local binding.
    target = _write(tmp_path / "src/lib/foo.ts", "export default class Foo { id = '' }\n")
    importer = _write(
        tmp_path / "src/routes/page.ts",
        "import Renamed from '../lib/foo'\nnew Renamed()\n",
    )

    result = _extract_for([target, importer], tmp_path)

    assert _has_symbol_edge(result, "src/routes/page.ts", "src/lib/foo.ts", "Foo")


def test_export_default_identifier_resolves_default_import(tmp_path: Path):
    target = _write(tmp_path / "src/lib/foo.ts", "class Foo { id = '' }\nexport default Foo\n")
    importer = _write(
        tmp_path / "src/routes/page.ts",
        "import Foo from '../lib/foo'\nnew Foo()\n",
    )

    result = _extract_for([target, importer], tmp_path)

    assert _has_symbol_edge(result, "src/routes/page.ts", "src/lib/foo.ts", "Foo")


def test_default_import_call_resolves_to_default_exported_function(tmp_path: Path):
    # Binding a default import also lets calls through it resolve to the origin.
    # The local binding (`mk`) deliberately differs from the exported name so the
    # edge can only come from the default-import alias, not global-label matching.
    target = _write(tmp_path / "src/lib/foo.ts", "export default function makeFoo() { return 1 }\n")
    importer = _write(
        tmp_path / "src/routes/page.ts",
        "import mk from '../lib/foo'\nconst X = () => mk()\n",
    )

    result = _extract_for([target, importer], tmp_path)

    assert _has_symbol_to_symbol_edge(
        result, "src/routes/page.ts", "X", "src/lib/foo.ts", "makeFoo", "calls"
    )


def test_pnpm_workspace_package_import_resolves_package_entry(tmp_path: Path):
    _write(
        tmp_path / "pnpm-workspace.yaml",
        "packages:\n  - 'apps/*'\n  - 'packages/*'\n",
    )
    _write(
        tmp_path / "packages/types/package.json",
        json.dumps({"name": "@workspace/types", "exports": "./src/index.ts"}),
    )
    target = _write(
        tmp_path / "packages/types/src/index.ts",
        "export interface SomeDto { id: string }\n",
    )
    importer = _write(
        tmp_path / "apps/web/src/page.ts",
        "import type { SomeDto } from '@workspace/types'\nconst dto: SomeDto = { id: '1' }\n",
    )

    result = _extract_for([target, importer], tmp_path)

    assert _has_edge(result, "apps/web/src/page.ts", "packages/types/src/index.ts")


def test_npm_workspace_package_import_resolves_package_entry(tmp_path: Path):
    _write(
        tmp_path / "package.json",
        json.dumps({"workspaces": ["apps/*", "packages/*"]}),
    )
    _write(
        tmp_path / "packages/types/package.json",
        json.dumps({"name": "@workspace/types", "exports": "./src/index.ts"}),
    )
    target = _write(
        tmp_path / "packages/types/src/index.ts",
        "export interface SomeDto { id: string }\n",
    )
    importer = _write(
        tmp_path / "apps/web/src/page.ts",
        "import type { SomeDto } from '@workspace/types'\nconst dto: SomeDto = { id: '1' }\n",
    )

    result = _extract_for([target, importer], tmp_path)

    assert _has_edge(result, "apps/web/src/page.ts", "packages/types/src/index.ts")


def test_yarn_workspace_package_import_resolves_package_entry(tmp_path: Path):
    _write(
        tmp_path / "package.json",
        json.dumps({"workspaces": {"packages": ["apps/*", "packages/*"]}}),
    )
    _write(
        tmp_path / "packages/types/package.json",
        json.dumps({"name": "@workspace/types", "exports": "./src/index.ts"}),
    )
    target = _write(
        tmp_path / "packages/types/src/index.ts",
        "export interface SomeDto { id: string }\n",
    )
    importer = _write(
        tmp_path / "apps/web/src/page.ts",
        "import type { SomeDto } from '@workspace/types'\nconst dto: SomeDto = { id: '1' }\n",
    )

    result = _extract_for([target, importer], tmp_path)

    assert _has_edge(result, "apps/web/src/page.ts", "packages/types/src/index.ts")


def test_pnpm_workspace_takes_precedence_over_package_json_workspaces(tmp_path: Path):
    _write(
        tmp_path / "pnpm-workspace.yaml",
        "packages:\n  - 'apps/*'\n  - 'packages/*'\n",
    )
    _write(
        tmp_path / "package.json",
        json.dumps({"workspaces": ["other/*"]}),
    )
    _write(
        tmp_path / "packages/types/package.json",
        json.dumps({"name": "@workspace/types", "exports": "./src/index.ts"}),
    )
    target = _write(
        tmp_path / "packages/types/src/index.ts",
        "export interface SomeDto { id: string }\n",
    )
    importer = _write(
        tmp_path / "apps/web/src/page.ts",
        "import type { SomeDto } from '@workspace/types'\nconst dto: SomeDto = { id: '1' }\n",
    )

    result = _extract_for([target, importer], tmp_path)

    assert _has_edge(result, "apps/web/src/page.ts", "packages/types/src/index.ts")


def test_workspace_subpath_export_string_resolves(tmp_path: Path):
    _write(
        tmp_path / "pnpm-workspace.yaml",
        "packages:\n  - 'apps/*'\n  - 'packages/*'\n",
    )
    _write(
        tmp_path / "packages/pkg-a/package.json",
        json.dumps({
            "name": "@example/pkg-a",
            "exports": {
                ".": "./src/index.ts",
                "./browser": "./src/browser.ts",
            },
        }),
    )
    target = _write(
        tmp_path / "packages/pkg-a/src/browser.ts",
        'export const value = "ok"\n',
    )
    importer = _write(
        tmp_path / "apps/web/src/consumer.ts",
        "import { value } from '@example/pkg-a/browser'\nexport const v = value\n",
    )

    result = _extract_for([target, importer], tmp_path)

    assert _has_edge(result, "apps/web/src/consumer.ts", "packages/pkg-a/src/browser.ts")


def test_workspace_subpath_export_condition_object_resolves(tmp_path: Path):
    _write(
        tmp_path / "pnpm-workspace.yaml",
        "packages:\n  - 'apps/*'\n  - 'packages/*'\n",
    )
    _write(
        tmp_path / "packages/pkg-a/package.json",
        json.dumps({
            "name": "@example/pkg-a",
            "exports": {
                "./browser": {
                    "source": "./src/browser.ts",
                    "import": "./dist/esm/browser.js",
                    "require": "./dist/cjs/browser.js",
                    "types": "./dist/types/browser.d.ts",
                },
            },
        }),
    )
    target = _write(
        tmp_path / "packages/pkg-a/src/browser.ts",
        'export const value = "ok"\n',
    )
    importer = _write(
        tmp_path / "apps/web/src/consumer.ts",
        "import { value } from '@example/pkg-a/browser'\nexport const v = value\n",
    )

    result = _extract_for([target, importer], tmp_path)

    assert _has_edge(result, "apps/web/src/consumer.ts", "packages/pkg-a/src/browser.ts")


def test_workspace_subpath_export_wildcard_resolves(tmp_path: Path):
    _write(
        tmp_path / "pnpm-workspace.yaml",
        "packages:\n  - 'apps/*'\n  - 'packages/*'\n",
    )
    _write(
        tmp_path / "packages/pkg-a/package.json",
        json.dumps({
            "name": "@example/pkg-a",
            "exports": {
                "./*": {"source": "./src/*.ts"},
            },
        }),
    )
    target = _write(
        tmp_path / "packages/pkg-a/src/utils.ts",
        "export function add(a: number, b: number) { return a + b }\n",
    )
    importer = _write(
        tmp_path / "apps/web/src/consumer.ts",
        "import { add } from '@example/pkg-a/utils'\nexport const sum = add(1, 2)\n",
    )

    result = _extract_for([target, importer], tmp_path)

    assert _has_edge(result, "apps/web/src/consumer.ts", "packages/pkg-a/src/utils.ts")


def test_workspace_subpath_export_falls_back_to_filesystem(tmp_path: Path):
    _write(
        tmp_path / "pnpm-workspace.yaml",
        "packages:\n  - 'apps/*'\n  - 'packages/*'\n",
    )
    _write(
        tmp_path / "packages/pkg-a/package.json",
        json.dumps({"name": "@example/pkg-a"}),
    )
    target = _write(
        tmp_path / "packages/pkg-a/browser.ts",
        'export const value = "ok"\n',
    )
    importer = _write(
        tmp_path / "apps/web/src/consumer.ts",
        "import { value } from '@example/pkg-a/browser'\nexport const v = value\n",
    )

    result = _extract_for([target, importer], tmp_path)

    assert _has_edge(result, "apps/web/src/consumer.ts", "packages/pkg-a/browser.ts")


def test_workspace_subpath_export_rejects_path_escape(tmp_path: Path):
    # An exports target that escapes the package dir must NOT resolve to the
    # outside path (path-containment security guard). Resolution falls through
    # to the bare-path fallback, which has no real file here, so no edge lands
    # on the escaped target.
    _write(
        tmp_path / "pnpm-workspace.yaml",
        "packages:\n  - 'apps/*'\n  - 'packages/*'\n",
    )
    _write(
        tmp_path / "packages/pkg-a/package.json",
        json.dumps({
            "name": "@example/pkg-a",
            "exports": {
                "./evil": "../../../../secret.ts",
            },
        }),
    )
    # A real file outside the package that the malicious export points at.
    outside = _write(
        tmp_path / "secret.ts",
        'export const leak = "secret"\n',
    )
    importer = _write(
        tmp_path / "apps/web/src/consumer.ts",
        "import { leak } from '@example/pkg-a/evil'\nexport const v = leak\n",
    )

    result = _extract_for([outside, importer], tmp_path)

    # The import must NOT resolve to the escaped outside file.
    assert not _has_edge(result, "apps/web/src/consumer.ts", "secret.ts")


def test_workspace_subpath_export_default_consulted_last(tmp_path: Path):
    # When both `default` and an earlier condition match, the earlier
    # condition (import) must win -- `default` is Node's catch-all.
    _write(
        tmp_path / "pnpm-workspace.yaml",
        "packages:\n  - 'apps/*'\n  - 'packages/*'\n",
    )
    _write(
        tmp_path / "packages/pkg-a/package.json",
        json.dumps({
            "name": "@example/pkg-a",
            "exports": {
                "./browser": {
                    "default": "./src/default-entry.ts",
                    "import": "./src/import-entry.ts",
                },
            },
        }),
    )
    import_entry = _write(
        tmp_path / "packages/pkg-a/src/import-entry.ts",
        'export const value = "import"\n',
    )
    default_entry = _write(
        tmp_path / "packages/pkg-a/src/default-entry.ts",
        'export const value = "default"\n',
    )
    importer = _write(
        tmp_path / "apps/web/src/consumer.ts",
        "import { value } from '@example/pkg-a/browser'\nexport const v = value\n",
    )

    result = _extract_for([import_entry, default_entry, importer], tmp_path)

    # `import` wins over `default`.
    assert _has_edge(result, "apps/web/src/consumer.ts", "packages/pkg-a/src/import-entry.ts")
    assert not _has_edge(result, "apps/web/src/consumer.ts", "packages/pkg-a/src/default-entry.ts")


def test_js_import_resolution_ignores_stale_importer_cache_when_target_appears(tmp_path: Path):
    importer = _write(
        tmp_path / "src/lib/page.ts",
        "import { foo } from './foo'\nconsole.log(foo)\n",
    )

    first = _extract_for([importer], tmp_path)
    assert not _has_edge(first, "src/lib/page.ts", "src/lib/foo.ts")

    target = _write(tmp_path / "src/lib/foo.ts", "export const foo = 1\n")
    second = _extract_for([target, importer], tmp_path)

    assert _has_edge(second, "src/lib/page.ts", "src/lib/foo.ts")


def test_workspace_package_cache_refreshes_between_extract_calls(tmp_path: Path):
    _write(
        tmp_path / "pnpm-workspace.yaml",
        "packages:\n  - 'apps/*'\n  - 'packages/*'\n",
    )
    importer = _write(
        tmp_path / "apps/web/src/page.ts",
        "import type { SomeDto } from '@workspace/types'\nconst dto: SomeDto = { id: '1' }\n",
    )

    first = _extract_for([importer], tmp_path)
    assert not _has_edge(first, "apps/web/src/page.ts", "packages/types/src/index.ts")

    _write(
        tmp_path / "packages/types/package.json",
        json.dumps({"name": "@workspace/types", "exports": "./src/index.ts"}),
    )
    target = _write(
        tmp_path / "packages/types/src/index.ts",
        "export interface SomeDto { id: string }\n",
    )

    second = _extract_for([target, importer], tmp_path)

    assert _has_edge(second, "apps/web/src/page.ts", "packages/types/src/index.ts")


def test_pnpm_workspace_dot_package_does_not_crash(tmp_path: Path):
    """packages: - '.' in pnpm-workspace.yaml must not raise IndexError on any Python version."""
    _write(
        tmp_path / "pnpm-workspace.yaml",
        "packages:\n  - '.'\n  - 'examples/*'\n",
    )
    _write(
        tmp_path / "package.json",
        json.dumps({"name": "my-app"}),
    )
    src = _write(
        tmp_path / "index.ts",
        "import { foo } from 'my-app';\n",
    )

    result = _extract_for([src], tmp_path)

    nodes = result.get("nodes", [])
    assert isinstance(nodes, list)
    for node in nodes:
        error = node.get("error", "") if isinstance(node, dict) else ""
        assert "IndexError" not in error


def test_ts_type_relationships_and_contexts(tmp_path: Path):
    base = _write(
        tmp_path / "src/lib/base.ts",
        "export interface IProcessor<T> { run(input: T): Result<T> }\n"
        "export abstract class BaseProcessor {}\n"
        "export type Result<T> = { value: T }\n"
        "export class Payload {}\n",
    )
    impl = _write(
        tmp_path / "src/lib/impl.ts",
        "import type { IProcessor, BaseProcessor, Result, Payload } from './base'\n"
        "export abstract class DataProcessor extends BaseProcessor implements IProcessor<Payload> {\n"
        "  current!: Result<Payload>\n"
        "  run(input: Payload): Result<Payload> { return this.current }\n"
        "}\n",
    )

    result = _extract_for([base, impl], tmp_path)
    labels = {node["id"]: node["label"] for node in result["nodes"]}

    def _norm(label: str) -> str:
        return label.strip("()").lstrip(".")

    reference_contexts = {
        (
            _norm(labels.get(edge["source"], edge["source"])),
            _norm(labels.get(edge["target"], edge["target"])),
            edge.get("context"),
        )
        for edge in result["edges"]
        if edge.get("relation") == "references"
    }

    assert _has_symbol_to_symbol_edge(result, "src/lib/impl.ts", "DataProcessor", "src/lib/base.ts", "BaseProcessor", "inherits")
    assert _has_symbol_to_symbol_edge(result, "src/lib/impl.ts", "DataProcessor", "src/lib/base.ts", "IProcessor", "implements")
    assert ("run", "Payload", "parameter_type") in reference_contexts
    assert ("run", "Result", "return_type") in reference_contexts
    assert ("run", "Payload", "generic_arg") in reference_contexts


# ── #1531: tsconfig path-alias fallback targets ──────────────────────────────


def test_tsconfig_alias_resolves_second_target_when_first_missing(tmp_path: Path):
    # tsc tries each `paths` target in declared order until one resolves on disk.
    # The file lives only at the SECOND target, so keeping only the first entry
    # (#1531) dropped the edge.
    _write(
        tmp_path / "tsconfig.json",
        json.dumps({"compilerOptions": {"baseUrl": ".", "paths": {"$lib/*": ["generated/*", "src/lib/*"]}}}),
    )
    target = _write(tmp_path / "src/lib/utils.ts", "export const helper = 1\n")
    importer = _write(
        tmp_path / "src/routes/page.ts",
        "import { helper } from '$lib/utils'\nconsole.log(helper)\n",
    )

    result = _extract_for([target, importer], tmp_path)

    assert _has_edge(result, "src/routes/page.ts", "src/lib/utils.ts")


def test_tsconfig_alias_first_target_wins_when_both_exist(tmp_path: Path):
    # When the file exists at BOTH targets, tsc resolves to the FIRST. The edge
    # must target the generated/ copy, not src/lib.
    _write(
        tmp_path / "tsconfig.json",
        json.dumps({"compilerOptions": {"baseUrl": ".", "paths": {"$lib/*": ["generated/*", "src/lib/*"]}}}),
    )
    first = _write(tmp_path / "generated/utils.ts", "export const helper = 1\n")
    second = _write(tmp_path / "src/lib/utils.ts", "export const helper = 2\n")
    importer = _write(
        tmp_path / "src/routes/page.ts",
        "import { helper } from '$lib/utils'\nconsole.log(helper)\n",
    )

    result = _extract_for([first, second, importer], tmp_path)

    assert _has_edge(result, "src/routes/page.ts", "generated/utils.ts")
    assert not _has_edge(result, "src/routes/page.ts", "src/lib/utils.ts")


def test_tsconfig_alias_none_exist_creates_no_false_edge(tmp_path: Path):
    # The file exists at neither target; no concrete imports_from edge to either
    # candidate may be fabricated (it stays an external/phantom target).
    _write(
        tmp_path / "tsconfig.json",
        json.dumps({"compilerOptions": {"baseUrl": ".", "paths": {"$lib/*": ["generated/*", "src/lib/*"]}}}),
    )
    other = _write(tmp_path / "src/routes/other.ts", "export const x = 1\n")
    importer = _write(
        tmp_path / "src/routes/page.ts",
        "import { helper } from '$lib/utils'\nconsole.log(helper)\n",
    )

    result = _extract_for([other, importer], tmp_path)

    assert not _has_edge(result, "src/routes/page.ts", "generated/utils.ts")
    assert not _has_edge(result, "src/routes/page.ts", "src/lib/utils.ts")


def test_unresolved_relative_import_uses_stable_ref_target(tmp_path: Path):
    """A missing local module must not leak the checkout path into graph IDs (#2457)."""
    importer = _write(
        tmp_path / "src/consumer.ts",
        "import { getFoo } from './generated/api'\n"
        "export function run(): number { return getFoo() }\n",
    )

    result = _extract_for([importer], tmp_path)
    source = _file_node_id(Path("src/consumer.ts"))
    imports_from = [
        edge["target"]
        for edge in result["edges"]
        if edge["source"] == source and edge["relation"] == "imports_from"
    ]

    assert imports_from == [_make_id("ref", "./generated/api")]
    assert not any(
        edge["source"] == source and edge["relation"] == "imports"
        for edge in result["edges"]
    )



def test_unresolved_relative_require_uses_stable_ref_target(tmp_path: Path):
    """CommonJS require() of a missing local module took a separate path from
    static imports and still minted its target, and every destructured symbol
    under it, from the attempted absolute path: the checkout location and the
    OS username ended up in node ids (#2457 residual)."""
    importer = _write(
        tmp_path / "src/consumer.js",
        "const { loadFoundation } = require('./generated/api');\n"
        "function run() { return loadFoundation(); }\n"
        "module.exports = { run };\n",
    )

    result = _extract_for([importer], tmp_path)
    source = _file_node_id(Path("src/consumer.js"))
    imports_from = [
        edge["target"]
        for edge in result["edges"]
        if edge["source"] == source and edge["relation"] == "imports_from"
    ]

    assert imports_from == [_make_id("ref", "./generated/api")]
    checkout = _make_id(str(tmp_path))
    leaked = [
        endpoint
        for edge in result["edges"]
        for endpoint in (edge["source"], edge["target"])
        if checkout in endpoint
    ] + [node["id"] for node in result["nodes"] if checkout in node["id"]]
    assert leaked == []

# ── #927: wildcard tsconfig path patterns ────────────────────────────────────


def test_tsconfig_wildcard_alias_substitutes_captured_path(tmp_path, monkeypatch):
    _write(
        tmp_path / "tsconfig.json",
        json.dumps({
            "compilerOptions": {
                "baseUrl": ".",
                "paths": {"@*": ["features/*/src/"]},
            }
        }),
    )
    _write(
        tmp_path / "features/communicate/documentv2/src/index.ts",
        "export const FileChipComponent = {}\n",
    )
    _write(
        tmp_path / "src/routes/page.ts",
        "import { FileChipComponent } from '@communicate/documentv2'\n",
    )

    monkeypatch.chdir(tmp_path)
    result = extract(
        [
            Path("features/communicate/documentv2/src/index.ts"),
            Path("src/routes/page.ts"),
        ],
        cache_root=Path("."),
    )

    assert _has_edge(
        result,
        "src/routes/page.ts",
        "features/communicate/documentv2/src/index.ts",
    )


def test_tsconfig_wildcard_alias_substitutes_before_suffix(tmp_path: Path):
    _write(
        tmp_path / "tsconfig.json",
        json.dumps({
            "compilerOptions": {
                "baseUrl": ".",
                "paths": {"@*/interfaces": ["features/*/src/interfaces.ts"]},
            }
        }),
    )
    target = _write(
        tmp_path / "features/communicate/src/interfaces.ts",
        "export interface Message { id: string }\n",
    )
    importer = _write(
        tmp_path / "src/routes/page.ts",
        "import type { Message } from '@communicate/interfaces'\n",
    )

    result = _extract_for([target, importer], tmp_path)

    assert _has_edge(
        result,
        "src/routes/page.ts",
        "features/communicate/src/interfaces.ts",
    )


def test_tsconfig_wildcard_alias_substitutes_before_normalizing_target(tmp_path: Path):
    _write(
        tmp_path / "tsconfig.json",
        json.dumps({
            "compilerOptions": {
                "baseUrl": ".",
                "paths": {"@/*": ["generated/*/../shared"]},
            }
        }),
    )
    target = _write(
        tmp_path / "generated/feature/shared/index.ts",
        "export const shared = 1\n",
    )
    importer = _write(
        tmp_path / "src/routes/page.ts",
        "import { shared } from '@/feature/nested'\n",
    )

    result = _extract_for([target, importer], tmp_path)

    assert _has_edge(
        result,
        "src/routes/page.ts",
        "generated/feature/shared/index.ts",
    )


def test_tsconfig_wildcard_alias_allows_empty_capture(tmp_path: Path):
    _write(
        tmp_path / "tsconfig.json",
        json.dumps({
            "compilerOptions": {
                "baseUrl": ".",
                "paths": {"app*": ["src/config/index.ts"]},
            }
        }),
    )
    target = _write(tmp_path / "src/config/index.ts", "export const config = {}\n")
    importer = _write(
        tmp_path / "src/routes/page.ts",
        "import { config } from 'app'\n",
    )

    result = _extract_for([target, importer], tmp_path)

    assert _has_edge(result, "src/routes/page.ts", "src/config/index.ts")


def test_tsconfig_wildcard_alias_prefers_longest_matching_prefix(tmp_path: Path):
    _write(
        tmp_path / "tsconfig.json",
        json.dumps({
            "compilerOptions": {
                "baseUrl": ".",
                "paths": {
                    "@/*": ["fallback/*"],
                    "@/common/integration/*": ["preferred/*"],
                },
            }
        }),
    )
    fallback = _write(
        tmp_path / "fallback/common/integration/foo.ts",
        "export const Foo = 1\n",
    )
    preferred = _write(tmp_path / "preferred/foo.ts", "export const Foo = 2\n")
    importer = _write(
        tmp_path / "src/routes/page.ts",
        "import { Foo } from '@/common/integration/foo'\n",
    )

    result = _extract_for([fallback, preferred, importer], tmp_path)

    assert _has_edge(result, "src/routes/page.ts", "preferred/foo.ts")
    assert not _has_edge(result, "src/routes/page.ts", "fallback/common/integration/foo.ts")


def test_tsconfig_exact_alias_still_resolves(tmp_path: Path):
    _write(
        tmp_path / "tsconfig.json",
        json.dumps({
            "compilerOptions": {
                "baseUrl": ".",
                "paths": {"app-config": ["src/config/index.ts"]},
            }
        }),
    )
    target = _write(tmp_path / "src/config/index.ts", "export const config = {}\n")
    importer = _write(
        tmp_path / "src/routes/page.ts",
        "import { config } from 'app-config'\n",
    )

    result = _extract_for([target, importer], tmp_path)

    assert _has_edge(result, "src/routes/page.ts", "src/config/index.ts")


# ── #1529: alias/workspace import targets orphaned by the full-path migration ──


def test_alias_import_edge_resolves_with_relative_input_paths(tmp_path, monkeypatch):
    # CRUCIAL: pass RELATIVE input paths (chdir into the project). Alias imports
    # resolve specifiers through .resolve(), so the import-target id is keyed off
    # the ABSOLUTE path; with relative inputs the id_remap (keyed on the input
    # form) never rewrote it -> orphan -> dropped edge (#1529). Absolute/tmp_path
    # inputs hide the bug because the two forms coincide.
    _write(
        tmp_path / "tsconfig.json",
        json.dumps({"compilerOptions": {"baseUrl": ".", "paths": {"@/*": ["src/*"]}}}),
    )
    _write(tmp_path / "src/lib/utils.ts", "export function formatDate(d) { return d }\n")
    _write(
        tmp_path / "src/components/Button.tsx",
        "import { formatDate } from '@/lib/utils'\nexport function Button() { return formatDate(1) }\n",
    )

    monkeypatch.chdir(tmp_path)
    rel_paths = [Path("src/lib/utils.ts"), Path("src/components/Button.tsx")]
    result = extract(rel_paths, cache_root=Path("."))

    node_ids = {n["id"] for n in result["nodes"]}
    target_id = _file_node_id(Path("src/lib/utils.ts"))

    # The file-level imports_from edge must target the REAL utils file node (a node
    # that exists in the graph), not an orphan keyed by an absolute prefix.
    assert _has_edge(result, "src/components/Button.tsx", "src/lib/utils.ts")
    assert target_id in node_ids
    import_targets = [
        e["target"]
        for e in result["edges"]
        if e["relation"] == "imports_from" and e["source"] == _file_node_id(Path("src/components/Button.tsx"))
    ]
    assert import_targets == [target_id]
    # No surviving edge target may carry an absolute-path prefix from tmp_path.
    abs_prefix = _file_node_id(Path("src/lib/utils.ts").resolve())
    assert all(not t.startswith(abs_prefix + "_") and t != abs_prefix for t in import_targets)

    # The named-symbol edge to formatDate must resolve to the real symbol node too.
    assert _has_symbol_edge(result, "src/components/Button.tsx", "src/lib/utils.ts", "formatDate")
    symbol_target = _make_id(_file_stem(Path("src/lib/utils.ts")), "formatDate")
    named_imports = [
        edge
        for edge in result["edges"]
        if edge["source"] == _file_node_id(Path("src/components/Button.tsx"))
        and edge["relation"] == "imports"
        and edge["source_location"] == "L1"
    ]
    assert [edge["target"] for edge in named_imports] == [symbol_target]
    assert all(
        edge["source"] in node_ids and edge["target"] in node_ids
        for edge in result["edges"]
        if edge["relation"] in ("imports", "imports_from")
    )


def test_alias_import_symbol_resolves_from_parent_working_directory(tmp_path, monkeypatch):
    project = tmp_path / "project"
    _write(
        project / "tsconfig.json",
        json.dumps({"compilerOptions": {"baseUrl": ".", "paths": {"@/*": ["src/*"]}}}),
    )
    _write(project / "src/lib/utils.ts", "export function formatDate(d) { return d }\n")
    _write(
        project / "src/components/Button.tsx",
        "import { formatDate } from '@/lib/utils'\n",
    )

    monkeypatch.chdir(tmp_path)
    result = extract(
        [Path("project/src/lib/utils.ts"), Path("project/src/components/Button.tsx")],
        cache_root=Path("project"),
    )

    node_ids = {node["id"] for node in result["nodes"]}
    source_id = _file_node_id(Path("src/components/Button.tsx"))
    symbol_target = _make_id(_file_stem(Path("src/lib/utils.ts")), "formatDate")
    named_imports = [
        edge
        for edge in result["edges"]
        if edge["source"] == source_id and edge["relation"] == "imports"
    ]

    assert [edge["target"] for edge in named_imports] == [symbol_target]
    assert all(edge["source"] in node_ids and edge["target"] in node_ids for edge in named_imports)


@pytest.mark.parametrize(
    "statement",
    [
        "export { formatDate } from '@/lib/utils'\n",
        "export { formatDate as displayDate } from '@/lib/utils'\n",
    ],
)
def test_alias_reexport_symbol_resolves_with_relative_input_paths(
    tmp_path, monkeypatch, statement
):
    _write(
        tmp_path / "tsconfig.json",
        json.dumps({"compilerOptions": {"baseUrl": ".", "paths": {"@/*": ["src/*"]}}}),
    )
    _write(tmp_path / "src/lib/utils.ts", "export function formatDate() { return 'ok' }\n")
    _write(tmp_path / "src/lib/index.ts", statement)

    monkeypatch.chdir(tmp_path)
    target = Path("src/lib/utils.ts")
    barrel = Path("src/lib/index.ts")
    result = extract([target, barrel], cache_root=Path("."))

    node_ids = {node["id"] for node in result["nodes"]}
    file_target = _file_node_id(target)
    symbol_target = _make_id(_file_stem(target), "formatDate")
    reexports = [
        edge
        for edge in result["edges"]
        if edge["source"] == _file_node_id(barrel)
        and edge["relation"] == "re_exports"
    ]

    assert sorted(edge["target"] for edge in reexports) == sorted(
        [file_target, symbol_target]
    )
    assert all(edge["target"] in node_ids for edge in reexports)
    absolute_prefix = _file_node_id(target.resolve())
    assert all(not edge["target"].startswith(absolute_prefix + "_") for edge in reexports)


def test_alias_reexport_symbol_resolves_from_parent_working_directory(tmp_path, monkeypatch):
    project = tmp_path / "project"
    _write(
        project / "tsconfig.json",
        json.dumps({"compilerOptions": {"baseUrl": ".", "paths": {"@/*": ["src/*"]}}}),
    )
    _write(project / "src/lib/utils.ts", "export function formatDate() { return 'ok' }\n")
    _write(project / "src/lib/index.ts", "export { formatDate } from '@/lib/utils'\n")

    monkeypatch.chdir(tmp_path)
    target = Path("project/src/lib/utils.ts")
    barrel = Path("project/src/lib/index.ts")
    result = extract([target, barrel], cache_root=Path("project"))

    node_ids = {node["id"] for node in result["nodes"]}
    source = _file_node_id(Path("src/lib/index.ts"))
    symbol_target = _make_id(_file_stem(Path("src/lib/utils.ts")), "formatDate")
    symbol_reexports = [
        edge
        for edge in result["edges"]
        if edge["source"] == source
        and edge["relation"] == "re_exports"
        and edge["target"] != _file_node_id(Path("src/lib/utils.ts"))
    ]

    assert [edge["target"] for edge in symbol_reexports] == [symbol_target]
    assert all(edge["target"] in node_ids for edge in symbol_reexports)


def test_alias_reexport_does_not_rewrite_an_owned_symbol_id(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    target = Path("src/lib/utils.ts")
    absolute_prefix = _file_node_id(target.resolve())
    mirror = Path(f"{absolute_prefix}.ts")
    barrel = Path("src/lib/index.ts")

    _write(
        Path("tsconfig.json"),
        json.dumps({"compilerOptions": {"baseUrl": ".", "paths": {"@/*": ["src/*"]}}}),
    )
    _write(target, "export function formatDate() { return 'target' }\n")
    _write(mirror, "export function formatDate() { return 'mirror' }\n")
    _write(barrel, "export { formatDate } from '@/lib/utils'\n")

    result = extract([target, mirror, barrel], cache_root=Path("."))

    node_ids = {node["id"] for node in result["nodes"]}
    owned_target = _make_id(_file_stem(mirror), "formatDate")
    symbol_reexports = [
        edge
        for edge in result["edges"]
        if edge["source"] == _file_node_id(barrel)
        and edge["relation"] == "re_exports"
        and edge["target"] != _file_node_id(target)
    ]

    assert [edge["target"] for edge in symbol_reexports] == [owned_target]
    assert owned_target in node_ids


def test_alias_import_does_not_remap_an_owned_symbol_id(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    target = Path("src/lib/utils.ts")
    absolute_prefix = _file_node_id(target.resolve())
    mirror = Path(f"{absolute_prefix}.ts")
    button = Path("src/components/Button.tsx")
    mirror_user = Path("src/components/Mirror.tsx")

    _write(
        Path("tsconfig.json"),
        json.dumps({"compilerOptions": {"baseUrl": ".", "paths": {"@/*": ["src/*"]}}}),
    )
    _write(target, "export function formatDate(d) { return d }\n")
    _write(mirror, "export function formatDate(d) { return 999 }\n")
    _write(
        button,
        "import { formatDate } from '@/lib/utils'\nexport const a = formatDate(1)\n",
    )
    _write(
        mirror_user,
        f"import {{ formatDate }} from '../../{mirror.stem}'\nexport const b = formatDate(2)\n",
    )

    result = extract(
        [target, mirror, button, mirror_user],
        cache_root=Path("."),
    )

    node_ids = {node["id"] for node in result["nodes"]}
    symbols = {
        node["source_file"]: node["id"]
        for node in result["nodes"]
        if node.get("label") == "formatDate()"
    }
    target_symbol = _make_id(_file_stem(target), "formatDate")
    mirror_symbol = _make_id(_file_stem(mirror), "formatDate")
    # as_posix, not str: source_file is canonical POSIX in extract() output
    # (#2625), while str(Path(...)) is the native spelling and so only matched
    # on POSIX hosts.
    assert symbols[target.as_posix()] == target_symbol
    assert symbols[mirror.as_posix()] == mirror_symbol

    imports = [
        edge
        for edge in result["edges"]
        if edge["relation"] == "imports" and edge["source_location"] == "L1"
    ]
    by_source: dict[str, list[str]] = {}
    for edge in imports:
        by_source.setdefault(edge["source_file"], []).append(edge["target"])
    assert by_source[button.as_posix()] == [target_symbol]
    assert by_source[mirror_user.as_posix()] == [mirror_symbol]
    assert all(edge["source"] in node_ids and edge["target"] in node_ids for edge in imports)


def test_alias_import_preserves_owned_same_line_symbol_edge(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    target = Path("src/lib/utils.ts")
    absolute_prefix = _file_node_id(target.resolve())
    mirror = Path(f"{absolute_prefix}.ts")
    importer = Path("src/components/Both.tsx")

    _write(
        Path("tsconfig.json"),
        json.dumps({"compilerOptions": {"baseUrl": ".", "paths": {"@/*": ["src/*"]}}}),
    )
    _write(target, "export function formatDate(d) { return d }\n")
    _write(mirror, "export function formatDate(d) { return 999 }\n")
    _write(
        importer,
        f"import {{ formatDate as a }} from '@/lib/utils'; "
        f"import {{ formatDate as b }} from '../../{mirror.stem}';\n"
        "export const value = a(1) + b(2)\n",
    )

    result = extract([target, mirror, importer], cache_root=Path("."))

    node_ids = {node["id"] for node in result["nodes"]}
    target_symbol = _make_id(_file_stem(target), "formatDate")
    mirror_symbol = _make_id(_file_stem(mirror), "formatDate")
    imports = [
        edge
        for edge in result["edges"]
        if edge["source"] == _file_node_id(importer)
        and edge["relation"] == "imports"
        and edge["source_location"] == "L1"
    ]

    assert sorted(edge["target"] for edge in imports) == sorted([target_symbol, mirror_symbol])
    assert all(edge["source"] in node_ids and edge["target"] in node_ids for edge in imports)


# --- #1983 (follow-up): alias re-exports THROUGH a barrel ---------------------
# The candidates rewrite learns old->canonical symbol forms only from symbols a
# file DEFINES. A barrel defines nothing, so a re-export/import that resolves to
# the barrel synthesizes an absolute-prefixed target no rewrite ever learns:
# the checkout path leaks into the id and the edge dangles.

def _barrel_fixture(tmp_path):
    _write(
        tmp_path / "tsconfig.json",
        json.dumps({"compilerOptions": {"baseUrl": ".", "paths": {"@/*": ["src/*"]}}}),
    )
    _write(tmp_path / "src/lib/utils.ts", "export function formatDate() { return 'ok' }\n")
    _write(tmp_path / "src/lib/index.ts", "export { formatDate } from '@/lib/utils'\n")


def test_alias_reexport_through_barrel_resolves_to_defining_symbol(tmp_path, monkeypatch):
    _barrel_fixture(tmp_path)
    _write(tmp_path / "src/barrel2.ts", "export { formatDate } from '@/lib'\n")

    monkeypatch.chdir(tmp_path)
    files = sorted(Path("src").rglob("*.ts"))
    result = extract(files, cache_root=Path("."))

    node_ids = {node["id"] for node in result["nodes"]}
    defining_symbol = _make_id(_file_stem(Path("src/lib/utils.ts")), "formatDate")
    barrel_reexports = [
        edge
        for edge in result["edges"]
        if edge["source"] == _file_node_id(Path("src/barrel2.ts"))
        and edge["relation"] == "re_exports"
        and edge["target"] != _file_node_id(Path("src/lib/index.ts"))
    ]

    assert [edge["target"] for edge in barrel_reexports] == [defining_symbol]
    assert all(edge["target"] in node_ids for edge in barrel_reexports)


def test_alias_reexport_two_hop_barrel_chain_resolves(tmp_path, monkeypatch):
    _barrel_fixture(tmp_path)
    _write(tmp_path / "src/barrel2.ts", "export { formatDate } from '@/lib'\n")
    _write(tmp_path / "src/barrel3.ts", "export { formatDate } from '@/barrel2'\n")

    monkeypatch.chdir(tmp_path)
    files = sorted(Path("src").rglob("*.ts"))
    result = extract(files, cache_root=Path("."))

    node_ids = {node["id"] for node in result["nodes"]}
    defining_symbol = _make_id(_file_stem(Path("src/lib/utils.ts")), "formatDate")
    barrel3_reexports = [
        edge
        for edge in result["edges"]
        if edge["source"] == _file_node_id(Path("src/barrel3.ts"))
        and edge["relation"] == "re_exports"
        and edge["target"] != _file_node_id(Path("src/barrel2.ts"))
    ]

    assert [edge["target"] for edge in barrel3_reexports] == [defining_symbol]
    assert all(edge["target"] in node_ids for edge in barrel3_reexports)


def test_no_symbol_edge_target_contains_checkout_prefix(tmp_path, monkeypatch):
    """No re_exports/imports target may embed the absolute checkout path —
    the core complaint of #1983, which barrels still triggered after the
    single-hop fix."""
    _barrel_fixture(tmp_path)
    _write(tmp_path / "src/barrel2.ts", "export { formatDate } from '@/lib'\n")
    _write(
        tmp_path / "src/consumer.ts",
        "import { formatDate } from '@/lib'\nexport function useIt() { return formatDate() }\n",
    )

    monkeypatch.chdir(tmp_path)
    files = sorted(Path("src").rglob("*.ts"))
    result = extract(files, cache_root=Path("."))

    abs_prefix = _make_id(str(Path("src").resolve().parent))
    offenders = [
        (edge["relation"], edge["target"])
        for edge in result["edges"]
        if edge.get("relation") in ("re_exports", "imports")
        and str(edge.get("target", "")).startswith(abs_prefix)
    ]
    assert offenders == [], f"checkout path leaked into edge targets: {offenders}"


def test_ambiguous_barrel_reexport_chain_does_not_guess(tmp_path, monkeypatch):
    """When a barrel re-exports the SAME local name from two different modules,
    the barrel-chain resolver must NOT collapse an importer's edge onto one of
    them by last-write-wins (#2034 follow-up). With the ambiguity guard the chain
    leaves the import unresolved at the barrel symbol (dangling, dropped at build)
    rather than fabricating a specific target; without it the chain repoints to
    whichever module was learned last."""
    _write(
        tmp_path / "tsconfig.json",
        json.dumps({"compilerOptions": {"baseUrl": ".", "paths": {"@/*": ["src/*"]}}}),
    )
    _write(tmp_path / "src/lib/a.ts", "export function dup() { return 'a' }\n")
    _write(tmp_path / "src/lib/b.ts", "export function dup() { return 'b' }\n")
    _write(tmp_path / "src/lib/index.ts",
           "export { dup } from '@/lib/a'\nexport { dup } from '@/lib/b'\n")
    _write(tmp_path / "src/consumer.ts",
           "import { dup } from '@/lib'\nexport function useIt() { return dup() }\n")

    monkeypatch.chdir(tmp_path)
    result = extract(sorted(Path("src").rglob("*.ts")), cache_root=Path("."))

    barrel_sym = _make_id(_file_stem(Path("src/lib/index.ts")), "dup")
    consumer = _file_node_id(Path("src/consumer.ts"))
    consumer_imports = [
        e for e in result["edges"]
        if e.get("source") == consumer and e.get("relation") == "imports"
    ]
    # The chain-produced import edge stays at the barrel symbol (unresolved) —
    # proof the chain refused to guess. Without the fix it would be repointed to
    # src_lib_a_dup / src_lib_b_dup (last-write-wins), so this edge would vanish.
    assert any(e.get("target") == barrel_sym for e in consumer_imports), (
        f"ambiguous barrel import was chain-resolved instead of left unresolved: "
        f"{[e.get('target') for e in consumer_imports]}"
    )
    # Both legitimate barrel re-exports still resolve to their own module.
    barrel = _file_node_id(Path("src/lib/index.ts"))
    reexport_targets = {
        e.get("target") for e in result["edges"]
        if e.get("source") == barrel and e.get("relation") == "re_exports"
    }
    assert _make_id(_file_stem(Path("src/lib/a.ts")), "dup") in reexport_targets
    assert _make_id(_file_stem(Path("src/lib/b.ts")), "dup") in reexport_targets


# ── #3487: the exports-map condition must follow the importer ────────────────


def _write_workspace_package(root: Path, name: str, exports: dict | str) -> None:
    _write(
        root / "pnpm-workspace.yaml",
        "packages:\n  - 'apps/*'\n  - 'packages/*'\n",
    )
    _write(
        root / "packages/pkg-a/package.json",
        json.dumps({"name": name, "exports": exports}),
    )


def test_export_types_condition_never_beats_a_real_runtime_target(tmp_path: Path):
    """#3487 detail 1. `types` points into unbuilt `dist/`, so resolving to it
    produces an edge to a node that does not exist — and because that target is
    what got returned, the `default` source beside it was never tried."""
    _write_workspace_package(tmp_path, "@example/pkg-a", {
        "./browser": {
            "types": "./dist/browser.d.ts",
            "default": "./src/browser.ts",
        },
    })
    target = _write(
        tmp_path / "packages/pkg-a/src/browser.ts",
        'export const value = "ok"\n',
    )
    importer = _write(
        tmp_path / "apps/web/src/consumer.ts",
        "import { value } from '@example/pkg-a/browser'\nexport const v = value\n",
    )

    result = _extract_for([target, importer], tmp_path)

    assert _has_edge(result, "apps/web/src/consumer.ts", "packages/pkg-a/src/browser.ts")


def test_export_types_loses_even_when_the_declaration_exists(tmp_path: Path):
    """The lock on the ordering itself: `types` is a declaration, so it must not
    win merely because `dist/` happens to be present in the corpus."""
    _write_workspace_package(tmp_path, "@example/pkg-a", {
        "./browser": {
            "types": "./dist/browser.d.ts",
            "default": "./src/browser.ts",
        },
    })
    declaration = _write(
        tmp_path / "packages/pkg-a/dist/browser.d.ts",
        "export declare const value: string\n",
    )
    target = _write(
        tmp_path / "packages/pkg-a/src/browser.ts",
        'export const value = "ok"\n',
    )
    importer = _write(
        tmp_path / "apps/web/src/consumer.ts",
        "import { value } from '@example/pkg-a/browser'\nexport const v = value\n",
    )

    result = _extract_for([declaration, target, importer], tmp_path)

    assert _has_edge(result, "apps/web/src/consumer.ts", "packages/pkg-a/src/browser.ts")
    assert not _has_edge(
        result, "apps/web/src/consumer.ts", "packages/pkg-a/dist/browser.d.ts"
    )


def test_export_react_native_condition_selected_for_native_importer(tmp_path: Path):
    """#3487 detail 2. `react-native` is a custom condition, so it applies to the
    importer that opts into it rather than to the package as a whole."""
    _write_workspace_package(tmp_path, "@example/pkg-a", {
        "./Icon": {
            "types": "./dist/Icon.d.ts",
            "react-native": "./src/Icon.native.tsx",
            "default": "./src/Icon.web.tsx",
        },
    })
    native_target = _write(
        tmp_path / "packages/pkg-a/src/Icon.native.tsx",
        "export function Icon() { return null }\n",
    )
    web_target = _write(
        tmp_path / "packages/pkg-a/src/Icon.web.tsx",
        "export function Icon() { return null }\n",
    )
    importer = _write(
        tmp_path / "apps/mobile/src/App.tsx",
        "import { Icon } from '@example/pkg-a/Icon'\nexport const a = Icon\n",
    )

    result = _extract_for([native_target, web_target, importer], tmp_path)

    assert _has_edge(
        result, "apps/mobile/src/App.tsx", "packages/pkg-a/src/Icon.native.tsx"
    )
    assert not _has_edge(
        result, "apps/mobile/src/App.tsx", "packages/pkg-a/src/Icon.web.tsx"
    )


def test_export_react_native_condition_ignored_for_web_importer(tmp_path: Path):
    """The other half of detail 2: a web importer resolves through `default`, or
    the native file is attributed to code that never imports it."""
    _write_workspace_package(tmp_path, "@example/pkg-a", {
        "./Icon": {
            "react-native": "./src/Icon.native.tsx",
            "default": "./src/Icon.web.tsx",
        },
    })
    native_target = _write(
        tmp_path / "packages/pkg-a/src/Icon.native.tsx",
        "export function Icon() { return null }\n",
    )
    web_target = _write(
        tmp_path / "packages/pkg-a/src/Icon.web.tsx",
        "export function Icon() { return null }\n",
    )
    importer = _write(
        tmp_path / "apps/web/src/Page.tsx",
        "import { Icon } from '@example/pkg-a/Icon'\nexport const a = Icon\n",
    )

    result = _extract_for([native_target, web_target, importer], tmp_path)

    assert _has_edge(
        result, "apps/web/src/Page.tsx", "packages/pkg-a/src/Icon.web.tsx"
    )
    assert not _has_edge(
        result, "apps/web/src/Page.tsx", "packages/pkg-a/src/Icon.native.tsx"
    )


def test_export_wildcard_target_absent_falls_through_to_platform_sibling(tmp_path: Path):
    """#3487 detail 3. `./src/controls/*.tsx` names `BottomNav.tsx`, which does
    not exist — a bundler reaches `BottomNav.web.tsx` through its platform list,
    and the import must not be dropped for naming a file that was never there."""
    _write_workspace_package(tmp_path, "@example/pkg-a", {
        "./controls/*": {"default": "./src/controls/*.tsx"},
    })
    target = _write(
        tmp_path / "packages/pkg-a/src/controls/BottomNav.web.tsx",
        "export function BottomNav() { return null }\n",
    )
    other = _write(
        tmp_path / "packages/pkg-a/src/controls/BottomNav.native.tsx",
        "export function BottomNav() { return null }\n",
    )
    importer = _write(
        tmp_path / "apps/web/src/consumer.tsx",
        "import { BottomNav } from '@example/pkg-a/controls/BottomNav'\n"
        "export const b = BottomNav\n",
    )

    result = _extract_for([target, other, importer], tmp_path)

    assert _has_edge(
        result,
        "apps/web/src/consumer.tsx",
        "packages/pkg-a/src/controls/BottomNav.web.tsx",
    )


def test_export_rejected_target_still_falls_back_to_the_bare_path(tmp_path: Path):
    """A rejected (escaping) target must not consume the import: resolution
    still reaches the bare-path fallback, which is a real file here."""
    _write_workspace_package(tmp_path, "@example/pkg-a", {
        "./widget": "../../../../secret.ts",
    })
    outside = _write(tmp_path / "secret.ts", "export const leak = 1\n")
    target = _write(
        tmp_path / "packages/pkg-a/widget.ts",
        'export const value = "ok"\n',
    )
    importer = _write(
        tmp_path / "apps/web/src/consumer.ts",
        "import { value } from '@example/pkg-a/widget'\nexport const v = value\n",
    )

    result = _extract_for([outside, target, importer], tmp_path)

    assert _has_edge(result, "apps/web/src/consumer.ts", "packages/pkg-a/widget.ts")
    assert not _has_edge(result, "apps/web/src/consumer.ts", "secret.ts")


def test_export_bare_root_types_condition_falls_through_to_default(tmp_path: Path):
    """The bare-root form carries the same defect: `import { x } from
    '@scope/pkg'` resolved to the `types` target and stopped there."""
    _write(tmp_path / "pnpm-workspace.yaml", "packages:\n  - 'apps/*'\n  - 'packages/*'\n")
    _write(
        tmp_path / "packages/pkg-a/package.json",
        json.dumps({
            "name": "@example/pkg-a",
            "exports": {
                ".": {
                    "types": "./dist/index.d.ts",
                    "default": "./src/index.ts",
                },
            },
        }),
    )
    target = _write(
        tmp_path / "packages/pkg-a/src/index.ts",
        'export const value = "ok"\n',
    )
    importer = _write(
        tmp_path / "apps/web/src/consumer.ts",
        "import { value } from '@example/pkg-a'\nexport const v = value\n",
    )

    result = _extract_for([target, importer], tmp_path)

    assert _has_edge(result, "apps/web/src/consumer.ts", "packages/pkg-a/src/index.ts")


def test_ts_paths_alias_behind_solution_file_references_resolves(tmp_path: Path):
    """Vite / `tsc -b` layout: the root tsconfig.json is a solution file
    (`files: []` + `references`) with no `paths` of its own; the alias lives in
    the referenced project config. The loader followed `extends` but not
    `references`, so it found the solution file, saw no paths, and every alias
    import silently got no edge (#3745). Following references resolves it."""
    _write(
        tmp_path / "tsconfig.json",
        json.dumps({"files": [], "references": [{"path": "./tsconfig.app.json"}]}),
    )
    _write(
        tmp_path / "tsconfig.app.json",
        json.dumps({"compilerOptions": {"paths": {"@app/*": ["./src/*"]}}, "include": ["src"]}),
    )
    target = _write(tmp_path / "src/b.ts", "export const b = 1\n")
    importer = _write(
        tmp_path / "src/a.ts",
        "import { b } from '@app/b'\nexport const a = b + 1\n",
    )

    result = _extract_for([target, importer], tmp_path)

    assert _has_edge(result, "src/a.ts", "src/b.ts")


def test_ts_paths_alias_behind_directory_reference_resolves(tmp_path: Path):
    """A `references` entry may name a directory rather than a config file
    (`{path: "./packages/app"}`), which `tsc -b` resolves to that directory's
    tsconfig.json. The alias declared there must still be reached (#3745)."""
    _write(
        tmp_path / "tsconfig.json",
        json.dumps({"files": [], "references": [{"path": "./packages/app"}]}),
    )
    _write(
        tmp_path / "packages/app/tsconfig.json",
        json.dumps({"compilerOptions": {"baseUrl": ".", "paths": {"@lib/*": ["../../src/*"]}}}),
    )
    target = _write(tmp_path / "src/b.ts", "export const b = 1\n")
    importer = _write(
        tmp_path / "src/a.ts",
        "import { b } from '@lib/b'\nexport const a = b + 1\n",
    )

    result = _extract_for([target, importer], tmp_path)

    assert _has_edge(result, "src/a.ts", "src/b.ts")


def test_workspace_main_dist_target_falls_through_to_src_index_when_built(tmp_path: Path):
    """#3834: A workspace package declaring "main": "./dist/index.js" without exports
    resolves to built dist/index.js if it exists on disk. Because dist/ is outside the
    corpus (build output / ignored), the target node is absent and the edge dropped.
    Resolution must fall through to the source entry point (src/index.ts)."""
    _write(tmp_path / "pnpm-workspace.yaml", "packages:\n  - 'apps/*'\n  - 'packages/*'\n")
    _write(
        tmp_path / "packages/pkg-a/package.json",
        json.dumps({
            "name": "@example/pkg-a",
            "main": "./dist/index.js",
            "types": "./dist/index.d.ts",
        }),
    )
    # Simulate a built package: both dist/ and src/ exist on disk
    _write(
        tmp_path / "packages/pkg-a/dist/index.js",
        'export const value = "from-dist";\n',
    )
    _write(
        tmp_path / "packages/pkg-a/dist/index.d.ts",
        'export declare const value: string;\n',
    )
    source_target = _write(
        tmp_path / "packages/pkg-a/src/index.ts",
        'export const value = "ok";\n',
    )
    importer = _write(
        tmp_path / "apps/web/src/consumer.ts",
        "import { value } from '@example/pkg-a'\nexport const v = value\n",
    )

    result = _extract_for([source_target, importer], tmp_path)

    assert _has_edge(result, "apps/web/src/consumer.ts", "packages/pkg-a/src/index.ts")
    assert not _has_edge(result, "apps/web/src/consumer.ts", "packages/pkg-a/dist/index.js")


def test_workspace_main_dist_target_used_when_no_source_entry_exists(tmp_path: Path):
    """When no source entry point exists, the build artifact candidate remains the fallback."""
    _write(tmp_path / "pnpm-workspace.yaml", "packages:\n  - 'apps/*'\n  - 'packages/*'\n")
    _write(
        tmp_path / "packages/pkg-a/package.json",
        json.dumps({
            "name": "@example/pkg-a",
            "main": "./dist/index.js",
        }),
    )
    dist_target = _write(
        tmp_path / "packages/pkg-a/dist/index.js",
        'export const value = "from-dist";\n',
    )
    importer = _write(
        tmp_path / "apps/web/src/consumer.ts",
        "import { value } from '@example/pkg-a'\nexport const v = value\n",
    )

    result = _extract_for([dist_target, importer], tmp_path)

    assert _has_edge(result, "apps/web/src/consumer.ts", "packages/pkg-a/dist/index.js")


# ── tsconfig `customConditions` reach source the fixed walk cannot ─────────
#
# Every import that the fixed condition walk (#3487) already resolves to a
# source file keeps its target. customConditions only change imports that
# walk leaves on build output or on an external stub.


def _write_source_condition_package(root: Path, exports: dict) -> None:
    """zod's layout: every export names its source behind a custom condition,
    and the runtime conditions point at build output that is not in the scan."""
    _write_workspace_package(root, "@example/pkg-a", exports)
    _write(
        root / "tsconfig.base.json",
        "{\n  // JSONC, like most real configs\n"
        '  "compilerOptions": {"module": "esnext", "moduleResolution": "bundler",\n'
        '    "customConditions": ["@example/source"]},\n}\n',
    )


def _write_condition_importer(
    root: Path, conditions: list[str], exports: dict, nested: bool = True,
    extra_options: "dict | None" = None,
) -> Path:
    """One workspace package plus an importer whose tsconfig enables `conditions`."""
    _write_workspace_package(root, "@example/pkg-a", exports)
    _write(
        root / "apps/web/tsconfig.json",
        json.dumps({"compilerOptions": {
            "module": "esnext",
            "moduleResolution": "bundler",
            "customConditions": conditions,
            **(extra_options or {}),
        }}),
    )
    source = "import { a } from '@example/pkg-a'\n"
    if nested:
        source += "import { n } from '@example/pkg-a/nested'\n"
    return _write(root / "apps/web/src/consumer.ts", source + "export const v = a\n")


def test_tsconfig_custom_condition_resolves_workspace_export_to_source(tmp_path: Path):
    """`import 'zod/v4'` in zod resolves through `"@zod/source": "./src/..."`
    because packages/zod/tsconfig.json declares that condition. Graphify
    consulted only its fixed condition list, reached the `import`/`types`
    targets in an unbuilt package, and left the import pointing at nothing."""
    _write_source_condition_package(tmp_path, {
        ".": {
            "@example/source": "./src/index.ts",
            "types": "./index.d.ts",
            "import": "./index.js",
        },
        "./mini": {
            "@example/source": "./src/mini/index.ts",
            "types": "./mini/index.d.ts",
            "import": "./mini/index.js",
        },
    })
    _write(tmp_path / "apps/web/tsconfig.json", '{"extends": "../../tsconfig.base.json"}')
    root_entry = _write(tmp_path / "packages/pkg-a/src/index.ts", "export const a = 1\n")
    mini_entry = _write(tmp_path / "packages/pkg-a/src/mini/index.ts", "export const m = 1\n")
    importer = _write(
        tmp_path / "apps/web/src/consumer.ts",
        "import { a } from '@example/pkg-a'\n"
        "import { m } from '@example/pkg-a/mini'\n"
        "export const v = a + m\n",
    )

    result = _extract_for([root_entry, mini_entry, importer], tmp_path)

    assert _has_edge(result, "apps/web/src/consumer.ts", "packages/pkg-a/src/index.ts")
    assert _has_edge(result, "apps/web/src/consumer.ts", "packages/pkg-a/src/mini/index.ts")


def test_tsconfig_custom_condition_follows_the_importers_own_config(tmp_path: Path):
    """The condition set belongs to the importing project. A sibling whose
    tsconfig overrides the inherited list with `[]` keeps the fixed walk's
    answer, here the built `dist/` file, like `tsc` does for zod's packages/tsc."""
    _write_source_condition_package(tmp_path, {
        ".": {"@example/source": "./src/source.ts", "default": "./dist/index.js"},
    })
    _write(tmp_path / "apps/web/tsconfig.json", '{"extends": "../../tsconfig.base.json"}')
    _write(
        tmp_path / "apps/admin/tsconfig.json",
        '{"extends": "../../tsconfig.base.json", "compilerOptions": {"customConditions": []}}',
    )
    source = _write(tmp_path / "packages/pkg-a/src/source.ts", "export const a = 1\n")
    built = _write(tmp_path / "packages/pkg-a/dist/index.js", "export const a = 2\n")
    web = _write(
        tmp_path / "apps/web/src/consumer.ts",
        "import { a } from '@example/pkg-a'\nexport const v = a\n",
    )
    admin = _write(
        tmp_path / "apps/admin/src/consumer.ts",
        "import { a } from '@example/pkg-a'\nexport const v = a\n",
    )

    result = _extract_for([source, built, web, admin], tmp_path)

    assert _has_edge(result, "apps/web/src/consumer.ts", "packages/pkg-a/src/source.ts")
    assert not _has_edge(result, "apps/web/src/consumer.ts", "packages/pkg-a/dist/index.js")
    assert _has_edge(result, "apps/admin/src/consumer.ts", "packages/pkg-a/dist/index.js")
    assert not _has_edge(result, "apps/admin/src/consumer.ts", "packages/pkg-a/src/source.ts")


def test_tsconfig_custom_condition_escaping_or_missing_target_keeps_the_v8_result(
    tmp_path: Path,
):
    """Fail closed: a custom-condition target that is not a real file, or that
    escapes the package directory, leaves the import where the fixed walk put
    it (the build output here)."""
    from graphify.extractors.resolution import _resolve_js_module_path

    _write_source_condition_package(tmp_path, {
        ".": {"@example/source": "./src/missing.ts", "default": "./dist/index.js"},
        "./widget": {"@example/source": "./../../secret.ts", "default": "./dist/widget.js"},
    })
    _write(tmp_path / "apps/web/tsconfig.json", '{"extends": "../../tsconfig.base.json"}')
    outside = _write(tmp_path / "secret.ts", "export const leak = 1\n")
    # The escaping target names a real file, so only the containment check
    # keeps it out; a missing file would pass this test for the wrong reason.
    assert (tmp_path / "packages/pkg-a/../../secret.ts").resolve() == outside.resolve()
    built = _write(tmp_path / "packages/pkg-a/dist/index.js", "export const a = 1\n")
    built_widget = _write(tmp_path / "packages/pkg-a/dist/widget.js", "export const w = 1\n")
    importer_dir = tmp_path / "apps/web/src"
    importer_dir.mkdir(parents=True)

    assert _resolve_js_module_path("@example/pkg-a", importer_dir) == built
    assert _resolve_js_module_path("@example/pkg-a/widget", importer_dir) == built_widget


def test_tsconfig_custom_condition_symlink_escape_keeps_the_v8_result(tmp_path: Path):
    """Containment is checked on the file finally reached. `./src/link.js` does
    not exist, the `.js` -> `.ts` rule finds `src/link.ts`, and that is a
    symlink to a file outside the package, so the custom target is refused."""
    from graphify.extractors.resolution import _resolve_js_module_path

    importer = _write_condition_importer(tmp_path, ["custom"], {
        ".": {"custom": "./src/link.js", "default": "./dist/index.js"},
    }, nested=False)
    outside = _write(tmp_path / "secret.ts", "export const leak = 1\n")
    built = _write(tmp_path / "packages/pkg-a/dist/index.js", "export const a = 1\n")
    link = tmp_path / "packages/pkg-a/src/link.ts"
    link.parent.mkdir(parents=True, exist_ok=True)
    try:
        link.symlink_to(outside)
    except OSError:
        pytest.skip("symlinks are not available on this platform")

    assert _resolve_js_module_path("@example/pkg-a", importer.parent) == built


def test_tsconfig_custom_condition_never_changes_an_import_v8_resolves_to_source(
    tmp_path: Path,
):
    """An unrelated custom condition must not move an import the fixed walk
    already resolves. `require` listed before `import`: v8 and tsc 5.9.3 give
    this ESM importer `esm.ts`; no export even uses "custom"."""
    importer = _write_condition_importer(tmp_path, ["custom"], {
        ".": {"require": "./src/cjs.ts", "import": "./src/esm.ts"},
    }, nested=False)
    files = [
        _write(tmp_path / f"packages/pkg-a/src/{name}.ts", "export const a = 1\n")
        for name in ("cjs", "esm")
    ]

    result = _extract_for([*files, importer], tmp_path)

    assert _has_edge(result, "apps/web/src/consumer.ts", "packages/pkg-a/src/esm.ts")
    assert not _has_edge(result, "apps/web/src/consumer.ts", "packages/pkg-a/src/cjs.ts")


def test_tsconfig_custom_condition_does_not_beat_an_earlier_export_key(tmp_path: Path):
    """A custom condition listed after `default`, at the top level or inside a
    nested condition object, does not displace the `default` file. tsc 5.9.3
    resolves both specifiers here to the `default` files too."""
    importer = _write_condition_importer(tmp_path, ["custom"], {
        ".": {"default": "./src/default.ts", "custom": "./src/custom.ts"},
        "./nested": {
            "types": "./dist/nested.d.ts",
            "import": {"default": "./src/nested-default.ts", "custom": "./src/nested-custom.ts"},
        },
    })
    files = [
        _write(tmp_path / f"packages/pkg-a/src/{name}.ts", "export const a = 1, n = 1\n")
        for name in ("default", "custom", "nested-default", "nested-custom")
    ]

    result = _extract_for([*files, importer], tmp_path)

    assert _has_edge(result, "apps/web/src/consumer.ts", "packages/pkg-a/src/default.ts")
    assert _has_edge(result, "apps/web/src/consumer.ts", "packages/pkg-a/src/nested-default.ts")
    assert not _has_edge(result, "apps/web/src/consumer.ts", "packages/pkg-a/src/custom.ts")
    assert not _has_edge(result, "apps/web/src/consumer.ts", "packages/pkg-a/src/nested-custom.ts")


def test_tsconfig_custom_condition_first_key_decides_not_list_order(tmp_path: Path):
    """The order inside `customConditions` is not a ranking. With ["b", "a"]
    and an exports object listing `a` first, tsc 5.9.3 picks `a`."""
    importer = _write_condition_importer(tmp_path, ["b", "a"], {
        ".": {"a": "./src/a.ts", "b": "./src/b.ts"},
    }, nested=False)
    files = [
        _write(tmp_path / f"packages/pkg-a/src/{name}.ts", "export const a = 1\n")
        for name in ("a", "b")
    ]

    result = _extract_for([*files, importer], tmp_path)

    assert _has_edge(result, "apps/web/src/consumer.ts", "packages/pkg-a/src/a.ts")
    assert not _has_edge(result, "apps/web/src/consumer.ts", "packages/pkg-a/src/b.ts")


def test_tsconfig_custom_condition_root_shorthand_target(tmp_path: Path):
    """A root condition object with no `"."` key is shorthand for
    `{".": {...}}`. The fixed walk ignores it and finds nothing here; tsc
    5.9.3 picks `src/shorthand.ts`."""
    importer = _write_condition_importer(tmp_path, ["custom"], {
        "custom": "./src/shorthand.ts", "import": "./dist/index.js",
    }, nested=False)
    target = _write(tmp_path / "packages/pkg-a/src/shorthand.ts", "export const a = 1\n")

    result = _extract_for([target, importer], tmp_path)

    assert _has_edge(result, "apps/web/src/consumer.ts", "packages/pkg-a/src/shorthand.ts")


def test_tsconfig_custom_condition_js_target_resolves_to_ts_sibling(tmp_path: Path):
    """tsc's first pass swaps `.js` for `.ts`, so `./src/thing.js` with only
    `src/thing.ts` on disk resolves to the TypeScript file (tsc 5.9.3 agrees)."""
    importer = _write_condition_importer(
        tmp_path, ["custom"], {".": {"custom": "./src/thing.js"}}, nested=False
    )
    target = _write(tmp_path / "packages/pkg-a/src/thing.ts", "export const a = 1\n")

    result = _extract_for([target, importer], tmp_path)

    assert _has_edge(result, "apps/web/src/consumer.ts", "packages/pkg-a/src/thing.ts")


def test_tsconfig_custom_conditions_layered_diamond_reads_each_config_once(
    tmp_path: Path, monkeypatch,
):
    """32 configs where each layer extends both configs of the layer below.
    Re-merging shared parents per branch read them 98,303 times; a finished
    merge is cached per path, so each config is read once."""
    from graphify.extractors import resolution

    _write(tmp_path / "base.json", json.dumps({"compilerOptions": {
        "moduleResolution": "bundler", "customConditions": ["custom"],
    }}))
    for layer in range(16):
        below = ["./base.json"] if layer == 0 else [f"./left{layer - 1}.json", f"./right{layer - 1}.json"]
        for side in ("left", "right"):
            _write(tmp_path / f"{side}{layer}.json", json.dumps({"extends": below}))
    reads = []
    original = resolution._read_json_config
    monkeypatch.setattr(resolution, "_read_json_config", lambda p: reads.append(p) or original(p))
    resolution._TSCONFIG_EXPORTS_OPTIONS_CACHE.clear()

    options = resolution._read_tsconfig_exports_options(tmp_path / "left15.json")

    assert options is not None and options["customConditions"] == ["custom"]
    assert len(reads) == len(set(reads)) == 32


def test_tsconfig_custom_condition_missing_target_keeps_the_v8_fallback(tmp_path: Path):
    """When the custom target is missing, resolution is what it was without
    customConditions: here the conventional `src/index` entry."""
    importer = _write_condition_importer(
        tmp_path, ["custom"], {".": {"custom": "./src/missing.ts"}}, nested=False
    )
    entry = _write(tmp_path / "packages/pkg-a/src/index.ts", "export const a = 1\n")

    result = _extract_for([entry, importer], tmp_path)

    assert _has_edge(result, "apps/web/src/consumer.ts", "packages/pkg-a/src/index.ts")


def test_tsconfig_custom_conditions_config_rules(tmp_path: Path):
    """When the importer's options are known the way tsc knows them, and
    when they rule the fallback out.

    compilerOptions merge key by key over `extends`: a later array entry
    beats an earlier one, a parent shared by two branches is read in both, and
    the nearest config that sets a key wins; a suffix-less relative `extends`
    gets `.json`. Unknown options (a package-name `extends` anywhere in the
    chain, a parent that does not parse, a cycle) turn the fallback off, as do
    the node10 default, `resolvePackageJsonExports: false`, `moduleSuffixes`,
    any `outDir` or `declarationDir` (even `""`), a `paths` key that could
    take the specifier first, any `baseUrl` at all, a `${configDir}` template
    (not expanded here) in a path option, set directly or inherited, and a
    non-string condition."""
    from graphify.extractors.resolution import _load_tsconfig_custom_conditions

    def conditions(directory: str, _package: Path, specifier: str = "@example/pkg-a"):
        return _load_tsconfig_custom_conditions(tmp_path / directory, specifier)

    def config(path: str, data: dict | str) -> None:
        _write(tmp_path / path, data if isinstance(data, str) else json.dumps(data))

    bundler = {"module": "esnext", "moduleResolution": "bundler"}
    other = tmp_path / "packages/other"
    other.mkdir(parents=True)
    config("configs/first.json", {"compilerOptions": {**bundler, "customConditions": ["first"]}})
    config("configs/second.json", {"extends": "./second.base"})
    config("configs/second.base.json", {"compilerOptions": {"customConditions": ["second"]}})
    config("nonstring/tsconfig.json", {"compilerOptions": {**bundler, "customConditions": ["c", 7]}})
    config("array/tsconfig.json", {"extends": ["../configs/first.json", "../configs/second.json"]})
    config("diamond/shared.json", {"compilerOptions": {**bundler, "customConditions": []}})
    config("diamond/left.json", {"extends": "./shared.json", "compilerOptions": {"customConditions": ["c"]}})
    config("diamond/right.json", {"extends": "./shared.json"})
    config("diamond/tsconfig.json", {"extends": ["./left.json", "./right.json"]})
    config("pkgparent/tsconfig.json", {
        "extends": "@tsconfig/strictest/tsconfig.json",
        "compilerOptions": {**bundler, "customConditions": ["c"]},
    })
    config("deep/base.json", {"extends": "@tsconfig/strictest/tsconfig.json"})
    config("deep/tsconfig.json", {
        "extends": "./base.json", "compilerOptions": {**bundler, "customConditions": ["c"]},
    })
    config("broken/base.json", "{ not json")
    config("broken/tsconfig.json", {
        "extends": "./base.json", "compilerOptions": {**bundler, "customConditions": ["c"]},
    })
    config("cycle/a.json", {"extends": "./tsconfig.json"})
    config("cycle/tsconfig.json", {"extends": "./a.json", "compilerOptions": {**bundler, "customConditions": ["c"]}})
    config("node10/tsconfig.json", {"compilerOptions": {"customConditions": ["c"]}})
    config("nodenext/tsconfig.json", {"compilerOptions": {"module": "nodenext", "customConditions": ["c"]}})
    config("off/base.json", {"compilerOptions": {**bundler, "resolvePackageJsonExports": False}})
    config("off/tsconfig.json", {"extends": "./base.json", "compilerOptions": {"customConditions": ["c"]}})
    config("suffixes/base.json", {"compilerOptions": {"moduleSuffixes": [".ios", ""]}})
    config("suffixes/tsconfig.json", {
        "extends": "./base.json", "compilerOptions": {**bundler, "customConditions": ["c"]},
    })
    config("nosuffix/tsconfig.json", {"compilerOptions": {**bundler, "customConditions": ["c"], "moduleSuffixes": [""]}})
    config("aliased/tsconfig.json", {"compilerOptions": {
        **bundler, "customConditions": ["c"], "paths": {"@example/*": ["./vendor/*"]},
    }})
    config("based/tsconfig.json", {"compilerOptions": {**bundler, "customConditions": ["c"], "baseUrl": "./lib"}})
    config("based-parent/base.json", {"compilerOptions": {"baseUrl": "./nowhere"}})
    config("based-parent/tsconfig.json", {
        "extends": "./base.json", "compilerOptions": {**bundler, "customConditions": ["c"]},
    })
    config("templated/tsconfig.json", {"compilerOptions": {
        **bundler, "customConditions": ["c"], "typeRoots": ["${configDir}/types"],
    }})
    config("templated-parent/base.json", {"compilerOptions": {"paths": {"x/*": ["${configDir}/x/*"]}}})
    config("templated-parent/tsconfig.json", {
        "extends": "./base.json", "compilerOptions": {**bundler, "customConditions": ["c"]},
    })
    _write(tmp_path / "based/lib/@example/pkg-a/index.ts", "export const a = 1\n")
    self_pkg = tmp_path / "packages/self"
    config("packages/self/tsconfig.json", {"compilerOptions": {**bundler, "customConditions": ["c"], "outDir": "dist"}})
    config("emptyout/tsconfig.json", {"compilerOptions": {**bundler, "customConditions": ["c"], "outDir": ""}})
    config("emptydecl/tsconfig.json", {"compilerOptions": {
        **bundler, "customConditions": ["c"], "declarationDir": "",
    }})
    (tmp_path / "array/src/deep").mkdir(parents=True)

    assert conditions("array/src/deep", other) == ("second",)
    assert conditions("diamond", other) == ()
    assert conditions("pkgparent", other) == ()
    assert conditions("deep", other) == ()
    assert conditions("broken", other) == ()
    assert conditions("cycle", other) == ()
    assert conditions("node10", other) == ()
    assert conditions("nodenext", other) == ("c",)
    assert conditions("off", other) == ()
    assert conditions("suffixes", other) == ()
    assert conditions("nosuffix", other) == ("c",)
    assert conditions("aliased", other) == ()
    assert conditions("aliased", other, "@other/pkg") == ("c",)
    assert conditions("based", other) == ()
    assert conditions("based", other, "@example/pkg-b") == ()
    assert conditions("based-parent", other) == ()
    assert conditions("templated", other) == ()
    assert conditions("templated-parent", other) == ()
    assert conditions("packages/self", self_pkg) == ()
    assert conditions("packages/self", other) == ()
    assert conditions("emptyout", other) == ()
    assert conditions("emptydecl", other) == ()
    assert conditions("nonstring", other) == ()


_KEEPS_V8_EXPORTS = [
    # (exports["."], files on disk, extra compilerOptions, v8's result, a file the
    #  import must not reach). The first twelve are reviewer fixtures where an
    #  earlier revision of this PR picked that file while tsc 5.9.3 resolves
    #  them to a declaration, another file, or nothing. The last seven are
    #  targets tsc does resolve to that file, which the fallback deliberately
    #  leaves to v8: `//` and `\\` spellings, and the unsupported shapes.
    pytest.param(
        {"default": "./dist/runtime.d.ts", "custom": "./src/custom.ts"},
        ["dist/runtime.d.ts", "src/custom.ts"], None, "dist/runtime.d.ts", "src/custom.ts",
        id="earlier-default-target-exists",
    ),
    pytest.param(
        {"custom": ["./dist/runtime.d.ts", "./src/custom.ts"]},
        ["dist/runtime.d.ts", "src/custom.ts"], None, None, "src/custom.ts",
        id="earlier-array-entry-exists",
    ),
    pytest.param(
        {"custom": "./src/component"},
        ["src/component/index.ts"], None, None, "src/component/index.ts",
        id="directory-target",
    ),
    pytest.param(
        {"custom": "./src/component.js"},
        ["src/component.js.ts"], None, None, "src/component.js.ts",
        id="appended-extension",
    ),
    pytest.param(
        {"custom": "./src/../private.ts"},
        # src/ exists, so only the segment rule (not the OS) refuses `src/..`.
        ["private.ts", "src/other.ts"], None, None, "private.ts",
        id="internal-traversal",
    ),
    pytest.param(
        {"custom": "./src/custom.ts"},
        ["src/custom.ts"], {"resolvePackageJsonExports": False}, None, "src/custom.ts",
        id="exports-resolution-off",
    ),
    pytest.param(
        {"custom": {"require": "./src/cjs.ts", "import": "./src/esm.ts"}},
        ["src/cjs.ts", "src/esm.ts"], None, None, "src/cjs.ts",
        id="custom-key-around-require-and-import",
    ),
    pytest.param(
        {"custom": ["./src//first.ts", "./src/second.ts"]},
        ["src/first.ts", "src/second.ts"], None, None, "src/second.ts",
        id="double-slash-array-entry",
    ),
    pytest.param(
        {"custom": ["./src\\first.ts", "./src/second.ts"]},
        ["src/first.ts", "src/second.ts"], None, None, "src/second.ts",
        id="backslash-array-entry",
    ),
    pytest.param(
        {"custom": "./src/first.js", "second": "./src/second.ts"},
        ["src/first.js", "src/second.ts"], {"customConditions": ["custom", "second"]},
        None, "src/first.js",
        id="javascript-first-target-typescript-later",
    ),
    pytest.param(
        {"custom": "./src\\custom.ts"},
        # On Linux both a literal `src\custom.ts` file and `src/custom.ts` exist.
        ["src\\custom.ts", "src/custom.ts"], None, None, "src\\custom.ts",
        id="backslash-target-with-literal-file",
    ),
    pytest.param(
        {"custom": "./src/custom.ts", "0": "./src/zero.ts"},
        ["src/custom.ts", "src/zero.ts"], {"customConditions": ["custom", "0"]},
        None, "src/custom.ts",
        id="integer-like-key-enumerates-first",
    ),
    pytest.param(
        {"custom": "./src//double.ts"},
        ["src/double.ts"], None, None, "src/double.ts",
        id="double-slash-target",
    ),
    pytest.param(
        {"custom": "./src\\back.ts"},
        ["src/back.ts"], None, None, "src/back.ts",
        id="backslash-target",
    ),
    pytest.param(
        {"custom": "./src/only.js"},
        ["src/only.js"], None, None, "src/only.js",
        id="unsupported-javascript-only-target",
    ),
    pytest.param(
        {"default": None, "custom": "./src/custom.ts"},
        ["src/custom.ts"], None, None, "src/custom.ts",
        id="unsupported-null-before-custom",
    ),
    pytest.param(
        {"custom": ["./src/custom.ts"]},
        ["src/custom.ts"], None, None, "src/custom.ts",
        id="unsupported-array-target",
    ),
    pytest.param(
        {"custom": {"custom": "./src/custom.ts"}},
        ["src/custom.ts"], None, None, "src/custom.ts",
        id="unsupported-nested-object",
    ),
    pytest.param(
        {"import": "./dist/index.js", "custom": "./src/custom.ts"},
        ["src/custom.ts"], None, None, "src/custom.ts",
        id="unsupported-custom-not-first",
    ),
]


@pytest.mark.parametrize("exports, files, options, v8_result, not_target", _KEEPS_V8_EXPORTS)
def test_tsconfig_custom_condition_keeps_v8_outside_the_supported_shape(
    tmp_path: Path, exports, files, options, v8_result, not_target,
):
    """Only `{"<custom>": "./<file>", ...}` with the custom key first is
    handled. Everything else, and every target tsc would refuse or resolve
    differently, keeps exactly v8's result."""
    from graphify.extractors.resolution import _resolve_js_module_path

    importer = _write_condition_importer(
        tmp_path, ["custom"], {".": exports}, nested=False, extra_options=options
    )
    written = [
        _write(tmp_path / "packages/pkg-a" / name, "export const a = 1\n") for name in files
    ]

    resolved = _resolve_js_module_path("@example/pkg-a", importer.parent)
    result = _extract_for([*written, importer], tmp_path)

    expected = None if v8_result is None else tmp_path / "packages/pkg-a" / v8_result
    assert resolved == expected
    assert not _has_edge(result, "apps/web/src/consumer.ts", f"packages/pkg-a/{not_target}")


def test_tsconfig_custom_condition_keeps_v8_for_wildcard_exports(tmp_path: Path):
    """`*` patterns are not handled: `pkg/feature/a` stays where v8 left it
    even though tsc 5.9.3 maps it through `./feature/*`."""
    from graphify.extractors.resolution import _resolve_js_module_path

    importer = _write_condition_importer(tmp_path, ["custom"], {
        "./*": {"custom": "./src/broad/*.ts"},
        "./feature/*": {"custom": "./src/specific/*.ts"},
    }, nested=False)
    importer.write_text("import { a } from '@example/pkg-a/feature/a'\n", encoding="utf-8")
    for name in ("broad/feature/a", "specific/a"):
        _write(tmp_path / f"packages/pkg-a/src/{name}.ts", "export const a = 1\n")

    assert _resolve_js_module_path("@example/pkg-a/feature/a", importer.parent) is None


@pytest.mark.parametrize(
    "layout", ["diamond", "package-name-parent-with-module-suffixes", "configdir-baseurl"]
)
def test_tsconfig_custom_condition_keeps_v8_when_inherited_options_say_so(
    tmp_path: Path, layout,
):
    """REVIEW-4 config fixtures. Diamond: the importer extends [left, right],
    both extend shared (`customConditions: []`); only left sets ["custom"], so
    tsc ends with [] from right and reports the import unresolved. Package
    parent: the importer extends `@fixture/config/tsconfig.json`, whose
    `moduleSuffixes` make tsc pick `custom.ios.ts`; a package-name parent is
    not resolved here, so the fallback stays off. `${configDir}` baseUrl: tsc
    expands it and finds `apps/web/vendor/@example/pkg-a.ts` first; templates
    are not expanded here, so the fallback stays off. All keep v8's stub."""
    from graphify.extractors.resolution import _resolve_js_module_path

    _write_workspace_package(tmp_path, "@example/pkg-a", {".": {"custom": "./src/custom.js"}})
    files = [_write(tmp_path / "packages/pkg-a/src/custom.ts", "export const a = 1\n")]
    bundler = {"module": "esnext", "moduleResolution": "bundler"}
    if layout == "diamond":
        _write(tmp_path / "configs/shared.json", json.dumps(
            {"compilerOptions": {**bundler, "customConditions": []}}))
        _write(tmp_path / "configs/left.json", json.dumps(
            {"extends": "./shared.json", "compilerOptions": {"customConditions": ["custom"]}}))
        _write(tmp_path / "configs/right.json", json.dumps({"extends": "./shared.json"}))
        importer_config = {"extends": ["../../configs/left.json", "../../configs/right.json"]}
    elif layout == "configdir-baseurl":
        files.append(_write(tmp_path / "apps/web/vendor/@example/pkg-a.ts", "export const a = 3\n"))
        importer_config = {"compilerOptions": {
            **bundler, "customConditions": ["custom"], "baseUrl": "${configDir}/vendor",
        }}
    else:
        files.append(_write(tmp_path / "packages/pkg-a/src/custom.ios.ts", "export const a = 2\n"))
        _write(tmp_path / "node_modules/@fixture/config/package.json", '{"name": "@fixture/config"}')
        _write(tmp_path / "node_modules/@fixture/config/tsconfig.json", json.dumps(
            {"compilerOptions": {"moduleSuffixes": [".ios", ""]}}))
        importer_config = {
            "extends": "@fixture/config/tsconfig.json",
            "compilerOptions": {**bundler, "customConditions": ["custom"]},
        }
    _write(tmp_path / "apps/web/tsconfig.json", json.dumps(importer_config))
    importer = _write(
        tmp_path / "apps/web/src/consumer.ts",
        "import { a } from '@example/pkg-a'\nexport const v = a\n",
    )

    resolved = _resolve_js_module_path("@example/pkg-a", importer.parent)
    result = _extract_for([*files, importer], tmp_path)

    assert resolved is None
    assert not _has_edge(result, "apps/web/src/consumer.ts", "packages/pkg-a/src/custom.ts")


def test_tsconfig_custom_conditions_refuse_symlinked_configs(tmp_path: Path):
    """tsc reads every config through its lexical path and resolves relative
    options from there. A config that is a symlink, or is reached through a
    symlinked directory, turns the fallback off rather than risk reading
    those options from the wrong directory."""
    from graphify.extractors.resolution import _load_tsconfig_custom_conditions

    other = tmp_path / "packages/other"
    other.mkdir(parents=True)
    options = {"compilerOptions": {
        "module": "esnext", "moduleResolution": "bundler", "customConditions": ["c"],
    }}
    _write(tmp_path / "real/tsconfig.json", json.dumps(options))
    _write(tmp_path / "shared/base.json", json.dumps(options))
    (tmp_path / "own").mkdir()
    (tmp_path / "via-dir").mkdir()
    _write(tmp_path / "via-dir/tsconfig.json", json.dumps({"extends": "./linked/base.json"}))
    try:
        (tmp_path / "own/tsconfig.json").symlink_to(tmp_path / "real/tsconfig.json")
        (tmp_path / "via-dir/linked").symlink_to(tmp_path / "shared", target_is_directory=True)
    except OSError:
        pytest.skip("symlinks are not available on this platform")

    assert _load_tsconfig_custom_conditions(tmp_path / "real", "@example/pkg-a") == ("c",)
    assert _load_tsconfig_custom_conditions(tmp_path / "own", "@example/pkg-a") == ()
    assert _load_tsconfig_custom_conditions(tmp_path / "via-dir", "@example/pkg-a") == ()


@pytest.mark.parametrize(
    "case", ["inherited-baseurl-js", "direct-baseurl-mjs", "symlinked-parent-config"]
)
def test_tsconfig_custom_condition_keeps_v8_when_tsc_may_resolve_elsewhere(
    tmp_path: Path, case,
):
    """REVIEW-6 fixtures. tsc 5.9.3 resolves each import outside the
    package: `<baseUrl>/@example/pkg-a/feature.js` swaps to an existing `.ts`
    (inherited baseUrl), `.mjs` swaps to `.mts` (direct baseUrl), and a parent
    config reached through a symlink has a `baseUrl` that tsc reads from the
    link's directory. Any `baseUrl` and any symlinked config turn the
    fallback off, so each import keeps v8's stub."""
    from graphify.extractors.resolution import _resolve_js_module_path

    specifier = {
        "inherited-baseurl-js": "@example/pkg-a/feature.js",
        "direct-baseurl-mjs": "@example/pkg-a/feature.mjs",
    }.get(case, "@example/pkg-a")
    key = "." if specifier == "@example/pkg-a" else "./" + specifier.split("/", 2)[2]
    _write_workspace_package(tmp_path, "@example/pkg-a", {key: {"custom": "./src/custom.ts"}})
    files = [_write(tmp_path / "packages/pkg-a/src/custom.ts", "export const a = 1\n")]
    options = {"module": "esnext", "moduleResolution": "bundler", "customConditions": ["custom"]}
    config: dict = {"compilerOptions": options}
    if case == "inherited-baseurl-js":
        _write(tmp_path / "base.json", json.dumps({"compilerOptions": {"baseUrl": "./vendor"}}))
        config["extends"] = "../../base.json"
        files.append(_write(tmp_path / "vendor/@example/pkg-a/feature.ts", "export const a = 2\n"))
    elif case == "direct-baseurl-mjs":
        options["baseUrl"] = "./vendor"
        files.append(_write(tmp_path / "apps/web/vendor/@example/pkg-a/feature.mts", "export const a = 2\n"))
    else:
        shared = _write(tmp_path / "configs/shared.json", json.dumps({"compilerOptions": {"baseUrl": "./vendor"}}))
        (tmp_path / "apps/web").mkdir(parents=True)
        try:
            (tmp_path / "apps/web/base.json").symlink_to(shared)
        except OSError:
            pytest.skip("symlinks are not available on this platform")
        config["extends"] = "./base.json"
        files.append(_write(tmp_path / "apps/web/vendor/@example/pkg-a.ts", "export const a = 2\n"))
    _write(tmp_path / "apps/web/tsconfig.json", json.dumps(config))
    importer = _write(
        tmp_path / "apps/web/src/consumer.ts",
        f"import {{ a }} from '{specifier}'\nexport const v = a\n",
    )

    resolved = _resolve_js_module_path(specifier, importer.parent)
    result = _extract_for([*files, importer], tmp_path)

    assert resolved is None
    assert not _has_edge(result, "apps/web/src/consumer.ts", "packages/pkg-a/src/custom.ts")


@pytest.mark.parametrize(
    "case",
    ["empty-outdir", "empty-declarationdir", "pattern-precedence", "multi-star", "jsonc-condition"],
)
def test_tsconfig_custom_condition_keeps_v8_for_output_dirs_patterns_and_jsonc(
    tmp_path: Path, case,
):
    """REVIEW-7 fixtures; v8 leaves each one unresolved.

    - A self-import with `rootDir: ./src` and `outDir` or `declarationDir` set
      to `""`: tsc maps `./lib/custom.js` to `src/lib/custom.ts`. Any outDir or
      declarationDir turns the fallback off.
    - `pkg-a/feature/` with `"./feature/"` and `"./feature/*"` keys: tsc picks
      the pattern target. `pkg-a/foo/**` against a literal `"./foo/**"` key:
      tsc leaves it unresolved. Requests containing `*` or ending in `/` are
      refused.
    - A JSONC config with `"customConditions": ["custom,}"]`: the shared
      JSONC parser reads it as `custom}`, so the condition is refused unless
      it appears verbatim in the file. tsc leaves the import unresolved."""
    from graphify.extractors.resolution import _resolve_js_module_path

    options: dict = {"module": "esnext", "moduleResolution": "bundler", "customConditions": ["custom"]}
    specifier = "@example/pkg-a"
    exports: dict = {".": {"custom": "./lib/custom.ts"}}
    names = ["lib/custom.ts"]
    config_dir = tmp_path / "apps/web"
    if case in ("empty-outdir", "empty-declarationdir"):
        config_dir = tmp_path / "packages/pkg-a"
        options.update({"rootDir": "./src", "outDir" if case == "empty-outdir" else "declarationDir": ""})
        exports = {".": {"custom": "./lib/custom.js"}}
        names.append("src/lib/custom.ts")
    elif case == "pattern-precedence":
        specifier = "@example/pkg-a/feature/"
        exports = {"./feature/": {"custom": "./lib/custom.ts"}, "./feature/*": {"custom": "./lib/other.ts"}}
        names.append("lib/other.ts")
    elif case == "multi-star":
        specifier = "@example/pkg-a/foo/**"
        exports = {"./foo/**": {"custom": "./lib/custom.ts"}}
    elif case == "jsonc-condition":
        options["customConditions"] = ["custom,}"]
        exports = {".": {"custom}": "./lib/custom.ts"}}
    _write_workspace_package(tmp_path, "@example/pkg-a", exports)
    config_text = json.dumps({"compilerOptions": options})
    if case == "jsonc-condition":
        config_text = "// comment\n" + config_text
    config = _write(config_dir / "tsconfig.json", config_text)
    importer = _write(config_dir / "consumer.ts", f"import {{ a }} from '{specifier}'\nexport const v = a\n")
    files = [_write(tmp_path / "packages/pkg-a" / name, "export const a = 1\n") for name in names]

    if case == "jsonc-condition":
        from graphify.extractors.resolution import _read_json_config, _read_tsconfig_exports_options

        # The shared parser alters the string; the fallback must not use it.
        parsed = _read_json_config(config)
        merged = _read_tsconfig_exports_options(config)
        assert parsed is not None and parsed["compilerOptions"]["customConditions"] == ["custom}"]
        assert merged is not None and merged["customConditions"] is None
    resolved = _resolve_js_module_path(specifier, importer.parent)
    result = _extract_for([*files, importer], tmp_path)

    assert resolved is None
    importer_rel = importer.relative_to(tmp_path).as_posix()
    assert not _has_edge(result, importer_rel, "packages/pkg-a/lib/custom.ts")


def test_tsconfig_custom_conditions_refresh_between_extract_calls(tmp_path: Path):
    """The per-config cache has no mtime component, so extract() must clear it
    per run, like the alias cache (#2917). `graphify watch` and the MCP server
    rebuild in one process and would otherwise keep the old condition list."""
    _write_source_condition_package(tmp_path, {
        ".": {"@example/source": "./src/source.ts", "default": "./dist/index.js"},
    })
    config = _write(
        tmp_path / "apps/web/tsconfig.json", '{"extends": "../../tsconfig.base.json"}'
    )
    source = _write(tmp_path / "packages/pkg-a/src/source.ts", "export const a = 1\n")
    built = _write(tmp_path / "packages/pkg-a/dist/index.js", "export const a = 2\n")
    importer = _write(
        tmp_path / "apps/web/src/consumer.ts",
        "import { a } from '@example/pkg-a'\nexport const v = a\n",
    )

    first = _extract_for([source, built, importer], tmp_path)
    assert _has_edge(first, "apps/web/src/consumer.ts", "packages/pkg-a/src/source.ts")

    config.write_text(
        '{"compilerOptions": {"moduleResolution": "bundler", "customConditions": []}}',
        encoding="utf-8",
    )
    second = _extract_for([source, built, importer], tmp_path)

    assert _has_edge(second, "apps/web/src/consumer.ts", "packages/pkg-a/dist/index.js")
    assert not _has_edge(second, "apps/web/src/consumer.ts", "packages/pkg-a/src/source.ts")
