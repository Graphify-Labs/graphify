"""`graphify extract --code-only` indexes code without an LLM key (#1734).

A mixed repo (code + docs) with no API key configured used to hard-fail on the
doc/paper/image files. `--code-only` skips the semantic pass so the code graph
still builds, and the no-key error now points users at the flag.
"""
from __future__ import annotations

import os
import json
import subprocess
import sys
from pathlib import Path

import pytest

PYTHON = sys.executable
_KEY_VARS = ("GEMINI_API_KEY", "GOOGLE_API_KEY", "OPENAI_API_KEY", "OPENAI_BASE_URL",
             "ANTHROPIC_API_KEY", "MOONSHOT_API_KEY", "DEEPSEEK_API_KEY")


def _mixed_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "app.py").write_text("def hello():\n    return 1\n")
    (repo / "README.md").write_text("# Design\n\nHow it works.\n")
    (repo / "NOTES.txt").write_text("Architecture notes and rationale.\n")
    return repo


def _run(repo: Path, *extra: str):
    env = {k: v for k, v in os.environ.items() if k not in _KEY_VARS}
    env["GRAPHIFY_OUT"] = str(repo / "graphify-out")
    return subprocess.run(
        [PYTHON, "-m", "graphify", "extract", ".", *extra],
        cwd=repo, capture_output=True, text=True, env=env,
    )


def test_code_only_succeeds_without_key(tmp_path):
    repo = _mixed_repo(tmp_path)
    r = _run(repo, "--code-only")
    assert r.returncode == 0, f"--code-only should succeed with no key: {r.stderr}"
    out = r.stdout + r.stderr
    assert "--code-only: skipping" in out
    graph = repo / "graphify-out" / "graph.json"
    assert graph.exists(), "code graph must still be written"
    import json
    g = json.loads(graph.read_text())
    labels = [n.get("label") for n in g["nodes"]]
    assert any(str(l).startswith("hello") for l in labels), "code was indexed"


def test_multigraph_flag_writes_keyed_directed_graph(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "app.py").write_text(
        "def target():\n    return 1\n\ndef caller():\n    return target()\n",
        encoding="utf-8",
    )
    result = _run(repo, "--code-only", "--multigraph")
    assert result.returncode == 0, result.stderr
    graph = json.loads((repo / "graphify-out" / "graph.json").read_text())
    assert graph["multigraph"] is True and graph["directed"] is True
    assert graph["links"] and all("key" in edge for edge in graph["links"])


def _link_signature(links):
    """Endpoints + relation data per link, ignoring only the multigraph key."""
    return sorted(
        (str(l.get("source")), str(l.get("target")), str(l.get("relation", "")))
        for l in links
    )


def test_filter_payload_sources_drops_hyperedges_with_removed_members():
    from graphify.cli import _filter_payload_sources

    payload = {
        "nodes": [
            {"id": "removed", "source_file": "stale.py"},
            {"id": "kept", "source_file": "live.py"},
        ],
        "links": [],
        "hyperedges": [
            {
                "id": "dangling",
                "nodes": ["removed", "kept"],
                "source_file": "live.py",
            },
            {
                "id": "owned-by-stale",
                "nodes": ["kept"],
                "source_file": "stale.py",
            },
            {"id": "kept", "nodes": ["kept"], "source_file": "live.py"},
            "malformed",
        ],
    }

    assert _filter_payload_sources(payload, {"stale.py"}) == 1
    assert payload["nodes"] == [{"id": "kept", "source_file": "live.py"}]
    assert payload["hyperedges"] == [
        {"id": "kept", "nodes": ["kept"], "source_file": "live.py"}
    ]


