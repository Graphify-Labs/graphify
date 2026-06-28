"""Tests for direct semantic-extraction backend selection."""

from pathlib import Path
from unittest.mock import patch

import pytest

from graphify import llm


def _clear_backend_env(monkeypatch):
    for env_key in (
        "GEMINI_API_KEY",
        "GOOGLE_API_KEY",
        "MOONSHOT_API_KEY",
        "ANTHROPIC_API_KEY",
        "OPENAI_API_KEY",
        "DEEPSEEK_API_KEY",
        "AZURE_OPENAI_API_KEY",
        "AZURE_OPENAI_ENDPOINT",
    ):
        monkeypatch.delenv(env_key, raising=False)


def test_gemini_accepts_gemini_api_key(monkeypatch):
    _clear_backend_env(monkeypatch)
    monkeypatch.setenv("GEMINI_API_KEY", "gemini-key")

    assert llm.detect_backend() == "gemini"
    assert llm._get_backend_api_key("gemini") == "gemini-key"


def test_gemini_accepts_google_api_key(monkeypatch):
    _clear_backend_env(monkeypatch)
    monkeypatch.setenv("GOOGLE_API_KEY", "google-key")

    assert llm.detect_backend() == "gemini"
    assert llm._get_backend_api_key("gemini") == "google-key"


def test_backend_detection_prefers_gemini(monkeypatch):
    _clear_backend_env(monkeypatch)
    monkeypatch.setenv("OPENAI_API_KEY", "openai-key")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "anthropic-key")
    monkeypatch.setenv("MOONSHOT_API_KEY", "moonshot-key")
    monkeypatch.setenv("GEMINI_API_KEY", "gemini-key")

    assert llm.detect_backend() == "gemini"


def test_openai_backend_detected(monkeypatch):
    _clear_backend_env(monkeypatch)
    monkeypatch.setenv("OPENAI_API_KEY", "openai-key")

    assert llm.detect_backend() == "openai"
    assert llm._get_backend_api_key("openai") == "openai-key"


def test_extract_files_direct_routes_gemini_through_openai_compat(tmp_path, monkeypatch):
    _clear_backend_env(monkeypatch)
    monkeypatch.setenv("GOOGLE_API_KEY", "google-key")
    source = tmp_path / "note.md"
    source.write_text("# Architecture\n\nThe runner emits a snapshot.\n")
    result = {"nodes": [], "edges": [], "hyperedges": [], "input_tokens": 1, "output_tokens": 1}

    with patch("graphify.llm._call_openai_compat", return_value=result) as call:
        assert llm.extract_files_direct([source], backend="gemini", root=tmp_path) is result

    assert call.call_args.args[:3] == (
        "https://generativelanguage.googleapis.com/v1beta/openai/",
        "google-key",
        "gemini-3-flash-preview",
    )
    # Source content is wrapped in an untrusted_source delimiter block (#1210)
    # rather than the old `=== path ===` separator.
    user_msg = call.call_args.args[3]
    assert '<untrusted_source path="note.md" sha256=' in user_msg
    assert "# Architecture\n\nThe runner emits a snapshot." in user_msg
    assert user_msg.rstrip().endswith("</untrusted_source>")
    assert call.call_args.kwargs["temperature"] == 0
    assert call.call_args.kwargs["reasoning_effort"] == "low"
    assert call.call_args.kwargs["max_completion_tokens"] == 16384


@pytest.mark.parametrize(
    "backend, env_key",
    [
        ("ollama", "OLLAMA_API_KEY"),
        ("deepseek", "DEEPSEEK_API_KEY"),
        ("openai", "OPENAI_API_KEY"),
        ("kimi", "MOONSHOT_API_KEY"),
    ],
)
def test_openai_compat_backends_resolve_full_output_cap(tmp_path, monkeypatch, backend, env_key):
    # #1365: these configs define `max_tokens: 16384`, but the dispatch used to
    # read only the `max_completion_tokens` key (which only gemini sets), so the
    # output cap silently fell back to 8192 and truncated deep-mode JSON. The
    # dispatch must resolve their configured 16384.
    _clear_backend_env(monkeypatch)
    monkeypatch.delenv("GRAPHIFY_MAX_OUTPUT_TOKENS", raising=False)
    monkeypatch.setenv(env_key, "test-key")
    source = tmp_path / "note.md"
    source.write_text("# Architecture\n")
    result = {"nodes": [], "edges": [], "hyperedges": [], "input_tokens": 1, "output_tokens": 1}

    with patch("graphify.llm._call_openai_compat", return_value=result) as call:
        llm.extract_files_direct([source], backend=backend, root=tmp_path)

    assert call.call_args.kwargs["max_completion_tokens"] == 16384


def test_gemini_model_can_be_overridden_by_env(tmp_path, monkeypatch):
    _clear_backend_env(monkeypatch)
    monkeypatch.setenv("GOOGLE_API_KEY", "google-key")
    monkeypatch.setenv("GRAPHIFY_GEMINI_MODEL", "gemini-3.1-pro-preview")
    source = tmp_path / "note.md"
    source.write_text("# Architecture\n")
    result = {"nodes": [], "edges": [], "hyperedges": [], "input_tokens": 1, "output_tokens": 1}

    with patch("graphify.llm._call_openai_compat", return_value=result) as call:
        llm.extract_files_direct([source], backend="gemini", root=tmp_path)

    assert call.call_args.args[2] == "gemini-3.1-pro-preview"


