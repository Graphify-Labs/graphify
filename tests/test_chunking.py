"""Tests for token-aware chunking and parallel chunk execution in graphify.llm."""
import time
from pathlib import Path
from unittest.mock import patch

import pytest


@pytest.fixture(autouse=False)
def no_tokenizer():
    """Force the chars/4 fallback so packing math is deterministic regardless
    of whether tiktoken is installed in the test environment. tiktoken's BPE
    compresses repeated/synthetic content heavily, which would make pack-size
    assertions tied to specific input sizes flaky."""
    from graphify import llm
    with patch.object(llm, "_TOKENIZER", None):
        yield


# ---- Token-aware packing -----------------------------------------------------

def test_pack_chunks_packs_small_files_together(tmp_path):
    """Many small files should land in a single chunk, not one chunk per file."""
    from graphify.llm import _pack_chunks_by_tokens

    files = []
    for i in range(20):
        f = tmp_path / f"small_{i}.py"
        f.write_text("x = 1\n")  # ~6 bytes => ~1 token
        files.append(f)

    chunks = _pack_chunks_by_tokens(files, token_budget=10_000)
    assert len(chunks) == 1
    assert sorted(chunks[0]) == sorted(files)


def test_pack_chunks_starts_new_chunk_when_budget_would_overflow(tmp_path, no_tokenizer):
    """When the next file would push the chunk past the budget, start a new chunk.

    With chars/4 fallback: each 10,000-char file = (10000+80)/4 = 2520 tokens.
    Budget 6000 fits two (5040 < 6000) but not three (7560 > 6000).
    Five files → 2/2/1 = three chunks.
    """
    from graphify.llm import _pack_chunks_by_tokens

    files = []
    for i in range(5):
        f = tmp_path / f"file_{i}.py"
        f.write_text("x" * 10_000)
        files.append(f)

    chunks = _pack_chunks_by_tokens(files, token_budget=6_000)
    sizes = [len(c) for c in chunks]
    assert sizes == [2, 2, 1], f"expected [2, 2, 1], got {sizes}"
    assert sum(sizes) == 5  # all files accounted for


def test_pack_chunks_groups_by_directory(tmp_path):
    """Files in the same directory should land in the same chunk when they fit."""
    from graphify.llm import _pack_chunks_by_tokens

    dir_a = tmp_path / "a"
    dir_b = tmp_path / "b"
    dir_a.mkdir()
    dir_b.mkdir()

    a1 = dir_a / "x.py"; a1.write_text("a")
    a2 = dir_a / "y.py"; a2.write_text("a")
    b1 = dir_b / "x.py"; b1.write_text("b")
    b2 = dir_b / "y.py"; b2.write_text("b")

    # Big budget — everything fits in one chunk in principle, but the order
    # within the chunk should keep dir_a's files contiguous and dir_b's
    # contiguous (not interleaved).
    chunks = _pack_chunks_by_tokens([a1, b1, a2, b2], token_budget=1_000_000)
    assert len(chunks) == 1
    chunk = chunks[0]
    a_indices = [i for i, p in enumerate(chunk) if p.parent == dir_a]
    b_indices = [i for i, p in enumerate(chunk) if p.parent == dir_b]
    assert a_indices == sorted(a_indices)
    assert b_indices == sorted(b_indices)
    # all of one directory comes before all of the other
    assert max(a_indices) < min(b_indices) or max(b_indices) < min(a_indices)


def test_pack_chunks_oversized_file_gets_its_own_chunk(tmp_path, no_tokenizer):
    """A file larger than the budget can't be split — it goes alone in a chunk."""
    from graphify.llm import _pack_chunks_by_tokens

    big = tmp_path / "big.py"; big.write_text("x" * 200_000)  # ~50k tokens (cap-bound)
    small = tmp_path / "small.py"; small.write_text("x")

    chunks = _pack_chunks_by_tokens([big, small], token_budget=1_000)
    sizes = [len(c) for c in chunks]
    # big should be alone in its own chunk; small in its own (no other file
    # to share with)
    assert sizes == [1, 1]


def test_pack_chunks_rejects_non_positive_budget(tmp_path):
    from graphify.llm import _pack_chunks_by_tokens

    f = tmp_path / "x.py"; f.write_text("a")
    with pytest.raises(ValueError):
        _pack_chunks_by_tokens([f], token_budget=0)


# ---- Tokenizer fallback ------------------------------------------------------

