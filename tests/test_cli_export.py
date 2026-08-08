"""Integration tests for graphify export subcommands and CLI commands.

Each test builds a minimal graph in a temp dir, runs the CLI command as a subprocess,
and asserts the expected output file exists and is non-empty / valid.
"""
from __future__ import annotations
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

PYTHON = sys.executable
FIXTURES = Path(__file__).parent / "fixtures"


def _run(args: list[str], cwd: Path, env: dict[str, str] | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        [PYTHON, "-m", "graphify"] + args,
        cwd=cwd,
        capture_output=True,
        text=True,
        env=env,
    )


def _make_graph(tmp_path: Path) -> Path:
    """Build a minimal graph.json + analysis/labels files in tmp_path/graphify-out/."""
    out = tmp_path / "graphify-out"
    out.mkdir()

    extraction = json.loads((FIXTURES / "extraction.json").read_text())
    from graphify.build import build_from_json
    from graphify.cluster import cluster, score_all
    from graphify.analyze import god_nodes, surprising_connections
    from graphify.export import to_json

    G = build_from_json(extraction)
    communities = cluster(G)
    cohesion = score_all(G, communities)
    gods = god_nodes(G)
    surprises = surprising_connections(G, communities)
    labels = {cid: f"Community {cid}" for cid in communities}

    to_json(G, communities, str(out / "graph.json"))

    analysis = {
        "communities": {str(k): v for k, v in communities.items()},
        "cohesion": {str(k): v for k, v in cohesion.items()},
        "gods": gods,
        "surprises": surprises,
    }
    (out / ".graphify_analysis.json").write_text(json.dumps(analysis))
    (out / ".graphify_labels.json").write_text(
        json.dumps({str(k): v for k, v in labels.items()})
    )
    return out


# ── graphify export html ─────────────────────────────────────────────────────

def test_export_html_creates_file(tmp_path):
    _make_graph(tmp_path)
    r = _run(["export", "html"], tmp_path)
    assert r.returncode == 0, r.stderr
    html = tmp_path / "graphify-out" / "graph.html"
    assert html.exists()
    assert html.stat().st_size > 0


def test_export_html_no_viz_removes_file(tmp_path):
    out = _make_graph(tmp_path)
    (out / "graph.html").write_text("<html/>")
    r = _run(["export", "html", "--no-viz"], tmp_path)
    assert r.returncode == 0, r.stderr
    assert not (out / "graph.html").exists()


def test_export_html_error_without_graph(tmp_path):
    r = _run(["export", "html"], tmp_path)
    assert r.returncode != 0


# ── graphify export obsidian ─────────────────────────────────────────────────

def test_export_obsidian_creates_vault(tmp_path):
    _make_graph(tmp_path)
    r = _run(["export", "obsidian"], tmp_path)
    assert r.returncode == 0, r.stderr
    vault = tmp_path / "graphify-out" / "obsidian"
    assert vault.exists()
    md_files = list(vault.glob("*.md"))
    assert len(md_files) > 0


def test_export_obsidian_custom_dir(tmp_path):
    _make_graph(tmp_path)
    custom = tmp_path / "my-vault"
    r = _run(["export", "obsidian", "--dir", str(custom)], tmp_path)
    assert r.returncode == 0, r.stderr
    assert custom.exists()
    assert len(list(custom.glob("*.md"))) > 0


# ── graphify export wiki ─────────────────────────────────────────────────────

def test_export_wiki_creates_articles(tmp_path):
    _make_graph(tmp_path)
    r = _run(["export", "wiki"], tmp_path)
    assert r.returncode == 0, r.stderr
    wiki = tmp_path / "graphify-out" / "wiki"
    assert wiki.exists()
    assert (wiki / "index.md").exists()


def test_export_wiki_accepts_edges_only_graph_json(tmp_path):
    out = _make_graph(tmp_path)
    graph_path = out / "graph.json"
    data = json.loads(graph_path.read_text())
    data["edges"] = data.pop("links")
    graph_path.write_text(json.dumps(data))

    r = _run(["export", "wiki"], tmp_path)

    assert r.returncode == 0, r.stderr
    assert (out / "wiki" / "index.md").exists()


