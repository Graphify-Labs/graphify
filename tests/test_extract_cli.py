"""Tests for `graphify extract` CLI dispatch path in graphify.__main__."""
from __future__ import annotations

import os

import pytest

import graphify.__main__ as mainmod


def _make_corpus(tmp_path):
    """Minimal corpus: one Go code file + one Markdown doc.

    Both file types are needed so semantic extraction is requested
    (docs path triggers the LLM step we want to assert against).
    """
    (tmp_path / "main.go").write_text("package main\nfunc main() {}\n")
    (tmp_path / "README.md").write_text("# Notes\nThe main function entry point.\n")
    return tmp_path


def test_extract_exits_nonzero_when_all_semantic_chunks_fail(
    monkeypatch, tmp_path, capsys
):
    """When every semantic chunk errors (e.g. backend SDK not installed),
    the CLI must exit non-zero instead of silently writing an AST-only graph.

    The bug this guards: `pip install graphifyy` doesn't pull in `anthropic`,
    so `graphify extract --backend claude` would print per-chunk errors and
    still exit 0 with a graph.json. Callers checking exit status saw success.
    """
    corpus = _make_corpus(tmp_path)
    out_dir = tmp_path / "out"

    # Stub the API-key check so the backend gate doesn't reject before we
    # reach the semantic-extraction step.
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-fake-key")

    # Patch extract_corpus_parallel to simulate "all chunks failed":
    # return an empty merged accumulator without ever invoking on_chunk_done.
    # This matches the real behavior of extract_corpus_parallel when every
    # chunk raises (the per-chunk failures print to stderr and the loop
    # continues without calling the success callback).
    def _all_chunks_failed(paths, **kwargs):
        return {
            "nodes": [],
            "edges": [],
            "hyperedges": [],
            "input_tokens": 0,
            "output_tokens": 0,
        }

    monkeypatch.setattr(
        "graphify.llm.extract_corpus_parallel", _all_chunks_failed
    )
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)
    monkeypatch.setattr(
        mainmod.sys,
        "argv",
        ["graphify", "extract", str(corpus), "--backend", "claude",
         "--out", str(out_dir)],
    )

    with pytest.raises(SystemExit) as exc_info:
        mainmod.main()

    assert exc_info.value.code == 1, (
        f"expected exit code 1 when all semantic chunks fail, "
        f"got {exc_info.value.code}"
    )

    stderr = capsys.readouterr().err
    assert "all semantic chunks failed" in stderr
    assert "claude" in stderr

    # No graph.json should have been written - the failure must abort before
    # the merge/cluster/write phase, not after.
    assert not (out_dir / "graphify-out" / "graph.json").exists(), (
        "graph.json must not be written when semantic extraction fails"
    )


def test_extract_succeeds_when_at_least_one_chunk_completes(
    monkeypatch, tmp_path
):
    """Sanity counter-test: a successful chunk run keeps exit 0. Confirms the
    new guard only fires on the all-failed path, not on every extract."""
    corpus = _make_corpus(tmp_path)
    out_dir = tmp_path / "out"
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-fake-key")

    def _one_chunk_succeeded(paths, **kwargs):
        on_chunk = kwargs.get("on_chunk_done")
        if on_chunk:
            on_chunk(0, 1, {"nodes": [], "edges": [], "hyperedges": []})
        return {
            "nodes": [],
            "edges": [],
            "hyperedges": [],
            "input_tokens": 100,
            "output_tokens": 50,
        }

    monkeypatch.setattr(
        "graphify.llm.extract_corpus_parallel", _one_chunk_succeeded
    )
    cache_call = {}

    def _capture_semantic_cache(*args, **kwargs):
        cache_call.update(kwargs)
        return 0

    monkeypatch.setattr(
        "graphify.cache.save_semantic_cache", _capture_semantic_cache
    )
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)
    monkeypatch.setattr(
        mainmod.sys,
        "argv",
        ["graphify", "extract", str(corpus), "--backend", "claude",
         "--out", str(out_dir)],
    )

    # extract may still raise SystemExit at the end (clean exit code 0)
    # depending on platform; accept either no exception or SystemExit(0).
    try:
        mainmod.main()
    except SystemExit as exc:
        assert exc.code in (None, 0), f"unexpected exit code {exc.code}"

    # graph.json should exist on the happy path
    assert (out_dir / "graphify-out" / "graph.json").exists(), (
        "graph.json must be written on the happy path"
    )
    assert {
        str(path) for path in cache_call["allowed_source_files"]
    } == {str(corpus / "README.md")}


