"""Claude Code hooks that keep the context window small (``graphify token-guard``).

Every request re-sends the whole conversation, so anything that enters context
is paid for again on each later request. These hooks cut the largest sources:

``reread``    PreToolUse, matcher ``Read``. A Read of a file this agent already
              read, unchanged on disk, over a range an earlier read covers, is
              denied once with a note that the content is already in context.
              Re-issuing the same Read is then allowed.
``read-done`` PostToolUse, matcher ``Read``. Records the range a Read returned.
              PostToolUse fires only after the tool succeeded, so a Read that
              failed or was blocked is never taken to be in context. Without
              this entry nothing is recorded and ``reread`` denies nothing.
``reset``     SessionStart, matcher ``compact``. Compaction drops file contents
              from context, so the session's read records are cleared.
``budget``    UserPromptSubmit. When the context size recorded in the transcript
              crosses GRAPHIFY_CONTEXT_BUDGET (and each further
              GRAPHIFY_CONTEXT_BUDGET_STEP) the user and the model are told once.
``bash-cap``  PostToolUse, matcher ``Bash``. Output above GRAPHIFY_BASH_CAP
              characters is replaced by its head and tail (``updatedToolOutput``);
              the full output is saved to a file whose path is stated.

``daily``     SessionStart, matcher ``startup``. Once per local calendar day the
              user (not the model) is shown what the hooks kept out of context
              since the previous notice.

Each saving is appended to a ledger under the state dir
(``savings/YYYY-MM-DD.jsonl``: timestamp, kind, characters, session key; never
file contents, commands or prompts). ``savings`` prints it per day.

``install`` / ``uninstall`` / ``status`` manage the entries in Claude Code's
settings.json.

Conventions, shared with ``graphify hook-guard``: every hook fails open (any
error prints nothing and exits 0), messages state facts instead of giving
orders, each installed entry carries a ``timeout``, and no hook can deny the
same thing twice, so an agent is never stranded.

Standard library only, and nothing heavy at import time: these run on every
tool call.
"""
from __future__ import annotations

import json
import os
import sys

_HOOK_SUBCOMMANDS = ("reread", "read-done", "reset", "budget", "bash-cap", "daily")
# A hook payload carries the tool's whole output (bash-cap: many MB is
# legitimate). Past this size the payload is not parsed and the hook does nothing.
_STDIN_MAX_BYTES = 64 << 20
# settings.json is a few KB. A larger file is refused like an unparseable one.
_SETTINGS_MAX_BYTES = 4 << 20
# Extensions the Read tool does not return as plain text lines (images, PDFs,
# notebooks): offset/limit coverage says nothing about what was shown.
_NON_TEXT_EXTS = frozenset({
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".tif", ".tiff", ".ico",
    ".heic", ".heif", ".avif", ".svg", ".pdf", ".ipynb",
})
# Read returns at most this many lines when no limit is given.
_DEFAULT_READ_LINES = 2000
# A Read without a limit is refused by Claude Code when the file is too large,
# so such a call puts nothing in context. Above this size it is neither
# recorded nor denied.
_UNLIMITED_READ_MAX_BYTES = 100_000
_STATE_MAX_AGE = 7 * 86400
_TRANSCRIPT_CHUNK = 1 << 20
_TRANSCRIPT_MAX_SCAN = 32 << 20
_LEDGER_MAX_AGE_DAYS = 90
# Sizing a denied Read's line range reads the file up to the end of that range;
# past this many bytes the file's size is used instead.
_RANGE_SCAN_MAX = 4 << 20
# Rough characters per token, used only to label ledger totals as an estimate.
_CHARS_PER_TOKEN = 4
_LEDGER_KINDS = ("bash-cap", "reread", "reread-retry", "budget")


# --------------------------------------------------------------------------- #
# Small helpers
# --------------------------------------------------------------------------- #
def _env_on(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() not in ("0", "false", "off", "no")


def _enabled() -> bool:
    return _env_on("GRAPHIFY_TOKEN_GUARD")


def _env_int(name: str, default: int) -> int:
    try:
        return int(str(os.environ.get(name, "")).strip() or default)
    except ValueError:
        return default


def _state_dir() -> str:
    """Per-user state root. ``graphify hook-guard`` keeps its markers under the
    project's graphify-out/, which only exists once a graph is built; these
    hooks work in any directory, so their state lives under the user's cache."""
    override = os.environ.get("GRAPHIFY_TOKEN_GUARD_DIR")
    if override:
        return override
    return os.path.join(os.path.expanduser("~"), ".cache", "graphify", "token-guard")


def _session_key(payload: dict, *, with_agent: bool = True) -> str:
    """Filesystem-safe key for the session, and for the subagent within it.

    Same sanitising as hook-guard's markers. Subagents share the parent's
    session id but have their own context, so ``agent_id`` is hashed in.
    """
    import re
    key = re.sub(r"[^A-Za-z0-9_-]", "_", str(payload.get("session_id") or ""))[:64]
    if not key:
        return ""
    agent = str(payload.get("agent_id") or "") if with_agent else ""
    if agent:
        import hashlib
        key += "-" + hashlib.sha256(agent.encode("utf-8")).hexdigest()[:16]
    return key


def _read_stdin_payload() -> "dict | None":
    try:
        raw = sys.stdin.buffer.read(_STDIN_MAX_BYTES + 1)
        if len(raw) > _STDIN_MAX_BYTES:
            return None
        data = json.loads(raw.decode("utf-8", "replace"))
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def _emit(obj: dict) -> None:
    out = json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
    try:
        sys.stdout.buffer.write(out.encode("utf-8"))
        sys.stdout.buffer.flush()
    except AttributeError:  # stdout replaced by a text-only stream
        sys.stdout.write(out)


def _load_json(path: str) -> dict:
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _write_atomic(path: str, text: str, mode: int = 0o600) -> None:
    import tempfile
    d = os.path.dirname(path)
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".tg-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", errors="replace") as fh:
            fh.write(text)
        try:
            os.chmod(tmp, mode)
        except OSError:
            pass
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _make_dir(path: str) -> bool:
    """Create *path* (0700). True when it did not exist before."""
    if os.path.isdir(path):
        return False
    os.makedirs(path, mode=0o700, exist_ok=True)
    return True


