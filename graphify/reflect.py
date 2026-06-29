"""Deterministic "work memory" reflection over graphify-out/memory/.

`graphify reflect` reads the Q&A memory docs that `graphify save-result` files back
into the graph, aggregates their outcome signals (useful / dead_end / corrected), and
writes a single lessons artifact an agent can load at the start of the next session:

  - **Preferred sources** — nodes corroborated by multiple ``useful`` answers.
  - **Tentative** — nodes seen useful only once (not yet corroborated).
  - **Contested** — nodes with both positive and negative signals; recency decides.
  - **Known dead ends** — questions/sources marked ``dead_end``; don't re-derive them.
  - **Corrections** — answers the user corrected, and what the right answer was.

Source nodes are scored, not counted: each citation contributes a signed,
time-decayed value (``useful`` positive, ``dead_end``/``corrected`` negative, with a
half-life so a fresh dead end outweighs a months-old useful). A node is only promoted
to "preferred" once corroborated by enough distinct results; one save can't mint a
trusted lesson. When a graph is in hand, source nodes that no longer exist are dropped.

It is deterministic: no LLM, stable sort orders, byte-stable output for a given input
and a given ``now``. When a graph (`graph.json` + `.graphify_analysis.json`) is available
the lessons are also grouped by community label; without it they degrade to a single
flat section.

The artifact lands at ``graphify-out/reflections/LESSONS.md`` rather than inside the wiki
because ``graphify export wiki`` deletes every ``wiki/*.md`` on each run — a lessons file
written there would be clobbered on the next export.
"""
from __future__ import annotations

import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from graphify.ingest import OUTCOMES

_UNCATEGORIZED = "Uncategorized"

# Scoring defaults (both exposed as CLI flags).
_DEFAULT_HALF_LIFE_DAYS = 30.0   # a signal's weight halves every 30 days
_DEFAULT_MIN_CORROBORATION = 2   # distinct useful results needed to "prefer" a node

