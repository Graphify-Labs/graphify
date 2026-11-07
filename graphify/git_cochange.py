"""Git co-change: files that keep changing in the same commits.

`graphify affected` follows code links. Files that are edited together in
history (a module and its docs, a setting and its changelog entry, a function
and the test that exercises it through a string) are often not linked in code
at all. This module mines that signal from ``git log`` and stores it in
``graphify-out/cochange.json`` so ``affected`` can list it in its own,
clearly labelled section. It never adds edges to the graph.

Choices, all deterministic for a given repository and commit:

- window: the last ``years`` years counted back from the mined commit's
  committer date (never the wall clock), and at most ``max_commits`` commits;
- non-merge commits only; renames are followed to the file's name at the
  mined commit;
- commits touching more than ``max_files_per_commit`` files (reformats,
  vendoring, mass renames) are skipped: they couple everything to everything;
- only files tracked at the mined commit are kept; lockfiles, generated and
  vendored files and graphify's own output are dropped; and `refresh_cochange`
  (what `graphify update` calls) also drops every file `graphify update` itself
  would not scan: .graphifyignore/.gitignore rules, persisted ``--exclude``
  patterns, noise directories and skipped or sensitive files (see
  `corpus_filter`). Tracked docs, configs and tests stay: they are the point;
- each file keeps at most ``max_partners`` partners with support of at least
  ``min_support`` commits, ranked by support then path. Confidence of a pair
  for a seed is ``support / commits(seed)`` and is computed when reading;
- if the result is larger than ``max_bytes``, the support floor is raised
  until it fits, and the floor actually used is recorded.

``git`` always runs from an argument list (no shell), with
``core.quotepath=false`` so non-ASCII paths stay readable, ``--relative`` so a
graph built from a subdirectory lines up with git's paths, and the ``%x1e``
format escape as a record separator (a raw control byte in argv breaks on
Windows).
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
from collections import Counter
from itertools import combinations
from pathlib import Path, PurePosixPath
from typing import Any, Callable

FORMAT_VERSION = 1
FILE_NAME = "cochange.json"

DEFAULT_YEARS = 3
DEFAULT_MAX_COMMITS = 10_000
DEFAULT_MAX_FILES_PER_COMMIT = 30
DEFAULT_MIN_SUPPORT = 2
DEFAULT_MAX_PARTNERS = 50
DEFAULT_MAX_BYTES = 5_000_000

# What `affected` shows by default.
DEFAULT_MIN_CONFIDENCE = 0.2
DEFAULT_TOP = 10

_YEAR_SECONDS = 365 * 86400
_RECORD = "\x1e"
_FIELD = "\x1f"

_LOCKFILES = frozenset({
    "package-lock.json", "npm-shrinkwrap.json", "yarn.lock", "pnpm-lock.yaml",
    "bun.lock", "bun.lockb", "poetry.lock", "uv.lock", "pipfile.lock", "pdm.lock",
    "go.sum", "cargo.lock", "composer.lock", "gemfile.lock",
})
_GENERATED_SUFFIXES = (".min.js", ".min.css", ".map", ".mo", ".pyc", ".pb.go", "_pb2.py", ".snap")
_EXCLUDED_DIRS = frozenset({"node_modules", "vendor", "third_party", "dist", "__snapshots__", ".yarn"})


def _excluded(path: str, out_name: str) -> bool:
    p = PurePosixPath(path)
    name = p.name.lower()
    if name in _LOCKFILES or name.endswith(_GENERATED_SUFFIXES):
        return True
    dirs = p.parts[:-1]
    return any(part in _EXCLUDED_DIRS or part == out_name for part in dirs)


def _git(root: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-c", "core.quotepath=false", "-C", str(root), *args],
        capture_output=True, stdin=subprocess.DEVNULL, check=False,
    )


def _unavailable(reason: str) -> dict[str, Any]:
    return {"version": FORMAT_VERSION, "status": "unavailable", "reason": reason}



def _is_shallow(root: Path) -> bool:
    return _git(root, "rev-parse", "--is-shallow-repository").stdout.decode().strip() == "true"

def mine_cochange(
    repo_root: str | os.PathLike[str],
    *,
    rev: str = "HEAD",
    years: int = DEFAULT_YEARS,
    max_commits: int = DEFAULT_MAX_COMMITS,
    max_files_per_commit: int = DEFAULT_MAX_FILES_PER_COMMIT,
    min_support: int = DEFAULT_MIN_SUPPORT,
    max_partners: int = DEFAULT_MAX_PARTNERS,
    max_bytes: int = DEFAULT_MAX_BYTES,
    out_name: str = "graphify-out",
    keep: Callable[[str], bool] | None = None,
) -> dict[str, Any]:
    """Mine co-change for the files under ``repo_root`` as of ``rev``.

    ``keep`` is an optional corpus predicate on root-relative POSIX paths
    (see `corpus_filter`); files it rejects never enter the counts.

    Returns a JSON-ready dict. ``status`` is ``"ok"``, or ``"unavailable"``
    with a ``reason`` when there is no usable git history (not a repository,
    git missing, no commits). Paths are relative to ``repo_root`` in POSIX form,
    the same form the graph uses for ``source_file``.
    """
    root = Path(repo_root)
    try:
        head = _git(root, "rev-parse", "--verify", "--quiet", f"{rev}^{{commit}}")
    except OSError:
        return _unavailable("git is not installed")
    if head.returncode != 0:
        inside = _git(root, "rev-parse", "--is-inside-work-tree")
        if inside.returncode != 0:
            return _unavailable("not a git repository")
        return _unavailable(f"no commit at {rev}")
    sha = head.stdout.decode().strip()
    anchor = int(_git(root, "log", "-1", "--format=%ct", sha).stdout.decode().strip() or 0)
    since = anchor - years * _YEAR_SECONDS
    shallow = _is_shallow(root)

    # Files at `rev`, relative to root (ls-tree is cwd-relative like --relative).
    tracked_out = _git(root, "ls-tree", "-r", "-z", "--name-only", sha)
    tracked = {p for p in tracked_out.stdout.decode("utf-8", "replace").split("\0") if p}

    log = _git(
        root, "log", "--no-merges", "--relative", "-M", "--name-status",
        # %x1e / %x1f: git emits the separators; never put raw control bytes in argv
        "--format=%x1e%H%x1f%ct", f"--max-count={max_commits}",
        f"--since=@{since}", sha, "--",
    )
    if log.returncode != 0:
        return _unavailable("git log failed: " + log.stderr.decode("utf-8", "replace").strip()[:200])

    kept_cache: dict[str, bool] = {}

    def in_corpus(path: str) -> bool:
        if path not in kept_cache:
            kept_cache[path] = (
                path in tracked and not _excluded(path, out_name)
                and (keep is None or keep(path))
            )
        return kept_cache[path]

    alias: dict[str, str] = {}  # historical path -> path at `rev`
    file_commits: Counter[str] = Counter()
    pair_commits: Counter[tuple[str, str]] = Counter()
    seen = used = bulk = 0
    for record in log.stdout.decode("utf-8", "replace").split(_RECORD):
        lines = [ln for ln in record.split("\n") if ln.strip()]
        if not lines:
            continue
        _sha, _, ts = lines[0].partition(_FIELD)
        if not ts or int(ts) < since:
            continue  # --since is a walk hint; this makes the window exact
        seen += 1
        entries = [ln.split("\t") for ln in lines[1:]]
        files: set[str] = set()
        for cols in entries:
            status = cols[0]
            path = cols[-1]
            if status == "R100":
                continue  # a pure rename changes no content
            files.add(alias[path] if path in alias else path)
        for cols in entries:  # newest first: older names map to today's name
            if cols[0].startswith("R") and len(cols) == 3:
                new = cols[2]
                alias[cols[1]] = alias[new] if new in alias else new
        kept = sorted(f for f in files if in_corpus(f))
        if not kept:
            continue
        if len(kept) > max_files_per_commit:
            bulk += 1
            continue
        used += 1
        file_commits.update(kept)
        pair_commits.update(combinations(kept, 2))

    support = min_support
    while True:
        partners: dict[str, list[list[Any]]] = {}
        for (a, b), s in pair_commits.items():
            if s < support:
                continue
            partners.setdefault(a, []).append([b, s])
            partners.setdefault(b, []).append([a, s])
        for f, lst in partners.items():
            lst.sort(key=lambda p: (-p[1], p[0]))
            del lst[max_partners:]
        listed = set(partners)
        for lst in partners.values():
            listed.update(p[0] for p in lst)
        data = {
            "version": FORMAT_VERSION,
            "status": "ok",
            "rev": sha,
            "anchor_time": anchor,
            "since_time": since,
            "shallow": shallow,
            "commits_seen": seen,
            "commits_used": used,
            "bulk_skipped": bulk,
            "params": {
                "years": years, "max_commits": max_commits,
                "max_files_per_commit": max_files_per_commit,
                "min_support": support, "max_partners": max_partners,
            },
            "files": {f: file_commits[f] for f in sorted(listed)},
            "partners": {f: partners[f] for f in sorted(partners)},
        }
        if len(dumps(data)) <= max_bytes or not partners:
            return data
        support += 1


def dumps(data: dict[str, Any]) -> str:
    """Canonical serialisation: sorted keys, no whitespace variation."""
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n"


def corpus_filter(
    root: Path,
    *,
    extra_excludes: list[str] | None = None,
    gitignore: bool = True,
) -> Callable[[str], bool]:
    """Keep-predicate with the corpus rules `graphify update` scans with.

    A root-relative path is kept unless ``detect.ignored_predicate`` says the
    scan would exclude it (the .graphifyignore/.gitignore chain including nested
    files, persisted ``--exclude`` patterns, noise directories such as
    node_modules or virtualenvs, and skipped file names) or
    ``detect._is_sensitive`` flags it as a likely secret. Tracked files are not
    dropped by .gitignore alone, matching the scan.
    """
    from graphify.detect import _is_sensitive, ignored_predicate

    base = Path(root).resolve()
    ignored = ignored_predicate(base, extra_excludes=extra_excludes, gitignore=gitignore)

    def keep(rel: str) -> bool:
        return not ignored(base / rel) and not _is_sensitive(Path(rel))

    return keep


def _corpus_key(root: Path, extra_excludes: list[str] | None, gitignore: bool) -> dict[str, Any]:
    """What the corpus filter depended on, so a change re-mines even at the same HEAD."""
    digest = hashlib.sha256()
    for name in (".graphifyignore", ".gitignore"):
        try:
            digest.update(name.encode() + b"\0" + (root / name).read_bytes() + b"\0")
        except OSError:
            digest.update(name.encode() + b"\0-\0")
    return {"excludes": sorted(extra_excludes or []), "gitignore": gitignore,
            "ignore_files_sha256": digest.hexdigest()}


def refresh_cochange(
    root: Path,
    out_dir: Path,
    *,
    extra_excludes: list[str] | None = None,
    gitignore: bool = True,
) -> tuple[dict[str, Any] | None, str | None]:
    """Write ``out_dir/cochange.json`` for ``root`` unless it is already current.

    ``extra_excludes``/``gitignore`` are the persisted build settings the
    rebuild itself used, so co-change covers the same corpus as the graph scan.
    Returns ``(data, note)``. ``data`` is None when there is no usable history
    (nothing is written then). ``note`` is one line worth printing, or None.
    ``GRAPHIFY_NO_COCHANGE=1`` turns the step off.
    """
    if os.environ.get("GRAPHIFY_NO_COCHANGE", "").lower() in ("1", "true", "yes"):
        return None, None
    target = out_dir / FILE_NAME
    try:
        head = _git(root, "rev-parse", "--verify", "--quiet", "HEAD^{commit}")
    except OSError:
        return None, "co-change: skipped (git is not installed)"
    corpus = _corpus_key(root, extra_excludes, gitignore)
    old = load_cochange(target) if head.returncode == 0 else None
    if (old is not None and old.get("rev") == head.stdout.decode().strip()
            and old.get("corpus") == corpus and not (old.get("shallow") and not _is_shallow(root))):
        return old, None  # same HEAD, corpus rules and depth of history: already current
    data = mine_cochange(
        root, out_name=out_dir.name,
        keep=corpus_filter(root, extra_excludes=extra_excludes, gitignore=gitignore),
    )
    if data.get("status") != "ok":
        return None, f"co-change: skipped ({data.get('reason')})"
    data["corpus"] = corpus
    out_dir.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(target.name + ".tmp")
    tmp.write_text(dumps(data), encoding="utf-8")
    os.replace(tmp, target)
    if data["shallow"]:
        return data, (f"co-change: shallow clone, only {data['commits_used']} commits of history; "
                      "run `git fetch --unshallow` for better results")
    return data, None


def load_cochange(path: Path) -> dict[str, Any] | None:
    """Read a cochange.json; None when absent or unreadable."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict) or data.get("version") != FORMAT_VERSION:
        return None
    return data


def cochange_partners(
    data: dict[str, Any],
    seed_file: str,
    *,
    min_confidence: float = DEFAULT_MIN_CONFIDENCE,
    top: int = DEFAULT_TOP,
) -> list[dict[str, Any]]:
    """Files that changed together with ``seed_file``, best first.

    Each item: ``file``, ``confidence`` (support / commits of the seed),
    ``support`` (commits with both) and ``seed_commits``.
    """
    if data.get("status") != "ok":
        return []
    seed_commits = int(data.get("files", {}).get(seed_file, 0))
    if not seed_commits:
        return []
    out = []
    for other, support in data.get("partners", {}).get(seed_file, []):
        conf = support / seed_commits
        if conf + 1e-12 < min_confidence:
            continue
        out.append({"file": other, "confidence": round(conf, 3), "support": int(support),
                    "seed_commits": seed_commits})
    out.sort(key=lambda d: (-d["confidence"], -d["support"], d["file"]))
    return out[:top]