def _prune(root: "str | None" = None) -> None:
    """Best-effort removal of state older than 7 days. Runs when a session's
    state directory is first created, not on every call."""
    import shutil
    import time
    root = root or _state_dir()
    cutoff = time.time() - _STATE_MAX_AGE
    for sub in ("reads", "budget", "outputs"):
        try:
            entries = list(os.scandir(os.path.join(root, sub)))
        except OSError:
            continue
        for entry in entries:
            try:
                if entry.stat(follow_symlinks=False).st_mtime >= cutoff:
                    continue
                if entry.is_dir(follow_symlinks=False):
                    newest = max(
                        (e.stat(follow_symlinks=False).st_mtime for e in os.scandir(entry.path)),
                        default=0.0,
                    )
                    if newest < cutoff:
                        shutil.rmtree(entry.path, ignore_errors=True)
                else:
                    os.unlink(entry.path)
            except OSError:
                pass


# --------------------------------------------------------------------------- #
# Savings ledger
# --------------------------------------------------------------------------- #
def _now() -> float:
    import time
    return time.time()


def _day(offset: int = 0) -> str:
    """Local calendar date as YYYY-MM-DD, *offset* days from today."""
    from datetime import date, timedelta
    return (date.fromtimestamp(_now()) + timedelta(days=offset)).isoformat()


def _is_day(name: str) -> bool:
    import re
    return re.fullmatch(r"\d{4}-\d{2}-\d{2}", name) is not None


def _ledger_dir() -> str:
    return os.path.join(_state_dir(), "savings")


def _ledger_append(kind: str, chars: int, session: str) -> None:
    """Append one event to today's ledger file. Never raises: bookkeeping must
    not change what a hook decides.

    One ``os.write`` of one short line on an O_APPEND descriptor, so parallel
    hook processes cannot interleave or overwrite each other's lines. Only the
    kind, a size and the session key are stored.
    """
    try:
        today = _day()
        directory = _ledger_dir()
        path = os.path.join(directory, today + ".jsonl")
        fresh = not os.path.exists(path)
        if fresh:
            os.makedirs(directory, mode=0o700, exist_ok=True)
        line = json.dumps({"ts": int(_now()), "kind": kind, "chars": int(chars), "session": session},
                          separators=(",", ":")) + "\n"
        fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
        try:
            os.write(fd, line.encode("utf-8"))
        finally:
            os.close(fd)
        if fresh:  # first event of the day: drop ledger files past retention
            cutoff = _day(-_LEDGER_MAX_AGE_DAYS)
            for name in os.listdir(directory):
                if name.endswith(".jsonl") and _is_day(name[:-6]) and name[:-6] < cutoff:
                    try:
                        os.unlink(os.path.join(directory, name))
                    except OSError:
                        pass
    except Exception:
        pass


def _ledger_days(first: str, last: str) -> "list[str]":
    """Days with a ledger file, ``first <= day <= last``, oldest first."""
    try:
        names = os.listdir(_ledger_dir())
    except OSError:
        return []
    return sorted(n[:-6] for n in names
                  if n.endswith(".jsonl") and _is_day(n[:-6]) and first <= n[:-6] <= last)


def _ledger_read(day: str) -> "dict[str, dict[str, int]]":
    """``{kind: {"events": n, "chars": c}}`` for one day; bad lines are skipped."""
    kinds: "dict[str, dict[str, int]]" = {}
    try:
        with open(os.path.join(_ledger_dir(), day + ".jsonl"), "r", encoding="utf-8", errors="replace") as fh:
            lines = fh.readlines()
    except OSError:
        return kinds
    for line in lines:
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if not isinstance(event, dict) or event.get("kind") not in _LEDGER_KINDS:
            continue
        chars = event.get("chars")
        if not isinstance(chars, int) or isinstance(chars, bool):
            continue
        slot = kinds.setdefault(event["kind"], {"events": 0, "chars": 0})
        slot["events"] += 1
        slot["chars"] += chars
    return kinds


def _summarize(kinds: "dict[str, dict[str, int]]") -> dict:
    """Totals of one ``{kind: {events, chars}}`` mapping. A ``reread-retry``
    carries negative chars and cancels the ``reread`` it follows."""
    def n(kind: str, field: str = "events") -> int:
        return kinds.get(kind, {}).get(field, 0)
    chars = sum(k["chars"] for k in kinds.values())
    return {
        "events": sum(k["events"] for k in kinds.values()),
        "chars": chars,
        "estimated_tokens": max(0, chars) // _CHARS_PER_TOKEN,
        "bash_capped": n("bash-cap"),
        "reads_skipped": max(0, n("reread") - n("reread-retry")),
        "budget_notices": n("budget"),
        "kinds": {k: dict(kinds[k]) for k in _LEDGER_KINDS if k in kinds},
    }