def test_estimate_file_tokens_uses_tiktoken_when_available(tmp_path):
    """When tiktoken is installed, the estimator should call into it for
    accurate counts rather than the chars/4 heuristic."""
    from graphify import llm

    f = tmp_path / "sample.py"
    text = "def hello():\n    return 'world'\n" * 50  # ~1500 chars
    f.write_text(text)

    # Force the tokenizer to be a mock that records calls and returns a known
    # token list, so we can assert the tiktoken path is taken.
    # Match tiktoken's real signature: encode(text, *, disallowed_special=...)
    # so the #1685 hardening call (disallowed_special=()) reaches the mock.
    fake_encoder = type("E", (), {"encode": staticmethod(lambda s, **kw: [0] * 999)})()
    with patch.object(llm, "_TOKENIZER", fake_encoder):
        n = llm._estimate_file_tokens(f)
    assert n == 999 + (llm._PER_FILE_OVERHEAD_CHARS // llm._CHARS_PER_TOKEN)


def test_estimate_file_tokens_falls_back_to_chars_when_no_tokenizer(tmp_path):
    """Without tiktoken installed, the estimator falls back to chars/4."""
    from graphify import llm

    f = tmp_path / "sample.py"
    f.write_text("x" * 1_000)  # 1000 bytes

    with patch.object(llm, "_TOKENIZER", None):
        n = llm._estimate_file_tokens(f)
    # 1000 chars + 80 overhead = 1080 / 4 = 270 tokens
    assert n == (1000 + llm._PER_FILE_OVERHEAD_CHARS) // llm._CHARS_PER_TOKEN


# ---- Parallel execution ------------------------------------------------------

def _stub_chunk_result(file_count: int, idx: int) -> dict:
    """Build a deterministic fake extraction result for a chunk."""
    return {
        "nodes": [{"id": f"chunk_{idx}_node_{i}"} for i in range(file_count)],
        "edges": [],
        "hyperedges": [],
        "input_tokens": 100 * file_count,
        "output_tokens": 50 * file_count,
    }


def test_corpus_parallel_runs_chunks_concurrently(tmp_path):
    """With max_concurrency > 1, total wall time should be ~max(chunk times),
    not the sum. Each stub extraction sleeps; we assert wall time."""
    from graphify.llm import extract_corpus_parallel

    files = []
    for i in range(8):
        f = tmp_path / f"f{i}.py"; f.write_text("x")
        files.append(f)

    def slow_extract(chunk, **kwargs):
        time.sleep(0.3)
        return _stub_chunk_result(len(chunk), 0)

    with patch("graphify.llm.extract_files_direct", side_effect=slow_extract):
        t0 = time.time()
        # Force 4 chunks of 2 files each by setting a tight token budget.
        result = extract_corpus_parallel(
            files, backend="kimi", token_budget=None, chunk_size=2, max_concurrency=4
        )
        elapsed = time.time() - t0

    # 4 chunks × 0.3s sequential = 1.2s. Parallel with 4 workers should land near 0.3-0.5s.
    assert elapsed < 1.0, f"expected parallel speedup, took {elapsed:.2f}s"
    assert len(result["nodes"]) == 8


def test_corpus_parallel_sequential_when_max_concurrency_is_one(tmp_path):
    """max_concurrency=1 should run sequentially (no thread pool)."""
    from graphify.llm import extract_corpus_parallel

    files = []
    for i in range(3):
        f = tmp_path / f"f{i}.py"; f.write_text("x")
        files.append(f)

    call_order = []

    def record(chunk, **kwargs):
        call_order.append(tuple(p.name for p in chunk))
        return _stub_chunk_result(len(chunk), len(call_order))

    with patch("graphify.llm.extract_files_direct", side_effect=record):
        extract_corpus_parallel(
            files, backend="kimi", token_budget=None, chunk_size=1, max_concurrency=1
        )

    # Sequential => we see calls in submission order
    assert call_order == [("f0.py",), ("f1.py",), ("f2.py",)]


def test_corpus_parallel_merge_order_is_submission_order_not_completion(tmp_path):
    """#1632: merged node/edge order must be deterministic (submission order),
    not the order chunks' network calls happen to finish. We skew latencies so
    the first-submitted chunk finishes LAST; the merged result must still be in
    file/submission order so graph.json is stable run-to-run."""
    from graphify.llm import extract_corpus_parallel

    files = []
    for i in range(4):
        f = tmp_path / f"f{i}.py"; f.write_text("x")
        files.append(f)

    def latency_skewed(chunk, **kwargs):
        # chunk is a single file (chunk_size=1). Earlier files sleep longer, so
        # completion order is the reverse of submission order.
        name = chunk[0].name  # f0.py .. f3.py
        idx = int(name[1])
        time.sleep(0.05 * (4 - idx))  # f0 sleeps 0.20s, f3 sleeps 0.05s
        return {
            "nodes": [{"id": f"node_from_{name}"}],
            "edges": [{"source": f"node_from_{name}", "target": "t"}],
            "hyperedges": [],
            "input_tokens": 1,
            "output_tokens": 1,
        }

    with patch("graphify.llm.extract_files_direct", side_effect=latency_skewed):
        result = extract_corpus_parallel(
            files, backend="kimi", token_budget=None, chunk_size=1, max_concurrency=4
        )

    node_ids = [n["id"] for n in result["nodes"]]
    assert node_ids == [
        "node_from_f0.py",
        "node_from_f1.py",
        "node_from_f2.py",
        "node_from_f3.py",
    ], f"merge order not deterministic: {node_ids}"
    edge_srcs = [e["source"] for e in result["edges"]]
    assert edge_srcs == [
        "node_from_f0.py",
        "node_from_f1.py",
        "node_from_f2.py",
        "node_from_f3.py",
    ], f"edge merge order not deterministic: {edge_srcs}"


def test_corpus_parallel_continues_after_chunk_failure(tmp_path, capsys):
    """A single chunk raising should be logged but not abort the run.
    Other chunks' results should still be merged."""
    from graphify.llm import extract_corpus_parallel

    files = []
    for i in range(4):
        f = tmp_path / f"f{i}.py"; f.write_text("x")
        files.append(f)

    call_count = {"n": 0}

    def maybe_fail(chunk, **kwargs):
        call_count["n"] += 1
        if call_count["n"] == 2:
            raise RuntimeError("simulated API error")
        return _stub_chunk_result(len(chunk), call_count["n"])

    with patch("graphify.llm.extract_files_direct", side_effect=maybe_fail):
        result = extract_corpus_parallel(
            files, backend="kimi", token_budget=None, chunk_size=1, max_concurrency=1
        )

    # 4 chunks dispatched, 1 failed → 3 chunks contributed nodes
    assert len(result["nodes"]) == 3
    err = capsys.readouterr().err
    assert "failed" in err and "simulated API error" in err


def test_checkpoint_scopes_cache_writes_to_chunk_files(tmp_path):
    """#1757: the per-chunk incremental checkpoint must not let a chunk's
    mis-attributed node clobber another corpus file's semantic cache. A chunk
    processing only A.py that returns a node attributed to B.py must leave B.py's
    existing cache entry untouched. Guards the call site the original fix missed."""
    from graphify.llm import extract_corpus_parallel
    from graphify.cache import save_semantic_cache, load_cached

    a = tmp_path / "A.py"; a.write_text("def a(): pass")
    b = tmp_path / "B.py"; b.write_text("def b(): pass")

    # Seed B.py's legitimate semantic cache (a full, correct entry).
    save_semantic_cache(
        [{"id": "b_real", "source_file": "B.py", "file_type": "code"}],
        [], [], root=tmp_path,
    )
    before = load_cached(b, tmp_path, kind="semantic")
    assert before and [n["id"] for n in before["nodes"]] == ["b_real"]

    # The chunk dispatches only A.py, but the (untrusted) model result attributes
    # a stray node to B.py — the #1757 mis-attribution.
    def stray(chunk, **kwargs):
        return {
            "nodes": [
                {"id": "a_ok", "source_file": "A.py", "file_type": "code"},
                {"id": "b_stray", "source_file": "B.py", "file_type": "code"},
            ],
            "edges": [], "hyperedges": [],
            "input_tokens": 1, "output_tokens": 1,
        }

    with patch("graphify.llm.extract_files_direct", side_effect=stray):
        extract_corpus_parallel(
            [a], backend="kimi", root=tmp_path,
            token_budget=None, chunk_size=1, max_concurrency=1,
        )

    # B.py's cache is unchanged: the stray node was rejected, not merged in.
    after = load_cached(b, tmp_path, kind="semantic")
    assert [n["id"] for n in after["nodes"]] == ["b_real"], (
        f"B.py cache was clobbered by an out-of-chunk node: {after}"
    )
    # A.py (the actual chunk file) was legitimately cached.
    a_cache = load_cached(a, tmp_path, kind="semantic")
    assert a_cache and any(n["id"] == "a_ok" for n in a_cache["nodes"])


def test_omitted_documents_are_reconciled_and_warned(tmp_path, capsys):
    """#1890: a chunk can return a clean, non-empty response that omits some of the
    documents it was given. Those docs must not vanish silently — the run reports
    them in `uncovered_files` and warns, instead of dropping them with no signal."""
    from graphify.llm import extract_corpus_parallel

    docs = []
    for i in range(4):
        f = tmp_path / f"doc{i}.md"
        f.write_text(f"# Doc {i}\n\nsome content\n", encoding="utf-8")
        docs.append(f)

    def omit_odd(chunk, **kwargs):
        # Return nodes only for even-numbered docs; a clean response, not a failure.
        nodes = []
        for u in chunk:
            name = getattr(u, "path", u).name
            idx = int(name[len("doc")])
            if idx % 2 == 0:
                nodes.append({"id": f"n{idx}", "source_file": name, "file_type": "document"})
        return {"nodes": nodes, "edges": [], "hyperedges": [], "input_tokens": 1, "output_tokens": 1}

    with patch("graphify.llm.extract_files_direct", side_effect=omit_odd):
        result = extract_corpus_parallel(
            docs, backend="kimi", root=tmp_path,
            token_budget=None, chunk_size=1, max_concurrency=1,
        )

    uncovered = {Path(p).name for p in result.get("uncovered_files", [])}
    assert uncovered == {"doc1.md", "doc3.md"}, f"reconciliation missed omissions: {uncovered}"
    err = capsys.readouterr().err
    assert "produced no nodes" in err and "doc1.md" in err


def test_out_of_scope_nodes_are_dropped_from_merged_result(tmp_path, capsys):
    """#1895: the #1757 cache guard skips the CACHE write for a node attributed
    to a real corpus file that was not dispatched, but the node itself still
    flowed into merged["nodes"] and landed in graph.json. The merged result must
    drop such nodes (and edges/hyperedges touching them), warn once, and record
    the count — while keeping in-scope sibling attributions (a node attributed
    to a different dispatched file in the same chunk) and non-file concept
    source_files, mirroring the #1757 `.is_file()` condition."""
    from graphify.llm import extract_corpus_parallel

    a = tmp_path / "A.md"; a.write_text("# a\n")
    c = tmp_path / "C.md"; c.write_text("# c\n")
    # B.py exists on disk but is NOT dispatched — the #1895 out-of-scope case.
    b = tmp_path / "B.py"; b.write_text("def b(): pass\n")

    def stray(chunk, **kwargs):
        return {
            "nodes": [
                {"id": "a_ok", "source_file": "A.md", "file_type": "document"},
                # sibling attribution: a different dispatched file in the same chunk
                {"id": "c_sibling", "source_file": "C.md", "file_type": "document"},
                # out-of-scope: real file on disk, never dispatched
                {"id": "b_stray", "source_file": "B.py", "file_type": "code"},
                # concept node: source_file is not a file — must survive
                {"id": "auth_flow", "source_file": "auth flow", "file_type": "concept"},
            ],
            "edges": [
                {"source": "a_ok", "target": "c_sibling", "source_file": "A.md"},
                {"source": "a_ok", "target": "b_stray", "source_file": "A.md"},
            ],
            "hyperedges": [
                {"id": "h_bad", "nodes": ["a_ok", "c_sibling", "b_stray"], "source_file": "A.md"},
                {"id": "h_ok", "nodes": ["a_ok", "c_sibling", "auth_flow"], "source_file": "A.md"},
            ],
            "input_tokens": 1, "output_tokens": 1,
        }

    with patch("graphify.llm.extract_files_direct", side_effect=stray):
        result = extract_corpus_parallel(
            [a, c], backend="kimi", root=tmp_path,
            token_budget=None, chunk_size=2, max_concurrency=1,
        )

    ids = {n["id"] for n in result["nodes"]}
    assert "b_stray" not in ids, "out-of-scope node leaked into the merged graph (#1895)"
    assert {"a_ok", "c_sibling", "auth_flow"} <= ids, (
        f"in-scope sibling/concept attributions must be kept: {ids}"
    )
    assert result["out_of_scope_dropped"] == 1
    # Edges/hyperedges referencing the dropped node id are gone; in-scope ones stay.
    assert all(
        "b_stray" not in (e.get("source"), e.get("target")) for e in result["edges"]
    ), f"edge to dropped node survived: {result['edges']}"
    assert any(
        e["source"] == "a_ok" and e["target"] == "c_sibling" for e in result["edges"]
    )
    assert [h["id"] for h in result["hyperedges"]] == ["h_ok"]
    err = capsys.readouterr().err
    assert "out-of-scope" in err and "B.py" in err
    # The dispatched files all produced nodes — reconciliation sees no gaps.
    assert result["uncovered_files"] == []


def test_out_of_scope_drop_count_is_zero_when_all_in_scope(tmp_path, capsys):
    """Counter-test: a clean run records out_of_scope_dropped == 0 and no warning."""
    from graphify.llm import extract_corpus_parallel

    a = tmp_path / "A.md"; a.write_text("# a\n")

    def clean(chunk, **kwargs):
        return {
            "nodes": [{"id": "a_ok", "source_file": "A.md", "file_type": "document"}],
            "edges": [], "hyperedges": [], "input_tokens": 1, "output_tokens": 1,
        }

    with patch("graphify.llm.extract_files_direct", side_effect=clean):
        result = extract_corpus_parallel(
            [a], backend="kimi", root=tmp_path,
            token_budget=None, chunk_size=1, max_concurrency=1,
        )

    assert result["out_of_scope_dropped"] == 0
    assert [n["id"] for n in result["nodes"]] == ["a_ok"]
    assert "out-of-scope" not in capsys.readouterr().err


def test_checkpoint_caches_sliced_document_chunks(tmp_path, capsys):
    """#1870: the checkpoint's allowlist must resolve a FileSlice to its parent
    path (via unit_path), not read a non-existent `.rel`. An oversized doc is
    split into FileSlice units; before the fix each sliced chunk leaked the
    FileSlice object into the allowlist, so save_semantic_cache raised TypeError,
    the best-effort except swallowed it, and the slice was never checkpointed."""
    from graphify.llm import extract_corpus_parallel, expand_oversized_files, _FILE_CHAR_CAP
    from graphify.file_slice import FileSlice
    from graphify.cache import load_cached

    doc = tmp_path / "big.md"
    doc.write_text("# Title\n" + ("word " * 12000) + "\n## Section\n" + ("more " * 12000))
    # sanity: the doc really does slice into FileSlice units
    units = expand_oversized_files([doc], _FILE_CHAR_CAP)
    assert len(units) > 1 and all(isinstance(u, FileSlice) for u in units)

    def sliced(chunk, **kwargs):
        assert any(isinstance(c, FileSlice) for c in chunk)
        return {
            "nodes": [{"id": "big_title", "source_file": "big.md", "file_type": "document"}],
            "edges": [], "hyperedges": [], "input_tokens": 1, "output_tokens": 1,
        }

    with patch("graphify.llm.extract_files_direct", side_effect=sliced):
        extract_corpus_parallel(
            [doc], backend="kimi", root=tmp_path,
            token_budget=None, chunk_size=1, max_concurrency=1,
        )

    assert "incremental cache checkpoint failed" not in capsys.readouterr().err, (
        "checkpoint raised on a FileSlice chunk (#1870)"
    )
    cached = load_cached(doc, tmp_path, kind="semantic")
    assert cached and any(n["id"] == "big_title" for n in cached["nodes"]), (
        "sliced document was never checkpointed (#1870)"
    )


def test_corpus_parallel_legacy_mode_when_token_budget_is_none(tmp_path):
    """token_budget=None should fall back to legacy fixed-count chunking."""
    from graphify.llm import extract_corpus_parallel

    files = []
    for i in range(45):
        f = tmp_path / f"f{i}.py"; f.write_text("x")
        files.append(f)

    chunks_seen = []

    def record(chunk, **kwargs):
        chunks_seen.append(len(chunk))
        return _stub_chunk_result(len(chunk), len(chunks_seen))

    with patch("graphify.llm.extract_files_direct", side_effect=record):
        extract_corpus_parallel(
            files, backend="kimi", token_budget=None, chunk_size=20, max_concurrency=1
        )

    # 45 files / chunk_size=20 = 3 chunks of 20, 20, 5
    assert chunks_seen == [20, 20, 5]


def test_corpus_parallel_token_budget_default_packs_files(tmp_path):
    """With the default token_budget, many tiny files pack into one chunk."""
    from graphify.llm import extract_corpus_parallel

    files = []
    for i in range(50):
        f = tmp_path / f"f{i}.py"; f.write_text("x = 1\n")
        files.append(f)

    chunks_seen = []

    def record(chunk, **kwargs):
        chunks_seen.append(len(chunk))
        return _stub_chunk_result(len(chunk), len(chunks_seen))

    with patch("graphify.llm.extract_files_direct", side_effect=record):
        extract_corpus_parallel(files, backend="kimi", max_concurrency=1)

    # 50 tiny files at default 60k token budget should pack into 1 chunk
    assert len(chunks_seen) == 1
    assert chunks_seen[0] == 50


# ---- Adaptive retry on truncation -------------------------------------------

def _stub_with_finish(file_count: int, finish_reason: str = "stop") -> dict:
    """Build a stub extraction result with a controllable finish_reason."""
    return {
        "nodes": [{"id": f"n_{i}"} for i in range(file_count)],
        "edges": [],
        "hyperedges": [],
        "input_tokens": 100 * file_count,
        "output_tokens": 50 * file_count,
        "finish_reason": finish_reason,
    }


def test_adaptive_retry_returns_directly_when_not_truncated(tmp_path):
    """No retry when finish_reason='stop' — single call, result passes through."""
    from graphify.llm import _extract_with_adaptive_retry

    files = [tmp_path / f"f{i}.py" for i in range(4)]
    for f in files:
        f.write_text("x")

    calls = []

    def stub(chunk, **kwargs):
        calls.append(len(chunk))
        return _stub_with_finish(len(chunk), finish_reason="stop")

    with patch("graphify.llm.extract_files_direct", side_effect=stub):
        result = _extract_with_adaptive_retry(
            files, backend="kimi", api_key=None, model=None, root=tmp_path, max_depth=3
        )

    assert calls == [4], f"expected 1 call of 4 files, got {calls}"
    assert len(result["nodes"]) == 4


def test_adaptive_retry_splits_when_finish_reason_length(tmp_path):
    """finish_reason='length' triggers split-in-half. Both halves succeed
    on the second try (mocked) and results merge."""
    from graphify.llm import _extract_with_adaptive_retry

    files = [tmp_path / f"f{i}.py" for i in range(4)]
    for f in files:
        f.write_text("x")

    calls = []

    def stub(chunk, **kwargs):
        calls.append(len(chunk))
        finish = "length" if len(chunk) == 4 else "stop"
        return _stub_with_finish(len(chunk), finish_reason=finish)

    with patch("graphify.llm.extract_files_direct", side_effect=stub):
        result = _extract_with_adaptive_retry(
            files, backend="kimi", api_key=None, model=None, root=tmp_path, max_depth=3
        )

    assert calls == [4, 2, 2], f"expected [4, 2, 2], got {calls}"
    assert len(result["nodes"]) == 4
    assert result["finish_reason"] == "stop"


def test_adaptive_retry_recurses_for_persistent_truncation(tmp_path):
    """When even the half-chunk truncates, split again. With 8 files and a
    truncation cutoff at >2 files, splits 8 → 4 → 2 (4 leaves of 2)."""
    from graphify.llm import _extract_with_adaptive_retry

    files = [tmp_path / f"f{i}.py" for i in range(8)]
    for f in files:
        f.write_text("x")

    calls = []

    def stub(chunk, **kwargs):
        calls.append(len(chunk))
        finish = "length" if len(chunk) > 2 else "stop"
        return _stub_with_finish(len(chunk), finish_reason=finish)

    with patch("graphify.llm.extract_files_direct", side_effect=stub):
        result = _extract_with_adaptive_retry(
            files, backend="kimi", api_key=None, model=None, root=tmp_path, max_depth=3
        )

    # Tree: 8 (trunc) → 4 + 4 (both trunc) → 2+2+2+2 (all stop)
    # Total calls: 1 + 2 + 4 = 7
    assert sorted(calls) == [2, 2, 2, 2, 4, 4, 8]
    assert len(result["nodes"]) == 8


def test_adaptive_retry_caps_at_max_depth(tmp_path, capsys):
    """If everything truncates, retries stop at max_depth — partial result
    kept with a warning, no infinite loop."""
    from graphify.llm import _extract_with_adaptive_retry

    files = [tmp_path / f"f{i}.py" for i in range(8)]
    for f in files:
        f.write_text("x")

    calls = []

    def always_truncate(chunk, **kwargs):
        calls.append(len(chunk))
        return _stub_with_finish(len(chunk), finish_reason="length")

    with patch("graphify.llm.extract_files_direct", side_effect=always_truncate):
        _extract_with_adaptive_retry(
            files, backend="kimi", api_key=None, model=None, root=tmp_path, max_depth=2
        )

    # max_depth=2 bounds the tree: root + 2 + 4 = 7 calls maximum
    assert len(calls) <= 7, f"recursion not bounded — {len(calls)} calls"
    err = capsys.readouterr().err
    assert "still truncated" in err


def test_adaptive_retry_single_file_truncation_does_not_recurse(tmp_path, capsys):
    """A single file that truncates can't be split further — surface a
    warning and return what we got. No infinite loop."""
    from graphify.llm import _extract_with_adaptive_retry

    f = tmp_path / "huge.py"; f.write_text("x")

    calls = []

    def stub(chunk, **kwargs):
        calls.append(len(chunk))
        return _stub_with_finish(len(chunk), finish_reason="length")

    with patch("graphify.llm.extract_files_direct", side_effect=stub):
        _extract_with_adaptive_retry(
            [f], backend="kimi", api_key=None, model=None, root=tmp_path, max_depth=3
        )

    assert calls == [1], f"single-file chunk recursed; calls = {calls}"
    err = capsys.readouterr().err
    assert "single-file chunk" in err and "truncated" in err


def test_corpus_parallel_uses_adaptive_retry(tmp_path):
    """End-to-end: extract_corpus_parallel routes through adaptive retry,
    so a chunk that truncates gets split and merged transparently before
    on_chunk_done fires."""
    from graphify.llm import extract_corpus_parallel

    files = [tmp_path / f"f{i}.py" for i in range(4)]
    for f in files:
        f.write_text("x")

    calls = []

    def stub(chunk, **kwargs):
        calls.append(len(chunk))
        finish = "length" if len(chunk) == 4 else "stop"
        return _stub_with_finish(len(chunk), finish_reason=finish)

    chunk_done_args = []
    with patch("graphify.llm.extract_files_direct", side_effect=stub):
        result = extract_corpus_parallel(
            files,
            backend="kimi",
            token_budget=None,
            chunk_size=4,
            max_concurrency=1,
            on_chunk_done=lambda i, t, r: chunk_done_args.append((i, t, len(r["nodes"]))),
        )

    # Adaptive retry runs INSIDE _run_one: 4 → 2 + 2 = 3 underlying API calls
    assert calls == [4, 2, 2]
    # User-visible: 1 chunk completion (the merged result)
    assert len(chunk_done_args) == 1
    assert chunk_done_args[0] == (0, 1, 4)
    assert len(result["nodes"]) == 4


# ---- #1685: special-token strings in docs must not crash token estimation ----

def test_estimate_file_tokens_handles_tiktoken_special_token(tmp_path):
    """A doc containing a literal tiktoken special token (e.g. <|endoftext|>)
    must not crash token estimation. tiktoken's default encode() raises on such
    strings appearing as ordinary text; we pass disallowed_special=() since this
    is only an estimate (#1685)."""
    import graphify.llm as llm
    if llm._TOKENIZER is None:
        import pytest
        pytest.skip("tiktoken not installed; estimation uses the char heuristic")
    f = tmp_path / "tokenizer-notes.md"
    f.write_text("The GPT end-of-text token is <|endoftext|> in the vocab.\n")
    n = llm._estimate_file_tokens(f)  # must not raise
    assert isinstance(n, int) and n > 0


def test_pack_chunks_with_special_token_doc_does_not_crash(tmp_path):
    """End to end: packing a corpus that includes a special-token doc must not
    raise (the crash in #1685 happened during token-budget packing)."""
    from graphify.llm import _pack_chunks_by_tokens
    doc = tmp_path / "doc.md"; doc.write_text("see <|endoftext|> and <|im_start|> tokens\n")
    code = tmp_path / "code.py"; code.write_text("def f():\n    return 1\n")
    chunks = _pack_chunks_by_tokens([doc, code], token_budget=60_000)
    assert chunks  # produced at least one chunk, no exception
