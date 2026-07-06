"""#1631 — a malformed LLM chunk (a stray non-dict entry in edges/nodes) must
not crash the merge/cache-write and discard all successful chunks.

`sem_result["edges"]` could contain a bare list where an edge object belongs
(a JSON array slipping past parse). Downstream code calls ``.get()`` per entry
(the AST+semantic merge at __main__.py and the semantic-cache writer both did),
raising ``AttributeError: 'list' object has no attribute 'get'`` and losing all
33 successful chunks. `_parse_llm_json` now sanitizes the fragment at the single
parse chokepoint so every consumer only ever sees lists of dicts.
"""
from __future__ import annotations

import json

from graphify.llm import _parse_llm_json, _sanitize_fragment


def test_sanitize_drops_non_dict_edge_entries():
    frag = {
        "nodes": [{"id": "a"}, ["not", "a", "dict"], "bare-string", {"id": "b"}],
        "edges": [{"source": "a", "target": "b"}, ["stray", "list"], 42],
        "hyperedges": [{"id": "h"}, None],
    }
    out = _sanitize_fragment(frag)
    assert out["nodes"] == [{"id": "a"}, {"id": "b"}]
    assert out["edges"] == [{"source": "a", "target": "b"}]
    assert out["hyperedges"] == [{"id": "h"}]


def test_sanitize_coerces_non_list_values_to_empty():
    frag = {"nodes": {"id": "oops"}, "edges": "nope", "hyperedges": None}
    out = _sanitize_fragment(frag)
    assert out["nodes"] == []
    assert out["edges"] == []
    # None is left as-is (absent key semantics) — the guard only fixes lists/values
    assert out.get("hyperedges") is None


def test_parse_llm_json_sanitizes_stray_list_in_edges():
    raw = json.dumps({
        "nodes": [{"id": "a"}],
        "edges": [{"source": "a", "target": "b"}, ["malformed"]],
        "hyperedges": [],
    })
    parsed = _parse_llm_json(raw)
    # Every entry that survives must be a dict so downstream .get() is safe.
    for key in ("nodes", "edges", "hyperedges"):
        assert all(isinstance(x, dict) for x in parsed.get(key, []))
    assert parsed["edges"] == [{"source": "a", "target": "b"}]


def test_parse_llm_json_fenced_response_is_sanitized():
    raw = (
        "Here you go:\n\n```json\n"
        + json.dumps({"nodes": [["bad"], {"id": "ok"}], "edges": []})
        + "\n```\n"
    )
    parsed = _parse_llm_json(raw)
    assert parsed["nodes"] == [{"id": "ok"}]


def test_merge_after_sanitize_does_not_raise_on_source_file_access():
    # Mirrors the __main__.py comprehension that crashed: e.get("source_file", "").
    parsed = _parse_llm_json(json.dumps({
        "nodes": [{"id": "a", "source_file": "d.md"}],
        "edges": [{"source": "a", "target": "b"}, ["oops"]],
    }))
    # This is exactly the pattern at __main__.py:4858-4860.
    seen = {n.get("source_file", "") for n in parsed.get("nodes", [])}
    seen |= {e.get("source_file", "") for e in parsed.get("edges", [])}
    assert "d.md" in seen
