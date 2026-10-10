"""Regression tests for #3357: unmapped `@/` path alias resolution.

When no tsconfig.json or jsconfig.json exists, `@/...` represents an internal
project-root convention alias. It resolves against project_anchor / "src" / subpath
(if src/ exists) or project_anchor / subpath.
"""
from __future__ import annotations

import json
from pathlib import Path

from graphify.extract import _make_id, extract
from graphify.extractors.resolution import _resolve_js_module_path, _resolve_js_import_target
from graphify.extract import _resolve_rescued_specifier


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_3357_minimal_reproduction_no_config_emits_calls_edge(tmp_path: Path, monkeypatch):
    """Minimal reproduction for #3357:

    - adapter.js exports fn
    - caller.js imports fn from "@/adapter.js"
    - no package.json, no tsconfig.json, no jsconfig.json
    - emits imports_from, imports, and calls edges to the actual adapter/function nodes.
    """
    # Prevent host machine VCS roots (e.g. C:\Users\HP\.git) from anchoring temp test paths
    monkeypatch.setattr("graphify.detect._find_vcs_root", lambda start: None)
    adapter = _write(
        tmp_path / "adapter.js",
        "export function enableBackgroundBle() { return 1; }\n",
    )
    caller = _write(
        tmp_path / "caller.js",
        'import { enableBackgroundBle } from "@/adapter.js";\n'
        "function run() { enableBackgroundBle(); }\n",
    )
    res = extract([adapter, caller], cache_root=tmp_path, parallel=False)
    nodes = {n["id"]: n for n in res["nodes"]}
    edges = res["edges"]


    adapter_nid = _make_id(str(adapter.relative_to(tmp_path).with_suffix("")))
    fn_nid = _make_id("adapter", "enableBackgroundBle")

    # 1. imports_from edge points to adapter file node
    imports_from = [
        e for e in edges
        if e.get("relation") == "imports_from" and e.get("source") == "caller"
    ]
    assert len(imports_from) == 1
    assert imports_from[0]["target"] == adapter_nid

    # 2. imports edge points to actual function symbol node
    imports = [
        e for e in edges
        if e.get("relation") == "imports" and e.get("source") == "caller"
    ]
    assert len(imports) == 1
    assert imports[0]["target"] == fn_nid

    # 3. calls edge emitted with EXTRACTED confidence
    calls = [
        e for e in edges
        if e.get("relation") == "calls"
        and nodes.get(e["source"], {}).get("label") == "run()"
    ]
    assert len(calls) == 1
    assert calls[0]["target"] == fn_nid
    assert calls[0]["confidence"] == "EXTRACTED"


def test_nested_importer_src_layout_resolves_to_src(tmp_path: Path):
    """In a standard src/ layout with a nested importer, @/ resolves to src/."""
    _write(tmp_path / "package.json", '{"name": "test-pkg"}\n')
    adapter = _write(
        tmp_path / "src" / "adapter.js",
        "export function doThing() { return 2; }\n",
    )
    caller = _write(
        tmp_path / "src" / "features" / "caller.js",
        'import { doThing } from "@/adapter.js";\n'
        "export function run() { doThing(); }\n",
    )
    res = extract([adapter, caller], cache_root=tmp_path, parallel=False)
    nodes = {n["id"]: n for n in res["nodes"]}

    adapter_nid = _make_id(str(adapter.relative_to(tmp_path).with_suffix("")))
    fn_nid = _make_id("src_adapter", "doThing")

    calls = [
        e for e in res["edges"]
        if e.get("relation") == "calls"
        and nodes.get(e["source"], {}).get("label") == "run()"
    ]
    assert len(calls) == 1
    assert calls[0]["target"] == fn_nid
    assert calls[0]["confidence"] == "EXTRACTED"


def test_nested_importer_flat_layout_resolves_to_root(tmp_path: Path):
    """In a flat layout (no src/ dir) with a nested importer, @/ resolves to root."""
    _write(tmp_path / "package.json", '{"name": "flat-pkg"}\n')
    adapter = _write(
        tmp_path / "adapter.js",
        "export function rootHelper() { return 3; }\n",
    )
    caller = _write(
        tmp_path / "features" / "deep" / "caller.js",
        'import { rootHelper } from "@/adapter.js";\n'
        "export function run() { rootHelper(); }\n",
    )
    res = extract([adapter, caller], cache_root=tmp_path, parallel=False)
    nodes = {n["id"]: n for n in res["nodes"]}

    adapter_nid = _make_id(str(adapter.relative_to(tmp_path).with_suffix("")))
    fn_nid = _make_id("adapter", "rootHelper")

    calls = [
        e for e in res["edges"]
        if e.get("relation") == "calls"
        and nodes.get(e["source"], {}).get("label") == "run()"
    ]
    assert len(calls) == 1
    assert calls[0]["target"] == fn_nid
    assert calls[0]["confidence"] == "EXTRACTED"


def test_tsconfig_without_paths_leaves_at_alias_unresolved(tmp_path: Path):
    """#3125 invariant: when tsconfig.json exists without paths, @/ must NOT resolve."""
    _write(tmp_path / "tsconfig.json", json.dumps({"compilerOptions": {"target": "es2020"}}))
    adapter = _write(
        tmp_path / "adapter.js",
        "export function enableBackgroundBle() { return 1; }\n",
    )
    caller = _write(
        tmp_path / "caller.js",
        'import { enableBackgroundBle } from "@/adapter.js";\n'
        "function run() { enableBackgroundBle(); }\n",
    )
    res = extract([adapter, caller], cache_root=tmp_path, parallel=False)
    edges = res["edges"]

    # Must fall back to ref target
    ref_target = _make_id("ref", "@/adapter.js")
    imports_from = [
        e for e in edges
        if e.get("relation") == "imports_from" and e.get("source") == "caller"
    ]
    assert len(imports_from) == 1
    assert imports_from[0]["target"] == ref_target

    # No symbol import edge
    assert not any(e.get("relation") == "imports" and e.get("source") == "caller" for e in edges)

    # No calls edge (gated by #1659)
    assert not any(e.get("relation") == "calls" for e in edges)