# Rounding for the signed score keeps sort order and the contested verdict stable
# across platforms (C pow can differ in the last ULP).
_SCORE_NDIGITS = 9


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
    without recognisable frontmatter (foreign .md files, the LESSONS.md artifact)
    are skipped.
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
    """Build a lookup from node id AND node label -> community label, or None if the
    graph isn't available.

    Mirrors how `graphify export wiki` reads graph.json + .graphify_analysis.json +
    .graphify_labels.json. Community membership in the analysis sidecar is keyed by
    node id, but `save-result` cites nodes by label, so both are mapped — otherwise a
    cited ``build_from_json()`` never finds its community and every lesson collapses
    into Uncategorized. Best-effort: any missing/unparseable artifact disables grouping.
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
    # id -> label from the graph, so a label-form citation resolves to a community too.
    id_to_label: dict[str, str] = {}
    try:
        gdata = json.loads(graph_path.read_text(encoding="utf-8"))
        for n in gdata.get("nodes", []):
            if isinstance(n, dict) and n.get("id") is not None and n.get("label") is not None:
                id_to_label[str(n["id"])] = str(n["label"])
    except (OSError, ValueError):
        id_to_label = {}
    # Sorted cid iteration + setdefault makes any label collision resolve
    # deterministically (smallest community id wins).
    node_community: dict[str, str] = {}
    for cid in sorted(communities, key=str):
        label = labels.get(str(cid)) or labels.get(cid) or f"Community {cid}"
        for nid in communities[cid]:
            nid = str(nid)
            node_community.setdefault(nid, label)
            nlabel = id_to_label.get(nid)
            if nlabel is not None:
                node_community.setdefault(nlabel, label)
    return node_community


def _load_known_nodes(graph_path: Path) -> set[str] | None:
    """The set of node ids AND labels in the current graph, or None if unavailable.

    Used to drop source nodes from lessons once the code they pointed at is gone
    (deleted/renamed) — a stale lesson shouldn't keep getting recommended. Both ids
    and labels are collected because `save-result` records source nodes by their
    human-readable label (what an agent cites, e.g. ``build_from_json()``), while
    graph nodes are keyed by id (e.g. ``module_build_from_json``). Matching on either
    keeps a still-present node and only drops one that survives under neither name —
    indexing ids alone silently dropped every label-form citation (the common case).
    """
    try:
        data = json.loads(Path(graph_path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    nodes = data.get("nodes")
    if not isinstance(nodes, list):
        return None
    known: set[str] = set()
    for n in nodes:
        if not isinstance(n, dict):
            continue
        if n.get("id") is not None:
            known.add(str(n["id"]))
        if n.get("label") is not None:
            known.add(str(n["label"]))
    return known or None


def _doc_community(nodes: list[str],
                   node_community: dict[str, str] | None) -> str:
    """The community a doc belongs to: the plurality community of its source nodes.

    Ties break to the lexicographically-smallest label, so the result is
    deterministic regardless of source-node order. Docs with no resolvable
    community (no source nodes, or no graph) fall into the Uncategorized bucket.
    """
    if not node_community:
        return _UNCATEGORIZED
    labels = [node_community[n] for n in nodes if n in node_community]
    if not labels:
        return _UNCATEGORIZED
    counts = Counter(labels)
    # Highest count wins; on a tie, the smaller label (most-negative count first,
    # then ascending label) — a plain min() over (-count, label).
    return min(counts.items(), key=lambda kv: (-kv[1], kv[0]))[0]


# --- scoring helpers -----------------------------------------------------------


def _parse_dt(date_str: str) -> datetime | None:
    """Parse an ISO date/datetime to an aware UTC datetime, or None if unparseable."""
    if not date_str:
        return None
    try:
        dt = datetime.fromisoformat(date_str)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _decay(date_str: str, now: datetime, half_life_days: float) -> float:
    """Time-decay weight in (0, 1]: halves every ``half_life_days``.

    Undated/unparseable signals keep full weight (1.0); future-dated ones are
    clamped to age 0 (also 1.0).
    """
    dt = _parse_dt(date_str)
    if dt is None or half_life_days <= 0:
        return 1.0
    age_days = max(0.0, (now - dt).total_seconds() / 86400.0)
    return 0.5 ** (age_days / half_life_days)


# --- aggregation ---------------------------------------------------------------


def _empty_bucket() -> dict[str, Any]:
    return {
        "counts": {k: 0 for k in (*OUTCOMES, "unmarked")},
        # node -> running signed, time-decayed score
        "node_score": {},
        # node -> distinct positive / negative result counts (for corroboration)
        "node_pos": Counter(),
        "node_neg": Counter(),
        # node -> most recent event date seen (for the contested verdict line)
        "node_last": {},
        "dead_ends": [],
        "corrections": [],
    }


def _record_node(bucket: dict[str, Any], node: str, sign: int,
                 weight: float, date: str) -> None:
    bucket["node_score"][node] = bucket["node_score"].get(node, 0.0) + sign * weight
    if sign > 0:
        bucket["node_pos"][node] += 1
    elif sign < 0:
        bucket["node_neg"][node] += 1
    if date > bucket["node_last"].get(node, ""):
        bucket["node_last"][node] = date


def _finalize_sources(bucket: dict[str, Any],
                      min_corroboration: int) -> dict[str, list]:
    """Split a bucket's scored nodes into preferred / tentative / contested lists."""
    preferred, tentative, contested = [], [], []
    for node in bucket["node_score"]:
        pos = bucket["node_pos"][node]
        neg = bucket["node_neg"][node]
        score = round(bucket["node_score"][node], _SCORE_NDIGITS)
        if pos and neg:
            verdict = "useful" if score > 0 else "dead end" if score < 0 else "even"
            contested.append({"node": node, "pos": pos, "neg": neg,
                              "score": score, "verdict": verdict,
                              "last": bucket["node_last"].get(node, "")})
        elif pos:  # positive-only
            entry = {"node": node, "n": pos, "score": score}
            (preferred if pos >= min_corroboration else tentative).append(entry)
        # negative-only nodes are surfaced via the dead-ends questions, not here.
    preferred.sort(key=lambda e: (-e["score"], e["node"]))
    tentative.sort(key=lambda e: (-e["score"], e["node"]))
    contested.sort(key=lambda e: (-e["score"], e["node"]))
    return {"preferred": preferred, "tentative": tentative, "contested": contested}


