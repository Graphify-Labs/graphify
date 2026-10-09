"""#197: `graphify pipeline <step>` — the skill's steps as importable functions.

The skill used to run each pipeline step as inline `python -c`, which forced an
interpreter path through `$(cat graphify-out/.graphify_python)` and triggered an
approval prompt per step. These tests pin the behaviour that replaced it: the same
sidecars, the same graph, and a clean error when a step is run out of order.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]


def _gx(*args: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "graphify", *args],
        cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace",
    )


@pytest.fixture()
def corpus(tmp_path: Path) -> Path:
    """A small mixed corpus: one code file, one doc."""
    src = tmp_path / "src"
    (src / "pkg").mkdir(parents=True)
    (src / "pkg" / "mod.py").write_text(
        "def helper(x):\n"
        "    return x + 1\n"
        "\n"
        "class Widget:\n"
        "    def render(self):\n"
        "        return helper(1)\n",
        encoding="utf-8",
    )
    (src / "notes.md").write_text("# Notes\n\nA short document.\n", encoding="utf-8")
    return src


def test_pipeline_lists_its_steps(capsys: pytest.CaptureFixture[str]) -> None:
    """No args prints the step inventory, so a skill author can discover the surface."""
    from graphify.cli import _pipeline_usage

    usage = _pipeline_usage()
    for step in ("detect", "extract-ast", "merge-extraction", "build", "save-manifest"):
        assert step in usage, f"{step} missing from the pipeline usage text"


def test_unknown_pipeline_step_exits_with_the_valid_list(tmp_path: Path) -> None:
    p = _gx("pipeline", "nope", cwd=tmp_path)
    assert p.returncode != 0
    assert "unknown pipeline step 'nope'" in p.stderr
    assert "merge-extraction" in p.stderr, "error must list what is available"


def test_detect_writes_sidecar_and_reports_count(corpus: Path, tmp_path: Path) -> None:
    work = tmp_path / "work"
    work.mkdir()
    p = _gx("pipeline", "detect", str(corpus), cwd=work)
    assert p.returncode == 0, p.stderr

    sidecar = work / "graphify-out" / ".graphify_detect.json"
    assert sidecar.exists(), "detect must write .graphify_detect.json"
    data = json.loads(sidecar.read_text(encoding="utf-8"))
    assert data["total_files"] == 2
    assert any(f.endswith("mod.py") for f in data["files"]["code"])
    assert any(f.endswith("notes.md") for f in data["files"]["document"])
    assert "Detected 2 files" in p.stdout


def test_full_code_only_pipeline_matches_the_inline_python_result(
    corpus: Path, tmp_path: Path
) -> None:
    """A code-only run must produce the same graph the old inline blocks produced.

    Walks detect -> extract-ast -> empty-semantic -> merge-extraction -> build, then
    asserts the graph is non-empty and every sidecar Part C needed exists. This is the
    #197 claim in miniature: same graph, no inline Python.
    """
    work = tmp_path / "work"
    work.mkdir()

    for step in ("detect", "extract-ast", "empty-semantic", "merge-extraction", "build"):
        args = ["pipeline", step, str(corpus)] if step in ("detect", "extract-ast", "build") else ["pipeline", step]
        p = _gx(*args, cwd=work)
        assert p.returncode == 0, f"{step} failed: {p.stderr}"

    out = work / "graphify-out"
    graph = json.loads((out / "graph.json").read_text(encoding="utf-8"))
    nodes = graph.get("nodes", [])
    assert nodes, "code-only corpus must still produce a graph"
    labels = {n.get("label") for n in nodes}
    assert "helper()" in labels, f"AST node for helper() missing from {sorted(labels)}"
    assert "Widget" in labels, f"AST node for Widget missing from {sorted(labels)}"

    for sidecar in (
        ".graphify_detect.json", ".graphify_ast.json",
        ".graphify_semantic.json", ".graphify_extract.json",
        ".graphify_analysis.json",
    ):
        assert (out / sidecar).exists(), f"{sidecar} missing after the pipeline"

    report = (out / "GRAPH_REPORT.md").read_text(encoding="utf-8")
    assert "helper()" in report, "report should mention the extracted symbol"


def test_merge_extraction_without_its_input_fails_loudly(tmp_path: Path) -> None:
    """A step run out of order must error, not silently write an empty graph."""
    work = tmp_path / "work"
    (work / "graphify-out").mkdir(parents=True)
    p = _gx("pipeline", "merge-extraction", cwd=work)
    assert p.returncode != 0
    assert "AST sidecar missing" in p.stderr
    assert not (work / "graphify-out" / ".graphify_extract.json").exists()


def test_build_refuses_an_empty_graph_without_clobbering_outputs(tmp_path: Path) -> None:
    """#479/#1392: an empty extraction must not overwrite a good graph.json."""
    work = tmp_path / "work"
    out = work / "graphify-out"
    out.mkdir(parents=True)
    (out / "graph.json").write_text('{"nodes": ["sentinel"], "edges": []}', encoding="utf-8")
    (out / "GRAPH_REPORT.md").write_text("sentinel report", encoding="utf-8")
    (out / ".graphify_detect.json").write_text('{"files": {}, "total_files": 0}', encoding="utf-8")
    (out / ".graphify_extract.json").write_text('{"nodes": [], "edges": []}', encoding="utf-8")

    p = _gx("pipeline", "build", str(work), cwd=work)
    assert p.returncode != 0
    assert "graph is empty" in p.stderr
    assert json.loads((out / "graph.json").read_text(encoding="utf-8"))["nodes"] == ["sentinel"]
    assert (out / "GRAPH_REPORT.md").read_text(encoding="utf-8") == "sentinel report"


