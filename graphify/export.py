# write graph to HTML, JSON, SVG, GraphML, Obsidian vault, and Neo4j Cypher
from __future__ import annotations
import hashlib
import html as _html
import json
import math
import os
import re
import shutil
import sys
from collections import Counter
from datetime import date
from pathlib import Path
import networkx as nx
from networkx.readwrite import json_graph
from graphify.security import sanitize_label
from graphify.analyze import _node_community_map
from graphify.build import edge_data

from graphify.exporters.graphdb import push_to_falkordb, push_to_neo4j  # noqa: E402,F401


# Artifacts worth preserving across rebuilds (non-regenerable without LLM or curation).
_BACKUP_ARTIFACTS = [
    "graph.json",
    "GRAPH_REPORT.md",
    ".graphify_labels.json",
    ".graphify_analysis.json",
    "manifest.json",
    ".graphify_semantic_marker",
    "cost.json",
]


def backup_if_protected(out_dir: Path) -> "Path | None":
    """Snapshot graph artifacts to a dated subfolder before an overwrite.

    Triggers when graph.json exists AND either:
    - .graphify_semantic_marker is present (graph cost real LLM tokens), or
    - .graphify_labels.json contains at least one non-default community label
      (graph has been curated by a human or skill).

    Returns the backup folder path, or None if no backup was taken.
    Never raises — backup failure prints a warning but never blocks the write.
    Set GRAPHIFY_NO_BACKUP=1 to disable.
    """
    if os.environ.get("GRAPHIFY_NO_BACKUP"):
        return None
    out = Path(out_dir)
    if not (out / "graph.json").exists():
        return None

    is_semantic = (out / ".graphify_semantic_marker").exists()
    is_curated = False
    labels_file = out / ".graphify_labels.json"
    if labels_file.exists():
        try:
            labels = json.loads(labels_file.read_text(encoding="utf-8"))
            is_curated = any(v != f"Community {k}" for k, v in labels.items())
        except Exception:
            pass

    if not is_semantic and not is_curated:
        return None

    reason = "+".join(filter(None, ["semantic" if is_semantic else "", "curated" if is_curated else ""]))
    today = date.today().isoformat()
    backup_dir = out / today
    graph_src = out / "graph.json"

    # Skip re-copying if today's backup already has identical graph.json content.
    # If content differs (graph changed since the last backup today), overwrite
    # the backup in place — one folder per day, always the latest pre-overwrite state.
    if backup_dir.exists() and (backup_dir / "graph.json").exists():
        src_hash = hashlib.sha256(graph_src.read_bytes()).hexdigest()
        bak_hash = hashlib.sha256((backup_dir / "graph.json").read_bytes()).hexdigest()
        if src_hash == bak_hash:
            return backup_dir  # identical content, nothing to do

    try:
        backup_dir.mkdir(parents=True, exist_ok=True)
        copied = 0
        for name in _BACKUP_ARTIFACTS:
            src = out / name
            if src.exists():
                try:
                    shutil.copy2(src, backup_dir / name)
                    copied += 1
                except Exception:
                    pass
        if copied:
            print(f"[graphify] backed up {reason} graph ({copied} files) -> {backup_dir.name}/")
        return backup_dir
    except Exception as exc:
        import sys
        print(f"[graphify] warning: backup failed ({exc}) - continuing with overwrite", file=sys.stderr)
        return None

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


def attach_hyperedges(G: nx.Graph, hyperedges: list) -> None:
    """Store hyperedges in the graph's metadata dict."""
    existing = G.graph.get("hyperedges", [])
    seen_ids = {h["id"] for h in existing}
    for h in hyperedges:
        if h.get("id") and h["id"] not in seen_ids:
            existing.append(h)
            seen_ids.add(h["id"])
    G.graph["hyperedges"] = existing


def _git_head() -> str | None:
    """Return the current git HEAD commit hash, or None if not in a git repo."""
    import subprocess as _sp
    try:
        r = _sp.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, timeout=3)
        return r.stdout.strip() if r.returncode == 0 else None
    except Exception:
        return None