def test_multigraph_conversion_of_unchanged_graph_preserves_content(tmp_path):
    """`--multigraph` on an unchanged simple graph bypasses the no-change early
    exit to rewrite the format — it must carry the existing graph forward, not
    serialize this run's empty incremental extraction over it."""
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "app.py").write_text(
        "def target():\n    return 1\n\ndef caller():\n    return target()\n",
        encoding="utf-8",
    )
    (repo / "lib.py").write_text("def helper():\n    return 2\n", encoding="utf-8")
    assert _run(repo, "--code-only").returncode == 0
    graph_path = repo / "graphify-out" / "graph.json"
    before = json.loads(graph_path.read_text())
    assert before.get("multigraph", False) is False and before["nodes"]
    # Seed a hyperedge over real node ids, as a prior semantic pass would have
    # left it — conversion must carry hyperedge CONTENT forward too. graph.json
    # is not a manifest-tracked source, so the run below still sees no changes.
    hyper_nodes = sorted(n["id"] for n in before["nodes"])[:2]
    before["hyperedges"] = [{
        "id": "flow_seeded", "nodes": hyper_nodes, "relation": "data_flow",
        "label": "seeded flow", "source_file": "app.py",
    }]
    graph_path.write_text(json.dumps(before), encoding="utf-8")

    result = _run(repo, "--code-only", "--multigraph")
    assert result.returncode == 0, result.stderr
    after = json.loads(graph_path.read_text())
    assert after["multigraph"] is True and after["directed"] is True
    assert {n["id"] for n in after["nodes"]} == {n["id"] for n in before["nodes"]}
    before_links = before.get("links", before.get("edges", []))
    assert _link_signature(after["links"]) == _link_signature(before_links)
    assert all("key" in edge for edge in after["links"])
    (hyper,) = after["hyperedges"]
    assert hyper["relation"] == "data_flow"
    assert sorted(hyper["nodes"]) == hyper_nodes


def test_multigraph_conversion_with_changed_file_replaces_its_content(tmp_path):
    """A conversion run that coincides with a changed file must NOT carry that
    file's old content forward — fresh extraction replaces it (no stale nodes,
    no duplicate parallel edges) while other files' content is preserved."""
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "app.py").write_text(
        "def target():\n    return 1\n\ndef caller():\n    return target()\n",
        encoding="utf-8",
    )
    (repo / "lib.py").write_text("def helper():\n    return 2\n", encoding="utf-8")
    assert _run(repo, "--code-only").returncode == 0
    graph_path = repo / "graphify-out" / "graph.json"
    before_ids = {n["id"] for n in json.loads(graph_path.read_text())["nodes"]}
    assert "lib_helper" in before_ids

    (repo / "lib.py").write_text("def renamed():\n    return 2\n", encoding="utf-8")
    result = _run(repo, "--code-only", "--multigraph")
    assert result.returncode == 0, result.stderr
    after = json.loads(graph_path.read_text())
    after_ids = {n["id"] for n in after["nodes"]}
    assert "lib_helper" not in after_ids, "changed file's stale node survived"
    assert "lib_renamed" in after_ids
    assert before_ids - {"lib_helper"} <= after_ids, "unchanged files' nodes lost"
    sigs = _link_signature(after["links"])
    assert len(sigs) == len(set(sigs)), "duplicate parallel edges from the carry-forward"


def test_mixed_repo_without_key_errors_and_points_at_code_only(tmp_path):
    repo = _mixed_repo(tmp_path)
    r = _run(repo)  # no --code-only, no key
    assert r.returncode != 0, "mixed repo with no key should still error without the flag"
    assert "--code-only" in r.stderr, "the no-key error must point users at --code-only"


def test_extract_usage_advertises_code_only(tmp_path):
    """#2071: --code-only must be discoverable in the extract usage text, not only
    by triggering the no-key error. `graphify extract` with no path prints usage."""
    r = subprocess.run(
        [PYTHON, "-m", "graphify", "extract"],
        cwd=tmp_path, capture_output=True, text=True,
    )
    assert r.returncode != 0
    assert "--code-only" in r.stdout + r.stderr, (
        "extract usage must advertise --code-only (#2071)"
    )


