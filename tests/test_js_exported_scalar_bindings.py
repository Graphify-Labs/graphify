from __future__ import annotations

import pytest

from graphify.extract import extract, extract_js


@pytest.mark.parametrize("suffix", [".js", ".ts"])
def test_exported_scalar_bindings_emit_nodes(tmp_path, suffix):
    source = tmp_path / f"constants{suffix}"
    source.write_text(
        """
export const NUMBER = 42;
export const STRING = "value";
export const BOOLEAN = true;
export const TEMPLATE = `value-${NUMBER}`;
export const MEMBER = process.env.VALUE;
export const LOGICAL = process.env.VALUE ?? "fallback";
export const TERNARY = BOOLEAN ? "yes" : "no";

const internalScalar = 1;
function helper() {
  const localScalar = 2;
}
""",
        encoding="utf-8",
    )

    result = extract_js(source)
    labels = {node["label"] for node in result["nodes"]}

    assert {
        "NUMBER",
        "STRING",
        "BOOLEAN",
        "TEMPLATE",
        "MEMBER",
        "LOGICAL",
        "TERNARY",
    } <= labels
    assert "internalScalar" not in labels
    assert "localScalar" not in labels


def test_exported_scalar_fix_skips_unsupported_binding_patterns(tmp_path):
    source = tmp_path / "patterns.ts"
    source.write_text(
        """
const config = { source: 1 };
const items = [1];
export const { source: renamed } = config;
export const [first] = items;
export const $ = 1;
export const _ = 2;
""",
        encoding="utf-8",
    )

    result = extract_js(source)
    labels = {node["label"] for node in result["nodes"]}

    assert "$" not in labels
    assert "_" not in labels
    assert not any("renamed" in label or "first" in label for label in labels)
    assert all(edge["source"] != edge["target"] for edge in result["edges"])


def test_exported_scalar_binding_satisfies_named_import_target(tmp_path):
    exporter = tmp_path / "constants.ts"
    exporter.write_text(
        """
export const A_PREFIX = process.env.A_PREFIX ?? "X>";
export const A_MAX = Number(process.env.A_MAX || 10);
""",
        encoding="utf-8",
    )
    importer = tmp_path / "consumer.ts"
    importer.write_text(
        'import { A_PREFIX, A_MAX } from "./constants";\n',
        encoding="utf-8",
    )

    result = extract(
        [exporter, importer],
        cache_root=tmp_path,
        parallel=False,
    )
    node_ids = {node["id"] for node in result["nodes"]}
    import_targets = {
        edge["target"]
        for edge in result["edges"]
        if edge["relation"] == "imports"
    }

    assert import_targets
    assert import_targets <= node_ids


def test_destructuring_declarator_nodes_bound_names_not_pattern_text(tmp_path):
    """A destructuring declarator binds identifiers; its ``name`` field is the
    pattern source. Reading that field verbatim minted a node labelled
    ``{ a, b: renamed, c = 1, ...rest }`` — text that names no symbol and can
    never be a reference target."""
    source = tmp_path / "patterns.ts"
    source.write_text(
        """
type Cfg = { a: number; b: number; c: number; deep: { inner: number } };
const { a, b: renamed, c = 1, ...rest } = obj as Cfg;
const [first, , third] = arr as number[];
const { deep: { inner } } = obj as Cfg;
""",
        encoding="utf-8",
    )

    result = extract_js(source)
    labels = {node["label"] for node in result["nodes"]}

    # Each bound identifier is its own node.
    assert {"a", "renamed", "c", "rest", "first", "third", "inner"} <= labels
    # The pattern source is never a label.
    assert not any(label.startswith(("{", "[")) for label in labels)
    # `b` is a property key, not a binding — `b: renamed` binds only `renamed`.
    assert "b" not in labels
    # `deep` is a key too; the nested pattern binds `inner`.
    assert "deep" not in labels
    # Array holes bind nothing and must not mint an empty-labelled node.
    assert "" not in labels


