from pathlib import Path

from graphify.diagnostics import diagnose_extraction
from graphify.extract import extract


def test_js_import_endpoints_are_explicitly_classified_and_materialized(
    tmp_path: Path,
) -> None:
    source = tmp_path / "src/app.ts"
    source.parent.mkdir(parents=True)
    source.write_text(
        "import React from 'react'\n"
        "import { Missing } from './missing.js'\n"
        "import stylesheet from './styles.css?url'\n",
        encoding="utf-8",
    )
    (source.parent / "styles.css").write_text("body {}", encoding="utf-8")

    result = extract(
        [source],
        cache_root=tmp_path / "cache",
        root=tmp_path,
        parallel=False,
    )
    imports = [
        edge for edge in result["edges"]
        if edge.get("relation") == "imports_from"
    ]
    node_ids = {node["id"] for node in result["nodes"]}

    assert len(imports) == 3
    assert sum(edge.get("external") is True for edge in imports) == 1
    assert sum(edge.get("unresolved_internal") is True for edge in imports) == 1
    assert sum(edge.get("excluded_local") is True for edge in imports) == 1
    assert all(edge["target"] in node_ids for edge in imports)

    summary = diagnose_extraction(result, root=tmp_path)
    assert summary["external_endpoint_edges"] == 1
    assert summary["unresolved_internal_endpoint_edges"] == 1
    assert summary["excluded_local_endpoint_edges"] == 1
    assert summary["dangling_endpoint_edges"] == 0
    assert summary["unclassified_endpoint_edges"] == 0


def test_existing_but_unscanned_tsconfig_alias_is_excluded_local(
    tmp_path: Path,
) -> None:
    source = tmp_path / "src/app.ts"
    source.parent.mkdir(parents=True)
    source.write_text(
        "import { browser } from 'collections/browser'\n",
        encoding="utf-8",
    )
    hidden = tmp_path / ".source/browser.ts"
    hidden.parent.mkdir()
    hidden.write_text("export const browser = true\n", encoding="utf-8")
    (tmp_path / "tsconfig.json").write_text(
        '{"compilerOptions":{"paths":{"collections/*":["./.source/*"]}}}',
        encoding="utf-8",
    )

    result = extract(
        [source],
        cache_root=tmp_path / "cache",
        root=tmp_path,
        parallel=False,
    )
    edge = next(
        edge
        for edge in result["edges"]
        if edge.get("relation") == "imports_from"
    )
    endpoint = next(node for node in result["nodes"] if node["id"] == edge["target"])

    assert edge.get("excluded_local") is True
    assert edge.get("unresolved_internal") is not True
    assert endpoint.get("excluded_local") is True
    assert endpoint["source_file"] == ".source/browser.ts"