def _merge_kinds(total: "dict[str, dict[str, int]]", kinds: "dict[str, dict[str, int]]") -> None:
    for kind, value in kinds.items():
        slot = total.setdefault(kind, {"events": 0, "chars": 0})
        slot["events"] += value["events"]
        slot["chars"] += value["chars"]


# --------------------------------------------------------------------------- #
# reread (PreToolUse, matcher Read)
# --------------------------------------------------------------------------- #
def _requested_range(tool_input: dict, size: int) -> "tuple[int, int] | None":
    """The half-open line range ``[start, end)`` a Read asks for, or None when
    it cannot be judged (bad values, or an unlimited read of a large file)."""
    offset, limit = tool_input.get("offset"), tool_input.get("limit")
    if isinstance(offset, bool) or isinstance(limit, bool):
        return None
    try:
        start = max(1, int(offset)) if offset is not None else 1
        if limit is None:
            if size > _UNLIMITED_READ_MAX_BYTES:
                return None
            count = _DEFAULT_READ_LINES
        else:
            count = int(limit)
    except (TypeError, ValueError):
        return None
    if count <= 0:
        return None
    return start, start + count


def _merge_ranges(ranges: list) -> "list[list[int]]":
    clean = sorted(
        [int(r[0]), int(r[1])] for r in ranges
        if isinstance(r, (list, tuple)) and len(r) == 2
        and all(isinstance(v, int) and not isinstance(v, bool) for v in r) and r[0] < r[1]
    )
    merged: "list[list[int]]" = []
    for start, end in clean:
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    return merged


def _covered(ranges: "list[list[int]]", start: int, end: int) -> bool:
    return any(a <= start and end <= b for a, b in ranges)


def _range_chars(path: str, start: int, end: int, size: int) -> int:
    """Characters in lines ``[start, end)`` of *path*: what a Read of that
    range would have put in context, not counting the line-number prefixes
    Read adds. Falls back to the file size when the range lies deep in a large
    file or the file cannot be read."""
    try:
        total = scanned = 0
        with open(path, "rb") as fh:
            for number, line in enumerate(fh, 1):
                if number >= end:
                    break
                scanned += len(line)
                if scanned > _RANGE_SCAN_MAX:
                    return size
                if number >= start:
                    total += len(line.decode("utf-8", "replace"))
        return total
    except OSError:
        return size


def _read_request(payload: dict) -> "tuple | None":
    """``(session key, real path, stat, start, end)`` for a Read of a text
    file whose range can be judged, else None. A missing file raises (the
    caller fails open and Read reports it)."""
    if payload.get("tool_name") not in (None, "Read"):
        return None
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        return None
    file_path = tool_input.get("file_path")
    if not isinstance(file_path, str) or not file_path:
        return None
    if tool_input.get("pages") is not None:
        return None
    if os.path.splitext(file_path)[1].lower() in _NON_TEXT_EXTS:
        return None
    key = _session_key(payload)
    if not key:
        return None
    cwd = payload.get("cwd")
    if not os.path.isabs(file_path) and isinstance(cwd, str) and cwd:
        file_path = os.path.join(cwd, file_path)
    real = os.path.realpath(file_path)
    st = os.stat(real)
    import stat as _stat
    if not _stat.S_ISREG(st.st_mode):
        return None
    wanted = _requested_range(tool_input, st.st_size)
    if wanted is None:
        return None
    return key, real, st, wanted[0], wanted[1]


def _read_record(key: str, real: str, st: os.stat_result) -> "tuple[str, str, list[list[int]], bool, int]":
    """``(session dir, record path, ranges, denied, saved)`` of what is on
    record for this version of *real*; empty when the file changed since."""
    import hashlib
    session_dir = os.path.join(_state_dir(), "reads", key)
    record_path = os.path.join(
        session_dir, hashlib.sha256(real.encode("utf-8", "surrogatepass")).hexdigest()[:32] + ".json")
    rec = _load_json(record_path)
    if not (rec.get("path") == real and rec.get("mtime_ns") == st.st_mtime_ns
            and rec.get("size") == st.st_size):
        return session_dir, record_path, [], False, 0
    ranges = _merge_ranges(rec["ranges"]) if isinstance(rec.get("ranges"), list) else []
    # Characters the denial kept out of context that have not come back since.
    saved = rec.get("saved")
    if not isinstance(saved, int) or isinstance(saved, bool) or saved < 0:
        saved = 0
    return session_dir, record_path, ranges, bool(rec.get("denied")), saved


def _write_read_record(path: str, real: str, st: os.stat_result,
                       ranges: "list[list[int]]", denied: bool, saved: int) -> None:
    _write_atomic(path, json.dumps({
        "path": real, "mtime_ns": st.st_mtime_ns, "size": st.st_size,
        "ranges": ranges, "denied": denied, "saved": saved,
    }))


