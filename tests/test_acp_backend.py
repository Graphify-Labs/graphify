"""Tests for Graphify's generic ACP backend."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from graphify import llm
from graphify.acp import AcpResult, _child_environment, _json_object, run_acp


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


def test_codex_cli_alias_routes_through_acp(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("GRAPHIFY_CODEX_BIN", raising=False)
    monkeypatch.delenv("GRAPHIFY_ACP_BIN", raising=False)
    llm._WARNED_BACKEND_ALIASES.clear()
    source = tmp_path / "note.md"
    source.write_text("# Compatibility route\n")
    result = {"nodes": [], "edges": [], "hyperedges": []}
    with patch("graphify.llm._call_acp", return_value=result) as call:
        assert llm.extract_files_direct([source], backend="codex-cli", root=tmp_path) is result
    assert call.called
    assert "deprecated" in capsys.readouterr().err


def test_codex_cli_alias_rejects_legacy_direct_binary(monkeypatch):
    monkeypatch.setenv("GRAPHIFY_CODEX_BIN", "/nix/store/example/bin/codex")
    monkeypatch.delenv("GRAPHIFY_ACP_BIN", raising=False)
    with pytest.raises(RuntimeError, match="GRAPHIFY_ACP_BIN"):
        llm._normalize_backend("codex-cli")


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
    assert llm._normalize_backend("acp") == "acp"


def test_acp_config_rejects_non_scalar_values():
    with pytest.raises(ValueError, match="strings or booleans"):
        _json_object('{"nested": {"unsafe": true}}', "GRAPHIFY_ACP_CONFIG_JSON")


def test_acp_child_environment_does_not_forward_secrets(monkeypatch):
    monkeypatch.setenv("HOME", "/tmp/graphify-home")
    monkeypatch.setenv("PATH", "/bin")
    monkeypatch.setenv("CODEX_HOME", "/tmp/codex-home")
    monkeypatch.setenv("OPENAI_API_KEY", "secret-openai")
    monkeypatch.setenv("GITHUB_TOKEN", "secret-github")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "secret-anthropic")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "secret-aws")
    monkeypatch.setenv("ACP_PROVIDER_TOKEN", "explicit-provider-token")
    monkeypatch.setenv("GRAPHIFY_CHILD_ENV_ALLOWLIST", "ACP_PROVIDER_TOKEN")

    environment = _child_environment()

    assert environment["HOME"] == "/tmp/graphify-home"
    assert environment["CODEX_HOME"] == "/tmp/codex-home"
    assert environment["ACP_PROVIDER_TOKEN"] == "explicit-provider-token"
    for secret_name in (
        "OPENAI_API_KEY",
        "GITHUB_TOKEN",
        "ANTHROPIC_API_KEY",
        "AWS_SECRET_ACCESS_KEY",
    ):
        assert secret_name not in environment
    assert environment["NO_BROWSER"] == "1"


def test_acp_child_environment_rejects_invalid_allowlist_names(monkeypatch):
    monkeypatch.setenv("GRAPHIFY_CHILD_ENV_ALLOWLIST", "VALID_NAME,NOT-VALID")
    with pytest.raises(ValueError, match="invalid environment variable name"):
        _child_environment()


def test_official_sdk_transport_and_session_options(tmp_path, monkeypatch):
    config_log = tmp_path / "config.jsonl"
    fake_agent = Path(__file__).with_name("fake_acp_agent.py")
    monkeypatch.setenv("GRAPHIFY_ACP_BIN", sys.executable)
    monkeypatch.setenv("GRAPHIFY_ACP_ARGS_JSON", json.dumps([str(fake_agent)]))
    monkeypatch.setenv("GRAPHIFY_ACP_CONFIG_JSON", '{"mode": "read-only"}')
    monkeypatch.setenv("GRAPHIFY_FAKE_ACP_CONFIG_LOG", str(config_log))
    monkeypatch.setenv("GRAPHIFY_CHILD_ENV_ALLOWLIST", "GRAPHIFY_FAKE_ACP_CONFIG_LOG")

    result = run_acp("extract", model="gpt-test")

    assert result.text == '{"nodes": [], "edges": [], "hyperedges": []}'
    assert result.input_tokens == 11
    assert result.output_tokens == 7
    options = [json.loads(line) for line in config_log.read_text().splitlines()]
    assert {option["configId"]: option["value"] for option in options} == {
        "model": "gpt-test",
        "mode": "read-only",
    }
