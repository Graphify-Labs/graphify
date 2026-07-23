# write native graph snapshots to presentation and graph-database formats
from __future__ import annotations
import hashlib
import html as _html
import json
import math
import os
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from .helix.model import GraphBuildData, edge_attributes, graphify_attributes, node_attributes
from graphify.security import sanitize_label
from graphify.analyze import _node_community_map
from graphify.build import edge_data

from graphify.exporters.graphdb import push_to_falkordb, push_to_neo4j  # noqa: E402,F401


def _portable_identity(value: Any) -> str:
    """Lossless string identity for formats without Helix typed IDs."""
    from helixdb.graph import external_id_to_json

    return json.dumps(
        external_id_to_json(value), sort_keys=True, separators=(",", ":")
    )

def _obsidian_tag(name: str) -> str:
    """Sanitize a community name for use as an Obsidian tag.

    Obsidian tags only allow alphanumerics, hyphens, underscores, and slashes.
    Spaces become underscores; everything else is stripped.
    """
    return re.sub(r"[^a-zA-Z0-9_\-/]", "", name.replace(" ", "_"))


def _strip_diacritics(text: str | None) -> str:
    import unicodedata
    if not isinstance(text, str):
        text = "" if text is None else str(text)
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def _yaml_str(s: str) -> str:
    """Escape a value for safe embedding in a YAML double-quoted scalar (F-009).

    See `graphify.ingest._yaml_str` for the full rationale; duplicated here to
    avoid pulling the URL-fetching `ingest` module into export's dependency
    graph. Handles backslash, double-quote, all line breaks (\\n, \\r,
    U+2028, U+2029), tab, NUL, and other C0/DEL control characters that
    would otherwise let a hostile `source_file` / `community` / etc. break
    out of the YAML scalar and inject sibling keys.
    """
    if s is None:
        return ""
    out: list[str] = []
    for ch in str(s):
        cp = ord(ch)
        if ch == "\\":
            out.append("\\\\")
        elif ch == '"':
            out.append('\\"')
        elif ch == "\n":
            out.append("\\n")
        elif ch == "\r":
            out.append("\\r")
        elif ch == "\t":
            out.append("\\t")
        elif ch == "\0":
            out.append("\\0")
        elif cp == 0x2028:
            out.append("\\L")
        elif cp == 0x2029:
            out.append("\\P")
        elif cp < 0x20 or cp == 0x7F:
            out.append(f"\\x{cp:02x}")
        else:
            out.append(ch)
    return "".join(out)


from graphify.exporters.base import COMMUNITY_COLORS  # noqa: E402,F401

from graphify.exporters.html import to_html  # noqa: E402,F401


_CONFIDENCE_SCORE_DEFAULTS = {"EXTRACTED": 1.0, "INFERRED": 0.5, "AMBIGUOUS": 0.2}


def _edge_rows(graph: Any, node_id: Any | None = None):
    records = graph.edges() if node_id is None else (
        graph.edge(edge_id) for edge_id in graph.incident_edge_ids(node_id)
    )
    for edge in records:
        if edge is not None:
            yield edge.source, edge.target, edge_attributes(edge), edge


def _edge_attributes(graph: Any, source: Any, target: Any) -> dict:
    edge_ids = graph.edges_between(source, target)
    edge = graph.edge(edge_ids[0]) if edge_ids else None
    return edge_attributes(edge) if edge is not None else {}


def _graph_attributes(graph: Any) -> dict:
    metadata = dict(graph.attributes)
    value = metadata.get("graph", {})
    return dict(value) if isinstance(value, dict) else {}


def attach_hyperedges(G: GraphBuildData, hyperedges: list) -> None:
    """Store hyperedges in the graph's metadata dict."""
    existing = G.attributes.get("hyperedges", [])
    seen_ids = {h["id"] for h in existing}
    for h in hyperedges:
        if h.get("id") and h["id"] not in seen_ids:
            existing.append(h)
            seen_ids.add(h["id"])
    G.attributes["hyperedges"] = existing


def _git_head() -> str | None:
    """Return the current git HEAD commit hash, or None if not in a git repo."""
    import subprocess as _sp
    try:
        r = _sp.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, timeout=3)
        return r.stdout.strip() if r.returncode == 0 else None
    except Exception:
        return None


def prune_dangling_edges(graph_data: dict) -> tuple[dict, int]:
    """Remove edges whose source or target node is not in the node set.

    Returns the cleaned graph_data dict and the number of pruned edges.
    """
    node_ids = {n["id"] for n in graph_data["nodes"]}
    links_key = "links" if "links" in graph_data else "edges"
    before = len(graph_data[links_key])
    graph_data[links_key] = [
        e for e in graph_data[links_key]
        if e["source"] in node_ids and e["target"] in node_ids
    ]
    return graph_data, before - len(graph_data[links_key])


