"""Tests for `graphify extract --fallback-backend` (retry on a second brain).

When EVERY semantic chunk fails on the primary backend (missing SDK, bad key,
an outage), a configured fallback backend retries the same still-uncached
files once — nothing was cache-saved for a zero-success pass, so the retry
covers exactly the files the primary failed on. Only when the fallback also
ends at zero successes does extract keep the all-chunks-failed exit 1.
Without a fallback configured, behavior is unchanged.
"""
from __future__ import annotations

import pytest

import graphify.__main__ as mainmod


def _make_corpus(tmp_path):
    """Minimal corpus: one Go code file + one Markdown doc.

    Both file types are needed so semantic extraction is requested
    (docs path triggers the LLM step the fallback wraps).
    """
    (tmp_path / "main.go").write_text("package main\nfunc main() {}\n")
    (tmp_path / "README.md").write_text("# Notes\nThe main function entry point.\n")
    return tmp_path


def _recording_stub(calls, *, fail_backends=(), raise_backends=None):
    """Stub extract_corpus_parallel that records each dispatch.

    Backends in ``fail_backends`` simulate "all chunks failed": an empty
    accumulator, on_chunk_done never invoked. Backends in ``raise_backends``
    (a dict backend -> exception) crash the whole pass. Everything else
    succeeds with one chunk.
    """
    raise_backends = raise_backends or {}

    def _stub(paths, **kwargs):
        be = kwargs.get("backend")
        calls.append({
            "backend": be,
            "model": kwargs.get("model"),
            "paths": sorted(str(p) for p in paths),
        })
        if be in raise_backends:
            raise raise_backends[be]
        if be in fail_backends:
            return {"nodes": [], "edges": [], "hyperedges": [],
                    "input_tokens": 0, "output_tokens": 0}
        on_chunk = kwargs.get("on_chunk_done")
        if on_chunk:
            on_chunk(0, 1, {"nodes": [], "edges": [], "hyperedges": []})
        return {"nodes": [], "edges": [], "hyperedges": [],
                "input_tokens": 10, "output_tokens": 5}

    return _stub


def _arm(monkeypatch, tmp_path, stub, *, extra_argv=(), env=None):
    corpus = _make_corpus(tmp_path)
    out_dir = tmp_path / "out"
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-fake-key")
    monkeypatch.delenv("GRAPHIFY_FALLBACK_BACKEND", raising=False)
    for key, value in (env or {}).items():
        monkeypatch.setenv(key, value)
    monkeypatch.setattr("graphify.llm.extract_corpus_parallel", stub)
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)
    monkeypatch.setattr(
        mainmod.sys, "argv",
        ["graphify", "extract", str(corpus), "--backend", "claude",
         "--out", str(out_dir), *extra_argv],
    )
    return corpus, out_dir


def _run_ok(capsys=None):
    # extract may still raise SystemExit at the end (clean exit code 0)
    # depending on platform; accept either no exception or SystemExit(0).
    try:
        mainmod.main()
    except SystemExit as exc:
        assert exc.code in (None, 0), f"unexpected exit code {exc.code}"


def test_fallback_retries_same_paths_and_succeeds(monkeypatch, tmp_path, capsys):
    calls = []
    stub = _recording_stub(calls, fail_backends=("claude",))
    corpus, out_dir = _arm(
        monkeypatch, tmp_path, stub,
        extra_argv=["--fallback-backend", "openai", "--model", "claude-test-model"],
    )

    _run_ok()

    assert [c["backend"] for c in calls] == ["claude", "openai"]
    # The retry covers exactly the files the primary failed on.
    assert calls[0]["paths"] == calls[1]["paths"] == [str(corpus / "README.md")]
    # --model names a model on the PRIMARY backend only; the fallback runs
    # on its own default model.
    assert calls[0]["model"] == "claude-test-model"
    assert calls[1]["model"] is None
    out = capsys.readouterr().out
    assert "retrying once with fallback backend 'openai'" in out
    assert (out_dir / "graphify-out" / "graph.json").exists(), (
        "graph.json must be written when the fallback pass succeeds"
    )


def test_fallback_also_failing_keeps_exit_1(monkeypatch, tmp_path, capsys):
    calls = []
    stub = _recording_stub(calls, fail_backends=("claude", "openai"))
    _corpus, out_dir = _arm(
        monkeypatch, tmp_path, stub, extra_argv=["--fallback-backend", "openai"],
    )

    with pytest.raises(SystemExit) as exc:
        mainmod.main()

    assert exc.value.code == 1
    assert [c["backend"] for c in calls] == ["claude", "openai"], (
        "the fallback must be tried exactly once before failing"
    )
    err = capsys.readouterr().err
    assert "all semantic chunks failed" in err
    assert "openai" in err, "the final error must name the last backend tried"
    assert not (out_dir / "graphify-out" / "graph.json").exists()


def test_no_fallback_behavior_is_unchanged(monkeypatch, tmp_path, capsys):
    calls = []
    stub = _recording_stub(calls, fail_backends=("claude",))
    _arm(monkeypatch, tmp_path, stub)

    with pytest.raises(SystemExit) as exc:
        mainmod.main()

    assert exc.value.code == 1
    assert [c["backend"] for c in calls] == ["claude"]
    err = capsys.readouterr().err
    assert "all semantic chunks failed" in err
    assert "claude" in err