def test_missing_gemini_key_names_both_supported_env_vars(monkeypatch):
    _clear_backend_env(monkeypatch)

    with pytest.raises(ValueError) as exc:
        llm.extract_files_direct([Path("missing.md")], backend="gemini")

    assert "GEMINI_API_KEY or GOOGLE_API_KEY" in str(exc.value)


# ---------------------------------------------------------------------------
# #1386: public entry points accept str paths, not just pathlib.Path
# ---------------------------------------------------------------------------


def test_extract_files_direct_accepts_str_paths(tmp_path, monkeypatch):
    _clear_backend_env(monkeypatch)
    monkeypatch.setenv("GOOGLE_API_KEY", "google-key")
    source = tmp_path / "note.md"
    source.write_text("# Architecture\n\nThe runner emits a snapshot.\n")
    result = {"nodes": [], "edges": [], "hyperedges": [], "input_tokens": 1, "output_tokens": 1}

    # str path must not raise AttributeError: 'str' object has no attribute 'suffix'
    with patch("graphify.llm._call_openai_compat", return_value=result):
        assert llm.extract_files_direct([str(source)], backend="gemini", root=tmp_path) is result


def test_extract_corpus_parallel_accepts_str_and_mixed_paths(tmp_path, monkeypatch):
    _clear_backend_env(monkeypatch)
    monkeypatch.setenv("GOOGLE_API_KEY", "google-key")
    f1 = tmp_path / "a.md"
    f1.write_text("# A\n\nNode one.\n")
    f2 = tmp_path / "b.md"
    f2.write_text("# B\n\nNode two.\n")
    result = {"nodes": [], "edges": [], "hyperedges": [], "input_tokens": 1, "output_tokens": 1}

    with patch("graphify.llm._call_openai_compat", return_value=result):
        # all-str, all-Path, and mixed must each pack + run without AttributeError
        for files in ([str(f1), str(f2)], [f1, f2], [str(f1), f2]):
            merged = llm.extract_corpus_parallel(
                files, backend="gemini", root=tmp_path, max_concurrency=1
            )
            assert merged["failed_chunks"] == 0


def test_corpus_parallel_oversized_markdown_does_not_crash_on_fileslice(tmp_path, monkeypatch):
    # #1397/#1399 regression: a Markdown file large enough to be sliced into
    # FileSlice units must not crash extract_files_direct's Path() coercion
    # (#1386). The earlier str-path tests used tiny files, so slicing never ran.
    from graphify.llm import _FILE_CHAR_CAP
    _clear_backend_env(monkeypatch)
    monkeypatch.setenv("GOOGLE_API_KEY", "google-key")
    big = tmp_path / "big.md"
    big.write_text(("# Section\n\n" + "lorem ipsum dolor sit amet " * 60 + "\n\n") * 30)
    assert len(big.read_text()) > _FILE_CHAR_CAP  # guarantees slicing kicks in
    result = {"nodes": [], "edges": [], "hyperedges": [], "input_tokens": 1, "output_tokens": 1}

    with patch("graphify.llm._call_openai_compat", return_value=result):
        # both a str path and a FileSlice unit must flow through without TypeError
        merged = llm.extract_corpus_parallel(
            [str(big)], backend="gemini", root=tmp_path, max_concurrency=1
        )
    assert merged["failed_chunks"] == 0  # no chunk raised Path(FileSlice) TypeError


def test_str_path_entry_points_handle_edge_cases(tmp_path, monkeypatch):
    _clear_backend_env(monkeypatch)
    monkeypatch.setenv("GOOGLE_API_KEY", "google-key")
    result = {"nodes": [], "edges": [], "hyperedges": [], "input_tokens": 1, "output_tokens": 1}

    with patch("graphify.llm._call_openai_compat", return_value=result):
        # empty list: no chunks, nothing to extract, no crash
        empty = llm.extract_corpus_parallel([], backend="gemini", root=tmp_path)
        assert empty["nodes"] == [] and empty["failed_chunks"] == 0
        # a Path subclass is still a Path and must pass through unchanged
        class _SubPath(type(Path())):  # concrete OS-specific Path subclass
            pass
        sub = _SubPath(tmp_path / "c.md")
        sub.write_text("# C\n\nNode.\n")
        assert llm.extract_files_direct([sub], backend="gemini", root=tmp_path) is result


# ---------------------------------------------------------------------------
# Adaptive retry: context-window overflow recovery
# ---------------------------------------------------------------------------


def _ok(nodes=None, edges=None, model="m"):
    return {
        "nodes": nodes or [],
        "edges": edges or [],
        "hyperedges": [],
        "input_tokens": 1,
        "output_tokens": 1,
        "model": model,
        "finish_reason": "stop",
    }


def test_looks_like_context_exceeded_matches_common_messages():
    msgs = [
        "Error code: 400 - {'error': 'Context size has been exceeded.'}",
        "n_keep: 22374 >= n_ctx: 4096",
        "context_length_exceeded: This model's maximum context length is 8192 tokens",
        "exceeds the available context size",
        "The prompt is too long for this model.",
    ]
    for m in msgs:
        assert llm._looks_like_context_exceeded(RuntimeError(m)), m