def _hook_reread(payload: dict) -> None:
    """Decide only. Coverage comes from ``read-done`` records, written after a
    Read succeeded; this hook runs before the tool and cannot know whether the
    Read it lets through will return anything."""
    request = _read_request(payload)
    if request is None:
        return
    key, real, st, start, end = request
    _, record_path, ranges, denied, _ = _read_record(key, real, st)
    if denied or not _covered(ranges, start, end):
        return
    saved = _range_chars(real, start, end, st.st_size)
    # The record is written before the denial is printed: if it cannot be
    # written this raises, nothing is printed, and the Read goes ahead. A
    # denial that was not recorded could repeat.
    _write_read_record(record_path, real, st, ranges, True, saved)
    _ledger_append("reread", saved, key)
    tool_input = payload["tool_input"]
    span = "the whole file" if tool_input.get("offset") is None and tool_input.get("limit") is None \
        else f"lines {start}-{end - 1}"
    reason = (
        f"graphify token-guard: {real} ({span}) was already read earlier in this session "
        "and the file is unchanged on disk since then (same modification time and size), "
        "so that content is already in context. This notice is given once per file version: "
        "re-issuing the same Read will be allowed, for example if the earlier result is no "
        "longer visible."
    )
    _emit({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "deny",
        "permissionDecisionReason": reason,
    }})


# --------------------------------------------------------------------------- #
# read-done (PostToolUse, matcher Read)
# --------------------------------------------------------------------------- #
def _hook_read_done(payload: dict) -> None:
    """Record the range of a Read that returned text."""
    if payload.get("hook_event_name", "PostToolUse") != "PostToolUse":
        return
    # The Read tool's structured output for text. A failed call carries the
    # error text as a string; images, PDFs and notebooks have another type.
    response = payload.get("tool_response")
    if not isinstance(response, dict) or response.get("type") != "text":
        return
    request = _read_request(payload)
    if request is None:
        return
    key, real, st, start, end = request
    session_dir, record_path, ranges, denied, saved = _read_record(key, real, st)
    returned = 0
    if saved and _covered(ranges, start, end):
        # The denied content was read after all: the saving is undone, up to
        # the size of what this read brought back.
        returned = min(saved, _range_chars(real, start, end, st.st_size))
        saved = 0
    if _make_dir(session_dir):
        _prune()
    _write_read_record(record_path, real, st, _merge_ranges(ranges + [[start, end]]), denied, saved)
    if returned:
        _ledger_append("reread-retry", -returned, key)


# --------------------------------------------------------------------------- #
# reset (SessionStart, matcher compact)
# --------------------------------------------------------------------------- #
def _hook_reset(payload: dict) -> None:
    if payload.get("hook_event_name", "SessionStart") != "SessionStart" \
            or payload.get("source") != "compact":
        return
    key = _session_key(payload, with_agent=False)
    if not key:
        return
    import re
    import shutil
    reads = os.path.join(_state_dir(), "reads")
    # The session's own records and those of each of its subagents
    # ("<key>-<16 hex>"). Other sessions are untouched.
    own = re.compile(re.escape(key) + r"(?:-[0-9a-f]{16})?")
    try:
        entries = list(os.scandir(reads))
    except OSError:
        return
    for entry in entries:
        if own.fullmatch(entry.name):
            shutil.rmtree(entry.path, ignore_errors=True)


# --------------------------------------------------------------------------- #
# budget (UserPromptSubmit)
# --------------------------------------------------------------------------- #
def _usage_context(line: bytes) -> "int | None":
    """Context tokens of one transcript line: 0 for a compaction boundary, the
    prompt size for a main-conversation assistant message, else None."""
    is_usage = b'"usage"' in line and b'"assistant"' in line
    is_boundary = b'"compact_boundary"' in line
    if not (is_usage or is_boundary):
        return None
    try:
        entry = json.loads(line)
    except ValueError:
        return None
    if not isinstance(entry, dict) or entry.get("isSidechain"):
        return None
    if entry.get("type") == "system" and entry.get("subtype") == "compact_boundary":
        return 0
    if entry.get("type") != "assistant":
        return None
    message = entry.get("message")
    usage = message.get("usage") if isinstance(message, dict) else None
    if not isinstance(usage, dict):
        return None
    total = 0
    for field in ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens"):
        value = usage.get(field)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            total += int(value)
    # Synthetic messages (API errors, interruptions) carry an all-zero usage.
    return total if total > 0 else None


def transcript_context_tokens(path: str, max_scan: int = _TRANSCRIPT_MAX_SCAN) -> "int | None":
    """Context size of the most recent request in a Claude Code transcript.

    Reads the JSONL file backwards in 1 MB chunks and stops at the first line
    (from the end) that answers, so a transcript of hundreds of MB costs one or
    two chunk reads. Gives up after *max_scan* bytes. None when unknown.
    """
    with open(path, "rb") as fh:
        fh.seek(0, os.SEEK_END)
        pos = fh.tell()
        scanned = 0
        pending: "list[bytes]" = []  # pieces of a line that started in an earlier chunk
        while pos > 0 and scanned < max_scan:
            step = min(_TRANSCRIPT_CHUNK, pos)
            pos -= step
            fh.seek(pos)
            chunk = fh.read(step)
            scanned += step
            if b"\n" not in chunk and pos > 0:
                pending.insert(0, chunk)
                continue
            head, _, rest = chunk.partition(b"\n") if pos > 0 else (b"", b"", chunk)
            lines = (rest + b"".join(pending)).split(b"\n")
            pending = [head] if pos > 0 else []
            for line in reversed(lines):
                found = _usage_context(line)
                if found is not None:
                    return found
    return None


def _fmt_tokens(n: int) -> str:
    return f"{n / 1_000_000:.2f}M" if n >= 1_000_000 else f"{round(n / 1000)}k"