# ── graphify export graphml ──────────────────────────────────────────────────

def test_export_graphml_creates_file(tmp_path):
    _make_graph(tmp_path)
    r = _run(["export", "graphml"], tmp_path)
    assert r.returncode == 0, r.stderr
    gml = tmp_path / "graphify-out" / "graph.graphml"
    assert gml.exists()
    assert gml.stat().st_size > 0
    content = gml.read_text()
    assert "<graphml" in content


# ── graphify export neo4j (cypher) ───────────────────────────────────────────

def test_export_neo4j_creates_cypher(tmp_path):
    _make_graph(tmp_path)
    r = _run(["export", "neo4j"], tmp_path)
    assert r.returncode == 0, r.stderr
    cypher = tmp_path / "graphify-out" / "cypher.txt"
    assert cypher.exists()
    assert cypher.stat().st_size > 0
    content = cypher.read_text()
    assert "MERGE" in content or "CREATE" in content


# ── graphify export falkordb (cypher) ────────────────────────────────────────

def test_export_falkordb_creates_cypher(tmp_path):
    _make_graph(tmp_path)
    r = _run(["export", "falkordb"], tmp_path)
    assert r.returncode == 0, r.stderr
    cypher = tmp_path / "graphify-out" / "cypher.txt"
    assert cypher.exists()
    assert cypher.stat().st_size > 0
    content = cypher.read_text()
    assert "MERGE" in content or "CREATE" in content


# ── graphify query ───────────────────────────────────────────────────────────

def test_query_returns_output(tmp_path):
    _make_graph(tmp_path)
    r = _run(["query", "test"], tmp_path)
    assert r.returncode == 0, r.stderr
    assert len(r.stdout) > 0


def test_query_dfs_flag(tmp_path):
    _make_graph(tmp_path)
    r = _run(["query", "test", "--dfs"], tmp_path)
    assert r.returncode == 0, r.stderr


def test_query_budget_flag(tmp_path):
    _make_graph(tmp_path)
    r = _run(["query", "test", "--budget", "500"], tmp_path)
    assert r.returncode == 0, r.stderr


def test_query_missing_graph_fails(tmp_path):
    r = _run(["query", "anything"], tmp_path)
    assert r.returncode != 0


def test_query_uses_graphify_out_env(tmp_path):
    out = _make_graph(tmp_path)
    custom_out = tmp_path / "custom-graph"
    out.rename(custom_out)
    env = os.environ.copy()
    env["GRAPHIFY_OUT"] = custom_out.name

    r = _run(["query", "test"], tmp_path, env=env)

    assert r.returncode == 0, r.stderr
    assert len(r.stdout) > 0


def test_extract_writes_to_graphify_out_env(tmp_path):
    """#1423: `graphify extract` honours GRAPHIFY_OUT for where it WRITES, not only
    where readers look — previously it hardcoded graphify-out/ and ignored the
    override. Code-only corpus, so no LLM backend is needed."""
    (tmp_path / "m.py").write_text("def a():\n    return b()\n\n\ndef b():\n    return 1\n")
    env = os.environ.copy()
    env["GRAPHIFY_OUT"] = "custom-out"

    r = _run(["extract", "."], tmp_path, env=env)

    assert r.returncode == 0, r.stderr
    assert (tmp_path / "custom-out" / "graph.json").exists(), r.stdout
    assert (tmp_path / "custom-out" / "manifest.json").exists()
    # The default dir must NOT be created when the override is set.
    assert not (tmp_path / "graphify-out").exists(), "extract ignored GRAPHIFY_OUT and wrote graphify-out/"
    # Manifest keys are relative to the scan root (portable) — #1417.
    keys = list(json.loads((tmp_path / "custom-out" / "manifest.json").read_text()).keys())
    assert keys == ["m.py"], keys


