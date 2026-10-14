"""Integration tests for incremental graphify extract behavior."""
from __future__ import annotations
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

PYTHON = sys.executable

# Backend-selecting env vars. These tests assume no working LLM backend (a docs
# corpus should fail without one); strip them so a developer who has a real
# ANTHROPIC_API_KEY / OPENAI_API_KEY / etc. exported does not make a docs extract
# succeed and break the "no backend" path. CI has none of these set anyway.
_LLM_ENV_KEYS = (
    "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY",
    "MOONSHOT_API_KEY", "DEEPSEEK_API_KEY", "OLLAMA_BASE_URL",
    "AWS_PROFILE", "AWS_REGION", "AWS_DEFAULT_REGION", "AWS_ACCESS_KEY_ID",
)


def _run(args: list[str], cwd: Path) -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items() if k not in _LLM_ENV_KEYS}
    return subprocess.run(
        [PYTHON, "-m", "graphify"] + args,
        cwd=cwd,
        capture_output=True,
        text=True,
        env=env,
    )


def _make_docs_corpus(tmp_path: Path) -> Path:
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "intro.md").write_text("# Introduction\nThis doc introduces the system.")
    (docs / "api.md").write_text("# API Reference\nThe API has endpoints.")
    return docs


def test_manifest_written_after_extract(tmp_path):
    """After a full extract run, manifest.json must exist (or run fails before writing it)."""
    docs = _make_docs_corpus(tmp_path)
    r = _run(["extract", str(docs)], tmp_path)
    # Should fail with no API key — but NOT with a path error
    assert "no LLM API key" in r.stderr or r.returncode != 0
    # manifest should NOT exist (run failed before writing)
    manifest = docs / "graphify-out" / "manifest.json"
    assert not manifest.exists()


def test_incremental_mode_detected_via_manifest(tmp_path):
    """If manifest.json + graph.json exist, incremental mode message is shown."""
    docs = _make_docs_corpus(tmp_path)
    out = docs / "graphify-out"
    out.mkdir()
    (out / "graph.json").write_text(json.dumps({"nodes": [], "links": []}))
    (out / "manifest.json").write_text(json.dumps({"document": [str(docs / "intro.md")]}))
    r = _run(["extract", str(docs)], tmp_path)
    combined = r.stdout + r.stderr
    assert "incremental" in combined.lower() or r.returncode != 0


def test_no_incremental_without_manifest(tmp_path):
    """Without manifest.json, full scan message is shown (not incremental)."""
    docs = _make_docs_corpus(tmp_path)
    r = _run(["extract", str(docs)], tmp_path)
    # Check combined output doesn't contain incremental-mode phrasing.
    # Use a phrase rather than a bare word to avoid matching the tmp_path,
    # which pytest derives from the test name and contains "incremental".
    assert "incremental update" not in r.stdout.lower()
    assert "incremental scan" not in r.stdout.lower()


def test_extract_no_cluster_incremental_noop_preserves_existing_graph(tmp_path):
    """#1347: no-op incremental no-cluster extract must not overwrite graph.json."""
    project = tmp_path / "project"
    project.mkdir()
    (project / "app.py").write_text(
        "def alpha():\n    return 1\n", encoding="utf-8"
    )

    first = _run(["extract", str(project), "--no-cluster"], tmp_path)
    assert first.returncode == 0, first.stderr
    graph_path = project / "graphify-out" / "graph.json"
    before_text = graph_path.read_text(encoding="utf-8")
    before = json.loads(before_text)
    assert before.get("nodes"), "first run should produce a non-empty code graph"

    second = _run(["extract", str(project), "--no-cluster"], tmp_path)
    assert second.returncode == 0, second.stderr

    after_text = graph_path.read_text(encoding="utf-8")
    after = json.loads(after_text)
    assert after.get("nodes"), "no-op incremental run must not empty the graph"
    assert after_text == before_text


def _edges(graph_json: Path) -> list[dict]:
    g = json.loads(graph_json.read_text())
    return g.get("links", g.get("edges", []))