def test_looks_like_context_exceeded_ignores_unrelated_errors():
    for m in ["timeout", "rate limit", "401 unauthorized", "connection refused"]:
        assert not llm._looks_like_context_exceeded(RuntimeError(m)), m


def test_adaptive_retry_splits_on_context_exceeded(tmp_path):
    files = [tmp_path / f"f{i}.md" for i in range(4)]
    for f in files:
        f.write_text("hello")

    calls = {"n": 0}

    def fake_extract(chunk, *_, **__):
        calls["n"] += 1
        # First call (whole chunk) fails with context overflow; recursive
        # halves succeed. This is the same shape LM Studio / vLLM / OpenAI
        # produce when a chunk overflows the model's context window.
        if len(chunk) == 4:
            raise RuntimeError("Error 400: Context size has been exceeded.")
        return _ok(nodes=[{"id": f.stem} for f in chunk])

    with patch("graphify.llm.extract_files_direct", side_effect=fake_extract):
        result = llm._extract_with_adaptive_retry(
            files, backend="kimi", api_key="k", model="m", root=tmp_path, max_depth=3
        )

    assert len(result["nodes"]) == 4
    assert calls["n"] == 3  # 1 failure + 2 halves


def test_adaptive_retry_gives_up_on_single_file_overflow(tmp_path):
    f = tmp_path / "huge.md"
    f.write_text("x")

    def fake_extract(*_, **__):
        raise RuntimeError("context_length_exceeded")

    with patch("graphify.llm.extract_files_direct", side_effect=fake_extract):
        result = llm._extract_with_adaptive_retry(
            [f], backend="kimi", api_key="k", model="m", root=tmp_path, max_depth=3
        )

    # Single-file overflow returns an empty fragment instead of raising — the
    # caller can keep going on the rest of the corpus.
    assert result["nodes"] == []
    assert result["edges"] == []
    assert result["finish_reason"] == "stop"


def test_adaptive_retry_re_raises_unrelated_errors(tmp_path):
    f = tmp_path / "f.md"
    f.write_text("x")

    def fake_extract(*_, **__):
        raise RuntimeError("rate limit hit")

    with patch("graphify.llm.extract_files_direct", side_effect=fake_extract):
        with pytest.raises(RuntimeError, match="rate limit"):
            llm._extract_with_adaptive_retry(
                [f], backend="kimi", api_key="k", model="m", root=tmp_path, max_depth=3
            )


# ---------------------------------------------------------------------------
# Hollow-response detection: empty / null / unparseable content from a
# successful HTTP call must route into the same bisection path as a true
# `finish_reason="length"` truncation, not be silently dropped.
# ---------------------------------------------------------------------------


def test_response_is_hollow_flags_empty_string():
    assert llm._response_is_hollow("", {"nodes": [], "edges": [], "hyperedges": []})


def test_response_is_hollow_flags_none_content():
    assert llm._response_is_hollow(None, {"nodes": [], "edges": [], "hyperedges": []})


def test_response_is_hollow_flags_whitespace_only():
    assert llm._response_is_hollow("   \n\t  ", {"nodes": [], "edges": [], "hyperedges": []})


def test_response_is_hollow_flags_parsed_but_no_nodes_or_edges():
    # Content was non-empty (e.g. model said `{"sorry": "I cannot"}` or returned
    # `{}` literally) but the parsed result has nothing usable.
    assert llm._response_is_hollow('{"sorry": "I cannot"}', {})
    assert llm._response_is_hollow("{}", {"nodes": [], "edges": [], "hyperedges": []})


def test_response_is_hollow_accepts_real_extraction():
    parsed = {"nodes": [{"id": "x"}], "edges": [], "hyperedges": []}
    assert not llm._response_is_hollow('{"nodes":[{"id":"x"}]}', parsed)
    parsed = {"nodes": [], "edges": [{"source": "a", "target": "b"}], "hyperedges": []}
    assert not llm._response_is_hollow('{"edges":[...]}', parsed)


def _fake_openai_response(content, *, finish_reason="stop", prompt_tokens=100, completion_tokens=0):
    """Build a minimal stand-in for an `openai` SDK ChatCompletion response."""
    class _Usage:
        def __init__(self):
            self.prompt_tokens = prompt_tokens
            self.completion_tokens = completion_tokens

    class _Message:
        def __init__(self):
            self.content = content

    class _Choice:
        def __init__(self):
            self.message = _Message()
            self.finish_reason = finish_reason

    class _Resp:
        def __init__(self):
            self.choices = [_Choice()]
            self.usage = _Usage()

    return _Resp()


def _install_fake_openai(monkeypatch, fake_resp):
    """Inject a stub `openai` module so `_call_openai_compat` can run without
    the real SDK installed. The function does `from openai import OpenAI`
    inside its body, so we satisfy that lookup via `sys.modules`."""
    import sys
    import types

    class _FakeOpenAI:
        def __init__(self, *_, **__):
            self.chat = self
            self.completions = self
        def create(self, **__):
            return fake_resp

    fake_module = types.ModuleType("openai")
    fake_module.OpenAI = _FakeOpenAI
    monkeypatch.setitem(sys.modules, "openai", fake_module)