def _cypher_escape(s: str) -> str:
    """Escape a string for safe embedding in a Cypher single-quoted literal.

    Handles all characters that could prematurely terminate the literal or
    inject control sequences:
      - `\\` and `'` (literal terminators)
      - newlines/CRs (would break the per-line statement framing)
      - NUL/control bytes (defensive — Neo4j errors on raw NULs)

    Also strips any leading/trailing whitespace that would let an attacker
    break the `;`-terminated statement boundary used by `cypher-shell`.
    Closing `}` and `)` are NOT special inside a single-quoted Cypher string,
    so escaping the quote and backslash correctly is sufficient (a `}` inside
    a properly-closed `'...'` literal is just a character) — but we previously
    missed `\\n` / `\\r` which DO let a payload break out of the statement
    line and inject a fresh MATCH/DELETE on the following line. See F-008.
    """
    # First normalise: drop NUL and other C0 control chars except tab.
    s = "".join(ch for ch in s if ch >= " " or ch == "\t")
    return (
        s.replace("\\", "\\\\")
         .replace("'", "\\'")
         .replace("\n", "\\n")
         .replace("\r", "\\r")
    )


# Restrict identifier-position values (labels and relationship types are NOT
# quoted in Cypher and so cannot be safely escaped — they must be allowlisted).
_CYPHER_IDENT_RE = re.compile(r"[^A-Za-z0-9_]")


def _cypher_label(raw: str, fallback: str) -> str:
    """Sanitise a value used in identifier position (node label / rel type).

    Cypher does not provide a way to escape `:Foo` label syntax, so we must
    strip everything except `[A-Za-z0-9_]` and require the result to start
    with a letter; otherwise we fall back to a safe constant.
    """
    cleaned = _CYPHER_IDENT_RE.sub("", raw or "")
    if not cleaned or not cleaned[0].isalpha():
        return fallback
    return cleaned


def to_cypher(G: Any, output_path: str) -> None:
    lines = ["// Neo4j Cypher import - generated by /graphify", ""]
    for node in G.nodes():
        node_id, data = node.id, graphify_attributes(node.attributes)
        label = _cypher_escape(data.get("label", node_id))
        node_id_esc = _cypher_escape(_portable_identity(node_id))
        ftype = _cypher_label(
            (data.get("file_type", "unknown") or "unknown").capitalize(),
            "Entity",
        )
        lines.append(f"MERGE (n:{ftype} {{id: '{node_id_esc}', label: '{label}'}});")
    lines.append("")
    for edge in G.edges():
        u, v, data = edge.source, edge.target, edge_attributes(edge)
        rel = _cypher_label(
            (data.get("relation", "RELATES_TO") or "RELATES_TO").upper(),
            "RELATES_TO",
        )
        conf = _cypher_escape(data.get("confidence", "EXTRACTED"))
        u_esc = _cypher_escape(_portable_identity(u))
        v_esc = _cypher_escape(_portable_identity(v))
        lines.append(
            f"MATCH (a {{id: '{u_esc}'}}), (b {{id: '{v_esc}'}}) "
            f"MERGE (a)-[:{rel} {{confidence: '{conf}'}}]->(b);"
        )
    with open(output_path, "w", encoding="utf-8") as f:  # nosec
        f.write("\n".join(lines))


# Keep backward-compatible alias - skill.md calls generate_html
generate_html = to_html


def _cap_filename(s: str, limit: int = 200) -> str:
    """Cap a filename stem to ``limit`` UTF-8 bytes so it stays under the 255-byte
    filesystem limit even after the ``.md`` extension and dedup suffix are added
    (#1094). The cap is on BYTES, not chars, because a label of multibyte
    characters (CJK, accented) can exceed 255 bytes well under 255 chars. When
    truncation happens, an 8-char hash of the full label is appended so two
    distinct labels sharing a long prefix produce distinct, deterministic
    filenames instead of colliding."""
    b = s.encode("utf-8")
    if len(b) <= limit:
        return s
    digest = hashlib.sha1(s.encode("utf-8")).hexdigest()[:8]  # nosec - not security
    keep = limit - 9  # "_" + 8 hex chars
    truncated = b[:keep].decode("utf-8", "ignore")  # "ignore" drops a split trailing char
    return f"{truncated}_{digest}"