def to_json(G: nx.Graph, communities: dict[int, list[str]], output_path: str, *, force: bool = False, built_at_commit: str | None = None, community_labels: dict[int, str] | None = None) -> bool:
    # Safety check: refuse to silently shrink an existing graph (#479)
    existing_path = Path(output_path)
    if not force and existing_path.exists():
        from graphify.security import check_graph_file_size_cap
        try:
            check_graph_file_size_cap(existing_path)
        except Exception:
            # Existing graph.json trips the size cap; reading it to compare would
            # be the very DoS the cap guards against. Can't verify — let the new
            # graph replace the oversized file.
            oversized = True
        else:
            oversized = False
        if not oversized:
            try:
                raw = existing_path.read_text(encoding="utf-8")
            except Exception:
                raw = ""
            if not raw.strip():
                # Empty/whitespace existing file (e.g. a freshly touched path):
                # no nodes to lose, so any new graph is a growth — proceed.
                existing_n = 0
            else:
                try:
                    existing_data = json.loads(raw)
                    existing_n = len(existing_data.get("nodes", []))
                except Exception as exc:
                    # Non-empty but unparseable existing graph (corrupt or a
                    # mid-write): we cannot verify the new graph is not a silent
                    # shrink. Fail SAFE — refuse rather than overwrite. A
                    # fail-OPEN here (the prior behavior) is the silent data-loss
                    # path #479 exists to prevent: a transiently unreadable
                    # graph.json would let a partial rebuild clobber a good one.
                    import sys as _sys
                    print(
                        f"[graphify] WARNING: existing {existing_path} could not be "
                        f"read to verify the new graph is not smaller ({exc}). "
                        f"Refusing to overwrite; pass force=True to override.",
                        file=_sys.stderr,
                    )
                    return False
            new_n = G.number_of_nodes()
            if new_n < existing_n:
                import sys as _sys
                print(
                    f"[graphify] WARNING: new graph has {new_n} nodes but existing "
                    f"graph.json has {existing_n} (net -{existing_n - new_n}). "
                    f"Refusing to overwrite. Possible causes: missing chunk files from "
                    f"a previous session, or fuzzy dedup collapsed same-named symbols "
                    f"across files during an --update on an already-current graph. "
                    f"Run a full rebuild (/graphify .) to be safe, or pass force=True "
                    f"only if you have verified the reduction is legitimate.",
                    file=_sys.stderr,
                )
                return False

    node_community = _node_community_map(communities)
    _labels: dict[int, str] = {int(k): v for k, v in (community_labels or {}).items()}
    try:
        data = json_graph.node_link_data(G, edges="links")
    except TypeError:
        data = json_graph.node_link_data(G)
    for node in data["nodes"]:
        cid = node_community.get(node["id"])
        node["community"] = cid
        if cid is not None and _labels:
            node["community_name"] = _labels.get(cid, f"Community {cid}")
        node["norm_label"] = _strip_diacritics(node.get("label", "")).lower()
    for link in data["links"]:
        if "confidence_score" not in link:
            conf = link.get("confidence", "EXTRACTED")
            link["confidence_score"] = _CONFIDENCE_SCORE_DEFAULTS.get(conf, 1.0)
        # Restore original edge direction. Undirected NetworkX storage may
        # canonicalize endpoint order, flipping `calls` and other directional
        # edges in graph.json. The build path stashes the true endpoints in
        # _src/_tgt for exactly this purpose (#563).
        true_src = link.pop("_src", None)
        true_tgt = link.pop("_tgt", None)
        if true_src is not None and true_tgt is not None:
            link["source"] = true_src
            link["target"] = true_tgt
    data["hyperedges"] = getattr(G, "graph", {}).get("hyperedges", [])
    commit = built_at_commit if built_at_commit is not None else _git_head()
    if commit:
        data["built_at_commit"] = commit
    with open(output_path, "w", encoding="utf-8") as f:  # nosec
        json.dump(data, f, indent=2)
    return True


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