def _hook_budget(payload: dict) -> None:
    threshold = _env_int("GRAPHIFY_CONTEXT_BUDGET", 200_000)
    step = _env_int("GRAPHIFY_CONTEXT_BUDGET_STEP", 100_000)
    if threshold <= 0:
        return
    key = _session_key(payload, with_agent=False)
    transcript = payload.get("transcript_path")
    if not key or not isinstance(transcript, str) or not transcript:
        return
    context = transcript_context_tokens(os.path.expanduser(transcript))
    if context is None:
        return
    if context < threshold:
        level = 0
    elif step > 0:
        level = 1 + (context - threshold) // step
    else:
        level = 1
    budget_dir = os.path.join(_state_dir(), "budget")
    state_path = os.path.join(budget_dir, key + ".json")
    previous = _load_json(state_path).get("level")
    if not isinstance(previous, int) or isinstance(previous, bool):
        previous = 0
    if level == previous:
        return
    if _make_dir(budget_dir):
        _prune()
    # Recorded first: a level that could not be recorded is not announced, so
    # it cannot be announced on every prompt.
    _write_atomic(state_path, json.dumps({"level": level, "context": context}))
    if level < previous:
        return  # context shrank (compaction): levels above are re-armed
    size = _fmt_tokens(context)
    text = (
        f"graphify token-guard: the context is now about {size} tokens "
        f"(budget {_fmt_tokens(threshold)}). Every further request re-reads all of it. "
        "/compact, or a fresh session started from `graphify handoff` "
        "(writes graphify-out/HANDOFF.md), would shrink it."
    )
    _ledger_append("budget", 0, key)  # a notice saves nothing by itself: counted only
    _emit({
        "systemMessage": text,
        "hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": text},
    })


