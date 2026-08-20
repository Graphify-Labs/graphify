"""`graphify extract --no-dedup` (#2881).

The incremental merge path hardcoded `dedup=True`, so fuzzy dedup always ran
over the COMBINED node set (existing graph + new chunk). On a large graph a
small diff could therefore collapse pre-existing nodes belonging to files the
diff never touched, and the #479 shrink guard — the one thing that would have
caught it — is deliberately skipped while dedup is on, because fuzzy merging
shrinks the graph legitimately. There was no way to opt out from the CLI.
"""
from __future__ import annotations

import graphify.__main__ as mainmod


def _corpus(tmp_path):
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "main.go").write_text("package main\nfunc main() {}\n")
    return corpus


def _run(monkeypatch, argv):
    """Run the CLI and return its exit code (0 when main() simply returns)."""
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)
    monkeypatch.setattr(mainmod.sys, "argv", argv)
    try:
        mainmod.main()
    except SystemExit as exc:
        return exc.code or 0
    return 0


def _capture_dedup(monkeypatch):
    """Record the `dedup` kwarg both build entry points are called with."""
    import graphify.build as buildmod

    seen: dict[str, bool] = {}
    real_build = buildmod.build
    real_merge = buildmod.build_merge

    def fake_build(chunks, *a, **kw):
        seen["build"] = kw.get("dedup", True)
        return real_build(chunks, *a, **kw)

    def fake_merge(chunks, *a, **kw):
        seen["build_merge"] = kw.get("dedup", True)
        return real_merge(chunks, *a, **kw)

    monkeypatch.setattr(buildmod, "build", fake_build)
    monkeypatch.setattr(buildmod, "build_merge", fake_merge)
    return seen


def test_no_dedup_flag_disables_dedup(monkeypatch, tmp_path):
    corpus = _corpus(tmp_path)
    seen = _capture_dedup(monkeypatch)
    code = _run(monkeypatch, [
        "graphify", "extract", str(corpus), "--code-only",
        "--no-dedup", "--out", str(tmp_path / "out"),
    ])
    assert code == 0
    assert seen.get("build") is False


def test_dedup_is_on_by_default(monkeypatch, tmp_path):
    corpus = _corpus(tmp_path)
    seen = _capture_dedup(monkeypatch)
    code = _run(monkeypatch, [
        "graphify", "extract", str(corpus), "--code-only",
        "--out", str(tmp_path / "out"),
    ])
    assert code == 0
    assert seen.get("build") is True


def test_no_dedup_reaches_the_incremental_merge(monkeypatch, tmp_path):
    corpus = _corpus(tmp_path)
    out = tmp_path / "out"
    # First run establishes graph.json, so the second run takes the
    # build_merge (incremental) path rather than build().
    assert _run(monkeypatch, [
        "graphify", "extract", str(corpus), "--code-only",
        "--out", str(out),
    ]) == 0

    (corpus / "other.go").write_text("package main\nfunc other() {}\n")
    seen = _capture_dedup(monkeypatch)
    assert _run(monkeypatch, [
        "graphify", "extract", str(corpus), "--code-only",
        "--no-dedup", "--out", str(out),
    ]) == 0
    assert seen.get("build_merge") is False, (
        "the incremental path hardcoded dedup=True, which is the bug"
    )


def test_no_dedup_conflicts_with_dedup_llm(monkeypatch, tmp_path, capsys):
    corpus = _corpus(tmp_path)
    code = _run(monkeypatch, [
        "graphify", "extract", str(corpus), "--code-only",
        "--no-dedup", "--dedup-llm", "--out", str(tmp_path / "out"),
    ])
    assert code == 2
    assert "mutually exclusive" in capsys.readouterr().err