def to_cypher(G: nx.Graph, output_path: str) -> None:
    lines = ["// Neo4j Cypher import - generated by /graphify", ""]
    for node_id, data in G.nodes(data=True):
        label = _cypher_escape(data.get("label", node_id))
        node_id_esc = _cypher_escape(node_id)
        ftype = _cypher_label(
            (data.get("file_type", "unknown") or "unknown").capitalize(),
            "Entity",
        )
        lines.append(f"MERGE (n:{ftype} {{id: '{node_id_esc}', label: '{label}'}});")
    lines.append("")
    for u, v, data in G.edges(data=True):
        rel = _cypher_label(
            (data.get("relation", "RELATES_TO") or "RELATES_TO").upper(),
            "RELATES_TO",
        )
        conf = _cypher_escape(data.get("confidence", "EXTRACTED"))
        u_esc = _cypher_escape(u)
        v_esc = _cypher_escape(v)
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


def _dedup_node_filenames(G: nx.Graph, safe_name) -> dict[str, str]:
    """Map each node_id to a unique note filename, appending a numeric suffix on
    collision. The collision set is keyed on the lowercased name so two labels
    differing only by case (e.g. "References" vs "references") still get distinct
    filenames - on case-insensitive filesystems (macOS/APFS, Windows/NTFS) they
    would otherwise resolve to one path and silently overwrite each other on disk.
    The suffixed candidate is itself re-checked, so a generated "base_1" never
    silently overwrites a node whose literal label is already "base_1"."""
    node_filenames: dict[str, str] = {}
    used: set[str] = set()
    for node_id, data in G.nodes(data=True):
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
    G: nx.Graph,
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
        for u, v, edata in G.edges(node_id, data=True):
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
    for node_id, data in G.nodes(data=True):
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
            for neighbor in sorted(neighbors, key=lambda n: G.nodes[n].get("label", n)):
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
    for u, v in G.edges():
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
        members = [m for m in all_members if m in G and m in node_filename]
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
        for node_id in sorted(members, key=lambda n: G.nodes[n].get("label", n)):
            data = G.nodes[node_id]
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
            (node_id, G.degree(node_id), _community_reach(node_id))
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
    G: nx.Graph,
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
    if not communities and G.number_of_nodes() > 0:
        communities = {0: [str(n) for n in G.nodes()]}

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
        members = [m for m in communities[cid] if m in G and m in node_filenames]
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
        members = [m for m in members if m in G and m in node_filenames]
        sorted_members = sorted(members, key=lambda n: G.nodes[n].get("label", n))
        for m_idx, node_id in enumerate(sorted_members):
            col = m_idx % inner_cols
            row = m_idx // inner_cols
            nx_x = gx + 20 + col * (180 + 20)
            nx_y = gy + 80 + row * (60 + 20)
            fname = node_filenames.get(node_id, safe_name(G.nodes[node_id].get("label", node_id)))
            canvas_nodes.append({
                "id": f"n_{node_id}",
                "type": "file",
                "file": f"{fname}.md",
                "x": nx_x,
                "y": nx_y,
                "width": 180,
                "height": 60,
            })

    # Generate edges - only between nodes both in canvas, cap at 200 highest-weight
    all_edges_weighted: list[tuple[float, str, str, str]] = []
    for u, v, edata in G.edges(data=True):
        if u in all_canvas_nodes and v in all_canvas_nodes:
            weight = edata.get("weight", 1.0)
            relation = edata.get("relation", "")
            conf = edata.get("confidence", "EXTRACTED")
            label = f"{relation} [{conf}]" if relation else f"[{conf}]"
            all_edges_weighted.append((weight, u, v, label))

    all_edges_weighted.sort(key=lambda x: -x[0])
    for weight, u, v, label in all_edges_weighted[:200]:
        canvas_edges.append({
            "id": f"e_{u}_{v}",
            "fromNode": f"n_{u}",
            "toNode": f"n_{v}",
            "label": label,
        })

    canvas_data = {"nodes": canvas_nodes, "edges": canvas_edges}
    Path(output_path).write_text(json.dumps(canvas_data, indent=2), encoding="utf-8")  # nosec