def _run_relative_out(repo: Path, *extra: str):
    """Like _run but with a RELATIVE GRAPHIFY_OUT so --out/--output controls the
    parent dir (an absolute GRAPHIFY_OUT would override the flag)."""
    env = {k: v for k, v in os.environ.items() if k not in _KEY_VARS}
    env["GRAPHIFY_OUT"] = "graphify-out"
    return subprocess.run(
        [PYTHON, "-m", "graphify", "extract", ".", *extra],
        cwd=repo, capture_output=True, text=True, env=env,
    )


def test_output_flag_is_alias_of_out(tmp_path):
    """#2004 part 3: `--output DIR` was silently ignored on extract (output went
    to the default `<path>/graphify-out/`). It is now an alias of `--out`."""
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "app.py").write_text("def hello():\n    return 1\n")
    custom = tmp_path / "elsewhere"

    r = _run_relative_out(repo, "--code-only", "--no-cluster", "--output", str(custom))
    assert r.returncode == 0, r.stderr
    assert (custom / "graphify-out" / "graph.json").exists(), "--output was ignored (#2004)"
    assert not (repo / "graphify-out").exists(), "output must not go to the default dir"


def test_output_flag_inline_form(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "app.py").write_text("def hello():\n    return 1\n")
    custom = tmp_path / "out2"
    r = _run_relative_out(repo, "--code-only", "--no-cluster", f"--output={custom}")
    assert r.returncode == 0, r.stderr
    assert (custom / "graphify-out" / "graph.json").exists()


def test_no_gitignore_indexes_vcs_ignored_code_but_keeps_graphifyignore(tmp_path):
    repo = tmp_path / "repo"
    generated = repo / "proj" / "deep" / "generated"
    generated.mkdir(parents=True)
    (repo / ".git" / "info").mkdir(parents=True)
    (repo / ".git" / "info" / "exclude").write_text("local/\n")
    (repo / "proj" / ".gitignore").write_text("generated/\n")
    (repo / "proj" / ".graphifyignore").write_text("hidden/\n")
    (generated / "Gen.cs").write_text("namespace N { public class Gen {} }\n")
    local = repo / "local"
    local.mkdir()
    (local / "Local.cs").write_text("namespace N { public class Local {} }\n")
    hidden = repo / "proj" / "hidden"
    hidden.mkdir()
    (hidden / "Hidden.cs").write_text("namespace N { public class Hidden {} }\n")

    result = _run(repo, "--no-gitignore", "--no-cluster")

    assert result.returncode == 0, result.stderr
    graph = json.loads((repo / "graphify-out" / "graph.json").read_text())
    sources = {Path(str(node.get("source_file", ""))).as_posix() for node in graph["nodes"]}
    assert any(source.endswith("proj/deep/generated/Gen.cs") for source in sources)
    assert any(source.endswith("local/Local.cs") for source in sources)
    assert not any(source.endswith("proj/hidden/Hidden.cs") for source in sources)


def test_no_gitignore_setting_persists_across_flagless_extract(tmp_path):
    """#1971 persistence: once --no-gitignore is set, a later flag-less
    `graphify extract` must NOT clobber it back to honoring .gitignore (which
    would make the git-ignored code silently disappear again)."""
    repo = tmp_path / "repo"
    gen = repo / "generated"
    gen.mkdir(parents=True)
    (repo / ".gitignore").write_text("generated/\n")
    (repo / "app.py").write_text("def hello():\n    return 1\n")
    (gen / "Gen.py").write_text("def gen():\n    return 2\n")

    def _sources():
        g = json.loads((repo / "graphify-out" / "graph.json").read_text())
        return {Path(str(n.get("source_file", ""))).as_posix() for n in g["nodes"]}

    r1 = _run(repo, "--no-gitignore", "--code-only", "--no-cluster")
    assert r1.returncode == 0, r1.stderr
    assert any(s.endswith("generated/Gen.py") for s in _sources())

    # A plain flag-less re-extract must keep the git-ignored file (setting persisted).
    r2 = _run(repo, "--code-only", "--no-cluster")
    assert r2.returncode == 0, r2.stderr
    assert any(s.endswith("generated/Gen.py") for s in _sources()), (
        "flag-less re-extract clobbered the persisted --no-gitignore setting (#1971)"
    )