# ── graphify path ────────────────────────────────────────────────────────────

def test_path_runs_without_error(tmp_path):
    _make_graph(tmp_path)
    r = _run(["path", "Transformer", "LayerNorm"], tmp_path)
    # May find or not find a path — either is valid, should not crash
    assert r.returncode == 0, r.stderr


def test_path_missing_graph_fails(tmp_path):
    r = _run(["path", "a", "b"], tmp_path)
    assert r.returncode != 0


def test_path_uses_graphify_out_env(tmp_path):
    out = _make_graph(tmp_path)
    custom_out = tmp_path / "custom-graph"
    out.rename(custom_out)
    env = os.environ.copy()
    env["GRAPHIFY_OUT"] = custom_out.name

    r = _run(["path", "Transformer", "LayerNorm"], tmp_path, env=env)

    assert r.returncode == 0, r.stderr


# ── graphify path direction (#2487) ─────────────────────────────────────────

def _write_path_graph(tmp_path: Path, nodes: list[str], links: list[dict]) -> Path:
    """Write a minimal hand-rolled directed graph.json for path-direction tests."""
    out = tmp_path / "graphify-out"
    out.mkdir()
    (out / "graph.json").write_text(json.dumps({
        "directed": True,
        "multigraph": False,
        "graph": {},
        "nodes": [{"id": n, "label": n} for n in nodes],
        "links": links,
    }))
    return out


def _calls(src: str, tgt: str) -> dict:
    return {"source": src, "target": tgt, "relation": "calls"}


def test_path_directed_respects_direction(tmp_path):
    _write_path_graph(
        tmp_path, ["alpha", "beta", "gamma"],
        [_calls("alpha", "beta"), _calls("beta", "gamma")],
    )
    r = _run(["path", "alpha", "gamma"], tmp_path)
    assert r.returncode == 0, r.stderr
    assert r.stdout.count("-->") == 2
    assert "<--" not in r.stdout
    # Explicit --directed is the same as the default.
    r2 = _run(["path", "alpha", "gamma", "--directed"], tmp_path)
    assert r2.returncode == 0, r2.stderr
    assert r2.stdout == r.stdout


def test_path_directed_backwards_is_no_path(tmp_path):
    # Default-change guard (#2487): a plain `path` with no flag is directed,
    # so walking the chain backwards must report no directed path.
    _write_path_graph(
        tmp_path, ["alpha", "beta", "gamma"],
        [_calls("alpha", "beta"), _calls("beta", "gamma")],
    )
    r = _run(["path", "gamma", "alpha"], tmp_path)
    assert r.returncode == 0, r.stderr
    assert "No directed path found" in r.stdout
    assert "--undirected" in r.stdout
    assert "-->" not in r.stdout
    assert "<--" not in r.stdout


def test_path_undirected_flag_opt_in(tmp_path):
    _write_path_graph(
        tmp_path, ["alpha", "beta", "gamma"],
        [_calls("alpha", "beta"), _calls("beta", "gamma")],
    )
    r = _run(["path", "gamma", "alpha", "--undirected"], tmp_path)
    assert r.returncode == 0, r.stderr
    assert "Shortest path (2 hops)" in r.stdout
    assert r.stdout.count("<--calls--") == 2
    assert "-->" not in r.stdout


def test_path_directed_legacy_markers(tmp_path):
    # Legacy canonicalized file: the persisted arc is flipped (beta->alpha) but
    # the _src/_tgt markers carry the true direction alpha->beta. Direction
    # truth must come from the markers, not the raw arc order (#2309/#2487).
    _write_path_graph(
        tmp_path, ["alpha", "beta"],
        [{"source": "beta", "target": "alpha",
          "_src": "alpha", "_tgt": "beta", "relation": "calls"}],
    )
    r = _run(["path", "alpha", "beta"], tmp_path)
    assert r.returncode == 0, r.stderr
    assert "Shortest path (1 hops)" in r.stdout
    assert "-->" in r.stdout
    assert "<--" not in r.stdout
    r2 = _run(["path", "beta", "alpha"], tmp_path)
    assert r2.returncode == 0, r2.stderr
    assert "No directed path found" in r2.stdout