def _dedup_node_filenames(G: Any, safe_name) -> dict[Any, str]:
    """Map each node_id to a unique note filename, appending a numeric suffix on
    collision. The collision set is keyed on the lowercased name so two labels
    differing only by case (e.g. "References" vs "references") still get distinct
    filenames - on case-insensitive filesystems (macOS/APFS, Windows/NTFS) they
    would otherwise resolve to one path and silently overwrite each other on disk.
    The suffixed candidate is itself re-checked, so a generated "base_1" never
    silently overwrites a node whose literal label is already "base_1"."""
    node_filenames: dict[str, str] = {}
    used: set[str] = set()
    for node in G.nodes():
        node_id, data = node.id, graphify_attributes(node.attributes)
        base = safe_name(data.get("label", node_id))
        candidate = base
        n = 1
        while candidate.lower() in used:
            candidate = f"{base}_{n}"
            n += 1
        used.add(candidate.lower())
        node_filenames[node_id] = candidate
    return node_filenames


def to_obsidian(
    G: Any,
    communities: dict[int, list[str]],
    output_dir: str,
    community_labels: dict[int, str] | None = None,
    cohesion: dict[int, float] | None = None,
) -> int:
    """Export graph as an Obsidian vault - one .md file per node with [[wikilinks]],
    plus one _COMMUNITY_name.md overview note per community (sorted to top by underscore prefix).

    Open the output directory as a vault in Obsidian to get an interactive
    graph view with community colors and full-text search over node metadata.

    Returns the number of node notes + community notes written.
    """
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    # #1506: when the export target is an existing Obsidian vault (a user pointed
    # --obsidian-dir at one), we must not clobber the user's own notes or their
    # .obsidian/ config. Track the files graphify owns in a manifest; a pre-existing
    # file NOT in the manifest is the user's and is never overwritten.
    _manifest_path = out / ".graphify_obsidian_manifest.json"
    try:
        _owned: set[str] = set(json.loads(_manifest_path.read_text(encoding="utf-8")).get("files", []))
    except (OSError, ValueError):
        _owned = set()
    _written: list[str] = []
    _skipped: list[str] = []

    def _owned_write(rel_name: str, content: str) -> bool:
        """Write a graphify-owned file, refusing to overwrite a pre-existing file
        graphify didn't create. Returns True if written."""
        target = out / rel_name
        if target.exists() and rel_name not in _owned:
            _skipped.append(rel_name)
            return False
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")  # nosec
        _written.append(rel_name)
        return True

    node_community = _node_community_map(communities)

    # Map node_id → safe filename so wikilinks stay consistent.
    # Deduplicate: if two nodes produce the same filename, append a numeric suffix.
    def safe_name(label: str) -> str:
        cleaned = re.sub(r'[\\/*?:"<>|#^[\]]', "", label.replace("\r\n", " ").replace("\r", " ").replace("\n", " ")).strip()
        # Strip trailing .md/.mdx/.markdown so "CLAUDE.md" doesn't become "CLAUDE.md.md"
        cleaned = re.sub(r"\.(md|mdx|qmd|markdown)$", "", cleaned, flags=re.IGNORECASE)
        # A stem of only punctuation (e.g. "@", "*", "#") survives the unsafe-char
        # strip above but is empty once a downstream tool re-slugs on word chars
        # (e.g. qmd's handelize() reduces "@" -> "" and raises, aborting the whole
        # `qmd update`). Require at least one word char; else fall back so we never
        # emit a "@.md"-style filename. (#1409)
        if not re.search(r"\w", cleaned, flags=re.UNICODE):
            return "unnamed"
        return _cap_filename(cleaned)

    node_filename = _dedup_node_filenames(G, safe_name)

    # Helper: compute dominant confidence for a node across all its edges
    def _dominant_confidence(node_id: str) -> str:
        confs = []
        for u, v, edata, _ in _edge_rows(G, node_id):
            confs.append(edata.get("confidence", "EXTRACTED"))
        if not confs:
            return "EXTRACTED"
        return Counter(confs).most_common(1)[0][0]

    # Map file_type → graphify tag
    _FTYPE_TAG = {
        "code": "graphify/code",
        "document": "graphify/document",
        "paper": "graphify/paper",
        "image": "graphify/image",
    }

    # Write one .md file per node
    node_notes_written = 0
    for node in G.nodes():
        node_id, data = node.id, graphify_attributes(node.attributes)
        label = data.get("label", node_id)
        cid = node_community.get(node_id)
        community_name = (
            community_labels.get(cid, f"Community {cid}")
            if community_labels and cid is not None
            else f"Community {cid}"
        )

        # Build tags for this node
        ftype = data.get("file_type", "")
        ftype_tag = _FTYPE_TAG.get(ftype, f"graphify/{ftype}" if ftype else "graphify/document")
        dom_conf = _dominant_confidence(node_id)
        conf_tag = f"graphify/{dom_conf}"
        comm_tag = f"community/{_obsidian_tag(community_name)}"
        node_tags = [ftype_tag, conf_tag, comm_tag]

        lines: list[str] = []

        # YAML frontmatter - readable in Obsidian's properties panel.
        # All scalars pass through _yaml_str so a hostile source_file or
        # community label cannot break out and inject sibling keys (F-009).
        lines += [
            "---",
            f'source_file: "{_yaml_str(data.get("source_file", ""))}"',
            f'type: "{_yaml_str(ftype)}"',
            f'community: "{_yaml_str(community_name)}"',
        ]
        if data.get("source_location"):
            lines.append(f'location: "{_yaml_str(str(data["source_location"]))}"')
        # Add tags list to frontmatter
        lines.append("tags:")
        for tag in node_tags:
            lines.append(f"  - {tag}")
        lines += ["---", "", f"# {label}", ""]

        # Outgoing edges as wikilinks
        neighbors = list(G.neighbors(node_id))
        if neighbors:
            lines.append("## Connections")
            for neighbor in sorted(
                neighbors,
                key=lambda n: str(node_attributes(G, n).get("label", n)),
            ):
                edata = edge_data(G, node_id, neighbor)
                neighbor_label = node_filename[neighbor]
                relation = edata.get("relation", "")
                confidence = edata.get("confidence", "EXTRACTED")
                lines.append(f"- [[{neighbor_label}]] - `{relation}` [{confidence}]")
            lines.append("")

        # Inline tags at bottom of note body (for Obsidian tag panel)
        inline_tags = " ".join(f"#{t}" for t in node_tags)
        lines.append(inline_tags)

        fname = node_filename[node_id] + ".md"
        if _owned_write(fname, "\n".join(lines)):
            node_notes_written += 1

    # Write one _COMMUNITY_name.md overview note per community
    # Build inter-community edge counts for "Connections to other communities"
    inter_community_edges: dict[int, dict[int, int]] = {}
    for cid in communities:
        inter_community_edges[cid] = {}
    for edge in G.edges():
        u, v = edge.source, edge.target
        cu = node_community.get(u)
        cv = node_community.get(v)
        if cu is not None and cv is not None and cu != cv:
            inter_community_edges.setdefault(cu, {})
            inter_community_edges.setdefault(cv, {})
            inter_community_edges[cu][cv] = inter_community_edges[cu].get(cv, 0) + 1
            inter_community_edges[cv][cu] = inter_community_edges[cv].get(cu, 0) + 1

    # Precompute per-node community reach (number of distinct communities a node connects to)
    def _community_reach(node_id: str) -> int:
        neighbor_cids = {
            node_community[nb]
            for nb in G.neighbors(node_id)
            if nb in node_community and node_community[nb] != node_community.get(node_id)
        }
        return len(neighbor_cids)

    def _community_name(cid) -> str:
        return (
            community_labels.get(cid, f"Community {cid}")
            if community_labels and cid is not None
            else f"Community {cid}"
        )

    # One case-folded-deduped filename per community, computed once so the note we
    # write and every [[_COMMUNITY_...]] cross-reference resolve to the same file.
    # Two community labels differing only by case (e.g. LLM labels "API" vs "Api")
    # would otherwise overwrite each other on case-insensitive filesystems - and
    # this path had no dedup at all, so even same-case duplicate labels collided.
    community_filename: dict = {}
    used_community: set[str] = set()
    for cid in communities:
        base = f"_COMMUNITY_{safe_name(_community_name(cid))}"
        candidate = base
        n = 1
        while candidate.lower() in used_community:
            candidate = f"{base}_{n}"
            n += 1
        used_community.add(candidate.lower())
        community_filename[cid] = candidate

    community_notes_written = 0
    for cid, all_members in communities.items():
        community_name = _community_name(cid)
        # A community's member list can contain ids with no backing node in G
        # (e.g. pruned nodes, stale community assignments from a prior run, or
        # synthesized/merge-artifact ids). Dereferencing those via G.nodes[n] or
        # node_filename[n] raises KeyError and aborts the whole vault export, so
        # skip dangling members rather than crashing (issue #1236).
        members = [m for m in all_members if G.contains_node(m) and m in node_filename]
        n_members = len(members)
        coh_value = cohesion.get(cid) if cohesion else None

        lines: list[str] = []

        # YAML frontmatter
        lines.append("---")
        lines.append("type: community")
        if coh_value is not None:
            lines.append(f"cohesion: {coh_value:.2f}")
        lines.append(f"members: {n_members}")
        lines.append("---")
        lines.append("")
        lines.append(f"# {community_name}")
        lines.append("")

        # Cohesion + member count summary
        if coh_value is not None:
            cohesion_desc = (
                "tightly connected" if coh_value >= 0.7
                else "moderately connected" if coh_value >= 0.4
                else "loosely connected"
            )
            lines.append(f"**Cohesion:** {coh_value:.2f} - {cohesion_desc}")
        lines.append(f"**Members:** {n_members} nodes")
        lines.append("")

        # Members section
        lines.append("## Members")
        for node_id in sorted(
            members, key=lambda n: str(node_attributes(G, n).get("label", n))
        ):
            data = node_attributes(G, node_id)
            node_label = node_filename[node_id]
            ftype = data.get("file_type", "")
            source = data.get("source_file", "")
            entry = f"- [[{node_label}]]"
            if ftype:
                entry += f" - {ftype}"
            if source:
                entry += f" - {source}"
            lines.append(entry)
        lines.append("")

        # Dataview live query (improvement 2)
        comm_tag_name = _obsidian_tag(community_name)
        lines.append("## Live Query (requires Dataview plugin)")
        lines.append("")
        lines.append("```dataview")
        lines.append(f"TABLE source_file, type FROM #community/{comm_tag_name}")
        lines.append("SORT file.name ASC")
        lines.append("```")
        lines.append("")

        # Connections to other communities
        cross = inter_community_edges.get(cid, {})
        if cross:
            lines.append("## Connections to other communities")
            for other_cid, edge_count in sorted(cross.items(), key=lambda x: -x[1]):
                other_fname = community_filename.get(other_cid) or f"_COMMUNITY_{safe_name(_community_name(other_cid))}"
                lines.append(f"- {edge_count} edge{'s' if edge_count != 1 else ''} to [[{other_fname}]]")
            lines.append("")

        # Top bridge nodes - highest degree nodes that connect to other communities
        bridge_nodes = [
            (node_id, G.degree(node_id).degree, _community_reach(node_id))
            for node_id in members
            if _community_reach(node_id) > 0
        ]
        bridge_nodes.sort(key=lambda x: (-x[2], -x[1]))
        top_bridges = bridge_nodes[:5]
        if top_bridges:
            lines.append("## Top bridge nodes")
            for node_id, degree, reach in top_bridges:
                node_label = node_filename[node_id]
                lines.append(
                    f"- [[{node_label}]] - degree {degree}, connects to {reach} "
                    f"{'community' if reach == 1 else 'communities'}"
                )

        fname = community_filename[cid] + ".md"
        if _owned_write(fname, "\n".join(lines)):
            community_notes_written += 1

    # Improvement 4: write .obsidian/graph.json to color nodes by community in graph
    # view — but never clobber an existing .obsidian/graph.json graphify doesn't own
    # (the user's graph-view settings live there). _owned_write handles that and
    # creates the .obsidian/ dir only when it actually writes.
    graph_config = {
        "colorGroups": [
            {
                "query": f"tag:#community/{label.replace(' ', '_')}",
                "color": {"a": 1, "rgb": int(COMMUNITY_COLORS[cid % len(COMMUNITY_COLORS)].lstrip('#'), 16)}
            }
            for cid, label in sorted((community_labels or {}).items())
        ]
    }
    _owned_write(".obsidian/graph.json", json.dumps(graph_config, indent=2))

    # #1896: prune notes for nodes that dropped out of the graph. Only files the
    # manifest says graphify owns are candidates, and anything written or skipped
    # this run is excluded — so a user's own note is never touched (foreign files
    # land in _skipped, never _owned). Guard each path to stay inside the vault in
    # case a corrupt/hostile manifest contains `../` entries.
    stale = _owned - set(_written) - set(_skipped)
    pruned = 0
    for rel_name in sorted(stale):
        target = (out / rel_name).resolve()
        if out.resolve() not in target.parents:
            continue
        try:
            target.unlink(missing_ok=True)
            pruned += 1
        except OSError:
            pass
    if pruned:
        print(
            f"[graphify] pruned {pruned} note(s) for nodes no longer in the graph",
            file=sys.stderr,
        )

    # Persist the manifest of files graphify owns, so a re-run can safely update its
    # own notes while still refusing to touch the user's. Warn (once, aggregated)
    # about anything skipped to avoid clobbering a pre-existing file.
    try:
        _manifest_path.write_text(json.dumps({"files": sorted(set(_written))}, indent=2), encoding="utf-8")
    except OSError:
        pass
    if _skipped:
        shown = ", ".join(_skipped[:5]) + (f" (+{len(_skipped) - 5} more)" if len(_skipped) > 5 else "")
        print(
            f"[graphify] WARNING: skipped {len(_skipped)} pre-existing file(s) graphify "
            f"did not create, to avoid overwriting your notes: {shown}. "
            f"Export into an empty directory (or the default graphify-out/obsidian) "
            f"to get the full vault.",
            file=sys.stderr,
        )

    return node_notes_written + community_notes_written


