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
from graphify.paths import GRAPHIFY_OUT_NAME

_UNCATEGORIZED = "Uncategorized"

# Derived experiential layer written alongside graph.json (a SIDECAR, kept
# separate from the durable structural truth in graph.json — no learning_*
# fields are ever stamped into the graph itself). Read-surface annotations are
# merged in at display time from this file.
LEARNING_SIDECAR_NAME = ".graphify_learning.json"
_LEARNING_SCHEMA_VERSION = 1
_PROVENANCE_CAP = 5  # most-recent (question, date, outcome) entries per node

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
        # node -> list of (date, question, outcome) for useful/corrected citations.
        # Feeds the sidecar overlay's per-node provenance; never read by LESSONS.md,
        # so it doesn't touch the aggregate's public shape.
        "node_provenance": {},
        "dead_ends": [],
        "corrections": [],
    }


def _record_node(bucket: dict[str, Any], node: str, sign: int,
                 weight: float, date: str, *, outcome: str | None = None,
                 question: str = "") -> None:
    bucket["node_score"][node] = bucket["node_score"].get(node, 0.0) + sign * weight
    if sign > 0:
        bucket["node_pos"][node] += 1
    elif sign < 0:
        bucket["node_neg"][node] += 1
    if date > bucket["node_last"].get(node, ""):
        bucket["node_last"][node] = date
    # Provenance: only useful/corrected events are recorded (the experiential
    # trail an agent cares about — what cited this node, and how it turned out).
    if outcome in ("useful", "corrected"):
        bucket["node_provenance"].setdefault(node, []).append(
            (date, question, outcome))


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
                    _record_node(target, n, sign, weight, date,
                                 outcome=outcome, question=doc.get("question", ""))
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
        # Private: per-node (date, question, outcome) trail for the sidecar
        # overlay's provenance. Underscore-prefixed and not rendered by
        # render_lessons_md, so the public aggregate shape is unchanged.
        "_node_provenance": overall["node_provenance"],
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

    # Also project a derived experiential sidecar next to graph.json when a graph
    # is in hand. Best-effort: a sidecar failure must never break LESSONS.md.
    if graph_path is not None:
        try:
            write_learning_sidecar(agg, Path(graph_path), now=now)
        except Exception:
            pass

    return out_path, agg


# --- work-memory overlay sidecar ------------------------------------------------
#
# A derived, experiential projection of the reflect aggregate, written next to
# graph.json as ``.graphify_learning.json``. It carries which nodes have proven
# preferred/tentative/contested, a code fingerprint for staleness detection, and
# a short provenance trail. graph.json (durable structural truth) is never
# touched — read surfaces merge this overlay in only at display time.


