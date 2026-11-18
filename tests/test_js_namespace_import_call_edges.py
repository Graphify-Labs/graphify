"""Tests for resolving call edges through JavaScript and TypeScript namespace imports
and whole-module CommonJS require (#5114).

Also covers #5144: the namespace/whole-module member call added by #5114 resolved
a unique same-named exported symbol without checking whether that symbol was
callable at all, so `m.handler()` through `const handler = {a: 1}` got a calls
edge to the object literal.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from graphify.extract import extract


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


CASES = [
    (
        "commonjs-member",
        ".js",
        "function format(x) { return x; }\nmodule.exports = { format };\n",
        "const helpers = require('./helpers');\nfunction go(x) { return helpers.format(x); }\n",
    ),
    (
        "commonjs-destructured",
        ".js",
        "function format(x) { return x; }\nmodule.exports = { format };\n",
        "const { format } = require('./helpers');\nfunction go(x) { return format(x); }\n",
    ),
    (
        "esm-namespace-js",
        ".js",
        "export function format(x) { return x; }\n",
        "import * as helpers from './helpers.js';\nexport function go(x) { return helpers.format(x); }\n",
    ),
    (
        "esm-named-js",
        ".js",
        "export function format(x) { return x; }\n",
        "import { format } from './helpers.js';\nexport function go(x) { return format(x); }\n",
    ),
    (
        "esm-namespace-ts",
        ".ts",
        "export function format(x: string) { return x; }\n",
        "import * as helpers from './helpers';\nexport function go(x: string) { return helpers.format(x); }\n",
    ),
    (
        "esm-named-ts",
        ".ts",
        "export function format(x: string) { return x; }\n",
        "import { format } from './helpers';\nexport function go(x: string) { return format(x); }\n",
    ),
]


@pytest.mark.parametrize("name,ext,module_code,consumer_code", CASES)
def test_namespace_import_and_whole_module_require_call_edges(
    tmp_path: Path, name: str, ext: str, module_code: str, consumer_code: str
):
    helper = _write(tmp_path / f"helpers{ext}", module_code)
    user = _write(tmp_path / f"user{ext}", consumer_code)

    graph = extract([helper, user], root=tmp_path, cache_root=tmp_path / "cache", parallel=False)
    nodes = {n["id"]: n for n in graph["nodes"]}
    hits = [
        (
            nodes[e["source"]]["label"],
            nodes[e["target"]]["label"],
            Path(nodes[e["target"]]["source_file"]).name,
        )
        for e in graph["edges"]
        if e["relation"] == "calls"
        and e["source"] in nodes
        and e["target"] in nodes
        and nodes[e["source"]]["label"] == "go()"
        and nodes[e["target"]]["label"] == "format()"
    ]
    assert hits == [("go()", "format()", f"helpers{ext}")]


def test_ts_import_equals_require_member_call(tmp_path: Path):
    helper = _write(tmp_path / "helpers.ts", "export function format(x: string) { return x; }\n")
    user = _write(
        tmp_path / "user.ts",
        "import helpers = require('./helpers');\nexport function go(x: string) { return helpers.format(x); }\n",
    )

    graph = extract([helper, user], root=tmp_path, cache_root=tmp_path / "cache", parallel=False)
    nodes = {n["id"]: n for n in graph["nodes"]}
    hits = [
        (
            nodes[e["source"]]["label"],
            nodes[e["target"]]["label"],
            Path(nodes[e["target"]]["source_file"]).name,
        )
        for e in graph["edges"]
        if e["relation"] == "calls"
        and e["source"] in nodes
        and e["target"] in nodes
        and nodes[e["source"]]["label"] == "go()"
        and nodes[e["target"]]["label"] == "format()"
    ]
    assert hits == [("go()", "format()", "helpers.ts")]


@pytest.mark.parametrize(
    "shadow_code",
    [
        "const helpers = require('./helpers');\nfunction go(helpers) { return helpers.format(); }\n",
        "const helpers = require('./helpers');\nfunction go() { const helpers = {}; return helpers.format(); }\n",
        "import * as helpers from './helpers.js';\nexport function go(helpers) { return helpers.format(); }\n",
        "import * as helpers from './helpers.js';\nexport function go() { const helpers = {}; return helpers.format(); }\n",
    ],
)
def test_namespace_receiver_shadowed_has_no_call_edge(tmp_path: Path, shadow_code: str):
    helper = _write(tmp_path / "helpers.js", "export function format() {}\nmodule.exports = { format };\n")
    user = _write(tmp_path / "user.js", shadow_code)

    graph = extract([helper, user], root=tmp_path, cache_root=tmp_path / "cache", parallel=False)
    nodes = {n["id"]: n for n in graph["nodes"]}
    hits = [
        e
        for e in graph["edges"]
        if e["relation"] == "calls"
        and e["source"] in nodes
        and e["target"] in nodes
        and nodes[e["source"]]["label"] == "go()"
        and nodes[e["target"]]["label"] == "format()"
    ]
    assert hits == []


@pytest.mark.parametrize(
    "module_code,consumer_code",
    [
        (
            "const handler = { a: 1 };\nmodule.exports = { handler };\n",
            "const m = require('./helpers');\nfunction go() { return m.handler(); }\n",
        ),
        (
            "export const handler = { a: 1 };\n",
            "import * as m from './helpers.js';\nexport function go() { return m.handler(); }\n",
        ),
    ],
)
def test_namespace_member_call_to_non_callable_export_has_no_call_edge(
    tmp_path: Path, module_code: str, consumer_code: str
):
    """#5144: the exported value is a plain object, never a function, so
    `m.handler()` must not produce a calls edge to it even though exactly
    one export named "handler" exists."""
    helper = _write(tmp_path / "helpers.js", module_code)
    user = _write(tmp_path / "user.js", consumer_code)

    graph = extract([helper, user], root=tmp_path, cache_root=tmp_path / "cache", parallel=False)
    nodes = {n["id"]: n for n in graph["nodes"]}
    hits = [
        e
        for e in graph["edges"]
        if e["relation"] == "calls"
        and e["source"] in nodes
        and e["target"] in nodes
        and nodes[e["source"]]["label"] == "go()"
        and nodes[e["target"]]["label"] == "handler"
    ]
    assert hits == []


def test_namespace_member_call_to_callable_export_is_unaffected(tmp_path: Path):
    """Control: the exact shape #5114 fixed (a real function behind the same
    member-call mechanism) must still resolve after gating on callability."""
    helper = _write(
        tmp_path / "helpers.js",
        "function handler() { return 1; }\nmodule.exports = { handler };\n",
    )
    user = _write(
        tmp_path / "user.js",
        "const m = require('./helpers');\nfunction go() { return m.handler(); }\n",
    )

    graph = extract([helper, user], root=tmp_path, cache_root=tmp_path / "cache", parallel=False)
    nodes = {n["id"]: n for n in graph["nodes"]}
    hits = [
        (nodes[e["source"]]["label"], nodes[e["target"]]["label"])
        for e in graph["edges"]
        if e["relation"] == "calls"
        and e["source"] in nodes
        and e["target"] in nodes
        and nodes[e["source"]]["label"] == "go()"
    ]
    assert hits == [("go()", "handler()")]