def test_path_directed_deterministic(tmp_path):
    # Diamond with two equal-length directed routes: the chosen route must not
    # depend on the process hash seed (#2074 discipline for the digraph too).
    _write_path_graph(
        tmp_path, ["start", "left", "right", "goal"],
        [_calls("start", "left"), _calls("left", "goal"),
         _calls("start", "right"), _calls("right", "goal")],
    )
    outputs = []
    for seed in ("0", "1"):
        env = os.environ.copy()
        env["PYTHONHASHSEED"] = seed
        r = _run(["path", "start", "goal"], tmp_path, env=env)
        assert r.returncode == 0, r.stderr
        assert "-->" in r.stdout
        outputs.append(r.stdout)
    assert outputs[0] == outputs[1]


def test_path_flags_mutually_exclusive(tmp_path):
    _write_path_graph(
        tmp_path, ["alpha", "beta"], [_calls("alpha", "beta")],
    )
    r = _run(["path", "alpha", "beta", "--directed", "--undirected"], tmp_path)
    assert r.returncode != 0
    assert "mutually exclusive" in r.stderr


# ── graphify explain ─────────────────────────────────────────────────────────

def test_explain_runs_without_error(tmp_path):
    _make_graph(tmp_path)
    r = _run(["explain", "test"], tmp_path)
    assert r.returncode == 0, r.stderr


def test_explain_missing_graph_fails(tmp_path):
    r = _run(["explain", "anything"], tmp_path)
    assert r.returncode != 0


def test_explain_uses_graphify_out_env(tmp_path):
    out = _make_graph(tmp_path)
    custom_out = tmp_path / "custom-graph"
    out.rename(custom_out)
    env = os.environ.copy()
    env["GRAPHIFY_OUT"] = custom_out.name

    r = _run(["explain", "test"], tmp_path, env=env)

    assert r.returncode == 0, r.stderr


# ── graphify export unknown format ───────────────────────────────────────────

def test_export_unknown_format_fails(tmp_path):
    r = _run(["export", "pdf"], tmp_path)
    assert r.returncode != 0


def test_update_no_cluster_writes_raw_graph(tmp_path):
    src = tmp_path / "sample.py"
    src.write_text("def f():\n    return 1\n", encoding="utf-8")

    r = _run(["update", ".", "--no-cluster"], tmp_path)
    assert r.returncode == 0, r.stderr

    graph_path = tmp_path / "graphify-out" / "graph.json"
    assert graph_path.exists()
    data = json.loads(graph_path.read_text(encoding="utf-8"))
    assert "nodes" in data and "links" in data
    assert all("community" not in node for node in data["nodes"])


# Regression test for #934 - cluster-only crashes when graphify-out/ doesn't exist

def test_cluster_only_creates_output_dir_when_missing(tmp_path):
    """cluster-only must not crash with FileNotFoundError when graphify-out/ is absent (#934)."""
    # Build graph.json somewhere other than the default graphify-out/ location
    # so we can point --graph at it while graphify-out/ doesn't exist yet.
    graph_src = tmp_path / "backup" / "graph.json"
    graph_src.parent.mkdir()

    out_dir = _make_graph(tmp_path)
    graph_json = out_dir / "graph.json"
    # Simulate user archiving the output dir before re-clustering
    import shutil
    shutil.copy(graph_json, graph_src)
    shutil.rmtree(out_dir)

    assert not (tmp_path / "graphify-out").exists()

    r = _run(["cluster-only", ".", "--graph", str(graph_src), "--no-viz"], tmp_path)
    assert r.returncode == 0, r.stderr
    assert (tmp_path / "graphify-out" / "GRAPH_REPORT.md").exists()


