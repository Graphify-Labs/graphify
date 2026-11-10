"""A sliced file is cached complete only once every slice has succeeded (#4943, #5106).

Each slice's checkpoint used to write the parent file's entry as complete, so a
run interrupted after the first slice served the head of the file as the whole
file, and a failed slice was hidden by the final save in the same way. Similarly,
incomplete precomputed slice inputs must not be cached as complete (#5106).
"""

from pathlib import Path
from unittest.mock import patch

import pytest

from graphify import llm
from graphify.cache import check_semantic_cache
from graphify.file_slice import FileSlice


def _big_doc(root: Path) -> Path:
    path = root / "guide.md"
    path.write_text(
        "# Early\nEarly fact.\n" + "filler " * 6000 + "\n# Tail\nTail fact.\n",
        encoding="utf-8",
    )
    return path


def _small_doc(root: Path) -> Path:
    path = root / "note.md"
    path.write_text("# Note\nA short note.\n", encoding="utf-8")
    return path


def _endpoint(fail_on: int, exc: BaseException):
    calls: list[list] = []

    def endpoint(files, **kwargs):
        calls.append(list(files))
        if len(calls) == fail_on:
            raise exc
        nodes = [
            {"id": f"n{len(calls)}_{i}", "label": f"fact {len(calls)}",
             "source_file": str(llm.unit_path(f)), "source_location": "L1"}
            for i, f in enumerate(files)
        ]
        return {"nodes": nodes, "edges": [], "hyperedges": [],
                "input_tokens": 1, "output_tokens": 1, "finish_reason": "stop",
                "model": "fixture"}

    return endpoint, calls


def _run(root: Path, files: list[Path], endpoint) -> dict:
    with patch.object(llm, "extract_files_direct", endpoint):
        return llm.extract_corpus_parallel(
            files, backend="openai", root=root, cache_root=root / "out",
            max_concurrency=1, token_budget=1, max_retry_depth=0,
        )


def _uncached(root: Path, files: list[Path]) -> list[str]:
    *_, missing = check_semantic_cache(
        [str(f) for f in files], root=root, cache_root=root / "out",
        prompt=llm._extraction_system(),
    )
    return [Path(m).name for m in missing]


def test_interrupted_slices_leave_the_file_uncached(tmp_path):
    doc = _big_doc(tmp_path)
    endpoint, calls = _endpoint(fail_on=2, exc=KeyboardInterrupt())
    with pytest.raises(KeyboardInterrupt):
        _run(tmp_path, [doc], endpoint)
    assert len(calls) == 2
    assert _uncached(tmp_path, [doc]) == ["guide.md"]


def test_every_slice_succeeding_caches_the_file(tmp_path):
    doc = _big_doc(tmp_path)
    endpoint, calls = _endpoint(fail_on=0, exc=RuntimeError())
    _run(tmp_path, [doc], endpoint)
    assert len(calls) >= 2
    assert _uncached(tmp_path, [doc]) == []


def test_failed_slice_marks_the_file_partial_for_the_final_save(tmp_path):
    doc = _big_doc(tmp_path)
    endpoint, _ = _endpoint(fail_on=2, exc=RuntimeError("rate limited"))
    result = _run(tmp_path, [doc], endpoint)
    assert str(doc) in llm._partial_source_files(result)
    assert _uncached(tmp_path, [doc]) == ["guide.md"]


def test_unsliced_file_is_still_checkpointed_before_an_interrupt(tmp_path):
    note = _small_doc(tmp_path)
    doc = _big_doc(tmp_path)
    endpoint, _ = _endpoint(fail_on=2, exc=KeyboardInterrupt())
    with pytest.raises(KeyboardInterrupt):
        _run(tmp_path, [note, doc], endpoint)
    assert _uncached(tmp_path, [note, doc]) == ["guide.md"]


