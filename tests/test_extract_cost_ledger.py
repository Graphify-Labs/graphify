"""#1769 - `graphify extract` printed this run's tokens but never added them to
graphify-out/cost.json, so the ledger only ever showed the skill's first run.
"""
from __future__ import annotations

import json

import pytest

import graphify.__main__ as mainmod


def _make_corpus(tmp_path):
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "main.go").write_text("package main\nfunc main() {}\n")
    (corpus / "README.md").write_text("# Notes\nThe main function entry point.\n")
    return corpus


def _fake_llm(paths, **kwargs):
    on_chunk = kwargs.get("on_chunk_done")
    if on_chunk:
        on_chunk(0, 1, {"nodes": [], "edges": [], "hyperedges": []})
    return {
        "nodes": [{"id": f"n{i}", "label": f"n{i}", "source_file": str(p),
                   "file_type": "document"} for i, p in enumerate(paths)],
        "edges": [],
        "hyperedges": [],
        "input_tokens": 100,
        "output_tokens": 40,
    }


def _run_extract(monkeypatch, corpus, out_dir, *extra):
    monkeypatch.setattr(
        mainmod.sys, "argv",
        ["graphify", "extract", str(corpus), "--backend", "claude",
         "--out", str(out_dir), *extra],
    )
    try:
        mainmod.main()
    except SystemExit as exc:
        assert exc.code in (None, 0), f"unexpected exit code {exc.code}"


@pytest.fixture
def setup(monkeypatch, tmp_path):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-fake-key")
    monkeypatch.setattr("graphify.llm.extract_corpus_parallel", _fake_llm)
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)
    return _make_corpus(tmp_path), tmp_path / "out"


@pytest.mark.parametrize("extra", [(), ("--no-cluster",)])
def test_each_extract_run_is_added_to_cost_json(monkeypatch, setup, extra):
    corpus, out_dir = setup
    cost_path = out_dir / "graphify-out" / "cost.json"

    _run_extract(monkeypatch, corpus, out_dir, *extra)
    cost = json.loads(cost_path.read_text(encoding="utf-8"))
    assert len(cost["runs"]) == 1
    assert cost["runs"][0]["input_tokens"] == 100
    assert cost["runs"][0]["output_tokens"] == 40
    assert cost["runs"][0]["files"] == 2
    assert cost["runs"][0]["date"]

    # A changed doc is re-extracted, and that run is added on top.
    (corpus / "README.md").write_text("# Notes\nChanged, so it is sent again.\n")
    _run_extract(monkeypatch, corpus, out_dir, *extra)
    cost = json.loads(cost_path.read_text(encoding="utf-8"))
    assert len(cost["runs"]) == 2
    assert cost["total_input_tokens"] == 200
    assert cost["total_output_tokens"] == 80


def test_existing_skill_ledger_is_kept(monkeypatch, setup):
    corpus, out_dir = setup
    cost_path = out_dir / "graphify-out" / "cost.json"
    cost_path.parent.mkdir(parents=True)
    earlier = {"date": "2026-01-01T00:00:00+00:00", "input_tokens": 5000,
               "output_tokens": 0, "files": 493}
    cost_path.write_text(json.dumps({"runs": [earlier], "total_input_tokens": 5000,
                                     "total_output_tokens": 0}), encoding="utf-8")

    _run_extract(monkeypatch, corpus, out_dir)
    cost = json.loads(cost_path.read_text(encoding="utf-8"))
    assert cost["runs"][0] == earlier
    assert len(cost["runs"]) == 2
    assert cost["total_input_tokens"] == 5100
    assert cost["total_output_tokens"] == 40


@pytest.mark.parametrize("bad", [
    "{not json",
    "[]",
    "null",
    '{"runs": {}}',
    '{"runs": [], "total_input_tokens": "5"}',
    '{"runs": [], "total_input_tokens": null}',
])
def test_unreadable_ledger_is_not_overwritten(monkeypatch, setup, bad):
    corpus, out_dir = setup
    cost_path = out_dir / "graphify-out" / "cost.json"
    cost_path.parent.mkdir(parents=True)
    cost_path.write_text(bad, encoding="utf-8")

    _run_extract(monkeypatch, corpus, out_dir)
    assert (out_dir / "graphify-out" / "graph.json").exists()
    assert cost_path.read_text(encoding="utf-8") == bad


def test_code_only_run_with_no_tokens_writes_nothing(monkeypatch, tmp_path):
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "main.go").write_text("package main\nfunc main() {}\n")
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)
    out_dir = tmp_path / "out"

    _run_extract(monkeypatch, corpus, out_dir)
    assert (out_dir / "graphify-out" / "graph.json").exists()
    assert not (out_dir / "graphify-out" / "cost.json").exists()