def test_incremental_partial_run_preserves_untouched_semantic_hash(
    monkeypatch, tmp_path
):
    """#1948 caller-side guard: an incremental run that only re-dispatches the
    CHANGED subset must not blank semantic_hash for live-but-untouched files.

    clear_semantic must be derived from what was actually SENT to the backend
    this run (semantic_files), not from the full live corpus (files_by_type):
    with the latter, every unchanged doc lands in the clear set on every
    incremental run, so the very next run re-extracts the whole corpus,
    forever."""
    import json

    corpus = _make_corpus(tmp_path)  # main.go + README.md
    (corpus / "OTHER.md").write_text("# Other\nAn independent second doc.\n")
    out_dir = tmp_path / "out"
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-fake-key")

    dispatched: list[list[str]] = []

    def _stamp_everything_sent(paths, **kwargs):
        sent = sorted(os.path.relpath(str(p), str(corpus)) for p in paths)
        dispatched.append(sent)
        on_chunk = kwargs.get("on_chunk_done")
        if on_chunk:
            on_chunk(0, 1, {"nodes": [], "edges": [], "hyperedges": []})
        return {
            "nodes": [{"id": f"n-{rel}", "source_file": rel,
                       "file_type": "document"} for rel in sent],
            "edges": [],
            "hyperedges": [],
            "input_tokens": 10,
            "output_tokens": 5,
        }

    monkeypatch.setattr(
        "graphify.llm.extract_corpus_parallel", _stamp_everything_sent
    )
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)

    def _run_extract():
        monkeypatch.setattr(
            mainmod.sys, "argv",
            ["graphify", "extract", str(corpus), "--backend", "claude",
             "--no-cluster", "--out", str(out_dir)],
        )
        try:
            mainmod.main()
        except SystemExit as exc:
            assert exc.code in (None, 0), f"unexpected exit code {exc.code}"

    # Run 1: full scan — both docs dispatched and stamped.
    _run_extract()
    manifest_path = out_dir / "graphify-out" / "manifest.json"
    m1 = json.loads(manifest_path.read_text())
    assert m1["README.md"].get("semantic_hash")
    assert m1["OTHER.md"].get("semantic_hash")

    # Run 2: only README.md changes → the incremental gate dispatches it alone.
    (corpus / "README.md").write_text("# Notes\nChanged content, new hash.\n")
    _run_extract()
    assert dispatched[-1] == ["README.md"], (
        f"run 2 should dispatch only the changed doc, got {dispatched[-1]}"
    )
    m2 = json.loads(manifest_path.read_text())
    assert m2["README.md"].get("semantic_hash")
    # The heart of the guard: an untouched, never-dispatched live doc keeps
    # its stamp across a partial incremental run.
    assert m2["OTHER.md"].get("semantic_hash"), (
        "untouched doc's semantic_hash was blanked by a partial incremental "
        "run — clear_semantic was derived from the full live corpus instead "
        "of the dispatched subset (#1948)"
    )


def test_manifest_stamps_freshly_extracted_semantic_docs(monkeypatch, tmp_path):
    """#1897: fresh extraction returns nodes with ROOT-RELATIVE source_file,
    while the #933 manifest filter compared them against detect()'s ABSOLUTE
    paths — so `f in _sem_extracted` was always False and every freshly
    extracted doc was dropped from the manifest (only code/zero-node files
    survived). Both sides must be resolved against the scan root; a genuinely
    omitted doc (zero nodes) must still stay unstamped (#933 is intentional)."""
    import json

    corpus = _make_corpus(tmp_path)  # main.go + README.md
    (corpus / "OMITTED.md").write_text("# never extracted\n")
    out_dir = tmp_path / "out"
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-fake-key")

    def _fresh_relative(paths, **kwargs):
        on_chunk = kwargs.get("on_chunk_done")
        if on_chunk:
            on_chunk(0, 1, {"nodes": [], "edges": [], "hyperedges": []})
        # Root-relative source_file, exactly what a fresh extraction produces.
        # OMITTED.md gets no nodes/edges — the model skipped it.
        return {
            "nodes": [{"id": "readme", "source_file": "README.md",
                       "file_type": "document"}],
            "edges": [],
            "hyperedges": [],
            "input_tokens": 10,
            "output_tokens": 5,
        }

    monkeypatch.setattr("graphify.llm.extract_corpus_parallel", _fresh_relative)
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)
    monkeypatch.setattr(
        mainmod.sys, "argv",
        ["graphify", "extract", str(corpus), "--backend", "claude",
         "--no-cluster", "--out", str(out_dir)],
    )

    try:
        mainmod.main()
    except SystemExit as exc:
        assert exc.code in (None, 0), f"unexpected exit code {exc.code}"

    manifest_path = out_dir / "graphify-out" / "manifest.json"
    assert manifest_path.exists()
    manifest = json.loads(manifest_path.read_text())

    assert "README.md" in manifest, (
        f"freshly-extracted doc missing from manifest (#1897): {sorted(manifest)}"
    )
    assert manifest["README.md"].get("semantic_hash"), (
        "freshly-extracted doc must carry a non-empty semantic_hash"
    )
    # Code files are always stamped.
    assert manifest.get("main.go", {}).get("semantic_hash")
    # The zero-node doc stays unstamped so detect_incremental re-queues it (#933).
    assert "OMITTED.md" not in manifest, (
        "zero-node doc must not be stamped in the manifest"
    )