def to_canvas(
    G: Any,
    communities: dict[int, list[str]],
    output_path: str,
    community_labels: dict[int, str] | None = None,
    node_filenames: dict[str, str] | None = None,
) -> None:
    """Export graph as an Obsidian Canvas file - communities as groups, nodes as cards.

    Generates a structured layout: communities arranged in a grid, nodes within
    each community arranged in rows. Edges shown between connected nodes.
    Opens in Obsidian as an infinite canvas with community groupings visible.
    """
    # Obsidian canvas color codes (cycle through for communities)
    CANVAS_COLORS = ["1", "2", "3", "4", "5", "6"]  # red, orange, yellow, green, cyan, purple

    def safe_name(label: str) -> str:
        cleaned = re.sub(r'[\\/*?:"<>|#^[\]]', "", label.replace("\r\n", " ").replace("\r", " ").replace("\n", " ")).strip()
        cleaned = re.sub(r"\.(md|mdx|qmd|markdown)$", "", cleaned, flags=re.IGNORECASE)
        # A stem of only punctuation (e.g. "@", "*", "#") survives the unsafe-char
        # strip above but is empty once a downstream tool re-slugs on word chars
        # (e.g. qmd's handelize() reduces "@" -> "" and raises, aborting the whole
        # `qmd update`). Require at least one word char; else fall back so we never
        # emit a "@.md"-style filename. (#1409)
        if not re.search(r"\w", cleaned, flags=re.UNICODE):
            return "unnamed"
        return _cap_filename(cleaned)

    # Build node_filenames if not provided (same dedup logic as to_obsidian)
    if node_filenames is None:
        node_filenames = _dedup_node_filenames(G, safe_name)

    # Fallback: with no community data (e.g. --no-cluster builds or a missing
    # analysis sidecar) the grid below produces nothing and the canvas is written
    # as an empty 32-byte shell on an otherwise populated graph. Emit every node
    # into one synthetic community so the canvas always reflects the graph (#1324).
    if not communities and G.node_count > 0:
        communities = {0: [node.id for node in G.nodes()]}

    num_communities = len(communities)
    cols = math.ceil(math.sqrt(num_communities)) if num_communities > 0 else 1
    rows = math.ceil(num_communities / cols) if num_communities > 0 else 1

    canvas_nodes: list[dict] = []
    canvas_edges: list[dict] = []

    # Lay out communities in a grid
    gap = 80
    group_x_offsets: list[int] = []
    group_y_offsets: list[int] = []

    # Precompute group sizes so we can calculate offsets.
    # inner_cols is the per-community grid width; the box dimensions AND the node
    # placement loop below both derive from it, so the cards always fill the box
    # instead of wrapping into a narrow strip inside an oversized box.
    sorted_cids = sorted(communities.keys())
    group_sizes: dict[int, tuple[int, int]] = {}
    group_cols: dict[int, int] = {}
    for cid in sorted_cids:
        # Skip dangling community members with no backing node / filename, so box
        # sizing matches the cards actually laid out and `G.nodes[m]` never
        # KeyErrors below — mirrors the to_obsidian guard (#1236).
        members = [m for m in communities[cid] if G.contains_node(m) and m in node_filenames]
        n = len(members)
        inner_cols = max(1, math.ceil(math.sqrt(n)))
        w = max(600, 220 * inner_cols)
        h = max(400, 100 * math.ceil(n / inner_cols) + 120)
        group_sizes[cid] = (w, h)
        group_cols[cid] = inner_cols

    # Compute cumulative row heights and col widths for grid placement
    # Each grid cell uses the max width/height in its col/row
    col_widths: list[int] = []
    row_heights: list[int] = []
    for col_idx in range(cols):
        max_w = 0
        for row_idx in range(rows):
            linear = row_idx * cols + col_idx
            if linear < len(sorted_cids):
                cid = sorted_cids[linear]
                w, _ = group_sizes[cid]
                max_w = max(max_w, w)
        col_widths.append(max_w)

    for row_idx in range(rows):
        max_h = 0
        for col_idx in range(cols):
            linear = row_idx * cols + col_idx
            if linear < len(sorted_cids):
                cid = sorted_cids[linear]
                _, h = group_sizes[cid]
                max_h = max(max_h, h)
        row_heights.append(max_h)

    # Map from cid → (group_x, group_y, group_w, group_h)
    group_layout: dict[int, tuple[int, int, int, int]] = {}
    for idx, cid in enumerate(sorted_cids):
        col_idx = idx % cols
        row_idx = idx // cols
        gx = sum(col_widths[:col_idx]) + col_idx * gap
        gy = sum(row_heights[:row_idx]) + row_idx * gap
        gw, gh = group_sizes[cid]
        group_layout[cid] = (gx, gy, gw, gh)

    # Build set of all node_ids in canvas for edge filtering
    all_canvas_nodes: set[str] = set()
    for members in communities.values():
        all_canvas_nodes.update(members)

    # Generate group and node canvas entries
    for idx, cid in enumerate(sorted_cids):
        members = communities[cid]
        community_name = (
            community_labels.get(cid, f"Community {cid}")
            if community_labels and cid is not None
            else f"Community {cid}"
        )
        gx, gy, gw, gh = group_layout[cid]
        canvas_color = CANVAS_COLORS[idx % len(CANVAS_COLORS)]

        # Group node
        canvas_nodes.append({
            "id": f"g{cid}",
            "type": "group",
            "label": community_name,
            "x": gx,
            "y": gy,
            "width": gw,
            "height": gh,
            "color": canvas_color,
        })

        # Node cards inside the group - laid out in the same ceil(sqrt(n))-column
        # grid the box was sized for (group_cols[cid]), so cards fill the box.
        inner_cols = group_cols[cid]
        # Same dangling-member guard as the sizing loop and to_obsidian (#1236):
        # a community id absent from G / node_filenames would KeyError the sort.
        members = [m for m in members if G.contains_node(m) and m in node_filenames]
        sorted_members = sorted(
            members, key=lambda n: str(node_attributes(G, n).get("label", n))
        )
        for m_idx, node_id in enumerate(sorted_members):
            col = m_idx % inner_cols
            row = m_idx // inner_cols
            nx_x = gx + 20 + col * (180 + 20)
            nx_y = gy + 80 + row * (60 + 20)
            fallback_name = safe_name(
                str(node_attributes(G, node_id).get("label", node_id))
            )
            fname = node_filenames.get(node_id, fallback_name)
            canvas_nodes.append({
                "id": f"n_{_portable_identity(node_id)}",
                "type": "file",
                "file": f"{fname}.md",
                "x": nx_x,
                "y": nx_y,
                "width": 180,
                "height": 60,
            })

    # Generate edges - only between nodes both in canvas, cap at 200 highest-weight
    all_edges_weighted: list[tuple[float, str, str, str]] = []
    for u, v, edata, _ in _edge_rows(G):
        if u in all_canvas_nodes and v in all_canvas_nodes:
            weight = edata.get("weight", 1.0)
            relation = edata.get("relation", "")
            conf = edata.get("confidence", "EXTRACTED")
            label = f"{relation} [{conf}]" if relation else f"[{conf}]"
            all_edges_weighted.append((weight, u, v, label))

    all_edges_weighted.sort(key=lambda x: -x[0])
    for weight, u, v, label in all_edges_weighted[:200]:
        canvas_edges.append({
            "id": f"e_{_portable_identity(u)}_{_portable_identity(v)}",
            "fromNode": f"n_{_portable_identity(u)}",
            "toNode": f"n_{_portable_identity(v)}",
            "label": label,
        })

    canvas_data = {"nodes": canvas_nodes, "edges": canvas_edges}
    Path(output_path).write_text(json.dumps(canvas_data, indent=2), encoding="utf-8")  # nosec