def test_held_slices_are_cached_in_chunk_order_under_parallel_completion(tmp_path):
    import json
    import threading
    doc = _big_doc(tmp_path)
    first_may_return = threading.Event()
    calls: list[int] = []
    lock = threading.Lock()

    def endpoint(files, **kwargs):
        with lock:
            calls.append(1)
            n = len(calls)
        text = llm.read_slice_text(files[0]) if isinstance(files[0], llm.FileSlice) else ""
        if "# Early" in text:
            first_may_return.wait(timeout=10)
        else:
            first_may_return.set()
        return {"nodes": [{"id": f"s{100 - n}", "label": "early" if "# Early" in text else f"later{n}",
                           "source_file": str(doc), "source_location": "L1"}],
                "edges": [], "hyperedges": [], "input_tokens": 1, "output_tokens": 1,
                "finish_reason": "stop", "model": "fixture"}

    with patch.object(llm, "extract_files_direct", endpoint):
        llm.extract_corpus_parallel(
            [doc], backend="openai", root=tmp_path, cache_root=tmp_path / "out",
            max_concurrency=4, token_budget=1, max_retry_depth=0,
        )
    entries = list((tmp_path / "out/graphify-out/cache/semantic").rglob("*.json"))
    assert len(entries) == 1
    labels = [n["label"] for n in json.loads(entries[0].read_text())["nodes"]]
    assert labels[0] == "early"


# ── precomputed FileSlice coverage (#5106) ──────────────────────────────────

def test_precomputed_fileslice_reproduction_5106_no_attribute_error(tmp_path):
    """Calling extract_corpus_parallel with precomputed FileSlice does not crash with AttributeError."""
    doc = tmp_path / "example.md"
    doc.write_text("HEAD\nTAIL\n", encoding="utf-8")
    endpoint, _ = _endpoint(fail_on=0, exc=RuntimeError())
    result = _run(tmp_path, [FileSlice(doc, 0, 5, 0, 2)], endpoint)
    assert result["failed_chunks"] == 0
    assert len(result["nodes"]) == 1
    assert str(doc) in (result.get("_partial_files") or [])


def test_incomplete_precomputed_slice_leaves_parent_uncached(tmp_path):
    """Incomplete slice coverage must not be checkpointed or cached as complete."""
    doc = tmp_path / "doc.md"
    doc.write_text("01234567890123456789", encoding="utf-8")  # 20 chars
    endpoint, _ = _endpoint(fail_on=0, exc=RuntimeError())
    result = _run(tmp_path, [FileSlice(doc, 0, 5, 0, 2)], endpoint)
    assert str(doc) in (result.get("_partial_files") or [])
    assert _uncached(tmp_path, [doc]) == ["doc.md"]


def test_complete_precomputed_slices_cache_the_parent(tmp_path):
    """Complete precomputed slices covering the whole parent file are cached complete."""
    doc = tmp_path / "doc.md"
    doc.write_text("0123456789", encoding="utf-8")  # 10 chars
    endpoint, _ = _endpoint(fail_on=0, exc=RuntimeError())
    slices = [FileSlice(doc, 0, 5, 0, 2), FileSlice(doc, 5, 10, 1, 2)]
    result = _run(tmp_path, slices, endpoint)
    assert str(doc) not in (result.get("_partial_files") or [])
    assert _uncached(tmp_path, [doc]) == []


def test_mixed_whole_file_and_precomputed_partial_slice(tmp_path):
    """A whole file is cached complete while an incomplete slice parent stays uncached."""
    note = _small_doc(tmp_path)
    doc = tmp_path / "doc.md"
    doc.write_text("01234567890123456789", encoding="utf-8")
    endpoint, _ = _endpoint(fail_on=0, exc=RuntimeError())
    result = _run(tmp_path, [note, FileSlice(doc, 0, 5, 0, 2)], endpoint)
    assert str(note) not in (result.get("_partial_files") or [])
    assert str(doc) in (result.get("_partial_files") or [])
    assert _uncached(tmp_path, [note, doc]) == ["doc.md"]