def test_label_requires_valid_json_labels(corpus: Path, tmp_path: Path) -> None:
    """`--labels` is the replacement for pasting a LABELS_DICT into a code block."""
    work = tmp_path / "work"
    work.mkdir()
    for step in ("detect", "extract-ast", "empty-semantic", "merge-extraction", "build"):
        args = ["pipeline", step, str(corpus)] if step in ("detect", "extract-ast", "build") else ["pipeline", step]
        assert _gx(*args, cwd=work).returncode == 0

    bad = _gx("pipeline", "label", str(corpus), "--labels", "not-json", cwd=work)
    assert bad.returncode != 0
    assert "not valid JSON" in bad.stderr

    missing = _gx("pipeline", "label", str(corpus), cwd=work)
    assert missing.returncode != 0
    assert "--labels" in missing.stderr

    empty = _gx("pipeline", "label", str(corpus), "--labels", "{}", cwd=work)
    assert empty.returncode != 0
    assert "non-empty" in empty.stderr


def test_label_applies_community_names_and_saves_them(corpus: Path, tmp_path: Path) -> None:
    work = tmp_path / "work"
    work.mkdir()
    for step in ("detect", "extract-ast", "empty-semantic", "merge-extraction", "build"):
        args = ["pipeline", step, str(corpus)] if step in ("detect", "extract-ast", "build") else ["pipeline", step]
        assert _gx(*args, cwd=work).returncode == 0

    analysis = json.loads(
        (work / "graphify-out" / ".graphify_analysis.json").read_text(encoding="utf-8")
    )
    cid = next(iter(analysis["communities"]))

    p = _gx("pipeline", "label", str(corpus), "--labels", json.dumps({cid: "Core Widgets"}), cwd=work)
    assert p.returncode == 0, p.stderr

    saved = json.loads((work / "graphify-out" / ".graphify_labels.json").read_text(encoding="utf-8"))
    assert saved[cid] == "Core Widgets"
    graph = json.loads((work / "graphify-out" / "graph.json").read_text(encoding="utf-8"))
    assert any(n.get("community_name") == "Core Widgets" for n in graph["nodes"])


