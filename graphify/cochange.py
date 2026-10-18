"""Co-change coupling: compare git history against the static graph.

Files that keep changing in the same commits but share no graph edge are
*hidden coupling* - an implicit contract (shared config, copy-pasted logic,
a wire format) that the AST cannot see. Files that are both heavily linked
and frequently changed are *hotspots*.

Heuristic boundaries (documented, not bugs):
- Renames are not followed; a renamed file's history starts at the rename.
- Commits touching more than ``max_files_per_commit`` files (bulk reformats,
  vendoring, mass renames) are skipped - they couple everything to everything.
- Only files that already appear as a ``source_file`` in the graph are
  considered, so the corpus boundary is the graph's own (``.graphifyignore``
  and detection rules), not a second interpretation of it.
- Co-change is a statistical signal, never a graph edge: nothing here is
  written back into graph.json.
"""
from __future__ import annotations

import subprocess
from collections import Counter
from itertools import combinations
from pathlib import Path, PurePath

import networkx as nx

_RECORD_SEP = "\x1e"


def _norm(path: str, root: Path) -> str:
    """Repo-root-relative POSIX form of a graph ``source_file``."""
    p = PurePath(path)
    if p.is_absolute():
        try:
            p = Path(path).resolve().relative_to(root.resolve())
        except ValueError:
            return ""
    return p.as_posix()


def git_commit_files(
    root: Path,
    *,
    max_commits: int = 500,
    since: str | None = None,
) -> list[list[str]]:
    """Files touched by each non-merge commit, relative to ``root``.

    ``--relative`` scopes history to ``root`` and makes paths relative to it,
    so a graph built from a subdirectory of the repo lines up with git's paths.
    """
    cmd = [
        "git", "-c", "core.quotepath=false", "-C", str(root),
        "log", "--no-merges", "--relative", "--name-only",
        "--format=%x1e", "-n", str(max_commits),  # git emits _RECORD_SEP; a raw control byte in argv breaks on Windows
    ]
    if since:
        cmd.append(f"--since={since}")
    cmd.append("--")
    proc = subprocess.run(cmd, capture_output=True, check=False)
    if proc.returncode != 0:
        err = proc.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"git log failed in {root}: {err or 'not a git repository?'}")
    out = proc.stdout.decode("utf-8", errors="replace")
    commits = []
    for record in out.split(_RECORD_SEP):
        files = sorted({line.strip() for line in record.splitlines() if line.strip()})
        if files:
            commits.append(files)
    return commits


def linked_file_pairs(G: nx.Graph, root: Path) -> tuple[set[frozenset[str]], Counter[str]]:
    """File pairs joined by at least one graph edge, and each file's linked-file count."""
    files = {n: _norm(d.get("source_file") or "", root) for n, d in G.nodes(data=True)}
    pairs: set[frozenset[str]] = set()
    for u, v in G.edges():
        fu, fv = files.get(u, ""), files.get(v, "")
        if fu and fv and fu != fv:
            pairs.add(frozenset((fu, fv)))
    degree: Counter[str] = Counter()
    for pair in pairs:
        for f in pair:
            degree[f] += 1
    return pairs, degree


def cochange_analysis(
    G: nx.Graph,
    commits: list[list[str]],
    root: Path,
    *,
    min_count: int = 3,
    max_files_per_commit: int = 30,
    top: int = 20,
) -> dict:
    """Rank hidden-coupling pairs and churn x centrality hotspots."""
    graph_files = {f for _, d in G.nodes(data=True) if (f := _norm(d.get("source_file") or "", root))}
    linked, link_degree = linked_file_pairs(G, root)

    file_commits: Counter[str] = Counter()
    pair_commits: Counter[tuple[str, str]] = Counter()
    skipped = 0
    for files in commits:
        if len(files) > max_files_per_commit:
            skipped += 1
            continue
        known = [f for f in files if f in graph_files]
        file_commits.update(known)
        pair_commits.update(combinations(known, 2))  # `known` is sorted, so pairs are canonical

    hidden = []
    for (a, b), count in pair_commits.items():
        if count < min_count or frozenset((a, b)) in linked:
            continue
        confidence = count / min(file_commits[a], file_commits[b])
        hidden.append({"files": [a, b], "commits": count, "confidence": round(confidence, 2)})
    hidden.sort(key=lambda h: (-h["commits"], -h["confidence"], h["files"]))

    hotspots = [
        {"file": f, "commits": c, "linked_files": link_degree[f], "score": c * link_degree[f]}
        for f, c in file_commits.items()
        if link_degree[f]
    ]
    hotspots.sort(key=lambda h: (-h["score"], h["file"]))

    return {
        "commits_analyzed": len(commits) - skipped,
        "commits_skipped": skipped,
        "hidden_coupling": hidden[:top],
        "hotspots": hotspots[:top],
    }


def format_cochange(result: dict) -> str:
    from graphify.security import sanitize_label

    lines = [
        f"Co-change analysis: {result['commits_analyzed']} commits "
        f"({result['commits_skipped']} bulk commits skipped)",
        "",
        "Hidden coupling (change together, no graph edge):",
    ]
    if not result["hidden_coupling"]:
        lines.append("  none found")
    for h in result["hidden_coupling"]:
        a, b = (sanitize_label(f) for f in h["files"])
        lines.append(f"  {a} <-> {b}  {h['commits']} commits, confidence {h['confidence']:.2f}")
    lines += ["", "Hotspots (commits x linked files):"]
    if not result["hotspots"]:
        lines.append("  none found")
    for h in result["hotspots"]:
        lines.append(
            f"  {sanitize_label(h['file'])}  {h['commits']} commits x {h['linked_files']} linked files"
        )
    return "\n".join(lines)
