"""Token usage report for Claude Code session transcripts — `graphify usage`.

Streams the JSONL transcripts under ``<config>/projects`` and reports where the
tokens went: by type, model, day, project, context-size bucket, session, tool
result and repeated ``Read`` calls. Output is a terminal summary, one JSON
document, or a self-contained HTML file.

Only counts, sizes, file paths, model names and dates leave this module. Prompt
text, tool output and file bodies are measured (``len``) and never stored.
"""
from __future__ import annotations

import argparse
import html
import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator

TOKEN_KEYS = (
    "input_tokens",
    "output_tokens",
    "cache_creation_input_tokens",
    "cache_read_input_tokens",
)

# (label, exclusive upper bound); the last bucket is open-ended.
BUCKETS: tuple[tuple[str, float], ...] = (
    ("<50k", 50_000),
    ("50-100k", 100_000),
    ("100-200k", 200_000),
    ("200-400k", 400_000),
    ("400k+", float("inf")),
)

DEFAULT_TOP = 20
DEFAULT_HTML = "graphify-out/usage.html"

# A line that carries none of these cannot contribute to the report, so it is
# skipped before json.loads — most of a transcript's bytes are such lines.
_MARKERS = (b'"usage"', b'"tool_use"', b'"tool_result"')
_CWD_PEEK_LINES = 40


def default_projects_dir() -> Path:
    """``$CLAUDE_CONFIG_DIR/projects`` or ``~/.claude/projects``."""
    config = os.environ.get("CLAUDE_CONFIG_DIR", "").strip()
    base = Path(config).expanduser() if config else Path.home() / ".claude"
    return base / "projects"


# ---------------------------------------------------------------------------
# Reading
# ---------------------------------------------------------------------------

def _parse_ts(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _int(value: Any) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) and value > 0 else 0


def _result_chars(content: Any) -> int:
    """Size of a tool_result payload: a string, or the text blocks of a list."""
    if isinstance(content, str):
        return len(content)
    if isinstance(content, list):
        total = 0
        for block in content:
            if isinstance(block, dict) and isinstance(block.get("text"), str):
                total += len(block["text"])
            elif isinstance(block, str):
                total += len(block)
        return total
    return 0


def _iter_lines(path: Path, counters: dict[str, int]) -> Iterator[dict]:
    """Yield the parsed objects of one transcript, one line at a time."""
    try:
        fh = path.open("rb")
    except OSError:
        counters["unreadable_files"] += 1
        return
    with fh:
        for raw in fh:
            if not any(m in raw for m in _MARKERS):
                continue
            try:
                obj = json.loads(raw)
            except ValueError:
                counters["malformed_lines"] += 1
                continue
            if isinstance(obj, dict):
                yield obj
            else:
                counters["malformed_lines"] += 1


def _peek_cwd(path: Path) -> str:
    """First ``cwd`` in the head of a transcript, or '' — used for --project."""
    try:
        with path.open("rb") as fh:
            for i, raw in enumerate(fh):
                if i >= _CWD_PEEK_LINES:
                    break
                if b'"cwd"' not in raw:
                    continue
                try:
                    obj = json.loads(raw)
                except ValueError:
                    continue
                if isinstance(obj, dict) and isinstance(obj.get("cwd"), str):
                    return obj["cwd"]
    except OSError:
        pass
    return ""


def _share(part: float, whole: float) -> float:
    return round(part / whole, 4) if whole else 0.0


# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------

