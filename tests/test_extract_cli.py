"""Tests for `graphify extract` CLI dispatch path in graphify.__main__."""
from __future__ import annotations

import pytest

import graphify.__main__ as mainmod


def _make_corpus(tmp_path):
    """Minimal corpus: one Go code file + one Markdown doc.

    Both file types are needed so semantic extraction is requested
    (docs path triggers the LLM step we want to assert against).
    """
    (tmp_path / "main.go").write_text("package main\nfunc main() {}\n")
    (tmp_path / "README.md").write_text("# Notes\nThe main function entry point.\n")
    return tmp_path


def test_extract_exits_nonzero_when_all_semantic_chunks_fail(
    monkeypatch, tmp_path, capsys
):
    """When every semantic chunk errors (e.g. backend SDK not installed),
    the CLI must exit non-zero instead of silently writing an AST-only graph.

    The bug this guards: `pip install graphifyy` doesn't pull in `anthropic`,
    so `graphify extract --backend claude` would print per-chunk errors and
    still exit 0 with a graph.json. Callers checking exit status saw success.
    """
    corpus = _make_corpus(tmp_path)
    out_dir = tmp_path / "out"

    # Stub the API-key check so the backend gate doesn't reject before we
    # reach the semantic-extraction step.
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-fake-key")

    # Patch extract_corpus_parallel to simulate "all chunks failed":
    # return an empty merged accumulator without ever invoking on_chunk_done.
    # This matches the real behavior of extract_corpus_parallel when every
    # chunk raises (the per-chunk failures print to stderr and the loop
    # continues without calling the success callback).
    def _all_chunks_failed(paths, **kwargs):
        return {
            "nodes": [],
            "edges": [],
            "hyperedges": [],
            "input_tokens": 0,
            "output_tokens": 0,
        }

    monkeypatch.setattr(
        "graphify.llm.extract_corpus_parallel", _all_chunks_failed
    )
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)
    monkeypatch.setattr(
        mainmod.sys,
        "argv",
        ["graphify", "extract", str(corpus), "--backend", "claude",
         "--out", str(out_dir)],
    )

    with pytest.raises(SystemExit) as exc_info:
        mainmod.main()

    assert exc_info.value.code == 1, (
        f"expected exit code 1 when all semantic chunks fail, "
        f"got {exc_info.value.code}"
    )

    stderr = capsys.readouterr().err
    assert "all semantic chunks failed" in stderr
    assert "claude" in stderr

    # No graph.json should have been written - the failure must abort before
    # the merge/cluster/write phase, not after.
    assert not (out_dir / "graphify-out" / "graph.json").exists(), (
        "graph.json must not be written when semantic extraction fails"
    )


def test_extract_succeeds_when_at_least_one_chunk_completes(
    monkeypatch, tmp_path
):
    """Sanity counter-test: a successful chunk run keeps exit 0. Confirms the
    new guard only fires on the all-failed path, not on every extract."""
    corpus = _make_corpus(tmp_path)
    out_dir = tmp_path / "out"
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-fake-key")

    def _one_chunk_succeeded(paths, **kwargs):
        on_chunk = kwargs.get("on_chunk_done")
        if on_chunk:
            on_chunk(0, 1, {"nodes": [], "edges": [], "hyperedges": []})
        return {
            "nodes": [],
            "edges": [],
            "hyperedges": [],
            "input_tokens": 100,
            "output_tokens": 50,
        }

    monkeypatch.setattr(
        "graphify.llm.extract_corpus_parallel", _one_chunk_succeeded
    )
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)
    monkeypatch.setattr(
        mainmod.sys,
        "argv",
        ["graphify", "extract", str(corpus), "--backend", "claude",
         "--out", str(out_dir)],
    )

    # extract may still raise SystemExit at the end (clean exit code 0)
    # depending on platform; accept either no exception or SystemExit(0).
    try:
        mainmod.main()
    except SystemExit as exc:
        assert exc.code in (None, 0), f"unexpected exit code {exc.code}"

    # graph.json should exist on the happy path
    assert (out_dir / "graphify-out" / "graph.json").exists(), (
        "graph.json must be written on the happy path"
    )


def _code_only_corpus(tmp_path):
    """A corpus with only code — no docs/papers/images."""
    (tmp_path / "auth.py").write_text(
        "def login(user):\n    return validate(user)\n\n"
        "def validate(user):\n    return True\n"
    )
    return tmp_path


def _clear_backend_keys(monkeypatch):
    """Clear every env var that detect_backend() or _get_backend_api_key() reads."""
    for key in (
        "GEMINI_API_KEY", "GOOGLE_API_KEY", "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY", "DEEPSEEK_API_KEY", "MOONSHOT_API_KEY",
        # bedrock: presence of any of these is treated as a valid credential
        "AWS_PROFILE", "AWS_REGION", "AWS_DEFAULT_REGION", "AWS_ACCESS_KEY_ID",
        # ollama: a set OLLAMA_BASE_URL triggers backend detection
        "OLLAMA_BASE_URL",
    ):
        monkeypatch.delenv(key, raising=False)