def test_extract_no_cluster_incremental_changed_file_preserves_unchanged_files(tmp_path):
    """#2169: an incremental --no-cluster extract of ONE changed file must merge
    into the existing graph, not overwrite graph.json with just that file's
    chunk — and the changed file's cross-file import edges must keep pointing at
    the unchanged target file's canonical node ids, not dangling
    absolute-path-derived ones."""
    proj = tmp_path / "proj"
    (proj / "app" / "add").mkdir(parents=True)
    (proj / "src" / "components").mkdir(parents=True)
    (proj / "src" / "components" / "ScanScreen.tsx").write_text(
        "export function ScanScreen() {\n  return null;\n}\n", encoding="utf-8"
    )
    scan_tsx = proj / "app" / "add" / "scan.tsx"
    scan_tsx.write_text(
        "import {ScanScreen} from '../../src/components/ScanScreen';\n"
        "export default ScanScreen;\n",
        encoding="utf-8",
    )

    first = _run(["extract", str(proj), "--code-only", "--no-cluster"], tmp_path)
    assert first.returncode == 0, first.stderr
    gj = proj / "graphify-out" / "graph.json"
    base = json.loads(gj.read_text(encoding="utf-8"))
    base_ids = {n["id"] for n in base["nodes"]}
    # Sanity: importer file, target file, and target symbol all present.
    assert {
        "app_add_scan",
        "src_components_scanscreen",
        "src_components_scanscreen_scanscreen",
    } <= base_ids, base_ids

    # Change ONLY scan.tsx (harmless comment), then re-run the same command.
    scan_tsx.write_text(
        scan_tsx.read_text(encoding="utf-8") + "\n// touched\n", encoding="utf-8"
    )
    second = _run(["extract", str(proj), "--code-only", "--no-cluster"], tmp_path)
    assert second.returncode == 0, second.stderr
    # Guard against a silent full rescan masking the merge bug.
    assert "incremental scan" in second.stdout.lower(), second.stdout

    after = json.loads(gj.read_text(encoding="utf-8"))
    after_ids = {n["id"] for n in after["nodes"]}
    # The unchanged file's nodes must survive the incremental raw write.
    assert after_ids == base_ids, (
        f"incremental --no-cluster dropped/changed nodes: "
        f"missing={base_ids - after_ids}, extra={after_ids - base_ids}"
    )
    after_edges = after.get("links", after.get("edges", []))
    # The unchanged file's own edge survives.
    assert any(
        e.get("relation") == "contains"
        and e.get("source") == "src_components_scanscreen"
        and e.get("target") == "src_components_scanscreen_scanscreen"
        for e in after_edges
    ), after_edges
    # No dangling endpoints on cross-file edges: the changed file's re-extracted
    # imports/re-exports must resolve to the unchanged target's canonical ids,
    # not absolute-path-derived ghosts (the extract.py half of #2169).
    for e in after_edges:
        if e.get("relation") in ("imports_from", "re_exports", "contains", "imports"):
            assert e.get("source") in after_ids, f"dangling source: {e}"
            assert e.get("target") in after_ids, f"dangling target: {e}"


def test_update_preserves_generic_rust_self_call_to_unchanged_impl(tmp_path):
    """The CLI incremental context carries Rust impl-family identity."""
    proj = tmp_path / "proj"
    proj.mkdir()
    (proj / "state.rs").write_text(
        "pub struct Bucket<T> { value: T }\n", encoding="utf-8"
    )
    (proj / "method.rs").write_text(
        "impl<T> Bucket<T> {\n"
        "    pub fn fetch_value(&self) {}\n"
        "}\n",
        encoding="utf-8",
    )
    caller = proj / "caller.rs"
    caller.write_text(
        "impl<U> Bucket<U> {\n"
        "    pub fn run(&self) { self.fetch_value(); }\n"
        "}\n",
        encoding="utf-8",
    )

    first = _run(
        ["extract", str(proj), "--code-only", "--no-cluster"], tmp_path
    )
    assert first.returncode == 0, first.stderr

    def has_call() -> bool:
        graph = json.loads(
            (proj / "graphify-out" / "graph.json").read_text(encoding="utf-8")
        )
        nodes = {
            (node.get("label"), node.get("source_file")): node["id"]
            for node in graph.get("nodes", [])
        }
        pair = (
            nodes[(".run()", "caller.rs")],
            nodes[(".fetch_value()", "method.rs")],
        )
        return any(
            edge.get("relation") == "calls"
            and (edge.get("source"), edge.get("target")) == pair
            for edge in graph.get("links", graph.get("edges", []))
        )

    assert has_call()
    caller.write_text(
        "impl<U> Bucket<U> {\n"
        "    pub fn run(&self) { let marker = 1; self.fetch_value(); }\n"
        "}\n",
        encoding="utf-8",
    )
    second = _run(["update", str(proj), "--no-cluster"], tmp_path)
    assert second.returncode == 0, second.stderr
    assert has_call()


