"""Tests for chunked C-encoder streaming in write_json_atomic."""
import json
from pathlib import Path

from graphify.paths import write_json_atomic


def test_write_json_atomic_chunked_matches_json_dumps_byte_for_byte(tmp_path: Path) -> None:
    """Chunked streaming for large lists must emit bytes identical to json.dumps."""
    obj = {
        "directed": False,
        "nodes": [{"id": f"n_{i}", "label": f"fn_{i}_é"} for i in range(2500)],
        "links": [{"source": f"n_{i}", "target": f"n_{i + 1}"} for i in range(2499)],
        "meta": {"version": 1},
    }
    for compact in (True, False):
        for ensure_ascii in (True, False):
            out = tmp_path / f"graph_{compact}_{ensure_ascii}.json"
            write_json_atomic(out, obj, ensure_ascii=ensure_ascii, compact=compact)
            seps = (",", ":") if compact else None
            expected = json.dumps(obj, ensure_ascii=ensure_ascii, separators=seps).encode("utf-8")
            assert out.read_bytes() == expected


def test_write_json_atomic_non_string_keys_fall_back_cleanly(tmp_path: Path) -> None:
    """Dicts with non-string keys still serialize identically to json.dumps."""
    obj = {1: "one", "items": list(range(1500))}
    out = tmp_path / "int_keys.json"
    write_json_atomic(out, obj, compact=True)
    assert out.read_bytes() == json.dumps(obj, separators=(",", ":")).encode("utf-8")
