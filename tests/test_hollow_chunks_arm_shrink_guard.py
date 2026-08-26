"""Hollow, unparseable and omitting chunks must count as incomplete (#3105).

The #479 shrink guard is bypassed (force=True) on a run that is classified
as complete. `_extraction_incomplete` tracked hard failures only — a crashed
pass, a chunk that raised. A chunk that came back hollow after every retry,
or as invalid JSON, or that simply omitted some of its files does not raise:
it returns fewer nodes and counts as a SUCCEEDED chunk. Two consecutive
`--update` runs on an unchanged repo: the first had 3 raised chunks and the
guard refused; the second had 0 raised, 6 hollow, and wrote 111 nodes over a
570-node graph without a word.
"""
from __future__ import annotations

import pytest

import graphify.__main__ as mainmod


def _corpus(tmp_path):
    (tmp_path / "README.md").write_text("# Notes\nThe entry point overview.\n", encoding="utf-8")
    (tmp_path / "GUIDE.md").write_text("# Guide\nHow to use the thing.\n", encoding="utf-8")
    return tmp_path


def _record_force(monkeypatch):
    rec = {"called": False, "force": None}

    def _stub(G, communities, output_path, *, force=False, **kwargs):
        rec["called"] = True
        rec["force"] = force
        return True

    monkeypatch.setattr("graphify.export.to_json", _stub)
    return rec


def _arm(monkeypatch, tmp_path, *, uncovered=(), partial=(), extra_argv=()):
    corpus = _corpus(tmp_path)
    out_dir = tmp_path / "out"
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-fake-key")

    def _stub_corpus(paths, **kwargs):
        # Every chunk "succeeds": the callback fires for each, nothing raises.
        on_chunk = kwargs.get("on_chunk_done")
        if on_chunk:
            on_chunk(0, 1, {"nodes": [], "edges": [], "hyperedges": []})
        nodes = [{"id": "s1", "source_file": str(corpus / "README.md"),
                  "file_type": "document", "label": "Notes"}]
        for sf in partial:
            nodes.append({"id": f"p_{sf}", "source_file": str(corpus / sf),
                          "file_type": "document", "label": sf, "_partial": True})
        return {"nodes": nodes, "edges": [], "hyperedges": [],
                "input_tokens": 10, "output_tokens": 5,
                "uncovered_files": [str(corpus / sf) for sf in uncovered]}

    monkeypatch.setattr("graphify.llm.extract_corpus_parallel", _stub_corpus)
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)
    monkeypatch.setattr(
        mainmod.sys, "argv",
        ["graphify", "extract", str(corpus), "--backend", "claude",
         "--out", str(out_dir), *extra_argv],
    )
    return out_dir


def _run():
    try:
        mainmod.main()
    except SystemExit as exc:
        return exc.code
    return 0


def test_a_chunk_that_omitted_files_arms_the_shrink_guard(monkeypatch, tmp_path, capsys):
    rec = _record_force(monkeypatch)
    _arm(monkeypatch, tmp_path, uncovered=("GUIDE.md",))
    _run()
    assert rec["called"] and rec["force"] is False, "an omitting chunk must not bypass the guard"
    assert "semantic extraction is incomplete" in capsys.readouterr().err


def test_a_hollow_chunk_arms_the_shrink_guard(monkeypatch, tmp_path, capsys):
    """After every retry a hollow chunk is returned (not raised) with its
    files marked partial; that is the reporter's run 2."""
    rec = _record_force(monkeypatch)
    _arm(monkeypatch, tmp_path, partial=("GUIDE.md",))
    _run()
    assert rec["called"] and rec["force"] is False
    assert "1 came back truncated or hollow" in capsys.readouterr().err


def test_allow_partial_still_overrides(monkeypatch, tmp_path):
    rec = _record_force(monkeypatch)
    _arm(monkeypatch, tmp_path, uncovered=("GUIDE.md",), extra_argv=["--allow-partial"])
    _run()
    assert rec["called"] and rec["force"] is True


def test_a_run_with_every_file_covered_keeps_force_write(monkeypatch, tmp_path, capsys):
    """The ordinary complete run is unchanged: a full build legitimately
    shrinks (dedup, deleted code) and keeps bypassing the guard."""
    rec = _record_force(monkeypatch)
    _arm(monkeypatch, tmp_path)
    _run()
    assert rec["called"] and rec["force"] is True
    assert "semantic extraction is incomplete" not in capsys.readouterr().err


def test_the_manifest_is_not_stamped_when_the_guard_refuses(monkeypatch, tmp_path):
    """Refusal must leave the omitted files un-stamped so the next run retries
    them — the same contract a crashed chunk already has."""
    def _refuse(G, communities, output_path, *, force=False, **kwargs):
        return False
    monkeypatch.setattr("graphify.export.to_json", _refuse)
    out_dir = _arm(monkeypatch, tmp_path, uncovered=("GUIDE.md",))
    code = _run()
    assert code not in (None, 0)
    assert not (out_dir / "graphify-out" / "manifest.json").exists()