def _dedupe_by_question(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Collapse repeated questions to one entry. Docs are processed oldest-first, so
    the last write per question wins (recency — e.g. the most recent correction text).
    Output is deterministically ordered by (date, question). Without this, saving the
    same Q&A twice duplicated lines in the dead-ends / corrections lists, even though
    node scoring already dedups by node.
    """
    latest: dict[str, dict[str, Any]] = {}
    for it in items:
        latest[it.get("question", "")] = it
    return sorted(latest.values(),
                  key=lambda it: (it.get("date", ""), it.get("question", "")))


def aggregate_lessons(docs: list[dict[str, Any]],
                      node_community: dict[str, str] | None = None,
                      *,
                      now: datetime | None = None,
                      half_life_days: float = _DEFAULT_HALF_LIFE_DAYS,
                      min_corroboration: int = _DEFAULT_MIN_CORROBORATION,
                      known_nodes: set[str] | None = None) -> dict[str, Any]:
    """Aggregate parsed memory docs into a deterministic lessons structure.

    ``now`` anchors the time-decay (pass it explicitly for byte-stable output).
    ``known_nodes`` (when given) gates out source nodes no longer in the graph.
    Returns ``{"total", "counts", "min_corroboration", "preferred", "tentative",
    "contested", "dead_ends", "corrections", "by_community"}``; ``by_community`` is
    empty unless a graph is supplied.
    """
    if now is None:
        now = datetime.now(timezone.utc)
    elif now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)

    overall = _empty_bucket()
    by_community: dict[str, dict[str, Any]] = {}

    for doc in docs:
        outcome = doc.get("outcome")
        date = doc.get("date", "")
        # One event per node per doc; drop nodes the graph no longer knows about.
        raw = doc.get("source_nodes", [])
        nodes = list(dict.fromkeys(
            n for n in raw if known_nodes is None or n in known_nodes))
        community = _doc_community(nodes, node_community)
        bucket = by_community.setdefault(community, _empty_bucket())

        sign = 1 if outcome == "useful" else -1 if outcome in ("dead_end", "corrected") else 0
        weight = _decay(date, now, half_life_days) if sign else 0.0

        for target in (overall, bucket):
            target["counts"][outcome if outcome in OUTCOMES else "unmarked"] += 1
            if sign:
                for n in nodes:
                    _record_node(target, n, sign, weight, date)
            if outcome == "dead_end":
                target["dead_ends"].append(
                    {"question": doc.get("question", ""), "nodes": nodes, "date": date})
            elif outcome == "corrected":
                target["corrections"].append(
                    {"question": doc.get("question", ""),
                     "correction": doc.get("correction", ""), "date": date})

    # Only surface per-community grouping when a graph was actually supplied;
    # without one every doc falls into Uncategorized and the section would just
    # duplicate the flat "Lessons" block.
    community_out: dict[str, dict[str, Any]] = {}
    if node_community:
        community_out = {
            label: {"counts": b["counts"], **_finalize_sources(b, min_corroboration),
                    "dead_ends": _dedupe_by_question(b["dead_ends"]),
                    "corrections": _dedupe_by_question(b["corrections"])}
            for label, b in by_community.items()
        }

    return {
        "total": len(docs),
        "counts": overall["counts"],
        "min_corroboration": min_corroboration,
        **_finalize_sources(overall, min_corroboration),
        "dead_ends": _dedupe_by_question(overall["dead_ends"]),
        "corrections": _dedupe_by_question(overall["corrections"]),
        "by_community": community_out,
    }


# --- rendering -----------------------------------------------------------------


def _render_bucket(out: list[str], data: dict[str, Any], k: int) -> None:
    preferred = data["preferred"]
    tentative = data["tentative"]
    contested = data["contested"]
    dead_ends = data["dead_ends"]
    corrections = data["corrections"]

    if preferred:
        out += [f"**Preferred sources** — corroborated by ≥{k} useful results; "
                "start here.", ""]
        for e in preferred:
            out.append(f"- `{e['node']}` ({e['n']}× useful)")
        out.append("")
    if tentative:
        out += [f"**Tentative** — useful in fewer than {k} results; verify before "
                "relying.", ""]
        for e in tentative:
            out.append(f"- `{e['node']}` ({e['n']}× useful)")
        out.append("")
    if contested:
        out += ["**Contested** — mixed signals; recency decides.", ""]
        for e in contested:
            day = e["last"][:10]
            verdict = ("evenly split" if e["verdict"] == "even"
                       else f"recency leans **{e['verdict']}**")
            out.append(
                f"- `{e['node']}` — {e['pos']}× useful, {e['neg']}× "
                f"dead end/corrected → {verdict}"
                + (f" (latest {day})" if day else ""))
        out.append("")
    if dead_ends:
        out += ["**Known dead ends** — led nowhere; don't re-derive.", ""]
        for d in dead_ends:
            nodes = ", ".join(f"`{n}`" for n in d["nodes"])
            out.append(f"- \"{d['question']}\"" + (f" — {nodes}" if nodes else ""))
        out.append("")
    if corrections:
        out += ["**Corrections** — do these differently.", ""]
        for c in corrections:
            out.append(f"- \"{c['question']}\" → {c['correction']}")
        out.append("")
    if not (preferred or tentative or contested or dead_ends or corrections):
        out += ["_No marked outcomes yet._", ""]


def render_lessons_md(agg: dict[str, Any]) -> str:
    """Render the aggregate into the deterministic LESSONS.md markdown body."""
    c = agg["counts"]
    k = agg.get("min_corroboration", _DEFAULT_MIN_CORROBORATION)
    out: list[str] = [
        "# Lessons",
        "",
        f"_Auto-generated by `graphify reflect` from {agg['total']} session "
        f"{'memory' if agg['total'] == 1 else 'memories'} in graphify-out/memory/. "
        "Deterministic; no LLM. Use for orientation — verify before relying, and "
        "revisit dead ends if the code has changed since._",
        "",
        "## Summary",
        "",
        f"- {c['useful']} useful · {c['dead_end']} dead ends · "
        f"{c['corrected']} corrected · {c['unmarked']} unmarked",
        "",
        "## Lessons",
        "",
    ]
    _render_bucket(out, agg, k)

    if agg["by_community"]:
        out += ["## By topic", ""]
        # Uncategorized sorts last; everything else alphabetically.
        def _topic_key(label: str) -> tuple[int, str]:
            return (1 if label == _UNCATEGORIZED else 0, label)
        for label in sorted(agg["by_community"], key=_topic_key):
            out += [f"### {label}", ""]
            _render_bucket(out, agg["by_community"][label], k)

    # Single trailing newline, no trailing whitespace lines.
    return "\n".join(out).rstrip("\n") + "\n"


# --- orchestrator --------------------------------------------------------------


def lessons_fresh(out_path: Path, memory_dir: Path,
                  graph_path: Path | None = None,
                  analysis_path: Path | None = None,
                  labels_path: Path | None = None) -> bool:
    """True if ``out_path`` exists and is at least as new as every input that
    feeds it (the memory docs, and the graph/sidecars when one is used).

    Lets ``graphify reflect --if-stale`` skip a redundant run — e.g. when the git
    post-commit hook just regenerated ``LESSONS.md`` and an agent then runs reflect
    again at the start of a session. A missing output is never fresh (it must be
    built). Mtime-based and best-effort; it only gates whether to *recompute*, not
    what the recomputation produces (that stays deterministic).
    """
    out_path = Path(out_path)
    try:
        out_mtime = out_path.stat().st_mtime
    except OSError:
        return False  # missing/unreadable -> must build
    newest = 0.0
    md = Path(memory_dir)
    if md.is_dir():
        for f in md.glob("*.md"):
            try:
                newest = max(newest, f.stat().st_mtime)
            except OSError:
                pass
    for input_path in (graph_path, analysis_path, labels_path):
        if input_path is None:
            continue
        gp = Path(input_path)
        try:
            newest = max(newest, gp.stat().st_mtime)
        except OSError:
            pass
    return out_mtime >= newest


def reflect(memory_dir: Path, out_path: Path,
            graph_path: Path | None = None,
            analysis_path: Path | None = None,
            labels_path: Path | None = None,
            *,
            now: datetime | None = None,
            half_life_days: float = _DEFAULT_HALF_LIFE_DAYS,
            min_corroboration: int = _DEFAULT_MIN_CORROBORATION,
            ) -> tuple[Path, dict[str, Any]]:
    """Scan ``memory_dir``, write the lessons doc to ``out_path``, return (path, agg).

    If ``graph_path`` is given lessons are grouped by community and source nodes no
    longer in the graph are dropped; otherwise the doc is a single flat section.
    """
    docs = load_memory_docs(memory_dir)

    node_community = None
    known_nodes = None
    if graph_path is not None:
        graph_path = Path(graph_path)
        analysis_path = Path(analysis_path) if analysis_path else (
            graph_path.parent / ".graphify_analysis.json")
        labels_path = Path(labels_path) if labels_path else (
            graph_path.parent / ".graphify_labels.json")
        node_community = _load_node_community(graph_path, analysis_path, labels_path)
        known_nodes = _load_known_nodes(graph_path)

    if now is None:
        now = datetime.now(timezone.utc)

    agg = aggregate_lessons(docs, node_community, now=now,
                            half_life_days=half_life_days,
                            min_corroboration=min_corroboration,
                            known_nodes=known_nodes)
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(render_lessons_md(agg), encoding="utf-8")
    return out_path, agg
