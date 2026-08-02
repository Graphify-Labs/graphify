"""Tests for the GitHub Copilot CLI subscription backend.

The subprocess and executable lookup are mocked so the suite needs neither a
Copilot installation nor network/enterprise credentials.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from graphify import llm

_RESPONSE = json.dumps(
    {
        "nodes": [
            {
                "id": "policy",
                "label": "Policy",
                "file_type": "document",
                "source_file": "policy.md",
            }
        ],
        "edges": [],
        "hyperedges": [],
    }
)

_HELP = "\n".join(
    [
        "-s, --silent",
        "--model=MODEL",
        "--no-color",
        "--no-custom-instructions",
        "--no-ask-user",
        "--no-auto-update",
        "--no-bash-env",
        "--no-experimental",
        "--disable-builtin-mcps",
        "--no-remote",
        "--no-remote-export",
        "--deny-tool=TOOL",
    ]
)


@pytest.fixture
def fake_copilot(monkeypatch):
    completed = MagicMock(returncode=0, stdout=_RESPONSE, stderr="")
    monkeypatch.setattr(llm, "_copilot_cli_help", lambda _cmd: _HELP)
    with patch("shutil.which", return_value="/fake/bin/copilot"), patch(
        "subprocess.run", return_value=completed
    ) as run:
        yield run


def test_backend_registered_with_zero_cost():
    assert "copilot-cli" in llm.BACKENDS
    assert llm.BACKENDS["copilot-cli"]["default_model"] == "auto"
    pricing = llm.BACKENDS["copilot-cli"]["pricing"]
    assert pricing == {"input": 0.0, "output": 0.0}
    assert llm.estimate_cost("copilot-cli", 1_000_000, 1_000_000) == 0.0


def test_default_model_precedence(monkeypatch):
    monkeypatch.delenv("GRAPHIFY_COPILOT_CLI_MODEL", raising=False)
    monkeypatch.delenv("COPILOT_MODEL", raising=False)
    assert llm._default_model_for_backend("copilot-cli") == "auto"

    monkeypatch.setenv("COPILOT_MODEL", "gpt-5-mini")
    assert llm._default_model_for_backend("copilot-cli") == "gpt-5-mini"

    monkeypatch.setenv("GRAPHIFY_COPILOT_CLI_MODEL", "claude-sonnet-4.6")
    assert llm._default_model_for_backend("copilot-cli") == "claude-sonnet-4.6"


def test_returns_parsed_graph_and_estimated_usage(fake_copilot):
    result = llm._call_copilot_cli("source", model="auto")
    assert result["nodes"][0]["id"] == "policy"
    assert result["model"] == "auto"
    assert result["finish_reason"] == "stop"
    assert result["input_tokens"] > 0
    assert result["output_tokens"] > 0


def test_large_prompt_is_piped_over_stdin_not_argv(fake_copilot):
    llm._call_copilot_cli("UNIQUE_SOURCE_MARKER", model="auto")
    argv = fake_copilot.call_args.args[0]
    sent = fake_copilot.call_args.kwargs["input"]

    assert "-p" not in argv
    assert "--prompt" not in " ".join(argv)
    assert "UNIQUE_SOURCE_MARKER" not in " ".join(argv)
    assert "UNIQUE_SOURCE_MARKER" in sent
    assert "graphify semantic extraction agent" in sent
    assert "output ONLY the JSON object" in sent
    assert "untrusted_source" in sent


def test_model_and_non_agentic_hardening_flags_are_forwarded(fake_copilot):
    llm._call_copilot_cli("source", model="gpt-5-mini")
    argv = fake_copilot.call_args.args[0]

    assert "-s" in argv
    assert "--model=gpt-5-mini" in argv
    for flag in (
        "--no-color",
        "--no-custom-instructions",
        "--no-ask-user",
        "--no-auto-update",
        "--no-bash-env",
        "--no-experimental",
        "--disable-builtin-mcps",
        "--no-remote-export",
    ):
        assert flag in argv
    assert "--deny-tool=memory,read,shell,url,write" in argv


def test_child_environment_preserves_enterprise_host_and_disables_agent_features(
    monkeypatch, fake_copilot
):
    monkeypatch.setenv("COPILOT_GH_HOST", "example.ghe.com")
    llm._call_copilot_cli("source", model="auto")
    env = fake_copilot.call_args.kwargs["env"]

    assert env["COPILOT_GH_HOST"] == "example.ghe.com"
    assert env["COPILOT_MODEL"] == "auto"
    assert env["COPILOT_ALLOW_ALL"] == "false"
    assert env["COPILOT_MCP_TOOL_CACHE"] == "false"
    assert env["GITHUB_COPILOT_PROMPT_MODE_EXTENSIONS"] == "false"
    assert env["GITHUB_COPILOT_PROMPT_MODE_REPO_HOOKS"] == "false"
    assert env["GITHUB_COPILOT_PROMPT_MODE_WORKSPACE_MCP"] == "false"


def test_runs_from_ephemeral_empty_working_directory(fake_copilot):
    llm._call_copilot_cli("source", model="auto")
    cwd = Path(fake_copilot.call_args.kwargs["cwd"])
    assert cwd.name.startswith("graphify-copilot-")
    assert not cwd.exists(), "temporary working directory should be cleaned up"


def test_optional_flags_are_omitted_for_older_cli(monkeypatch):
    completed = MagicMock(returncode=0, stdout=_RESPONSE, stderr="")
    monkeypatch.setattr(llm, "_copilot_cli_help", lambda _cmd: "legacy help")
    with patch("shutil.which", return_value="/fake/bin/copilot"), patch(
        "subprocess.run", return_value=completed
    ) as run:
        llm._call_copilot_cli("source", model="gpt-5-mini")

    argv = run.call_args.args[0]
    assert argv == ["/fake/bin/copilot", "-s"]
    # Model selection still works through the official COPILOT_MODEL fallback.
    assert run.call_args.kwargs["env"]["COPILOT_MODEL"] == "gpt-5-mini"


def test_capability_detection_does_not_confuse_remote_option_prefixes():
    assert llm._copilot_cli_supports("--no-remote-export", "--no-remote-export")
    assert not llm._copilot_cli_supports("--no-remote-export", "--no-remote")
    assert llm._copilot_cli_supports("--model=MODEL", "--model")


def test_remote_feature_rejection_retries_without_optional_flag(monkeypatch, capsys):
    rejected = MagicMock(
        returncode=2,
        stdout="",
        stderr="Remote sessions feature is not available for this account",
    )
    completed = MagicMock(returncode=0, stdout=_RESPONSE, stderr="")
    monkeypatch.setattr(llm, "_copilot_cli_help", lambda _cmd: _HELP)
    with patch("shutil.which", return_value="/fake/bin/copilot"), patch(
        "subprocess.run", side_effect=[rejected, completed]
    ) as run:
        result = llm._call_copilot_cli("source", model="auto")

    assert result["nodes"][0]["id"] == "policy"
    assert "--no-remote-export" in run.call_args_list[0].args[0]
    assert "--no-remote-export" not in run.call_args_list[1].args[0]
    assert "retrying without" in capsys.readouterr().err


def test_malformed_output_is_dropped_and_marked_for_retry(monkeypatch):
    completed = MagicMock(returncode=0, stdout="not json", stderr="")
    monkeypatch.setattr(llm, "_copilot_cli_help", lambda _cmd: _HELP)
    with patch("shutil.which", return_value="/fake/bin/copilot"), patch(
        "subprocess.run", return_value=completed
    ):
        result = llm._call_copilot_cli("source", model="auto")

    assert result["nodes"] == []
    assert result["edges"] == []
    assert result["finish_reason"] == "length"


def test_extract_files_direct_dispatches_without_api_key(tmp_path, fake_copilot):
    source = tmp_path / "policy.md"
    source.write_text("# Policy\n\nA policy document.\n", encoding="utf-8")
    result = llm.extract_files_direct(
        files=[source], backend="copilot-cli", root=tmp_path
    )
    assert fake_copilot.called
    assert result["nodes"][0]["source_file"] == "policy.md"


def test_simple_completion_path_uses_copilot_cli(monkeypatch, fake_copilot):
    fake_copilot.return_value.stdout = "compact answer"
    usage = {}
    out = llm._call_llm(
        "Summarize this", backend="copilot-cli", model="auto", usage_out=usage
    )
    assert out == "compact answer"
    assert usage["input"] > 0
    assert usage["output"] > 0


def test_hollow_response_is_marked_as_truncation(monkeypatch):
    completed = MagicMock(returncode=0, stdout="", stderr="")
    monkeypatch.setattr(llm, "_copilot_cli_help", lambda _cmd: _HELP)
    with patch("shutil.which", return_value="/fake/bin/copilot"), patch(
        "subprocess.run", return_value=completed
    ):
        result = llm._call_copilot_cli("source", model="auto")
    assert result["finish_reason"] == "length"


def test_nonzero_exit_includes_ghe_login_hint(monkeypatch):
    completed = MagicMock(returncode=1, stdout="", stderr="not authenticated")
    monkeypatch.setenv("COPILOT_GH_HOST", "example.ghe.com")
    monkeypatch.setattr(llm, "_copilot_cli_help", lambda _cmd: _HELP)
    with patch("shutil.which", return_value="/fake/bin/copilot"), patch(
        "subprocess.run", return_value=completed
    ):
        with pytest.raises(
            RuntimeError,
            match=r"copilot login --host https://example\.ghe\.com",
        ):
            llm._call_copilot_cli("source", model="auto")


def test_timeout_has_actionable_graphify_guidance(monkeypatch):
    monkeypatch.setattr(llm, "_copilot_cli_help", lambda _cmd: _HELP)
    with patch("shutil.which", return_value="/fake/bin/copilot"), patch(
        "subprocess.run",
        side_effect=subprocess.TimeoutExpired("copilot", 120),
    ):
        with pytest.raises(RuntimeError, match="GRAPHIFY_API_TIMEOUT"):
            llm._call_copilot_cli("source", model="auto")


def test_execution_oserror_has_resolved_command_context(monkeypatch):
    monkeypatch.setattr(llm, "_copilot_cli_help", lambda _cmd: _HELP)
    with patch("shutil.which", return_value="/fake/bin/copilot"), patch(
        "subprocess.run",
        side_effect=OSError("executable disappeared"),
    ):
        with pytest.raises(RuntimeError, match="/fake/bin/copilot"):
            llm._call_copilot_cli("source", model="auto")


def test_missing_cli_has_install_and_ghe_auth_guidance():
    with patch("shutil.which", return_value=None):
        with pytest.raises(RuntimeError, match="GitHub Copilot CLI not found") as exc:
            llm._call_copilot_cli("source", model="auto")
    assert "copilot login --host" in str(exc.value)


def test_windows_prefers_cmd_shim(monkeypatch):
    completed = MagicMock(returncode=0, stdout=_RESPONSE, stderr="")
    monkeypatch.setattr(llm, "_copilot_cli_help", lambda _cmd: _HELP)

    def fake_which(name):
        return {
            "copilot": r"C:\Users\u\AppData\Roaming\npm\copilot.ps1",
            "copilot.cmd": r"C:\Users\u\AppData\Roaming\npm\copilot.cmd",
        }.get(name)

    with patch("platform.system", return_value="Windows"), patch(
        "shutil.which", side_effect=fake_which
    ), patch("subprocess.run", return_value=completed) as run:
        llm._call_copilot_cli("source", model="auto")

    assert run.call_args.args[0][0] == r"C:\Users\u\AppData\Roaming\npm\copilot.cmd"


def test_help_probe_is_cached(monkeypatch):
    llm._COPILOT_CLI_HELP.clear()
    completed = MagicMock(returncode=0, stdout="--model=MODEL", stderr="")
    with patch("subprocess.run", return_value=completed) as run:
        assert "--model" in llm._copilot_cli_help("/fake/copilot")
        assert "--model" in llm._copilot_cli_help("/fake/copilot")
    assert run.call_count == 1


def test_detect_backend_does_not_auto_select_copilot(monkeypatch):
    """A binary on PATH is not consent to send corpus data to Copilot."""
    for key in (
        "GEMINI_API_KEY",
        "GOOGLE_API_KEY",
        "MOONSHOT_API_KEY",
        "ANTHROPIC_API_KEY",
        "OPENAI_API_KEY",
        "DEEPSEEK_API_KEY",
        "AZURE_OPENAI_API_KEY",
        "AZURE_OPENAI_ENDPOINT",
        "AWS_PROFILE",
        "AWS_REGION",
        "AWS_DEFAULT_REGION",
        "OLLAMA_BASE_URL",
        "OLLAMA_HOST",
    ):
        monkeypatch.delenv(key, raising=False)
    with patch("shutil.which", return_value="/fake/bin/copilot"):
        assert llm.detect_backend() is None


def _ok_graph(nodes=None):
    return {
        "nodes": nodes or [],
        "edges": [],
        "hyperedges": [],
        "input_tokens": 1,
        "output_tokens": 1,
        "model": "auto",
        "finish_reason": "stop",
    }


def test_extract_corpus_parallel_copilot_runs_serially(tmp_path, monkeypatch):
    files = [tmp_path / f"f{i}.md" for i in range(6)]
    for source in files:
        source.write_text("hello", encoding="utf-8")

    def fake_extract(chunk, *_, **__):
        return _ok_graph(nodes=[{"id": source.stem} for source in chunk])

    monkeypatch.delenv("GRAPHIFY_COPILOT_CLI_PARALLEL", raising=False)
    with patch("graphify.llm.extract_files_direct", side_effect=fake_extract), patch(
        "graphify.llm.ThreadPoolExecutor"
    ) as pool:
        result = llm.extract_corpus_parallel(
            files,
            backend="copilot-cli",
            model="auto",
            root=tmp_path,
            token_budget=None,
            chunk_size=2,
            max_concurrency=4,
        )

    pool.assert_not_called()
    assert len(result["nodes"]) == 6


def test_extract_corpus_parallel_copilot_parallel_opt_in(tmp_path, monkeypatch):
    files = [tmp_path / f"f{i}.md" for i in range(4)]
    for source in files:
        source.write_text("hello", encoding="utf-8")

    monkeypatch.setenv("GRAPHIFY_COPILOT_CLI_PARALLEL", "1")
    with patch("graphify.llm.extract_files_direct", return_value=_ok_graph()), patch(
        "graphify.llm.ThreadPoolExecutor"
    ) as pool:
        pool.return_value.__enter__ = lambda value: value
        pool.return_value.__exit__ = lambda _value, *_args: False
        pool.return_value.submit = lambda fn, *args, **kwargs: type(
            "Future", (), {"result": lambda self: fn(*args, **kwargs)}
        )()
        try:
            llm.extract_corpus_parallel(
                files,
                backend="copilot-cli",
                model="auto",
                root=tmp_path,
                token_budget=None,
                chunk_size=2,
                max_concurrency=4,
            )
        except Exception:
            # The minimal future mock only needs to prove the pool path was selected.
            pass

    pool.assert_called()
