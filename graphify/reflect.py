"""Deterministic "work memory" reflection over graphify-out/memory/.

`graphify reflect` reads the Q&A memory docs that `graphify save-result` files back
into the graph, aggregates their outcome signals (useful / dead_end / corrected), and
writes a single lessons artifact an agent can load at the start of the next session:

  - **Preferred sources** — nodes that recurred in answers marked ``useful``.
  - **Known dead ends** — questions/sources marked ``dead_end``; don't re-derive them.
  - **Corrections** — answers the user corrected, and what the right answer was.

It is deterministic: no LLM, stable sort orders, byte-stable output for a given input.
When a graph (`graph.json` + `.graphify_analysis.json`) is available the lessons are also
grouped by community label; without it they degrade to a single flat section.

The artifact lands at ``graphify-out/reflections/LESSONS.md`` rather than inside the wiki
because ``graphify export wiki`` deletes every ``wiki/*.md`` on each run — a lessons file
written there would be clobbered on the next export.
"""
from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

from graphify.ingest import OUTCOMES

# Human-facing labels for the outcome buckets, in display order.
_OUTCOME_ORDER = ("useful", "dead_end", "corrected")
_UNCATEGORIZED = "Uncategorized"


# --- frontmatter parsing -------------------------------------------------------
#
# save_query_result writes a tiny, hand-built YAML subset (no PyYAML dependency),
# so we parse the same subset by hand rather than adding a dependency: scalar
# `key: "value"` lines and a `source_nodes: ["a", "b"]` flow list. Anything we
# don't recognise is ignored, so foreign .md files in memory/ are skipped cleanly.

_SCALAR_RE = re.compile(r'^([A-Za-z_][\w-]*):\s*"(.*)"\s*$')
_LIST_RE = re.compile(r"^([A-Za-z_][\w-]*):\s*\[(.*)\]\s*$")
_DQ_ITEM_RE = re.compile(r'"((?:[^"\\]|\\.)*)"')


def _yaml_unescape(s: str) -> str:
    """Reverse the double-quoted escaping that ingest._yaml_str applies."""
    out: list[str] = []
    i = 0
    simple = {"n": "\n", "r": "\r", "t": "\t", "0": "\0", '"': '"', "\\": "\\",
              "L": "\u2028", "P": "\u2029"}  # YAML line/paragraph separators
    while i < len(s):
        ch = s[i]
        if ch == "\\" and i + 1 < len(s):
            nxt = s[i + 1]
            if nxt in simple:
                out.append(simple[nxt])
                i += 2
                continue
            if nxt == "x" and i + 3 < len(s):
                try:
                    out.append(chr(int(s[i + 2:i + 4], 16)))
                    i += 4
                    continue
                except ValueError:
                    pass
            if nxt == "u" and i + 5 < len(s):
                try:
                    out.append(chr(int(s[i + 2:i + 6], 16)))
                    i += 6
                    continue
                except ValueError:
                    pass
        out.append(ch)
        i += 1
    return "".join(out)


def parse_memory_doc(text: str) -> dict[str, Any] | None:
    """Parse the frontmatter of a memory doc into a dict, or None if it has none.

    Returns the recognised fields (``type``, ``date``, ``question``, ``outcome``,
    ``correction``, ``source_nodes``). ``source_nodes`` is always a list.
    """
    if not text.startswith("---"):
        return None
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return None
    fields: dict[str, Any] = {"source_nodes": []}
    for line in lines[1:]:
        if line.strip() == "---":
            break
        m = _LIST_RE.match(line)
        if m and m.group(1) == "source_nodes":
            fields["source_nodes"] = [
                _yaml_unescape(item) for item in _DQ_ITEM_RE.findall(m.group(2))
            ]
            continue
        m = _SCALAR_RE.match(line)
        if m:
            key, val = m.group(1), _yaml_unescape(m.group(2))
            if key in ("type", "date", "question", "outcome", "correction", "contributor"):
                fields[key] = val
    return fields


