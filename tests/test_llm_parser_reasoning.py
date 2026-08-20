"""#2882: reasoning-first models narrate before they answer.

`nvidia/nemotron-*`, gemma and friends reply with a chain of thought and only
then emit the JSON — sometimes bare, sometimes fenced, sometimes after a fence
of their own. The narration routinely contains braces, so the first `{` in the
text is not the answer. `_parse_llm_json` used to try exactly that one
candidate and give up, dropping chunks whose answer was sitting right there:

    [graphify] LLM returned invalid JSON, skipping chunk (first 200 chars:
    'Let me analyze the provided source files to extract a knowledge graph...')
"""
from __future__ import annotations

from graphify import llm

EMPTY = {"nodes": [], "edges": [], "hyperedges": []}


def test_chain_of_thought_preamble_then_bare_json():
    raw = (
        "Let me analyze the provided source files to extract a knowledge graph "
        "fragment. I need to follow the rules carefully:\n\n"
        "1. EXTRACTED: relationship explicit in source\n"
        "2. INFERRED: reasonable inference\n"
        "3. The shape I must emit is { ... } with the keys listed above\n\n"
        '{"nodes": [{"id": "a", "label": "A"}], "edges": [], "hyperedges": []}'
    )
    assert llm._parse_llm_json(raw)["nodes"] == [{"id": "a", "label": "A"}]


def test_narration_fence_precedes_the_answer_fence():
    """A ```text block in the narration must not swallow the ```json answer.

    The old fence handling took the FIRST ``` anywhere in the text and then cut
    at the LAST one, which mangled everything in between.
    """
    raw = (
        "Here's a thinking process:\n\n"
        "1.  **Analyze User Input:**\n"
        "   - User provided several `<untrusted_source>` blocks.\n"
        "   - Sketching the shape first:\n"
        "```text\n"
        "{ one node per file, plus edges }\n"
        "```\n\n"
        "Now the answer:\n\n"
        "```json\n"
        '{"nodes": [{"id": "docs_x", "label": "x.md"}], "edges": []}\n'
        "```\n"
    )
    assert llm._parse_llm_json(raw)["nodes"] == [{"id": "docs_x", "label": "x.md"}]


def test_think_block_is_stripped_before_parsing():
    """deepseek-r1 / qwq style: the chain of thought is tagged, and it is full
    of braces that would otherwise be probed as candidate objects."""
    raw = (
        "<think>\nI should emit {nodes, edges}. Let me check each file: "
        "{a.py} imports {b.py}...\n</think>\n"
        '{"nodes": [{"id": "b"}], "edges": [{"source": "a", "target": "b"}]}'
    )
    result = llm._parse_llm_json(raw)
    assert result["nodes"] == [{"id": "b"}]
    assert result["edges"] == [{"source": "a", "target": "b"}]


def test_parseable_prose_object_does_not_shadow_the_answer():
    """An earlier object that happens to be valid JSON is not the fragment."""
    raw = (
        'For reference the schema is {"description": "graph fragment"}.\n'
        '{"nodes": [{"id": "real"}], "edges": []}'
    )
    assert llm._parse_llm_json(raw)["nodes"] == [{"id": "real"}]


def test_pure_prose_reply_still_degrades_to_empty_fragment():
    """No answer anywhere: the empty fragment, never an exception, so the
    hollow detector takes over."""
    raw = (
        "Here's a thinking process:\n1. The user wants a knowledge graph.\n"
        "2. But I will describe it in words: { a depends on b }.\n"
    )
    assert llm._parse_llm_json(raw) == EMPTY


def test_candidate_scan_is_bounded():
    """A pathological reply full of braces must not turn recovery quadratic."""
    raw = "{ noise } " * 5000 + '{"nodes": [{"id": "z"}], "edges": []}'
    # The answer carries the fragment keys, so it is probed before the noise.
    assert llm._parse_llm_json(raw)["nodes"] == [{"id": "z"}]
    # Likely and unlikely candidates are capped separately, so the noise
    # cannot crowd out the answer, and neither list can grow without bound.
    assert len(llm._json_object_candidates(raw)) <= 2 * llm._MAX_OBJECT_CANDIDATES


def test_empty_schema_restatement_does_not_shadow_the_answer():
    """A restated shape carries the extraction keys but no content.

    Preferring any candidate that merely *has* nodes/edges let the restatement
    win over the answer below it — the same shadowing this module exists to
    prevent, one level deeper than a keyless prose object.
    """
    raw = (
        "The schema is:\n"
        "```json\n"
        '{"nodes": [], "edges": []}\n'
        "```\n"
        "Now the answer:\n"
        '{"nodes": [{"id": "real"}], "edges": []}\n'
    )
    assert llm._parse_llm_json(raw)["nodes"] == [{"id": "real"}]


def test_empty_restatement_without_a_fence_does_not_shadow_either():
    raw = (
        'Shape: {"nodes": [], "edges": [], "hyperedges": []}\n'
        'Answer: {"nodes": [{"id": "real"}], "edges": []}\n'
    )
    assert llm._parse_llm_json(raw)["nodes"] == [{"id": "real"}]


def test_a_genuinely_empty_extraction_is_still_returned():
    """The model looked and found nothing: that is a valid answer, and it must
    keep reading as an empty fragment so the hollow detector takes over."""
    assert llm._parse_llm_json('{"nodes": [], "edges": [], "hyperedges": []}') == EMPTY
    assert llm._parse_llm_json(
        'Nothing to extract here.\n```json\n{"nodes": [], "edges": []}\n```'
    )["nodes"] == []


def test_empty_fragment_outranks_a_non_fragment_object():
    """Right shape but empty still beats an object that is not a fragment."""
    raw = (
        'Notes: {"description": "graph fragment", "version": 2}\n'
        '{"nodes": [], "edges": []}\n'
    )
    result = llm._parse_llm_json(raw)
    assert "description" not in result
    assert result["nodes"] == []