def test_stamped_manifest_files_normalizes_both_sides(tmp_path):
    """Unit test for the #1897 helper: relative (fresh) and absolute (cache-hit)
    source_file values must both match detect()'s absolute file lists; docs with
    no output are filtered; code files pass through untouched."""
    from graphify.cli import _stamped_manifest_files

    fresh_doc = tmp_path / "fresh.md"; fresh_doc.write_text("# fresh")
    cached_doc = tmp_path / "cached.md"; cached_doc.write_text("# cached")
    omitted_doc = tmp_path / "omitted.md"; omitted_doc.write_text("# omitted")
    code = tmp_path / "app.py"; code.write_text("x = 1")

    files_by_type = {
        "code": [str(code)],
        "document": [str(fresh_doc), str(cached_doc), str(omitted_doc)],
    }
    sem_result = {
        # fresh extraction: root-relative source_file
        "nodes": [{"id": "n1", "source_file": "fresh.md"}],
        # cache replay: absolute source_file (edge-only coverage counts too)
        "edges": [{"source": "a", "target": "b", "source_file": str(cached_doc)}],
    }

    out = _stamped_manifest_files(files_by_type, sem_result, tmp_path)
    assert out["code"] == [str(code)]
    assert out["document"] == [str(fresh_doc), str(cached_doc)]


def test_stamped_manifest_files_counts_hyperedge_only_docs(tmp_path):
    """#1920: a doc whose only chunk output is a hyperedge (3+ nodes sharing a
    concept) is valid output — the semantic cache persists it per source_file —
    so it must be stamped. Before the fix the stamping loop only inspected
    ``nodes``/``edges``, leaving such a doc unstamped and re-queued forever."""
    from graphify.cli import _stamped_manifest_files

    hyper_doc = tmp_path / "hyper.md"; hyper_doc.write_text("# hyper")
    omitted_doc = tmp_path / "omitted.md"; omitted_doc.write_text("# omitted")

    files_by_type = {"document": [str(hyper_doc), str(omitted_doc)]}
    sem_result = {
        "nodes": [],
        "edges": [],
        "hyperedges": [
            {"id": "h1", "label": "L", "nodes": ["a", "b", "c"],
             "relation": "participate_in", "source_file": "hyper.md"},
        ],
    }

    out = _stamped_manifest_files(files_by_type, sem_result, tmp_path)
    assert str(hyper_doc) in out["document"], (
        "a hyperedge-only doc must be stamped (#1920)"
    )
    # A doc with no output at all still stays unstamped (#933).
    assert str(omitted_doc) not in out["document"]


def test_manifest_stamps_hyperedge_only_docs(monkeypatch, tmp_path):
    """#1920 end-to-end: a fresh extraction whose only output for a doc is a
    hyperedge stamps that doc's semantic_hash, so it is not re-dispatched."""
    import json

    corpus = _make_corpus(tmp_path)  # main.go + README.md
    out_dir = tmp_path / "out"
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-fake-key")

    def _hyperedge_only(paths, **kwargs):
        on_chunk = kwargs.get("on_chunk_done")
        if on_chunk:
            on_chunk(0, 1, {"nodes": [], "edges": [], "hyperedges": []})
        return {
            "nodes": [],
            "edges": [],
            "hyperedges": [{"id": "h1", "label": "Shared", "nodes": ["a", "b", "c"],
                            "relation": "participate_in", "source_file": "README.md"}],
            "input_tokens": 10,
            "output_tokens": 5,
        }

    monkeypatch.setattr("graphify.llm.extract_corpus_parallel", _hyperedge_only)
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)
    monkeypatch.setattr(
        mainmod.sys, "argv",
        ["graphify", "extract", str(corpus), "--backend", "claude",
         "--no-cluster", "--out", str(out_dir)],
    )
    try:
        mainmod.main()
    except SystemExit as exc:
        assert exc.code in (None, 0), f"unexpected exit code {exc.code}"

    manifest = json.loads((out_dir / "graphify-out" / "manifest.json").read_text())
    assert manifest.get("README.md", {}).get("semantic_hash"), (
        f"hyperedge-only doc must be stamped (#1920): {sorted(manifest)}"
    )


