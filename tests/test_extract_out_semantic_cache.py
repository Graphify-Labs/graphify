"""Two `graphify extract --out` runs must reuse the semantic cache (#4831).

This is the reporter's scenario at the CLI boundary: a docs-only corpus, all
output under `--out`, no source changes between runs. What must hold:

  run 1: 3 docs dispatched, entries written under <out>/graphify-out/cache/semantic
  run 2: 0 docs dispatched (nothing spent), entries still there
  always: the scanned corpus grows no graphify-out/ directory
  always: every doc is stamped with semantic_hash in the manifest

Before 0.9.20 the save resolved the LLM's corpus-relative `source_file` against
`out_root`, so every entry was skipped (cache dir stayed empty) and no doc was
stamped, so run 2 re-dispatched all of them. This test fails on that behaviour.
"""

from __future__ import annotations

import json

import graphify.__main__ as mainmod


def _vault(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    for i in (1, 2, 3):
        (vault / f"n{i}.md").write_text(f"# Note {i}\nAlice uses Redis. See n{i}.\n")
    return vault


def test_second_extract_with_out_reuses_semantic_cache(monkeypatch, tmp_path):
    vault = _vault(tmp_path)
    out_dir = tmp_path / "out"
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-fake-key")

    dispatched: list[list[str]] = []

    def _stub(paths, **kwargs):
        sent = sorted(str(p) for p in paths)
        dispatched.append(sent)
        on_chunk = kwargs.get("on_chunk_done")
        if on_chunk:
            on_chunk(0, 1, {"nodes": [], "edges": [], "hyperedges": []})
        return {
            "nodes": [
                {"id": f"note-{i}", "source_file": f"n{i}.md", "file_type": "document"}
                for i in (1, 2, 3)
            ],
            "edges": [],
            "hyperedges": [],
            "input_tokens": 10,
            "output_tokens": 5,
        }

    monkeypatch.setattr("graphify.llm.extract_corpus_parallel", _stub)
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)

    def _run():
        monkeypatch.setattr(
            mainmod.sys,
            "argv",
            ["graphify", "extract", str(vault), "--backend", "claude",
             "--no-cluster", "--out", str(out_dir)],
        )
        try:
            mainmod.main()
        except SystemExit as exc:
            assert exc.code in (None, 0), f"unexpected exit code {exc.code}"

    _run()
    assert len(dispatched) == 1, f"run 1 must dispatch once, got {dispatched}"
    assert len(dispatched[0]) == 3, f"run 1 must dispatch 3 docs, got {dispatched[0]}"

    cache_dir = out_dir / "graphify-out" / "cache" / "semantic"
    entries = sorted(p.name for p in cache_dir.rglob("*.json")) if cache_dir.exists() else []
    assert len(entries) == 3, (
        f"run 1 must write 3 semantic cache entries under --out, found {entries} "
        f"in {cache_dir}"
    )
    assert not (vault / "graphify-out").exists(), (
        "the scanned corpus must stay clean when --out is set"
    )

    manifest = json.loads((out_dir / "graphify-out" / "manifest.json").read_text())
    for i in (1, 2, 3):
        assert manifest[f"n{i}.md"].get("semantic_hash"), (
            f"n{i}.md was extracted but never stamped in the manifest"
        )

    _run()
    assert len(dispatched) == 1, (
        "run 2 with no source change must dispatch nothing; it re-extracted "
        f"{len(dispatched) - 1} batch(es): {dispatched[1:]}"
    )


def test_cache_serves_docs_the_manifest_does_not_stamp(monkeypatch, tmp_path):
    """The reporter's compounded shape: cache written under --out, manifest not
    stamped.

    Run 2 must re-queue the docs (the manifest lost them) and serve them from
    the cache, so the backend is never called. A save that resolved
    corpus-relative paths against out_root writes nothing (dispatch 3, bill 3);
    a check that does the same misses every entry (dispatch 3, bill 3).
    """
    vault = _vault(tmp_path)
    out_dir = tmp_path / "out"
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-fake-key")
    dispatched: list[list[str]] = []

    def _stub(paths, **kwargs):
        sent = sorted(str(p) for p in paths)
        dispatched.append(sent)
        on_chunk = kwargs.get("on_chunk_done")
        if on_chunk:
            on_chunk(0, 1, {"nodes": [], "edges": [], "hyperedges": []})
        return {
            "nodes": [
                {"id": f"note-{i}", "source_file": f"n{i}.md", "file_type": "document"}
                for i in (1, 2, 3)
            ],
            "edges": [],
            "hyperedges": [],
            "input_tokens": 10,
            "output_tokens": 5,
        }

    monkeypatch.setattr("graphify.llm.extract_corpus_parallel", _stub)
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)

    def _run():
        monkeypatch.setattr(
            mainmod.sys, "argv",
            ["graphify", "extract", str(vault), "--backend", "claude",
             "--no-cluster", "--out", str(out_dir)],
        )
        try:
            mainmod.main()
        except SystemExit as exc:
            assert exc.code in (None, 0), f"unexpected exit code {exc.code}"

    _run()
    assert len(dispatched) == 1

    manifest_path = out_dir / "graphify-out" / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    for i in (1, 2, 3):
        manifest.pop(f"n{i}.md", None)   # the #1897 half: docs never stamped
    manifest_path.write_text(json.dumps(manifest))

    _run()
    assert len(dispatched) == 1, (
        "run 2 re-dispatched docs that the cache already holds: "
        f"{[len(b) for b in dispatched[1:]]} file(s) billed"
    )