def load_memory_docs(memory_dir: Path) -> list[dict[str, Any]]:
    """Parse every memory doc under ``memory_dir``, sorted by date then filename.

    Each record is the parsed frontmatter plus ``_path`` (the source file). Docs
    without recognisable frontmatter (foreign .md files) are skipped.
    """
    memory_dir = Path(memory_dir)
    if not memory_dir.exists():
        return []
    docs: list[dict[str, Any]] = []
    for path in sorted(memory_dir.glob("*.md")):
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        parsed = parse_memory_doc(text)
        if parsed is None:
            continue
        parsed["_path"] = path.name
        docs.append(parsed)
    # Stable order: by (date, filename) so output is deterministic across runs.
    docs.sort(key=lambda d: (d.get("date", ""), d["_path"]))
    return docs


# --- graph / community lookup (optional) ---------------------------------------


def _load_node_community(graph_path: Path, analysis_path: Path,
                         labels_path: Path) -> dict[str, str] | None:
    """Build a node-id -> community-label map, or None if the graph isn't available.

    Mirrors how `graphify export wiki` reads graph.json + .graphify_analysis.json +
    .graphify_labels.json. Best-effort: any missing/unparseable artifact disables
    community grouping (reflect still produces a flat lessons doc).
    """
    if not graph_path.exists() or not analysis_path.exists():
        return None
    try:
        analysis = json.loads(analysis_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    communities = analysis.get("communities", {})
    if not communities:
        return None
    labels: dict[str, str] = {}
    if labels_path.exists():
        try:
            labels = json.loads(labels_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            labels = {}
    node_community: dict[str, str] = {}
    for cid, members in communities.items():
        label = labels.get(str(cid)) or labels.get(cid) or f"Community {cid}"
        for nid in members:
            node_community[nid] = label
    return node_community


def _doc_community(doc: dict[str, Any],
                   node_community: dict[str, str] | None) -> str:
    """The community a doc belongs to: the plurality community of its source nodes.

    Ties break to the lexicographically-smallest label, so the result is
    deterministic regardless of source-node order. Docs with no resolvable
    community (no source nodes, or no graph) fall into the Uncategorized bucket.
    """
    if not node_community:
        return _UNCATEGORIZED
    labels = [node_community[n] for n in doc.get("source_nodes", []) if n in node_community]
    if not labels:
        return _UNCATEGORIZED
    counts = Counter(labels)
    # Highest count wins; on a tie, the smaller label (most-negative count first,
    # then ascending label) — a plain min() over (-count, label).
    return min(counts.items(), key=lambda kv: (-kv[1], kv[0]))[0]


# --- aggregation ---------------------------------------------------------------


def _empty_bucket() -> dict[str, Any]:
    return {
        "counts": {k: 0 for k in (*OUTCOMES, "unmarked")},
        "preferred_sources": Counter(),
        "dead_ends": [],
        "corrections": [],
    }


def aggregate_lessons(docs: list[dict[str, Any]],
                      node_community: dict[str, str] | None = None) -> dict[str, Any]:
    """Aggregate parsed memory docs into a deterministic lessons structure.

    Returns ``{"total", "counts", "preferred_sources", "dead_ends", "corrections",
    "by_community"}``. ``by_community`` is empty when no graph is supplied.
    """
    overall = _empty_bucket()
    by_community: dict[str, dict[str, Any]] = {}

    for doc in docs:
        outcome = doc.get("outcome")
        nodes = doc.get("source_nodes", [])
        community = _doc_community(doc, node_community)
        bucket = by_community.setdefault(community, _empty_bucket())

        for target in (overall, bucket):
            if outcome in OUTCOMES:
                target["counts"][outcome] += 1
            else:
                target["counts"]["unmarked"] += 1

            if outcome == "useful":
                for n in nodes:
                    target["preferred_sources"][n] += 1
            elif outcome == "dead_end":
                target["dead_ends"].append(
                    {"question": doc.get("question", ""), "nodes": nodes,
                     "date": doc.get("date", "")}
                )
            elif outcome == "corrected":
                target["corrections"].append(
                    {"question": doc.get("question", ""),
                     "correction": doc.get("correction", ""),
                     "date": doc.get("date", "")}
                )

    # Only surface per-community grouping when a graph was actually supplied;
    # without one every doc falls into Uncategorized and the section would just
    # duplicate the flat "Lessons" block.
    community_out: dict[str, dict[str, Any]] = {}
    if node_community:
        community_out = {
            label: {
                "counts": b["counts"],
                "preferred_sources": _rank_sources(b["preferred_sources"]),
                "dead_ends": b["dead_ends"],
                "corrections": b["corrections"],
            }
            for label, b in by_community.items()
        }

    return {
        "total": len(docs),
        "counts": overall["counts"],
        "preferred_sources": _rank_sources(overall["preferred_sources"]),
        "dead_ends": overall["dead_ends"],
        "corrections": overall["corrections"],
        "by_community": community_out,
    }


def _rank_sources(counter: Counter) -> list[tuple[str, int]]:
    """Sources ranked by frequency desc, then name asc (deterministic)."""
    return sorted(counter.items(), key=lambda kv: (-kv[1], kv[0]))


# --- rendering -----------------------------------------------------------------


def _render_bucket(out: list[str], data: dict[str, Any]) -> None:
    sources = data["preferred_sources"]
    dead_ends = data["dead_ends"]
    corrections = data["corrections"]

    if sources:
        out += ["**Preferred sources** — recurred in useful answers; start here.", ""]
        for node, n in sources:
            out.append(f"- `{node}` ({n}×)")
        out.append("")
    if dead_ends:
        out += ["**Known dead ends** — led nowhere; don't re-derive.", ""]
        for d in dead_ends:
            nodes = ", ".join(f"`{n}`" for n in d["nodes"])
            tail = f" — {nodes}" if nodes else ""
            out.append(f"- \"{d['question']}\"{tail}")
        out.append("")
    if corrections:
        out += ["**Corrections** — do these differently.", ""]
        for c in corrections:
            out.append(f"- \"{c['question']}\" → {c['correction']}")
        out.append("")
    if not (sources or dead_ends or corrections):
        out += ["_No marked outcomes yet._", ""]


def render_lessons_md(agg: dict[str, Any]) -> str:
    """Render the aggregate into the deterministic LESSONS.md markdown body."""
    c = agg["counts"]
    out: list[str] = [
        "# Lessons",
        "",
        f"_Auto-generated by `graphify reflect` from {agg['total']} session "
        f"{'memory' if agg['total'] == 1 else 'memories'} in graphify-out/memory/. "
        "Deterministic; no LLM. Load this at the start of a session to reuse what "
        "worked and skip what didn't._",
        "",
        "## Summary",
        "",
        f"- {c['useful']} useful · {c['dead_end']} dead ends · "
        f"{c['corrected']} corrected · {c['unmarked']} unmarked",
        "",
        "## Lessons",
        "",
    ]
    _render_bucket(out, agg)

    if agg["by_community"]:
        out += ["## By topic", ""]
        # Uncategorized sorts last; everything else alphabetically.
        def _topic_key(label: str) -> tuple[int, str]:
            return (1 if label == _UNCATEGORIZED else 0, label)
        for label in sorted(agg["by_community"], key=_topic_key):
            out += [f"### {label}", ""]
            _render_bucket(out, agg["by_community"][label])

    # Single trailing newline, no trailing whitespace lines.
    return "\n".join(out).rstrip("\n") + "\n"


# --- orchestrator --------------------------------------------------------------


def reflect(memory_dir: Path, out_path: Path,
            graph_path: Path | None = None,
            analysis_path: Path | None = None,
            labels_path: Path | None = None) -> tuple[Path, dict[str, Any]]:
    """Scan ``memory_dir``, write the lessons doc to ``out_path``, return (path, agg).

    If ``graph_path`` is given (and its analysis sidecar exists) lessons are also
    grouped by community; otherwise the doc is a single flat section.
    """
    docs = load_memory_docs(memory_dir)

    node_community = None
    if graph_path is not None:
        graph_path = Path(graph_path)
        analysis_path = Path(analysis_path) if analysis_path else (
            graph_path.parent / ".graphify_analysis.json")
        labels_path = Path(labels_path) if labels_path else (
            graph_path.parent / ".graphify_labels.json")
        node_community = _load_node_community(graph_path, analysis_path, labels_path)

    agg = aggregate_lessons(docs, node_community)
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(render_lessons_md(agg), encoding="utf-8")
    return out_path, agg