def test_fallback_equal_to_primary_is_not_retried(monkeypatch, tmp_path):
    # Retrying the very backend that just zeroed out would double the spend
    # for the same outcome, so an identical fallback is a no-op.
    calls = []
    stub = _recording_stub(calls, fail_backends=("claude",))
    _arm(monkeypatch, tmp_path, stub, extra_argv=["--fallback-backend", "claude"])

    with pytest.raises(SystemExit) as exc:
        mainmod.main()

    assert exc.value.code == 1
    assert [c["backend"] for c in calls] == ["claude"]


def test_unknown_fallback_backend_is_rejected_upfront(monkeypatch, tmp_path, capsys):
    calls = []
    stub = _recording_stub(calls)
    _arm(monkeypatch, tmp_path, stub, extra_argv=["--fallback-backend", "warpdrive"])

    with pytest.raises(SystemExit) as exc:
        mainmod.main()

    assert exc.value.code == 1
    err = capsys.readouterr().err
    assert "unknown fallback backend 'warpdrive'" in err
    assert calls == [], "a typo'd fallback must fail before any API dispatch"


def test_env_var_arms_the_fallback(monkeypatch, tmp_path, capsys):
    calls = []
    stub = _recording_stub(calls, fail_backends=("claude",))
    _arm(monkeypatch, tmp_path, stub, env={"GRAPHIFY_FALLBACK_BACKEND": "openai"})

    _run_ok()

    assert [c["backend"] for c in calls] == ["claude", "openai"]


def test_cli_flag_wins_over_env_var(monkeypatch, tmp_path):
    calls = []
    stub = _recording_stub(calls, fail_backends=("claude",))
    _arm(
        monkeypatch, tmp_path, stub,
        extra_argv=["--fallback-backend=kimi"],
        env={"GRAPHIFY_FALLBACK_BACKEND": "openai"},
    )

    _run_ok()

    assert [c["backend"] for c in calls] == ["claude", "kimi"]


def test_primary_crash_triggers_fallback(monkeypatch, tmp_path, capsys):
    # A pass that raises leaves zero succeeded chunks, so it rides the same
    # retry path as per-chunk total failure.
    calls = []
    stub = _recording_stub(
        calls, raise_backends={"claude": RuntimeError("backend melted")},
    )
    _arm(monkeypatch, tmp_path, stub, extra_argv=["--fallback-backend", "openai"])

    _run_ok()

    assert [c["backend"] for c in calls] == ["claude", "openai"]
    captured = capsys.readouterr()
    assert "semantic extraction failed: backend melted" in captured.err
    assert "retrying once with fallback backend 'openai'" in captured.out


def test_primary_import_error_falls_back_instead_of_dying(monkeypatch, tmp_path, capsys):
    # A missing SDK package is fatal without a fallback, but with one
    # configured it is exactly the case the fallback exists for.
    calls = []
    stub = _recording_stub(
        calls, raise_backends={"claude": ImportError("requires the anthropic package")},
    )
    _arm(monkeypatch, tmp_path, stub, extra_argv=["--fallback-backend", "openai"])

    _run_ok()

    assert [c["backend"] for c in calls] == ["claude", "openai"]
    assert "requires the anthropic package" in capsys.readouterr().err


def test_partial_primary_success_does_not_fire_fallback(monkeypatch, tmp_path, capsys):
    # The fallback exists for TOTAL failure only. When the primary got at
    # least one chunk through, retrying the whole set on a second backend
    # would re-spend on the chunks that already succeeded — so a partial
    # pass keeps its result (and the incomplete-build guard), no retry.
    calls = []

    def _partial_stub(paths, **kwargs):
        calls.append({"backend": kwargs.get("backend")})
        on_chunk = kwargs.get("on_chunk_done")
        if on_chunk:
            # 1 of 2 chunks succeeded; the second never reports.
            on_chunk(0, 2, {"nodes": [], "edges": [], "hyperedges": []})
        return {"nodes": [], "edges": [], "hyperedges": [],
                "input_tokens": 10, "output_tokens": 5}

    _arm(monkeypatch, tmp_path, _partial_stub,
         extra_argv=["--fallback-backend", "openai"])

    _run_ok()

    assert [c["backend"] for c in calls] == ["claude"], (
        "a partially-succeeded primary pass must not re-dispatch on the fallback"
    )
    assert "retrying once with fallback backend" not in capsys.readouterr().out


def test_import_error_without_fallback_stays_fatal(monkeypatch, tmp_path, capsys):
    calls = []
    stub = _recording_stub(
        calls, raise_backends={"claude": ImportError("requires the anthropic package")},
    )
    _arm(monkeypatch, tmp_path, stub)

    with pytest.raises(SystemExit) as exc:
        mainmod.main()

    assert exc.value.code == 1
    assert [c["backend"] for c in calls] == ["claude"]
    assert "requires the anthropic package" in capsys.readouterr().err