def test_merge_chunks_validates_untrusted_subagent_output(tmp_path: Path) -> None:
    """Chunk files are untrusted subagent output: a bad one is skipped, not merged."""
    work = tmp_path / "work"
    out = work / "graphify-out"
    out.mkdir(parents=True)

    def _chunk(nid: str) -> None:
        (out / f".graphify_chunk_{nid}.json").write_text(
            json.dumps({
                "nodes": [{"id": f"n::{nid}", "label": nid, "file_type": "concept"}],
                "edges": [],
                "input_tokens": 1,
                "output_tokens": 2,
            }),
            encoding="utf-8",
        )

    (out / ".graphify_chunk_bad.json").write_text("{not json", encoding="utf-8")
    _chunk("00")
    _chunk("01")

    p = _gx("pipeline", "merge-chunks", cwd=work)
    assert p.returncode == 0, p.stderr
    merged = json.loads((out / ".graphify_semantic_new.json").read_text(encoding="utf-8"))
    assert {n["id"] for n in merged["nodes"]} == {"n::00", "n::01"}
    assert merged["input_tokens"] == 2 and merged["output_tokens"] == 4


def test_merge_chunks_refuses_when_every_chunk_is_invalid(tmp_path: Path) -> None:
    """All-invalid must not replace the semantic layer with an empty one."""
    work = tmp_path / "work"
    out = work / "graphify-out"
    out.mkdir(parents=True)
    (out / ".graphify_chunk_bad.json").write_text("{not json", encoding="utf-8")

    p = _gx("pipeline", "merge-chunks", cwd=work)
    assert p.returncode != 0
    assert "no valid chunks" in p.stderr
    assert not (out / ".graphify_semantic_new.json").exists()


def test_merge_chunks_without_any_chunks_writes_an_empty_sidecar(tmp_path: Path) -> None:
    """The all-cached path reaches B3 with zero chunks and must still write the
    semantic sidecar Part C reads unconditionally (#1392)."""
    work = tmp_path / "work"
    out = work / "graphify-out"
    out.mkdir(parents=True)
    p = _gx("pipeline", "merge-chunks", cwd=work)
    assert p.returncode == 0, p.stderr
    merged = json.loads((out / ".graphify_semantic_new.json").read_text(encoding="utf-8"))
    assert merged["nodes"] == [] and merged["edges"] == []


def test_cleanup_removes_sidecars_but_keeps_durable_outputs(corpus: Path, tmp_path: Path) -> None:
    work = tmp_path / "work"
    work.mkdir()
    for step in ("detect", "extract-ast", "empty-semantic", "merge-extraction", "build", "save-manifest"):
        args = ["pipeline", step, str(corpus)] if step in ("detect", "extract-ast", "build", "save-manifest") else ["pipeline", step]
        assert _gx(*args, cwd=work).returncode == 0, step

    out = work / "graphify-out"
    assert (out / "manifest.json").exists()

    p = _gx("pipeline", "cleanup", cwd=work)
    assert p.returncode == 0, p.stderr
    for gone in (
        ".graphify_detect.json", ".graphify_ast.json", ".graphify_semantic.json",
        ".graphify_extract.json", ".graphify_analysis.json",
    ):
        assert not (out / gone).exists(), f"{gone} should be cleaned up"
    for kept in ("graph.json", "GRAPH_REPORT.md", "manifest.json", "cost.json"):
        assert (out / kept).exists(), f"{kept} is a durable output and must survive"


def test_save_manifest_updates_the_cumulative_cost_tracker(corpus: Path, tmp_path: Path) -> None:
    """cost.json accumulates across runs, so run twice and check the totals."""
    work = tmp_path / "work"
    work.mkdir()
    for run in range(2):
        for step in ("detect", "extract-ast", "empty-semantic", "merge-extraction", "build", "save-manifest"):
            args = ["pipeline", step, str(corpus)] if step in ("detect", "extract-ast", "build", "save-manifest") else ["pipeline", step]
            assert _gx(*args, cwd=work).returncode == 0, f"run {run} step {step}"

    cost = json.loads((work / "graphify-out" / "cost.json").read_text(encoding="utf-8"))
    assert len(cost["runs"]) == 2
    assert "All time:" in _gx("pipeline", "save-manifest", str(corpus), cwd=work).stdout


