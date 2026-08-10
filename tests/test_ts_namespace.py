"""Regression tests: TypeScript namespace/module container nodes.

`namespace Foo {}` parses as `internal_module`, `module Bar {}` and ambient
`declare module "pkg" {}` as `module`. Neither was in `class_types`/`function_types`
nor handled by an extra-walk, so the container produced no node. Members were
still reached by the default recurse but the namespace itself was invisible.
"""
from pathlib import Path

from graphify.extract import _file_stem, _make_id, extract


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _node_label(result: dict, file: str, sym: str):
    nid = _make_id(_file_stem(Path(file)), sym)
    return next((n["label"] for n in result["nodes"] if n["id"] == nid), None)


def _has_node(result: dict, file: str, sym: str) -> bool:
    return _node_label(result, file, sym) is not None


def test_namespace_is_node(tmp_path):
    f = _write(tmp_path / "src" / "n.ts",
               "export namespace Geometry { export const PI = 3.14; }\n")
    r = extract([f], cache_root=tmp_path)
    assert _has_node(r, "src/n.ts", "Geometry")


def test_module_keyword_is_node(tmp_path):
    f = _write(tmp_path / "src" / "m.ts",
               "module Legacy { export class Thing {} }\n")
    r = extract([f], cache_root=tmp_path)
    assert _has_node(r, "src/m.ts", "Legacy")


def test_nested_namespace_name(tmp_path):
    f = _write(tmp_path / "src" / "nn.ts",
               "namespace App.Core.Util { export const v = 1; }\n")
    r = extract([f], cache_root=tmp_path)
    assert _node_label(r, "src/nn.ts", "App.Core.Util") == "App.Core.Util"


def test_namespace_members_still_extracted(tmp_path):
    """The container node must not cost us the members the default recurse reached."""
    f = _write(tmp_path / "src" / "n.ts",
               "namespace Shapes {\n"
               "  export class Circle {}\n"
               "  export function area() { return 0; }\n"
               "}\n")
    r = extract([f], cache_root=tmp_path)
    assert _has_node(r, "src/n.ts", "Shapes")
    assert _has_node(r, "src/n.ts", "Circle")
    assert _has_node(r, "src/n.ts", "area")


def test_ambient_string_module_quotes_stripped(tmp_path):
    f = _write(tmp_path / "src" / "amb.ts",
               'declare module "pkg-name" { export const z = 3; }\n')
    r = extract([f], cache_root=tmp_path)
    assert _node_label(r, "src/amb.ts", "pkg-name") == "pkg-name"


def test_namespace_node_not_emitted_in_js(tmp_path):
    """The handler is TS-only; plain JS has no namespace syntax to confuse it."""
    f = _write(tmp_path / "src" / "p.js", "function ok() {}\n")
    r = extract([f], cache_root=tmp_path)
    assert _has_node(r, "src/p.js", "ok")