def to_graphml(
    G: Any,
    communities: dict[int, list[str]],
    output_path: str,
) -> None:
    """Export graph as GraphML - opens in Gephi, yEd, and any GraphML-compatible tool.

    Community IDs are written as a node attribute so Gephi can colour by community.
    Edge confidence (EXTRACTED/INFERRED/AMBIGUOUS) is preserved as an edge attribute.
    """
    import xml.etree.ElementTree as ET

    node_community = _node_community_map(communities)
    root = ET.Element("graphml", xmlns="http://graphml.graphdrawing.org/xmlns")
    nodes = [
        (
            node.id,
            {
                **{k: v for k, v in graphify_attributes(node.attributes).items() if not k.startswith("_")},
                "community": node_community.get(node.id, -1),
            },
        )
        for node in G.nodes()
    ]
    edges = [
        (
            edge.source,
            edge.target,
            {k: v for k, v in edge_attributes(edge).items() if not k.startswith("_")},
        )
        for edge in G.edges()
    ]
    keys = sorted(
        {key for _, values in nodes for key in values}
        | {key for _, _, values in edges for key in values}
    )
    for key in keys:
        ET.SubElement(root, "key", attrib={
            "id": str(key), "for": "all", "attr.name": str(key), "attr.type": "string"
        })
    graph_element = ET.SubElement(
        root, "graph", edgedefault="directed" if G.directed else "undirected"
    )
    for node_id, values in nodes:
        element = ET.SubElement(graph_element, "node", id=_portable_identity(node_id))
        for key, value in sorted(values.items()):
            data = ET.SubElement(element, "data", key=str(key))
            data.text = value if isinstance(value, str) else json.dumps(value, default=str, sort_keys=True)
    for index, (source, target, values) in enumerate(edges):
        element = ET.SubElement(
            graph_element,
            "edge",
            id=f"e{index}",
            source=_portable_identity(source),
            target=_portable_identity(target),
        )
        for key, value in sorted(values.items()):
            data = ET.SubElement(element, "data", key=str(key))
            data.text = value if isinstance(value, str) else json.dumps(value, default=str, sort_keys=True)
    out = Path(output_path)
    tmp = out.with_name(out.name + ".tmp")
    try:
        ET.ElementTree(root).write(tmp, encoding="utf-8", xml_declaration=True)
        os.replace(tmp, out)
    finally:
        tmp.unlink(missing_ok=True)