def test_diagnose_reports_health_and_never_aborts(corpus: Path, tmp_path: Path) -> None:
    """Read-only gate: it must always exit 0 so the pipeline continues."""
    work = tmp_path / "work"
    work.mkdir()
    for step in ("detect", "extract-ast", "empty-semantic", "merge-extraction"):
        args = ["pipeline", step, str(corpus)] if step in ("detect", "extract-ast") else ["pipeline", step]
        assert _gx(*args, cwd=work).returncode == 0

    p = _gx("pipeline", "diagnose", str(corpus), cwd=work)
    assert p.returncode == 0, p.stderr
    assert "Graph health" in p.stdout


def test_cache_check_splits_content_files_only(corpus: Path, tmp_path: Path) -> None:
    """Only docs/papers/images are checked; code is the AST pass's job (#1392)."""
    work = tmp_path / "work"
    work.mkdir()
    assert _gx("pipeline", "detect", str(corpus), cwd=work).returncode == 0

    p = _gx("pipeline", "cache-check", str(corpus), cwd=work)
    assert p.returncode == 0, p.stderr

    uncached = (work / "graphify-out" / ".graphify_uncached.txt").read_text(encoding="utf-8")
    listed = [ln for ln in uncached.splitlines() if ln]
    assert len(listed) == 1, f"only the .md should be uncached, got {listed}"
    assert listed[0].endswith("notes.md")
    assert not any(ln.endswith("mod.py") for ln in listed), "code must not be re-extracted"
    assert "1 files hit" not in p.stdout  # nothing cached yet


def test_detect_does_not_nest_a_second_graphify_out(corpus: Path, tmp_path: Path) -> None:
    """cache_root is the dir CONTAINING graphify-out; passing graphify-out itself
    nested a second one (F1, detect.py:2065)."""
    work = tmp_path / "work"
    work.mkdir()
    p = _gx("pipeline", "detect", str(corpus), cwd=work)
    assert p.returncode == 0, p.stderr
    assert (work / "graphify-out" / ".graphify_detect.json").exists()
    assert not (work / "graphify-out" / "graphify-out").exists(), (
        "detect must not nest graphify-out inside graphify-out"
    )


def test_detect_honors_no_gitignore(corpus: Path, tmp_path: Path) -> None:
    """`--no-gitignore` is the CLI's conventional spelling and must not be dropped."""
    (corpus / ".gitignore").write_text("ignored.py\n", encoding="utf-8")
    (corpus / "ignored.py").write_text("x = 1\n", encoding="utf-8")

    gated = tmp_path / "gated"
    gated.mkdir()
    assert _gx("pipeline", "detect", str(corpus), cwd=gated).returncode == 0
    n_gated = json.loads(
        (gated / "graphify-out" / ".graphify_detect.json").read_text(encoding="utf-8")
    )["total_files"]

    opened = tmp_path / "opened"
    opened.mkdir()
    assert _gx("pipeline", "detect", str(corpus), "--no-gitignore", cwd=opened).returncode == 0
    n_open = json.loads(
        (opened / "graphify-out" / ".graphify_detect.json").read_text(encoding="utf-8")
    )["total_files"]

    assert n_open > n_gated, (
        f"--no-gitignore must include the git-ignored file ({n_gated} vs {n_open})"
    )


def _run_small_build(work: Path, corpus: Path) -> None:
    for step in ("detect", "extract-ast", "empty-semantic", "merge-extraction", "build"):
        args = ["pipeline", step, str(corpus)] if step in ("detect", "extract-ast", "build") else ["pipeline", step]
        assert _gx(*args, cwd=work).returncode == 0, step