def test_extract_no_cluster_incremental_code_only_preserves_doc_nodes(tmp_path):
    """#2169: an incremental --code-only --no-cluster run over a mixed corpus
    must carry forward doc-sourced nodes it did not re-extract."""
    proj = tmp_path / "proj"
    proj.mkdir()
    util = proj / "util.py"
    util.write_text("def alpha():\n    return 1\n", encoding="utf-8")
    (proj / "notes.md").write_text("# Notes\nSome prose.\n", encoding="utf-8")

    first = _run(["extract", str(proj), "--code-only", "--no-cluster"], tmp_path)
    assert first.returncode == 0, first.stderr
    gj = proj / "graphify-out" / "graph.json"
    g = json.loads(gj.read_text(encoding="utf-8"))
    assert g.get("nodes"), "first run should produce a non-empty code graph"

    # Seed a doc-sourced node, as a prior (LLM-backed) run would have written.
    g["nodes"].append({
        "id": "notes",
        "label": "notes.md",
        "type": "document",
        "source_file": "notes.md",
    })
    gj.write_text(json.dumps(g), encoding="utf-8")

    # Change only the code file; the doc node must survive the incremental run.
    util.write_text(
        "def alpha():\n    return 1\n\ndef beta():\n    return 2\n",
        encoding="utf-8",
    )
    second = _run(["extract", str(proj), "--code-only", "--no-cluster"], tmp_path)
    assert second.returncode == 0, second.stderr
    assert "incremental scan" in second.stdout.lower(), second.stdout

    after = json.loads(gj.read_text(encoding="utf-8"))
    after_by_id = {n["id"]: n for n in after["nodes"]}
    assert "notes" in after_by_id, (
        f"doc node dropped by incremental --code-only --no-cluster: "
        f"{sorted(after_by_id)}"
    )
    assert after_by_id["notes"].get("source_file") == "notes.md"
    # And the changed code file was actually re-extracted.
    assert any("beta" in i for i in after_by_id), sorted(after_by_id)


def test_incremental_python_relative_import_target_canonicalizes(tmp_path):
    """#2213 (defect 1, shared root with #2211): a Python relative import's
    imports_from edge must stamp target_file so the #2169 remap canonicalizes
    its target on an incremental extraction where the target file is NOT in
    the batch — instead of leaving an absolute-path-derived dangling id."""
    from graphify.extract import extract, _make_id

    # realpath: on macOS the pytest tmp dir can sit behind a symlink
    # (/tmp -> /private/tmp); anchor everything on the resolved form so the
    # canonical-id assertions are deterministic.
    tmp = Path(os.path.realpath(tmp_path))
    pkg = tmp / "pkg"
    pkg.mkdir()
    (pkg / "b.py").write_text(
        "class Thing:\n    def go(self):\n        return 1\n", encoding="utf-8"
    )
    a = pkg / "a.py"
    a.write_text(
        "from .b import Thing\n\n\ndef use():\n    return Thing().go()\n",
        encoding="utf-8",
    )

    full = extract([a, pkg / "b.py"], cache_root=tmp)
    full_imports = [
        e for e in full["edges"]
        if e.get("relation") == "imports_from"
        and str(e.get("source_file", "")).endswith("a.py")
    ]
    assert full_imports, full["edges"]
    canonical = full_imports[0]["target"]
    assert canonical == "pkg_b", canonical

    # Incremental: only the importer is in the batch (b.py unchanged, so the
    # #2169 merge path re-extracts a.py alone). Same cache/scan root.
    inc = extract([a], cache_root=tmp)
    inc_imports = [
        e for e in inc["edges"]
        if e.get("relation") == "imports_from"
        and str(e.get("source_file", "")).endswith("a.py")
    ]
    assert inc_imports, inc["edges"]
    assert inc_imports[0]["target"] == canonical, inc_imports
    # Not an absolute-path-shaped ghost id (…_pkg_b would end "_b", but the
    # pre-fix dangling form was the full path with the extension folded in).
    assert not inc_imports[0]["target"].endswith("_py"), inc_imports

    root_slug = _make_id(str(tmp))
    for e in inc["edges"]:
        assert root_slug not in str(e.get("target", "")), e
        # The target_file hint is transient and must never ship.
        assert "target_file" not in e, e