def to_graphml(
    G: nx.Graph,
    communities: dict[int, list[str]],
    output_path: str,
) -> None:
    """Export graph as GraphML - opens in Gephi, yEd, and any GraphML-compatible tool.

    Community IDs are written as a node attribute so Gephi can colour by community.
    Edge confidence (EXTRACTED/INFERRED/AMBIGUOUS) is preserved as an edge attribute.
    """
    H = G.copy()
    node_community = _node_community_map(communities)
    for node_id in H.nodes():
        H.nodes[node_id]["community"] = node_community.get(node_id, -1)
    # Drop internal markers (e.g. the AST-provenance "_origin" tag, #1116, and
    # the "_src"/"_tgt" direction markers) — they are persistence/runtime details,
    # not graph data, and should not leak into the exported file.
    for _, attrs in H.nodes(data=True):
        for k in [k for k in attrs if k.startswith("_")]:
            del attrs[k]
    for _, _, attrs in H.edges(data=True):
        for k in [k for k in attrs if k.startswith("_")]:
            del attrs[k]
    # nx.write_graphml only accepts scalar attribute values: None raises, and a
    # dict/list value (e.g. a per-node `metadata` dict, or the graph-level
    # `hyperedges` list set by attach_hyperedges()) raises
    # "GraphML does not support type <class 'dict'/'list'> as data values" (#1831).
    # Coerce None -> "" and non-scalars -> a JSON string, across all three scopes.
    def _graphml_safe(val):
        if val is None:
            return ""
        if isinstance(val, bool) or isinstance(val, (int, float, str)):
            return val  # GraphML-native scalars pass through unchanged
        try:
            return json.dumps(val, default=str, sort_keys=True)
        except (TypeError, ValueError):
            return str(val)

    for key, val in list(H.graph.items()):
        H.graph[key] = _graphml_safe(val)
    for node_id in H.nodes():
        for key, val in list(H.nodes[node_id].items()):
            H.nodes[node_id][key] = _graphml_safe(val)
    for u, v in H.edges():
        for key, val in list(H.edges[u, v].items()):
            H.edges[u, v][key] = _graphml_safe(val)

    # Write atomically: a mid-serialization error otherwise leaves a 0-byte
    # .graphml on disk that downstream tooling mistakes for a completed export
    # (#1831). Write to a sibling temp file, then replace on success.
    out = Path(output_path)
    tmp = out.with_name(out.name + ".tmp")
    try:
        nx.write_graphml(H, str(tmp))
        os.replace(str(tmp), str(out))
    finally:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass


def to_svg(
    G: nx.Graph,
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

    pos = nx.spring_layout(G, seed=42, k=2.0 / (G.number_of_nodes() ** 0.5 + 1))

    degree = dict(G.degree())
    max_deg = max(degree.values(), default=1) or 1

    node_colors = [COMMUNITY_COLORS[node_community.get(n, 0) % len(COMMUNITY_COLORS)] for n in G.nodes()]
    node_sizes = [300 + 1200 * (degree.get(n, 1) / max_deg) for n in G.nodes()]

    # Draw edges - dashed for non-EXTRACTED
    for u, v, data in G.edges(data=True):
        conf = data.get("confidence", "EXTRACTED")
        style = "solid" if conf == "EXTRACTED" else "dashed"
        alpha = 0.6 if conf == "EXTRACTED" else 0.3
        x0, y0 = pos[u]
        x1, y1 = pos[v]
        ax.plot([x0, x1], [y0, y1], color="#aaaaaa", linewidth=0.8,
                linestyle=style, alpha=alpha, zorder=1)

    nx.draw_networkx_nodes(G, pos, ax=ax, node_color=node_colors,
                           node_size=node_sizes, alpha=0.9)
    nx.draw_networkx_labels(G, pos, ax=ax,
                            labels={n: G.nodes[n].get("label", n) for n in G.nodes()},
                            font_size=7, font_color="white")

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
