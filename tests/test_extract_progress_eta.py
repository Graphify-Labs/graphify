"""Elapsed time and ETA in the semantic chunk progress line (#3179)."""
from __future__ import annotations

import time

import graphify.__main__ as mainmod


def _fmt(done, total, elapsed_seconds):
    from graphify.cli import format_chunk_progress

    return format_chunk_progress(done, total, elapsed_seconds)


def test_progress_line_shows_elapsed_and_minutes_left():
    assert _fmt(12, 87, 250.0) == (
        "[graphify extract] chunk 12/87 done · 4m10s elapsed · ~26m left"
    )


def test_progress_line_shows_seconds_left_under_a_minute():
    assert _fmt(10, 11, 400.0) == (
        "[graphify extract] chunk 10/11 done · 6m40s elapsed · ~40s left"
    )


def test_progress_line_shows_hours_left():
    assert _fmt(2, 40, 206.0) == (
        "[graphify extract] chunk 2/40 done · 3m26s elapsed · ~1h05m left"
    )


def test_progress_line_formats_sub_minute_elapsed_in_seconds():
    assert _fmt(5, 10, 42.3) == (
        "[graphify extract] chunk 5/10 done · 42s elapsed · ~42s left"
    )


def test_progress_line_formats_hour_elapsed():
    assert _fmt(65, 85, 3900.0) == (
        "[graphify extract] chunk 65/85 done · 1h05m elapsed · ~20m left"
    )


def test_progress_line_omits_left_after_a_single_chunk():
    assert _fmt(1, 87, 20.0) == "[graphify extract] chunk 1/87 done · 20s elapsed"


def test_progress_line_omits_left_before_any_chunk():
    assert _fmt(0, 10, 5.0) == "[graphify extract] chunk 0/10 done · 5s elapsed"


def test_progress_line_omits_left_when_all_chunks_done():
    assert _fmt(87, 87, 3900.0) == (
        "[graphify extract] chunk 87/87 done · 1h05m elapsed"
    )


def test_progress_line_tolerates_non_positive_elapsed():
    for elapsed in (0.0, -1.0):
        line = _fmt(5, 10, elapsed)
        assert line.startswith("[graphify extract] chunk 5/10 done · ")
        assert "elapsed" in line
        assert "inf" not in line
        assert "nan" not in line


def _make_corpus(tmp_path):
    (tmp_path / "main.go").write_text("package main\nfunc main() {}\n")
    (tmp_path / "README.md").write_text("# Notes\nThe main function entry point.\n")
    return tmp_path


def test_extract_cli_prints_elapsed_and_eta_per_chunk(monkeypatch, tmp_path, capsys):
    corpus = _make_corpus(tmp_path)
    out_dir = tmp_path / "out"
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-fake-key")

    clock = {"now": 1000.0}
    monkeypatch.setattr(time, "perf_counter", lambda: clock["now"])

    total = 87
    finished_at = {1: 20.0, 12: 250.0, total: 3900.0}

    def _chunks_finish_over_time(paths, **kwargs):
        on_chunk = kwargs["on_chunk_done"]
        for idx in range(total):
            done = idx + 1
            clock["now"] = 1000.0 + finished_at.get(done, 20.0 * done)
            on_chunk(idx, total, {"nodes": [], "edges": [], "hyperedges": []})
        return {
            "nodes": [],
            "edges": [],
            "hyperedges": [],
            "input_tokens": 100,
            "output_tokens": 50,
        }

    monkeypatch.setattr(
        "graphify.llm.extract_corpus_parallel", _chunks_finish_over_time
    )
    monkeypatch.setattr("graphify.cache.save_semantic_cache", lambda *a, **k: 0)
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)
    monkeypatch.setattr(
        mainmod.sys,
        "argv",
        ["graphify", "extract", str(corpus), "--backend", "claude",
         "--out", str(out_dir)],
    )

    try:
        mainmod.main()
    except SystemExit as exc:
        assert exc.code in (None, 0), f"unexpected exit code {exc.code}"

    lines = capsys.readouterr().out.splitlines()
    chunk_lines = [ln for ln in lines if ln.startswith("[graphify extract] chunk ")]
    assert len(chunk_lines) == total
    assert chunk_lines[0] == "[graphify extract] chunk 1/87 done · 20s elapsed"
    assert chunk_lines[11] == (
        "[graphify extract] chunk 12/87 done · 4m10s elapsed · ~26m left"
    )
    assert chunk_lines[-1] == "[graphify extract] chunk 87/87 done · 1h05m elapsed"


def test_extract_cli_counts_completed_chunks_when_they_finish_out_of_order(
    monkeypatch, tmp_path, capsys
):
    corpus = _make_corpus(tmp_path)
    out_dir = tmp_path / "out"
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-fake-key")

    clock = {"now": 1000.0}
    monkeypatch.setattr(time, "perf_counter", lambda: clock["now"])

    total = 10
    completion = [(5, 30.0), (0, 50.0), (3, 84.0), (1, 100.0), (2, 110.0),
                  (4, 120.0), (6, 130.0), (7, 140.0), (8, 150.0), (9, 160.0)]

    def _chunks_finish_out_of_order(paths, **kwargs):
        on_chunk = kwargs["on_chunk_done"]
        for idx, at in completion:
            clock["now"] = 1000.0 + at
            on_chunk(idx, total, {"nodes": [], "edges": [], "hyperedges": []})
        return {
            "nodes": [],
            "edges": [],
            "hyperedges": [],
            "input_tokens": 100,
            "output_tokens": 50,
        }

    monkeypatch.setattr(
        "graphify.llm.extract_corpus_parallel", _chunks_finish_out_of_order
    )
    monkeypatch.setattr("graphify.cache.save_semantic_cache", lambda *a, **k: 0)
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)
    monkeypatch.setattr(
        mainmod.sys,
        "argv",
        ["graphify", "extract", str(corpus), "--backend", "claude",
         "--out", str(out_dir)],
    )

    try:
        mainmod.main()
    except SystemExit as exc:
        assert exc.code in (None, 0), f"unexpected exit code {exc.code}"

    lines = capsys.readouterr().out.splitlines()
    chunk_lines = [ln for ln in lines if ln.startswith("[graphify extract] chunk ")]
    assert chunk_lines[:3] == [
        "[graphify extract] chunk 1/10 done · 30s elapsed",
        "[graphify extract] chunk 2/10 done · 50s elapsed · ~3m left",
        "[graphify extract] chunk 3/10 done · 1m24s elapsed · ~3m left",
    ]
    assert chunk_lines[-1] == "[graphify extract] chunk 10/10 done · 2m40s elapsed"