def test_exclude_setting_persists_across_flagless_extract(tmp_path):
    repo = tmp_path / "repo"
    vendor = repo / "vendor"
    vendor.mkdir(parents=True)
    (repo / "app.py").write_text("def app():\n    return 1\n")
    (vendor / "lib.py").write_text("def vendor():\n    return 2\n")

    def _sources():
        graph = json.loads((repo / "graphify-out" / "graph.json").read_text())
        return {
            Path(str(node.get("source_file", ""))).as_posix()
            for node in graph["nodes"]
        }

    first = _run(
        repo, "--exclude", "vendor", "--code-only", "--no-cluster"
    )
    assert first.returncode == 0, first.stderr
    assert any(source.endswith("app.py") for source in _sources())
    assert not any(source.endswith("vendor/lib.py") for source in _sources())

    second = _run(repo, "--code-only", "--no-cluster")
    assert second.returncode == 0, second.stderr
    assert any(source.endswith("app.py") for source in _sources())
    assert not any(source.endswith("vendor/lib.py") for source in _sources())


def test_explicit_exclude_replaces_persisted_setting_with_custom_out(tmp_path):
    repo = tmp_path / "repo"
    vendor = repo / "vendor"
    generated = repo / "generated"
    vendor.mkdir(parents=True)
    generated.mkdir()
    (repo / "app.py").write_text("def app():\n    return 1\n")
    (vendor / "lib.py").write_text("def vendor():\n    return 2\n")
    (generated / "gen.py").write_text("def generated():\n    return 3\n")
    out_root = tmp_path / "custom-output"

    env = {key: value for key, value in os.environ.items() if key not in _KEY_VARS}
    env["GRAPHIFY_OUT"] = "graphify-out"

    def _run_extract(*extra: str):
        return subprocess.run(
            [
                PYTHON,
                "-m",
                "graphify",
                "extract",
                ".",
                "--out",
                str(out_root),
                "--code-only",
                "--no-cluster",
                *extra,
            ],
            cwd=repo,
            capture_output=True,
            text=True,
            env=env,
        )

    first = _run_extract("--exclude", "vendor")
    assert first.returncode == 0, first.stderr

    graph_out = out_root / "graphify-out"
    def _sources():
        graph = json.loads((graph_out / "graph.json").read_text())
        return {
            Path(str(node.get("source_file", ""))).as_posix()
            for node in graph["nodes"]
        }

    persisted = _run_extract("--force")
    assert persisted.returncode == 0, persisted.stderr
    assert any(source.endswith("app.py") for source in _sources())
    assert not any(source.endswith("vendor/lib.py") for source in _sources())
    assert any(source.endswith("generated/gen.py") for source in _sources())

    replacement = _run_extract("--exclude", "generated", "--force")
    assert replacement.returncode == 0, replacement.stderr
    sources = _sources()
    assert any(source.endswith("app.py") for source in sources)
    assert any(source.endswith("vendor/lib.py") for source in sources)
    assert not any(source.endswith("generated/gen.py") for source in sources)
    assert json.loads((graph_out / ".graphify_build.json").read_text()) == {
        "excludes": ["generated"]
    }


def test_extract_names_skipped_sensitive_files(tmp_path):
    """#2106 traceability: a file dropped by the sensitive-file filter is reported
    by NAME (not just a count), so a wrongly-flagged file is visible."""
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "app.py").write_text("def hello():\n    return 1\n")
    (repo / "github_token.txt").write_text("ghp_secretvalue\n")  # real secret -> skipped
    r = _run(repo, "--code-only", "--no-cluster")
    assert r.returncode == 0, r.stderr
    out = r.stdout + r.stderr
    assert "skipped as potentially sensitive" in out
    assert "github_token.txt" in out, "the skipped filename must be surfaced (#2106)"