def test_call_openai_compat_relabels_empty_content_as_length(monkeypatch):
    # Simulates an overwhelmed Ollama: HTTP 200, empty content, finish_reason
    # "stop", zero completion tokens. Pre-fix this would silently return an
    # empty fragment and the chunk would be dropped. Post-fix `finish_reason`
    # is rewritten to "length" so the adaptive retry layer bisects.
    fake_resp = _fake_openai_response("", finish_reason="stop", completion_tokens=0)
    _install_fake_openai(monkeypatch, fake_resp)

    result = llm._call_openai_compat(
        "http://localhost:11434/v1", "ollama", "qwen2.5-coder:7b",
        "user msg", temperature=0, max_completion_tokens=8192, backend="ollama",
    )
    assert result["finish_reason"] == "length", (
        "empty content from a 'successful' call must be re-labelled so the "
        "adaptive retry layer treats it as a truncation and bisects the chunk"
    )


def test_call_openai_compat_relabels_none_content_as_length(monkeypatch):
    fake_resp = _fake_openai_response(None, finish_reason="stop")
    _install_fake_openai(monkeypatch, fake_resp)

    result = llm._call_openai_compat(
        "http://localhost:11434/v1", "ollama", "qwen2.5-coder:7b",
        "u", temperature=0, max_completion_tokens=8192, backend="ollama",
    )
    assert result["finish_reason"] == "length"


def test_call_openai_compat_relabels_unparseable_json_as_length(monkeypatch):
    # A half-generated response: `{"nodes": [{"id":` parses to {} (empty
    # fragment) via _parse_llm_json's JSONDecodeError fallback. That is also
    # hollow and must trigger bisection.
    fake_resp = _fake_openai_response('{"nodes": [{"id":', finish_reason="stop", completion_tokens=20)
    _install_fake_openai(monkeypatch, fake_resp)

    result = llm._call_openai_compat(
        "http://localhost:11434/v1", "ollama", "qwen2.5-coder:7b",
        "u", temperature=0, max_completion_tokens=8192, backend="ollama",
    )
    assert result["finish_reason"] == "length"


def test_call_openai_compat_preserves_real_finish_reason(monkeypatch):
    # A genuine extraction with real nodes must NOT be re-labelled.
    fake_resp = _fake_openai_response(
        '{"nodes":[{"id":"a"}],"edges":[],"hyperedges":[]}',
        finish_reason="stop",
        completion_tokens=200,
    )
    _install_fake_openai(monkeypatch, fake_resp)

    result = llm._call_openai_compat(
        "http://localhost:11434/v1", "k", "m",
        "u", temperature=0, max_completion_tokens=8192, backend="kimi",
    )
    assert result["finish_reason"] == "stop"
    assert result["nodes"] == [{"id": "a"}]


# ---------------------------------------------------------------------------
# Ollama context-window fix (#798): num_ctx + keep_alive in extra_body,
# serial execution by default.
# ---------------------------------------------------------------------------


def _install_capturing_openai(monkeypatch):
    """Like _install_fake_openai but records kwargs passed to create()."""
    import sys
    import types

    captured = {}

    class _FakeOpenAI:
        def __init__(self, *_, **__):
            self.chat = self
            self.completions = self

        def create(self, **kwargs):
            captured.update(kwargs)
            return _fake_openai_response(
                '{"nodes":[{"id":"x"}],"edges":[],"hyperedges":[]}',
                finish_reason="stop",
                completion_tokens=100,
            )

    fake_module = types.ModuleType("openai")
    fake_module.OpenAI = _FakeOpenAI
    monkeypatch.setitem(sys.modules, "openai", fake_module)
    return captured


def test_ollama_extra_body_sets_num_ctx_and_keep_alive(monkeypatch):
    captured = _install_capturing_openai(monkeypatch)
    monkeypatch.delenv("GRAPHIFY_OLLAMA_NUM_CTX", raising=False)
    monkeypatch.delenv("GRAPHIFY_OLLAMA_KEEP_ALIVE", raising=False)

    llm._call_openai_compat(
        "http://localhost:11434/v1", "ollama", "qwen2.5-coder:7b",
        "user msg", temperature=0, max_completion_tokens=8192, backend="ollama",
    )

    assert "extra_body" in captured, "extra_body must be sent to Ollama"
    eb = captured["extra_body"]
    # num_ctx is now dynamic: derived from message size, not hardcoded 131072
    assert "num_ctx" in eb.get("options", {}), "num_ctx must be present"
    assert eb["options"]["num_ctx"] >= 8192, "num_ctx must be at least the floor value"
    assert eb.get("keep_alive") == "30m", "default keep_alive must be 30m"


def test_ollama_num_ctx_scales_with_small_token_budget(monkeypatch):
    # Regression for #798 follow-up: with --token-budget 8192, the old hardcoded
    # 131072 forced Ollama to allocate 128k KV-cache slots on a 31B model, causing
    # VRAM exhaustion by chunk 4. num_ctx must now reflect actual chunk size.
    captured = _install_capturing_openai(monkeypatch)
    monkeypatch.delenv("GRAPHIFY_OLLAMA_NUM_CTX", raising=False)
    monkeypatch.delenv("GRAPHIFY_OLLAMA_KEEP_ALIVE", raising=False)

    # Simulate an 8k-token chunk: ~32k chars of content
    small_chunk_msg = "x" * 32_000

    llm._call_openai_compat(
        "http://localhost:11434/v1", "ollama", "qwen2.5-coder:7b",
        small_chunk_msg, temperature=0, max_completion_tokens=16384, backend="ollama",
    )

    num_ctx = captured["extra_body"]["options"]["num_ctx"]
    # Should be far less than 131072 for an 8k input — VRAM-friendly
    assert num_ctx < 131072, (
        f"num_ctx={num_ctx} is too large for a small chunk; "
        "this wastes VRAM and causes OOM on large models (#798)"
    )
    # But still large enough to fit input + output
    assert num_ctx >= 8192, "num_ctx must cover at least the output cap"