def test_incremental_md_reference_target_canonicalizes(tmp_path):
    """#2211: a markdown [link](docs/setup.md) references edge must stamp
    target_file so the #2169 remap canonicalizes its target on an incremental
    extraction where the linked doc is NOT in the batch — instead of the
    md->md reference dangling on an absolute-path-derived id and dropping."""
    from graphify.extract import extract, _make_id

    tmp = Path(os.path.realpath(tmp_path))
    docs = tmp / "docs"
    docs.mkdir()
    setup = docs / "setup.md"
    setup.write_text("# Setup\nInstall the thing.\n", encoding="utf-8")
    claude = tmp / "CLAUDE.md"
    claude.write_text(
        "# Overview\nSee [setup](docs/setup.md) for install steps.\n",
        encoding="utf-8",
    )

    full = extract([claude, setup], cache_root=tmp)
    full_refs = [
        e for e in full["edges"]
        if e.get("relation") == "references"
        and str(e.get("source_file", "")).endswith("CLAUDE.md")
    ]
    assert full_refs, full["edges"]
    canonical = full_refs[0]["target"]
    assert canonical == "docs_setup", canonical

    # Incremental: only the linking doc is in the batch.
    inc = extract([claude], cache_root=tmp)
    inc_refs = [
        e for e in inc["edges"]
        if e.get("relation") == "references"
        and str(e.get("source_file", "")).endswith("CLAUDE.md")
    ]
    assert inc_refs, inc["edges"]
    assert inc_refs[0]["target"] == canonical, inc_refs

    root_slug = _make_id(str(tmp))
    for e in inc["edges"]:
        assert root_slug not in str(e.get("target", "")), e
        assert "target_file" not in e, e


def test_update_prunes_a_removed_imports_edge(tmp_path):
    """#1521: when an import is deleted from a file, `graphify update` must prune
    the edge it produced — preserving it (keyed only on endpoint membership) left a
    stale edge that drove phantom circular-dependency findings."""
    proj = tmp_path / "proj"
    pkg = proj / "pkg"
    pkg.mkdir(parents=True)
    (pkg / "b.py").write_text("def helper():\n    return 1\n")
    (pkg / "a.py").write_text("from pkg.b import helper\ndef use():\n    return helper()\n")

    # initial extract -> the import edge a -> b exists
    r1 = _run(["extract", str(proj), "--no-cluster"], tmp_path)
    assert r1.returncode == 0, r1.stderr
    gj = proj / "graphify-out" / "graph.json"
    before = _edges(gj)
    assert any(e.get("relation") in ("imports", "imports_from") and
               str(e.get("source_file", "")).endswith("a.py") for e in before), \
        f"expected an import edge from a.py initially: {before}"

    # remove the import, then update
    (pkg / "a.py").write_text("def use():\n    return 1\n")
    r2 = _run(["update", str(proj)], tmp_path)
    assert r2.returncode == 0, r2.stderr
    after = _edges(gj)

    # the stale import edge owned by a.py must be gone
    stale = [e for e in after
             if e.get("relation") in ("imports", "imports_from")
             and str(e.get("source_file", "")).endswith("a.py")]
    assert not stale, f"removed import's edge survived update (stale): {stale}"


def test_update_preserves_cross_file_imports_and_calls_to_unchanged_file(tmp_path):
    """#3776: incremental update must resolve symbols defined in unchanged files."""
    proj = tmp_path / "proj"
    proj.mkdir()
    (proj / "b.py").write_text("def helper():\n    return 1\n", encoding="utf-8")
    a = proj / "a.py"
    a.write_text(
        "from b import helper\n\n"
        "def use():\n"
        "    return helper()\n",
        encoding="utf-8",
    )

    r1 = _run(["extract", str(proj), "--no-cluster"], tmp_path)
    assert r1.returncode == 0, r1.stderr
    gj = proj / "graphify-out" / "graph.json"
    before = _edges(gj)

    # Initial build must contain both the imports edge and the calls edge
    has_import_before = any(
        e.get("relation") == "imports"
        and e.get("source") == "a"
        and e.get("target") == "b_helper"
        for e in before
    )
    assert has_import_before, f"expected initial imports edge a -> b_helper: {before}"

    has_call_before = any(
        e.get("relation") == "calls"
        and e.get("source") == "a_use"
        and e.get("target") == "b_helper"
        for e in before
    )
    assert has_call_before, f"expected initial calls edge a_use -> b_helper: {before}"

    # Modify only a.py with an unrelated change
    a.write_text(
        "from b import helper\n\n"
        "def use():\n"
        "    # unrelated change\n"
        "    return helper()\n",
        encoding="utf-8",
    )

    r2 = _run(["extract", str(proj), "--code-only", "--no-cluster"], tmp_path)
    assert r2.returncode == 0, r2.stderr
    after = _edges(gj)

    # Incremental update must preserve the imports edge to the unchanged file
    has_import_after = any(
        e.get("relation") == "imports"
        and e.get("source") == "a"
        and e.get("target") == "b_helper"
        for e in after
    )
    assert has_import_after, f"imports edge a -> b_helper lost after incremental update: {after}"

    # Incremental update must preserve the calls edge to the unchanged file
    has_call_after = any(
        e.get("relation") == "calls"
        and e.get("source") == "a_use"
        and e.get("target") == "b_helper"
        for e in after
    )
    assert has_call_after, f"calls edge a_use -> b_helper lost after incremental update: {after}"