def test_cluster_only_graph_in_graphify_out_writes_beside_it(tmp_path):
    """#1747 Case 2: `cluster-only --graph <elsewhere>/graphify-out/graph.json`
    must write GRAPH_REPORT.md and the re-clustered graph beside that graph, not
    into a stray graphify-out/ in the CWD."""
    project = tmp_path / "project"
    project.mkdir()
    out_dir = _make_graph(project)  # project/graphify-out/graph.json

    cwd = tmp_path / "elsewhere"
    cwd.mkdir()
    r = _run(
        ["cluster-only", ".", "--graph", str(out_dir / "graph.json"), "--no-viz", "--no-label"],
        cwd,
    )
    assert r.returncode == 0, r.stderr
    assert (out_dir / "GRAPH_REPORT.md").exists()          # beside --graph
    assert not (cwd / "graphify-out").exists()             # no CWD pollution


def test_extract_out_does_not_pollute_corpus(tmp_path):
    """#1747 Case 1: `extract <corpus> --out <elsewhere>` must not leave a stray
    graphify-out/ (cache, stat-index) inside the scanned corpus."""
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "a.py").write_text("def main():\n    return 1\n")
    out = tmp_path / "scratch"

    r = _run(
        ["extract", str(corpus), "--out", str(out), "--no-cluster", "--code-only"],
        tmp_path,
    )
    assert r.returncode == 0, r.stderr
    assert (out / "graphify-out" / "graph.json").exists()   # graph in --out
    assert not (corpus / "graphify-out").exists()           # corpus untouched


# Regression test for #1027 - cluster-only must remap labels via node overlap

def test_cluster_only_persists_analysis_sidecar(tmp_path):
    """cluster-only must refresh .graphify_analysis.json alongside graph.json.

    Downstream export commands use the sidecar for community membership and
    should not see stale or missing community analysis after a recluster.
    """
    out = _make_graph(tmp_path)
    analysis_path = out / ".graphify_analysis.json"
    analysis_path.unlink()

    r = _run(["cluster-only", ".", "--no-viz"], tmp_path)
    assert r.returncode == 0, r.stderr
    assert analysis_path.exists()

    analysis = json.loads(analysis_path.read_text(encoding="utf-8"))
    assert analysis["communities"]
    assert analysis["cohesion"]
    assert "gods" in analysis
    assert "surprises" in analysis
    assert "questions" in analysis

    graph = json.loads((out / "graph.json").read_text(encoding="utf-8"))
    graph_cids = {
        str(node["community"])
        for node in graph.get("nodes", [])
        if node.get("community") is not None
    }
    assert graph_cids == set(analysis["communities"])


def test_cluster_only_remaps_labels_to_previous_cids(tmp_path):
    """cluster-only must invoke remap_communities_to_previous so the existing
    .graphify_labels.json keeps tracking the same conceptual communities after
    re-clustering. Without the remap call, Leiden's size-descending cid order
    re-applies labels by raw index and they silently misalign with cluster
    contents (#1027). Mirror of the watch/update fix from #822.
    """
    out = _make_graph(tmp_path)
    graph_json = out / "graph.json"
    labels_json = out / ".graphify_labels.json"

    # Tag every node with an out-of-band community id and write a labels file
    # keyed on those ids. After cluster-only, at least one of those sentinel
    # ids must survive in the labels file (= remap succeeded by node overlap).
    # If the cluster-only branch skips remap, Leiden returns small ints
    # (0, 1, ...) and the sentinel keys disappear entirely.
    g = json.loads(graph_json.read_text(encoding="utf-8"))
    nodes = g.get("nodes", [])
    assert len(nodes) >= 4, "fixture must have enough nodes to form 2+ communities"
    sentinel_a, sentinel_b = 4242, 9999
    half = len(nodes) // 2
    for i, n in enumerate(nodes):
        n["community"] = sentinel_a if i < half else sentinel_b
    graph_json.write_text(json.dumps(g), encoding="utf-8")
    labels_json.write_text(
        json.dumps({str(sentinel_a): "First Group", str(sentinel_b): "Second Group"}),
        encoding="utf-8",
    )

    r = _run(["cluster-only", ".", "--no-viz"], tmp_path)
    assert r.returncode == 0, r.stderr

    # Real signal: labels.json keys must align with the community ids actually
    # written to graph.json's per-node community attribute. Without remap,
    # Leiden returns small cids (0, 1, ...) but labels.json still carries the
    # old sentinel keys, so the intersection is empty and labels are orphaned.
    final_graph = json.loads(graph_json.read_text(encoding="utf-8"))
    final_labels = json.loads(labels_json.read_text(encoding="utf-8"))
    actual_cids = {n.get("community") for n in final_graph.get("nodes", [])}
    label_cids = {int(k) for k in final_labels.keys()}
    overlap = actual_cids & label_cids
    assert overlap, (
        f"After cluster-only with prior labels keyed on cids {label_cids}, at "
        f"least one of those cids must still appear in graph.json's community "
        f"attribute ({actual_cids}). Without remap_communities_to_previous "
        f"(#1027) Leiden renumbers communities to 0,1,... and the prior labels "
        f"become orphaned. Final labels: {final_labels}"
    )


