"""Independent model fragments must not become a first-fragment cache hit."""
from __future__ import annotations

import json

import pytest

from graphify import llm
from graphify.cache import check_semantic_cache, save_semantic_cache


FIRST = {"nodes": [{"id": "first", "label": "First", "source_file": "doc.md"}],
         "edges": [], "hyperedges": []}
SECOND = {"nodes": [{"id": "second", "label": "Second", "source_file": "doc.md"}],
          "edges": [], "hyperedges": []}
EMPTY = {"nodes": [], "edges": [], "hyperedges": []}


def _fenced(*fragments):
    return "Here are the fragments:\n" + "\n".join(
        "```json\n" + json.dumps(f) + "\n```" for f in fragments
    )


@pytest.mark.parametrize("raw", [
    _fenced(FIRST, SECOND), json.dumps([FIRST, SECOND]),
    "```json\n" + json.dumps([FIRST, SECOND]) + "\n```",
    json.dumps(FIRST) + "\n" + json.dumps(SECOND),
    _fenced(FIRST) + "\n" + json.dumps(SECOND),
])
def test_independent_fragments_fail_closed_and_trigger_retry(raw, capsys):
    parsed = llm._parse_llm_json(raw)
    assert parsed == EMPTY
    assert llm._response_is_hollow(raw, parsed)
    assert "fragment" in capsys.readouterr().err.lower()


def test_later_edges_or_hyperedges_also_prevent_first_fragment_acceptance():
    later = {"edges": [{"source": "first", "target": "other", "relation": "calls"}],
             "hyperedges": [{"id": "group", "nodes": ["first", "other", "third"]}]}
    assert llm._parse_llm_json(_fenced(FIRST, later)) == EMPTY


@pytest.mark.parametrize("raw", [_fenced(FIRST), _fenced(FIRST, FIRST)])
def test_duplicate_discovery_of_one_fragment_is_not_ambiguity(raw):
    assert llm._parse_llm_json(raw) == FIRST


@pytest.mark.parametrize("raw", [
    json.dumps([FIRST]),
    "```json\n" + json.dumps([FIRST]) + "\n```",
])
def test_single_element_array_with_one_valid_fragment_is_accepted(raw):
    # A model that wraps its one answer in a single-element array is
    # unambiguous; unwrap it rather than fail-closed into an endless retry.
    assert llm._parse_llm_json(raw) == FIRST


def test_nested_graph_shaped_metadata_is_not_an_independent_answer():
    outer = {"nodes": [{"id": "outer", "metadata": {"nodes": [{"id": "inner"}]}}],
             "edges": [], "hyperedges": []}
    assert llm._parse_llm_json(_fenced(outer)) == outer


def test_complete_top_level_object_is_authoritative():
    outer = {"nodes": [{"id": "outer"}], "edges": [], "hyperedges": [],
             "metadata": {"nodes": [{"id": "inner"}]}}
    assert llm._parse_llm_json(json.dumps(outer)) == outer


def test_fenced_array_cannot_hide_later_fragments_behind_candidate_limit():
    first = {"nodes": [{"id": str(i), "metadata": {"nodes": [{"id": "nested"}]}}
                       for i in range(2 * llm._MAX_OBJECT_CANDIDATES)]}
    raw = "```json\n" + json.dumps([first, SECOND]) + "\n```"
    assert llm._parse_llm_json(raw) == EMPTY


@pytest.mark.parametrize("recover", [False, True])
def test_ambiguous_response_retries_or_leaves_file_uncached(tmp_path, monkeypatch, recover):
    doc = tmp_path / "doc.md"
    doc.write_text("# Doc\nFirst and Second\n", encoding="utf-8")
    responses = [_fenced(FIRST, SECOND), json.dumps({
        "nodes": FIRST["nodes"] + SECOND["nodes"], "edges": [], "hyperedges": [],
    })]
    calls = []

    def extract(*args, **kwargs):
        index = min(len(calls), 1) if recover else 0
        raw = responses[index]
        calls.append(raw)
        result = llm._parse_llm_json(raw)
        result.update(input_tokens=1, output_tokens=1, finish_reason="stop", model="test")
        return llm._mark_hollow(result, raw, "test")

    monkeypatch.setattr(llm, "extract_files_direct", extract)
    monkeypatch.setattr(llm, "_HOLLOW_BACKOFF_S", (0,))
    result = llm._extract_with_adaptive_retry(
        [doc], "openai", "test", "test", tmp_path, max_depth=1,
    )
    partial = llm._partial_source_files(result)
    save_semantic_cache(result["nodes"], result.get("edges", []), result.get("hyperedges", []),
                        root=tmp_path, allowed_source_files=[doc], prompt="test",
                        partial_source_files=partial)
    cached, _, _, uncached = check_semantic_cache([str(doc)], root=tmp_path, prompt="test")
    assert len(calls) == 2
    if recover:
        assert partial == []
        assert uncached == []
        assert {n["id"] for n in cached} == {"first", "second"}
    else:
        assert partial == [str(doc)]
        assert uncached == [str(doc)]
        assert cached == []
