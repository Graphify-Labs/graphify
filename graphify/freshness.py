"""Auto-refresh enforcement for the MCP query path (opt-in prototype).

When ``GRAPHIFY_AUTO_REFRESH=1`` (or the server is started with
``--auto-refresh``), every MCP tool call that carries a ``project_path`` first
verifies that ``<project_path>/graphify-out/graph.json`` was built at the
repository's current git HEAD; if not, it runs ``graphify update`` once (a
subprocess, bounded by a timeout) before answering, so tool answers reflect the
code the agent can actually see.

Fail-open by design: a missing ``git``, a non-repo project path, a rebuild
failure or a timeout never raises and never exits; the call is answered from
whatever graph is on disk and prefixed with a clear STALE / refresh-failed
banner.

Memoisation exists to survive the ``graphify update`` no-restamp behaviour: a
commit that does not change graph topology leaves ``graph.json`` untouched
(``watch.py`` strips ``built_at_commit`` before the no-op comparison), so
``built_at_commit`` keeps naming the *older* commit. Without a memo a naive
``built_at_commit != HEAD`` check would rebuild on every call forever; here a
successful rebuild records HEAD, and later calls at the same HEAD skip all work.

This module is self-contained: the only hook in ``serve.py`` is a call to
:func:`ensure_fresh` from ``call_tool`` before ``_warm_graph`` / ``_select_graph``
plus the provenance lines :func:`graph_stats_lines` adds to ``graph_stats``
when the feature is opted in (v8 already reports built-at-commit in
``graph_stats`` unconditionally; the extra lines add a freshness state).
"""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

_TRUTHY = {"1", "true", "yes", "on"}
_DEFAULT_TIMEOUT = 120.0
_DEFAULT_DEBOUNCE = 30.0