def to_svg(
    G: Any,
    communities: dict[int, list[str]],
    output_path: str,
    community_labels: dict[int, str] | None = None,
    figsize: tuple[int, int] = (20, 14),
) -> None:
    """Export graph as an SVG file using matplotlib + spring layout.

    Lightweight and embeddable - works in Obsidian notes, Notion, GitHub READMEs,
    and any markdown renderer. No JavaScript required.

    Node size scales with degree. Community colors match the HTML output.
    """
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import matplotlib.patches as mpatches
    except ImportError as e:
        raise ImportError("matplotlib not installed. Run: pip install matplotlib") from e

    node_community = _node_community_map(communities)

    fig, ax = plt.subplots(figsize=figsize, facecolor="#1a1a2e")
    ax.set_facecolor("#1a1a2e")
    ax.axis("off")

    from helixdb.graph import LayoutOptions

    pos = {
        point.node_id: (point.x, point.y)
        for point in G.spring_layout(LayoutOptions(
            seed=42, k=2.0 / (G.node_count ** 0.5 + 1)
        ))
    }
    degree = {row.node_id: int(row.degree) for row in G.degrees()}
    max_deg = max(degree.values(), default=1) or 1

    node_ids = [node.id for node in G.nodes()]
    node_colors = [COMMUNITY_COLORS[node_community.get(n, 0) % len(COMMUNITY_COLORS)] for n in node_ids]
    node_sizes = [300 + 1200 * (degree.get(n, 1) / max_deg) for n in node_ids]

    # Draw edges - dashed for non-EXTRACTED
    for u, v, data, _ in _edge_rows(G):
        conf = data.get("confidence", "EXTRACTED")
        style = "solid" if conf == "EXTRACTED" else "dashed"
        alpha = 0.6 if conf == "EXTRACTED" else 0.3
        x0, y0 = pos[u]
        x1, y1 = pos[v]
        ax.plot([x0, x1], [y0, y1], color="#aaaaaa", linewidth=0.8,
                linestyle=style, alpha=alpha, zorder=1)

    ax.scatter(
        [pos[node][0] for node in node_ids],
        [pos[node][1] for node in node_ids],
        c=node_colors,
        s=node_sizes,
        alpha=0.9,
        zorder=2,
    )
    for node in node_ids:
        ax.text(
            pos[node][0],
            pos[node][1],
            str(node_attributes(G, node).get("label", node)),
            fontsize=7,
            color="white",
            ha="center",
            va="center",
            zorder=3,
        )

    # Legend
    if community_labels:
        patches = [
            mpatches.Patch(
                color=COMMUNITY_COLORS[cid % len(COMMUNITY_COLORS)],
                label=f"{label} ({len(communities.get(cid, []))})",
            )
            for cid, label in sorted(community_labels.items())
        ]
        ax.legend(handles=patches, loc="upper left", framealpha=0.7,
                  facecolor="#2a2a4e", labelcolor="white", fontsize=8)

    plt.tight_layout()
    plt.savefig(output_path, format="svg", bbox_inches="tight",
                facecolor=fig.get_facecolor())
    plt.close(fig)