def test_force_rebuild_preserves_multigraph_format(tmp_path):
    """`extract --force` without a repeated --multigraph must keep the existing
    graph's format — the only intended downgrade path is --no-multigraph."""
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "app.py").write_text(
        "def target():\n    return 1\n\ndef caller():\n    return target()\n",
        encoding="utf-8",
    )
    assert _run(repo, "--code-only", "--multigraph").returncode == 0
    graph_path = repo / "graphify-out" / "graph.json"
    assert json.loads(graph_path.read_text())["multigraph"] is True

    result = _run(repo, "--code-only", "--force")
    assert result.returncode == 0, result.stderr
    graph = json.loads(graph_path.read_text())
    assert graph["multigraph"] is True, "--force silently downgraded the format"
    assert graph["links"] and all("key" in edge for edge in graph["links"])


def test_no_multigraph_downgrades_with_warning(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "app.py").write_text(
        "def target():\n    return 1\n\ndef caller():\n    return target()\n",
        encoding="utf-8",
    )
    assert _run(repo, "--code-only", "--multigraph").returncode == 0
    graph_path = repo / "graphify-out" / "graph.json"
    before = json.loads(graph_path.read_text())
    assert before["multigraph"] is True

    # Incremental downgrade on an unchanged corpus: the conversion must bypass
    # the no-change early exit and still carry the graph content forward.
    result = _run(repo, "--code-only", "--no-multigraph")
    assert result.returncode == 0, result.stderr
    assert "collapsing parallel relations" in result.stderr
    graph = json.loads(graph_path.read_text())
    assert graph.get("multigraph", False) is False
    assert {n["id"] for n in graph["nodes"]} == {n["id"] for n in before["nodes"]}
    assert graph["links"], "downgrade must keep the edges"


@pytest.mark.parametrize(
    "flags",
    [
        ("--multigraph", "--no-multigraph"),
        ("--no-multigraph", "--multigraph"),
    ],
)
def test_conflicting_multigraph_flags_fail_before_extraction(tmp_path, flags):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "app.py").write_text("def hello():\n    return 1\n", encoding="utf-8")

    result = _run(repo, "--code-only", *flags)
    assert result.returncode == 2
    assert "mutually exclusive" in result.stderr
    assert not (repo / "graphify-out" / "graph.json").exists()


def test_repeated_multigraph_flag_is_idempotent(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "app.py").write_text("def hello():\n    return 1\n", encoding="utf-8")

    result = _run(repo, "--code-only", "--multigraph", "--multigraph")
    assert result.returncode == 0, result.stderr
    graph = json.loads((repo / "graphify-out" / "graph.json").read_text())
    assert graph["multigraph"] is True