def _flag(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in _TRUTHY


def enabled() -> bool:
    """True when auto-refresh is opted in (env var; ``--auto-refresh`` sets it)."""
    return _flag("GRAPHIFY_AUTO_REFRESH")


def dirty_enabled() -> bool:
    """True when working-tree (uncommitted) changes also trigger a rebuild."""
    return enabled() and _flag("GRAPHIFY_AUTO_REFRESH_DIRTY")


def _float_env(name: str, default: float, minimum: float = 0.0) -> float:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return max(minimum, float(raw))
    except ValueError:
        return default


def _timeout() -> float:
    return _float_env("GRAPHIFY_AUTO_REFRESH_TIMEOUT", _DEFAULT_TIMEOUT, 1.0)


def _debounce() -> float:
    return _float_env("GRAPHIFY_AUTO_REFRESH_DEBOUNCE", _DEFAULT_DEBOUNCE, 0.0)


@dataclass
class Freshness:
    """Outcome of one freshness check. ``banner`` is '' when there is nothing
    worth telling the caller (fresh graph, or feature not applicable)."""

    state: str  # skipped | fresh | refreshed | failed
    banner: str = ""
    built: str | None = None
    head: str | None = None
    reason: str = ""
    durations: dict = field(default_factory=dict)


@dataclass
class Provenance:
    built: str | None
    head: str | None
    state: str  # fresh | stale | unknown


# ---------------------------------------------------------------------------
# Shared state
# ---------------------------------------------------------------------------

_STATE_LOCK = threading.Lock()
_BUILD_LOCKS: dict[str, threading.Lock] = {}
_MEMO: dict[str, "_RepoState"] = {}
_BUILT_CACHE: dict[str, tuple[tuple[int, int], str | None]] = {}


@dataclass
class _RepoState:
    """Per-repo results, keyed by a freshness key (HEAD, or HEAD+fingerprint)."""

    ok_key: str | None = None
    ok_head: str | None = None
    ok_fp: str | None = None
    ok_ts: float = 0.0
    fail_key: str | None = None


def reset_state() -> None:
    """Test helper: drop all memoised state and per-repo locks."""
    with _STATE_LOCK:
        _BUILD_LOCKS.clear()
        _MEMO.clear()
        _BUILT_CACHE.clear()


def _short(commit: str | None) -> str:
    if not commit:
        return "unknown"
    return commit[:8]


# ---------------------------------------------------------------------------
# git + graph probes
# ---------------------------------------------------------------------------


def _git(args: list[str], cwd: "str | Path", timeout: float = 3.0) -> str | None:
    """Run ``git args`` in ``cwd``; return stripped stdout or None on any failure."""
    try:
        proc = subprocess.run(
            ["git", *args],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except Exception:
        return None
    if proc.returncode != 0:
        return None
    return proc.stdout.strip()


def _git_head(root: "str | Path") -> str | None:
    return _git(["rev-parse", "HEAD"], root) or None


def _repo_root(project_path: "str | Path") -> str | None:
    out = _git(["rev-parse", "--show-toplevel"], project_path)
    return out or None


def _parse_built_commit(graph_path: str) -> str | None:
    """Read the top-level ``built_at_commit`` from graph.json without loading it
    into a graph. Streams the file looking for the key so a very large graph is
    not fully materialised in memory; the result is cached per (mtime, size)."""
    try:
        with open(graph_path, "rb") as fh:
            needle = b'"built_at_commit"'
            tail = b""
            while True:
                chunk = fh.read(1 << 20)
                if not chunk:
                    return None
                buf = tail + chunk
                idx = buf.find(needle)
                if idx != -1:
                    rest = buf[idx + len(needle):]
                    colon = rest.find(b":")
                    if colon == -1:
                        # key split across the 1 MiB boundary; keep the tail
                        tail = buf[idx:]
                        continue
                    after = rest[colon + 1:].lstrip()
                    if not after.startswith(b'"'):
                        return None
                    end = after.find(b'"', 1)
                    if end == -1:
                        tail = buf[idx:]
                        continue
                    return after[1:end].decode("utf-8", "replace")
                tail = buf[-64:]
    except OSError:
        return None


def read_built_commit(graph_path: str) -> str | None:
    """Cached read of ``built_at_commit`` (keyed by mtime_ns + size)."""
    try:
        st = os.stat(graph_path)
    except OSError:
        return None
    key = (st.st_mtime_ns, st.st_size)
    with _STATE_LOCK:
        cached = _BUILT_CACHE.get(graph_path)
        if cached is not None and cached[0] == key:
            return cached[1]
    commit = _parse_built_commit(graph_path)
    with _STATE_LOCK:
        _BUILT_CACHE[graph_path] = (key, commit)
    return commit


def _graph_path(project_path: "str | Path") -> str:
    from graphify.paths import GRAPHIFY_OUT

    return str(Path(project_path) / GRAPHIFY_OUT / "graph.json")


# ---------------------------------------------------------------------------
# Dirty working-tree fingerprint
# ---------------------------------------------------------------------------

_CLEAN_FP = hashlib.sha1(b"").hexdigest()


def _dirty_fingerprint(root: str) -> str | None:
    """Cheap-ish fingerprint of the working tree: ``git status --porcelain``
    plus the mtimes of every changed path. ``None`` if git is unavailable."""
    porcelain = _git(["status", "--porcelain"], root, timeout=5.0)
    if porcelain is None:
        return None
    if not porcelain.strip():
        return _CLEAN_FP
    parts = [porcelain]
    for line in porcelain.splitlines():
        path = line[3:].strip()
        if " -> " in path:  # rename: fingerprint the destination
            path = path.split(" -> ", 1)[1]
        path = path.strip('"')
        try:
            parts.append(str(os.stat(Path(root) / path).st_mtime_ns))
        except OSError:
            parts.append("missing")
    return hashlib.sha1("\n".join(parts).encode("utf-8", "replace")).hexdigest()


# ---------------------------------------------------------------------------
# The update subprocess
# ---------------------------------------------------------------------------


def _update_command(root: str) -> list[str]:
    """argv for the rebuild. A subprocess (not an in-process ``_rebuild_code``)
    so the console-script ``PYTHONHASHSEED=0`` re-exec in ``__main__`` applies;
    an in-process call would re-cluster non-deterministically. Kept as a
    function so tests can monkeypatch the executable (failure injection)."""
    exe = sys.executable or "graphify"
    return [exe, "-m", "graphify", "update", root]


def _run_update(root: str) -> tuple[bool, str, float]:
    """Run one rebuild, foreground, bounded by ``GRAPHIFY_AUTO_REFRESH_TIMEOUT``.

    ``GRAPHIFY_AUTO_REFRESH_LOG`` (a file path), when set, appends one line per
    attempted rebuild — used by tests to count invocations precisely.
    """
    timeout = _timeout()
    started = time.monotonic()
    ok = True
    reason = ""
    try:
        proc = subprocess.run(
            _update_command(root),
            cwd=root,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        ok, reason = False, f"timeout after {timeout:g}s"
    except Exception as exc:  # missing binary, permission, OSError, ...
        ok, reason = False, f"{type(exc).__name__}: {exc}"
    else:
        if proc.returncode != 0:
            lines = [ln for ln in (proc.stderr or proc.stdout or "").splitlines() if ln.strip()]
            detail = lines[-1] if lines else ""
            ok = False
            reason = f"exit {proc.returncode}{': ' + detail if detail else ''}"
    duration = time.monotonic() - started
    _log_attempt(root, ok, duration, reason)
    return ok, reason, duration


def _log_attempt(root: str, ok: bool, duration: float, reason: str) -> None:
    path = os.environ.get("GRAPHIFY_AUTO_REFRESH_LOG", "").strip()
    if not path:
        return
    try:
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(
                f"{time.time():.3f}\tok={int(ok)}\tdur={duration:.3f}\t{root}\t{reason}\n"
            )
    except OSError:
        pass


def _build_lock(root: str) -> threading.Lock:
    with _STATE_LOCK:
        lock = _BUILD_LOCKS.get(root)
        if lock is None:
            lock = _BUILD_LOCKS[root] = threading.Lock()
        return lock


# ---------------------------------------------------------------------------
# Banners
# ---------------------------------------------------------------------------


def _refreshed_banner(built: str | None, head: str, dirty: bool, duration: float) -> str:
    if built is None:
        return f"[graphify] no graph existed; built for HEAD {_short(head)} in {duration:.1f}s"
    if built != head:
        return (
            f"[graphify] graph was behind HEAD ({_short(built)}\u2192{_short(head)}); "
            f"rebuilt in {duration:.1f}s"
        )
    if dirty:
        return f"[graphify] graph refreshed for uncommitted changes; rebuilt in {duration:.1f}s"
    return f"[graphify] graph rebuilt in {duration:.1f}s"


def _failed_banner(built: str | None, head: str, exists: bool, reason: str) -> str:
    if not exists:
        return (
            f"[graphify] no graph.json yet and auto-refresh failed ({reason}); "
            "run `graphify update .` manually."
        )
    return (
        f"[graphify] graph may be STALE (built {_short(built)}, HEAD {_short(head)}); "
        f"auto-refresh failed ({reason}). Serving the existing graph."
    )


# ---------------------------------------------------------------------------
# Public entry points
# ---------------------------------------------------------------------------


def ensure_fresh(project_path) -> Freshness:
    """Ensure the project's graph matches HEAD; never raises.

    Returns a :class:`Freshness` whose ``banner`` is empty when there is nothing
    to report.
    """
    if not project_path:
        return Freshness("skipped", reason="global graph (no project_path)")
    try:
        return _ensure_fresh(str(project_path))
    except Exception as exc:  # defensive: freshness must never break a tool call
        return Freshness(
            "failed",
            banner=f"[graphify] freshness check failed ({type(exc).__name__}: {exc}); "
            "serving the existing graph.",
            reason=f"{type(exc).__name__}: {exc}",
        )


def _ensure_fresh(project_path: str) -> Freshness:
    project = Path(project_path)
    if not project.exists():
        return Freshness("skipped", reason="project_path does not exist")
    root = _repo_root(project)
    if not root:
        return Freshness("skipped", reason="not a git repository")
    head = _git_head(root)
    if not head:
        return Freshness("skipped", reason="git HEAD unavailable")

    graph_path = _graph_path(project_path)
    exists = os.path.exists(graph_path)
    built = read_built_commit(graph_path) if exists else None

    dirty = dirty_enabled()
    fp: str | None = None
    if dirty:
        fp = _dirty_fingerprint(root)
        if fp is None:
            dirty = False  # git status unavailable -> commit-only behaviour

    key = head if not dirty else f"{head}:{fp}"

    with _STATE_LOCK:
        st = _MEMO.get(root)
    # Fast paths: already known-good, or a known failure we must not retry.
    if st is not None and exists:
        if st.ok_key == key:
            return Freshness("fresh", built=built, head=head, reason="memoised")
        if st.fail_key == key:
            return Freshness(
                "failed",
                banner=_failed_banner(built, head, exists=True, reason="previous refresh failed"),
                built=built,
                head=head,
                reason="previous refresh failed",
            )

    commit_stale = (not exists) or (built != head)

    dirty_stale = False
    if dirty:
        if st is None or st.ok_fp is None:
            # First sighting in dirty mode: rebuild once if the tree is dirty.
            dirty_stale = fp != _CLEAN_FP
        elif fp != st.ok_fp:
            if (time.monotonic() - st.ok_ts) >= _debounce():
                dirty_stale = True
            else:
                return Freshness("fresh", built=built, head=head, reason="debounce")

    if not commit_stale and not dirty_stale:
        if st is None:
            # Establish the baseline so a later dirty edit has an fp to compare.
            with _STATE_LOCK:
                _MEMO[root] = _RepoState(ok_key=key, ok_head=head, ok_fp=fp, ok_ts=time.monotonic())
        return Freshness("fresh", built=built, head=head)

    return _rebuild(root, graph_path, head, built, key, fp, exists, dirty)


def _rebuild(
    root: str,
    graph_path: str,
    head: str,
    built: str | None,
    key: str,
    fp: str | None,
    exists: bool,
    dirty: bool,
) -> Freshness:
    lock = _build_lock(root)
    with lock:
        # Another call may have rebuilt while we waited for the lock.
        with _STATE_LOCK:
            st = _MEMO.get(root)
            already = st is not None and st.ok_key == key
        if already and os.path.exists(graph_path):
            return Freshness(
                "fresh", built=read_built_commit(graph_path), head=head, reason="built concurrently"
            )

        ok, reason, duration = _run_update(root)
        if ok:
            with _STATE_LOCK:
                _MEMO[root] = _RepoState(
                    ok_key=key, ok_head=head, ok_fp=fp, ok_ts=time.monotonic()
                )
            return Freshness(
                "refreshed",
                banner=_refreshed_banner(built, head, dirty, duration),
                built=read_built_commit(graph_path),
                head=head,
                durations={"update_s": duration},
            )

        with _STATE_LOCK:
            state = _MEMO.setdefault(root, _RepoState())
            state.fail_key = key
        return Freshness(
            "failed",
            banner=_failed_banner(built, head, exists, reason),
            built=built,
            head=head,
            reason=reason,
            durations={"update_s": duration},
        )


def provenance(graph_path: str) -> Provenance:
    """``built_at_commit`` vs the repo's HEAD for a given graph.json."""
    built = read_built_commit(graph_path)
    root = _repo_root(Path(graph_path).resolve().parent)
    head = _git_head(root) if root else None
    if built is None or head is None:
        return Provenance(built, head, "unknown")
    if built == head:
        return Provenance(built, head, "fresh")
    with _STATE_LOCK:
        st = _MEMO.get(root) if root else None
    if st is not None and st.ok_head == head:
        return Provenance(built, head, "fresh")
    return Provenance(built, head, "stale")


def graph_stats_lines(graph_path: str) -> list[str]:
    """Provenance lines appended to the ``graph_stats`` tool output."""
    prov = provenance(graph_path)
    lines = [
        f"Built at commit: {_short(prov.built)}",
        f"HEAD commit: {_short(prov.head)}",
        f"Freshness: {prov.state}",
    ]
    if prov.state == "stale":
        lines.append("  (graph is behind HEAD; run `graphify update .` to refresh)")
    return lines
