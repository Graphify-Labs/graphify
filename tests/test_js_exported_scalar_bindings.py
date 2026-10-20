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