def test_force_overrides_the_shrink_guard(corpus: Path, tmp_path: Path) -> None:
    """The #479 refusal tells the user to re-run with --force; --force must work."""
    work = tmp_path / "work"
    work.mkdir()
    _run_small_build(work, corpus)
    out = work / "graphify-out"
    graph_path = out / "graph.json"
    before = json.loads(graph_path.read_text(encoding="utf-8"))

    # Simulate a larger existing graph so the same extraction now looks like a shrink.
    padded = dict(before)
    padded["nodes"] = list(before["nodes"]) + [
        {"id": f"pad{i}", "label": f"pad{i}", "file_type": "code"} for i in range(50)
    ]
    graph_path.write_text(json.dumps(padded), encoding="utf-8")

    refused = _gx("pipeline", "build", str(corpus), cwd=work)
    assert refused.returncode != 0, "the shrink guard must refuse without --force"
    assert "refused to shrink" in refused.stderr
    assert len(json.loads(graph_path.read_text(encoding="utf-8"))["nodes"]) == len(
        padded["nodes"]
    ), "a refused build must leave the existing graph.json untouched"

    forced = _gx("pipeline", "build", str(corpus), "--force", cwd=work)
    assert forced.returncode == 0, forced.stderr
    assert len(json.loads(graph_path.read_text(encoding="utf-8"))["nodes"]) == len(
        before["nodes"]
    ), "--force must actually replace the larger graph"


def test_label_rejects_non_numeric_community_keys(corpus: Path, tmp_path: Path) -> None:
    """A non-integer key must be a clean error, not a traceback (step_label int()s it)."""
    work = tmp_path / "work"
    work.mkdir()
    _run_small_build(work, corpus)
    p = _gx("pipeline", "label", str(corpus),
            "--labels", '{"community_0": "X"}', cwd=work)
    assert p.returncode != 0
    assert "community ids" in p.stderr
    assert "Traceback" not in p.stderr


def test_vocab_extracts_tokens_from_labels(corpus: Path, tmp_path: Path) -> None:
    """The query reference expands a question only with tokens from this file."""
    work = tmp_path / "work"
    work.mkdir()
    _run_small_build(work, corpus)
    p = _gx("pipeline", "vocab", cwd=work)
    assert p.returncode == 0, p.stderr
    vocab = (work / "graphify-out" / ".vocab.txt").read_text(encoding="utf-8").split()
    assert "helper" in vocab and "widget" in vocab, f"expected label tokens, got {vocab[:10]}"
    assert all(t == t.lower() for t in vocab)


def test_detect_incremental_writes_both_sidecars(corpus: Path, tmp_path: Path) -> None:
    """--update diffs against the manifest and populates the detect sidecar."""
    work = tmp_path / "work"
    work.mkdir()
    _run_small_build(work, corpus)
    assert _gx("pipeline", "save-manifest", str(corpus), cwd=work).returncode == 0

    (corpus / "pkg" / "mod.py").write_text(
        "def helper(x):\n    return x + 1\n\ndef second(y):\n    return y\n",
        encoding="utf-8",
    )
    p = _gx("pipeline", "detect-incremental", str(corpus), cwd=work)
    assert p.returncode == 0, p.stderr
    out = work / "graphify-out"
    inc = json.loads((out / ".graphify_incremental.json").read_text(encoding="utf-8"))
    detect = json.loads((out / ".graphify_detect.json").read_text(encoding="utf-8"))
    assert inc.get("new_total", 0) >= 1
    assert detect["needs_graph"] is True
    assert any(f.endswith("mod.py") for f in detect["files"].get("code", []))


def test_incremental_update_merges_a_new_symbol(corpus: Path, tmp_path: Path) -> None:
    """The full --update flow: detect-incremental -> extract-ast -> merge -> update-merge."""
    work = tmp_path / "work"
    work.mkdir()
    _run_small_build(work, corpus)
    assert _gx("pipeline", "save-manifest", str(corpus), cwd=work).returncode == 0

    # Add a function, keep the class: a pure addition so the merged graph does not
    # trip the #479 shrink guard (removing the class would be a legitimate shrink).
    (corpus / "pkg" / "mod.py").write_text(
        "def helper(x):\n    return x + 1\n\ndef second(y):\n    return y * 2\n"
        "\nclass Widget:\n    def render(self):\n        return helper(1)\n",
        encoding="utf-8",
    )
    assert _gx("pipeline", "detect-incremental", str(corpus), cwd=work).returncode == 0
    assert _gx("pipeline", "code-only-check", cwd=work).returncode == 0

    assert _gx("pipeline", "extract-ast", str(corpus), cwd=work).returncode == 0
    assert _gx("pipeline", "empty-semantic", cwd=work).returncode == 0
    assert _gx("pipeline", "merge-extraction", cwd=work).returncode == 0
    assert _gx("pipeline", "update-merge", str(corpus), cwd=work).returncode == 0
    # The reference then runs Steps 4-8 on the merged graph: `build` reads the
    # merged .graphify_extract.json and writes graph.json.
    assert _gx("pipeline", "build", str(corpus), cwd=work).returncode == 0

    graph = json.loads((work / "graphify-out" / "graph.json").read_text(encoding="utf-8"))
    labels = {n.get("label") for n in graph["nodes"]}
    assert "second()" in labels, f"the new symbol must be merged in, got {sorted(labels)}"
    assert "helper()" in labels, "the unchanged symbol must survive the merge"


