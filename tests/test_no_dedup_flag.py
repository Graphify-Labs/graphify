"""`graphify extract --no-dedup` (#2881).

The incremental merge path hardcoded `dedup=True`, so fuzzy dedup always ran
over the COMBINED node set (existing graph + new chunk). On a large graph a
small diff could therefore collapse pre-existing nodes belonging to files the
diff never touched, and the #479 shrink guard — the one thing that would have
caught it — is deliberately skipped while dedup is on, because fuzzy merging
shrinks the graph legitimately. There was no way to opt out from the CLI.
"""
from __future__ import annotations

import graphify.__main__ as mainmod


def _corpus(tmp_path):
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "main.go").write_text("package main\nfunc main() {}\n")
    return corpus


def _run(monkeypatch, argv):
    """Run the CLI and return its exit code (0 when main() simply returns)."""
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)
    monkeypatch.setattr(mainmod.sys, "argv", argv)
    try:
        mainmod.main()
    except SystemExit as exc:
        return exc.code or 0
    return 0


def _capture_dedup(monkeypatch):
    """Record the `dedup` kwarg both build entry points are called with.

    Patching `graphify.build` does reach the CLI's `_build` / `_build_merge`
    aliases, even though it refers to them by those names: the

        from graphify.build import build as _build, build_merge as _build_merge

    is function-local to `dispatch_command`, so the alias is bound when the
    command runs, which is after this patch is installed. A module-level import
    would bind at import time and make the patch inert — `_assert_spied` below
    turns that into a loud failure rather than a test that quietly asserts
    nothing.
    """
    import graphify.build as buildmod

    seen: dict[str, bool] = {}
    real_build = buildmod.build
    real_merge = buildmod.build_merge

    def fake_build(chunks, *a, **kw):
        seen["build"] = kw.get("dedup", True)
        return real_build(chunks, *a, **kw)

    def fake_merge(chunks, *a, **kw):
        seen["build_merge"] = kw.get("dedup", True)
        return real_merge(chunks, *a, **kw)

    monkeypatch.setattr(buildmod, "build", fake_build)
    monkeypatch.setattr(buildmod, "build_merge", fake_merge)
    return seen


def _assert_spied(seen: dict, entry_point: str) -> None:
    """Fail loudly if the spy never fired, so no assertion is vacuous."""
    assert entry_point in seen, (
        f"{entry_point}() was never called through the patched "
        f"graphify.build symbol — the spy is inert and every dedup assertion "
        f"below it would be vacuous. Did the CLI's import of it move to module "
        f"scope, or did this run take a path that skips the build stage?"
    )


def test_no_dedup_flag_disables_dedup(monkeypatch, tmp_path):
    corpus = _corpus(tmp_path)
    seen = _capture_dedup(monkeypatch)
    code = _run(monkeypatch, [
        "graphify", "extract", str(corpus), "--code-only",
        "--no-dedup", "--out", str(tmp_path / "out"),
    ])
    assert code == 0
    _assert_spied(seen, "build")
    assert seen["build"] is False


def test_dedup_is_on_by_default(monkeypatch, tmp_path):
    corpus = _corpus(tmp_path)
    seen = _capture_dedup(monkeypatch)
    code = _run(monkeypatch, [
        "graphify", "extract", str(corpus), "--code-only",
        "--out", str(tmp_path / "out"),
    ])
    assert code == 0
    _assert_spied(seen, "build")
    assert seen["build"] is True


def test_no_dedup_reaches_the_incremental_merge(monkeypatch, tmp_path):
    corpus = _corpus(tmp_path)
    out = tmp_path / "out"
    # First run establishes graph.json, so the second run takes the
    # build_merge (incremental) path rather than build().
    assert _run(monkeypatch, [
        "graphify", "extract", str(corpus), "--code-only",
        "--out", str(out),
    ]) == 0

    (corpus / "other.go").write_text("package main\nfunc other() {}\n")
    seen = _capture_dedup(monkeypatch)
    assert _run(monkeypatch, [
        "graphify", "extract", str(corpus), "--code-only",
        "--no-dedup", "--out", str(out),
    ]) == 0
    _assert_spied(seen, "build_merge")
    assert seen["build_merge"] is False, (
        "the incremental path hardcoded dedup=True, which is the bug"
    )


def test_no_dedup_conflicts_with_dedup_llm(monkeypatch, tmp_path, capsys):
    corpus = _corpus(tmp_path)
    code = _run(monkeypatch, [
        "graphify", "extract", str(corpus), "--code-only",
        "--no-dedup", "--dedup-llm", "--out", str(tmp_path / "out"),
    ])
    assert code == 2
    assert "mutually exclusive" in capsys.readouterr().err


# ── graph-level behaviour (the invariant that makes --no-dedup safe) ─────────
# The CLI tests above only prove the dedup=False kwarg reaches build/build_merge.
# These prove what that kwarg actually does to the graph: fuzzy near-duplicates
# are preserved, but exact-id collisions still collapse (a structural invariant
# of the graph, not a dedup responsibility), so the flag cannot corrupt it.

from graphify.build import build


def test_no_dedup_preserves_fuzzy_near_duplicates_but_dedup_merges_them():
    # "GraphExtractor" vs "Graph Extractor": a Jaro-Winkler >= 0.92 fuzzy pair
    # (distinct ids, non-code so the _is_code skip does not apply).
    extraction = {"nodes": [
        {"id": "graphextractor", "label": "GraphExtractor", "source_file": "a.md"},
        {"id": "graph_extractor", "label": "Graph Extractor", "source_file": "b.md"},
    ], "edges": [], "hyperedges": []}

    merged = build([extraction], dedup=True)
    assert merged.number_of_nodes() == 1, "dedup=True should fuzzy-merge the pair"

    kept = build([extraction], dedup=False)
    assert kept.number_of_nodes() == 2, "dedup=False must preserve both near-duplicates"


def test_no_dedup_still_collapses_exact_id_collisions():
    # Two extractions emit the SAME id. NetworkX add_node collapses them
    # regardless of dedup, so --no-dedup cannot produce duplicate-id corruption.
    ext_a = {"nodes": [{"id": "pkg.foo", "label": "foo()", "source_file": "x.go"}],
             "edges": [], "hyperedges": []}
    ext_b = {"nodes": [{"id": "pkg.foo", "label": "foo()", "source_file": "x.go"}],
             "edges": [], "hyperedges": []}
    G = build([ext_a, ext_b], dedup=False)
    assert [n for n in G.nodes] == ["pkg.foo"], "exact-id duplicates must still collapse to one node"
