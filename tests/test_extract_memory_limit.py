"""#3011: process-tree memory budget (--memory-limit-mb / GRAPHIFY_MEMORY_LIMIT_MB)."""
from __future__ import annotations

import time

import pytest

import graphify.__main__ as mainmod
from graphify import memory_budget as mb_mod


@pytest.fixture(autouse=True)
def _reset_monitor():
    yield
    mb_mod.stop_memory_budget_monitor()


def _make_corpus(tmp_path):
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "main.go").write_text("package main\nfunc main() {}\n")
    return corpus


# --- resolution: flag > env > off -------------------------------------------


def test_resolve_explicit_flag_wins_over_env(monkeypatch):
    monkeypatch.setenv("GRAPHIFY_MEMORY_LIMIT_MB", "123")
    assert mb_mod.resolve_memory_limit_mb(456) == 456


def test_resolve_env(monkeypatch):
    monkeypatch.setenv("GRAPHIFY_MEMORY_LIMIT_MB", "2048")
    assert mb_mod.resolve_memory_limit_mb(None) == 2048


def test_resolve_unset_garbage_or_nonpositive_is_off(monkeypatch):
    monkeypatch.delenv("GRAPHIFY_MEMORY_LIMIT_MB", raising=False)
    assert mb_mod.resolve_memory_limit_mb(None) is None
    # An opt-in safety valve must not become a new way for extraction to
    # refuse to run: garbage silently disables rather than erroring.
    monkeypatch.setenv("GRAPHIFY_MEMORY_LIMIT_MB", "not-a-number")
    assert mb_mod.resolve_memory_limit_mb(None) is None
    monkeypatch.setenv("GRAPHIFY_MEMORY_LIMIT_MB", "-5")
    assert mb_mod.resolve_memory_limit_mb(None) is None


def test_process_tree_rss_returns_positive_int_or_none():
    value = mb_mod.process_tree_rss_bytes()
    assert value is None or (isinstance(value, int) and value > 0)


# --- arming ------------------------------------------------------------------


def test_start_without_config_is_a_no_op(monkeypatch):
    monkeypatch.delenv("GRAPHIFY_MEMORY_LIMIT_MB", raising=False)
    assert mb_mod.start_memory_budget_monitor(None) is None
    assert mb_mod._active is None


def test_start_with_env_arms_the_sampler(monkeypatch):
    monkeypatch.setenv("GRAPHIFY_MEMORY_LIMIT_MB", "64")
    assert mb_mod.start_memory_budget_monitor(None) == 64
    assert mb_mod._active is not None
    assert mb_mod._active.limit_mb == 64


# --- breach semantics --------------------------------------------------------


def test_breach_reports_phase_usage_and_exits_stable_code(
    monkeypatch, tmp_path, capsys
):
    """Breach kills live worker children and hard-exits with EXIT_MEMORY_LIMIT."""
    import multiprocessing

    sleeper = multiprocessing.Process(target=time.sleep, args=(30,))
    sleeper.start()
    try:
        monitor = mb_mod._BudgetMonitor(16, "extract")
        monitor.set_phase("semantic-extraction")

        def _fake_exit(code):
            raise SystemExit(code)

        monkeypatch.setattr(mb_mod.os, "_exit", _fake_exit)
        with pytest.raises(SystemExit) as exc_info:
            monitor.breach(used=32 * 1024 * 1024)

        assert exc_info.value.code == mb_mod.EXIT_MEMORY_LIMIT == 3
        err = capsys.readouterr().err
        assert "memory budget exceeded" in err
        assert "limit 16 MB" in err
        assert "observed 32 MB" in err
        assert "phase 'semantic-extraction'" in err
        assert f"exit {mb_mod.EXIT_MEMORY_LIMIT}" in err
        # Child workers are terminated before the hard exit (#3011 ask 1).
        sleeper.join(timeout=5)
        assert not sleeper.is_alive()
    finally:
        if sleeper.is_alive():
            sleeper.terminate()
            sleeper.join(timeout=5)


# --- CLI wiring --------------------------------------------------------------


def _run_extract(argv_tail, monkeypatch, corpus):
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)
    monkeypatch.setattr(
        mainmod.sys, "argv", ["graphify", "extract", str(corpus)] + argv_tail
    )
    try:
        mainmod.main()
        return 0
    except SystemExit as exc:
        return exc.code


def test_extract_with_budget_flag_completes(monkeypatch, tmp_path, capsys):
    """A generous budget arms the sampler without disturbing the happy path."""
    corpus = _make_corpus(tmp_path)
    out_dir = tmp_path / "out"
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    code = _run_extract(
        ["--code-only", "--memory-limit-mb", "1048576", "--out", str(out_dir)],
        monkeypatch, corpus,
    )

    assert code in (None, 0), f"unexpected exit {code}"
    assert "memory budget: 1048576 MB" in capsys.readouterr().out
    assert (out_dir / "graphify-out" / "graph.json").exists()


def test_extract_budget_via_env_var(monkeypatch, tmp_path, capsys):
    corpus = _make_corpus(tmp_path)
    out_dir = tmp_path / "out"
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("GRAPHIFY_MEMORY_LIMIT_MB", "1048576")

    code = _run_extract(
        ["--code-only", "--out", str(out_dir)],
        monkeypatch, corpus,
    )

    assert code in (None, 0), f"unexpected exit {code}"
    assert "memory budget: 1048576 MB" in capsys.readouterr().out
    assert (out_dir / "graphify-out" / "graph.json").exists()


def test_extract_without_budget_prints_nothing_about_it(monkeypatch, tmp_path, capsys):
    corpus = _make_corpus(tmp_path)
    out_dir = tmp_path / "out"
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("GRAPHIFY_MEMORY_LIMIT_MB", raising=False)

    code = _run_extract(
        ["--code-only", "--out", str(out_dir)],
        monkeypatch, corpus,
    )

    assert code in (None, 0), f"unexpected exit {code}"
    assert "memory budget" not in capsys.readouterr().out
