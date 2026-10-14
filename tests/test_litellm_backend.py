"""The optional `litellm` backend: any LiteLLM model string, no key of its own.

Every test here runs without network access. LiteLLM is replaced by a fake
module (or, where the real package is installed, driven with its own
`mock_response=`), and an autouse fixture refuses any non-loopback socket
connect so a regression cannot reach a real provider.
"""
from __future__ import annotations

import socket
import sys
import types
from pathlib import Path
from types import SimpleNamespace

import pytest

import graphify.__main__ as mainmod
from graphify import llm

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10
    import tomli as tomllib  # type: ignore[no-redef]

PYPROJECT = Path(__file__).resolve().parent.parent / "pyproject.toml"
_NODE_JSON = '{"nodes": [{"id": "a", "label": "A"}], "edges": [], "hyperedges": []}'
_MODEL = "bedrock/anthropic.claude-3-5-sonnet-20241022-v2:0"


@pytest.fixture(autouse=True)
def _no_outbound_network(monkeypatch):
    real_connect = socket.socket.connect

    def _guard(self, address, *args, **kwargs):
        host = address[0] if isinstance(address, tuple) else address
        if isinstance(host, str) and host not in ("localhost", "127.0.0.1", "::1"):
            raise AssertionError(f"test tried to open a network connection to {host!r}")
        return real_connect(self, address, *args, **kwargs)

    monkeypatch.setattr(socket.socket, "connect", _guard)


@pytest.fixture(autouse=True)
def _clean_litellm_env(monkeypatch):
    for key in ("GRAPHIFY_LITELLM_MODEL", "GRAPHIFY_LLM_TEMPERATURE", "GRAPHIFY_MAX_RETRIES",
                "GRAPHIFY_API_TIMEOUT", "GRAPHIFY_MAX_OUTPUT_TOKENS"):
        monkeypatch.delenv(key, raising=False)


def _fake_litellm(monkeypatch, *, content=_NODE_JSON, usage=None, finish_reason="stop"):
    """Install a stand-in `litellm` module and return the list of recorded calls."""
    calls: list[dict] = []
    if usage is None:
        usage = SimpleNamespace(prompt_tokens=11, completion_tokens=7)

    def completion(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=content), finish_reason=finish_reason)],
            usage=usage,
        )

    mod = types.ModuleType("litellm")
    setattr(mod, "completion", completion)
    monkeypatch.setitem(sys.modules, "litellm", mod)
    return calls


def _extras():
    return tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))["project"]["optional-dependencies"]


# ── packaging ────────────────────────────────────────────────────────────────

def test_litellm_extra_excludes_the_compromised_releases():
    deps = _extras()["litellm"]
    assert deps == ["litellm>=1.83.7,<2"]


def test_litellm_in_all_extra():
    assert "litellm>=1.83.7,<2" in _extras()["all"]


# ── registration and selection ───────────────────────────────────────────────

def test_litellm_backend_is_registered_without_an_api_key():
    cfg = llm.BACKENDS["litellm"]
    assert llm._backend_env_keys("litellm") == []
    assert cfg["model_env_key"] == "GRAPHIFY_LITELLM_MODEL"
    assert llm.estimate_cost("litellm", 1000, 1000) == 0.0


def test_model_comes_from_the_environment(monkeypatch):
    assert llm._default_model_for_backend("litellm") == ""
    monkeypatch.setenv("GRAPHIFY_LITELLM_MODEL", "vertex_ai/gemini-2.0-flash")
    assert llm._default_model_for_backend("litellm") == "vertex_ai/gemini-2.0-flash"


def test_detect_backend_selects_litellm_only_when_a_model_is_set(monkeypatch):
    assert llm.detect_backend() != "litellm"
    monkeypatch.setenv("GRAPHIFY_LITELLM_MODEL", "  ")
    assert llm.detect_backend() != "litellm"
    monkeypatch.setenv("GRAPHIFY_LITELLM_MODEL", "ollama/llama3.1")
    assert llm.detect_backend() == "litellm"