# --------------------------------------------------------------------------- #
# bash-cap (PostToolUse, matcher Bash)
# --------------------------------------------------------------------------- #
def _head_tail(text: str, budget: int, note: str) -> str:
    """Keep the first and last ``budget/2`` characters of *text*, snapped to
    line boundaries where one is near, with *note* in between."""
    if len(text) <= budget:
        return text
    half = max(1, budget // 2)
    head, tail = text[:half], text[-half:]
    cut = head.rfind("\n")
    if cut >= half * 0.8:
        head = head[:cut + 1]
    cut = tail.find("\n")
    if 0 <= cut <= half * 0.2:
        tail = tail[cut + 1:]
    omitted = len(text) - len(head) - len(tail)
    if omitted <= 0:
        return text
    if not head.endswith("\n"):
        head += "\n"
    return f"{head}[{note.format(omitted=omitted)}]\n{tail}"


def _hook_bash_cap(payload: dict) -> None:
    if payload.get("tool_name") not in (None, "Bash"):
        return
    cap = _env_int("GRAPHIFY_BASH_CAP", 20_000)
    if cap <= 0:
        return
    response = payload.get("tool_response")
    if not isinstance(response, dict) or response.get("isImage"):
        return
    stdout, stderr = response.get("stdout"), response.get("stderr")
    if not isinstance(stdout, str) or not isinstance(stderr, str):
        return
    total = len(stdout) + len(stderr)
    if total <= cap:
        return

    import re
    import time
    key = _session_key(payload, with_agent=False) or "no-session"
    out_dir = os.path.join(_state_dir(), "outputs", key)
    if _make_dir(out_dir):
        _prune()
    call_id = re.sub(r"[^A-Za-z0-9_-]", "_", str(payload.get("tool_use_id") or ""))[:80] \
        or f"{time.time_ns()}-{os.getpid()}"
    out_path = os.path.join(out_dir, call_id + ".txt")
    full = stdout if not stderr else f"{stdout}\n--- stderr ---\n{stderr}"
    # Saved before anything is replaced: if this raises, the hook prints
    # nothing and Claude sees the original output.
    _write_atomic(out_path, full)

    shown_path = out_path.replace("\\", "/")
    note = (
        "graphify token-guard: {omitted} characters omitted here "
        f"(the command printed {total}); full output saved to {shown_path}"
    )
    stderr_budget = min(len(stderr), cap // 4)
    # Only stdout and stderr change: updatedToolOutput has to match the Bash
    # tool's output shape, so every other field is passed back as received.
    updated = dict(response)
    updated["stdout"] = _head_tail(stdout, cap - stderr_budget, note)
    updated["stderr"] = _head_tail(stderr, max(stderr_budget, cap - len(stdout)), note)
    kept_out = total - len(updated["stdout"]) - len(updated["stderr"])
    if kept_out > 0:
        _ledger_append("bash-cap", kept_out, key)
    _emit({"hookSpecificOutput": {"hookEventName": "PostToolUse", "updatedToolOutput": updated}})


# --------------------------------------------------------------------------- #
# daily (SessionStart, matcher startup)
# --------------------------------------------------------------------------- #
def _fmt_count(n: int) -> str:
    return str(n) if n < 1000 else _fmt_tokens(n)


def _times(n: int) -> str:
    return "once" if n == 1 else f"{n} times"


def _hook_daily(payload: dict) -> None:
    if not _env_on("GRAPHIFY_TOKEN_GUARD_DAILY"):
        return
    if payload.get("hook_event_name", "SessionStart") != "SessionStart" \
            or payload.get("source") not in (None, "startup"):
        return
    today = _day()
    marker_dir = os.path.join(_state_dir(), "daily")
    os.makedirs(marker_dir, mode=0o700, exist_ok=True)
    # Exclusive create: of several sessions starting together exactly one gets
    # past this line; the day is marked whether or not anything is shown.
    try:
        os.close(os.open(os.path.join(marker_dir, today), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600))
    except FileExistsError:
        return
    earlier = sorted(n for n in os.listdir(marker_dir) if _is_day(n) and n < today)
    # Events logged on the day of the previous notice, after it, were not in
    # it, so that day is included. No earlier marker: everything retained.
    since = earlier[-1] if earlier else ""
    for name in earlier:
        try:
            os.unlink(os.path.join(marker_dir, name))
        except OSError:
            pass
    total: "dict[str, dict[str, int]]" = {}
    days = []
    for day in _ledger_days(since, _day(-1)):
        kinds = _ledger_read(day)
        if kinds:
            days.append(day)
            _merge_kinds(total, kinds)
    summary = _summarize(total)
    parts = []
    if summary["bash_capped"]:
        parts.append(f"Bash output capped {_times(summary['bash_capped'])}")
    if summary["reads_skipped"]:
        n = summary["reads_skipped"]
        parts.append(f"{n} repeated read{'' if n == 1 else 's'} skipped")
    if summary["budget_notices"]:
        n = summary["budget_notices"]
        parts.append(f"{n} context-budget notice{'' if n == 1 else 's'}")
    if not parts:
        return
    span = days[0] if days[0] == days[-1] else f"{days[0]} to {days[-1]}"
    # systemMessage only: shown to the user, never added to the model's context.
    _emit({"systemMessage": (
        f"graphify token-guard, {span}: kept ~{_fmt_count(summary['estimated_tokens'])} tokens "
        f"out of context ({', '.join(parts)}). Details: graphify token-guard savings"
    )})


# --------------------------------------------------------------------------- #
# savings
# --------------------------------------------------------------------------- #
_LOWER_BOUND_NOTE = (
    "Lower bound: each token kept out of context would otherwise have been sent again "
    "on every later request of that session, so the real effect is larger than the "
    "direct figure. No multiplier is applied here."
)


def _savings_report(days: int) -> dict:
    first, last = _day(1 - days), _day()
    total: "dict[str, dict[str, int]]" = {}
    by_day = []
    for day in _ledger_days(first, last):
        kinds = _ledger_read(day)
        if kinds:
            by_day.append({"date": day, **_summarize(kinds)})
            _merge_kinds(total, kinds)
    return {
        "days": days, "from": first, "to": last,
        "chars_per_token": _CHARS_PER_TOKEN,
        "by_day": by_day,
        "total": _summarize(total),
        "note": _LOWER_BOUND_NOTE,
    }


def _cmd_savings(args: "list[str]") -> int:
    days, as_json = 7, False
    i = 0
    while i < len(args):
        arg = args[i]
        value = None
        if arg == "--json":
            as_json = True
        elif arg == "--days" and i + 1 < len(args):
            i += 1
            value = args[i]
        elif arg.startswith("--days="):
            value = arg[len("--days="):]
        else:
            print(f"[graphify] token-guard savings: unknown argument {arg}", file=sys.stderr)
            return 2
        if value is not None:
            if not value.isdigit() or int(value) < 1:
                print("[graphify] token-guard savings: --days takes a positive whole number", file=sys.stderr)
                return 2
            days = min(int(value), 36500)
        i += 1
    report = _savings_report(days)
    if as_json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return 0
    print(f"graphify token-guard savings, {report['from']} to {report['to']} "
          f"({days} day{'' if days == 1 else 's'}; ledger keeps {_LEDGER_MAX_AGE_DAYS})")
    if not report["by_day"]:
        print("  nothing recorded in this period")
    else:
        def kind(row: dict, name: str, field: str) -> int:
            return row["kinds"].get(name, {}).get(field, 0)

        print(f"  {'date':<10}  {'bash-cap':>8} {'chars':>10}  {'reads skipped':>13} {'chars':>10}"
              f"  {'budget':>6}  {'chars':>10}  {'~tokens':>9}")
        for row in report["by_day"] + [{"date": "total", **report["total"]}]:
            read_chars = kind(row, "reread", "chars") + kind(row, "reread-retry", "chars")
            print(f"  {row['date']:<10}  {row['bash_capped']:>8} {kind(row, 'bash-cap', 'chars'):>10}"
                  f"  {row['reads_skipped']:>13} {read_chars:>10}"
                  f"  {row['budget_notices']:>6}  {row['chars']:>10}  {row['estimated_tokens']:>9}")
        print("  bash-cap: Bash outputs cut to head+tail. reads skipped: repeated reads denied and not"
              " retried. budget: context-budget notices (counted; a notice saves nothing by itself).")
    print(f"Tokens are an estimate: characters / {_CHARS_PER_TOKEN}.")
    print(_LOWER_BOUND_NOTE)
    return 0


# --------------------------------------------------------------------------- #
# install / uninstall / status
# --------------------------------------------------------------------------- #
def _hook_entries(project: bool = False) -> "dict[str, list[dict]]":
    """The settings.json hook groups ``install`` writes, keyed by event."""
    from graphify.install import _resolve_graphify_exe
    exe = _resolve_graphify_exe(project=project)
    if " " in exe and not exe.startswith('"'):
        exe = f'"{exe}"'

    def group(sub: str, matcher: "str | None") -> dict:
        g: dict = {"matcher": matcher} if matcher else {}
        g["hooks"] = [{"type": "command", "command": f"{exe} token-guard {sub}", "timeout": 10}]
        return g

    return {
        "PreToolUse": [group("reread", "Read")],
        "PostToolUse": [group("bash-cap", "Bash"), group("read-done", "Read")],
        "UserPromptSubmit": [group("budget", None)],
        "SessionStart": [group("reset", "compact"), group("daily", "startup")],
    }


def _own_subcommand(entry: object) -> "str | None":
    """The token-guard subcommand a ``hooks[]`` element runs, else None.

    Ours only when the whole command is ``<graphify> token-guard <sub>``, the
    form ``install`` writes: the program is ``graphify`` or ``graphify.exe``,
    bare or as the last component of a path (quoted or not, either slash, any
    case). A command that merely contains the words, or passes them to another
    program (``my-wrapper token-guard reread``), is someone else's.
    """
    if not isinstance(entry, dict) or entry.get("type") != "command":
        return None
    command = entry.get("command")
    if not isinstance(command, str):
        return None
    import re
    m = re.fullmatch(
        r"""\s*(?:"([^"]+)"|'([^']+)'|([^\s"']+))\s+token-guard\s+(%s)\s*"""
        % "|".join(re.escape(sub) for sub in _HOOK_SUBCOMMANDS),
        command,
    )
    if m is None:
        return None
    exe = m.group(1) or m.group(2) or m.group(3)
    if re.split(r"[\\/]", exe)[-1].lower() not in ("graphify", "graphify.exe"):
        return None
    return m.group(4)


def _strip_own(groups: list) -> list:
    """Drop token-guard entries from *groups*; everything else is kept as is,
    and a group is removed only when it held nothing but token-guard entries."""
    kept: list = []
    for group in groups:
        entries = group.get("hooks") if isinstance(group, dict) else None
        if not isinstance(entries, list):
            kept.append(group)
            continue
        remaining = [e for e in entries if _own_subcommand(e) is None]
        if len(remaining) == len(entries):
            kept.append(group)
        elif remaining:
            kept.append({**group, "hooks": remaining})
    return kept


def _settings_path(project: bool) -> str:
    if project:
        return os.path.join(os.getcwd(), ".claude", "settings.json")
    config = os.environ.get("CLAUDE_CONFIG_DIR") or os.path.join(os.path.expanduser("~"), ".claude")
    return os.path.join(config, "settings.json")


class _SettingsError(Exception):
    pass


def _read_settings(path: str) -> "tuple[dict, str | None]":
    """``(settings, raw text or None when the file does not exist)``. A file
    that is not a JSON object raises instead of being treated as empty, so it
    is never overwritten."""
    if not os.path.exists(path):
        return {}, None
    try:
        with open(path, "rb") as fh:
            data = fh.read(_SETTINGS_MAX_BYTES + 1)
    except OSError as exc:
        raise _SettingsError(f"refusing to modify {path}: not readable ({exc})") from exc
    if len(data) > _SETTINGS_MAX_BYTES:
        raise _SettingsError(f"refusing to modify {path}: larger than {_SETTINGS_MAX_BYTES} bytes")
    try:
        raw = data.decode("utf-8-sig")
        settings = json.loads(raw) if raw.strip() else {}
    except ValueError as exc:
        raise _SettingsError(f"refusing to modify {path}: not readable as JSON ({exc})") from exc
    if not isinstance(settings, dict):
        raise _SettingsError(f"refusing to modify {path}: top level is not a JSON object")
    hooks = settings.get("hooks")
    if hooks is not None and not isinstance(hooks, dict):
        raise _SettingsError(f"refusing to modify {path}: \"hooks\" is not an object")
    return settings, raw


def _write_settings(path: str, settings: dict, raw: "str | None") -> bool:
    """Write *settings* atomically. False when nothing changed. The previous
    file is copied to ``<name>.graphify-bak`` first, as graphify's installer does."""
    output = json.dumps(settings, indent=2, ensure_ascii=False)
    if raw is not None and raw.endswith("\n"):
        output += "\n"
    if raw is not None and raw.replace("\r\n", "\n") == output:
        return False
    target = os.path.realpath(path)  # keep a symlinked settings.json a symlink
    os.makedirs(os.path.dirname(target), exist_ok=True)
    mode = 0o644
    if raw is not None:
        import shutil
        shutil.copy2(target, target + ".graphify-bak")
        try:
            mode = os.stat(target).st_mode & 0o777
        except OSError:
            pass
    _write_atomic(target, output, mode=mode)
    return True


def _apply(settings: dict, wanted: "dict[str, list[dict]]") -> dict:
    """*settings* with token-guard's entries replaced by *wanted* (empty to
    remove them). Events that end up empty, and an empty ``hooks``, are dropped
    only if token-guard emptied them."""
    result = dict(settings)
    hooks = dict(result.get("hooks") or {})
    for event in ("PreToolUse", "PostToolUse", "UserPromptSubmit", "SessionStart"):
        existing = hooks.get(event)
        if existing is not None and not isinstance(existing, list):
            continue  # not a shape this installer understands: leave it alone
        stripped = _strip_own(existing or [])
        groups = stripped + wanted.get(event, [])
        if groups:
            hooks[event] = groups
        elif existing is not None and len(stripped) != len(existing):
            hooks.pop(event, None)
    if hooks:
        result["hooks"] = hooks
    elif "hooks" in settings and settings["hooks"] != {}:
        result.pop("hooks", None)
    return result


def _installed_subcommands(settings: dict) -> "dict[str, str]":
    """``{subcommand: command string}`` for token-guard entries in *settings*."""
    found: "dict[str, str]" = {}
    hooks = settings.get("hooks")
    if not isinstance(hooks, dict):
        return found
    for groups in hooks.values():
        if not isinstance(groups, list):
            continue
        for group in groups:
            entries = group.get("hooks") if isinstance(group, dict) else None
            for entry in entries if isinstance(entries, list) else []:
                sub = _own_subcommand(entry)
                if sub:
                    found.setdefault(sub, entry["command"])
    return found


def _cmd_install(project: bool, remove: bool = False) -> int:
    path = _settings_path(project)
    try:
        settings, raw = _read_settings(path)
        if remove and raw is None:
            print(f"[graphify] token-guard: no hooks installed ({path} does not exist)")
            return 0
        changed = _write_settings(path, _apply(settings, {} if remove else _hook_entries(project)), raw)
    except _SettingsError as exc:
        print(f"[graphify] token-guard: {exc}", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"[graphify] token-guard: could not write {path}: {exc}", file=sys.stderr)
        return 1
    if remove:
        print(f"[graphify] token-guard: {'hooks removed from' if changed else 'no hooks installed in'} {path}")
    else:
        print(f"[graphify] token-guard: {'hooks installed in' if changed else 'hooks already up to date in'} {path}")
        print("  reread     PreToolUse/Read        one notice when an unchanged file is read again")
        print("  read-done  PostToolUse/Read       records what a successful Read returned, for reread")
        print("  bash-cap   PostToolUse/Bash       output above GRAPHIFY_BASH_CAP chars cut to head+tail, full copy saved")
        print("  budget     UserPromptSubmit       notice when context crosses GRAPHIFY_CONTEXT_BUDGET")
        print("  reset      SessionStart/compact   clears read records after compaction")
        print("  daily      SessionStart/startup   once a day, shows what was kept out of context (GRAPHIFY_TOKEN_GUARD_DAILY=0: off)")
        print("  Takes effect in new Claude Code sessions. GRAPHIFY_TOKEN_GUARD=0 turns the hooks off.")
        print("  graphify token-guard savings shows the per-day ledger.")
    return 0


def _cmd_status(project: bool) -> int:
    path = _settings_path(project)
    try:
        settings, _ = _read_settings(path)
    except _SettingsError as exc:
        print(f"[graphify] token-guard: {exc}", file=sys.stderr)
        return 1
    found = _installed_subcommands(settings)
    print(f"settings: {path}")
    for sub in _HOOK_SUBCOMMANDS:
        print(f"  {sub:<10} {'installed: ' + found[sub] if sub in found else 'not installed'}")
    print(f"state dir: {_state_dir()}")
    print(f"GRAPHIFY_TOKEN_GUARD={'on' if _enabled() else 'off'}"
          f"  GRAPHIFY_TOKEN_GUARD_DAILY={'on' if _env_on('GRAPHIFY_TOKEN_GUARD_DAILY') else 'off'}"
          f"  GRAPHIFY_CONTEXT_BUDGET={_env_int('GRAPHIFY_CONTEXT_BUDGET', 200_000)}"
          f"  GRAPHIFY_CONTEXT_BUDGET_STEP={_env_int('GRAPHIFY_CONTEXT_BUDGET_STEP', 100_000)}"
          f"  GRAPHIFY_BASH_CAP={_env_int('GRAPHIFY_BASH_CAP', 20_000)}")
    return 0


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #
_USAGE = """usage: graphify token-guard <subcommand>

  install [--project]     add the hooks to ~/.claude/settings.json (or ./.claude/settings.json)
  uninstall [--project]   remove them
  status [--project]      show which are installed
  savings [--days N] [--json]   what the hooks kept out of context, per day (default 7 days)

Hook subcommands (read Claude Code hook JSON on stdin):
  reread      PreToolUse, matcher Read
  read-done   PostToolUse, matcher Read
  bash-cap    PostToolUse, matcher Bash
  budget      UserPromptSubmit
  reset       SessionStart, matcher compact
  daily       SessionStart, matcher startup
"""

_HOOKS = {
    "reread": _hook_reread,
    "read-done": _hook_read_done,
    "reset": _hook_reset,
    "budget": _hook_budget,
    "bash-cap": _hook_bash_cap,
    "daily": _hook_daily,
}


def main(argv: "list[str]") -> int:
    """``graphify token-guard <sub> [args]``; *argv* is everything after
    ``token-guard``. Hook subcommands always return 0."""
    sub = argv[0] if argv else ""
    hook = _HOOKS.get(sub)
    if hook is not None:
        try:
            payload = _read_stdin_payload()
            if payload is not None and _enabled():
                hook(payload)
        except Exception:
            pass  # fail open: a guard bug never blocks a tool call or a prompt
        return 0
    if sub in ("install", "uninstall", "status"):
        extra = [a for a in argv[1:] if a != "--project"]
        if extra:
            print(f"[graphify] token-guard {sub}: unknown argument {extra[0]}", file=sys.stderr)
            return 2
        project = "--project" in argv[1:]
        if sub == "status":
            return _cmd_status(project)
        return _cmd_install(project, remove=(sub == "uninstall"))
    if sub == "savings":
        return _cmd_savings(argv[1:])
    if sub in ("", "-h", "--help", "help"):
        print(_USAGE, end="")
        return 0
    print(f"[graphify] token-guard: unknown subcommand {sub!r}\n\n{_USAGE}", end="", file=sys.stderr)
    return 2