@pytest.mark.parametrize("relative_out", [False, True], ids=["absolute-out", "relative-out"])
def test_update_external_output_keeps_nested_identity_and_unchanged_call_target(
    tmp_path, monkeypatch, relative_out
):
    """#1287: cache placement must not become the extractor's source root."""
    monkeypatch.delenv("GRAPHIFY_OUT", raising=False)
    monkeypatch.delenv("GRAPHIFY_FORCE", raising=False)
    project = tmp_path / "project"
    for directory in ("app", "services", "other"):
        (project / directory).mkdir(parents=True)
    target = project / "services" / "util.py"
    target.write_text("def helper():\n    return 1\n", encoding="utf-8")
    (project / "other" / "util.py").write_text(
        "def unrelated():\n    return 2\n", encoding="utf-8"
    )
    caller = project / "app" / "caller.py"
    caller.write_text(
        "from services.util import helper\n\n"
        "def use():\n    return helper()\n",
        encoding="utf-8",
    )
    external = tmp_path / "external"
    source_arg = "project"
    out_arg = "external" if relative_out else str(external)
    out = external / "graphify-out"
    graph_path = out / "graph.json"
    manifest_path = out / "manifest.json"

    first = _run(
        ["extract", source_arg, "--code-only", "--no-cluster", "--out", out_arg],
        tmp_path,
    )
    assert first.returncode == 0, first.stderr
    before = json.loads(graph_path.read_text(encoding="utf-8"))
    before_nodes = {node["id"]: node for node in before["nodes"]}
    expected = {"app_caller_use", "services_util_helper", "other_util_unrelated"}
    assert expected <= before_nodes.keys(), before_nodes.keys()
    assert before_nodes["services_util_helper"]["source_file"] == "services/util.py"
    assert before_nodes["other_util_unrelated"]["source_file"] == "other/util.py"
    assert before_nodes["app_caller_use"]["source_file"] == "app/caller.py"
    assert any(
        edge.get("relation") == "calls"
        and edge.get("source") == "app_caller_use"
        and edge.get("target") == "services_util_helper"
        for edge in _edges(graph_path)
    )
    # Preserve a live semantic layer across relative-source and cross-CWD updates.
    (project / "guide.txt").write_text("A guide to this project.\n", encoding="utf-8")
    before["nodes"].append({
        "id": "guide_topic", "label": "Guide", "file_type": "concept",
        "source_file": "guide.txt", "_origin": "semantic",
    })
    before["links" if "links" in before else "edges"].append({
        "source": "guide_topic", "target": "app_caller_use",
        "relation": "implemented_by", "confidence": "INFERRED",
        "source_file": "guide.txt",
    })
    graph_path.write_text(json.dumps(before), encoding="utf-8")
    before_manifest = manifest_path.read_text(encoding="utf-8")

    # Change only the caller; the callee must be reused under its original ID.
    caller.write_text(
        "from services.util import helper\n\n"
        "def use():\n    marker = 1\n    return helper() + marker\n",
        encoding="utf-8",
    )
    out_option = [f"--out={out_arg}"] if relative_out else ["--out", out_arg]
    second = _run(["update", source_arg, *out_option, "--no-cluster"], tmp_path)
    assert second.returncode == 0, second.stderr
    after = json.loads(graph_path.read_text(encoding="utf-8"))
    after_nodes = {node["id"]: node for node in after["nodes"]}
    assert expected <= after_nodes.keys(), after_nodes.keys()
    for node_id in expected:
        assert after_nodes[node_id]["source_file"] == before_nodes[node_id]["source_file"]
    assert any(
        edge.get("relation") == "calls"
        and edge.get("source") == "app_caller_use"
        and edge.get("target") == "services_util_helper"
        for edge in _edges(graph_path)
    ), after.get("links", after.get("edges", []))
    assert after_nodes["guide_topic"]["source_file"] == "guide.txt"
    other_cwd = tmp_path / "elsewhere"
    other_cwd.mkdir()
    recovered = _run(["update", "--out", str(external), "--no-cluster"], other_cwd)
    assert recovered.returncode == 0, recovered.stderr
    retained = json.loads(graph_path.read_text(encoding="utf-8"))
    assert any(
        node["id"] == "guide_topic" and node["source_file"] == "guide.txt"
        for node in retained["nodes"]
    )
    assert any(
        edge["source"] == "guide_topic" and edge["target"] == "app_caller_use"
        for edge in retained.get("links", retained.get("edges", []))
    )
    assert manifest_path.read_text(encoding="utf-8") != before_manifest
    assert (out / "cache" / "stat-index.json").exists()
    assert not (project / "graphify-out").exists()

    # The CLI rebuild above covers the full corpus. A changed-path rebuild
    # exercises the incremental resolver with the callee absent from its batch.
    from graphify.watch import _rebuild_code

    caller.write_text(
        caller.read_text(encoding="utf-8").replace("marker = 1", "marker = 2")
        + "\ndef fresh():\n    return use()\n",
        encoding="utf-8",
    )
    assert _rebuild_code(
        project, changed_paths=[caller], output_root=external,
        no_cluster=relative_out, acquire_lock=False,
    ) is True
    partial = json.loads(graph_path.read_text(encoding="utf-8"))
    partial_nodes = {node["id"]: node for node in partial["nodes"]}
    assert "app_caller_fresh" in partial_nodes
    assert partial_nodes["services_util_helper"]["source_file"] == "services/util.py"
    assert partial_nodes["services_util_helper"]["id"] == before_nodes["services_util_helper"]["id"]
    assert partial_nodes["app_caller_use"]["source_file"] == "app/caller.py"
    assert any(
        edge.get("relation") == "calls"
        and edge.get("source") == "app_caller_use"
        and edge.get("target") == "services_util_helper"
        for edge in partial.get("links", partial.get("edges", []))
    ), partial.get("links", partial.get("edges", []))
    assert partial_nodes["guide_topic"]["source_file"] == "guide.txt"
    if not relative_out:
        assert (out / "GRAPH_REPORT.md").exists()
    assert not (project / "graphify-out").exists()

    # With no path argument, update must recover this project from the marker
    # in the selected external output, including when --force is combined.
    assert (out / ".graphify_root").read_text(encoding="utf-8") == str(project.resolve())
    caller.write_text(
        caller.read_text(encoding="utf-8") + "\ndef added():\n    return use()\n",
        encoding="utf-8",
    )
    third = _run(["update", "--out", out_arg, "--force", "--no-cluster"], tmp_path)
    assert third.returncode == 0, third.stderr
    final_ids = {
        node["id"] for node in json.loads(graph_path.read_text(encoding="utf-8"))["nodes"]
    }
    assert "app_caller_added" in final_ids
    assert not (project / "graphify-out").exists()


