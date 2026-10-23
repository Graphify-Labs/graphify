"""Regression tests for #3640: `save-result` and `add` must accept their
free-text arguments (question, answer, node labels, URL, author, contributor)
from files instead of only the command line, so a skill that builds this
command from untrusted or unbounded free text never has to embed it inside a
shell-quoted argument (the injection vector reported in #3640)."""
from __future__ import annotations
import json
import pytest
import graphify.__main__ as mainmod


def _run(monkeypatch, capsys, *argv):
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)
    monkeypatch.setattr(mainmod.sys, "argv", ["graphify", *argv])
    with pytest.raises(SystemExit) as exc_info:
        mainmod.main()
    return exc_info.value.code, capsys.readouterr()


def _run_no_exit(monkeypatch, capsys, *argv):
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)
    monkeypatch.setattr(mainmod.sys, "argv", ["graphify", *argv])
    mainmod.main()
    return capsys.readouterr()


# ── save-result ───────────────────────────────────────────────────────────

def test_save_result_from_files(tmp_path, monkeypatch, capsys):
    qf = tmp_path / "q.txt"
    af = tmp_path / "a.txt"
    nf = tmp_path / "nodes.txt"
    qf.write_text("what does $(rm -rf /) do?", encoding="utf-8")
    af.write_text("it's a `backtick` and $(command) substitution risk", encoding="utf-8")
    nf.write_text("node_one\nnode_two\n", encoding="utf-8")
    mem = tmp_path / "memory"

    out = _run_no_exit(
        monkeypatch, capsys,
        "save-result",
        "--question-file", str(qf),
        "--answer-file", str(af),
        "--nodes-file", str(nf),
        "--memory-dir", str(mem),
    )
    assert "Saved to" in out.out
    saved = list(mem.glob("*.md"))
    assert len(saved) == 1
    content = saved[0].read_text(encoding="utf-8")
    assert "$(rm -rf /)" in content
    assert "$(command)" in content
    assert "node_one" in content and "node_two" in content


def test_save_result_nodes_file_accepts_multiple_paths(tmp_path, monkeypatch, capsys):
    qf = tmp_path / "q.txt"
    af = tmp_path / "a.txt"
    qf.write_text("q", encoding="utf-8")
    af.write_text("a", encoding="utf-8")
    nf1 = tmp_path / "n1.txt"
    nf2 = tmp_path / "n2.txt"
    nf1.write_text("alpha\n", encoding="utf-8")
    nf2.write_text("beta\n", encoding="utf-8")
    mem = tmp_path / "memory"

    out = _run_no_exit(
        monkeypatch, capsys,
        "save-result",
        "--question-file", str(qf),
        "--answer-file", str(af),
        "--nodes-file", str(nf1), str(nf2),
        "--memory-dir", str(mem),
    )
    content = next(mem.glob("*.md")).read_text(encoding="utf-8")
    assert "alpha" in content and "beta" in content


def test_save_result_requires_question_or_question_file(tmp_path, monkeypatch, capsys):
    af = tmp_path / "a.txt"
    af.write_text("a", encoding="utf-8")
    code, captured = _run(
        monkeypatch, capsys,
        "save-result", "--answer-file", str(af), "--memory-dir", str(tmp_path / "memory"),
    )
    assert code != 0
    assert "--question or --question-file is required" in captured.err


def test_save_result_rejects_empty_question_file(tmp_path, monkeypatch, capsys):
    qf = tmp_path / "q.txt"
    af = tmp_path / "a.txt"
    qf.write_text("   \n", encoding="utf-8")
    af.write_text("a", encoding="utf-8")
    code, captured = _run(
        monkeypatch, capsys,
        "save-result",
        "--question-file", str(qf), "--answer-file", str(af),
        "--memory-dir", str(tmp_path / "memory"),
    )
    assert code != 0
    assert "--question must not be empty" in captured.err


def test_save_result_missing_file_is_clean_error_not_traceback(tmp_path, monkeypatch, capsys):
    missing = tmp_path / "does-not-exist.txt"
    code, captured = _run(
        monkeypatch, capsys,
        "save-result",
        "--question", "q",
        "--answer-file", str(missing),
        "--memory-dir", str(tmp_path / "memory"),
    )
    assert code != 0
    assert "could not read --answer-file" in captured.err
    assert "Traceback" not in captured.err


def test_save_result_still_accepts_inline_args(tmp_path, monkeypatch, capsys):
    """No regression: the original --question/--answer form keeps working."""
    out = _run_no_exit(
        monkeypatch, capsys,
        "save-result",
        "--question", "q", "--answer", "a",
        "--memory-dir", str(tmp_path / "memory"),
    )
    assert "Saved to" in out.out


# ── add --from-file ──────────────────────────────────────────────────────

def test_add_from_file_reads_json_payload(tmp_path, monkeypatch, capsys):
    calls = {}

    def _fake_ingest(url, target_dir, author=None, contributor=None):
        calls["url"] = url
        calls["target_dir"] = target_dir
        calls["author"] = author
        calls["contributor"] = contributor
        return target_dir / "saved.md"

    import graphify.ingest as ingest_mod
    monkeypatch.setattr(ingest_mod, "ingest", _fake_ingest)

    payload = tmp_path / "payload.json"
    payload.write_text(json.dumps({
        "url": "https://example.com/a'; rm -rf ~ #",
        "author": "Robert'); DROP TABLE x; --",
        "contributor": "$(whoami)",
    }), encoding="utf-8")

    out = _run_no_exit(monkeypatch, capsys, "add", "--from-file", str(payload))
    assert "Saved to" in out.out
    assert calls["url"] == "https://example.com/a'; rm -rf ~ #"
    assert calls["author"] == "Robert'); DROP TABLE x; --"
    assert calls["contributor"] == "$(whoami)"


def test_add_from_file_requires_url_key(tmp_path, monkeypatch, capsys):
    payload = tmp_path / "payload.json"
    payload.write_text(json.dumps({"author": "A"}), encoding="utf-8")
    code, captured = _run(monkeypatch, capsys, "add", "--from-file", str(payload))
    assert code != 0
    assert "missing required key 'url'" in captured.err


def test_add_from_file_rejects_non_object_payload(tmp_path, monkeypatch, capsys):
    payload = tmp_path / "payload.json"
    payload.write_text(json.dumps(["not", "an", "object"]), encoding="utf-8")
    code, captured = _run(monkeypatch, capsys, "add", "--from-file", str(payload))
    assert code != 0
    assert "must be a JSON object" in captured.err


def test_add_still_accepts_inline_form(tmp_path, monkeypatch, capsys):
    """No regression: the original positional-url form keeps working."""
    calls = {}

    def _fake_ingest(url, target_dir, author=None, contributor=None):
        calls["url"] = url
        return target_dir / "saved.md"

    import graphify.ingest as ingest_mod
    monkeypatch.setattr(ingest_mod, "ingest", _fake_ingest)

    out = _run_no_exit(monkeypatch, capsys, "add", "https://example.com/page")
    assert "Saved to" in out.out
    assert calls["url"] == "https://example.com/page"