def test_extract_codeonly_succeeds_without_api_key(monkeypatch, tmp_path):
    """A code-only corpus must run with no LLM API key.

    Regression: graphify extract validated a backend upfront and exited 1 with
    'no LLM API key found' even for a code-only corpus that never calls a model.
    The keyless AST path now runs to a written graph.json (#1122).
    """
    corpus = _code_only_corpus(tmp_path)
    out_dir = tmp_path / "out"
    _clear_backend_keys(monkeypatch)
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)
    monkeypatch.setattr(
        mainmod.sys, "argv",
        ["graphify", "extract", str(corpus), "--out", str(out_dir)],
    )

    try:
        mainmod.main()
    except SystemExit as exc:
        assert exc.code in (None, 0), f"unexpected exit code {exc.code}"

    graph = out_dir / "graphify-out" / "graph.json"
    assert graph.exists(), "code-only extract must write graph.json without a key"
    import json
    assert len(json.loads(graph.read_text()).get("nodes", [])) > 0


def test_extract_out_keeps_project_root_clean(monkeypatch, tmp_path):
    """`extract --out DIR` routes every artifact to DIR/graphify-out/ and the
    scanned project must not grow a graphify-out/ (or anything else) beside
    its sources.

    Guards the centralized-output workflow: run from the project root with
    --out pointing outside the repo, and the repo stays byte-identical.
    """
    project = tmp_path / "project"
    project.mkdir()
    corpus = _code_only_corpus(project)
    external = tmp_path / "external-graphs"

    _clear_backend_keys(monkeypatch)
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)
    monkeypatch.chdir(corpus)  # run from the project root, like a real user
    monkeypatch.setattr(
        mainmod.sys, "argv",
        ["graphify", "extract", ".", "--out", str(external)],
    )

    try:
        mainmod.main()
    except SystemExit as exc:
        assert exc.code in (None, 0), f"unexpected exit code {exc.code}"

    out = external / "graphify-out"
    assert (out / "graph.json").exists(), "graph.json must land under --out"
    assert (out / "manifest.json").exists(), "manifest.json must land under --out"
    assert not (corpus / "graphify-out").exists(), (
        "scanned project must not grow a graphify-out/ when --out is set"
    )
    assert sorted(p.name for p in corpus.iterdir()) == ["auth.py"], (
        "no stray files may appear in the project root"
    )


def test_extract_without_key_still_errors_when_docs_present(
    monkeypatch, tmp_path, capsys
):
    """Key requirement still fires when semantic work is needed.

    A corpus with a Markdown doc needs LLM semantic extraction, so a keyless
    extract must exit 1 with clear guidance (#1122).
    """
    corpus = _make_corpus(tmp_path)  # includes a Markdown doc
    out_dir = tmp_path / "out"
    _clear_backend_keys(monkeypatch)
    # Patch detect_backend too so ambient AWS/ollama env can't slip through.
    monkeypatch.setattr("graphify.llm.detect_backend", lambda: None)
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)
    monkeypatch.setattr(
        mainmod.sys, "argv",
        ["graphify", "extract", str(corpus), "--out", str(out_dir)],
    )

    with pytest.raises(SystemExit) as exc_info:
        mainmod.main()
    assert exc_info.value.code == 1
    err = capsys.readouterr().err
    assert "no LLM API key found" in err
    assert "code-only corpus needs no key" in err
    assert not (out_dir / "graphify-out" / "graph.json").exists()


def test_extract_timing_flag_emits_stage_timings(monkeypatch, tmp_path, capsys):
    """--timing prints per-stage `[graphify timing]` lines to stderr (#1490); omitting
    it prints none, so default output is unchanged. Code-only corpus => no API key."""
    code = tmp_path / "code"
    code.mkdir()
    (code / "a.py").write_text("def a():\n    return b()\ndef b():\n    return 1\n")

    # with --timing
    monkeypatch.setattr(
        mainmod.sys, "argv",
        ["graphify", "extract", str(code), "--no-cluster", "--out", str(tmp_path / "o1"), "--timing"],
    )
    with pytest.raises(SystemExit) as exc:
        mainmod.main()
    assert exc.value.code == 0
    err = capsys.readouterr().err
    assert "[graphify timing] detect:" in err
    assert "[graphify timing] total:" in err

    # without --timing => no timing lines
    monkeypatch.setattr(
        mainmod.sys, "argv",
        ["graphify", "extract", str(code), "--no-cluster", "--out", str(tmp_path / "o2")],
    )
    with pytest.raises(SystemExit) as exc2:
        mainmod.main()
    assert exc2.value.code == 0
    assert "graphify timing" not in capsys.readouterr().err