def _build_id_label_maps(graph_path: Path) -> tuple[dict[str, str], dict[str, list[str]],
                                                    dict[str, dict[str, Any]]]:
    """From graph.json build:

    - ``id_set``: id -> id (every node id, so an id-form citation resolves to itself)
    - ``label_to_ids``: label -> [ids] (so a label-form citation can be resolved,
      and ambiguity — one label, many ids — can be detected and skipped)
    - ``node_by_id``: id -> node dict (for source_file lookup)

    Best-effort; an unreadable/garbage graph yields empty maps.
    """
    id_set: dict[str, str] = {}
    label_to_ids: dict[str, list[str]] = {}
    node_by_id: dict[str, dict[str, Any]] = {}
    try:
        data = json.loads(Path(graph_path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return id_set, label_to_ids, node_by_id
    for n in data.get("nodes", []):
        if not isinstance(n, dict) or n.get("id") is None:
            continue
        nid = str(n["id"])
        id_set[nid] = nid
        node_by_id[nid] = n
        label = n.get("label")
        if label is not None:
            label_to_ids.setdefault(str(label), []).append(nid)
    return id_set, label_to_ids, node_by_id


def _resolve_canonical_id(cited: str, id_set: dict[str, str],
                          label_to_ids: dict[str, list[str]]) -> str | None:
    """Resolve a cited node (a label OR an id) to a single canonical node id.

    Returns None if the citation is unresolved (stale — gone from the graph) or
    ambiguous (a label shared by >1 node id). Such citations can't be displayed
    against a single node, so the caller skips them.
    """
    if cited in id_set:
        return id_set[cited]
    ids = label_to_ids.get(cited)
    if ids and len(ids) == 1:
        return ids[0]
    return None


def _resolve_source_path(src: str, graph_path: Path) -> Path | None:
    """Locate a node's ``source_file`` on disk, returning an existing file or None.

    ``source_file`` is stored relative to the PROJECT root, but graph.json may
    live in ``<root>/graphify-out/`` (so its own dir is not the root) or directly
    at the root (``extract --out .``). Resolve the root in the most-likely order
    and return the first candidate where the file actually exists, so a defeated
    heuristic or a stale marker can never strand the file (every node would then
    look "changed"). The same search runs at write and read time, so the writer
    and reader resolve to the same file.

    Order: the committed ``.graphify_root`` marker (#686/#1423 — authoritative for
    an absolute/elsewhere ``GRAPHIFY_OUT`` override); then the layout-appropriate
    root *first* — graph.json's parent's parent for the ``graphify-out`` layout,
    or graph.json's own dir for a flat layout — which avoids matching a same-named
    file one directory up; then the other of the two; then the cwd.
    """
    if not src:
        return None
    p = Path(src)
    if p.is_absolute():
        return p if p.is_file() else None
    gp = Path(graph_path)
    out_dir = gp.parent
    candidates: list[Path] = []
    try:
        recorded = (out_dir / ".graphify_root").read_text(encoding="utf-8").strip()
        if recorded:
            candidates.append(Path(recorded))
    except (OSError, ValueError):
        pass  # unreadable/non-UTF-8 marker -> fall through (best-effort)
    # Layout-appropriate root first (precision), then the other (robustness).
    if out_dir.name == GRAPHIFY_OUT_NAME:
        candidates += [out_dir.parent, out_dir]
    else:
        candidates += [out_dir, out_dir.parent]
    candidates.append(Path("."))
    seen: set[str] = set()
    for base in candidates:
        key = str(base)
        if key in seen:
            continue
        seen.add(key)
        cand = base / p
        if cand.is_file():
            return cand
    return None


def _content_hash(path: Path) -> str:
    """SHA256 of file CONTENT only (no path mixed in), so the fingerprint is
    independent of which root resolved the file — write and read agree, and a
    committed sidecar stays valid across machines/checkouts."""
    import hashlib
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return ""


def _code_fingerprint(node: dict[str, Any] | None, graph_path: Path) -> str:
    """Content hash of the node's ``source_file``, or '' if unavailable.

    Coarse on purpose — a file-level hash over-flags (any edit to the file marks
    every node in it stale) rather than under-flags, which is the safe direction
    for a "re-verify" hint.
    """
    if not node:
        return ""
    sp = _resolve_source_path(node.get("source_file") or "", graph_path)
    return _content_hash(sp) if sp is not None else ""


def _provenance_for(node: str, prov_map: dict[str, list],
                    fallback_outcome: str) -> list[dict[str, str]]:
    """Most-recent-first, capped provenance entries for a node.

    ``prov_map`` is the aggregate's private per-node (date, question, outcome)
    trail. ``fallback_outcome`` covers an entry with no recorded trail (shouldn't
    happen for preferred/tentative/contested, which all have ≥1 positive event).
    """
    events = prov_map.get(node, [])
    # Sort recent-first; (date desc, then question for a stable tiebreak).
    ordered = sorted(events, key=lambda e: (e[0], e[1]), reverse=True)
    out: list[dict[str, str]] = []
    for date, question, outcome in ordered[:_PROVENANCE_CAP]:
        out.append({"q": question, "date": date, "outcome": outcome})
    return out


def build_learning_overlay(agg: dict[str, Any], graph_path: Path,
                           *, now: datetime | None = None) -> dict[str, Any]:
    """Project the reflect aggregate into the sidecar's ``{version, generated_at,
    nodes}`` structure, keyed by canonical node id.

    Built from preferred + tentative + contested (NOT dead_ends — those stay
    query-scoped, surfaced only in the report). Citations that don't resolve to
    exactly one node id are skipped.
    """
    if now is None:
        now = datetime.now(timezone.utc)
    elif now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)

    graph_path = Path(graph_path)
    id_set, label_to_ids, node_by_id = _build_id_label_maps(graph_path)
    prov_map = agg.get("_node_provenance", {})

    # id -> entry; a canonical id can be cited under both its id and label form,
    # but the aggregate dedups per node string, so collisions here are benign and
    # resolved deterministically by iteration order (preferred, tentative, contested).
    nodes_out: dict[str, dict[str, Any]] = {}

    def _add(entry_src: dict[str, Any], status: str) -> None:
        cited = entry_src["node"]
        cid = _resolve_canonical_id(cited, id_set, label_to_ids)
        if cid is None:
            return  # ambiguous or stale — can't display against a single node
        if cid in nodes_out:
            return  # first status wins (preferred > tentative > contested order)
        node = node_by_id.get(cid)
        out: dict[str, Any] = {
            "status": status,
            "score": entry_src["score"],
            "uses": entry_src.get("n", entry_src.get("pos", 0)),
            "last": entry_src.get("last", ""),
            "label": str(node.get("label", cited)) if node else str(cited),
            "source_file": str(node.get("source_file") or "") if node else "",
            "code_fingerprint": _code_fingerprint(node, graph_path),
            "provenance": _provenance_for(cited, prov_map, status),
        }
        if status == "contested":
            out["verdict"] = entry_src.get("verdict", "even")
            out["neg"] = entry_src.get("neg", 0)
        else:
            # preferred/tentative carry no contested verdict; derive `last` from
            # provenance if the finalizer didn't (positive-only buckets do track it
            # via node_last for contested only).
            if not out["last"] and out["provenance"]:
                out["last"] = out["provenance"][0]["date"]
        nodes_out[cid] = out

    for e in agg.get("preferred", []):
        _add(e, "preferred")
    for e in agg.get("tentative", []):
        _add(e, "tentative")
    for e in agg.get("contested", []):
        _add(e, "contested")

    return {
        "version": _LEARNING_SCHEMA_VERSION,
        "generated_at": now.isoformat(),
        "nodes": nodes_out,
    }


def write_learning_sidecar(agg: dict[str, Any], graph_path: Path,
                           *, now: datetime | None = None) -> Path:
    """Write ``.graphify_learning.json`` next to ``graph_path`` deterministically.

    Sorted keys + indent=2 so re-runs on identical input (and a fixed ``now``)
    are byte-identical. Returns the sidecar path.
    """
    overlay = build_learning_overlay(agg, graph_path, now=now)
    sidecar = Path(graph_path).parent / LEARNING_SIDECAR_NAME
    sidecar.write_text(
        json.dumps(overlay, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return sidecar


def load_learning_overlay(graph_path: Path) -> dict[str, dict[str, Any]]:
    """Load the sidecar next to ``graph_path`` and return ``{node_id -> entry}``
    with a recomputed ``stale: bool`` per entry. Best-effort -> {} on any error.

    Staleness: recompute ``file_hash(source_file)`` and compare to the entry's
    stored ``code_fingerprint``. Matching fingerprints -> not stale. Differing,
    missing-but-recomputable, or a vanished file -> stale (the safe, over-flagging
    direction). An entry with no stored fingerprint AND no current file is not
    marked stale (nothing to re-verify).
    """
    sidecar = Path(graph_path).parent / LEARNING_SIDECAR_NAME
    try:
        data = json.loads(sidecar.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    nodes = data.get("nodes")
    if not isinstance(nodes, dict):
        return {}
    out: dict[str, dict[str, Any]] = {}
    for nid, entry in nodes.items():
        if not isinstance(entry, dict):
            continue
        merged = dict(entry)
        merged["stale"] = _is_stale(entry, graph_path)
        out[str(nid)] = merged
    return out


def _is_stale(entry: dict[str, Any], graph_path: Path) -> bool:
    """True if the node's source file changed (or vanished) since the fingerprint
    was taken. Uses the same file resolution + content hash as the writer, so a
    freshly-written verdict on unchanged code is never spuriously stale."""
    src = entry.get("source_file", "")
    if not src:
        # No file to track — nothing to re-verify.
        return False
    sp = _resolve_source_path(src, graph_path)
    if sp is None:
        return True  # file gone / unfindable — re-verify
    stored = entry.get("code_fingerprint", "")
    if not stored:
        return True  # had a file but never fingerprinted it -> can't trust -> stale
    return _content_hash(sp) != stored