def test_ollama_num_ctx_env_override(monkeypatch):
    captured = _install_capturing_openai(monkeypatch)
    monkeypatch.setenv("GRAPHIFY_OLLAMA_NUM_CTX", "65536")
    monkeypatch.delenv("GRAPHIFY_OLLAMA_KEEP_ALIVE", raising=False)

    llm._call_openai_compat(
        "http://localhost:11434/v1", "ollama", "qwen2.5-coder:7b",
        "u", temperature=0, max_completion_tokens=8192, backend="ollama",
    )

    assert captured["extra_body"]["options"]["num_ctx"] == 65536


def test_non_ollama_backend_gets_no_num_ctx_extra_body(monkeypatch):
    captured = _install_capturing_openai(monkeypatch)

    llm._call_openai_compat(
        "https://api.openai.com/v1", "sk-test", "gpt-4.1-mini",
        "u", temperature=0, max_completion_tokens=8192, backend="openai",
    )

    eb = captured.get("extra_body")
    assert eb is None or "options" not in eb, "non-ollama backends must not get num_ctx injection"


def test_openai_compat_forces_non_streaming_response(monkeypatch):
    captured = _install_capturing_openai(monkeypatch)

    llm._call_openai_compat(
        "https://gateway.example/v1", "sk-test", "gpt-4.1-mini",
        "u", temperature=0, max_completion_tokens=8192, backend="openai",
    )

    assert captured["stream"] is False


# ---------------------------------------------------------------------------
# Custom-provider extra_body: lets providers.json route around the moonshot-only
# default. Self-hosted Qwen3 served by vLLM needs
# `chat_template_kwargs.enable_thinking=false` or the model emits chain-of-thought
# instead of the JSON the extraction parser expects.
# ---------------------------------------------------------------------------


def test_call_openai_compat_uses_explicit_extra_body(monkeypatch):
    captured = _install_capturing_openai(monkeypatch)

    llm._call_openai_compat(
        "https://kitor.example/vllm/v1", "tk", "Qwen3.6-27B",
        "u", temperature=0, max_completion_tokens=8192, backend="kitor-vllm",
        extra_body={"chat_template_kwargs": {"enable_thinking": False}},
    )

    assert captured["extra_body"] == {"chat_template_kwargs": {"enable_thinking": False}}


def test_call_openai_compat_extra_body_wins_over_moonshot_default(monkeypatch):
    # A user could legitimately set up a moonshot-compatible custom provider
    # and want a different extra_body — explicit kwarg must override the default.
    captured = _install_capturing_openai(monkeypatch)

    llm._call_openai_compat(
        "https://api.moonshot.ai/v1", "tk", "kimi-k2-thinking",
        "u", temperature=0, max_completion_tokens=8192, backend="kimi",
        extra_body={"thinking": {"type": "enabled"}},
    )

    assert captured["extra_body"] == {"thinking": {"type": "enabled"}}


def test_call_openai_compat_explicit_extra_body_skips_ollama_auto_derive(monkeypatch):
    # An explicit extra_body means "I own this request shape" — Ollama's
    # num_ctx auto-derive (a default) must step aside or we'd clobber it.
    captured = _install_capturing_openai(monkeypatch)
    monkeypatch.delenv("GRAPHIFY_OLLAMA_NUM_CTX", raising=False)
    monkeypatch.delenv("GRAPHIFY_OLLAMA_KEEP_ALIVE", raising=False)

    llm._call_openai_compat(
        "http://localhost:11434/v1", "ollama", "qwen2.5-coder:7b",
        "u", temperature=0, max_completion_tokens=8192, backend="ollama",
        extra_body={"options": {"num_ctx": 4096}},
    )

    assert captured["extra_body"] == {"options": {"num_ctx": 4096}}, (
        "explicit extra_body must replace the ollama auto-derived num_ctx"
    )


def test_extract_corpus_parallel_ollama_runs_serially(tmp_path, monkeypatch):
    # With 3 chunks and backend=ollama, ThreadPoolExecutor must NOT be used
    # (workers=1 takes the sequential path). We verify by ensuring all chunks
    # are processed and no pool is spun up.
    files = [tmp_path / f"f{i}.md" for i in range(6)]
    for f in files:
        f.write_text("hello")

    call_order = []

    def fake_extract(chunk, *_, **__):
        call_order.append(len(chunk))
        return _ok(nodes=[{"id": f.stem} for f in chunk])

    monkeypatch.delenv("GRAPHIFY_OLLAMA_PARALLEL", raising=False)

    with patch("graphify.llm.extract_files_direct", side_effect=fake_extract):
        with patch("graphify.llm.ThreadPoolExecutor") as mock_pool:
            result = llm.extract_corpus_parallel(
                files, backend="ollama", api_key="ollama", model="qwen2.5-coder:7b",
                root=tmp_path, token_budget=None, chunk_size=2, max_concurrency=4,
            )

    mock_pool.assert_not_called()
    assert len(result["nodes"]) == 6