def test_code_only_check_true_for_a_code_only_change(tmp_path: Path) -> None:
    """A code-only corpus change needs no semantic extraction (no LLM)."""
    src = tmp_path / "src"
    (src / "pkg").mkdir(parents=True)
    (src / "pkg" / "mod.py").write_text("def a():\n    return 1\n", encoding="utf-8")
    work = tmp_path / "work"
    work.mkdir()
    for step in ("detect", "extract-ast", "empty-semantic", "merge-extraction", "build", "save-manifest"):
        args = ["pipeline", step, str(src)] if step in ("detect", "extract-ast", "build", "save-manifest") else ["pipeline", step]
        assert _gx(*args, cwd=work).returncode == 0, step

    (src / "pkg" / "mod.py").write_text("def a():\n    return 1\n\ndef b():\n    return 2\n", encoding="utf-8")
    assert _gx("pipeline", "detect-incremental", str(src), cwd=work).returncode == 0
    p = _gx("pipeline", "code-only-check", cwd=work)
    assert p.returncode == 0
    assert "code_only: True" in p.stdout, p.stdout


def test_empty_extract_only_when_missing(tmp_path: Path) -> None:
    work = tmp_path / "work"
    (work / "graphify-out").mkdir(parents=True)
    first = _gx("pipeline", "empty-extract", cwd=work)
    assert first.returncode == 0 and "Created" in first.stdout
    (work / "graphify-out" / ".graphify_extract.json").write_text('{"nodes": []}', encoding="utf-8")
    second = _gx("pipeline", "empty-extract", cwd=work)
    assert second.returncode == 0 and "already exists" in second.stdout


def test_graph_diff_reports_no_backup(corpus: Path, tmp_path: Path) -> None:
    work = tmp_path / "work"
    work.mkdir()
    _run_small_build(work, corpus)
    p = _gx("pipeline", "graph-diff", cwd=work)
    assert p.returncode == 0
    assert "No previous graph" in p.stdout


def test_graphify_out_env_relocates_sidecars(corpus: Path, tmp_path: Path) -> None:
    """The pipeline honors the GRAPHIFY_OUT override the rest of the CLI uses (#686)."""
    work = tmp_path / "work"
    work.mkdir()
    env = {**os.environ, "GRAPHIFY_OUT": "custom-out"}
    p = subprocess.run(
        [sys.executable, "-m", "graphify", "pipeline", "detect", str(corpus)],
        cwd=work, capture_output=True, text=True, encoding="utf-8", errors="replace", env=env,
    )
    assert p.returncode == 0, p.stderr
    assert (work / "custom-out" / ".graphify_detect.json").exists(), (
        "GRAPHIFY_OUT must relocate the sidecar tree"
    )
    assert not (work / "graphify-out").exists(), "the default dir must not also be written"


def test_out_option_relocates_sidecars(corpus: Path, tmp_path: Path) -> None:
    """`--out` separates the sidecar tree from the cwd the pipeline runs in."""
    work = tmp_path / "work"
    work.mkdir()
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()

    p = _gx("pipeline", "detect", str(corpus), "--out", str(elsewhere), cwd=work)
    assert p.returncode == 0, p.stderr
    assert (elsewhere / "graphify-out" / ".graphify_detect.json").exists()
    assert not (work / "graphify-out" / ".graphify_detect.json").exists()