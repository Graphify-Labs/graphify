"""Tests for the Ollama backend additions in graphify/llm.py."""
from __future__ import annotations

import pytest

from graphify.llm import detect_backend, BACKENDS, _validate_ollama_base_url


@pytest.mark.parametrize("url", [
    "http://169.254.169.254/v1",
    "http://169.254.1.5:11434/v1",
    "http://metadata.google.internal/v1",
    "http://0.0.0.0:11434/v1",
])
def test_ollama_blocks_link_local_and_metadata(url):
    """Link-local / cloud-metadata Ollama targets fail closed (F3)."""
    with pytest.raises(ValueError):
        _validate_ollama_base_url(url)


def test_ollama_loopback_and_lan_do_not_raise(capsys):
    """Loopback is silent; a general LAN host warns but is allowed (F3)."""
    _validate_ollama_base_url("http://localhost:11434/v1")
    assert capsys.readouterr().err == ""
    _validate_ollama_base_url("http://192.168.1.50:11434/v1")  # LAN: warn, not raise
    assert "non-loopback" in capsys.readouterr().err


def test_ollama_alias_resolving_to_link_local_blocked(monkeypatch):
    """A hostname that RESOLVES to a link-local IP is blocked, not just literals (F3)."""
    from graphify import llm

    def fake_getaddrinfo(host, *a, **k):
        return [(2, 1, 6, "", ("169.254.169.254", 0))]  # alias -> metadata IP

    monkeypatch.setattr("socket.getaddrinfo", fake_getaddrinfo)
    with pytest.raises(ValueError):
        llm._validate_ollama_base_url("http://innocent-looking-host/v1")


def test_ollama_warn_false_still_hard_blocks_but_stays_quiet(capsys):
    """warn=False suppresses the LAN warning but never the metadata hard-block (F3)."""
    # LAN host with warn=False: allowed, and no warning emitted (early-gate use).
    _validate_ollama_base_url("http://192.168.1.50:11434/v1", warn=False)
    assert capsys.readouterr().err == ""
    # metadata host with warn=False: still raises.
    with pytest.raises(ValueError):
        _validate_ollama_base_url("http://169.254.169.254/v1", warn=False)


def test_ollama_in_backends():
    assert "ollama" in BACKENDS
    assert BACKENDS["ollama"]["pricing"]["input"] == 0.0
    assert BACKENDS["ollama"]["pricing"]["output"] == 0.0
    assert "max_tokens" in BACKENDS["ollama"]


def test_minimax_fallback_disabled_when_openai_sdk_missing(monkeypatch, capsys):
    from graphify import llm

    monkeypatch.setenv("MINIMAX_API_KEY", "test-key")
    monkeypatch.setattr(llm, "_module_available", lambda name: name != "openai")
    llm._BACKEND_UNAVAILABLE_WARNED.clear()

    assert llm._automatic_fallback_backend("ollama", allow=True) is None
    err = capsys.readouterr().err
    assert "minimax fallback disabled" in err.lower()
    assert "openai" in err.lower()


def test_failed_minimax_spill_retries_locally_and_disables_spill(monkeypatch, tmp_path, capsys):
    from graphify import llm

    for key in (
        "GRAPHIFY_OLLAMA_BALANCE",
        "GRAPHIFY_OLLAMA_DAYTIME_FILE_LIMIT",
        "GRAPHIFY_OLLAMA_MINIMAX_MAX_FRACTION",
    ):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("GRAPHIFY_OLLAMA_BALANCE", "remote")
    monkeypatch.setenv("GRAPHIFY_OLLAMA_DAYTIME_FILE_LIMIT", "1")
    monkeypatch.setenv("GRAPHIFY_OLLAMA_MINIMAX_MAX_FRACTION", "1")
    monkeypatch.setenv("MINIMAX_API_KEY", "test-key")
    monkeypatch.setattr(llm, "_backend_runtime_unavailable_reason", lambda backend: None)

    files = []
    for idx in range(2):
        path = tmp_path / f"f{idx}.md"
        path.write_text(f"file {idx}", encoding="utf-8")
        files.append(path)

    calls = []

    def fake_extract(chunk, **kwargs):
        backend = kwargs["backend"]
        calls.append(backend)
        if backend == "minimax":
            raise ImportError("missing openai")
        return {
            "nodes": [{"id": f"n{len(calls)}", "label": "N", "file_type": "document", "source_file": str(chunk[0])}],
            "edges": [],
            "hyperedges": [],
            "input_tokens": 1,
            "output_tokens": 1,
        }

    monkeypatch.setattr(llm, "_extract_with_adaptive_retry", fake_extract)

    result = llm.extract_corpus_parallel(
        files,
        backend="ollama",
        token_budget=None,
        chunk_size=1,
        max_concurrency=1,
        allow_minimax_fallback=True,
    )

    assert calls == ["minimax", "ollama", "ollama"]
    assert result["failed_chunks"] == 0
    assert result["minimax_chunks"] == 0
    assert len(result["nodes"]) == 2
    assert "disabling remote spill" in capsys.readouterr().err

def _clear_non_ollama_keys(monkeypatch):
    for key in (
        "MINIMAX_API_KEY", "GRAPHIFY_MINIMAX_API_KEY",
        "GEMINI_API_KEY", "GOOGLE_API_KEY", "MOONSHOT_API_KEY",
        "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "DEEPSEEK_API_KEY",
        "AWS_PROFILE", "AWS_REGION", "AWS_DEFAULT_REGION",
        "OLLAMA_BASE_URL", "OLLAMA_MODEL", "GRAPHIFY_OLLAMA_MODEL",
        "GRAPHIFY_DISABLE_OLLAMA_PRIMARY",
    ):
        monkeypatch.delenv(key, raising=False)



def test_detect_backend_ollama(monkeypatch):
    _clear_non_ollama_keys(monkeypatch)
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")
    assert detect_backend() == "ollama"


def test_detect_backend_ollama_beats_kimi(monkeypatch):
    _clear_non_ollama_keys(monkeypatch)
    monkeypatch.setenv("MOONSHOT_API_KEY", "test-key")
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")
    assert detect_backend() == "ollama"


def test_detect_backend_ollama_beats_claude(monkeypatch):
    _clear_non_ollama_keys(monkeypatch)
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    assert detect_backend() == "ollama"


def test_detect_backend_none_when_ollama_primary_disabled(monkeypatch):
    _clear_non_ollama_keys(monkeypatch)
    monkeypatch.setenv("GRAPHIFY_DISABLE_OLLAMA_PRIMARY", "1")
    assert detect_backend() is None


def test_ollama_native_backend_does_not_require_api_key(monkeypatch):
    """extract_files_direct with backend=ollama and no OLLAMA_API_KEY should not raise."""
    monkeypatch.delenv("OLLAMA_API_KEY", raising=False)
    from unittest.mock import patch
    from pathlib import Path
    import tempfile

    fake_result = {
        "nodes": [],
        "edges": [],
        "hyperedges": [],
        "input_tokens": 0,
        "output_tokens": 10,
        "finish_reason": "stop",
    }
    with patch("graphify.llm._call_ollama_native", return_value=fake_result) as mock_call:
        from graphify.llm import extract_files_direct
        with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False) as f:
            f.write("x = 1\n")
            tmp = Path(f.name)
        try:
            extract_files_direct([tmp], backend="ollama", root=tmp.parent)
            assert mock_call.called
        finally:
            tmp.unlink(missing_ok=True)