def analyze(
    projects_dir: str | Path | None = None,
    *,
    days: int | None = None,
    project: str | None = None,
    top: int = DEFAULT_TOP,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Scan transcripts under *projects_dir* and return the report as a dict.

    *days* keeps only entries from the last N days, *project* keeps projects
    whose directory slug or ``cwd`` contains the substring (case-insensitive),
    *top* bounds every ranked list. *now* is injectable for tests.
    """
    root = Path(projects_dir).expanduser() if projects_dir else default_projects_dir()
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    cutoff = now - timedelta(days=days) if days and days > 0 else None
    cutoff_epoch = cutoff.timestamp() if cutoff else None
    needle = project.lower() if project else None
    top = max(1, int(top))

    counters: dict[str, int] = defaultdict(int)
    totals = dict.fromkeys(TOKEN_KEYS, 0)
    by_model: dict[str, dict[str, int]] = {}
    by_day: dict[str, dict[str, int]] = {}
    by_project: dict[str, dict[str, Any]] = {}
    buckets = [{"requests": 0, "tokens": 0} for _ in BUCKETS]
    sessions: list[dict[str, Any]] = []
    tools: dict[str, dict[str, int]] = {}
    reread_files: dict[str, dict[str, int]] = {}
    reads = rereads = reread_chars = read_chars = 0
    requests = 0

    # Resumed sessions copy earlier lines into a new file, so these are global.
    seen_requests: set[tuple[str, str]] = set()
    seen_tool_uses: set[str] = set()
    seen_tool_results: set[str] = set()
    project_match: dict[str, bool] = {}

    files = sorted(root.rglob("*.jsonl")) if root.is_dir() else []
    for path in files:
        rel = path.relative_to(root)
        slug = rel.parts[0] if len(rel.parts) > 1 else root.name
        if needle is not None:
            ok = project_match.get(slug)
            if ok is None:
                ok = needle in slug.lower()
                if ok:
                    project_match[slug] = True
            if not ok:
                ok = needle in _peek_cwd(path).lower()
                if ok:
                    project_match[slug] = True
            if not ok:
                continue
        if cutoff_epoch is not None:
            try:
                if path.stat().st_mtime < cutoff_epoch:
                    continue
            except OSError:
                continue
        counters["files"] += 1

        proj = by_project.get(slug)
        if proj is None:
            proj = by_project[slug] = {
                "slug": slug, "name": "", "requests": 0, "sessions": 0,
                **dict.fromkeys(TOKEN_KEYS, 0),
            }
        sess: dict[str, Any] = {
            "id": path.stem, "session_id": "", "project": slug,
            "file": rel.as_posix(), "subagent": "subagents" in rel.parts,
            "start": "", "requests": 0, "context_tokens": 0, "output_tokens": 0,
            "max_context": 0, "first_context": 0,
        }
        tool_by_id: dict[str, tuple[str, bool]] = {}  # tool_use id -> (name, is re-read)
        read_counts: dict[str, int] = defaultdict(int)

        for obj in _iter_lines(path, counters):
            ts = _parse_ts(obj.get("timestamp"))
            if cutoff is not None and (ts is None or ts < cutoff):
                continue
            if not proj["name"] and isinstance(obj.get("cwd"), str):
                proj["name"] = obj["cwd"]
            if not sess["session_id"] and isinstance(obj.get("sessionId"), str):
                sess["session_id"] = obj["sessionId"]
            msg = obj.get("message")
            if not isinstance(msg, dict):
                continue

            usage = msg.get("usage")
            model = msg.get("model")
            if isinstance(usage, dict) and model != "<synthetic>":
                mid = msg.get("id")
                key = (str(mid), str(obj.get("requestId") or ""))
                vals = {k: _int(usage.get(k)) for k in TOKEN_KEYS}
                if mid and key not in seen_requests and any(vals.values()):
                    seen_requests.add(key)
                    requests += 1
                    ctx = (vals["input_tokens"] + vals["cache_creation_input_tokens"]
                           + vals["cache_read_input_tokens"])
                    day = ts.strftime("%Y-%m-%d") if ts else "unknown"
                    mrow = by_model.setdefault(
                        str(model or "unknown"), {"requests": 0, **dict.fromkeys(TOKEN_KEYS, 0)})
                    drow = by_day.setdefault(day, {"requests": 0, **dict.fromkeys(TOKEN_KEYS, 0)})
                    for row in (mrow, drow, proj):
                        row["requests"] += 1
                        for k in TOKEN_KEYS:
                            row[k] += vals[k]
                    for k in TOKEN_KEYS:
                        totals[k] += vals[k]
                    for i, (_label, upper) in enumerate(BUCKETS):
                        if ctx < upper:
                            buckets[i]["requests"] += 1
                            buckets[i]["tokens"] += ctx
                            break
                    if sess["requests"] == 0:
                        sess["first_context"] = ctx
                        sess["start"] = ts.isoformat() if ts else ""
                    sess["requests"] += 1
                    sess["context_tokens"] += ctx
                    sess["output_tokens"] += vals["output_tokens"]
                    if ctx > sess["max_context"]:
                        sess["max_context"] = ctx

            content = msg.get("content")
            if not isinstance(content, list):
                continue
            for block in content:
                if not isinstance(block, dict):
                    continue
                btype = block.get("type")
                if btype == "tool_use":
                    tid = block.get("id")
                    name = block.get("name")
                    if not isinstance(tid, str) or not isinstance(name, str):
                        continue
                    if tid in tool_by_id:
                        continue
                    is_reread = False
                    fresh = tid not in seen_tool_uses
                    seen_tool_uses.add(tid)
                    if fresh:
                        trow = tools.setdefault(name, {"calls": 0, "results": 0, "chars": 0})
                        trow["calls"] += 1
                    inp = block.get("input")
                    if name == "Read" and fresh and isinstance(inp, dict):
                        fp = inp.get("file_path")
                        if isinstance(fp, str) and fp:
                            reads += 1
                            read_counts[fp] += 1
                            frow = reread_files.setdefault(
                                fp, {"reads": 0, "rereads": 0, "chars_reread": 0})
                            frow["reads"] += 1
                            if read_counts[fp] > 1:
                                is_reread = True
                                rereads += 1
                                frow["rereads"] += 1
                    tool_by_id[tid] = (name, is_reread)
                    if is_reread and isinstance(inp, dict):
                        tool_by_id[tid + "\0path"] = (inp["file_path"], True)
                elif btype == "tool_result":
                    tid = block.get("tool_use_id")
                    if not isinstance(tid, str) or tid in seen_tool_results:
                        continue
                    seen_tool_results.add(tid)
                    chars = _result_chars(block.get("content"))
                    name, is_reread = tool_by_id.get(tid, ("(unknown)", False))
                    trow = tools.setdefault(name, {"calls": 0, "results": 0, "chars": 0})
                    trow["results"] += 1
                    trow["chars"] += chars
                    if name == "Read":
                        read_chars += chars
                    if is_reread:
                        reread_chars += chars
                        reread_files[tool_by_id[tid + "\0path"][0]]["chars_reread"] += chars

        if sess["requests"]:
            proj["sessions"] += 1
            sessions.append(sess)

    # -- assemble ----------------------------------------------------------
    context_total = (totals["input_tokens"] + totals["cache_creation_input_tokens"]
                     + totals["cache_read_input_tokens"])
    grand_total = context_total + totals["output_tokens"]

    def _tok(row: dict[str, Any]) -> int:
        return sum(row[k] for k in TOKEN_KEYS)

    models_out = sorted(
        ({"model": m, **r, "total_tokens": _tok(r), "share": _share(_tok(r), grand_total)}
         for m, r in by_model.items()),
        key=lambda r: -r["total_tokens"])
    days_out = [{"day": d, **r, "total_tokens": _tok(r)} for d, r in sorted(by_day.items())]
    projects_out = sorted(
        ({**r, "name": r["name"] or r["slug"], "total_tokens": _tok(r),
          "share": _share(_tok(r), grand_total)}
         for r in by_project.values() if r["requests"]),
        key=lambda r: -r["total_tokens"])
    buckets_out = [
        {"bucket": label, "requests": b["requests"], "tokens": b["tokens"],
         "request_share": _share(b["requests"], requests),
         "token_share": _share(b["tokens"], context_total)}
        for (label, _u), b in zip(BUCKETS, buckets)
    ]

    sessions.sort(key=lambda s: (-s["context_tokens"], s["file"]))
    top_sessions = [
        {**s, "project_name": by_project[s["project"]]["name"] or s["project"],
         "share": _share(s["context_tokens"], context_total)}
        for s in sessions[:top]
    ]
    top_tokens = sum(s["context_tokens"] for s in sessions[:top])
    # A resumed session's first request already carries its whole history, so its
    # first-request context is not fixed overhead. Cap each session's baseline at
    # twice the median first request so those sessions do not inflate the estimate.
    firsts = sorted(s["first_context"] for s in sessions)
    baseline_cap = 2 * firsts[len(firsts) // 2] if firsts else 0
    baselines = [min(s["first_context"], baseline_cap) for s in sessions]
    overhead = sum(b * s["requests"] for b, s in zip(baselines, sessions))
    first_avg = round(sum(baselines) / len(baselines)) if baselines else 0

    tool_chars = sum(t["chars"] for t in tools.values())
    tools_out = sorted(
        ({"tool": n, **t, "share": _share(t["chars"], tool_chars)} for n, t in tools.items()),
        key=lambda t: (-t["chars"], -t["calls"], t["tool"]))
    reread_top = sorted(
        ({"file_path": p, **r} for p, r in reread_files.items() if r["rereads"]),
        key=lambda r: (-r["rereads"], -r["chars_reread"], r["file_path"]))[:top]

    report: dict[str, Any] = {
        "generated_at": now.isoformat(),
        "source": {
            "dir": str(root),
            "files": counters["files"],
            "malformed_lines": counters["malformed_lines"],
            "unreadable_files": counters["unreadable_files"],
            "days": days if cutoff else None,
            "project": project or None,
            "top": top,
            "timezone": "UTC",
        },
        "totals": {
            **totals,
            "context_tokens": context_total,
            "total_tokens": grand_total,
            "requests": requests,
            "sessions": len(sessions),
            "avg_context_per_request": round(context_total / requests) if requests else 0,
        },
        "by_model": models_out,
        "by_day": days_out,
        "by_project": projects_out,
        "context_buckets": buckets_out,
        "sessions": {
            "count": len(sessions),
            "top_n": len(top_sessions),
            "top_tokens": top_tokens,
            "top_share": _share(top_tokens, context_total),
            "over_200k": sum(1 for s in sessions if s["max_context"] >= 200_000),
            "over_400k": sum(1 for s in sessions if s["max_context"] >= 400_000),
            "top": top_sessions,
        },
        "overhead": {
            "estimate": True,
            "method": "sum over sessions of first-request context (capped at 2x the median) x requests",
            "tokens": overhead,
            "share": _share(overhead, context_total),
            "avg_first_context": first_avg,
        },
        "tools": {"total_chars": tool_chars, "by_tool": tools_out},
        "rereads": {
            "reads": reads,
            "rereads": rereads,
            "rate": _share(rereads, reads),
            "read_chars": read_chars,
            "chars_reread": reread_chars,
            "top_files": reread_top,
        },
    }
    report["recommendations"] = recommend(report)
    return report


def recommend(report: dict[str, Any]) -> list[str]:
    """Plain statements derived from the numbers. Facts first, then the action."""
    t = report["totals"]
    if not t["requests"]:
        return []
    out: list[str] = []
    b = {row["bucket"]: row for row in report["context_buckets"]}
    over200 = b["200-400k"]["token_share"] + b["400k+"]["token_share"]
    over200_req = b["200-400k"]["request_share"] + b["400k+"]["request_share"]
    if over200 >= 0.2:
        out.append(
            f"{_pct(over200)} of context tokens came from the {_pct(over200_req)} of requests "
            f"sent with more than 200k of context ({_pct(b['400k+']['token_share'])} from "
            f"requests above 400k). Average context per request is "
            f"{_num(t['avg_context_per_request'])}. Compact or start a new session before "
            f"the context passes 200k.")
    s = report["sessions"]
    if s["count"] > s["top_n"] and s["top_share"] >= 0.3:
        out.append(
            f"The top {s['top_n']} of {s['count']} sessions account for {_pct(s['top_share'])} "
            f"of context tokens. {s['over_400k']} sessions peaked above 400k and "
            f"{s['over_200k']} above 200k. Split long sessions into one task each.")
    elif s["over_400k"]:
        out.append(
            f"{s['over_400k']} of {s['count']} sessions peaked above 400k of context. "
            f"Split them into one task each.")
    o = report["overhead"]
    if o["share"] >= 0.1:
        out.append(
            f"A session starts at {_num(o['avg_first_context'])} tokens of context on average, "
            f"and that amount is re-read on every request: an estimated {_num(o['tokens'])} "
            f"tokens, {_pct(o['share'])} of all context. Remove unused MCP servers, skills and "
            f"long instruction files to lower it.")
    tools = report["tools"]["by_tool"]
    if tools and report["tools"]["total_chars"]:
        head = tools[0]
        if head["share"] >= 0.25:
            per = head["chars"] // head["results"] if head["results"] else 0
            out.append(
                f"{head['tool']} results are {_pct(head['share'])} of all tool-result text "
                f"({_num(head['chars'])} chars over {head['results']:,} results, "
                f"{_num(per)} per result). Narrow these calls: limits, offsets, filters.")
    r = report["rereads"]
    if r["reads"] >= 5 and r["rate"] >= 0.1:
        out.append(
            f"{_pct(r['rate'])} of Read calls ({r['rereads']:,} of {r['reads']:,}) re-read a "
            f"file already read in the same session, adding {_num(r['chars_reread'])} chars. "
            f"A graph query or a targeted line range avoids the repeat.")
    return out


# ---------------------------------------------------------------------------
# Formatting
# ---------------------------------------------------------------------------

def _num(n: float) -> str:
    n = float(n)
    for limit, suffix in ((1e9, "B"), (1e6, "M"), (1e3, "k")):
        if abs(n) >= limit:
            v = n / limit
            return f"{v:.2f}{suffix}" if v < 10 else f"{v:.1f}{suffix}" if v < 100 else f"{v:.0f}{suffix}"
    return f"{n:.0f}"


def _pct(x: float) -> str:
    return f"{x * 100:.0f}%" if x >= 0.1 or x == 0 else f"{x * 100:.1f}%"


def _short(text: str, width: int) -> str:
    return text if len(text) <= width else "..." + text[-(width - 3):]


def _table(headers: list[str], rows: list[list[str]], left: int = 1) -> list[str]:
    """Plain aligned columns; the first *left* columns are left-aligned."""
    widths = [max(len(h), *(len(r[i]) for r in rows)) if rows else len(h)
              for i, h in enumerate(headers)]

    def fmt(cells: list[str]) -> str:
        parts = [c.ljust(w) if i < left else c.rjust(w)
                 for i, (c, w) in enumerate(zip(cells, widths))]
        return "  " + "  ".join(parts).rstrip()

    return [fmt(headers), "  " + "  ".join("-" * w for w in widths), *map(fmt, rows)]


_EMPTY = "No Claude Code transcripts found under {dir}."


def render_text(report: dict[str, Any]) -> str:
    """Terminal summary."""
    t, src = report["totals"], report["source"]
    if not t["requests"]:
        return _EMPTY.format(dir=src["dir"])
    scope = []
    if src["days"]:
        scope.append(f"last {src['days']} days")
    if src["project"]:
        scope.append(f"project~{src['project']}")
    lines = [
        "graphify usage - " + (", ".join(scope) if scope else "all transcripts"),
        f"  {src['dir']}  ({src['files']:,} files)",
        "",
        f"  total tokens   {_num(t['total_tokens']):>8}   requests  {t['requests']:,}",
        f"  cache read     {_num(t['cache_read_input_tokens']):>8}   sessions  {t['sessions']:,}",
        f"  cache write    {_num(t['cache_creation_input_tokens']):>8}   "
        f"avg context/request  {_num(t['avg_context_per_request'])}",
        f"  input          {_num(t['input_tokens']):>8}",
        f"  output         {_num(t['output_tokens']):>8}",
        "",
        "Context size per request",
    ]
    lines += _table(
        ["context", "requests", "req %", "tokens", "tok %"],
        [[b["bucket"], f"{b['requests']:,}", _pct(b["request_share"]), _num(b["tokens"]),
          _pct(b["token_share"])] for b in report["context_buckets"]])
    o = report["overhead"]
    lines += [
        "",
        f"Fixed overhead (estimate): {_num(o['tokens'])} tokens, {_pct(o['share'])} of context",
        f"  = first-request context x requests, per session; "
        f"avg first request {_num(o['avg_first_context'])}",
        "",
        "By model",
    ]
    lines += _table(
        ["model", "requests", "tokens", "share", "output"],
        [[m["model"], f"{m['requests']:,}", _num(m["total_tokens"]), _pct(m["share"]),
          _num(m["output_tokens"])] for m in report["by_model"]])
    top = src["top"]
    lines += ["", f"By project (top {min(top, len(report['by_project']))})"]
    lines += _table(
        ["project", "sessions", "requests", "tokens", "share"],
        [[_short(p["name"], 48), f"{p['sessions']:,}", f"{p['requests']:,}",
          _num(p["total_tokens"]), _pct(p["share"])] for p in report["by_project"][:top]])
    s = report["sessions"]
    lines += ["", f"Top {s['top_n']} of {s['count']} sessions = {_pct(s['top_share'])} of context"]
    lines += _table(
        ["session", "project", "requests", "context", "max", "first", "share"],
        [[x["id"][:18], _short(x["project_name"], 30), f"{x['requests']:,}",
          _num(x["context_tokens"]), _num(x["max_context"]), _num(x["first_context"]),
          _pct(x["share"])] for x in s["top"]], left=2)
    days = report["by_day"][-14:]
    lines += ["", f"By day (UTC, last {len(days)})"]
    lines += _table(
        ["day", "requests", "tokens", "output"],
        [[d["day"], f"{d['requests']:,}", _num(d["total_tokens"]), _num(d["output_tokens"])]
         for d in days])
    lines += ["", "Tool results"]
    lines += _table(
        ["tool", "calls", "chars", "share"],
        [[_short(x["tool"], 48), f"{x['calls']:,}", _num(x["chars"]), _pct(x["share"])]
         for x in report["tools"]["by_tool"][:top]])
    r = report["rereads"]
    lines += [
        "",
        f"Re-reads: {r['rereads']:,} of {r['reads']:,} Read calls ({_pct(r['rate'])}), "
        f"{_num(r['chars_reread'])} chars re-read",
    ]
    if r["top_files"]:
        lines += _table(
            ["file", "reads", "re-reads", "chars"],
            [[_short(f["file_path"], 64), str(f["reads"]), str(f["rereads"]),
              _num(f["chars_reread"])] for f in r["top_files"][:10]])
    if report["recommendations"]:
        lines += ["", "What the numbers say"]
        lines += [f"  - {rec}" for rec in report["recommendations"]]
    if src["malformed_lines"]:
        lines += ["", f"  ({src['malformed_lines']:,} malformed lines skipped)"]
    return "\n".join(lines)


# -- HTML -------------------------------------------------------------------

_CSS = """
:root{--page:#f9f9f7;--surface:#fcfcfb;--ink:#0b0b0b;--ink2:#52514e;--line:#e3e2dd;
--bar:#2a78d6;--bar-hot:#eb6834}
@media (prefers-color-scheme:dark){:root{--page:#0d0d0d;--surface:#1a1a19;--ink:#f0efec;
--ink2:#c3c2b7;--line:#383835;--bar:#3987e5;--bar-hot:#d95926}}
*{box-sizing:border-box}
body{margin:0;background:var(--page);color:var(--ink);
font:14px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif}
main{max-width:1040px;margin:0 auto;padding:24px 16px 48px}
h1{font-size:22px;margin:0 0 4px}
h2{font-size:15px;margin:0 0 12px}
.sub,.note{color:var(--ink2);font-size:13px}
.note{margin:8px 0 0}
section{background:var(--surface);border:1px solid var(--line);border-radius:8px;
padding:16px;margin-top:16px}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;
margin-top:16px}
.tile{background:var(--surface);border:1px solid var(--line);border-radius:8px;padding:12px 14px}
.tile b{display:block;font-size:24px;font-weight:600;line-height:1.2}
.tile span{color:var(--ink2);font-size:12px}
.scroll{overflow-x:auto}
table{border-collapse:collapse;width:100%;font-size:13px}
th,td{padding:5px 10px 5px 0;text-align:right;white-space:nowrap;
border-bottom:1px solid var(--line);font-variant-numeric:tabular-nums}
th{color:var(--ink2);font-weight:500}
th.l,td.l{text-align:left}
td.p{white-space:normal;word-break:break-all;min-width:180px}
tr:last-child td{border-bottom:0}
svg{display:block;width:100%;height:auto}
svg text{fill:var(--ink2);font-size:11px}
svg text.v{fill:var(--ink)}
.bar{fill:var(--bar)}.hot{fill:var(--bar-hot)}.axis{stroke:var(--line);stroke-width:1}
.legend{display:flex;gap:16px;font-size:12px;color:var(--ink2);margin-bottom:8px}
.legend i{display:inline-block;width:10px;height:10px;border-radius:2px;margin-right:6px}
ul{margin:0;padding-left:20px}li{margin:6px 0}
"""


def _e(value: Any) -> str:
    return html.escape(str(value), quote=True)


def _html_table(headers: list[str], rows: list[list[Any]], left: int = 1,
                wrap: tuple[int, ...] = ()) -> str:
    def cls(i: int) -> str:
        names = (["l"] if i < left else []) + (["p"] if i in wrap else [])
        return f' class="{" ".join(names)}"' if names else ""

    head = "".join(f"<th{cls(i)}>{_e(h)}</th>" for i, h in enumerate(headers))
    body = "".join(
        "<tr>" + "".join(f"<td{cls(i)}>{_e(c)}</td>" for i, c in enumerate(r)) + "</tr>"
        for r in rows)
    return f'<div class="scroll"><table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>'


def _svg_buckets(buckets: list[dict[str, Any]]) -> str:
    """Horizontal bars: context tokens per context-size bucket."""
    w, row, label_w, value_w = 720, 30, 76, 170
    span = w - label_w - value_w
    peak = max((b["tokens"] for b in buckets), default=0) or 1
    parts = [f'<svg viewBox="0 0 {w} {row * len(buckets) + 4}" role="img" '
             f'aria-label="Context tokens by request context size">']
    for i, b in enumerate(buckets):
        y = i * row + 4
        bw = max(span * b["tokens"] / peak, 1 if b["tokens"] else 0)
        hot = " hot" if b["bucket"] in ("200-400k", "400k+") else ""
        tip = (f"{b['bucket']}: {_num(b['tokens'])} tokens ({_pct(b['token_share'])}), "
               f"{b['requests']:,} requests ({_pct(b['request_share'])})")
        parts.append(
            f'<g><title>{_e(tip)}</title>'
            f'<text x="{label_w - 8}" y="{y + 15}" text-anchor="end">{_e(b["bucket"])}</text>'
            f'<rect class="bar{hot}" x="{label_w}" y="{y}" width="{bw:.1f}" height="20" rx="3"/>'
            f'<text class="v" x="{label_w + bw + 8:.1f}" y="{y + 15}">'
            f'{_e(_pct(b["token_share"]))} of tokens, {_e(_pct(b["request_share"]))} of requests'
            f'</text></g>')
    parts.append("</svg>")
    return "".join(parts)


def _svg_days(days: list[dict[str, Any]]) -> str:
    """Vertical bars: total tokens per day."""
    w, h, left, bottom, top = 720, 200, 48, 22, 10
    plot_w, plot_h = w - left - 4, h - bottom - top
    peak = max((d["total_tokens"] for d in days), default=0) or 1
    n = max(len(days), 1)
    step = plot_w / n
    bar_w = max(min(step - 2, 28), 1)
    base = top + plot_h
    parts = [f'<svg viewBox="0 0 {w} {h}" role="img" aria-label="Total tokens per day">',
             f'<text x="{left - 6}" y="{top + 4}" text-anchor="end">{_e(_num(peak))}</text>',
             f'<text x="{left - 6}" y="{base}" text-anchor="end">0</text>',
             f'<line class="axis" x1="{left}" y1="{top}" x2="{w - 4}" y2="{top}"/>']
    label_every = max(1, -(-n // 8))
    for i, d in enumerate(days):
        bh = plot_h * d["total_tokens"] / peak
        x = left + i * step + (step - bar_w) / 2
        tip = f"{d['day']}: {_num(d['total_tokens'])} tokens, {d['requests']:,} requests"
        parts.append(
            f'<g><title>{_e(tip)}</title><rect class="bar" x="{x:.1f}" y="{base - bh:.1f}" '
            f'width="{bar_w:.1f}" height="{bh:.1f}" rx="{min(3, bar_w / 2):.1f}"/></g>')
        if i % label_every == 0:
            parts.append(f'<text x="{x + bar_w / 2:.1f}" y="{h - 6}" text-anchor="middle">'
                         f'{_e(d["day"][5:])}</text>')
    parts.append(f'<line class="axis" x1="{left}" y1="{base}" x2="{w - 4}" y2="{base}"/></svg>')
    return "".join(parts)


def render_html(report: dict[str, Any]) -> str:
    """One self-contained HTML document: inline CSS and SVG, no network."""
    t, src = report["totals"], report["source"]
    s, o, r = report["sessions"], report["overhead"], report["rereads"]
    top = src["top"]
    scope = []
    if src["days"]:
        scope.append(f"last {src['days']} days")
    if src["project"]:
        scope.append(f"project contains “{src['project']}”")
    scope_text = ", ".join(scope) if scope else "all transcripts"
    tiles = [
        (_num(t["total_tokens"]), "total tokens"),
        (f"{t['requests']:,}", "requests"),
        (_num(t["avg_context_per_request"]), "average context per request"),
        (f"{t['sessions']:,}", "sessions"),
        (_pct(s["top_share"]), f"of context in the top {s['top_n']} sessions"),
        (_pct(o["share"]), "fixed overhead (estimate)"),
        (_pct(r["rate"]), "of Read calls are re-reads"),
    ]
    out = [
        '<!doctype html><html lang="en"><head><meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width,initial-scale=1">',
        f"<title>Token usage</title><style>{_CSS}</style></head><body><main>",
        "<h1>Where the tokens went</h1>",
        f'<div class="sub">{_e(scope_text)} · {src["files"]:,} transcript files · '
        f'generated {_e(report["generated_at"][:16].replace("T", " "))} UTC</div>',
    ]
    if not t["requests"]:
        out.append(f"<section>{_e(_EMPTY.format(dir=src['dir']))}</section></main></body></html>")
        return "".join(out)
    out.append('<div class="tiles">' + "".join(
        f'<div class="tile"><b>{_e(v)}</b><span>{_e(k)}</span></div>' for v, k in tiles) + "</div>")
    if report["recommendations"]:
        out.append("<section><h2>What the numbers say</h2><ul>" + "".join(
            f"<li>{_e(x)}</li>" for x in report["recommendations"]) + "</ul></section>")
    out.append(
        "<section><h2>Context tokens by request context size</h2>"
        '<div class="legend"><span><i style="background:var(--bar)"></i>up to 200k</span>'
        '<span><i style="background:var(--bar-hot)"></i>above 200k</span></div>'
        + _svg_buckets(report["context_buckets"])
        + '<p class="note">Context = input + cache write + cache read tokens of one request.</p>'
        + _html_table(
            ["Context", "Requests", "Request share", "Tokens", "Token share"],
            [[b["bucket"], f"{b['requests']:,}", _pct(b["request_share"]), _num(b["tokens"]),
              _pct(b["token_share"])] for b in report["context_buckets"]])
        + "</section>")
    out.append(
        "<section><h2>Fixed overhead (estimate)</h2>"
        f"<p style=\"margin:0\">About <b>{_e(_num(o['tokens']))}</b> tokens, "
        f"<b>{_e(_pct(o['share']))}</b> of all context. A session's first request carries "
        f"{_e(_num(o['avg_first_context']))} tokens on average before any work is done.</p>"
        '<p class="note">Estimate: first-request context × number of requests, summed over '
        "sessions. It assumes the starting context is sent again on every request and overstates "
        "sessions that were resumed with history or compacted later.</p></section>")
    out.append("<section><h2>Total tokens per day (UTC)</h2>" + _svg_days(report["by_day"])
               + "</section>")
    out.append(
        "<section><h2>Token types</h2>" + _html_table(
            ["Type", "Tokens", "Share"],
            [[label, _num(t[k]), _pct(_share(t[k], t["total_tokens"]))] for label, k in (
                ("Cache read", "cache_read_input_tokens"),
                ("Cache write", "cache_creation_input_tokens"),
                ("Input (uncached)", "input_tokens"),
                ("Output", "output_tokens"))]) + "</section>")
    out.append(
        "<section><h2>By model</h2>" + _html_table(
            ["Model", "Requests", "Tokens", "Share", "Output"],
            [[m["model"], f"{m['requests']:,}", _num(m["total_tokens"]), _pct(m["share"]),
              _num(m["output_tokens"])] for m in report["by_model"]]) + "</section>")
    out.append(
        f"<section><h2>By project (top {min(top, len(report['by_project']))} of "
        f"{len(report['by_project'])})</h2>" + _html_table(
            ["Project", "Sessions", "Requests", "Tokens", "Share"],
            [[p["name"], f"{p['sessions']:,}", f"{p['requests']:,}", _num(p["total_tokens"]),
              _pct(p["share"])] for p in report["by_project"][:top]], wrap=(0,)) + "</section>")
    out.append(
        f"<section><h2>Top {s['top_n']} of {s['count']:,} sessions: {_e(_pct(s['top_share']))} "
        "of context</h2>" + _html_table(
            ["Session", "Project", "Started", "Requests", "Context", "Max", "First", "Share"],
            [[x["id"][:18] + (" (subagent)" if x["subagent"] else ""), x["project_name"],
              x["start"][:10], f"{x['requests']:,}", _num(x["context_tokens"]),
              _num(x["max_context"]), _num(x["first_context"]), _pct(x["share"])]
             for x in s["top"]], left=2, wrap=(1,))
        + '<p class="note">One transcript file is one session; subagent transcripts count '
          "separately. Max and First are the largest and the first request context.</p></section>")
    out.append(
        "<section><h2>Tool results</h2>" + _html_table(
            ["Tool", "Calls", "Result chars", "Share"],
            [[x["tool"], f"{x['calls']:,}", _num(x["chars"]), _pct(x["share"])]
             for x in report["tools"]["by_tool"][:top]], wrap=(0,)) + "</section>")
    reread = (
        f"<section><h2>Re-reads</h2><p style=\"margin:0 0 12px\"><b>{r['rereads']:,}</b> of "
        f"{r['reads']:,} Read calls ({_e(_pct(r['rate']))}) read a file that was already read in "
        f"the same session, adding {_e(_num(r['chars_reread']))} chars.</p>")
    if r["top_files"]:
        reread += _html_table(
            ["File", "Reads", "Re-reads", "Chars re-read"],
            [[f["file_path"], f["reads"], f["rereads"], _num(f["chars_reread"])]
             for f in r["top_files"]], wrap=(0,))
    out.append(reread + "</section>")
    out.append(
        f'<p class="note">Source: {_e(src["dir"])}. Counts, sizes, paths, model names and dates '
        "only; no transcript content is stored in this file."
        + (f" {src['malformed_lines']:,} malformed lines skipped." if src["malformed_lines"] else "")
        + "</p></main></body></html>")
    return "".join(out)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _positive(value: str) -> int:
    n = int(value)
    if n < 1:
        raise argparse.ArgumentTypeError("must be >= 1")
    return n


def main(argv: list[str] | None = None) -> int:
    """`graphify usage [--days N] [--project SUBSTR] [--top N] [--json] [--html [PATH]] [--dir PATH]`."""
    parser = argparse.ArgumentParser(
        prog="graphify usage",
        description="Show where Claude Code tokens went, from the session transcripts.")
    parser.add_argument("--days", type=_positive, metavar="N", help="only the last N days")
    parser.add_argument("--project", metavar="SUBSTR",
                        help="only projects whose directory or cwd contains SUBSTR")
    parser.add_argument("--top", type=_positive, default=DEFAULT_TOP, metavar="N",
                        help=f"rows in ranked lists (default {DEFAULT_TOP})")
    parser.add_argument("--json", action="store_true", help="print one JSON document")
    parser.add_argument("--html", nargs="?", const=DEFAULT_HTML, metavar="PATH",
                        help=f"write a self-contained HTML report (default {DEFAULT_HTML})")
    parser.add_argument("--dir", metavar="PATH",
                        help="transcripts directory (default $CLAUDE_CONFIG_DIR/projects "
                             "or ~/.claude/projects)")
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)

    report = analyze(args.dir, days=args.days, project=args.project, top=args.top)
    empty = not report["totals"]["requests"]
    if empty and not args.json:
        print(_EMPTY.format(dir=report["source"]["dir"]))
        return 0
    if args.html and not empty:
        out = Path(args.html).expanduser()
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(render_html(report), encoding="utf-8")
        # With --json, stdout stays one JSON document.
        print(str(out), file=sys.stderr if args.json else sys.stdout)
    if args.json:
        if empty:
            print(_EMPTY.format(dir=report["source"]["dir"]), file=sys.stderr)
        print(json.dumps(report, indent=2, ensure_ascii=False))
    elif not args.html:
        print(render_text(report))
    return 0


if __name__ == "__main__":
    sys.exit(main())