# --- #1894: --force and deep-mode dispatch over a warm cache -----------------

def _recording_extractor(calls):
    """extract_corpus_parallel stand-in that records each dispatch."""
    def _extract(paths, **kwargs):
        calls.append({"paths": [str(p) for p in paths], "kwargs": kwargs})
        on_chunk = kwargs.get("on_chunk_done")
        if on_chunk:
            on_chunk(0, 1, {"nodes": [], "edges": [], "hyperedges": []})
        return {
            "nodes": [{"id": "readme", "source_file": "README.md",
                       "file_type": "document"}],
            "edges": [],
            "hyperedges": [],
            "input_tokens": 10,
            "output_tokens": 5,
        }
    return _extract


def _run_extract(monkeypatch, argv):
    monkeypatch.setattr(mainmod.sys, "argv", argv)
    try:
        mainmod.main()
    except SystemExit as exc:
        assert exc.code in (None, 0), f"unexpected exit code {exc.code}"


def test_extract_mode_deep_dispatches_over_warm_cache(monkeypatch, tmp_path):
    """#1894 repro: over a warm manifest + warm standard semantic cache,
    `extract --mode deep` was a silent no-op — the incremental gate dispatched
    zero files before the cache was ever consulted, and the cache key ignored
    mode anyway. Deep must re-dispatch on the first deep run (deep namespace
    cold) and be served from cache/semantic-deep/ on the second."""
    corpus = _make_corpus(tmp_path)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-fake-key")
    monkeypatch.delenv("GRAPHIFY_FORCE", raising=False)
    calls: list[dict] = []
    monkeypatch.setattr("graphify.llm.extract_corpus_parallel",
                        _recording_extractor(calls))
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)

    # No --out: the default layout (graphify-out/ beside the sources) keeps the
    # CLI-level cache write's root anchored at the corpus, so the stub's
    # root-relative source_file resolves (real runs also checkpoint per chunk
    # inside llm.extract_corpus_parallel, which this stub replaces).
    base = ["graphify", "extract", str(corpus), "--backend", "claude",
            "--no-cluster"]

    # Run 1: cold standard extraction — warms manifest + plain semantic cache.
    _run_extract(monkeypatch, base)
    assert len(calls) == 1

    # Sanity: a warm standard re-run dispatches nothing (expected behavior).
    _run_extract(monkeypatch, base)
    assert len(calls) == 1

    # The repro: warm tree + --mode deep MUST dispatch.
    _run_extract(monkeypatch, base + ["--mode", "deep"])
    assert len(calls) == 2, (
        "--mode deep over a warm cache must re-dispatch (#1894)"
    )
    assert calls[1]["paths"] == [str(corpus / "README.md")]
    assert calls[1]["kwargs"].get("deep_mode") is True

    # Second deep run: served from the (now warm) deep namespace, no dispatch.
    _run_extract(monkeypatch, base + ["--mode", "deep"])
    assert len(calls) == 2, (
        "second deep run must be served from cache/semantic-deep/"
    )
    # The deep entry landed in its own namespace, not cache/semantic/. Entries are
    # nested under a p{prompt-fingerprint}/ subdir (#1939), hence the recursive glob.
    assert any((corpus / "graphify-out" / "cache" / "semantic-deep").glob("**/*.json"))


def test_extract_force_flag_redispatches_and_stamps_manifest(monkeypatch, tmp_path):
    """extract accepts --force: a warm tree re-dispatches every semantic file
    (cache read skipped, incremental gate off) and the manifest is still
    stamped afterward (#1897-compatible full coverage)."""
    import json

    corpus = _make_corpus(tmp_path)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-fake-key")
    monkeypatch.delenv("GRAPHIFY_FORCE", raising=False)
    calls: list[dict] = []
    monkeypatch.setattr("graphify.llm.extract_corpus_parallel",
                        _recording_extractor(calls))
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)

    base = ["graphify", "extract", str(corpus), "--backend", "claude",
            "--no-cluster"]

    _run_extract(monkeypatch, base)
    assert len(calls) == 1
    _run_extract(monkeypatch, base)  # warm: no dispatch
    assert len(calls) == 1

    _run_extract(monkeypatch, base + ["--force"])
    assert len(calls) == 2, (
        "--force over a warm tree must re-dispatch every semantic file"
    )
    assert calls[1]["paths"] == [str(corpus / "README.md")]

    # The forced run still wrote the semantic cache and stamped the manifest.
    # Entries nest under a p{prompt-fingerprint}/ subdir (#1939).
    assert any((corpus / "graphify-out" / "cache" / "semantic").glob("**/*.json"))
    manifest = json.loads(
        (corpus / "graphify-out" / "manifest.json").read_text()
    )
    assert manifest.get("README.md", {}).get("semantic_hash"), (
        "forced re-dispatch must still stamp the manifest"
    )
    assert manifest.get("main.go", {}).get("semantic_hash")


