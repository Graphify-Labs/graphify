from pathlib import Path

from graphify.diagnostics import diagnose_extraction
from graphify.extract import extract


def test_typescript_external_and_missing_local_imports_are_separate(tmp_path: Path) -> None:
    source = tmp_path / "src" / "app.ts"
    source.parent.mkdir(parents=True)
    source.write_text(
        "import {Component} from '@angular/core';\n"
        "import {Missing} from './missing';\n",
        encoding="utf-8",
    )

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

    assert len(imports) == 2
    assert sum(edge.get("external") is True for edge in imports) == 1
    assert sum(edge.get("unresolved_internal") is True for edge in imports) == 1

    summary = diagnose_extraction(result, root=tmp_path)
    assert summary["external_endpoint_edges"] == 1
    assert summary["unresolved_internal_endpoint_edges"] == 1
    assert summary["unclassified_endpoint_edges"] == 0


def test_unresolved_typescript_alias_is_internal(tmp_path: Path) -> None:
    (tmp_path / "tsconfig.json").write_text(
        '{"compilerOptions":{"baseUrl":".","paths":{"@app/*":["src/*"]}}}',
        encoding="utf-8",
    )
    source = tmp_path / "src" / "app.ts"
    source.parent.mkdir()
    source.write_text(
        "import {Missing} from '@app/missing';\n",
        encoding="utf-8",
    )

    result = extract(
        [source],
        cache_root=tmp_path / "cache",
        root=tmp_path,
        parallel=False,
    )
    edge = next(
        edge for edge in result["edges"]
        if edge.get("relation") == "imports_from"
    )

    assert edge.get("unresolved_internal") is True
    assert edge.get("external") is not True