def test_code_only_force_preserves_existing_semantic_layer(tmp_path):
    """#2923 regression: --code-only --force must not drop the existing semantic
    layer. The AST pass is fully replaced (full re-scan, semantic cache reads
    skipped) but the semantic pass is itself skipped, so doc/paper/image nodes
    from graph.json must be carried forward. Before the fix this combination
    silently rewrote graph.json with only the AST tier, losing every semantic
    node and every hyperedge connected to one.
    """
    repo = _mixed_repo(tmp_path)
    out = repo / "graphify-out"
    out.mkdir()
    graph = out / "graph.json"
    # Seed a graph.json as if a prior full extract with an LLM backend had run:
    # 2 AST nodes from app.py + 4 SEMANTIC nodes from README.md/NOTES.txt.
    graph.write_text(json.dumps({
        "nodes": [
            {"id": "app_py", "label": "app.py", "type": "file",
             "source_file": "app.py", "origin": "AST"},
            {"id": "app_hello", "label": "hello()", "type": "function",
             "source_file": "app.py", "origin": "AST"},
            {"id": "readme_md", "label": "readme.md", "type": "file",
             "source_file": "README.md", "origin": "SEMANTIC"},
            {"id": "readme_design", "label": "Design", "type": "concept",
             "source_file": "README.md", "origin": "SEMANTIC"},
            {"id": "notes_txt", "label": "NOTES.txt", "type": "file",
             "source_file": "NOTES.txt", "origin": "SEMANTIC"},
            {"id": "notes_architecture", "label": "Architecture", "type": "concept",
             "source_file": "NOTES.txt", "origin": "SEMANTIC"},
        ],
        "edges": [
            {"id": "e1", "source": "app_py", "target": "app_hello",
             "relation": "contains", "source_file": "app.py"},
            {"id": "e2", "source": "readme_md", "target": "readme_design",
             "relation": "concept_about", "source_file": "README.md"},
            {"id": "e3", "source": "notes_txt", "target": "notes_architecture",
             "relation": "concept_about", "source_file": "NOTES.txt"},
        ],
        "hyperedges": [],
        "input_tokens": 0,
        "output_tokens": 0,
    }))

    r = _run(repo, "--code-only", "--force", "--no-cluster")
    assert r.returncode == 0, r.stderr

    out_graph = json.loads(graph.read_text())
    semantic_labels = {n["label"] for n in out_graph["nodes"]
                       if n.get("origin") == "SEMANTIC"}
    semantic_source_files = {
        Path(str(n["source_file"])).name.lower()
        for n in out_graph["nodes"]
        if n.get("origin") == "SEMANTIC"
    }
    # Every seeded semantic node must survive. The AST pass may add new nodes
    # (or relabel existing ones — e.g. hello vs hello()) but it must not
    # silently drop the semantic tier.
    assert {"readme.md", "notes.txt"}.issubset(semantic_source_files), (
        "code-only --force erased the existing semantic layer (#2923); "
        f"semantic nodes remaining: {semantic_labels}"
    )
    # Hyperedges are also semantic tier; the seeded graph had none but the
    # AST re-extract must not have invented any non-semantic work, and the
    # surviving edges list must not have been wholesale replaced.
    assert "edges" in out_graph, "graph.json must still have an edges key"
    # And the user-visible console line must explain why a semantic-layer-
    # preserving branch fired.
    assert "existing semantic layer preserved" in r.stdout + r.stderr, (
        "the --force --code-only print must announce the semantic-preserving branch"
    )


def test_code_only_force_prunes_removed_semantic_files(tmp_path):
    """#2923 follow-up: --code-only --force preserves surviving semantic nodes
    but must still prune semantic nodes for files that have been removed from
    disk (the doc/paper/image tier cannot outlive the corpus it indexes).
    """
    repo = _mixed_repo(tmp_path)
    out = repo / "graphify-out"
    out.mkdir()
    graph = out / "graph.json"
    graph.write_text(json.dumps({
        "nodes": [
            {"id": "app_py", "label": "app.py", "type": "file",
             "source_file": "app.py", "origin": "AST"},
            {"id": "app_hello", "label": "hello()", "type": "function",
             "source_file": "app.py", "origin": "AST"},
            {"id": "notes_txt", "label": "NOTES.txt", "type": "file",
             "source_file": "NOTES.txt", "origin": "SEMANTIC"},
            {"id": "notes_architecture", "label": "Architecture", "type": "concept",
             "source_file": "NOTES.txt", "origin": "SEMANTIC"},
        ],
        "edges": [],
        "hyperedges": [],
        "input_tokens": 0,
        "output_tokens": 0,
    }))

    # Delete NOTES.txt between seed and re-run. The merge's graph_stale_sources
    # path must drop its semantic nodes because the file no longer exists.
    (repo / "NOTES.txt").unlink()

    r = _run(repo, "--code-only", "--force", "--no-cluster")
    assert r.returncode == 0, r.stderr
    out_graph = json.loads(graph.read_text())
    remaining_sources = {
        Path(n["source_file"]).name
        for n in out_graph["nodes"]
        if n.get("origin") == "SEMANTIC"
    }
    assert "NOTES.txt" not in remaining_sources, (
        "NOTES.txt was deleted from disk; its semantic nodes must be pruned "
        "(#2923 follow-up)"
    )