def test_extract_graphify_force_env_redispatches(monkeypatch, tmp_path):
    """GRAPHIFY_FORCE=1 behaves like --force (env parity with `update`)."""
    corpus = _make_corpus(tmp_path)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-fake-key")
    monkeypatch.delenv("GRAPHIFY_FORCE", raising=False)
    calls: list[dict] = []
    monkeypatch.setattr("graphify.llm.extract_corpus_parallel",
                        _recording_extractor(calls))
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)

    base = ["graphify", "extract", str(corpus), "--backend", "claude",
            "--no-cluster"]

    _run_extract(monkeypatch, base)
    assert len(calls) == 1
    _run_extract(monkeypatch, base)  # warm: no dispatch
    assert len(calls) == 1

    monkeypatch.setenv("GRAPHIFY_FORCE", "1")
    _run_extract(monkeypatch, base)
    assert len(calls) == 2, "GRAPHIFY_FORCE=1 must force a re-dispatch"


def test_cache_check_mode_deep_reads_deep_namespace(monkeypatch, tmp_path, capsys):
    """cache-check --mode deep consults cache/semantic-deep/; without the flag
    it keeps reading cache/semantic/ (deep entries are invisible to it)."""
    from graphify.cache import save_semantic_cache

    doc = tmp_path / "doc.md"
    doc.write_text("# Doc\n")
    save_semantic_cache([{"id": "d", "source_file": "doc.md"}], [],
                        root=tmp_path, mode="deep")
    files_from = tmp_path / "files.txt"
    files_from.write_text(str(doc) + "\n")
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)

    _run_extract(monkeypatch, ["graphify", "cache-check", str(files_from),
                               "--root", str(tmp_path)])
    assert "Cache: 0 hit, 1 miss" in capsys.readouterr().out

    _run_extract(monkeypatch, ["graphify", "cache-check", str(files_from),
                               "--root", str(tmp_path), "--mode", "deep"])
    assert "Cache: 1 hit, 0 miss" in capsys.readouterr().out


def _code_only_corpus(tmp_path):
    """A corpus with only code — no docs/papers/images."""
    (tmp_path / "auth.py").write_text(
        "def login(user):\n    return validate(user)\n\n"
        "def validate(user):\n    return True\n"
    )
    return tmp_path


def _clear_backend_keys(monkeypatch):
    """Clear every env var that detect_backend() or _get_backend_api_key() reads."""
    for key in (
        "GEMINI_API_KEY", "GOOGLE_API_KEY", "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY", "DEEPSEEK_API_KEY", "MOONSHOT_API_KEY",
        # bedrock: presence of any of these is treated as a valid credential
        "AWS_PROFILE", "AWS_REGION", "AWS_DEFAULT_REGION", "AWS_ACCESS_KEY_ID",
        # ollama: a set OLLAMA_BASE_URL triggers backend detection
        "OLLAMA_BASE_URL",
    ):
        monkeypatch.delenv(key, raising=False)


def test_extract_codeonly_succeeds_without_api_key(monkeypatch, tmp_path):
    """A code-only corpus must run with no LLM API key.

    Regression: graphify extract validated a backend upfront and exited 1 with
    'no LLM API key found' even for a code-only corpus that never calls a model.
    The keyless AST path now runs to a written graph.json (#1122).
    """
    corpus = _code_only_corpus(tmp_path)
    out_dir = tmp_path / "out"
    _clear_backend_keys(monkeypatch)
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)
    monkeypatch.setattr(
        mainmod.sys, "argv",
        ["graphify", "extract", str(corpus), "--out", str(out_dir)],
    )

    try:
        mainmod.main()
    except SystemExit as exc:
        assert exc.code in (None, 0), f"unexpected exit code {exc.code}"

    graph = out_dir / "graphify-out" / "graph.json"
    assert graph.exists(), "code-only extract must write graph.json without a key"
    import json
    assert len(json.loads(graph.read_text()).get("nodes", [])) > 0


