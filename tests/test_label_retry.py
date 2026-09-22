"""Tests for graphify.llm._label_batch_with_retry — adaptive split-and-retry
on JSON parse failure during community labeling (#1278).
"""
from __future__ import annotations

import json
import re

from graphify import llm as llm_mod


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
    call_count = {"n": 0}

    def fake_call_llm(prompt: str, **_kwargs) -> str:
        """First call (4 communities): returns broken JSON to trigger retry.
        Subsequent calls (<=2 communities): return a clean JSON object
        labeling whatever community IDs appear in the prompt.
        """
        call_count["n"] += 1
        cids_in_prompt = [int(m) for m in re.findall(r"Community (\d+):", prompt)]
        if call_count["n"] == 1:
            return "{this is not valid json, missing quotes"
        return json.dumps({str(cid): f"Label {cid}" for cid in cids_in_prompt})

    monkeypatch.setattr(llm_mod, "_call_llm", fake_call_llm)

    result = llm_mod._label_batch_with_retry(
        batch_cids, batch_lines, backend="gemini", model=None,
    )

    assert result == {42: "Label 42", 99: "Label 99", 137: "Label 137", 201: "Label 201"}
    assert call_count["n"] >= 2


def test_label_batch_escalates_budget_on_blank_reasoning_completion(monkeypatch):
    """A reasoning model can spend its whole completion budget on the
    (separately-returned) chain-of-thought and return empty content with
    finish_reason=length. Splitting the batch only shrinks the budget
    (min(256 + 48*n, 8192)), so it can never recover. The batch must escalate
    max_tokens first and stay whole (#3747)."""
    monkeypatch.delenv("GRAPHIFY_MAX_OUTPUT_TOKENS", raising=False)
    batch_cids = [1, 2]
    batch_lines = ["Community 1: alpha, beta", "Community 2: gamma, delta"]
    seen: dict = {"max_tokens": [], "batch_sizes": []}

    def fake_call_llm(prompt: str, **kwargs) -> str:
        mt = kwargs["max_tokens"]
        seen["max_tokens"].append(mt)
        cids = re.findall(r"Community (\d+):", prompt)
        seen["batch_sizes"].append(len(cids))
        # Base budget for 2 communities is min(256 + 48*2, 8192) = 352; the
        # reasoning model returns empty until the budget is doubled to 704.
        if mt < 704:
            return ""
        return json.dumps({cid: f"L{cid}" for cid in cids})

    monkeypatch.setattr(llm_mod, "_call_llm", fake_call_llm)

    result = llm_mod._label_batch_with_retry(
        batch_cids, batch_lines, backend="myendpoint", model=None,
    )

    assert result == {1: "L1", 2: "L2"}
    assert max(seen["max_tokens"]) >= 704, "budget must escalate past the base 352"
    assert all(sz == 2 for sz in seen["batch_sizes"]), (
        "the batch must recover via a larger budget, never by splitting"
    )


def test_label_batch_nonempty_malformed_splits_without_budget_escalation(monkeypatch):
    """A non-empty but malformed reply is a parse problem a bigger budget won't
    fix, so it must split immediately rather than burn extra full-budget calls
    (#3747). Only a blank completion triggers budget escalation."""
    monkeypatch.delenv("GRAPHIFY_MAX_OUTPUT_TOKENS", raising=False)
    batch_cids = [1, 2]
    batch_lines = ["Community 1: alpha, beta", "Community 2: gamma, delta"]
    seen: dict = {"max_tokens": []}

    def fake_call_llm(prompt: str, **kwargs) -> str:
        seen["max_tokens"].append(kwargs["max_tokens"])
        cids = re.findall(r"Community (\d+):", prompt)
        if len(cids) == 2:
            return "{garbage, not json"      # non-empty malformed -> split, no escalation
        return json.dumps({cid: f"L{cid}" for cid in cids})

    monkeypatch.setattr(llm_mod, "_call_llm", fake_call_llm)

    result = llm_mod._label_batch_with_retry(
        batch_cids, batch_lines, backend="myendpoint", model=None,
    )

    assert result == {1: "L1", 2: "L2"}
    # The 2-community call ran once at the base budget only; no doubled retry.
    assert seen["max_tokens"].count(352) == 1, "malformed (non-blank) must not escalate the budget"


def test_label_batch_blank_at_max_budget_raises_not_loops(monkeypatch):
    """A batch that stays blank even at the 8192 cap must eventually raise (so
    the caller falls back to placeholders), not loop forever escalating."""
    monkeypatch.delenv("GRAPHIFY_MAX_OUTPUT_TOKENS", raising=False)

    def fake_call_llm(prompt: str, **kwargs) -> str:
        return ""  # always blank, at every budget

    monkeypatch.setattr(llm_mod, "_call_llm", fake_call_llm)

    import pytest
    with pytest.raises((ValueError, json.JSONDecodeError)):
        llm_mod._label_batch_with_retry([1], ["Community 1: a, b"], backend="x", model=None)