def test_destructured_rune_props_do_not_mint_a_pattern_node(tmp_path):
    """The shape that made this universal: every Svelte 5 component
    destructures ``$props()``, so the pattern text was one junk node per
    component."""
    source = tmp_path / "props.ts"
    source.write_text(
        """
let { levels, selected = $bindable(), ariaLabel, disabled = false } = $props();
""",
        encoding="utf-8",
    )

    result = extract_js(source)
    labels = {node["label"] for node in result["nodes"]}

    assert {"levels", "selected", "ariaLabel", "disabled"} <= labels
    # The default expressions are not bindings.
    assert "$bindable" not in labels
    assert not any(label.startswith("{") for label in labels)


def test_destructuring_initializer_closures_still_tracked(tmp_path):
    """Closures in a destructured initializer are attributed to the first
    binding, so their calls are still walked (#2552 behaviour preserved)."""
    source = tmp_path / "closures.ts"
    source.write_text(
        """
function target() {}
const { handler } = wrapper(() => { target(); });
""",
        encoding="utf-8",
    )

    result = extract_js(source)
    labels = {node["label"] for node in result["nodes"]}
    assert "handler" in labels
    by_label = {n["label"]: n["id"] for n in result["nodes"]}
    calls = {
        (e["source"], e["target"])
        for e in result["edges"]
        if e.get("relation") == "calls"
    }
    assert (by_label["handler"], by_label["target()"]) in calls


def test_destructured_require_binds_the_import_not_a_local_node(tmp_path):
    """``const { doWork } = require('./lib')`` binds an import. Noding it as a
    local symbol would shadow the real cross-file definition, so the call in
    ``run()`` would resolve to this file's stub instead of ``lib.js``."""
    caller = tmp_path / "caller.js"
    callee = tmp_path / "lib.js"
    caller.write_text(
        "const { doWork } = require('./lib');\n"
        "function run() { doWork(); }\n",
        encoding="utf-8",
    )
    callee.write_text(
        "function doWork() { return 1; }\n"
        "module.exports = { doWork };\n",
        encoding="utf-8",
    )

    result = extract([caller, callee], cache_root=tmp_path)
    nodes = {n["id"]: n for n in result["nodes"]}
    calls = [
        e for e in result["edges"]
        if e["relation"] == "calls"
        and nodes[e["source"]]["label"] == "run()"
        and nodes[e["target"]]["label"] == "doWork()"
    ]
    assert len(calls) == 1
    # The call resolves into the callee's file, not a local stub.
    assert nodes[calls[0]["target"]]["source_file"].endswith("lib.js")


def test_non_require_call_initializer_still_binds(tmp_path):
    """The require exclusion keys on the callee name, not on the call shape —
    any other ``identifier(...)`` initializer still binds its names."""
    source = tmp_path / "runes.ts"
    source.write_text("let { levels, disabled } = $props();\n", encoding="utf-8")

    labels = {n["label"] for n in extract_js(source)["nodes"]}
    assert {"levels", "disabled"} <= labels


def test_member_access_require_is_still_an_import(tmp_path):
    """``const { doWork } = require('./lib').utils`` is a CJS import too.

    ``_require_imports_js`` edges the member-access form, so
    ``_is_require_initializer`` must recognise it as well — otherwise the
    destructured name would be both imported and shadowed by a local stub,
    and the call in ``run()`` would resolve to the stub.
    """
    caller = tmp_path / "caller.js"
    callee = tmp_path / "lib.js"
    caller.write_text(
        "const { doWork } = require('./lib').utils;\n"
        "function run() { doWork(); }\n",
        encoding="utf-8",
    )
    callee.write_text(
        "function doWork() { return 1; }\n"
        "module.exports = { utils: { doWork } };\n",
        encoding="utf-8",
    )

    result = extract([caller, callee], cache_root=tmp_path)
    nodes = {n["id"]: n for n in result["nodes"]}
    local_stubs = [
        n for n in result["nodes"]
        if n["label"] == "doWork" and n["source_file"].endswith("caller.js")
    ]
    assert not local_stubs
    calls = [
        e for e in result["edges"]
        if e["relation"] == "calls"
        and nodes[e["source"]]["label"] == "run()"
        and nodes[e["target"]]["label"] == "doWork()"
    ]
    assert len(calls) == 1
    assert nodes[calls[0]["target"]]["source_file"].endswith("lib.js")
