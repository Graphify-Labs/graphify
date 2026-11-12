"""Dead-code candidates: callables no live code reaches.

Liveness is a forward walk over usage edges (calls, references, imports,
inheritance, ...) starting from every code node that is not itself a callable
candidate - files and modules (whose top-level statements run on import) -
plus entry-point-shaped callables. A callable never reached is a candidate.
Unlike "zero callers", this also catches clusters that only call each other.

Heuristic boundaries (the output is *candidates*, never proof):
- Framework dispatch the AST cannot see - decorators that register routes,
  CLI commands or fixtures, reflection, ``getattr`` strings, plugin entry
  points in packaging metadata - makes live code look dead.
- Public library API that nothing in the repo calls is reported; that is
  the point for an application and a false positive for a library.
- A live class keeps all its methods live and a live function keeps its
  nested functions live, because the AST pass often leaves those calls
  unresolved; dead methods of a live class are therefore not reported.
- Methods that override a supertype member are never reported (dynamic
  dispatch can reach them), nor are dunder methods, ``main`` and
  test-shaped names, nor anything in a test file.
- Only ``_origin == "ast"`` callables are candidates; semantic (LLM) nodes
  and documents never are, and documents never make code live.
- ``AMBIGUOUS`` edges still count as usage: a guessed caller keeps a symbol
  off the list rather than producing a guessed "dead" claim.
"""
from __future__ import annotations

import re
from collections import deque
from pathlib import PurePosixPath

import networkx as nx

from graphify.affected import DEFAULT_AFFECTED_RELATIONS, _overridden_members

USAGE_RELATIONS = frozenset(DEFAULT_AFFECTED_RELATIONS) - {"defines"} | {
    "dispatches_to", "instantiates", "references_constant", "uses_static_prop",
    "listened_by", "bound_to", "specializes",
}
_ENTRY_NAME_RE = re.compile(r"^(main|__\w+__|test\w*|Test\w*)$")
_TEST_FILE_RE = re.compile(r"(^|/)(tests?|__tests__|spec)/|(^|/)test_[^/]*$|_test\.\w+$|\.(test|spec)\.\w+$")


def _bare(label: str) -> str:
    name = label[:-2] if label.endswith("()") else label
    return name.rsplit(".", 1)[-1]


def _is_test_file(path: str) -> bool:
    return bool(_TEST_FILE_RE.search(PurePosixPath(path.replace("\\", "/")).as_posix()))


def _carries_liveness(G: nx.DiGraph, u: str, relation: object) -> bool:
    # Calls into nested functions and on instance methods are often unresolved
    # by the AST pass, so a live function keeps its nested functions live and a
    # live class keeps its methods live; a file's `contains` never does.
    if relation in USAGE_RELATIONS or relation == "method":
        return True
    return relation == "contains" and bool(G.nodes[u].get("_callable"))


def dead_code_candidates(G: nx.DiGraph) -> list[dict]:
    """Unreached callables, sorted by file then line."""
    override_cache: dict[str, list[str]] = {}
    candidates: set[str] = set()
    live: set[str] = set()
    for n, d in G.nodes(data=True):
        if d.get("file_type") != "code":
            continue  # documents, rationale and concepts neither root nor get reported
        src = str(d.get("source_file") or "")
        is_candidate = (
            bool(d.get("_callable")) and d.get("_origin") == "ast" and bool(src)
            and not _is_test_file(src)
            and not _ENTRY_NAME_RE.match(_bare(str(d.get("label") or "")))
            and not _overridden_members(G, n, override_cache)
        )
        (candidates if is_candidate else live).add(n)

    queue = deque(live)
    while queue:
        u = queue.popleft()
        for _u, v, data in G.out_edges(u, data=True):
            if v not in live and _carries_liveness(G, u, data.get("relation")):
                live.add(v)
                queue.append(v)

    out = []
    for n in candidates - live:
        d = G.nodes[n]
        loc = str(d.get("source_location") or "")
        m = re.match(r"L(\d+)", loc)
        out.append({
            "id": n,
            "label": str(d.get("label") or n),
            "file": str(d.get("source_file")).replace("\\", "/"),
            "line": int(m.group(1)) if m else None,
        })
    out.sort(key=lambda c: (c["file"], c["line"] or 0, c["label"]))
    return out


def format_dead_code(candidates: list[dict]) -> str:
    from graphify.security import sanitize_label

    if not candidates:
        return "No dead-code candidates."
    lines = [f"{len(candidates)} dead-code candidate{'s' if len(candidates) != 1 else ''} (unreached callables; verify before deleting):"]
    current = None
    for c in candidates:
        if c["file"] != current:
            current = c["file"]
            lines.append(f"  {sanitize_label(current)}")
        where = f"L{c['line']}" if c["line"] else "?"
        lines.append(f"    {where:>6}  {sanitize_label(c['label'])}")
    return "\n".join(lines)
