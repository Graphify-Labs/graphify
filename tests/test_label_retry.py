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