# ── communities-fallback when .graphify_analysis.json is absent ──────────────
# The watch / post-commit rebuild path only writes graph.json + GRAPH_REPORT.md;
# it does NOT regenerate .graphify_analysis.json. The full `graphify extract`
# pipeline also removes its temp files at the end of the run on some skill
# workflows. In both cases the per-node `community` attribute is intact on
# every node in graph.json — that's the source of truth `to_json` writes.
# Without these tests, `graphify export html|obsidian|wiki|svg|graphml|neo4j`
# silently bails or generates a degraded artifact whenever the sidecar is
# missing, even though the data is right there.

def test_export_html_falls_back_to_node_community_attribute(tmp_path):
    """When .graphify_analysis.json is absent, export html should reconstruct
    communities from the per-node attribute in graph.json rather than bailing
    out with 'Single community - aggregated view not useful.'.
    """
    out = _make_graph(tmp_path)
    # Simulate the watch-rebuild / cleanup case: graph.json + labels survive,
    # analysis sidecar is gone.
    (out / ".graphify_analysis.json").unlink()

    r = _run(["export", "html"], tmp_path)
    assert r.returncode == 0, r.stderr
    html = out / "graph.html"
    assert html.exists(), "graph.html should be generated from the fallback"
    assert html.stat().st_size > 0
    # The success message comes from to_html — confirm we're not hitting the
    # "Single community" bail-out path.
    assert "Single community" not in r.stdout
    assert "Single community" not in r.stderr


def test_export_html_fallback_recovers_multiple_communities(tmp_path):
    """Stronger assertion: the reconstructed `communities` dict should have the
    SAME community count as the analysis sidecar would, so downstream code
    (aggregation thresholds, member counts) sees identical input.
    """
    out = _make_graph(tmp_path)

    # Read the canonical community count from the analysis sidecar
    analysis = json.loads((out / ".graphify_analysis.json").read_text(encoding="utf-8"))
    expected_count = len(analysis["communities"])

    # And the count we'd reconstruct from graph.json's node attributes
    graph = json.loads((out / "graph.json").read_text(encoding="utf-8"))
    reconstructed_cids = {
        n["community"] for n in graph.get("nodes", [])
        if n.get("community") is not None
    }
    assert len(reconstructed_cids) == expected_count, (
        f"reconstruction would lose communities: sidecar={expected_count} vs "
        f"graph.json={len(reconstructed_cids)}"
    )

    # Now remove the sidecar and confirm the CLI still succeeds end-to-end.
    (out / ".graphify_analysis.json").unlink()
    r = _run(["export", "html"], tmp_path)
    assert r.returncode == 0, r.stderr
    assert (out / "graph.html").exists()