def test_missing_manifest_code_only_preserves_semantic_layer(monkeypatch, tmp_path):
    """#1925: `graphify extract --code-only` with a MISSING manifest.json must
    not degrade to a full scan that discards the committed semantic layer. An
    existing graph.json is a sufficient incremental baseline, so doc/paper/image
    nodes (excluded by --code-only, not deleted) are preserved; a genuinely
    deleted source is still evicted (#1909 semantics retained)."""
    import json

    corpus = tmp_path / "proj"; corpus.mkdir()
    (corpus / "keep.py").write_text("def keep():\n    return 1\n")
    (corpus / "README.md").write_text("# Notes\nCurated docs.\n")
    out_dir = tmp_path / "out"
    graphify_out = out_dir / "graphify-out"
    _clear_backend_keys(monkeypatch)
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)

    def _sem_doc_count(g):
        return sum(1 for n in g["nodes"] if n.get("source_file") == "README.md")

    # 1) seed a code-only graph
    _run_extract(monkeypatch, ["graphify", "extract", str(corpus),
                               "--code-only", "--out", str(out_dir)])
    graph_path = graphify_out / "graph.json"
    graph = json.loads(graph_path.read_text())

    # 2) inject a committed semantic layer for README.md (nodes + edge + hyperedge)
    graph["nodes"].append({"id": "doc_readme_a", "label": "Concept A",
                           "source_file": "README.md", "file_type": "document"})
    graph["nodes"].append({"id": "doc_readme_b", "label": "Concept B",
                           "source_file": "README.md", "file_type": "document"})
    graph.setdefault("edges", []).append(
        {"source": "doc_readme_a", "target": "doc_readme_b",
         "relation": "relates_to", "source_file": "README.md"})
    graph.setdefault("hyperedges", []).append(
        {"id": "h1", "label": "Shared", "nodes": ["doc_readme_a", "doc_readme_b"],
         "relation": "participate_in", "source_file": "README.md"})
    graph_path.write_text(json.dumps(graph))
    (graphify_out / ".graphify_semantic_marker").write_text(
        json.dumps({"output_tokens": 1}))

    # 3) manifest goes missing (fresh clone / deliberately untracked)
    (graphify_out / "manifest.json").unlink()

    # 4) re-run the SAME code-only extract
    _run_extract(monkeypatch, ["graphify", "extract", str(corpus),
                               "--code-only", "--out", str(out_dir)])
    after = json.loads(graph_path.read_text())
    assert _sem_doc_count(after) >= 2, (
        "committed semantic doc nodes must survive a missing-manifest "
        f"--code-only rebuild (#1925); got {_sem_doc_count(after)}"
    )
    assert any(h.get("id") == "h1" for h in after.get("hyperedges", [])), (
        "committed hyperedge must survive the rebuild"
    )
    assert any("keep" in n["id"] for n in after["nodes"]), "code nodes intact"

    # 5) a genuine deletion still evicts the doc's semantic nodes
    (corpus / "README.md").unlink()
    (graphify_out / "manifest.json").unlink(missing_ok=True)
    _run_extract(monkeypatch, ["graphify", "extract", str(corpus),
                               "--code-only", "--out", str(out_dir)])
    gone = json.loads(graph_path.read_text())
    assert _sem_doc_count(gone) == 0, (
        "a genuinely deleted doc must still be evicted (#1909 semantics preserved)"
    )


def test_extract_out_keeps_project_root_clean(monkeypatch, tmp_path):
    """`extract --out DIR` routes every artifact to DIR/graphify-out/ and the
    scanned project must not grow a graphify-out/ (or anything else) beside
    its sources.

    Guards the centralized-output workflow: run from the project root with
    --out pointing outside the repo, and the repo stays byte-identical.
    """
    project = tmp_path / "project"
    project.mkdir()
    corpus = _code_only_corpus(project)
    external = tmp_path / "external-graphs"

    _clear_backend_keys(monkeypatch)
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)
    monkeypatch.chdir(corpus)  # run from the project root, like a real user
    monkeypatch.setattr(
        mainmod.sys, "argv",
        ["graphify", "extract", ".", "--out", str(external)],
    )

    try:
        mainmod.main()
    except SystemExit as exc:
        assert exc.code in (None, 0), f"unexpected exit code {exc.code}"

    out = external / "graphify-out"
    assert (out / "graph.json").exists(), "graph.json must land under --out"
    assert (out / "manifest.json").exists(), "manifest.json must land under --out"
    assert not (corpus / "graphify-out").exists(), (
        "scanned project must not grow a graphify-out/ when --out is set"
    )
    assert sorted(p.name for p in corpus.iterdir()) == ["auth.py"], (
        "no stray files may appear in the project root"
    )