def test_extract_corpus_parallel_ollama_parallel_env_restores_concurrency(tmp_path, monkeypatch):
    files = [tmp_path / f"f{i}.md" for i in range(4)]
    for f in files:
        f.write_text("hello")

    monkeypatch.setenv("GRAPHIFY_OLLAMA_PARALLEL", "1")

    with patch("graphify.llm.extract_files_direct", return_value=_ok()):
        with patch("graphify.llm.ThreadPoolExecutor") as mock_pool:
            mock_pool.return_value.__enter__ = lambda s: s
            mock_pool.return_value.__exit__ = lambda s, *a: False
            mock_pool.return_value.submit = lambda fn, *a, **kw: type(
                "F", (), {"result": lambda self: fn(*a, **kw)}
            )()
            try:
                llm.extract_corpus_parallel(
                    files, backend="ollama", api_key="ollama", model="m",
                    root=tmp_path, token_budget=None, chunk_size=2, max_concurrency=4,
                )
            except Exception:
                pass  # mock scaffolding may not be complete; we only care about the call

    mock_pool.assert_called()


def test_adaptive_retry_bisects_on_hollow_ollama_response(tmp_path):
    # End-to-end: an overwhelmed Ollama returns hollow on the full 4-file
    # chunk; halves succeed. The bug being fixed is that pre-fix this
    # produces zero nodes (chunk silently dropped). Post-fix the hollow
    # response is relabelled `finish_reason="length"` and the existing
    # bisection path recovers the full 4 nodes.
    files = [tmp_path / f"f{i}.md" for i in range(4)]
    for f in files:
        f.write_text("hello")

    calls = {"n": 0}

    def fake_extract(chunk, *_, **__):
        calls["n"] += 1
        if len(chunk) == 4:
            # Hollow response: looks successful, finish_reason already
            # rewritten to "length" by _call_openai_compat.
            return {
                "nodes": [], "edges": [], "hyperedges": [],
                "input_tokens": 100, "output_tokens": 0,
                "model": "m", "finish_reason": "length",
            }
        return _ok(nodes=[{"id": f.stem} for f in chunk])

    with patch("graphify.llm.extract_files_direct", side_effect=fake_extract):
        result = llm._extract_with_adaptive_retry(
            files, backend="ollama", api_key="ollama", model="qwen2.5-coder:7b",
            root=tmp_path, max_depth=3,
        )

    assert len(result["nodes"]) == 4, (
        "bisection should recover all 4 nodes from the two halves after the "
        "full chunk came back hollow"
    )
    assert calls["n"] == 3  # 1 hollow + 2 successful halves


# ---------------------------------------------------------------------------
# Azure backend
# ---------------------------------------------------------------------------


def _install_fake_azure_openai(monkeypatch, fake_resp):
    """Inject a stub openai module with AzureOpenAI so _call_azure and
    _azure_client can run without the real SDK installed."""
    import sys
    import types

    captured: dict = {}

    class _FakeAzureOpenAI:
        def __init__(self, *_, **kwargs):
            captured["init_kwargs"] = kwargs
            self.chat = self
            self.completions = self

        def create(self, **kwargs):
            captured["create_kwargs"] = kwargs
            return fake_resp

    fake_module = types.ModuleType("openai")
    fake_module.AzureOpenAI = _FakeAzureOpenAI
    monkeypatch.setitem(sys.modules, "openai", fake_module)
    return captured


def test_call_azure_uses_correct_client_params_and_max_completion_tokens(monkeypatch):
    monkeypatch.setenv("AZURE_OPENAI_API_VERSION", "2024-08-01-preview")
    monkeypatch.delenv("GRAPHIFY_API_TIMEOUT", raising=False)

    fake_resp = _fake_openai_response(
        '{"nodes":[{"id":"a"}],"edges":[],"hyperedges":[]}',
        finish_reason="stop",
        prompt_tokens=100,
        completion_tokens=50,
    )
    captured = _install_fake_azure_openai(monkeypatch, fake_resp)

    result = llm._call_azure(
        api_key="test-key",
        endpoint="https://my-resource.openai.azure.com/",
        model="gpt-4o",
        user_message="test",
    )

    assert captured["init_kwargs"].get("azure_endpoint") == "https://my-resource.openai.azure.com/"
    assert captured["init_kwargs"].get("api_version") == "2024-08-01-preview"
    assert "max_completion_tokens" in captured["create_kwargs"], "must use max_completion_tokens not max_tokens"
    assert "max_tokens" not in captured["create_kwargs"], "deprecated max_tokens must not be sent"
    assert result["nodes"] == [{"id": "a"}]


def test_detect_backend_returns_azure_when_both_vars_set(monkeypatch):
    _clear_backend_env(monkeypatch)
    monkeypatch.setenv("AZURE_OPENAI_API_KEY", "azure-key")
    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://my-resource.openai.azure.com/")

    assert llm.detect_backend() == "azure"
    assert llm._get_backend_api_key("azure") == "azure-key"


def test_detect_backend_azure_requires_endpoint_not_just_key(monkeypatch):
    _clear_backend_env(monkeypatch)
    monkeypatch.setenv("AZURE_OPENAI_API_KEY", "azure-key")
    # AZURE_OPENAI_ENDPOINT already cleared by _clear_backend_env

    assert llm.detect_backend() != "azure"