def test_detect_backend_prefers_the_explicit_litellm_model_over_an_ambient_key(monkeypatch):
    """An unrelated key in the environment must not redirect the corpus away from
    the provider the user chose with GRAPHIFY_LITELLM_MODEL."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-not-real")
    monkeypatch.setenv("GRAPHIFY_LITELLM_MODEL", _MODEL)
    assert llm.detect_backend() == "litellm"
    monkeypatch.delenv("GRAPHIFY_LITELLM_MODEL")
    assert llm.detect_backend() == "claude"


def test_litellm_model_env_is_part_of_the_isolated_detection_env():
    assert "GRAPHIFY_LITELLM_MODEL" in llm.backend_detection_env_vars()


# ── extraction call ──────────────────────────────────────────────────────────

def test_call_litellm_sends_system_and_user_messages_and_parses_the_reply(monkeypatch):
    calls = _fake_litellm(monkeypatch)
    result = llm._call_litellm(_MODEL, "FILE CONTENTS", max_tokens=1234)

    assert len(calls) == 1
    sent = calls[0]
    assert sent["model"] == _MODEL
    assert [m["role"] for m in sent["messages"]] == ["system", "user"]
    assert sent["messages"][1]["content"] == "FILE CONTENTS"
    assert sent["max_tokens"] == 1234
    assert sent["drop_params"] is True
    assert sent["temperature"] == 0
    assert sent["timeout"] == llm._resolve_api_timeout()
    assert sent["num_retries"] == llm._resolve_max_retries()

    assert [n["id"] for n in result["nodes"]] == ["a"]
    assert result["input_tokens"] == 11
    assert result["output_tokens"] == 7
    assert result["model"] == _MODEL
    assert result["finish_reason"] == "stop"


def test_call_litellm_honours_the_graphify_knobs(monkeypatch):
    calls = _fake_litellm(monkeypatch)
    monkeypatch.setenv("GRAPHIFY_API_TIMEOUT", "42")
    monkeypatch.setenv("GRAPHIFY_MAX_RETRIES", "1")
    monkeypatch.setenv("GRAPHIFY_LLM_TEMPERATURE", "none")
    llm._call_litellm(_MODEL, "x")
    assert calls[0]["timeout"] == 42.0
    assert calls[0]["num_retries"] == 1
    assert "temperature" not in calls[0]


def test_call_litellm_tolerates_null_usage(monkeypatch):
    _fake_litellm(monkeypatch, usage=SimpleNamespace(prompt_tokens=None, completion_tokens=None))
    result = llm._call_litellm(_MODEL, "x")
    assert result["input_tokens"] == 0
    assert result["output_tokens"] == 0


def test_call_litellm_tolerates_missing_usage(monkeypatch):
    _fake_litellm(monkeypatch)
    monkeypatch.setattr(
        sys.modules["litellm"], "completion",
        lambda **kw: SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=_NODE_JSON), finish_reason="stop")],
            usage=None,
        ),
    )
    result = llm._call_litellm(_MODEL, "x")
    assert (result["input_tokens"], result["output_tokens"]) == (0, 0)


def test_call_litellm_marks_an_empty_reply_hollow(monkeypatch):
    _fake_litellm(monkeypatch, content="")
    result = llm._call_litellm(_MODEL, "x")
    assert result["finish_reason"] == "hollow"


def test_call_litellm_rejects_an_empty_choice_list(monkeypatch):
    _fake_litellm(monkeypatch)
    monkeypatch.setattr(
        sys.modules["litellm"], "completion",
        lambda **kw: SimpleNamespace(choices=[], usage=None),
    )
    with pytest.raises(ValueError, match="empty or filtered"):
        llm._call_litellm(_MODEL, "x")


def test_missing_model_is_a_clear_error(monkeypatch):
    calls = _fake_litellm(monkeypatch)
    with pytest.raises(ValueError, match="GRAPHIFY_LITELLM_MODEL"):
        llm._call_litellm("", "x")
    assert calls == []


def test_missing_package_points_at_the_extra(monkeypatch):
    monkeypatch.setitem(sys.modules, "litellm", None)  # makes `import litellm` raise ImportError
    with pytest.raises(ImportError) as exc_info:
        llm._call_litellm(_MODEL, "x")
    assert "graphifyy[litellm]" in str(exc_info.value)


def test_real_litellm_response_shape_with_mock_response(monkeypatch):
    """Where the package is installed, drive the real `litellm.completion` with its
    own `mock_response=` so the parsing is checked against the real response type."""
    litellm = pytest.importorskip("litellm")
    real_completion = litellm.completion

    def _mocked(**kwargs):
        return real_completion(mock_response=_NODE_JSON, **kwargs)

    monkeypatch.setattr(litellm, "completion", _mocked)
    result = llm._call_litellm(_MODEL, "hello")
    assert [n["id"] for n in result["nodes"]] == ["a"]
    assert result["model"] == _MODEL
    assert isinstance(result["input_tokens"], int)
    assert isinstance(result["output_tokens"], int)


# ── dispatch ─────────────────────────────────────────────────────────────────

def test_extract_files_direct_routes_to_litellm_with_no_api_key(monkeypatch, tmp_path):
    calls = _fake_litellm(monkeypatch)
    doc = tmp_path / "notes.md"
    doc.write_text("# Notes\nThe entry point.\n", encoding="utf-8")

    result = llm.extract_files_direct([doc], backend="litellm", model=_MODEL, root=tmp_path)

    assert len(calls) == 1
    assert calls[0]["model"] == _MODEL
    assert "The entry point." in calls[0]["messages"][1]["content"]
    assert result["nodes"]


def test_extract_files_direct_reads_the_model_from_the_environment(monkeypatch, tmp_path):
    calls = _fake_litellm(monkeypatch)
    monkeypatch.setenv("GRAPHIFY_LITELLM_MODEL", "azure/my-deployment")
    doc = tmp_path / "notes.md"
    doc.write_text("# Notes\n", encoding="utf-8")

    llm.extract_files_direct([doc], backend="litellm", root=tmp_path)

    assert calls[0]["model"] == "azure/my-deployment"


def test_extract_files_direct_autodetects_litellm_from_the_model_env(monkeypatch, tmp_path):
    calls = _fake_litellm(monkeypatch)
    monkeypatch.setenv("GRAPHIFY_LITELLM_MODEL", "ollama/llama3.1")
    doc = tmp_path / "notes.md"
    doc.write_text("# Notes\n", encoding="utf-8")

    llm.extract_files_direct([doc], root=tmp_path)

    assert calls[0]["model"] == "ollama/llama3.1"


def test_call_llm_plain_text_path_records_usage(monkeypatch):
    calls = _fake_litellm(monkeypatch, content="Auth and Sessions")
    usage: dict = {}

    text = llm._call_llm("name this community", backend="litellm", model=_MODEL, usage_out=usage)

    assert text == "Auth and Sessions"
    assert calls[0]["messages"] == [{"role": "user", "content": "name this community"}]
    assert usage == {"input": 11, "output": 7}


def test_litellm_does_not_disturb_existing_backends():
    for name in ("gemini", "kimi", "claude", "openai", "deepseek", "azure", "bedrock", "ollama", "claude-cli"):
        assert name in llm.BACKENDS


# ── CLI ──────────────────────────────────────────────────────────────────────

def _corpus_with_a_doc(tmp_path):
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "main.go").write_text("package main\nfunc main() {}\n")
    (tmp_path / "README.md").write_text("# Notes\nThe main function entry point.\n")
    return tmp_path


def test_cli_litellm_without_a_model_exits_with_guidance(monkeypatch, tmp_path, capsys):
    corpus = _corpus_with_a_doc(tmp_path / "corpus")
    out_dir = tmp_path / "out"
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)
    monkeypatch.setattr(
        mainmod.sys, "argv",
        ["graphify", "extract", str(corpus), "--out", str(out_dir), "--backend", "litellm"],
    )

    with pytest.raises(SystemExit) as exc_info:
        mainmod.main()

    assert exc_info.value.code == 1
    err = capsys.readouterr().err
    assert "GRAPHIFY_LITELLM_MODEL" in err
    assert "--model" in err


def test_cli_litellm_with_a_model_reaches_the_backend(monkeypatch, tmp_path):
    calls = _fake_litellm(monkeypatch)
    corpus = _corpus_with_a_doc(tmp_path / "corpus")
    out_dir = tmp_path / "out"
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)
    monkeypatch.setattr(
        mainmod.sys, "argv",
        ["graphify", "extract", str(corpus), "--out", str(out_dir),
         "--backend", "litellm", "--model", _MODEL, "--no-cluster"],
    )

    try:
        mainmod.main()
    except SystemExit as exc:
        assert exc.code in (None, 0), f"unexpected exit code {exc.code}"

    assert calls, "the litellm backend was never called"
    assert all(c["model"] == _MODEL for c in calls)
    assert (out_dir / "graphify-out" / "graph.json").exists()