def test_extract_without_key_still_errors_when_docs_present(
    monkeypatch, tmp_path, capsys
):
    """Key requirement still fires when semantic work is needed.

    A corpus with a Markdown doc needs LLM semantic extraction, so a keyless
    extract must exit 1 with clear guidance (#1122).
    """
    corpus = _make_corpus(tmp_path)  # includes a Markdown doc
    out_dir = tmp_path / "out"
    _clear_backend_keys(monkeypatch)
    # Patch detect_backend too so ambient AWS/ollama env can't slip through.
    monkeypatch.setattr("graphify.llm.detect_backend", lambda: None)
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)
    monkeypatch.setattr(
        mainmod.sys, "argv",
        ["graphify", "extract", str(corpus), "--out", str(out_dir)],
    )

    with pytest.raises(SystemExit) as exc_info:
        mainmod.main()
    assert exc_info.value.code == 1
    err = capsys.readouterr().err
    assert "no LLM API key found" in err
    assert "code-only corpus needs no key" in err
    assert not (out_dir / "graphify-out" / "graph.json").exists()


def test_extract_timing_flag_emits_stage_timings(monkeypatch, tmp_path, capsys):
    """--timing prints per-stage `[graphify timing]` lines to stderr (#1490); omitting
    it prints none, so default output is unchanged. Code-only corpus => no API key."""
    code = tmp_path / "code"
    code.mkdir()
    (code / "a.py").write_text("def a():\n    return b()\ndef b():\n    return 1\n")

    # with --timing
    monkeypatch.setattr(
        mainmod.sys, "argv",
        ["graphify", "extract", str(code), "--no-cluster", "--out", str(tmp_path / "o1"), "--timing"],
    )
    with pytest.raises(SystemExit) as exc:
        mainmod.main()
    assert exc.value.code == 0
    err = capsys.readouterr().err
    assert "[graphify timing] detect:" in err
    assert "[graphify timing] total:" in err

    # without --timing => no timing lines
    monkeypatch.setattr(
        mainmod.sys, "argv",
        ["graphify", "extract", str(code), "--no-cluster", "--out", str(tmp_path / "o2")],
    )
    with pytest.raises(SystemExit) as exc2:
        mainmod.main()
    assert exc2.value.code == 0
    assert "graphify timing" not in capsys.readouterr().err


# ---------------------------------------------------------------------------
# #1909: a newly-excluded file's nodes must be pruned from graph.json on the
# next incremental extract even when the manifest never listed the file (the
# pre-#1897 state every 0.9.16 graph is in), so the manifest-diff prune set
# (`manifest - corpus`) can never see it.
# ---------------------------------------------------------------------------

def _two_file_corpus(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    (project / "x.py").write_text(
        "def secret_helper():\n    return 42\n\n"
        "def secret_caller():\n    return secret_helper()\n"
    )
    (project / "keep.py").write_text(
        "def kept():\n    return still_here()\n\n"
        "def still_here():\n    return 1\n"
    )
    return project


def _node_sources(graph_path):
    import json
    data = json.loads(graph_path.read_text(encoding="utf-8"))
    return {n.get("source_file", "") for n in data.get("nodes", [])}


def _run_extract(monkeypatch, argv):
    monkeypatch.setattr(mainmod.sys, "argv", argv)
    try:
        mainmod.main()
    except SystemExit as exc:
        assert exc.code in (None, 0), f"unexpected exit code {exc.code}"


def test_incremental_extract_prunes_newly_excluded_file_not_in_manifest(
    monkeypatch, tmp_path
):
    """Seed a graph with nodes for x.py, drop x.py from the manifest (pre-#1897
    manifests never listed excluded/omitted files), exclude x.py via
    .graphifyignore, re-run extract: x.py's nodes must be gone even though it
    was never on the deleted list."""
    import json
    project = _two_file_corpus(tmp_path)
    out_dir = tmp_path / "out"
    _clear_backend_keys(monkeypatch)
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)

    _run_extract(
        monkeypatch,
        ["graphify", "extract", str(project), "--out", str(out_dir)],
    )
    graph_path = out_dir / "graphify-out" / "graph.json"
    manifest_path = out_dir / "graphify-out" / "manifest.json"
    assert any("x.py" in s for s in _node_sources(graph_path)), (
        "seed extract must produce nodes for x.py"
    )

    # Simulate the pre-#1897 manifest state: x.py was never manifest-listed,
    # so `manifest - corpus` can never flag it.
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest = {k: v for k, v in manifest.items() if "x.py" not in k}
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    (project / ".graphifyignore").write_text("x.py\n")
    _run_extract(
        monkeypatch,
        ["graphify", "extract", str(project), "--out", str(out_dir)],
    )

    sources = _node_sources(graph_path)
    assert not any("x.py" in s for s in sources), (
        f"newly-excluded x.py must be pruned from graph.json, still see {sources}"
    )
    assert any("keep.py" in s for s in sources), (
        "unchanged keep.py nodes must survive the incremental merge"
    )
    # x.py exists on disk, is excluded, and must not creep into the manifest.
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert not any("x.py" in k for k in manifest), (
        f"excluded x.py must not be (re)listed in the manifest: {set(manifest)}"
    )


