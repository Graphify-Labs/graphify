"""`graphify token-guard`: Claude Code hooks that keep the context window small.

Hooks are driven through ``tokenguard.main`` with a synthetic stdin payload.
HOME, CLAUDE_CONFIG_DIR and the state dir all point into tmp_path, so nothing
here can touch the real ~/.claude or ~/.cache.
"""
import io
import json
import os
import time
from typing import Any

import pytest

from graphify import tokenguard as tg


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(home / ".claude"))
    monkeypatch.setenv("GRAPHIFY_TOKEN_GUARD_DIR", str(tmp_path / "state"))
    for name in ("GRAPHIFY_TOKEN_GUARD", "GRAPHIFY_TOKEN_GUARD_DAILY", "GRAPHIFY_CONTEXT_BUDGET",
                 "GRAPHIFY_CONTEXT_BUDGET_STEP", "GRAPHIFY_BASH_CAP"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr("graphify.install._resolve_graphify_exe",
                        lambda project=False: "graphify" if project else "/opt/bin/graphify")


class _Stdin:
    def __init__(self, data: bytes):
        self.buffer = io.BytesIO(data)


def run(sub, payload, monkeypatch, capsys) -> "tuple[int, Any]":
    """Run one hook; returns (exit code, parsed stdout JSON or None)."""
    data = payload if isinstance(payload, bytes) else json.dumps(payload).encode("utf-8")
    monkeypatch.setattr("sys.stdin", _Stdin(data))
    capsys.readouterr()
    code = tg.main([sub])
    out = capsys.readouterr().out
    return code, (json.loads(out) if out.strip() else None)


def read_payload(path, session="s1", agent=None, **tool_input: Any):
    p = {"session_id": session, "hook_event_name": "PreToolUse", "tool_name": "Read",
         "cwd": os.path.dirname(str(path)), "tool_input": {"file_path": str(path), **tool_input}}
    if agent:
        p["agent_id"] = agent
    return p


def denied(result):
    code, out = result
    assert code == 0
    if out is None:
        return False
    spec = out["hookSpecificOutput"]
    assert spec["hookEventName"] == "PreToolUse"
    assert spec["permissionDecision"] == "deny"
    return True


@pytest.fixture
def src(tmp_path):
    f = tmp_path / "proj" / "mod.py"
    f.parent.mkdir()
    f.write_text("".join(f"line {i}\n" for i in range(1, 301)), encoding="utf-8")
    return f


# --------------------------------------------------------------------------- #
# reread
# --------------------------------------------------------------------------- #
def test_reread_denies_once_then_allows(src, monkeypatch, capsys):
    assert not denied(run("reread", read_payload(src), monkeypatch, capsys))
    code, out = run("reread", read_payload(src), monkeypatch, capsys)
    assert denied((code, out))
    reason = out["hookSpecificOutput"]["permissionDecisionReason"]
    assert "already in context" in reason and "unchanged" in reason
    assert "will be allowed" in reason and os.path.realpath(src) in reason
    # Facts, not orders: this text is read by the model.
    assert "MUST" not in reason and "MANDATORY" not in reason
    # The immediate retry goes through, and so does every later read of this version.
    assert not denied(run("reread", read_payload(src), monkeypatch, capsys))
    assert not denied(run("reread", read_payload(src), monkeypatch, capsys))


def test_reread_changed_file_is_allowed_and_rearms(src, monkeypatch, capsys):
    assert not denied(run("reread", read_payload(src), monkeypatch, capsys))
    src.write_text("changed\n", encoding="utf-8")
    assert not denied(run("reread", read_payload(src), monkeypatch, capsys))
    # The new version was recorded: reading it again is the repeat.
    assert denied(run("reread", read_payload(src), monkeypatch, capsys))


def test_reread_same_size_new_mtime_is_allowed(src, monkeypatch, capsys):
    assert not denied(run("reread", read_payload(src), monkeypatch, capsys))
    st = src.stat()
    os.utime(src, ns=(st.st_atime_ns, st.st_mtime_ns + 5_000_000_000))
    assert not denied(run("reread", read_payload(src), monkeypatch, capsys))


def test_reread_range_coverage(src, monkeypatch, capsys):
    assert not denied(run("reread", read_payload(src, offset=10, limit=50), monkeypatch, capsys))
    # Not covered: extends past the earlier range, or lies outside it.
    assert not denied(run("reread", read_payload(src, offset=40, limit=50), monkeypatch, capsys))
    assert not denied(run("reread", read_payload(src, offset=200, limit=10), monkeypatch, capsys))
    # 10-59 and 40-89 merged: 20-79 is inside.
    code, out = run("reread", read_payload(src, offset=20, limit=60), monkeypatch, capsys)
    assert denied((code, out))
    assert "lines 20-79" in out["hookSpecificOutput"]["permissionDecisionReason"]


def test_reread_whole_file_read_covers_ranges(src, monkeypatch, capsys):
    assert not denied(run("reread", read_payload(src), monkeypatch, capsys))
    assert denied(run("reread", read_payload(src, offset=120, limit=30), monkeypatch, capsys))


def test_reread_range_does_not_cover_whole_file(src, monkeypatch, capsys):
    assert not denied(run("reread", read_payload(src, offset=1, limit=100), monkeypatch, capsys))
    assert not denied(run("reread", read_payload(src), monkeypatch, capsys))


def test_reread_denied_read_is_not_recorded(src, monkeypatch, capsys):
    """A denied request adds no coverage; only allowed reads are recorded."""
    assert not denied(run("reread", read_payload(src, offset=1, limit=10), monkeypatch, capsys))
    assert denied(run("reread", read_payload(src, offset=1, limit=10), monkeypatch, capsys))
    rec_dir = os.path.join(os.environ["GRAPHIFY_TOKEN_GUARD_DIR"], "reads", "s1")
    (rec_file,) = os.listdir(rec_dir)
    rec = json.loads(open(os.path.join(rec_dir, rec_file), encoding="utf-8").read())
    assert rec["ranges"] == [[1, 11]] and rec["denied"] is True


def test_reread_per_agent_and_per_session(src, monkeypatch, capsys):
    assert not denied(run("reread", read_payload(src), monkeypatch, capsys))
    # A subagent has its own context: its first read is not a repeat.
    assert not denied(run("reread", read_payload(src, agent="agent-a"), monkeypatch, capsys))
    assert not denied(run("reread", read_payload(src, agent="agent-b"), monkeypatch, capsys))
    assert not denied(run("reread", read_payload(src, session="s2"), monkeypatch, capsys))
    assert denied(run("reread", read_payload(src, agent="agent-a"), monkeypatch, capsys))
    assert denied(run("reread", read_payload(src), monkeypatch, capsys))


@pytest.mark.parametrize("name", ["shot.PNG", "doc.pdf", "nb.ipynb", "pic.jpeg"])
def test_reread_never_denies_non_text(tmp_path, name, monkeypatch, capsys):
    f = tmp_path / name
    f.write_bytes(b"x" * 100)
    for _ in range(3):
        assert not denied(run("reread", read_payload(f), monkeypatch, capsys))


def test_reread_never_denies_without_session(src, monkeypatch, capsys):
    p = read_payload(src)
    del p["session_id"]
    for _ in range(3):
        assert not denied(run("reread", p, monkeypatch, capsys))
    assert not os.path.exists(os.path.join(os.environ["GRAPHIFY_TOKEN_GUARD_DIR"], "reads"))


def test_reread_disabled_by_env(src, monkeypatch, capsys):
    monkeypatch.setenv("GRAPHIFY_TOKEN_GUARD", "0")
    for _ in range(3):
        assert not denied(run("reread", read_payload(src), monkeypatch, capsys))


def test_reread_large_unlimited_read_is_not_judged(tmp_path, monkeypatch, capsys):
    """Read refuses an unlimited read of a large file, so nothing entered context."""
    big = tmp_path / "big.log"
    big.write_text("x" * 99 + "\n" * 1 + ("y" * 99 + "\n") * 2000, encoding="utf-8")
    for _ in range(3):
        assert not denied(run("reread", read_payload(big), monkeypatch, capsys))
    assert not denied(run("reread", read_payload(big, offset=1, limit=100), monkeypatch, capsys))
    assert denied(run("reread", read_payload(big, offset=1, limit=100), monkeypatch, capsys))


def test_reread_missing_file_and_other_tools(tmp_path, src, monkeypatch, capsys):
    assert run("reread", read_payload(tmp_path / "nope.py"), monkeypatch, capsys) == (0, None)
    other = read_payload(src)
    other["tool_name"] = "Grep"
    for _ in range(2):
        assert run("reread", other, monkeypatch, capsys) == (0, None)


def test_reread_symlink_and_relative_path_resolve_to_same_file(src, tmp_path, monkeypatch, capsys):
    assert not denied(run("reread", read_payload(src), monkeypatch, capsys))
    rel = read_payload(src)
    rel["tool_input"]["file_path"] = "mod.py"
    assert denied(run("reread", rel, monkeypatch, capsys))


def test_reread_corrupt_state_fails_open(src, monkeypatch, capsys):
    assert not denied(run("reread", read_payload(src), monkeypatch, capsys))
    rec_dir = os.path.join(os.environ["GRAPHIFY_TOKEN_GUARD_DIR"], "reads", "s1")
    (rec_file,) = os.listdir(rec_dir)
    with open(os.path.join(rec_dir, rec_file), "w", encoding="utf-8") as fh:
        fh.write("{not json")
    assert not denied(run("reread", read_payload(src), monkeypatch, capsys))


def test_reread_unwritable_state_never_denies(src, tmp_path, monkeypatch, capsys):
    blocker = tmp_path / "blocker"
    blocker.write_text("a file where the state dir should be", encoding="utf-8")
    monkeypatch.setenv("GRAPHIFY_TOKEN_GUARD_DIR", str(blocker))
    for _ in range(3):
        assert run("reread", read_payload(src), monkeypatch, capsys) == (0, None)


@pytest.mark.parametrize("sub", ["reread", "reset", "budget", "bash-cap", "daily"])
@pytest.mark.parametrize("garbage", [b"", b"not json", b"[1, 2]", b"\xff\xfe\x00", b'"str"',
                                     b'{"session_id": 5, "tool_input": "x", "tool_response": 3}',
                                     b'{"session_id": "s", "tool_input": {"file_path": 7, "offset": "a"}}'])
def test_hooks_fail_open_on_garbage_stdin(sub, garbage, monkeypatch, capsys):
    assert run(sub, garbage, monkeypatch, capsys) == (0, None)


def test_reread_bad_offset_limit_fails_open(src, monkeypatch, capsys):
    cases: "list[dict[str, Any]]" = [
        {"offset": "abc"}, {"limit": []}, {"limit": 0}, {"limit": -5}, {"offset": True}]
    for bad in cases:
        for _ in range(2):
            assert run("reread", read_payload(src, **bad), monkeypatch, capsys) == (0, None)


# --------------------------------------------------------------------------- #
# reset
# --------------------------------------------------------------------------- #
def _start(source, session="s1"):
    return {"session_id": session, "hook_event_name": "SessionStart", "source": source}


def test_reset_on_compact_clears_session_and_its_subagents(src, monkeypatch, capsys):
    for agent in (None, "agent-a"):
        assert not denied(run("reread", read_payload(src, agent=agent), monkeypatch, capsys))
    assert not denied(run("reread", read_payload(src, session="s2"), monkeypatch, capsys))
    assert run("reset", _start("compact"), monkeypatch, capsys) == (0, None)
    # Content is gone from context: the next read is a first read again.
    assert not denied(run("reread", read_payload(src), monkeypatch, capsys))
    assert not denied(run("reread", read_payload(src, agent="agent-a"), monkeypatch, capsys))
    # Another session keeps its records.
    assert denied(run("reread", read_payload(src, session="s2"), monkeypatch, capsys))


@pytest.mark.parametrize("source", ["startup", "resume", "clear", "fork", None])
def test_reset_ignores_other_sources(src, source, monkeypatch, capsys):
    assert not denied(run("reread", read_payload(src), monkeypatch, capsys))
    assert run("reset", _start(source), monkeypatch, capsys) == (0, None)
    assert denied(run("reread", read_payload(src), monkeypatch, capsys))


def test_reset_does_not_touch_session_with_prefix_name(src, monkeypatch, capsys):
    assert not denied(run("reread", read_payload(src, session="s1x"), monkeypatch, capsys))
    run("reset", _start("compact", session="s1"), monkeypatch, capsys)
    assert denied(run("reread", read_payload(src, session="s1x"), monkeypatch, capsys))


# --------------------------------------------------------------------------- #
# budget
# --------------------------------------------------------------------------- #
def _assistant(inp=0, create=0, read=0, **extra):
    return {"type": "assistant", "isSidechain": False, **extra,
            "message": {"role": "assistant", "model": "m", "content": [],
                        "usage": {"input_tokens": inp, "cache_creation_input_tokens": create,
                                  "cache_read_input_tokens": read, "output_tokens": 999_999}}}


def _transcript(tmp_path, *entries, name="t.jsonl"):
    p = tmp_path / name
    with open(p, "w", encoding="utf-8") as fh:
        for e in entries:
            fh.write((e if isinstance(e, str) else json.dumps(e)) + "\n")
    return p


def _append(path, *entries):
    with open(path, "a", encoding="utf-8") as fh:
        for e in entries:
            fh.write(json.dumps(e) + "\n")


def _prompt(transcript, session="s1"):
    return {"session_id": session, "hook_event_name": "UserPromptSubmit",
            "transcript_path": str(transcript), "prompt": "hi"}


def test_transcript_context_sums_input_and_cache_tokens(tmp_path):
    t = _transcript(tmp_path, _assistant(10, 20, 30), {"type": "user", "message": {"content": "x"}},
                    _assistant(5, 1000, 200_000), {"type": "user", "message": {"content": "later"}})
    assert tg.transcript_context_tokens(str(t)) == 201_005


def test_transcript_context_skips_sidechain_synthetic_and_partial_lines(tmp_path):
    t = _transcript(tmp_path, _assistant(1, 2, 300_000),
                    _assistant(9, 9, 9, isSidechain=True),
                    _assistant(0, 0, 0),
                    '{"type":"assistant","message":{"usage":{"input_tokens": 5')
    assert tg.transcript_context_tokens(str(t)) == 300_003


def test_transcript_context_unknown(tmp_path):
    assert tg.transcript_context_tokens(str(_transcript(tmp_path, {"type": "user"}))) is None
    assert tg.transcript_context_tokens(str(_transcript(tmp_path, name="empty.jsonl"))) is None


def test_budget_silent_below_threshold(tmp_path, monkeypatch, capsys):
    t = _transcript(tmp_path, _assistant(100, 0, 150_000))
    assert run("budget", _prompt(t), monkeypatch, capsys) == (0, None)


def test_budget_levels_once_each_and_rearm(tmp_path, monkeypatch, capsys):
    t = _transcript(tmp_path, _assistant(10, 5_000, 200_000))
    code, out = run("budget", _prompt(t), monkeypatch, capsys)
    assert code == 0
    assert out["hookSpecificOutput"]["hookEventName"] == "UserPromptSubmit"
    text = out["hookSpecificOutput"]["additionalContext"]
    assert out["systemMessage"] == text
    assert "205k tokens" in text and "re-reads all of it" in text
    assert "/compact" in text and "graphify handoff" in text and "graphify-out/HANDOFF.md" in text
    assert "MUST" not in text and "MANDATORY" not in text
    # Same level: once only.
    assert run("budget", _prompt(t), monkeypatch, capsys) == (0, None)
    _append(t, _assistant(10, 0, 280_000))
    assert run("budget", _prompt(t), monkeypatch, capsys) == (0, None)
    # Next step (threshold + 100k).
    _append(t, _assistant(10, 0, 310_000))
    assert "310k" in run("budget", _prompt(t), monkeypatch, capsys)[1]["systemMessage"]
    assert run("budget", _prompt(t), monkeypatch, capsys) == (0, None)
    # Jumping several steps announces once.
    _append(t, _assistant(10, 0, 620_000))
    assert "620k" in run("budget", _prompt(t), monkeypatch, capsys)[1]["systemMessage"]
    assert run("budget", _prompt(t), monkeypatch, capsys) == (0, None)
    # Compaction: context falls back, silently, and the levels re-arm.
    _append(t, _assistant(10, 0, 40_000))
    assert run("budget", _prompt(t), monkeypatch, capsys) == (0, None)
    _append(t, _assistant(10, 0, 230_000))
    assert "230k" in run("budget", _prompt(t), monkeypatch, capsys)[1]["systemMessage"]
    assert run("budget", _prompt(t), monkeypatch, capsys) == (0, None)


def test_budget_partial_shrink_rearms_higher_levels_only(tmp_path, monkeypatch, capsys):
    t = _transcript(tmp_path, _assistant(0, 0, 450_000))
    assert run("budget", _prompt(t), monkeypatch, capsys)[1] is not None
    _append(t, _assistant(0, 0, 250_000))
    assert run("budget", _prompt(t), monkeypatch, capsys) == (0, None)
    _append(t, _assistant(0, 0, 350_000))
    assert "350k" in run("budget", _prompt(t), monkeypatch, capsys)[1]["systemMessage"]


def test_budget_compact_boundary_rearms(tmp_path, monkeypatch, capsys):
    t = _transcript(tmp_path, _assistant(0, 0, 250_000))
    assert run("budget", _prompt(t), monkeypatch, capsys)[1] is not None
    _append(t, {"type": "system", "subtype": "compact_boundary"}, {"type": "user"})
    assert run("budget", _prompt(t), monkeypatch, capsys) == (0, None)
    _append(t, _assistant(0, 0, 260_000))
    assert run("budget", _prompt(t), monkeypatch, capsys)[1] is not None


def test_budget_env_threshold_step_and_sessions(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("GRAPHIFY_CONTEXT_BUDGET", "1000")
    monkeypatch.setenv("GRAPHIFY_CONTEXT_BUDGET_STEP", "500")
    t = _transcript(tmp_path, _assistant(0, 0, 1_200))
    assert run("budget", _prompt(t), monkeypatch, capsys)[1] is not None
    # Levels are per session.
    assert run("budget", _prompt(t, session="s2"), monkeypatch, capsys)[1] is not None
    _append(t, _assistant(0, 0, 1_499))
    assert run("budget", _prompt(t), monkeypatch, capsys) == (0, None)
    _append(t, _assistant(0, 0, 1_500))
    assert run("budget", _prompt(t), monkeypatch, capsys)[1] is not None
    # Unparseable values fall back to the defaults; 0 turns the hook off.
    monkeypatch.setenv("GRAPHIFY_CONTEXT_BUDGET", "lots")
    assert run("budget", _prompt(t, session="s3"), monkeypatch, capsys) == (0, None)
    monkeypatch.setenv("GRAPHIFY_CONTEXT_BUDGET", "0")
    assert run("budget", _prompt(t, session="s4"), monkeypatch, capsys) == (0, None)


def test_budget_disabled_missing_transcript_or_session(tmp_path, monkeypatch, capsys):
    t = _transcript(tmp_path, _assistant(0, 0, 900_000))
    assert run("budget", _prompt(tmp_path / "missing.jsonl"), monkeypatch, capsys) == (0, None)
    no_session = _prompt(t)
    del no_session["session_id"]
    assert run("budget", no_session, monkeypatch, capsys) == (0, None)
    monkeypatch.setenv("GRAPHIFY_TOKEN_GUARD", "0")
    assert run("budget", _prompt(t), monkeypatch, capsys) == (0, None)


def test_budget_reads_only_the_tail_of_a_large_transcript(tmp_path, monkeypatch, capsys):
    """~40 MB of earlier conversation; the answer is in the last chunk."""
    t = tmp_path / "big.jsonl"
    filler = json.dumps({"type": "user", "message": {"content": "x" * 4000}}) + "\n"
    with open(t, "w", encoding="utf-8") as fh:
        fh.write(json.dumps(_assistant(0, 0, 111)) + "\n")
        block = filler * 250
        for _ in range(40):
            fh.write(block)
        # A 3 MB line (one tool result) spans several 1 MB chunks.
        fh.write(json.dumps({"type": "user", "toolUseResult": {"stdout": "y" * 3_000_000}}) + "\n")
        fh.write(json.dumps(_assistant(7, 0, 400_000)) + "\n")
        fh.write(filler * 300)
    assert t.stat().st_size > 40_000_000

    read_bytes = []
    real_open = open

    class Counting:
        def __init__(self, fh):
            self._fh = fh

        def read(self, n=-1):
            data = self._fh.read(n)
            read_bytes.append(len(data))
            return data

        def __getattr__(self, name):
            return getattr(self._fh, name)

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            self._fh.close()

    def counting_open(path, mode="r", *a, **kw):
        fh = real_open(path, mode, *a, **kw)
        return Counting(fh) if str(path) == str(t) else fh

    monkeypatch.setattr("builtins.open", counting_open)
    started = time.perf_counter()
    code, out = run("budget", _prompt(t), monkeypatch, capsys)
    elapsed = time.perf_counter() - started
    assert "400k" in out["systemMessage"]
    assert sum(read_bytes) <= 6 * (1 << 20), sum(read_bytes)
    assert elapsed < 2.0


def test_transcript_scan_gives_up_after_max_scan(tmp_path):
    t = tmp_path / "t.jsonl"
    with open(t, "w", encoding="utf-8") as fh:
        fh.write(json.dumps(_assistant(0, 0, 500_000)) + "\n")
        fh.write((json.dumps({"type": "user", "message": {"content": "x" * 1000}}) + "\n") * 4000)
    assert tg.transcript_context_tokens(str(t), max_scan=1 << 20) is None
    assert tg.transcript_context_tokens(str(t)) == 500_000


def test_transcript_line_split_across_chunk_boundary(tmp_path, monkeypatch):
    monkeypatch.setattr(tg, "_TRANSCRIPT_CHUNK", 64)
    t = _transcript(tmp_path, _assistant(1, 2, 3), _assistant(100, 200, 300),
                    {"type": "user", "message": {"content": "tail " * 40}})
    assert tg.transcript_context_tokens(str(t)) == 600


# --------------------------------------------------------------------------- #
# bash-cap
# --------------------------------------------------------------------------- #
def _bash(stdout="", stderr="", session="s1", tool_use_id="toolu_01", **extra):
    return {"session_id": session, "hook_event_name": "PostToolUse", "tool_name": "Bash",
            "tool_use_id": tool_use_id, "tool_input": {"command": "make"},
            "tool_response": {"stdout": stdout, "stderr": stderr, "interrupted": False,
                              "isImage": False, "noOutputExpected": False, **extra}}


def test_bash_cap_leaves_small_output_alone(monkeypatch, capsys):
    assert run("bash-cap", _bash("x" * 19_000, "e" * 1_000), monkeypatch, capsys) == (0, None)
    assert not os.path.exists(os.path.join(os.environ["GRAPHIFY_TOKEN_GUARD_DIR"], "outputs"))


def test_bash_cap_replaces_large_output_with_head_and_tail(monkeypatch, capsys):
    lines = "".join(f"row {i:06d}\n" for i in range(10_000))  # 110k chars
    code, out = run("bash-cap", _bash(lines), monkeypatch, capsys)
    spec = out["hookSpecificOutput"]
    assert code == 0 and spec["hookEventName"] == "PostToolUse"
    updated = spec["updatedToolOutput"]
    # The Bash output shape is kept: same keys, same non-text values.
    assert updated == {**_bash()["tool_response"], "stdout": updated["stdout"]}
    shown = updated["stdout"]
    assert len(shown) < 20_000 + 400
    assert shown.startswith("row 000000\n") and shown.endswith("row 009999\n")
    # Whole lines on both sides of the note.
    head, note, tail = shown.partition("[graphify token-guard:")
    assert head.endswith("\n") and tail.split("]\n", 1)[1].startswith("row ")
    assert "characters omitted" in tail and "printed 110000" in tail
    saved = tail.split("full output saved to ", 1)[1].split("]\n", 1)[0]
    assert saved.startswith(os.environ["GRAPHIFY_TOKEN_GUARD_DIR"].replace("\\", "/"))
    assert saved.endswith("/outputs/s1/toolu_01.txt")
    assert open(saved, encoding="utf-8").read() == lines
    omitted = int(tail.split(" characters omitted")[0].strip())
    assert omitted == len(lines) - len(head) - len(tail.split("]\n", 1)[1])


def test_bash_cap_env_and_stderr(monkeypatch, capsys):
    monkeypatch.setenv("GRAPHIFY_BASH_CAP", "1000")
    code, out = run("bash-cap", _bash("o" * 5_000, "e" * 5_000, tool_use_id="toolu_02"), monkeypatch, capsys)
    updated = out["hookSpecificOutput"]["updatedToolOutput"]
    assert len(updated["stdout"]) < 750 + 300 and len(updated["stderr"]) < 250 + 300
    assert "graphify token-guard" in updated["stdout"] and "graphify token-guard" in updated["stderr"]
    saved = os.path.join(os.environ["GRAPHIFY_TOKEN_GUARD_DIR"], "outputs", "s1", "toolu_02.txt")
    assert open(saved, encoding="utf-8").read() == "o" * 5_000 + "\n--- stderr ---\n" + "e" * 5_000
    # Short stderr next to long stdout is kept whole.
    code, out = run("bash-cap", _bash("o" * 5_000, "warning: x"), monkeypatch, capsys)
    assert out["hookSpecificOutput"]["updatedToolOutput"]["stderr"] == "warning: x"
    monkeypatch.setenv("GRAPHIFY_BASH_CAP", "0")
    assert run("bash-cap", _bash("o" * 50_000), monkeypatch, capsys) == (0, None)
    monkeypatch.setenv("GRAPHIFY_BASH_CAP", "1000")
    monkeypatch.setenv("GRAPHIFY_TOKEN_GUARD", "0")
    assert run("bash-cap", _bash("o" * 50_000), monkeypatch, capsys) == (0, None)


def test_bash_cap_skips_images_other_tools_and_odd_shapes(monkeypatch, capsys):
    big = "o" * 50_000
    assert run("bash-cap", _bash(big, isImage=True), monkeypatch, capsys) == (0, None)
    other = _bash(big)
    other["tool_name"] = "mcp__x__y"
    assert run("bash-cap", other, monkeypatch, capsys) == (0, None)
    odd = _bash(big)
    odd["tool_response"] = big
    assert run("bash-cap", odd, monkeypatch, capsys) == (0, None)
    odd["tool_response"] = {"stdout": big}
    assert run("bash-cap", odd, monkeypatch, capsys) == (0, None)


def test_bash_cap_keeps_original_when_output_cannot_be_saved(tmp_path, monkeypatch, capsys):
    blocker = tmp_path / "blocker"
    blocker.write_text("x", encoding="utf-8")
    monkeypatch.setenv("GRAPHIFY_TOKEN_GUARD_DIR", str(blocker))
    assert run("bash-cap", _bash("o" * 50_000), monkeypatch, capsys) == (0, None)


def test_bash_cap_non_ascii_output_round_trips(monkeypatch, capsys):
    text = "çğış — ✓\n" * 5_000
    code, out = run("bash-cap", _bash(text), monkeypatch, capsys)
    shown = out["hookSpecificOutput"]["updatedToolOutput"]["stdout"]
    assert shown.startswith("çğış — ✓\n") and shown.endswith("çğış — ✓\n")


# --------------------------------------------------------------------------- #
# savings ledger
# --------------------------------------------------------------------------- #
DAY = 86400
T0 = time.mktime((2026, 3, 10, 12, 0, 0, 0, 0, -1))  # local noon: day offsets stay clear of DST shifts


@pytest.fixture
def clock(monkeypatch):
    """Sets the module's clock; `clock(n)` moves to noon, n days after 2026-03-10."""
    def at(days=0):
        monkeypatch.setattr(tg, "_now", lambda: T0 + days * DAY)
    at(0)
    return at


def ledger(day="2026-03-10"):
    path = os.path.join(os.environ["GRAPHIFY_TOKEN_GUARD_DIR"], "savings", day + ".jsonl")
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as fh:
        return [json.loads(line) for line in fh]


def test_ledger_bash_cap_logs_chars_omitted(clock, monkeypatch, capsys):
    assert run("bash-cap", _bash("x" * 100), monkeypatch, capsys) == (0, None)
    assert ledger() == []
    lines = "".join(f"row {i:06d}\n" for i in range(10_000))
    _, out = run("bash-cap", _bash(lines), monkeypatch, capsys)
    updated = out["hookSpecificOutput"]["updatedToolOutput"]
    (event,) = ledger()
    assert event == {"ts": int(T0), "kind": "bash-cap", "session": "s1",
                     "chars": len(lines) - len(updated["stdout"]) - len(updated["stderr"])}
    assert 89_000 < event["chars"] < 91_000


def test_ledger_reread_deny_then_retry_nets_to_zero(src, clock, monkeypatch, capsys):
    size = len(src.read_text(encoding="utf-8"))
    assert not denied(run("reread", read_payload(src), monkeypatch, capsys))
    assert ledger() == []
    assert denied(run("reread", read_payload(src), monkeypatch, capsys))
    assert ledger() == [{"ts": int(T0), "kind": "reread", "chars": size, "session": "s1"}]
    assert not denied(run("reread", read_payload(src), monkeypatch, capsys))
    events = ledger()
    assert [(e["kind"], e["chars"]) for e in events] == [("reread", size), ("reread-retry", -size)]
    # Later reads of this version are plain reads: nothing more is logged.
    assert not denied(run("reread", read_payload(src), monkeypatch, capsys))
    assert ledger() == events


def test_ledger_reread_is_sized_by_the_requested_range(src, clock, monkeypatch, capsys):
    assert not denied(run("reread", read_payload(src), monkeypatch, capsys))
    assert denied(run("reread", read_payload(src, offset=1, limit=9), monkeypatch, capsys))
    assert ledger()[0]["chars"] == len("line 1\n") * 9
    # A read outside what was read before is not a retry.
    assert not denied(run("reread", read_payload(src, offset=5000, limit=5), monkeypatch, capsys))
    assert len(ledger()) == 1
    # A retry that brings back less than was denied gives back only that much.
    assert not denied(run("reread", read_payload(src, offset=1, limit=2), monkeypatch, capsys))
    assert [(e["kind"], e["chars"]) for e in ledger()] == [("reread", 63), ("reread-retry", -14)]


def test_ledger_reread_keys_subagents_separately(src, clock, monkeypatch, capsys):
    for _ in range(2):
        run("reread", read_payload(src, agent="agent-a"), monkeypatch, capsys)
    (event,) = ledger()
    assert event["session"].startswith("s1-") and "agent-a" not in event["session"]


def test_ledger_budget_notice_is_count_only(tmp_path, clock, monkeypatch, capsys):
    t = _transcript(tmp_path, _assistant(0, 0, 250_000))
    assert run("budget", _prompt(t), monkeypatch, capsys)[1] is not None
    assert run("budget", _prompt(t), monkeypatch, capsys) == (0, None)
    assert ledger() == [{"ts": int(T0), "kind": "budget", "chars": 0, "session": "s1"}]


def test_ledger_holds_no_content_paths_commands_or_prompts(tmp_path, clock, monkeypatch, capsys):
    secret = tmp_path / "SECRETNAME.py"
    secret.write_text("SECRETBODY = 1\n" * 50, encoding="utf-8")
    for _ in range(3):
        run("reread", read_payload(secret), monkeypatch, capsys)
    payload = _bash("SECRETOUT\n" * 5_000, "SECRETERR\n" * 5_000)
    payload["tool_input"]["command"] = "SECRETCMD"
    assert run("bash-cap", payload, monkeypatch, capsys)[1] is not None
    prompt = _prompt(_transcript(tmp_path, _assistant(0, 0, 250_000)))
    prompt["prompt"] = "SECRETPROMPT"
    assert run("budget", prompt, monkeypatch, capsys)[1] is not None
    raw = open(os.path.join(os.environ["GRAPHIFY_TOKEN_GUARD_DIR"], "savings", "2026-03-10.jsonl"),
               encoding="utf-8").read()
    assert "SECRET" not in raw and str(tmp_path) not in raw
    events = [json.loads(line) for line in raw.splitlines()]
    assert [e["kind"] for e in events] == ["reread", "reread-retry", "bash-cap", "budget"]
    for e in events:
        assert set(e) == {"ts", "kind", "chars", "session"}
        assert isinstance(e["ts"], int) and isinstance(e["chars"], int) and e["session"] == "s1"


def test_ledger_failure_does_not_change_the_hook_result(src, clock, monkeypatch, capsys):
    root = os.environ["GRAPHIFY_TOKEN_GUARD_DIR"]
    os.makedirs(root)
    with open(os.path.join(root, "savings"), "w") as fh:
        fh.write("a file where the ledger dir should be")
    assert not denied(run("reread", read_payload(src), monkeypatch, capsys))
    assert denied(run("reread", read_payload(src), monkeypatch, capsys))
    assert run("bash-cap", _bash("o" * 50_000), monkeypatch, capsys)[1] is not None


def test_ledger_appends_from_parallel_processes_stay_whole_lines(clock):
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(8) as pool:
        list(pool.map(lambda i: tg._ledger_append("bash-cap", i, "s1"), range(400)))
    events = ledger()
    assert sorted(e["chars"] for e in events) == list(range(400))


def test_ledger_files_past_retention_are_pruned_on_a_new_day(clock):
    d = os.path.join(os.environ["GRAPHIFY_TOKEN_GUARD_DIR"], "savings")
    os.makedirs(d)
    for name in ("2025-12-09.jsonl", "2025-12-11.jsonl", "notes.txt"):
        open(os.path.join(d, name), "w").close()
    tg._ledger_append("budget", 0, "s1")  # 2026-03-10: 90 days back is 2025-12-10
    assert sorted(os.listdir(d)) == ["2025-12-11.jsonl", "2026-03-10.jsonl", "notes.txt"]


# --------------------------------------------------------------------------- #
# savings
# --------------------------------------------------------------------------- #
def _seed(clock):
    """Day 0: one cap (4000) and a denied read (400). Day 2: denied read (800)
    retried (-800), a budget notice, and a line of junk."""
    clock(0)
    tg._ledger_append("bash-cap", 4000, "s1")
    tg._ledger_append("reread", 400, "s1")
    clock(2)
    tg._ledger_append("reread", 800, "s2")
    tg._ledger_append("reread-retry", -800, "s2")
    tg._ledger_append("budget", 0, "s2")
    with open(os.path.join(os.environ["GRAPHIFY_TOKEN_GUARD_DIR"], "savings", "2026-03-12.jsonl"), "a") as fh:
        fh.write('not json\n{"kind": "other", "chars": 9}\n{"kind": "reread", "chars": "many"}\n')


def test_savings_json_shape_and_aggregation(clock, capsys):
    _seed(clock)
    clock(3)
    capsys.readouterr()
    assert tg.main(["savings", "--json"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert list(report) == ["days", "from", "to", "chars_per_token", "by_day", "total", "note"]
    assert (report["days"], report["from"], report["to"]) == (7, "2026-03-07", "2026-03-13")
    assert report["chars_per_token"] == 4
    assert "larger than the direct figure" in report["note"] and "No multiplier" in report["note"]
    first, second = report["by_day"]
    assert first == {
        "date": "2026-03-10", "events": 2, "chars": 4400, "estimated_tokens": 1100,
        "bash_capped": 1, "reads_skipped": 1, "budget_notices": 0,
        "kinds": {"bash-cap": {"events": 1, "chars": 4000}, "reread": {"events": 1, "chars": 400}},
    }
    assert second == {
        "date": "2026-03-12", "events": 3, "chars": 0, "estimated_tokens": 0,
        "bash_capped": 0, "reads_skipped": 0, "budget_notices": 1,
        "kinds": {"reread": {"events": 1, "chars": 800}, "reread-retry": {"events": 1, "chars": -800},
                  "budget": {"events": 1, "chars": 0}},
    }
    total = report["total"]
    assert (total["events"], total["chars"], total["estimated_tokens"]) == (5, 4400, 1100)
    assert (total["bash_capped"], total["reads_skipped"], total["budget_notices"]) == (1, 1, 1)


def test_savings_days_window_and_text_output(clock, capsys):
    _seed(clock)
    clock(3)
    capsys.readouterr()
    assert tg.main(["savings", "--days", "2", "--json"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert [d["date"] for d in report["by_day"]] == ["2026-03-12"] and report["from"] == "2026-03-12"
    assert tg.main(["savings", "--days=1"]) == 0
    assert "nothing recorded" in capsys.readouterr().out
    assert tg.main(["savings"]) == 0
    out = capsys.readouterr().out
    assert "2026-03-07 to 2026-03-13 (7 days" in out
    rows = {line.split()[0]: line.split()[1:] for line in out.splitlines() if line.startswith("  20") or
            line.startswith("  total")}
    assert rows["2026-03-10"] == ["1", "4000", "1", "400", "0", "4400", "1100"]
    assert rows["2026-03-12"] == ["0", "0", "0", "0", "1", "0", "0"]
    assert rows["total"] == ["1", "4000", "1", "400", "1", "4400", "1100"]
    assert "Tokens are an estimate: characters / 4." in out
    assert "Lower bound:" in out and "larger than the direct figure" in out


def test_savings_with_no_ledger_and_bad_arguments(clock, capsys):
    assert tg.main(["savings"]) == 0
    assert "nothing recorded" in capsys.readouterr().out
    assert tg.main(["savings", "--json"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["by_day"] == [] and report["total"]["events"] == 0
    for bad in (["--days"], ["--days", "0"], ["--days", "x"], ["--days=-3"], ["--project"]):
        assert tg.main(["savings", *bad]) == 2
    assert not os.path.exists(os.environ["GRAPHIFY_TOKEN_GUARD_DIR"])


# --------------------------------------------------------------------------- #
# daily
# --------------------------------------------------------------------------- #
def test_daily_reports_previous_days_once_per_day(clock, monkeypatch, capsys):
    _seed(clock)
    clock(3)
    code, out = run("daily", _start("startup"), monkeypatch, capsys)
    # User-visible only: nothing that would enter the model's context.
    assert code == 0 and list(out) == ["systemMessage"]
    assert out["systemMessage"] == (
        "graphify token-guard, 2026-03-10 to 2026-03-12: kept ~1k tokens out of context "
        "(Bash output capped once, 1 repeated read skipped, 1 context-budget notice). "
        "Details: graphify token-guard savings")
    # A second session the same day (the loser of the O_EXCL create) says nothing.
    assert run("daily", _start("startup", session="s2"), monkeypatch, capsys) == (0, None)
    assert os.listdir(os.path.join(os.environ["GRAPHIFY_TOKEN_GUARD_DIR"], "daily")) == ["2026-03-13"]


def test_daily_covers_only_days_since_the_last_notice(clock, monkeypatch, capsys):
    clock(0)
    tg._ledger_append("bash-cap", 2000, "s1")
    clock(1)
    assert "2026-03-10: kept ~500 tokens" in run("daily", _start("startup"), monkeypatch, capsys)[1]["systemMessage"]
    # Logged on the day of that notice, after it, and on the day of the next one.
    tg._ledger_append("bash-cap", 8000, "s1")
    clock(2)
    tg._ledger_append("bash-cap", 1_000_000, "s1")
    msg = run("daily", _start("startup"), monkeypatch, capsys)[1]["systemMessage"]
    assert msg.startswith("graphify token-guard, 2026-03-11: kept ~2k tokens out of context (Bash output capped once)")
    clock(3)
    msg = run("daily", _start("startup"), monkeypatch, capsys)[1]["systemMessage"]
    assert "2026-03-12: kept ~250k tokens" in msg
    assert os.listdir(os.path.join(os.environ["GRAPHIFY_TOKEN_GUARD_DIR"], "daily")) == ["2026-03-13"]


def test_daily_without_events_is_silent_but_marks_the_day(clock, monkeypatch, capsys):
    assert run("daily", _start("startup"), monkeypatch, capsys) == (0, None)
    marker = os.path.join(os.environ["GRAPHIFY_TOKEN_GUARD_DIR"], "daily", "2026-03-10")
    assert os.path.exists(marker)
    # Today's own events are not yesterday's news, and the day is already marked.
    tg._ledger_append("bash-cap", 4000, "s1")
    assert run("daily", _start("startup"), monkeypatch, capsys) == (0, None)
    # A denied read that was retried saved nothing: no notice the next day.
    tg._ledger_append("reread", 800, "s2")
    tg._ledger_append("reread-retry", -800, "s2")
    clock(1)
    msg = run("daily", _start("startup"), monkeypatch, capsys)[1]["systemMessage"]
    assert "(Bash output capped once)" in msg and "read" not in msg.split("(")[1]


def test_daily_race_exactly_one_of_many_fires(clock, monkeypatch, capsys):
    _seed(clock)
    clock(3)
    emitted = []
    monkeypatch.setattr(tg, "_emit", emitted.append)
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(8) as pool:
        list(pool.map(lambda i: tg._hook_daily(_start("startup", session=f"s{i}")), range(40)))
    assert len(emitted) == 1 and "systemMessage" in emitted[0]


@pytest.mark.parametrize("source", ["resume", "clear", "compact", "fork"])
def test_daily_ignores_other_sources(source, clock, monkeypatch, capsys):
    _seed(clock)
    clock(3)
    assert run("daily", _start(source), monkeypatch, capsys) == (0, None)
    assert not os.path.exists(os.path.join(os.environ["GRAPHIFY_TOKEN_GUARD_DIR"], "daily"))
    # A payload without a source is treated as a startup.
    payload = _start("startup")
    del payload["source"]
    assert run("daily", payload, monkeypatch, capsys)[1] is not None


@pytest.mark.parametrize("name", ["GRAPHIFY_TOKEN_GUARD", "GRAPHIFY_TOKEN_GUARD_DAILY"])
def test_daily_disabled_by_env_leaves_the_day_unmarked(name, clock, monkeypatch, capsys):
    _seed(clock)
    clock(3)
    monkeypatch.setenv(name, "0")
    assert run("daily", _start("startup"), monkeypatch, capsys) == (0, None)
    assert not os.path.exists(os.path.join(os.environ["GRAPHIFY_TOKEN_GUARD_DIR"], "daily"))
    monkeypatch.delenv(name)
    assert run("daily", _start("startup"), monkeypatch, capsys)[1] is not None


def test_daily_switch_does_not_turn_off_the_other_hooks(src, clock, monkeypatch, capsys):
    monkeypatch.setenv("GRAPHIFY_TOKEN_GUARD_DAILY", "0")
    assert not denied(run("reread", read_payload(src), monkeypatch, capsys))
    assert denied(run("reread", read_payload(src), monkeypatch, capsys))
    assert len(ledger()) == 1


def test_daily_unwritable_state_fails_open(tmp_path, clock, monkeypatch, capsys):
    blocker = tmp_path / "blocker"
    blocker.write_text("x", encoding="utf-8")
    monkeypatch.setenv("GRAPHIFY_TOKEN_GUARD_DIR", str(blocker))
    assert run("daily", _start("startup"), monkeypatch, capsys) == (0, None)


# --------------------------------------------------------------------------- #
# state pruning
# --------------------------------------------------------------------------- #
def test_old_state_is_pruned_when_a_new_session_starts(src, monkeypatch, capsys):
    root = os.environ["GRAPHIFY_TOKEN_GUARD_DIR"]
    old = time.time() - 8 * 86400
    recent = time.time() - 6 * 86400
    made = {}
    for name, stamp in (("old", old), ("recent", recent)):
        for sub in ("reads", "outputs"):
            d = os.path.join(root, sub, name)
            os.makedirs(d)
            f = os.path.join(d, "x.json")
            open(f, "w").close()
            os.utime(f, (stamp, stamp))
            os.utime(d, (stamp, stamp))
            made[(sub, name)] = d
        os.makedirs(os.path.join(root, "budget"), exist_ok=True)
        f = os.path.join(root, "budget", name + ".json")
        with open(f, "w") as fh:
            fh.write("{}")
        os.utime(f, (stamp, stamp))
        made[("budget", name)] = f
    assert not denied(run("reread", read_payload(src, session="fresh"), monkeypatch, capsys))
    for (sub, name), path in made.items():
        assert os.path.exists(path) == (name == "recent"), (sub, name)
    assert os.path.isdir(os.path.join(root, "reads", "fresh"))


# --------------------------------------------------------------------------- #
# install / uninstall / status
# --------------------------------------------------------------------------- #
def _settings_file():
    return os.path.join(os.environ["CLAUDE_CONFIG_DIR"], "settings.json")


def _load():
    with open(_settings_file(), encoding="utf-8") as fh:
        return json.load(fh)


EXPECTED_HOOKS = {
    "PreToolUse": [{"matcher": "Read", "hooks": [
        {"type": "command", "command": "/opt/bin/graphify token-guard reread", "timeout": 10}]}],
    "PostToolUse": [{"matcher": "Bash", "hooks": [
        {"type": "command", "command": "/opt/bin/graphify token-guard bash-cap", "timeout": 10}]}],
    "UserPromptSubmit": [{"hooks": [
        {"type": "command", "command": "/opt/bin/graphify token-guard budget", "timeout": 10}]}],
    "SessionStart": [
        {"matcher": "compact", "hooks": [
            {"type": "command", "command": "/opt/bin/graphify token-guard reset", "timeout": 10}]},
        {"matcher": "startup", "hooks": [
            {"type": "command", "command": "/opt/bin/graphify token-guard daily", "timeout": 10}]},
    ],
}


def test_install_writes_expected_entries_into_fresh_settings(capsys):
    assert tg.main(["install"]) == 0
    assert _load() == {"hooks": EXPECTED_HOOKS}
    assert "hooks installed in" in capsys.readouterr().out


def test_installed_commands_survive_graphifys_own_hook_filter():
    """graphify install/uninstall strips its own entries by these markers."""
    from graphify.install import _is_graphify_hook_command, _strip_graphify_hooks
    for project in (False, True):
        for event, groups in tg._hook_entries(project=project).items():
            for g in groups:
                for h in g["hooks"]:
                    assert h["timeout"] == 10
                    assert "token-guard" in h["command"]
                    assert not _is_graphify_hook_command(h["command"])
            assert _strip_graphify_hooks(groups) == groups


USER_SETTINGS = {
    "model": "opus",
    "permissions": {"allow": ["Bash(ls:*)"]},
    "env": {"NAME": "çğ"},
    "hooks": {
        "PreToolUse": [
            {"matcher": "Bash|Grep", "hooks": [
                {"type": "command", "command": "/opt/bin/graphify hook-guard search", "timeout": 10}]},
            {"matcher": "Read", "hooks": [{"type": "command", "command": "my-read-audit.sh"}]},
        ],
        "Stop": [{"hooks": [{"type": "command", "command": "say done"}]}],
        "UserPromptSubmit": [{"hooks": [{"type": "command", "command": "echo token-guard-like but not ours"}]}],
    },
}


def _write_user_settings(text=None):
    os.makedirs(os.environ["CLAUDE_CONFIG_DIR"], exist_ok=True)
    with open(_settings_file(), "w", encoding="utf-8") as fh:
        fh.write(text if text is not None else json.dumps(USER_SETTINGS, indent=2, ensure_ascii=False) + "\n")


def test_install_preserves_everything_else_and_is_idempotent(capsys):
    _write_user_settings()
    assert tg.main(["install"]) == 0
    first = open(_settings_file(), encoding="utf-8").read()
    s = json.loads(first)
    assert {k: v for k, v in s.items() if k != "hooks"} == {k: v for k, v in USER_SETTINGS.items() if k != "hooks"}
    assert "çğ" in first and first.endswith("\n")
    assert s["hooks"]["Stop"] == USER_SETTINGS["hooks"]["Stop"]
    assert s["hooks"]["PreToolUse"] == USER_SETTINGS["hooks"]["PreToolUse"] + EXPECTED_HOOKS["PreToolUse"]
    assert s["hooks"]["UserPromptSubmit"] == \
        USER_SETTINGS["hooks"]["UserPromptSubmit"] + EXPECTED_HOOKS["UserPromptSubmit"]
    assert s["hooks"]["PostToolUse"] == EXPECTED_HOOKS["PostToolUse"]
    assert s["hooks"]["SessionStart"] == EXPECTED_HOOKS["SessionStart"]
    # The previous file is kept as a backup.
    assert json.load(open(_settings_file() + ".graphify-bak", encoding="utf-8")) == USER_SETTINGS

    mtime = os.stat(_settings_file()).st_mtime_ns
    capsys.readouterr()
    assert tg.main(["install"]) == 0
    assert "already up to date" in capsys.readouterr().out
    assert open(_settings_file(), encoding="utf-8").read() == first
    assert os.stat(_settings_file()).st_mtime_ns == mtime
    # No temp files left next to settings.json.
    assert sorted(os.listdir(os.environ["CLAUDE_CONFIG_DIR"])) == ["settings.json", "settings.json.graphify-bak"]


def test_uninstall_restores_user_settings_and_is_idempotent(capsys):
    _write_user_settings()
    before = open(_settings_file(), encoding="utf-8").read()
    assert tg.main(["install"]) == 0
    assert tg.main(["uninstall"]) == 0
    assert open(_settings_file(), encoding="utf-8").read() == before
    capsys.readouterr()
    assert tg.main(["uninstall"]) == 0
    assert "no hooks installed" in capsys.readouterr().out
    assert open(_settings_file(), encoding="utf-8").read() == before


def test_uninstall_on_fresh_install_leaves_no_empty_hooks_and_missing_file_is_fine(capsys):
    assert tg.main(["uninstall"]) == 0
    assert not os.path.exists(_settings_file())
    assert tg.main(["install"]) == 0
    assert tg.main(["uninstall"]) == 0
    assert _load() == {}


def test_install_replaces_stale_entries_and_keeps_neighbours_in_shared_group():
    stale = {"hooks": {"PreToolUse": [
        {"matcher": "Read", "hooks": [
            {"type": "command", "command": "/old/venv/bin/graphify token-guard reread", "timeout": 3},
            {"type": "command", "command": "keep-me.sh"}]},
        {"matcher": "Read", "hooks": [
            {"type": "command", "command": '"C:/Program Files/g/graphify.exe" token-guard reread'}]},
    ]}}
    _write_user_settings(json.dumps(stale))
    assert tg.main(["install"]) == 0
    assert _load()["hooks"]["PreToolUse"] == [
        {"matcher": "Read", "hooks": [{"type": "command", "command": "keep-me.sh"}]},
        EXPECTED_HOOKS["PreToolUse"][0],
    ]


@pytest.mark.parametrize("bad", ["{not json", "[1, 2]", '{"hooks": []}'])
def test_install_refuses_to_touch_unparseable_settings(bad, capsys):
    _write_user_settings(bad)
    for sub in ("install", "uninstall", "status"):
        assert tg.main([sub]) == 1
    assert "refusing to modify" in capsys.readouterr().err
    assert open(_settings_file(), encoding="utf-8").read() == bad
    assert os.listdir(os.environ["CLAUDE_CONFIG_DIR"]) == ["settings.json"]


def test_install_leaves_unknown_event_shapes_alone():
    _write_user_settings(json.dumps({"hooks": {"PreToolUse": {"weird": 1}, "PostToolUse": ["str", 5]}}))
    assert tg.main(["install"]) == 0
    hooks = _load()["hooks"]
    assert hooks["PreToolUse"] == {"weird": 1}
    assert hooks["PostToolUse"] == ["str", 5] + EXPECTED_HOOKS["PostToolUse"]
    assert tg.main(["uninstall"]) == 0
    assert _load()["hooks"] == {"PreToolUse": {"weird": 1}, "PostToolUse": ["str", 5]}


def test_install_follows_symlinked_settings(tmp_path):
    real = tmp_path / "dotfiles" / "settings.json"
    real.parent.mkdir()
    real.write_text('{"model": "opus"}', encoding="utf-8")
    os.makedirs(os.environ["CLAUDE_CONFIG_DIR"])
    try:
        os.symlink(real, _settings_file())
    except (OSError, NotImplementedError):
        pytest.skip("symlinks unavailable")
    assert tg.main(["install"]) == 0
    assert os.path.islink(_settings_file())
    assert json.loads(real.read_text(encoding="utf-8"))["hooks"] == EXPECTED_HOOKS


def test_project_install_uses_bare_command_and_cwd(tmp_path, monkeypatch, capsys):
    proj = tmp_path / "proj"
    proj.mkdir()
    monkeypatch.chdir(proj)
    assert tg.main(["install", "--project"]) == 0
    s = json.loads((proj / ".claude" / "settings.json").read_text(encoding="utf-8"))
    assert s["hooks"]["PreToolUse"][0]["hooks"][0]["command"] == "graphify token-guard reread"
    assert not os.path.exists(_settings_file())
    capsys.readouterr()
    assert tg.main(["status", "--project"]) == 0
    assert "not installed" not in capsys.readouterr().out
    assert tg.main(["uninstall", "--project"]) == 0
    assert json.loads((proj / ".claude" / "settings.json").read_text(encoding="utf-8")) == {}


def test_default_settings_path_is_under_home_without_config_dir(monkeypatch):
    monkeypatch.delenv("CLAUDE_CONFIG_DIR")
    assert tg._settings_path(False) == os.path.join(os.environ["HOME"], ".claude", "settings.json")
    monkeypatch.delenv("GRAPHIFY_TOKEN_GUARD_DIR")
    assert tg._state_dir() == os.path.join(os.environ["HOME"], ".cache", "graphify", "token-guard")


def test_status_reports_installed_and_missing(capsys):
    assert tg.main(["status"]) == 0
    out = capsys.readouterr().out
    assert out.count("not installed") == 5 and not os.path.exists(_settings_file())
    tg.main(["install"])
    capsys.readouterr()
    assert tg.main(["status"]) == 0
    out = capsys.readouterr().out
    assert "not installed" not in out
    for sub in ("reread", "reset", "budget", "bash-cap", "daily"):
        assert f"/opt/bin/graphify token-guard {sub}" in out


def test_install_upgrades_an_older_four_entry_install(capsys):
    """Settings written before `daily` existed gain it once; the rest is unchanged."""
    old = {"hooks": {**EXPECTED_HOOKS, "SessionStart": EXPECTED_HOOKS["SessionStart"][:1]}}
    _write_user_settings(json.dumps(old, indent=2) + "\n")
    assert tg.main(["install"]) == 0
    assert "hooks installed in" in capsys.readouterr().out
    assert _load() == {"hooks": EXPECTED_HOOKS}
    assert tg.main(["install"]) == 0
    assert "already up to date" in capsys.readouterr().out
    assert _load() == {"hooks": EXPECTED_HOOKS}
    assert tg.main(["uninstall"]) == 0
    assert _load() == {}


def test_uninstall_removes_daily_and_keeps_other_startup_hooks():
    mine = {"matcher": "startup", "hooks": [{"type": "command", "command": "my-startup.sh"}]}
    _write_user_settings(json.dumps({"hooks": {"SessionStart": [mine]}}))
    assert tg.main(["install"]) == 0
    assert _load()["hooks"]["SessionStart"] == [mine] + EXPECTED_HOOKS["SessionStart"]
    assert tg.main(["uninstall"]) == 0
    assert _load() == {"hooks": {"SessionStart": [mine]}}


def test_unknown_subcommand_and_arguments(capsys):
    assert tg.main(["nope"]) == 2
    assert tg.main(["install", "--global"]) == 2
    assert not os.path.exists(_settings_file())
    assert tg.main([]) == 0
    assert "usage: graphify token-guard" in capsys.readouterr().out
