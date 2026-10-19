"""A file the model read and found empty is not an omitted file (#4547)."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

import graphify.__main__ as mainmod
import graphify.llm as llm
from graphify.llm import (
    _mark_hollow,
    _parse_llm_json,
    _partial_source_files,
    _response_is_hollow,
    extract_corpus_parallel,
)


@pytest.fixture(autouse=True)
def _no_hollow_backoff(monkeypatch):
    # A hollow or truncated response is retried with 2s and 8s backoff; the
    # tests care about what happens, not about waiting for it.
    monkeypatch.setattr("graphify.llm.time.sleep", lambda _s: None)


def _docs(root, *names):
    out = []
    for name in names:
        f = root / name
        f.write_text(f"# {name}\n\nsome content\n", encoding="utf-8")
        out.append(f)
    return out


def _fake(nodes_for, acks=None):
    """Fake extract_files_direct: a node per file named in nodes_for, and a
    `files` acknowledgement per file named in acks ({name: entities}). acks=None
    sends no `files` key at all, like an old response."""
    def _call(chunk, **kwargs):
        names = [getattr(u, "path", u).name for u in chunk]
        result = {
            "nodes": [{"id": f"n_{n}", "source_file": n, "file_type": "document"}
                      for n in names if n in nodes_for],
            "edges": [], "hyperedges": [], "input_tokens": 1, "output_tokens": 1,
        }
        if acks is not None:
            result["files"] = [{"path": n, "entities": acks[n]} for n in names if n in acks]
        return result
    return _call


def _run(root, files, fake, chunk_size=2):
    with patch("graphify.llm.extract_files_direct", side_effect=fake):
        return extract_corpus_parallel(
            files, backend="kimi", root=root,
            token_budget=None, chunk_size=chunk_size, max_concurrency=1,
        )


def _names(paths):
    return {Path(p).name for p in paths}


# a. read and found nothing: not uncovered, recorded in empty_files
def test_empty_acknowledged_file_is_not_uncovered(tmp_path, capsys):
    files = _docs(tmp_path, "a.md", "empty.md")
    r = _run(tmp_path, files, _fake({"a.md"}, {"a.md": 3, "empty.md": 0}))
    assert r["uncovered_files"] == []
    assert _names(r["empty_files"]) == {"empty.md"}
    assert "produced no nodes" not in capsys.readouterr().err


# b. not acknowledged and no nodes: still uncovered (regression guard)
def test_unacknowledged_file_without_nodes_stays_uncovered(tmp_path, capsys):
    files = _docs(tmp_path, "a.md", "empty.md")
    r = _run(tmp_path, files, _fake({"a.md"}, {"a.md": 3}))
    assert _names(r["uncovered_files"]) == {"empty.md"}
    assert r.get("empty_files", []) == []
    assert "produced no nodes" in capsys.readouterr().err


# c. no "files" key: identical to current behaviour (regression guard)
def test_response_without_files_key_behaves_as_before(tmp_path):
    files = _docs(tmp_path, "a.md", "empty.md")
    r = _run(tmp_path, files, _fake({"a.md"}, acks=None))
    assert _names(r["uncovered_files"]) == {"empty.md"}
    assert r.get("empty_files", []) == []


# d. entities > 0 but no node: the mis-attribution case stays a failure
def test_acknowledged_with_entities_but_no_node_stays_uncovered(tmp_path):
    files = _docs(tmp_path, "a.md", "ghost.md")
    r = _run(tmp_path, files, _fake({"a.md"}, {"a.md": 3, "ghost.md": 2}))
    assert _names(r["uncovered_files"]) == {"ghost.md"}
    assert r.get("empty_files", []) == []


# d2. an acknowledgement for a path not sent in that chunk is ignored
def test_acknowledgement_for_a_path_not_in_the_chunk_is_ignored(tmp_path):
    files = _docs(tmp_path, "a.md", "other.md")

    def fake(chunk, **kwargs):
        names = [getattr(u, "path", u).name for u in chunk]
        if names == ["a.md"]:
            # a.md's response also claims other.md is empty; other.md went in a
            # different chunk, so the claim must not count
            return {"nodes": [{"id": "n_a", "source_file": "a.md", "file_type": "document"}],
                    "edges": [], "hyperedges": [], "input_tokens": 1, "output_tokens": 1,
                    "files": [{"path": "a.md", "entities": 1},
                              {"path": "other.md", "entities": 0}]}
        return {"nodes": [], "edges": [], "hyperedges": [], "input_tokens": 1, "output_tokens": 1}

    r = _run(tmp_path, files, fake, chunk_size=1)
    assert _names(r["uncovered_files"]) == {"other.md"}
    assert r.get("empty_files", []) == []


# e. a truncated chunk that acknowledges its file is still partial
def test_truncated_chunk_that_acknowledges_its_file_stays_partial(tmp_path):
    files = _docs(tmp_path, "empty.md")

    def fake(chunk, **kwargs):
        return {"nodes": [], "edges": [], "hyperedges": [], "input_tokens": 1,
                "output_tokens": 1, "finish_reason": "length",
                "files": [{"path": "empty.md", "entities": 0}]}

    r = _run(tmp_path, files, fake, chunk_size=1)
    assert _names(r["uncovered_files"]) == {"empty.md"}
    assert r.get("empty_files", []) == []
    # the helper cli.py uses to arm the shrink guard
    assert _names(_partial_source_files(r)) == {"empty.md"}


# --- through the real response handling (parse + hollow check + retry) ---

def _model_says(raw, calls):
    """Stand-in for a backend call: the model returns `raw`, parsed and hollow
    checked exactly as the real _call_* functions do."""
    def _call(api_key, model, user_message, *args, **kwargs):
        calls.append(user_message)
        result = _parse_llm_json(raw)
        result.update(input_tokens=1, output_tokens=1, model=model, finish_reason="stop")
        _mark_hollow(result, raw, "claude")
        return result
    return _call


def _run_backend(root, files, raw, calls):
    with patch("graphify.llm._call_claude", side_effect=_model_says(raw, calls)):
        return extract_corpus_parallel(
            files, backend="claude", api_key="sk-test", root=root,
            token_budget=None, chunk_size=len(files), max_concurrency=1,
        )


# The case from the issue: a chunk holding only an empty file.
def test_chunk_of_only_an_empty_file_succeeds_without_retry(tmp_path):
    robots = tmp_path / "robots.txt"
    robots.write_text("", encoding="utf-8")
    raw = ('{"nodes":[],"edges":[],"hyperedges":[],'
           '"files":[{"path":"robots.txt","entities":0}]}')
    calls = []
    r = _run_backend(tmp_path, [robots], raw, calls)
    assert r["uncovered_files"] == []
    assert _names(r["empty_files"]) == {"robots.txt"}
    assert _partial_source_files(r) == []
    assert len(calls) == 1, "an acknowledged-empty chunk must not be retried as hollow"


# A lazy answer that acknowledges only some files stays hollow and is retried.
def test_files_only_response_that_misses_a_file_is_still_hollow(tmp_path):
    a, b = _docs(tmp_path, "a.md", "b.md")
    raw = ('{"nodes":[],"edges":[],"hyperedges":[],'
           '"files":[{"path":"a.md","entities":0}]}')
    calls = []
    r = _run_backend(tmp_path, [a, b], raw, calls)
    assert len(calls) > 1, "a partly acknowledged empty answer must get the hollow retry"
    assert _names(r["uncovered_files"]) == {"a.md", "b.md"}
    assert r.get("empty_files", []) == []
    assert _names(_partial_source_files(r)) == {"a.md", "b.md"}


def test_files_only_response_is_not_hollow_but_empty_and_junk_are():
    ok = '{"nodes":[],"edges":[],"hyperedges":[],"files":[{"path":"robots.txt","entities":0}]}'
    assert not _response_is_hollow(ok, _parse_llm_json(ok))
    for raw in ('{"nodes":[],"edges":[],"hyperedges":[]}',
                '{"nodes":[],"edges":[],"hyperedges":[],"files":"all"}',
                '{"nodes":[],"edges":[],"hyperedges":[],"files":["robots.txt"]}',
                '{"nodes":[],"edges":[],"hyperedges":[],"files":[{"path":"x","entities":2}]}'):
        assert _response_is_hollow(raw, _parse_llm_json(raw)), raw


# --- CLI (same harness shape as tests/test_hollow_chunks_arm_shrink_guard.py) ---

def _cli(monkeypatch, tmp_path, names, fake_llm=None, uncovered=()):
    corpus = tmp_path / "corpus"
    corpus.mkdir(exist_ok=True)
    _docs(corpus, *names)
    out = tmp_path / "out"
    rec = {"called": False, "force": None}

    def _to_json(G, communities, output_path, *, force=False, **kwargs):
        rec["called"], rec["force"] = True, force
        return True

    monkeypatch.setattr("graphify.export.to_json", _to_json)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-fake-key")
    if fake_llm is not None:
        monkeypatch.setattr("graphify.llm.extract_files_direct", fake_llm)
    else:
        def _stub(paths, **kwargs):
            on_chunk = kwargs.get("on_chunk_done")
            if on_chunk:
                on_chunk(0, 1, {"nodes": [], "edges": [], "hyperedges": []})
            return {"nodes": [{"id": "s1", "source_file": str(corpus / names[0]),
                               "file_type": "document", "label": "x"}],
                    "edges": [], "hyperedges": [], "input_tokens": 1, "output_tokens": 1,
                    "uncovered_files": [str(corpus / n) for n in uncovered]}
        monkeypatch.setattr("graphify.llm.extract_corpus_parallel", _stub)
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)
    monkeypatch.setattr(mainmod.sys, "argv",
                        ["graphify", "extract", str(corpus), "--backend", "claude", "--out", str(out)])
    try:
        mainmod.main()
    except SystemExit as exc:
        rec["exit"] = exc.code
    return out, rec


# a2. end to end: an empty file no longer disarms force, so a smaller graph can be written
def test_extract_force_writes_when_an_empty_file_is_acknowledged(monkeypatch, tmp_path, capsys):
    out, rec = _cli(monkeypatch, tmp_path, ["README.md", "EMPTY.md"],
                    fake_llm=_fake({"README.md"}, {"README.md": 2, "EMPTY.md": 0}))
    assert rec["called"] and rec["force"] is True
    assert "semantic extraction is incomplete" not in capsys.readouterr().err


# f. the full list goes to uncovered_files.txt and is removed on a clean run
def test_uncovered_list_has_every_path_and_is_removed_on_a_clean_run(monkeypatch, tmp_path, capsys):
    names = [f"d{i}.md" for i in range(8)]
    out, rec = _cli(monkeypatch, tmp_path, ["keep.md", *names], uncovered=names)
    listing = out / "graphify-out" / "uncovered_files.txt"
    lines = listing.read_text(encoding="utf-8").splitlines()
    assert lines == sorted(names), "all 8 paths, relative to the corpus root"
    assert not any(Path(line).is_absolute() for line in lines)
    assert "uncovered_files.txt" in capsys.readouterr().err

    _cli(monkeypatch, tmp_path, ["keep.md", *names], uncovered=())
    assert not listing.exists()
