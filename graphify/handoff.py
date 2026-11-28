"""Session handoff note for graphify — compact, deterministic, no LLM calls.

A long Claude Code session re-sends its whole context on every request. Once
that context is hundreds of thousands of tokens, starting a fresh session is far
cheaper than continuing — provided the new session knows where the old one
stopped. ``graphify handoff`` writes that note (``graphify-out/HANDOFF.md``)
from three local sources: the session transcript, git, and the knowledge graph.

The note may be committed, so it carries only truncated and redacted user
prompts, file paths, counts, git summaries and the last task-list state. Tool
outputs, file bodies and assistant prose never reach it.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import subprocess
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator

from graphify.paths import out_path, write_text_atomic
from graphify.security import REDACTED_MARKER, redact_secrets

DEFAULT_MAX_CHARS = 6000
PROMPT_MAX_CHARS = 300
_LAST_PROMPTS = 5
_MAX_EDITED = 25
_MAX_READ = 10
_MAX_GIT_FILES = 15
_MAX_GRAPH_FILES = 10
_MAX_TODOS = 20
_TODO_MAX_CHARS = 120
_GIT_TIMEOUT = 5
_MAX_GRAPH_BYTES = 256 * 1024 * 1024
# A prompt is redacted before it is truncated, so only this much of a huge
# paste is ever scanned.
_PROMPT_SCAN_CHARS = 4000

_EDIT_TOOLS = frozenset({"Edit", "Write", "MultiEdit", "NotebookEdit"})
_READ_TOOLS = frozenset({"Read", "NotebookRead"})

# Only these record types matter; everything else (request blobs, snapshots,
# attachments) is skipped without a JSON parse. Both separator styles are
# accepted so a pretty-printed or re-serialised transcript still works.
_LINE_MARKERS = (
    '"type":"user"', '"type":"assistant"',
    '"type": "user"', '"type": "assistant"',
)

_SLUG_RE = re.compile(r"[^A-Za-z0-9]")
_SLUG_MAX = 200

_REMINDER_RE = re.compile(r"<system-reminder>.*?</system-reminder>", re.DOTALL)
_COMMAND_NAME_RE = re.compile(r"<command-name>\s*(.*?)\s*</command-name>", re.DOTALL)
_COMMAND_ARGS_RE = re.compile(r"<command-args>\s*(.*?)\s*</command-args>", re.DOTALL)
# Harness-injected user turns are wrapped in hyphenated pseudo-tags
# (<task-notification>, <local-command-stdout>, ...). Real HTML a human pastes
# (<div>, <meta ...>) has no hyphen in the tag name and is kept.
_WRAPPER_TAG_RE = re.compile(r"^<[a-z]+(?:-[a-z0-9]+)+[\s>]")
_WS_RE = re.compile(r"\s+")

_ASSIGN_RE = re.compile(
    # The keyword must be a whole name part (API_KEY, db.password, token) so
    # `monkey=` or `keyboard:` in prose is left alone.
    r"(?i)(?<![A-Za-z0-9])((?:[A-Z0-9]+[_.-])*(?:API_?KEY|KEY|TOKEN|SECRET|PASSWORD|PASSWD|PWD|CREDENTIALS?))"
    r"(\s*[=:]\s*)(\"[^\"\s]{4,}\"|'[^'\s]{4,}'|[^\s\"',;]{4,})"
)
_LONG_TOKEN_RE = re.compile(r"(?<![A-Za-z0-9+_=-])[A-Za-z0-9+_=-]{32,}(?![A-Za-z0-9+_=-])")


# ---------------------------------------------------------------------------
# Transcript location
# ---------------------------------------------------------------------------

def claude_config_dir() -> Path:
    """``$CLAUDE_CONFIG_DIR`` when set, else ``~/.claude``."""
    override = os.environ.get("CLAUDE_CONFIG_DIR", "").strip()
    if override:
        return Path(override).expanduser()
    return Path.home() / ".claude"


def project_slug(cwd: str | Path) -> str:
    """Claude Code's project directory name for *cwd*.

    Every non-alphanumeric character becomes ``-``:
    ``/Users/a/My Proj`` -> ``-Users-a-My-Proj``.
    """
    return _SLUG_RE.sub("-", str(cwd))


def _project_dirs(cwd: Path) -> list[Path]:
    """Existing transcript directories for *cwd*, nearest match first.

    Tries the working directory as given and symlink-resolved (``/tmp`` vs
    ``/private/tmp``), then each parent, so running from a subdirectory of the
    project still finds the session that was started at its root.
    """
    projects = claude_config_dir() / "projects"
    if not projects.is_dir():
        return []
    starts = [cwd]
    try:
        real = Path(os.path.realpath(str(cwd)))
        if real != cwd:
            starts.append(real)
    except OSError:
        pass
    seen: set[str] = set()
    found: list[Path] = []
    for start in starts:
        for candidate in (start, *start.parents):
            if candidate == candidate.parent:
                continue  # never match the filesystem root's "-" slug
            slug = project_slug(candidate)
            if slug in seen:
                continue
            seen.add(slug)
            direct = projects / slug
            if direct.is_dir():
                found.append(direct)
            elif len(slug) > _SLUG_MAX:
                # Over-long slugs are stored truncated with a suffix.
                try:
                    found.extend(sorted(
                        p for p in projects.iterdir()
                        if p.is_dir() and p.name.startswith(slug[:_SLUG_MAX])
                    ))
                except OSError:
                    pass
    return found


def _mtime(path: Path) -> float:
    try:
        return path.stat().st_mtime
    except OSError:
        return 0.0


def _newest(paths: list[Path]) -> Path | None:
    return max(paths, key=lambda p: (_mtime(p), p.name)) if paths else None


class AmbiguousSession(LookupError):
    """A ``--session`` prefix that matches more than one session.

    ``candidates`` holds the matching session ids, sorted.
    """

    def __init__(self, prefix: str, candidates: list[str]) -> None:
        super().__init__(f"session prefix {prefix!r} matches {len(candidates)} sessions")
        self.prefix = prefix
        self.candidates = candidates


def find_transcript(
    cwd: str | Path | None = None,
    session: str | None = None,
    transcript: str | Path | None = None,
) -> Path | None:
    """Resolve the transcript to summarise, or ``None`` when there is none.

    Precedence: an explicit *transcript* path, then *session* (a session id or
    unique prefix, looked up under the cwd's project first and every project
    after), then the most recently modified transcript for *cwd*.

    An exact session id always wins. A prefix shared by several different
    sessions raises :class:`AmbiguousSession` instead of choosing one.
    """
    if transcript:
        path = Path(transcript).expanduser()
        return path if path.is_file() else None
    base = Path(cwd) if cwd else Path.cwd()
    dirs = _project_dirs(base)
    if session:
        name = session[:-6] if session.endswith(".jsonl") else session
        if not name or "/" in name or "\\" in name or name.startswith("."):
            return None
        others: list[Path] = []
        try:
            others = sorted(
                p for p in (claude_config_dir() / "projects").iterdir()
                if p.is_dir() and p not in dirs
            )
        except OSError:
            pass
        for directory in (*dirs, *others):
            exact = directory / f"{name}.jsonl"
            if exact.is_file():
                return exact
        # Prefix: the cwd's project is one scope, every other project the next.
        # Within a scope the prefix has to name a single session id (the same id
        # may exist under more than one directory).
        for scope in (dirs, others):
            matches: list[Path] = []
            for directory in scope:
                try:
                    matches += [p for p in directory.glob("*.jsonl") if p.name.startswith(name)]
                except OSError:
                    continue
            ids = sorted({p.stem for p in matches})
            if len(ids) > 1:
                raise AmbiguousSession(name, ids)
            if matches:
                return _newest(matches)
        return None
    for directory in dirs:
        try:
            newest = _newest(list(directory.glob("*.jsonl")))
        except OSError:
            continue
        if newest is not None:
            return newest
    return None


# ---------------------------------------------------------------------------
# Redaction and text shaping
# ---------------------------------------------------------------------------

def _entropy(token: str) -> float:
    total = len(token)
    return -sum(n / total * math.log2(n / total) for n in Counter(token).values())


def _looks_random(token: str) -> bool:
    digits = sum(c.isdigit() for c in token)
    if not digits or digits == len(token):
        return False
    mixed_case = any(c.islower() for c in token) and any(c.isupper() for c in token)
    if not mixed_case and digits < len(token) * 0.2:
        return False  # long-kebab-case-names-with-a-2 are prose, not keys
    return _entropy(token) >= 3.5


def redact(text: str) -> str:
    """Mask credential-shaped substrings.

    Layers :func:`graphify.security.redact_secrets` (vendor token shapes, PEM
    blocks, URL userinfo) with two generic rules: ``NAME_KEY=value`` style
    assignments and long high-entropy tokens. Shape-based, so it reduces risk
    rather than guaranteeing a clean note.
    """
    if not text:
        return ""
    text = redact_secrets(text)
    text = _ASSIGN_RE.sub(lambda m: f"{m.group(1)}{m.group(2)}{REDACTED_MARKER}", text)
    return _LONG_TOKEN_RE.sub(
        lambda m: REDACTED_MARKER if _looks_random(m.group(0)) else m.group(0), text
    )


def _one_line(text: str, limit: int) -> str:
    """Redact, collapse to a single line and cut to *limit* characters."""
    text = redact(text[:_PROMPT_SCAN_CHARS])
    text = _WS_RE.sub(" ", text).strip()
    if len(text) > limit:
        text = text[: limit - 1].rstrip() + "…"
    return text


def _human_text(record: dict[str, Any]) -> str | None:
    """The text a human typed for this ``user`` record, or ``None``.

    Tool results, harness meta turns, compaction summaries and subagent
    (sidechain) turns are all ``type: user`` too and are rejected here.
    """
    if record.get("isMeta") or record.get("isSidechain") or record.get("isCompactSummary"):
        return None
    if record.get("isVisibleInTranscriptOnly") or "toolUseResult" in record:
        return None
    message = record.get("message")
    if not isinstance(message, dict):
        return None
    content = message.get("content")
    if isinstance(content, str):
        text = content
    elif isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if not isinstance(block, dict):
                continue
            kind = block.get("type")
            if kind == "tool_result":
                return None
            if kind == "text" and isinstance(block.get("text"), str):
                parts.append(block["text"])
        text = "\n".join(parts)
    else:
        return None
    text = _REMINDER_RE.sub("", text).strip()
    command = _COMMAND_NAME_RE.search(text)
    if command:
        args = _COMMAND_ARGS_RE.search(text)
        text = f"{command.group(1)} {args.group(1) if args else ''}".strip()
        if not text.startswith("/"):
            text = "/" + text
    elif _WRAPPER_TAG_RE.match(text) or text.startswith("[Request interrupted"):
        return None
    return text or None


# ---------------------------------------------------------------------------
# Transcript scan
# ---------------------------------------------------------------------------

@dataclass
class SessionSummary:
    """What one streamed pass over a transcript yields."""

    session_id: str = ""
    cwd: str = ""
    first_ts: str = ""
    last_ts: str = ""
    prompt_count: int = 0
    api_requests: int = 0
    compactions: int = 0
    context_tokens: int = 0
    first_prompt: str = ""
    last_prompts: list[str] = field(default_factory=list)  # oldest -> newest
    edited: Counter = field(default_factory=Counter)
    read: Counter = field(default_factory=Counter)
    todos: list[tuple[str, str]] = field(default_factory=list)  # (status, text)


def _iter_records(path: Path) -> Iterator[dict[str, Any]]:
    with path.open("r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            if not any(marker in line for marker in _LINE_MARKERS):
                continue
            try:
                record = json.loads(line)
            except ValueError:
                continue
            if isinstance(record, dict) and record.get("type") in ("user", "assistant"):
                yield record


def _context_tokens(usage: Any) -> int:
    if not isinstance(usage, dict):
        return 0
    total = 0
    for key in ("input_tokens", "cache_read_input_tokens", "cache_creation_input_tokens"):
        value = usage.get(key)
        if isinstance(value, int) and not isinstance(value, bool):
            total += value
    return total


class _TaskList:
    """Replays task-list tool calls; only the final state is reported."""

    def __init__(self) -> None:
        self.items: list[list[str]] = []  # [status, text]
        self._ids: dict[str, list[str]] = {}

    def apply(self, name: str, args: dict[str, Any]) -> None:
        if name == "TodoWrite" or name.endswith("update_plan"):
            rows = args.get("todos") if name == "TodoWrite" else args.get("items")
            if isinstance(rows, list):
                self.items = [
                    [str(r.get("status") or "pending"), str(r.get("content") or r.get("subject") or "")]
                    for r in rows if isinstance(r, dict)
                ]
                self._ids = {}
                return
            if name == "TodoWrite":
                return
            for index in args.get("done") or []:
                self._set(index, "completed")
            if isinstance(args.get("start"), int):
                self._set(args["start"], "in_progress")
            if args.get("advance") is True:
                seen_active = False
                for item in self.items:
                    if item[0] == "in_progress":
                        item[0] = "completed"
                        seen_active = True
                    elif item[0] == "pending" and seen_active:
                        item[0] = "in_progress"
                        break
        elif name == "TaskCreate":
            item = ["pending", str(args.get("subject") or args.get("content") or "")]
            self.items.append(item)
            self._ids[str(len(self.items))] = item
        elif name == "TaskUpdate":
            item = self._ids.get(str(args.get("taskId")))
            if item is not None:
                if isinstance(args.get("status"), str):
                    item[0] = args["status"]
                if isinstance(args.get("subject"), str):
                    item[1] = args["subject"]

    def _set(self, index: Any, status: str) -> None:
        if isinstance(index, int) and not isinstance(index, bool) and 1 <= index <= len(self.items):
            self.items[index - 1][0] = status

    def final(self) -> list[tuple[str, str]]:
        return [(s, t) for s, t in self.items if t.strip() and s != "deleted"]


def scan_transcript(path: str | Path) -> SessionSummary:
    """Stream a Claude Code JSONL transcript into a :class:`SessionSummary`.

    Reads line by line, so a multi-hundred-megabyte transcript costs time but
    not memory. Malformed lines and unknown record types are ignored.
    """
    path = Path(path)
    summary = SessionSummary(session_id=path.stem)
    tasks = _TaskList()
    tail: list[str] = []
    request_ids: set[str] = set()
    for record in _iter_records(path):
        if record.get("isSidechain"):
            continue
        ts = record.get("timestamp")
        if isinstance(ts, str) and ts:
            if not summary.first_ts:
                summary.first_ts = ts
            summary.last_ts = ts
        if isinstance(record.get("sessionId"), str) and record["sessionId"]:
            summary.session_id = record["sessionId"]
        if isinstance(record.get("cwd"), str) and record["cwd"]:
            summary.cwd = record["cwd"]
        if record["type"] == "user":
            if record.get("isCompactSummary"):
                summary.compactions += 1
                continue
            text = _human_text(record)
            if text is None:
                continue
            summary.prompt_count += 1
            if summary.prompt_count == 1:
                summary.first_prompt = text[:_PROMPT_SCAN_CHARS]
            else:
                tail.append(text[:_PROMPT_SCAN_CHARS])
                if len(tail) > _LAST_PROMPTS:
                    del tail[0]
            continue
        message = record.get("message")
        if not isinstance(message, dict):
            continue
        tokens = _context_tokens(message.get("usage"))
        if tokens:
            summary.context_tokens = tokens
            # One API response is logged as several records (one per content
            # block) sharing an id; count it once.
            rid = record.get("requestId") or message.get("id")
            if isinstance(rid, str) and rid:
                request_ids.add(rid)
            else:
                summary.api_requests += 1
        content = message.get("content")
        if not isinstance(content, list):
            continue
        for block in content:
            if not isinstance(block, dict) or block.get("type") != "tool_use":
                continue
            name = block.get("name")
            args = block.get("input")
            if not isinstance(name, str) or not isinstance(args, dict):
                continue
            if name in _EDIT_TOOLS or name in _READ_TOOLS:
                target = args.get("file_path") or args.get("notebook_path")
                if isinstance(target, str) and target:
                    (summary.edited if name in _EDIT_TOOLS else summary.read)[target] += 1
            else:
                tasks.apply(name, args)
    summary.api_requests += len(request_ids)
    summary.last_prompts = tail
    summary.todos = tasks.final()
    return summary


# ---------------------------------------------------------------------------
# Git and graph
# ---------------------------------------------------------------------------

def _git(cwd: Path, *args: str) -> str | None:
    try:
        proc = subprocess.run(
            ["git", "--no-optional-locks", *args], cwd=str(cwd), capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=_GIT_TIMEOUT,
        )
    except (OSError, subprocess.SubprocessError, ValueError):
        return None
    return proc.stdout if proc.returncode == 0 else None


def git_state(cwd: str | Path) -> dict[str, Any] | None:
    """Branch, porcelain status lines and the ``diff --stat`` summary line.

    ``None`` when *cwd* is not a repository, git is missing, or it times out.
    """
    cwd = Path(cwd)
    status = _git(cwd, "status", "--porcelain")
    if status is None:
        return None
    branch = (_git(cwd, "rev-parse", "--abbrev-ref", "HEAD") or "").strip()
    stat = (_git(cwd, "diff", "--stat") or "").strip().splitlines()
    return {
        "branch": branch,
        "status": [line.rstrip() for line in status.splitlines() if line.strip()],
        "diffstat": stat[-1].strip() if stat else "",
    }


def _norm(path: str) -> str:
    path = path.replace("\\", "/")
    while path.startswith("./"):
        path = path[2:]
    return path


def _display_path(path: str, cwd: str) -> str:
    """*path* relative to the project when inside it, else ``~``-shortened."""
    shown = _norm(path)
    root = _norm(cwd).rstrip("/")
    if root and shown.startswith(root + "/"):
        shown = shown[len(root) + 1:]
    else:
        home = _norm(str(Path.home())).rstrip("/")
        if home and shown.startswith(home + "/"):
            shown = "~" + shown[len(home):]
    return redact(shown).replace("`", "'")


def _degree_of(degree: Counter, node: dict[str, Any]) -> int:
    nid = node.get("id")
    return degree[nid] if isinstance(nid, (str, int)) else 0


def _community_labels(graph_path: Path) -> dict[str, str]:
    try:
        data = json.loads((graph_path.parent / ".graphify_labels.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    for wrapper in ("labels", "communities"):
        if isinstance(data, dict) and isinstance(data.get(wrapper), dict):
            data = data[wrapper]
    if not isinstance(data, dict):
        return {}
    labels: dict[str, str] = {}
    for key, value in data.items():
        if isinstance(value, dict):
            value = value.get("label") or value.get("name") or value.get("title")
        if isinstance(value, str) and value.strip():
            labels[str(key)] = value.strip()
    return labels


def graph_pointers(
    graph_path: str | Path, files: list[str], cwd: str | Path
) -> list[dict[str, Any]]:
    """Graph nodes and communities for each of *files* that the graph covers.

    Returns one ``{"file", "communities", "node_count", "labels"}`` entry per
    covered file, in the order given; ``labels`` holds the best-connected
    nodes, ready for ``graphify explain``. Any unreadable or oddly shaped graph
    yields an empty list.
    """
    graph_path = Path(graph_path)
    try:
        if graph_path.stat().st_size > _MAX_GRAPH_BYTES:
            return []
        data = json.loads(graph_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    if not isinstance(data, dict) or not isinstance(data.get("nodes"), list):
        return []
    root = _norm(str(cwd)).rstrip("/")
    wanted: dict[str, str] = {}
    for original in files:
        shown = _norm(original)
        wanted.setdefault(shown, original)
        if root and shown.startswith(root + "/"):
            wanted.setdefault(shown[len(root) + 1:], original)
    by_file: dict[str, list[dict[str, Any]]] = {}
    for node in data["nodes"]:
        if not isinstance(node, dict) or not isinstance(node.get("source_file"), str):
            continue
        original = wanted.get(_norm(node["source_file"]))
        if original is not None:
            by_file.setdefault(original, []).append(node)
    if not by_file:
        return []
    degree: Counter = Counter()
    edges = data.get("links") if isinstance(data.get("links"), list) else data.get("edges")
    for edge in edges if isinstance(edges, list) else []:
        if isinstance(edge, dict):
            for end in ("source", "target"):
                if isinstance(edge.get(end), (str, int)):
                    degree[edge[end]] += 1
    names = _community_labels(graph_path)
    pointers: list[dict[str, Any]] = []
    for original in files:
        nodes = by_file.get(original)
        if not nodes:
            continue
        communities: list[str] = []
        for node in nodes:
            cid = node.get("community")
            name = node.get("community_name")
            if not (isinstance(name, str) and name.strip()):
                if cid is None or isinstance(cid, (dict, list)):
                    continue
                name = names.get(str(cid)) or f"Community {cid}"
            name = _WS_RE.sub(" ", name).strip()
            if name not in communities:
                communities.append(name)
        ranked = sorted(
            enumerate(nodes), key=lambda pair: (-_degree_of(degree, pair[1]), pair[0])
        )
        labels: list[str] = []
        for _, node in ranked:
            label = node.get("label")
            if not isinstance(label, str):
                continue
            label = _WS_RE.sub(" ", label).strip()
            if not label or len(label) > 60 or any(c in label for c in '"`$\\'):
                continue
            if label not in labels:
                labels.append(label)
            if len(labels) == 2:
                break
        pointers.append({
            "file": original, "communities": communities,
            "node_count": len(nodes), "labels": labels,
        })
    return pointers


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

@dataclass
class _Section:
    title: str
    fixed: list[str] = field(default_factory=list)
    items: list[str] = field(default_factory=list)
    hidden: int = 0  # entries already left out before budget trimming
    keep: int = 0    # how many items survive the first trimming pass
    dropped: int = 0

    def lines(self) -> list[str]:
        if not self.fixed and not self.items:
            return []
        lines = [f"## {self.title}", *self.fixed, *self.items]
        omitted = self.hidden + self.dropped
        if omitted:
            lines.append(f"- … {omitted} more not shown")
        return lines


def _render(head: list[str], sections: list[_Section], foot: list[str]) -> str:
    blocks = [head, *(s.lines() for s in sections), foot]
    return "\n\n".join("\n".join(b) for b in blocks if b) + "\n"


def _short_ts(ts: str) -> str:
    return ts[:16].replace("T", " ") if len(ts) >= 16 else ts


def _plural(n: int, word: str) -> str:
    return f"{n:,} {word}" if n == 1 else f"{n:,} {word}s"


def _status_summary(status: list[str]) -> str:
    counts: Counter = Counter()
    for line in status:
        code = line[:2]
        if code == "??":
            counts["untracked"] += 1
        elif "U" in code or code in ("AA", "DD"):
            counts["conflicted"] += 1
        elif "D" in code:
            counts["deleted"] += 1
        elif "A" in code:
            counts["added"] += 1
        elif "R" in code:
            counts["renamed"] += 1
        else:
            counts["modified"] += 1
    order = ("modified", "added", "deleted", "renamed", "untracked", "conflicted")
    return ", ".join(f"{counts[k]} {k}" for k in order if counts[k])


_TODO_MARKS = {"completed": "[x]", "in_progress": "[~]"}


def render_handoff(
    summary: SessionSummary,
    git: dict[str, Any] | None = None,
    pointers: list[dict[str, Any]] | None = None,
    max_chars: int = DEFAULT_MAX_CHARS,
) -> str:
    """Render the Markdown note, at most *max_chars* characters long.

    Over the cap, list entries are dropped whole from the bottom of the least
    important sections first (reference reads, graph pointers, tasks, git
    files, edited files, older prompts); a line is never cut in the middle.
    """
    cwd = summary.cwd
    head = ["# Session handoff", ""]
    head.append(f"- Session: `{summary.session_id}`")
    if summary.first_ts:
        span = _short_ts(summary.first_ts)
        if _short_ts(summary.last_ts) != span:
            span += f" → {_short_ts(summary.last_ts)}"
        head.append(f"- Span (UTC): {span}")
    counts = [_plural(summary.prompt_count, "human prompt"), _plural(summary.api_requests, "API request")]
    if summary.compactions:
        counts.append(_plural(summary.compactions, "compaction"))
    head.append(f"- Requests: {', '.join(counts)}")
    if summary.context_tokens:
        head.append(f"- Last context size: {summary.context_tokens:,} tokens (re-sent on every request)")

    requests = _Section("Requests", keep=2)
    if summary.first_prompt:
        requests.fixed.append(f"- First: {_one_line(summary.first_prompt, PROMPT_MAX_CHARS)}")
    if summary.last_prompts:
        requests.fixed.append("Latest, newest first:")
        requests.items = [
            f"- {_one_line(p, PROMPT_MAX_CHARS)}" for p in reversed(summary.last_prompts)
        ]

    edited = _Section("Files edited", keep=5)
    ranked = sorted(summary.edited.items(), key=lambda kv: (-kv[1], kv[0]))
    edited.items = [
        f"- `{_display_path(p, cwd)}` — {_plural(n, 'edit')}" for p, n in ranked[:_MAX_EDITED]
    ]
    edited.hidden = max(0, len(ranked) - _MAX_EDITED)

    reads = _Section("Reference material (read, not edited)", keep=3)
    read_only = sorted(
        ((p, n) for p, n in summary.read.items() if p not in summary.edited),
        key=lambda kv: (-kv[1], kv[0]),
    )
    reads.items = [
        f"- `{_display_path(p, cwd)}` — {_plural(n, 'read')}" for p, n in read_only[:_MAX_READ]
    ]

    gitsec = _Section("Uncommitted git state", keep=5)
    if git:
        status = [s for s in git.get("status") or [] if isinstance(s, str)]
        if git.get("branch"):
            gitsec.fixed.append(f"- Branch: `{git['branch']}`")
        if status:
            gitsec.fixed.append(f"- Working tree: {_status_summary(status)}")
            if git.get("diffstat"):
                gitsec.fixed.append(f"- Diff: {git['diffstat']}")
            gitsec.items = [f"- `{redact(s).replace('`', chr(39))}`" for s in status[:_MAX_GIT_FILES]]
            gitsec.hidden = max(0, len(status) - _MAX_GIT_FILES)
        elif gitsec.fixed:
            gitsec.fixed.append("- Working tree: clean")

    graph = _Section("Graph pointers (query the graph instead of re-reading)", keep=3)
    for pointer in (pointers or [])[:_MAX_GRAPH_FILES]:
        line = f"- `{_display_path(pointer['file'], cwd)}` — {_plural(pointer['node_count'], 'node')}"
        if pointer.get("communities"):
            line += " in " + ", ".join(pointer["communities"][:3])
        if pointer.get("labels"):
            line += ": " + ", ".join(f'`graphify explain "{label}"`' for label in pointer["labels"])
        graph.items.append(line)
    graph.hidden = max(0, len(pointers or []) - _MAX_GRAPH_FILES)

    todo = _Section("Task list (last state)", keep=5)
    # Open work first: under a tight cap the finished items are what goes.
    open_first = sorted(summary.todos, key=lambda t: t[0] == "completed")
    todo.items = [
        f"- {_TODO_MARKS.get(status, '[ ]')} {_one_line(text, _TODO_MAX_CHARS)}"
        for status, text in open_first[:_MAX_TODOS]
    ]
    todo.hidden = max(0, len(open_first) - _MAX_TODOS)

    foot = [
        "## Resume",
        "Read this file first, then open only the files you need; prefer "
        "`graphify query \"<question>\"` or `graphify explain \"<node>\"` over re-reading "
        "whole files, and confirm the plan against the latest request above before editing.",
    ]

    sections = [requests, edited, reads, gitsec, graph, todo]
    trim_order = [reads, graph, todo, gitsec, edited, requests]
    text = _render(head, sections, foot)
    for floor in (None, 0):
        for section in trim_order:
            limit = section.keep if floor is None else floor
            while len(text) > max_chars and len(section.items) > limit:
                section.items.pop()
                section.dropped += 1
                text = _render(head, sections, foot)
    for section in trim_order:
        if len(text) <= max_chars:
            break
        section.fixed, section.items, section.hidden, section.dropped = [], [], 0, 0
        text = _render(head, sections, foot)
    if len(text) > max_chars:
        kept: list[str] = []
        size = 0
        for line in text.splitlines():
            if size + len(line) + 1 > max_chars:
                break
            kept.append(line)
            size += len(line) + 1
        text = "\n".join(kept).rstrip("\n") + "\n" if kept else ""
    return text


def build_handoff(
    transcript: str | Path,
    cwd: str | Path | None = None,
    max_chars: int = DEFAULT_MAX_CHARS,
    graph_path: str | Path | None = None,
) -> str:
    """Scan *transcript* and render the note for the project at *cwd*.

    *cwd* defaults to the current directory. Git and graph sections are
    best-effort: either is silently left out when its source is unavailable.
    """
    base = Path(cwd) if cwd else Path.cwd()
    summary = scan_transcript(transcript)
    # Paths are shown relative to the directory the command runs in (the
    # transcript records symlink-resolved paths, hence realpath), and git and
    # the graph are read from that same directory.
    summary.cwd = os.path.realpath(str(base))
    gp = Path(graph_path) if graph_path else base / out_path("graph.json")
    pointers: list[dict[str, Any]] = []
    if summary.edited and gp.is_file():
        ranked = [p for p, _ in sorted(summary.edited.items(), key=lambda kv: (-kv[1], kv[0]))]
        try:
            pointers = graph_pointers(gp, ranked, summary.cwd)
        except Exception:
            pointers = []
    return render_handoff(summary, git_state(base), pointers, max_chars)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    """``graphify handoff`` entry point. Returns a process exit code."""
    parser = argparse.ArgumentParser(
        prog="graphify handoff",
        description="Write a compact handoff note so a fresh Claude Code session "
                    "can continue a long one without re-reading its context.",
    )
    parser.add_argument("--session", metavar="ID", help="session id (or unique prefix) to summarise")
    parser.add_argument("--transcript", metavar="PATH", help="explicit transcript .jsonl path")
    parser.add_argument("--out", metavar="PATH", help="output file (default: graphify-out/HANDOFF.md)")
    parser.add_argument("--stdout", action="store_true", help="print the note instead of writing it")
    parser.add_argument("--max-chars", type=int, default=DEFAULT_MAX_CHARS, metavar="N",
                        help=f"hard size cap in characters (default: {DEFAULT_MAX_CHARS})")
    try:
        args = parser.parse_args(sys.argv[1:] if argv is None else argv)
    except SystemExit as exc:
        return exc.code if isinstance(exc.code, int) else 2
    if args.max_chars < 1:
        print("error: --max-chars must be positive", file=sys.stderr)
        return 2
    try:
        transcript = find_transcript(session=args.session, transcript=args.transcript)
    except AmbiguousSession as exc:
        print(f"error: session prefix {exc.prefix!r} is ambiguous; it matches "
              f"{len(exc.candidates)} sessions:", file=sys.stderr)
        for candidate in exc.candidates:
            print(f"  {candidate}", file=sys.stderr)
        return 1
    if transcript is None:
        if args.transcript:
            reason = f"transcript not found: {args.transcript}"
        elif args.session:
            reason = f"no transcript for session {args.session!r}"
        else:
            reason = (f"no Claude Code transcript for {Path.cwd()} under "
                      f"{claude_config_dir() / 'projects'} (use --session or --transcript)")
        print(f"error: {reason}", file=sys.stderr)
        return 1
    try:
        text = build_handoff(transcript, max_chars=args.max_chars)
    except OSError as exc:
        print(f"error: cannot read {transcript}: {exc}", file=sys.stderr)
        return 1
    if args.stdout:
        sys.stdout.write(text)
        return 0
    out = Path(args.out).expanduser() if args.out else out_path("HANDOFF.md")
    try:
        write_text_atomic(out, text)
    except OSError as exc:
        print(f"error: cannot write {out}: {exc}", file=sys.stderr)
        return 1
    print(f"Wrote {out} ({len(text):,} chars, ~{len(text) // 4:,} tokens)")
    print("Start a fresh session and have it read this file first.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
