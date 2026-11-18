"""Workspace globs: a YAML inline comment or a glob pathlib rejects must not break resolution (#4681)."""
from __future__ import annotations

import json

import pytest

from graphify.extract import extract


def _project(tmp_path, workspace, *, pkg_dir="pk/p", pnpm=True):
    """A workspace with one package at `pkg_dir`, a consumer that imports it by name,
    and a Python file, so a crash that takes the whole run down is visible."""
    pkg = tmp_path / pkg_dir
    pkg.mkdir(parents=True)
    (pkg / "package.json").write_text('{"name": "@x/p", "main": "index.ts"}')
    (pkg / "index.ts").write_text("export function boot() { return 1; }\n")
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "c.ts").write_text(
        'import { boot } from "@x/p";\nexport function go() { return boot(); }\n'
    )
    (tmp_path / "tool.py").write_text("def hello():\n    return 1\n")
    if pnpm:
        (tmp_path / "package.json").write_text('{"name": "root"}')
        (tmp_path / "pnpm-workspace.yaml").write_text("packages:\n" + workspace)
    else:
        (tmp_path / "package.json").write_text(json.dumps({"name": "root", "workspaces": workspace}))


def _run(tmp_path):
    files = sorted(p for p in tmp_path.rglob("*") if p.suffix in (".ts", ".py"))
    return extract(files, root=tmp_path)


def _labels(result):
    return {n["label"] for n in result["nodes"]}


def _imports_resolve_to_package(result):
    nodes = {n["id"]: n for n in result["nodes"]}
    targets = [nodes.get(e["target"]) for e in result["edges"] if e["relation"] == "imports_from"]
    return any(t and t.get("source_file", "").endswith("p/index.ts") for t in targets)


@pytest.mark.parametrize("glob", ["pk/**", "pk/*"])
@pytest.mark.parametrize("quote", ['"', "'"])
def test_inline_comment_after_quoted_glob_still_resolves_the_package(tmp_path, glob, quote):
    _project(tmp_path, f"  - {quote}{glob}{quote} # staging runner\n")
    result = _run(tmp_path)
    assert {"hello()", "go()"} <= _labels(result)
    assert _imports_resolve_to_package(result)


@pytest.mark.parametrize("bad", ["tools/**-cli", "ABSOLUTE"])
def test_workspace_glob_pathlib_rejects_does_not_drop_the_run(tmp_path, bad):
    glob = str(tmp_path / "elsewhere" / "*") if bad == "ABSOLUTE" else bad
    _project(tmp_path, [glob, "pk/*"], pnpm=False)
    result = _run(tmp_path)
    assert {"hello()", "go()"} <= _labels(result)
    assert _imports_resolve_to_package(result)


@pytest.mark.parametrize("glob", ["pk/**", "pk/*"])
def test_workspace_without_comment_resolves_the_package(tmp_path, glob):
    _project(tmp_path, f'  - "{glob}"\n')
    result = _run(tmp_path)
    assert {"hello()", "go()"} <= _labels(result)
    assert _imports_resolve_to_package(result)


def test_hash_inside_quotes_is_part_of_the_glob(tmp_path):
    _project(tmp_path, '  - "a#b/*"\n', pkg_dir="a#b/p")
    assert _imports_resolve_to_package(_run(tmp_path))
