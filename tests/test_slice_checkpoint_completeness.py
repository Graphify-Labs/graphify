"""A sliced file is cached complete only once every slice has succeeded (#4943).

Each slice's checkpoint used to write the parent file's entry as complete, so a
run interrupted after the first slice served the head of the file as the whole
file, and a failed slice was hidden by the final save in the same way.
"""

from pathlib import Path
from unittest.mock import patch

import pytest

from graphify import llm
from graphify.cache import check_semantic_cache


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