def test_export_html_no_community_data_at_all_still_succeeds(tmp_path):
    """If a graph.json was somehow written without any per-node `community`
    attribute (older versions of to_json, hand-built graphs), the fallback
    should produce an empty communities dict and the renderer should still
    not crash. Whether the aggregated view is useful is a separate question.
    """
    out = _make_graph(tmp_path)
    (out / ".graphify_analysis.json").unlink()

    # Strip the community attribute from every node
    graph_path = out / "graph.json"
    graph = json.loads(graph_path.read_text(encoding="utf-8"))
    for n in graph.get("nodes", []):
        n.pop("community", None)
    graph_path.write_text(json.dumps(graph), encoding="utf-8")

    r = _run(["export", "html"], tmp_path)
    # Should NOT crash. It may print a warning and skip rendering, but exit
    # code stays clean — same behaviour as the pre-fallback empty-communities
    # path, just no longer silently failing on the common case.
    assert r.returncode == 0, r.stderr


def test_graph_json_node_ids_are_portable_across_checkout_paths(tmp_path):
    """#1789: the committed graph.json's node ids must be relative to the scan
    root — not embed the absolute path — so the same repo yields identical ids
    on any machine/checkout and leaks no local username/home."""
    def _build(root: Path):
        (root / "pkg").mkdir(parents=True)
        (root / "pkg" / "mod.py").write_text("def f(): return 1\n")
        (root / "pkg" / "app.py").write_text("from pkg.mod import f\ndef g(): return f()\n")
        r = _run(["extract", ".", "--code-only", "--no-cluster"], root)
        assert r.returncode == 0, r.stderr
        data = json.loads((root / "graphify-out" / "graph.json").read_text())
        return sorted(n["id"] for n in data["nodes"])

    a = _build(tmp_path / "alice_home" / "proj")
    b = _build(tmp_path / "bob_elsewhere" / "checkout" / "proj")
    assert a == b, f"node ids differ across checkout paths: {a} vs {b}"
    leak = {"alice_home", "bob_elsewhere", "checkout", "tmp", "private", "users", "home", "var"}
    assert not any(part in leak for ident in a for part in ident.split("_")), \
        f"node id embeds an absolute-path component: {a}"


# ── cluster-only silent failures (#2534) + refused-write exit code (#2522) ───


def test_cluster_only_reports_failure_when_write_is_refused(tmp_path):
    """The #479 shrink guard can refuse to overwrite graph.json. cluster-only
    still printed "graph.json updated" and exited 0, and it had already written
    GRAPH_REPORT.md and the labels for the clustering it then discarded (#2436).
    Contributed by @aniJani (#2522)."""
    out = _make_graph(tmp_path)
    graph_json = out / "graph.json"

    # Duplicate node ids make the file look larger than the graph it loads into,
    # which is what trips the guard on a real re-cluster.
    data = json.loads(graph_json.read_text(encoding="utf-8"))
    data["nodes"] = data["nodes"] + data["nodes"][:3]
    graph_json.write_text(json.dumps(data), encoding="utf-8")

    report = out / "GRAPH_REPORT.md"
    report.write_text("PREVIOUS REPORT\n", encoding="utf-8")
    before = graph_json.read_text(encoding="utf-8")

    r = _run(["cluster-only", ".", "--no-viz", "--no-label"], tmp_path)

    assert r.returncode != 0, r.stdout
    assert "graph.json NOT written" in r.stderr, r.stderr
    assert "graph.json updated" not in r.stdout, r.stdout
    assert graph_json.read_text(encoding="utf-8") == before
    assert report.read_text(encoding="utf-8") == "PREVIOUS REPORT\n"


def test_cluster_only_happy_path_exits_zero(tmp_path):
    """Guard for the #2522 reordering: the normal re-cluster still succeeds."""
    _make_graph(tmp_path)
    r = _run(["cluster-only", ".", "--no-viz"], tmp_path)
    assert r.returncode == 0, r.stderr
    assert "Done -" in r.stdout, r.stdout
    assert "communities" in r.stdout


