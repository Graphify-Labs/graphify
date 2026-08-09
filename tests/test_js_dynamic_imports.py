"""`import('…')` in plain .ts/.js must produce an edge.

tree-sitter models ``await import('x')`` as a ``call_expression``, not an
``import_statement``, so the specifier never reaches the import walk. The
Svelte/Astro/Vue extractors already compensate with a regex pass; plain JS/TS
did not, because its AST pass "works" — for STATIC imports. The dynamic ones
fell through silently, which matters most in codebases that use dynamic import
deliberately to break require cycles: those edges sit under the hub modules, so
the loss compounds with traversal depth in ``graphify affected``.
"""
from __future__ import annotations

import json
from pathlib import Path

from graphify.affected import DEFAULT_AFFECTED_RELATIONS
from graphify.extract import _file_node_id, extract


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _has_edge(result: dict, source: str, target: str, relation: str) -> bool:
    expected = (_file_node_id(Path(source)), _file_node_id(Path(target)), relation)
    return expected in {
        (e["source"], e["target"], e["relation"]) for e in result["edges"]
    }


def test_relative_dynamic_import_edges(tmp_path: Path):
    target = _write(tmp_path / "src/lib/foo.ts", "export const foo = 1\n")
    importer = _write(
        tmp_path / "src/lib/page.ts",
        "export async function load() {\n"
        "    const { foo } = await import('./foo')\n"
        "    return foo\n"
        "}\n",
    )

    result = extract([target, importer], cache_root=tmp_path)

    assert _has_edge(result, "src/lib/page.ts", "src/lib/foo.ts", "dynamic_import")


def test_multi_level_relative_dynamic_import_edges(tmp_path: Path):
    target = _write(tmp_path / "src/runner.ts", "export const run = () => 1\n")
    importer = _write(
        tmp_path / "src/tools/impl/delegate.ts",
        "export async function go() {\n"
        "    const { run } = await import('../../runner')\n"
        "    return run()\n"
        "}\n",
    )

    result = extract([target, importer], cache_root=tmp_path)

    assert _has_edge(result, "src/tools/impl/delegate.ts", "src/runner.ts", "dynamic_import")


def test_tsconfig_aliased_dynamic_import_edges(tmp_path: Path):
    _write(
        tmp_path / "tsconfig.json",
        json.dumps({"compilerOptions": {"baseUrl": ".", "paths": {"@/*": ["./src/*"]}}}),
    )
    target = _write(tmp_path / "src/agent/runner.ts", "export const run = () => 1\n")
    importer = _write(
        tmp_path / "src/stores/store.ts",
        "export async function send() {\n"
        "    const { run } = await import('@/agent/runner')\n"
        "    return run()\n"
        "}\n",
    )

    result = extract([target, importer], cache_root=tmp_path)

    assert _has_edge(result, "src/stores/store.ts", "src/agent/runner.ts", "dynamic_import")


def test_static_import_still_edges_alongside_a_dynamic_one(tmp_path: Path):
    """The rescue pass must not disturb the AST pass it runs beside."""
    a = _write(tmp_path / "src/a.ts", "export const a = 1\n")
    b = _write(tmp_path / "src/b.ts", "export const b = 2\n")
    importer = _write(
        tmp_path / "src/main.ts",
        "import { a } from './a'\n"
        "export async function later() {\n"
        "    const { b } = await import('./b')\n"
        "    return a + b\n"
        "}\n",
    )

    result = extract([a, b, importer], cache_root=tmp_path)

    assert _has_edge(result, "src/main.ts", "src/a.ts", "imports_from")
    assert _has_edge(result, "src/main.ts", "src/b.ts", "dynamic_import")


def test_identifier_ending_in_import_is_not_matched(tmp_path: Path):
    """`fooimport('./x')` is a call to `fooimport`, not a dynamic import."""
    target = _write(tmp_path / "src/x.ts", "export const x = 1\n")
    importer = _write(
        tmp_path / "src/caller.ts",
        "declare function fooimport(s: string): unknown\n"
        "export const r = fooimport('./x')\n",
    )

    result = extract([target, importer], cache_root=tmp_path)

    assert not _has_edge(result, "src/caller.ts", "src/x.ts", "dynamic_import")


def test_dynamic_import_is_traversed_by_affected():
    """Emitting the edge is only half the fix.

    ``graphify affected`` walks ``DEFAULT_AFFECTED_RELATIONS``; while
    ``dynamic_import`` was absent from it, every dynamic edge stayed invisible to
    blast-radius traversal — including the ones the Svelte/Astro/Vue rescue
    passes had been emitting all along.
    """
    assert "dynamic_import" in DEFAULT_AFFECTED_RELATIONS