def test_update_absolute_graphify_out_keeps_inherited_location(tmp_path, monkeypatch):
    """An inherited absolute GRAPHIFY_OUT still owns graph, marker, and caches."""
    project = tmp_path / "project"
    project.mkdir()
    (project / "app.py").write_text("def run(): pass\n", encoding="utf-8")
    (project / "guide.txt").write_text(
        "The guide describes the project in plain text.\n", encoding="utf-8"
    )
    shared = tmp_path / "shared-graphify-out"
    ignored = tmp_path / "ignored-prefix"
    monkeypatch.setenv("GRAPHIFY_OUT", str(shared))
    result = _run(
        ["update", str(project), "--out", str(ignored), "--no-cluster"], tmp_path
    )
    assert result.returncode == 0, result.stderr
    assert (shared / "graph.json").exists()
    assert (shared / "manifest.json").exists()
    assert (shared / ".graphify_root").read_text(encoding="utf-8") == str(project.resolve())
    assert (shared / "cache" / "stat-index.json").exists()
    assert not (ignored / "graphify-out").exists()
    assert not (project / "graphify-out").exists()


def test_update_invalid_external_output_does_not_fall_back(tmp_path, monkeypatch):
    monkeypatch.delenv("GRAPHIFY_OUT", raising=False)
    project = tmp_path / "project"
    project.mkdir()
    (project / "app.py").write_text("def run(): pass\n", encoding="utf-8")
    blocked = tmp_path / "not-a-directory"
    blocked.write_text("occupied", encoding="utf-8")
    result = _run(["update", str(project), "--out", str(blocked)], tmp_path)
    assert result.returncode != 0
    assert blocked.read_text(encoding="utf-8") == "occupied"
    assert not (project / "graphify-out").exists()