def test_incremental_extract_prunes_excluded_file_listed_in_manifest(
    monkeypatch, tmp_path
):
    """Post-#1897 state: the excluded file IS manifest-listed. It must be
    pruned from graph.json AND dropped from the manifest (#1908), and stay
    settled on a further run."""
    import json
    project = _two_file_corpus(tmp_path)
    out_dir = tmp_path / "out"
    _clear_backend_keys(monkeypatch)
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)

    _run_extract(
        monkeypatch,
        ["graphify", "extract", str(project), "--out", str(out_dir)],
    )
    graph_path = out_dir / "graphify-out" / "graph.json"
    manifest_path = out_dir / "graphify-out" / "manifest.json"
    assert any("x.py" in k for k in json.loads(manifest_path.read_text()))

    (project / ".graphifyignore").write_text("x.py\n")
    _run_extract(
        monkeypatch,
        ["graphify", "extract", str(project), "--out", str(out_dir)],
    )

    sources = _node_sources(graph_path)
    assert not any("x.py" in s for s in sources)
    assert any("keep.py" in s for s in sources)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert not any("x.py" in k for k in manifest), (
        "excluded-but-alive manifest row must be pruned (#1908)"
    )

    # Steady state: a third run neither resurrects x.py nor loses keep.py.
    _run_extract(
        monkeypatch,
        ["graphify", "extract", str(project), "--out", str(out_dir)],
    )
    sources = _node_sources(graph_path)
    assert not any("x.py" in s for s in sources)
    assert any("keep.py" in s for s in sources)


def test_no_cluster_incremental_prunes_newly_excluded_file(
    monkeypatch, tmp_path, capsys
):
    """--no-cluster's exclusion-only early exit must still scrub the excluded
    file's nodes from the raw graph.json (that path never runs build_merge),
    and must not report the alive file as deleted."""
    import json
    project = _two_file_corpus(tmp_path)
    out_dir = tmp_path / "out"
    _clear_backend_keys(monkeypatch)
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)

    monkeypatch.setattr(
        mainmod.sys, "argv",
        ["graphify", "extract", str(project), "--no-cluster", "--out", str(out_dir)],
    )
    with pytest.raises(SystemExit) as exc:
        mainmod.main()
    assert exc.value.code == 0
    graph_path = out_dir / "graphify-out" / "graph.json"
    assert any("x.py" in s for s in _node_sources(graph_path))
    capsys.readouterr()

    (project / ".graphifyignore").write_text("x.py\n")
    with pytest.raises(SystemExit) as exc:
        mainmod.main()
    assert exc.value.code == 0
    out_text = capsys.readouterr().out
    assert "1 deleted" not in out_text, (
        "excluded-but-alive file must not be reported as deleted"
    )

    sources = _node_sources(graph_path)
    assert not any("x.py" in s for s in sources), (
        f"--no-cluster early exit must prune excluded sources, still see {sources}"
    )
    assert any("keep.py" in s for s in sources)


def test_cache_check_prompt_file_scopes_hits_to_that_prompt(monkeypatch, tmp_path, capsys):
    """#1939: cache-check --prompt-file only counts entries produced by that same
    extraction prompt, so an upgraded prompt reports a miss (re-extract) rather
    than replaying the older vintage."""
    from graphify.cache import save_semantic_cache

    doc = tmp_path / "doc.md"
    doc.write_text("# Doc\n")
    spec = tmp_path / "extraction-spec.md"
    spec.write_text("PROMPT V1", encoding="utf-8")
    save_semantic_cache([{"id": "d", "source_file": "doc.md"}], [],
                        root=tmp_path, prompt_file=str(spec))
    files_from = tmp_path / "files.txt"
    files_from.write_text(str(doc) + "\n")
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)

    base = ["graphify", "cache-check", str(files_from), "--root", str(tmp_path)]
    _run_extract(monkeypatch, base + ["--prompt-file", str(spec)])
    assert "Cache: 1 hit, 0 miss" in capsys.readouterr().out

    # An upgrade rewrites the prompt: the entry must no longer satisfy the run.
    spec.write_text("PROMPT V2 — rewritten by an upgrade", encoding="utf-8")
    os.utime(spec, ns=(0, 0))
    _run_extract(monkeypatch, base + ["--prompt-file", str(spec)])
    assert "Cache: 0 hit, 1 miss" in capsys.readouterr().out
