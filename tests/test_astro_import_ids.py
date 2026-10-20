"""Regression tests for #2195: Astro/Svelte regex-rescued imports must not mint
ghost nodes keyed by the absolute scan path.

The Svelte/Astro/Vue regex-rescue passes used to mint stub TARGET nodes whose id
was ``_make_id(str(resolved_path))`` — ABSOLUTE when the input paths were
absolute — producing ghost nodes (e.g. ``private_tmp_..._src_lib_content``)
alongside the real file node (``src_lib_content``), plus dangling
``imports_from`` edges. The static branches also used a naive ``.js``->``.ts``
suffix swap instead of extension probing, so extensionless specifiers
(``../../lib/content``) never matched the real ``content.ts`` file and the
edges carried no ``target_file`` stamp for the #2169 canonicalization pass to
learn from.

Fixed by routing all five rescue sites through the shared helper, which mirrors
``_import_js``: resolve via ``_resolve_js_module_path`` (extension probing) and,
when the target is a real file on disk, emit ONLY the ``target_file``-stamped
edge — no stub node.
"""
from __future__ import annotations

import os
from pathlib import Path

from graphify.extract import _file_node_id, _make_id, extract


def _write(path: Path, body: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


def _astro_project(tmp_path: Path) -> Path:
    # realpath: on macOS pytest's tmp dir lives under /private/var but is
    # handed out as /var — the extractor resolves paths, so anchor the test
    # on the resolved form to keep id/slug comparisons meaningful.
    root = Path(os.path.realpath(tmp_path))
    _write(
        root / "src/pages/work/index.astro",
        """---
import { projects } from '../../lib/content';
import { SITE } from '../../config';
import '../styles/global.css';
---
<h1>{SITE}</h1>
""",
    )
    _write(root / "src/lib/content.ts", "export const projects = [1];\n")
    _write(root / "src/config.ts", "export const SITE = 'x';\n")
    _write(root / "src/pages/styles/global.css", "body { margin: 0 }\n")
    return root


def _assert_no_root_slug(result: dict, root: Path) -> None:
    """No node id and no edge endpoint may embed the scan-root path slug."""
    root_slug = _make_id(str(root))
    for n in result["nodes"]:
        assert root_slug not in n["id"], f"ghost node id leaks scan root: {n['id']}"
    for e in result["edges"]:
        assert root_slug not in str(e.get("source") or ""), (
            f"edge source leaks scan root: {e['source']}"
        )
        assert root_slug not in str(e.get("target") or ""), (
            f"edge target leaks scan root: {e['target']}"
        )


def _astro_paths(root: Path) -> list[Path]:
    return [
        root / "src/pages/work/index.astro",
        root / "src/lib/content.ts",
        root / "src/config.ts",
    ]


def test_astro_absolute_inputs_no_ghost_import_nodes(tmp_path):
    """Absolute input paths must not mint absolute-id ghost stubs (#2195)."""
    root = _astro_project(tmp_path)
    result = extract(_astro_paths(root), cache_root=root)

    _assert_no_root_slug(result, root)

    # Exactly one node represents src/lib/content.ts, under its canonical id.
    content_file_nodes = [
        n for n in result["nodes"]
        if n.get("source_file") == "src/lib/content.ts"
        and n["id"] == _file_node_id(Path("src/lib/content.ts"))
    ]
    assert len(content_file_nodes) == 1
    assert content_file_nodes[0]["id"] == "src_lib_content"
    # And no OTHER node claims to BE that file (a ghost stub would carry the
    # same source_file but an absolute-derived id).
    file_level = [
        n for n in result["nodes"]
        if n.get("source_file") == "src/lib/content.ts"
        and n["id"].endswith("content")
    ]
    assert file_level == content_file_nodes

    # The rescued import edge lands on the canonical real node.
    index_id = _file_node_id(Path("src/pages/work/index.astro"))
    import_edges = {
        (e["source"], e["target"])
        for e in result["edges"]
        if e.get("relation") == "imports_from"
    }
    assert (index_id, "src_lib_content") in import_edges
    assert (index_id, "src_config") in import_edges

    # The CSS side-effect import edge must not leak the root either; its
    # canonical target is derived from the repo-relative path.
    css_targets = [
        e["target"] for e in result["edges"]
        if e.get("relation") == "imports_from" and "global" in str(e.get("target"))
    ]
    assert css_targets, "css import edge missing"
    assert all(t == "src_pages_styles_global" for t in css_targets)


def test_astro_relative_inputs_keep_canonical_ids(tmp_path, monkeypatch):
    """Relative inputs: the real file node keeps its canonical id — the #1462
    colliding-id disambiguator must not rename it away because a same-id ghost
    stub was minted (regression guard)."""
    root = _astro_project(tmp_path)
    monkeypatch.chdir(root)
    rel_paths = [
        Path("src/pages/work/index.astro"),
        Path("src/lib/content.ts"),
        Path("src/config.ts"),
    ]
    result = extract(rel_paths, cache_root=Path("."))

    _assert_no_root_slug(result, root)

    content_file_nodes = [
        n for n in result["nodes"] if n["id"] == "src_lib_content"
    ]
    assert len(content_file_nodes) == 1
    assert content_file_nodes[0]["source_file"] == "src/lib/content.ts"

    index_id = _file_node_id(Path("src/pages/work/index.astro"))
    import_edges = {
        (e["source"], e["target"])
        for e in result["edges"]
        if e.get("relation") == "imports_from"
    }
    assert (index_id, "src_lib_content") in import_edges
    assert (index_id, "src_config") in import_edges


def test_svelte_absolute_inputs_no_ghost_import_nodes(tmp_path):
    """Svelte <script> static imports go through the same rescue path (#2195)."""
    root = Path(os.path.realpath(tmp_path))
    _write(
        root / "src/routes/page.svelte",
        """<script>
  import { projects } from '../lib/content';
  const lazy = () => import('../lib/content');
</script>
<h1>{projects.length}</h1>
""",
    )
    _write(root / "src/lib/content.ts", "export const projects = [1];\n")

    result = extract(
        [root / "src/routes/page.svelte", root / "src/lib/content.ts"],
        cache_root=root,
    )

    _assert_no_root_slug(result, root)

    content_file_nodes = [
        n for n in result["nodes"] if n["id"] == "src_lib_content"
    ]
    assert len(content_file_nodes) == 1
    assert content_file_nodes[0]["source_file"] == "src/lib/content.ts"

    page_id = _file_node_id(Path("src/routes/page.svelte"))
    edge_pairs = {
        (e["source"], e["target"], e["relation"]) for e in result["edges"]
    }
    assert (page_id, "src_lib_content", "imports_from") in edge_pairs
    assert (page_id, "src_lib_content", "dynamic_import") in edge_pairs


def test_astro_unresolved_relative_import_id_still_portable(tmp_path):
    """A rescued import whose target does NOT exist still mints a stub (so the
    edge survives as a hint), but the stub id must be the repo-relative form,
    not the absolute-path slug — the belt-and-braces remap in the
    relativization pass (#2195)."""
    root = Path(os.path.realpath(tmp_path))
    _write(
        root / "src/pages/index.astro",
        """---
import { gone } from '../missing/nowhere';
---
<p>x</p>
""",
    )
    result = extract([root / "src/pages/index.astro"], cache_root=root)

    _assert_no_root_slug(result, root)
    stub = [n for n in result["nodes"] if n.get("label") == "../missing/nowhere"]
    assert len(stub) == 1
    assert stub[0]["id"] == "src_missing_nowhere"