@pytest.mark.parametrize("options", [["--out"], ["--out="], ["--out", "--force"]])
def test_update_rejects_missing_output_root(tmp_path, options):
    result = _run(["update", *options], tmp_path)
    assert result.returncode == 2
    assert "--out requires a directory" in result.stderr
    assert not (tmp_path / "graphify-out").exists()


@pytest.mark.parametrize("source_arg", [".", "src"])
def test_update_same_root_out_keeps_portable_marker(tmp_path, monkeypatch, source_arg):
    monkeypatch.delenv("GRAPHIFY_OUT", raising=False)
    original = tmp_path / "original"
    other = tmp_path / "other"
    project = original / source_arg
    project.mkdir(parents=True)
    (other / source_arg).mkdir(parents=True)
    (project / "app.py").write_text("def from_original(): pass\n", encoding="utf-8")
    (other / source_arg / "app.py").write_text("def from_other(): pass\n", encoding="utf-8")
    initial = _run(
        ["extract", source_arg, "--out", source_arg, "--code-only", "--no-cluster"],
        original,
    )
    assert initial.returncode == 0, initial.stderr
    result = _run(["update", source_arg, "--out", source_arg, "--no-cluster"], original)
    assert result.returncode == 0, result.stderr
    out = project / "graphify-out"
    assert (out / ".graphify_root").read_text() == source_arg

    recovered = _run(["update", "--out", str(project), "--no-cluster"], other)
    assert recovered.returncode == 0, recovered.stderr
    graph = json.loads((out / "graph.json").read_text())
    ids = {node["id"] for node in graph["nodes"]}
    assert "app_from_original" in ids
    assert "app_from_other" not in ids
    assert (out / ".graphify_root").read_text() == str(project.resolve())
    assert not (other / source_arg / "graphify-out").exists()


def test_update_does_not_resurrect_a_dropped_cross_file_edge_via_context(tmp_path):
    """#3776 negative: the resolution-context index widens the *target* view with
    unchanged files, so it must not resurrect an edge the edited file no longer
    warrants. Here b.py (with `helper`) stays unchanged and a.py drops its import
    and call — the a -> b_helper edges must NOT survive just because b_helper is
    still visible through the context index."""
    proj = tmp_path / "proj"
    proj.mkdir()
    (proj / "b.py").write_text("def helper():\n    return 1\n", encoding="utf-8")
    a = proj / "a.py"
    a.write_text(
        "from b import helper\n\n"
        "def use():\n"
        "    return helper()\n",
        encoding="utf-8",
    )

    r1 = _run(["extract", str(proj), "--no-cluster"], tmp_path)
    assert r1.returncode == 0, r1.stderr
    gj = proj / "graphify-out" / "graph.json"
    before = _edges(gj)
    assert any(
        e.get("relation") == "imports"
        and e.get("source") == "a"
        and e.get("target") == "b_helper"
        for e in before
    ), f"expected initial imports edge a -> b_helper: {before}"

    # Edit ONLY a.py to drop the import and the call; b.py (and b_helper) unchanged.
    a.write_text(
        "def use():\n"
        "    return 1\n",
        encoding="utf-8",
    )

    r2 = _run(["extract", str(proj), "--code-only", "--no-cluster"], tmp_path)
    assert r2.returncode == 0, r2.stderr
    after = _edges(gj)

    stale = [
        e for e in after
        if e.get("source") in ("a", "a_use")
        and e.get("target") == "b_helper"
        and e.get("relation") in ("imports", "calls")
    ]
    assert not stale, f"dropped cross-file edge resurrected via context index: {stale}"
