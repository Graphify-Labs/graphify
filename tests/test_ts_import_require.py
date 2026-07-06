"""Regression tests for the TypeScript import-equals form: `import x = require("./m")`.

Before the fix, the module string of an import-equals declaration was invisible:
tree-sitter parses it as an `import_statement` whose string sits inside an
`import_require_clause`, not as a direct child of the statement — so the
direct-child string scan in `_import_js` never found it and the file produced
no `imports_from` edge at all (while the equivalent ESM `import * as x from
"./m"` did). The fix gives the import-equals form exact parity with the ESM
namespace import: one file-level `imports_from` edge.
"""
from __future__ import annotations

from pathlib import Path

from graphify.extract import _file_node_id, _make_id, extract


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _has_edge(result: dict, source: str, target: str, relation: str = "imports_from") -> bool:
    expected = (_file_node_id(Path(source)), _file_node_id(Path(target)), relation)
    actual = {
        (edge["source"], edge["target"], edge["relation"])
        for edge in result["edges"]
    }
    return expected in actual


def test_import_require_relative_emits_file_edge(tmp_path: Path):
    target = _write(tmp_path / "src/lib/legacy.ts", "export function foo(): number { return 1 }\n")
    importer = _write(
        tmp_path / "src/lib/consumer.ts",
        'import legacy = require("./legacy");\nconst n = legacy.foo();\n',
    )

    result = extract([target, importer], cache_root=tmp_path)

    assert _has_edge(result, "src/lib/consumer.ts", "src/lib/legacy.ts")


def test_import_require_single_quotes(tmp_path: Path):
    target = _write(tmp_path / "src/util.ts", "export const V = 1\n")
    importer = _write(
        tmp_path / "src/main.ts",
        "import util = require('./util');\nexport const x = util.V;\n",
    )

    result = extract([target, importer], cache_root=tmp_path)

    assert _has_edge(result, "src/main.ts", "src/util.ts")


def test_import_require_bare_module_targets_ref_stub(tmp_path: Path):
    # A bare module (`require("fs")`) is external, so it emits an imports_from
    # edge to a ref-namespaced stub — NOT the bare `_make_id("fs")` id, which
    # would collide with any local file named fs.* via build.py's alias index
    # (#1638). Parity with the ESM external path (test_external_module_unchanged).
    importer = _write(
        tmp_path / "src/io.ts",
        'import fs = require("fs");\nexport const data = fs.readFileSync("x");\n',
    )

    result = extract([importer], cache_root=tmp_path)

    src = _file_node_id(Path("src/io.ts"))
    import_targets = {
        e["target"] for e in result["edges"]
        if e["source"] == src and e["relation"] == "imports_from"
    }
    # An external stub edge still exists...
    assert import_targets, "bare-module import-equals should still emit an external stub edge"
    # ...but it is ref-namespaced and never the bare, collision-prone id.
    assert _make_id("fs") not in import_targets
    assert any(t.startswith("ref") for t in import_targets), import_targets


def test_import_require_parity_with_namespace_import(tmp_path: Path):
    """`import x = require("./m")` must produce the same file-level edge as
    `import * as x from "./m"` — no more, no less."""
    _write(tmp_path / "a/dep.ts", "export function f() {}\n")
    req = _write(tmp_path / "a/via_require.ts", 'import dep = require("./dep");\ndep.f();\n')
    esm = _write(tmp_path / "a/via_esm.ts", 'import * as dep from "./dep";\ndep.f();\n')

    result = extract([tmp_path / "a/dep.ts", req, esm], cache_root=tmp_path)

    def edges_from(source_file: str):
        src = _file_node_id(Path(source_file))
        return sorted(
            (e["target"], e["relation"])
            for e in result["edges"]
            if e["source"] == src and e["relation"] != "contains"
        )

    assert _has_edge(result, "a/via_require.ts", "a/dep.ts")
    assert edges_from("a/via_require.ts") == edges_from("a/via_esm.ts")


def test_esm_imports_unaffected(tmp_path: Path):
    """Regression guard: the restructured string scan must not change ESM handling
    (file-level edge + named-import symbol edge both still emitted)."""
    target = _write(tmp_path / "src/bar.ts", "export class Bar {}\n")
    importer = _write(
        tmp_path / "src/app.ts",
        'import { Bar } from "./bar";\nexport const b = new Bar();\n',
    )

    result = extract([target, importer], cache_root=tmp_path)

    assert _has_edge(result, "src/app.ts", "src/bar.ts")
    src = _file_node_id(Path("src/app.ts"))
    sym = [
        e for e in result["edges"]
        if e["source"] == src and e["relation"] == "imports"
    ]
    assert sym, "named-import symbol edge should still be emitted"