def test_estimate_cost_azure_no_keyerror():
    cost = llm.estimate_cost("azure", 1_000_000, 500_000)
    assert cost == pytest.approx(2.50 + 5.00)  # 1M in * $2.50/M + 0.5M out * $10.00/M


# ---------------------------------------------------------------------------
# Temperature resolution (#1191): omit temperature for reasoning models
# (o1/o3/o4/gpt-5) and honour GRAPHIFY_LLM_TEMPERATURE.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "model",
    ["o1", "o1-preview", "o1-mini", "o3", "o3-mini", "o4-mini", "gpt-5", "gpt-5-mini", "openai/o3-mini"],
)
def test_model_requires_default_temperature_true_for_reasoning_models(model):
    assert llm._model_requires_default_temperature(model) is True


@pytest.mark.parametrize(
    "model",
    ["gpt-4.1-mini", "gpt-4o", "gpt-4.1", "kimi-k2.6", "deepseek-v4-flash", "", "o1x", "go3"],
)
def test_model_requires_default_temperature_false_for_normal_models(model):
    assert llm._model_requires_default_temperature(model) is False


def test_resolve_temperature_default_for_normal_model(monkeypatch):
    monkeypatch.delenv("GRAPHIFY_LLM_TEMPERATURE", raising=False)
    assert llm._resolve_temperature(0, "gpt-4.1-mini") == 0


def test_resolve_temperature_omitted_for_reasoning_model(monkeypatch):
    monkeypatch.delenv("GRAPHIFY_LLM_TEMPERATURE", raising=False)
    assert llm._resolve_temperature(0, "o3-mini") is None
    assert llm._resolve_temperature(0, "gpt-5") is None


def test_resolve_temperature_env_var_numeric_overrides(monkeypatch):
    monkeypatch.setenv("GRAPHIFY_LLM_TEMPERATURE", "0.7")
    assert llm._resolve_temperature(0, "gpt-4.1-mini") == 0.7
    # env var wins even for a reasoning model (explicit user choice)
    assert llm._resolve_temperature(0, "o3-mini") == 0.7


def test_resolve_temperature_env_var_none_omits(monkeypatch):
    monkeypatch.setenv("GRAPHIFY_LLM_TEMPERATURE", "none")
    assert llm._resolve_temperature(0, "gpt-4.1-mini") is None


def test_resolve_temperature_env_var_invalid_falls_back(monkeypatch):
    monkeypatch.setenv("GRAPHIFY_LLM_TEMPERATURE", "hot")
    # bad value -> backend default for a normal model, still omitted for reasoning
    assert llm._resolve_temperature(0, "gpt-4.1-mini") == 0
    assert llm._resolve_temperature(0, "o3-mini") is None


