"""Tests for graphify.llm._label_batch_with_retry — adaptive split-and-retry
on JSON parse failure during community labeling (#1278).
"""
from __future__ import annotations

import json
import re

import pytest

from graphify import llm as llm_mod


def _labels_for(
    prompt: str, unparseable: set[int] | frozenset[int] = frozenset()
) -> str:
    """Label every community in ``prompt``; garbage if any id is unparseable."""
    cids_in_prompt = [int(m) for m in re.findall(r"Community (\d+):", prompt)]
    if unparseable & set(cids_in_prompt):
        return "{this is not valid json, missing quotes"
    return json.dumps({str(cid): f"Label {cid}" for cid in cids_in_prompt})


def _make_sequenced_llm_stub(
    first_reply: str,
    prompts: list[list[int]],
    unparseable: set[int] | frozenset[int] = frozenset(),
):
    """Emit ``first_reply`` on the initial LLM call, then delegate to ``_labels_for``."""
    def fake_call_llm(prompt: str, **_kwargs) -> str:
        prompts.append([int(m) for m in re.findall(r"Community (\d+):", prompt)])
        if len(prompts) == 1:
            return first_reply
        return _labels_for(prompt, unparseable=unparseable)

    return fake_call_llm


def test_label_batch_recovers_via_split_on_invalid_json(monkeypatch):
    """Demonstrates the bug fix.

    The full batch of 4 communities triggers malformed JSON from the LLM.
    The helper splits in half (2+2) and retries each half. Both sub-batches
    succeed. Every community ends up labeled — none silently dropped.
    """
    batch_cids = [42, 99, 137, 201]
    batch_lines = [
        "Community 42: validate_token, get_session",
        "Community 99: create_order, add_to_cart",
        "Community 137: build_graph, cluster_nodes",
        "Community 201: render_route, handle_request",
    ]
    prompts: list[list[int]] = []
    monkeypatch.setattr(
        llm_mod,
        "_call_llm",
        _make_sequenced_llm_stub("{this is not valid json, missing quotes", prompts),
    )

    result = llm_mod._label_batch_with_retry(
        batch_cids, batch_lines, backend="gemini", model=None,
    )

    assert result == {42: "Label 42", 99: "Label 99", 137: "Label 137", 201: "Label 201"}
    assert len(prompts) >= 2


def test_label_batch_recovers_when_json_is_valid_but_incomplete(monkeypatch):
    """A truncated object can salvage valid pairs without covering the batch."""
    batch_cids = [42, 99, 137, 201]
    batch_lines = [f"Community {cid}: node_{cid}" for cid in batch_cids]
    prompts: list[list[int]] = []
    monkeypatch.setattr(
        llm_mod,
        "_call_llm",
        _make_sequenced_llm_stub(
            '{"42":"Label 42","99":"Label 99","137":"Label 137"', prompts
        ),
    )

    result = llm_mod._label_batch_with_retry(
        batch_cids, batch_lines, backend="gemini", model=None,
    )

    assert result == {cid: f"Label {cid}" for cid in batch_cids}
    assert len(prompts) == 2


def test_a_missing_id_that_never_parses_keeps_the_labels_already_had(monkeypatch):
    """A truncated reply labels part of the batch; retrying a missing id that
    still won't parse must not discard those labels or ask for them again.

    The nested retry used to run inside the try that guards this batch's own
    parse, so its failure re-split the whole batch (re-requesting 42 and 99)
    and the re-split failed the same way, dropping every label of the batch.
    """
    batch_cids = [42, 99, 137, 201]
    batch_lines = [f"Community {cid}: node_{cid}" for cid in batch_cids]
    prompts: list[list[int]] = []
    monkeypatch.setattr(
        llm_mod,
        "_call_llm",
        _make_sequenced_llm_stub(
            '{"42":"Label 42","99":"Label 99"', prompts, unparseable={137}
        ),
    )

    result = llm_mod._label_batch_with_retry(
        batch_cids, batch_lines, backend="gemini", model=None,
    )

    assert result == {42: "Label 42", 99: "Label 99", 201: "Label 201"}
    assert prompts == [batch_cids, [137], [201]]


def test_a_half_that_never_parses_does_not_discard_the_other_half(monkeypatch):
    """After a split, one half failing at the base case must not take the
    other half's labels down with it; only the unparseable id stays unlabeled."""
    batch_cids = [42, 99, 137, 201]
    batch_lines = [f"Community {cid}: node_{cid}" for cid in batch_cids]
    prompts: list[list[int]] = []
    monkeypatch.setattr(
        llm_mod,
        "_call_llm",
        _make_sequenced_llm_stub(
            "{this is not valid json, missing quotes", prompts, unparseable={137}
        ),
    )

    result = llm_mod._label_batch_with_retry(
        batch_cids, batch_lines, backend="gemini", model=None,
    )

    assert result == {42: "Label 42", 99: "Label 99", 201: "Label 201"}
    assert prompts == [batch_cids, [42, 99], [137, 201], [137], [201]]


def test_a_batch_that_never_parses_still_raises(monkeypatch):
    """With nothing labeled anywhere, the parse error still reaches the caller,
    which skips the batch (label_communities)."""
    monkeypatch.setattr(
        llm_mod, "_call_llm", lambda prompt, **_kwargs: "{not json at all",
    )

    with pytest.raises(ValueError) as exc_info:
        llm_mod._label_batch_with_retry(
            [1, 2, 3], ["Community 1: a", "Community 2: b", "Community 3: c"],
            backend="gemini", model=None,
        )
    assert "not parseable JSON" in str(exc_info.value)