def test_cluster_only_warns_when_labeling_flags_are_ignored(tmp_path):
    """#2534 case 1: with a saved .graphify_labels.json the reuse branch never
    calls the LLM, so --backend/--model/--batch-size used to be silently
    ignored while exiting 0. Reuse stays a success (exit 0), but the ignored
    flags must be named on stderr."""
    _make_graph(tmp_path)  # persists .graphify_labels.json -> reuse branch

    r = _run(["cluster-only", ".", "--backend", "openai", "--no-viz"], tmp_path)
    assert r.returncode == 0, r.stderr
    assert "--backend" in r.stderr and "ignored" in r.stderr, r.stderr
    assert "reusing saved labels" in r.stderr, r.stderr
    # the reuse branch must NOT have gone through the LLM labeling path
    assert "Labeling communities" not in r.stdout, r.stdout


def test_cluster_only_reuse_without_labeling_flags_stays_quiet(tmp_path):
    """Control for the #2534 case-1 warning: plain reuse prints no flag warning."""
    _make_graph(tmp_path)
    r = _run(["cluster-only", ".", "--no-viz"], tmp_path)
    assert r.returncode == 0, r.stderr
    assert "ignored" not in r.stderr, r.stderr
    assert "reusing saved labels" not in r.stderr, r.stderr


# ── cluster-only must not re-stamp built_at_commit from the shell's cwd ──────


def _init_git_repo(path: Path, message: str) -> str:
    """git init + one empty commit; returns the HEAD sha."""
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q", str(path)], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(path), "-c", "user.email=t@test", "-c", "user.name=t",
         "-c", "commit.gpgsign=false", "commit", "--allow-empty", "-q", "-m", message],
        check=True, capture_output=True,
    )
    return subprocess.run(
        ["git", "-C", str(path), "rev-parse", "HEAD"],
        check=True, capture_output=True, text=True,
    ).stdout.strip()


def test_cluster_only_preserves_built_at_commit_from_other_repo_cwd(tmp_path):
    """#2534 case 4: cluster-only re-clusters an EXISTING graph, so the
    extract-time built_at_commit must survive — running it from a DIFFERENT
    repo used to re-stamp graph.json with that repo's HEAD."""
    target = tmp_path / "target"
    commit_x = _init_git_repo(target, "init target")
    out = _make_graph(target)
    graph_json = out / "graph.json"
    data = json.loads(graph_json.read_text(encoding="utf-8"))
    data["built_at_commit"] = commit_x
    graph_json.write_text(json.dumps(data), encoding="utf-8")

    other = tmp_path / "other"
    commit_y = _init_git_repo(other, "init other")
    assert commit_x != commit_y

    r = _run(["cluster-only", str(target), "--no-viz"], other)
    assert r.returncode == 0, r.stderr
    final = json.loads(graph_json.read_text(encoding="utf-8"))
    assert final.get("built_at_commit") == commit_x, (
        f"built_at_commit re-stamped from the shell's cwd: expected {commit_x}, "
        f"got {final.get('built_at_commit')} (other repo HEAD is {commit_y})"
    )


def test_cluster_only_preserves_built_at_commit_from_non_repo_cwd(tmp_path):
    """#2534 case 4: from a cwd that is not a git repo at all, the stamp must
    still be preserved — not dropped."""
    target = tmp_path / "target"
    commit_x = _init_git_repo(target, "init target")
    out = _make_graph(target)
    graph_json = out / "graph.json"
    data = json.loads(graph_json.read_text(encoding="utf-8"))
    data["built_at_commit"] = commit_x
    graph_json.write_text(json.dumps(data), encoding="utf-8")

    plain = tmp_path / "plain"
    plain.mkdir()
    r = _run(["cluster-only", str(target), "--no-viz"], plain)
    assert r.returncode == 0, r.stderr
    final = json.loads(graph_json.read_text(encoding="utf-8"))
    assert final.get("built_at_commit") == commit_x
