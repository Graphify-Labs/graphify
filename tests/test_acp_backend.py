"""Tests for Graphify's generic ACP backend."""
from __future__ import annotations

from unittest.mock import patch

from graphify import llm
from graphify.acp import AcpResult


def test_acp_backend_requires_no_api_key():
    assert "acp" in llm.BACKENDS
    assert llm.BACKENDS["acp"]["pricing"] == {"input": 0.0, "output": 0.0}
    assert llm.estimate_cost("acp", 1_000_000, 1_000_000) == 0.0


def test_extract_files_direct_dispatches_to_acp_without_an_api_key(tmp_path):
    source = tmp_path / "note.md"
    source.write_text("# ACP route\n")
    result = {"nodes": [], "edges": [], "hyperedges": []}
    with patch("graphify.llm._call_acp", return_value=result) as call:
        assert llm.extract_files_direct([source], backend="acp", root=tmp_path) is result
    assert call.called


def test_codex_cli_routes_through_the_authenticated_cli(tmp_path):
    source = tmp_path / "note.md"
    source.write_text("# Compatibility route\n")
    result = {"nodes": [], "edges": [], "hyperedges": []}
    with patch("graphify.llm._call_codex_cli", return_value=result) as call:
        assert llm.extract_files_direct([source], backend="codex-cli", root=tmp_path) is result
    assert call.called


def test_call_acp_maps_usage_and_stop_reason():
    response = AcpResult(
        text='{"nodes": [{"label": "source"}], "edges": [], "hyperedges": []}',
        input_tokens=14,
        output_tokens=7,
        model="gpt-test",
        stop_reason="end_turn",
    )
    with patch("graphify.acp.run_acp", return_value=response):
        parsed = llm._call_acp("source", model="gpt-test", max_tokens=512)
    assert parsed["nodes"] == [{"label": "source"}]
    assert parsed["input_tokens"] == 14
    assert parsed["output_tokens"] == 7
    assert parsed["model"] == "gpt-test"
    assert parsed["finish_reason"] == "stop"


def test_acp_parallelism_is_serial_by_default(monkeypatch):
    monkeypatch.delenv("GRAPHIFY_ACP_PARALLEL", raising=False)
    assert llm._normalize_backend("codex-cli") == "codex-cli"