def test_explicit_tsconfig_alias_takes_precedence_over_convention(tmp_path: Path):
    """When tsconfig defines @/* paths, configured mapping wins over convention."""
    _write(tmp_path / "tsconfig.json", json.dumps({
        "compilerOptions": {
            "baseUrl": ".",
            "paths": {"@/*": ["custom/*"]}
        }
    }))
    custom_adapter = _write(
        tmp_path / "custom" / "adapter.js",
        "export function targetFunc() { return 'custom'; }\n",
    )
    # Root adapter that convention would have targeted
    root_adapter = _write(
        tmp_path / "adapter.js",
        "export function targetFunc() { return 'root'; }\n",
    )
    caller = _write(
        tmp_path / "caller.js",
        'import { targetFunc } from "@/adapter.js";\n'
        "function run() { targetFunc(); }\n",
    )
    res = extract([custom_adapter, root_adapter, caller], cache_root=tmp_path, parallel=False)
    nodes = {n["id"]: n for n in res["nodes"]}

    custom_fn_nid = _make_id("custom_adapter", "targetFunc")
    calls = [
        e for e in res["edges"]
        if e.get("relation") == "calls"
        and nodes.get(e["source"], {}).get("label") == "run()"
    ]
    assert len(calls) == 1
    assert calls[0]["target"] == custom_fn_nid


def test_missing_at_target_uses_ref_fallback(tmp_path: Path):
    """@/pointing to non-existent file falls back to stable ref target."""
    caller = _write(
        tmp_path / "caller.js",
        'import { missingFn } from "@/does-not-exist.js";\n'
        "function run() { missingFn(); }\n",
    )
    res = extract([caller], cache_root=tmp_path, parallel=False)
    edges = res["edges"]

    ref_target = _make_id("ref", "@/does-not-exist.js")
    imports_from = [
        e for e in edges
        if e.get("relation") == "imports_from" and e.get("source") == "caller"
    ]
    assert len(imports_from) == 1
    assert imports_from[0]["target"] == ref_target

    # No imports or calls edges
    assert not any(e.get("relation") == "imports" for e in edges)
    assert not any(e.get("relation") == "calls" for e in edges)


def test_scoped_package_import_remains_external(tmp_path: Path):
    """@scope/pkg is not an @/ alias and remains an external reference."""
    caller = _write(
        tmp_path / "caller.js",
        'import { something } from "@scope/pkg";\n'
        "function run() { something(); }\n",
    )
    res = extract([caller], cache_root=tmp_path, parallel=False)
    edges = res["edges"]

    ref_target = _make_id("ref", "@scope/pkg")
    imports_from = [
        e for e in edges
        if e.get("relation") == "imports_from" and e.get("source") == "caller"
    ]
    assert len(imports_from) == 1
    assert imports_from[0]["target"] == ref_target


def test_regex_rescue_unmapped_at_alias_resolves(tmp_path: Path):
    """The regex-rescue path in extract.py (#701) also resolves unmapped @/."""
    _write(tmp_path / "package.json", '{"name": "test-app"}\n')
    lib = _write(
        tmp_path / "lib.js",
        "export const helper = 42;\n",
    )
    svelte_file = tmp_path / "App.svelte"
    # Svelte static import rescued by regex
    svelte_file.write_text(
        '<script>\nimport { helper } from "@/lib.js";\n</script>\n<h1>Hello</h1>\n',
        encoding="utf-8",
    )
    resolution = _resolve_rescued_specifier(svelte_file, "@/lib.js", aliases={}, base_url=None)
    assert resolution is not None
    node_id, stub_sf, resolved_file = resolution
    assert resolved_file == lib


def test_unresolved_at_alias_does_not_infer_call_to_unrelated_definition(tmp_path: Path):
    """#1659 protection: an unresolved @/ alias must not infer calls to unrelated definitions.

    If caller.js imports { missingFn } from "@/does-not-exist.js" and unrelated.js
    happens to export a lone matching function missingFn(), Graphify must NOT emit
    a phantom INFERRED or EXTRACTED calls edge from caller.js to unrelated.js.
    """
    caller = _write(
        tmp_path / "caller.js",
        'import { missingFn } from "@/does-not-exist.js";\n'
        "function run() { missingFn(); }\n",
    )
    unrelated = _write(
        tmp_path / "unrelated.js",
        "export function missingFn() { return 'unrelated'; }\n",
    )
    res = extract([caller, unrelated], cache_root=tmp_path, parallel=False)
    edges = res["edges"]

    # The @/ import must resolve to ref_ target
    ref_target = _make_id("ref", "@/does-not-exist.js")
    imports_from = [
        e for e in edges
        if e.get("relation") == "imports_from" and e.get("source") == "caller"
    ]
    assert len(imports_from) == 1
    assert imports_from[0]["target"] == ref_target

    # Must NOT produce any calls edge from caller.js (run) to unrelated.js (missingFn)
    unrelated_fn_nid = _make_id("unrelated", "missingFn")
    calls_to_unrelated = [
        e for e in edges
        if e.get("relation") == "calls" and e.get("target") == unrelated_fn_nid
    ]
    assert not calls_to_unrelated
