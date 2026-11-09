"""Splittable documents below character cap can bisect after output truncation (#5072)."""
from pathlib import Path
from unittest.mock import patch

import pytest

import graphify.llm as llm
from graphify.file_slice import (
    FileSlice,
    is_splittable_text,
    read_slice_text,
    unit_source_text,
)


@pytest.mark.parametrize("ext", [".md", ".txt", ".rst"])
def test_splittable_document_under_cap_bisects_on_truncation(tmp_path, ext):
    """When a splittable document below _FILE_CHAR_CAP truncates (finish_reason='length'),
    adaptive retry should promote the raw Path unit to a full-range FileSlice and bisect it,
    completing without being marked partial (#5072).
    """
    path = tmp_path / f"dense{ext}"
    content = "# Title\n\n" + "".join(f"Paragraph {i} with some content.\n\n" for i in range(40))
    path.write_text(content, encoding="utf-8")
    text = unit_source_text(path)
    assert len(text) < llm._FILE_CHAR_CAP

    raw = llm.expand_oversized_files([path], llm._FILE_CHAR_CAP)
    assert raw == [path], "File below cap must initially stay a raw Path"

    calls = []

    def mock_extract(chunk, **kwargs):
        calls.append(chunk)
        chunk_text = "".join(
            read_slice_text(u) if isinstance(u, FileSlice) else unit_source_text(u)
            for u in chunk
        )
        if len(chunk_text) > 700:
            return {
                "nodes": [{"id": f"node_{len(calls)}", "label": "n", "source_file": str(path)}],
                "edges": [],
                "hyperedges": [],
                "finish_reason": "length",
            }
        return {
            "nodes": [{"id": f"leaf_{len(calls)}", "label": "leaf", "source_file": str(path)}],
            "edges": [],
            "hyperedges": [],
            "finish_reason": "stop",
        }

    with patch.object(llm, "extract_files_direct", side_effect=mock_extract):
        result = llm._extract_with_adaptive_retry(
            raw, "kimi", "offline", "offline", path.parent, max_depth=3
        )

    is_partial = bool(result.get("partial") or result.get("_partial_files"))
    assert not is_partial, "Splittable document under cap should bisect and recover from truncation"
    assert result["finish_reason"] == "stop"
    assert len(calls) >= 3, f"Expected at least 1 root truncated call + bisected slice calls, got {len(calls)}"
    for subcall in calls[1:]:
        assert isinstance(subcall[0], FileSlice), "Bisected unit must be a FileSlice"


def test_code_file_under_cap_does_not_bisect_on_truncation(tmp_path):
    """Code files must never be sliced or bisected; they remain whole and partial on truncation."""
    path = tmp_path / "dense.py"
    path.write_text("x = 1\n" * 100, encoding="utf-8")
    raw = [path]

    calls = []

    def mock_extract(chunk, **kwargs):
        calls.append(chunk)
        return {
            "nodes": [{"id": "code_node", "label": "n", "source_file": str(path)}],
            "edges": [],
            "hyperedges": [],
            "finish_reason": "length",
        }

    with patch.object(llm, "extract_files_direct", side_effect=mock_extract):
        result = llm._extract_with_adaptive_retry(
            raw, "kimi", "offline", "offline", path.parent, max_depth=3
        )

    is_partial = bool(result.get("partial") or result.get("_partial_files"))
    assert is_partial, "Code file must stay partial when truncated"
    assert len(calls) == 1, "Code file must not be bisected"
