from __future__ import annotations

import json
from pathlib import Path

import pytest

from graphify.extract import _file_node_id, _file_stem, _make_id, extract


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _extract_for(paths: list[Path], root: Path):
    return extract(paths, cache_root=root)


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
    import_targets = {
        e["target"]
        for e in result["edges"]
        if e["relation"] == "imports_from" and e["source"] == _file_node_id(Path("src/components/Button.tsx"))
    }
    assert target_id in import_targets
    # No surviving edge target may carry an absolute-path prefix from tmp_path.
    abs_prefix = _file_node_id(Path("src/lib/utils.ts").resolve())
    assert all(not t.startswith(abs_prefix + "_") and t != abs_prefix for t in import_targets)

    # The named-symbol edge to formatDate must resolve to the real symbol node too.
    assert _has_symbol_edge(result, "src/components/Button.tsx", "src/lib/utils.ts", "formatDate")