def test_openai_compat_omits_temperature_for_o3_model(tmp_path, monkeypatch):
    # Regression for #1191: with a reasoning model the request must not carry a
    # `temperature` key at all, or the API returns HTTP 400.
    _clear_backend_env(monkeypatch)
    monkeypatch.delenv("GRAPHIFY_LLM_TEMPERATURE", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("GRAPHIFY_OPENAI_MODEL", "o3-mini")
    captured = _install_capturing_openai(monkeypatch)
    (tmp_path / "f.py").write_text("x = 1\n")

    llm.extract_files_direct([tmp_path / "f.py"], backend="openai", root=tmp_path)

    assert "temperature" not in captured, (
        "reasoning models (o3) reject an explicit temperature; it must be omitted (#1191)"
    )
    assert captured["model"] == "o3-mini"


def test_openai_compat_sends_temperature_for_normal_model(tmp_path, monkeypatch):
    _clear_backend_env(monkeypatch)
    monkeypatch.delenv("GRAPHIFY_LLM_TEMPERATURE", raising=False)
    monkeypatch.delenv("GRAPHIFY_OPENAI_MODEL", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    captured = _install_capturing_openai(monkeypatch)
    (tmp_path / "f.py").write_text("x = 1\n")

    llm.extract_files_direct([tmp_path / "f.py"], backend="openai", root=tmp_path)

    assert captured.get("temperature") == 0, "normal models keep the deterministic default"


def test_openai_compat_env_var_temperature_applied(tmp_path, monkeypatch):
    _clear_backend_env(monkeypatch)
    monkeypatch.setenv("GRAPHIFY_LLM_TEMPERATURE", "0.3")
    monkeypatch.delenv("GRAPHIFY_OPENAI_MODEL", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    captured = _install_capturing_openai(monkeypatch)
    (tmp_path / "f.py").write_text("x = 1\n")

    llm.extract_files_direct([tmp_path / "f.py"], backend="openai", root=tmp_path)

    assert captured.get("temperature") == 0.3


def test_native_extraction_prompt_requests_hyperedges():
    """The native-backend prompt must request hyperedges, like the skill's
    extraction-spec does — otherwise `graphify extract --backend X` silently
    produces zero hyperedges while the agent path produces them. Guards against
    the two prompts drifting apart again.
    """
    for deep in (False, True):
        prompt = llm._extraction_system(deep=deep)
        assert "hyperedge" in prompt.lower(), f"deep={deep}: prompt does not mention hyperedges"
        assert "3 or more nodes" in prompt, f"deep={deep}: prompt lacks the hyperedge guidance"
        # The schema example must show a populated hyperedge, not an empty array.
        assert '"hyperedges":[]' not in prompt, f"deep={deep}: schema still shows empty hyperedges"
        assert '"nodes":["node_id1"' in prompt, f"deep={deep}: schema lacks a populated hyperedge example"


def test_native_extraction_prompt_matches_skill_spec_on_hyperedges():
    """Both extraction paths share the same hyperedge contract (the '3 or more
    nodes … participate together' rule), so a corpus yields the same hyperedge
    behaviour whether built via the skill or `graphify extract --backend`.
    """
    spec = (
        Path(__file__).resolve().parents[1]
        / "tools" / "skillgen" / "fragments" / "references" / "shared" / "extraction-spec.md"
    ).read_text(encoding="utf-8")
    shared = "3 or more nodes clearly participate together"
    assert shared in spec, "skill extraction-spec changed its hyperedge wording"
    assert shared in llm._EXTRACTION_SYSTEM, "native prompt drifted from the skill hyperedge wording"


# --- *_BASE_URL env overrides for kimi / gemini / deepseek (#1458) -------------
# BACKENDS reads the env at import time, so each case runs in a fresh interpreter
# (subprocess) to avoid reload contamination of the test session.
import subprocess
import sys as _sys


def _backend_base_url(backend: str, env_extra: dict) -> str:
    out = subprocess.run(
        [_sys.executable, "-c",
         f"import graphify.llm as l; print(l.BACKENDS[{backend!r}]['base_url'])"],
        env={**os.environ, **env_extra}, capture_output=True, text=True, check=True,
    )
    return out.stdout.strip()


import os  # noqa: E402


@pytest.mark.parametrize("backend,env_var,override", [
    ("kimi", "KIMI_BASE_URL", "https://proxy.example/kimi/v1"),
    ("gemini", "GEMINI_BASE_URL", "https://proxy.example/gemini"),
    ("deepseek", "DEEPSEEK_BASE_URL", "https://proxy.example/deepseek"),
])
def test_base_url_env_overrides(backend, env_var, override):
    assert _backend_base_url(backend, {env_var: override}) == override


@pytest.mark.parametrize("backend,default", [
    ("kimi", "https://api.moonshot.ai/v1"),
    ("gemini", "https://generativelanguage.googleapis.com/v1beta/openai/"),
    ("deepseek", "https://api.deepseek.com"),
])
def test_base_url_defaults_without_env(backend, default):
    # Ensure the override env vars are unset so the hardcoded default is used.
    cleared = {k: "" for k in ("KIMI_BASE_URL", "GEMINI_BASE_URL", "DEEPSEEK_BASE_URL")}
    # empty string would be falsy-but-set; delete instead by reconstructing env without them
    env = {k: v for k, v in os.environ.items() if k not in cleared}
    out = subprocess.run(
        [_sys.executable, "-c",
         f"import graphify.llm as l; print(l.BACKENDS[{backend!r}]['base_url'])"],
        env=env, capture_output=True, text=True, check=True,
    )
    assert out.stdout.strip() == default


# ---------------------------------------------------------------------------
# #1505: claude-cli subprocess.run must use errors="replace" so non-UTF-8
# bytes from claude.cmd on Chinese Windows (GBK/cp936) don't crash the reader
# thread.
# ---------------------------------------------------------------------------

import json as _json


def _make_cli_envelope(result_text: str) -> str:
    """Return a minimal claude -p --output-format json envelope."""
    return _json.dumps({"type": "result", "result": result_text, "usage": {}, "modelUsage": {}})


def test_call_claude_cli_passes_errors_replace_to_subprocess():
    """subprocess.run must be called with errors='replace' so non-UTF-8 output
    bytes (e.g. GBK from claude.cmd on Chinese Windows) are tolerated instead
    of crashing the reader thread with UnicodeDecodeError (#1505)."""
    from unittest.mock import patch, MagicMock

    valid_envelope = _make_cli_envelope('{"nodes":[],"edges":[],"hyperedges":[]}')
    mock_proc = MagicMock()
    mock_proc.returncode = 0
    mock_proc.stdout = valid_envelope
    mock_proc.stderr = ""

    with patch("platform.system", return_value="Linux"), \
         patch("shutil.which", return_value="/usr/bin/claude"), \
         patch("subprocess.run", return_value=mock_proc) as mock_run:
        llm._call_claude_cli("test prompt")

    assert mock_run.call_args.kwargs.get("errors") == "replace", \
        "subprocess.run missing errors='replace' — non-UTF-8 bytes will crash the reader thread"


def test_call_claude_cli_tolerates_non_utf8_in_stderr():
    """When errors='replace' is set, non-UTF-8 bytes in stderr produce replacement
    chars instead of UnicodeDecodeError, allowing the error path to report cleanly."""
    from unittest.mock import patch, MagicMock

    mock_proc = MagicMock()
    mock_proc.returncode = 1
    mock_proc.stdout = ""
    mock_proc.stderr = "GBK error: ��"  # replacement chars after decode

    with patch("platform.system", return_value="Linux"), \
         patch("shutil.which", return_value="/usr/bin/claude"), \
         patch("subprocess.run", return_value=mock_proc):
        with pytest.raises(RuntimeError, match="claude -p exited 1"):
            llm._call_claude_cli("test prompt")
