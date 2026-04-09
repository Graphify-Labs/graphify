# Enrich corpus subfolders with semantic INDEX.md files derived from the knowledge graph
from __future__ import annotations
from pathlib import Path
import datetime
import networkx as nx


def _group_nodes_by_folder(G: nx.Graph, corpus_path: Path) -> dict[Path, list[str]]:
    """Group node IDs by their immediate parent folder, excluding graphify-out/.

    Folder keys are always relative to corpus_path. Absolute source_file paths
    that fall under corpus_path are made relative; others are used as-is.
    """
    corpus_path = Path(corpus_path).resolve()
    groups: dict[Path, list[str]] = {}
    for node_id, data in G.nodes(data=True):
        src = data.get("source_file", "")
        if not src:
            continue
        p = Path(src)
        if not p.parts:
            continue
        # Normalise absolute paths to corpus-relative
        if p.is_absolute():
            try:
                p = p.relative_to(corpus_path)
            except ValueError:
                pass  # outside corpus — use as-is
        folder = p.parent
        if not folder.parts:
            continue
        if "graphify-out" in folder.parts:
            continue
        groups.setdefault(folder, []).append(node_id)
    return groups


def _cross_folder_edges(
    folder: Path,
    node_ids: list[str],
    G: nx.Graph,
) -> list[dict]:
    """Return edges from nodes in `folder` that cross into other folders.

    Each unique (source, target) pair is emitted at most once.
    """
    node_set = set(node_ids)
    # frozenset dedup is correct for nx.Graph (undirected); would need revision for DiGraph
    seen: set[frozenset] = set()
    results = []
    for nid in node_ids:
        for neighbor in G.neighbors(nid):
            if neighbor in node_set:
                continue
            pair = frozenset((nid, neighbor))
            if pair in seen:
                continue
            seen.add(pair)
            n_src = G.nodes[neighbor].get("source_file", "")
            if not n_src:
                continue
            target_folder = Path(n_src).parent
            if not target_folder.parts:
                continue
            edata = G.edges[nid, neighbor]
            results.append({
                "source_node": nid,
                "target_node": neighbor,
                "target_folder": target_folder,
                "relation": edata.get("relation", ""),
                "confidence": edata.get("confidence", "EXTRACTED"),
            })
    return results


def _write_subfolder_index(
    folder: Path,
    data: dict,
    dry_run: bool = False,
) -> str | None:
    """Write enriched INDEX.md for a subfolder.

    Returns the content string when dry_run=True (no file written).
    Returns None after writing the file when dry_run=False.
    """
    folder_path = Path(data["folder"])
    now = datetime.date.today().isoformat()
    nodes = data["nodes"]
    cross_edges = data.get("cross_edges", [])
    summary = data.get("summary", "")

    docs = sorted({Path(n["source_file"]).name for n in nodes if n.get("source_file")})
    entities = [n["label"] for n in nodes if n.get("label")]
    # Quote each entity so the YAML list is valid when parsed programmatically
    entity_list = ", ".join(f'"{e}"' for e in entities[:10])

    connected: dict[str, str] = {}
    for e in cross_edges:
        tf = str(e["target_folder"])
        if tf not in connected:
            connected[tf] = e["relation"]

    lines = [
        "---",
        f'folder: "{folder_path}"',
        f'entities: [{entity_list}]',
        f'last_enriched: "{now}"',
        "---",
        "",
        f"# {folder_path.name.replace('-', ' ').replace('_', ' ').title()}",
        "",
    ]

    if summary:
        lines += ["## What's here", "", summary, ""]

    lines += ["## Documents", ""]
    for doc in docs:
        lines.append(f"- {doc}")
    lines.append("")

    if entities:
        lines += ["## Key entities", ""]
        for entity in entities[:20]:
            lines.append(f"- {entity}")
        lines.append("")

    if connected:
        lines += ["## Connected folders", ""]
        for tf, relation in connected.items():
            lines.append(f"- [[{tf}]] — `{relation}`")
        lines.append("")

    content = "\n".join(lines)

    if dry_run:
        return content

    index_path = folder / "INDEX.md"
    index_path.write_text(content, encoding="utf-8")
    return None


def _write_master_index(
    corpus_path: Path,
    folder_summaries: dict[Path, dict],
    dry_run: bool = False,
) -> str | None:
    """Write master INDEX.md at corpus root.

    Returns the content string when dry_run=True (no file written).
    Returns None after writing the file when dry_run=False.
    """
    corpus_path = Path(corpus_path)
    now = datetime.date.today().isoformat()

    lines = [
        "---",
        f'last_enriched: "{now}"',
        f"total_folders: {len(folder_summaries)}",
        "---",
        "",
        "# Master Index",
        "",
        "## Folder map",
        "",
        "| Folder | What's there | Key entities |",
        "| --- | --- | --- |",
    ]

    for folder, data in sorted(folder_summaries.items()):
        summary = data.get("summary", "").replace("|", r"\|")
        entities = ", ".join(e.replace("|", r"\|") for e in data.get("entities", [])[:5])
        lines.append(f"| {folder} | {summary} | {entities} |")

    lines += ["", "## Entity → Folder map", ""]

    entity_map: dict[str, list[str]] = {}
    for folder, data in folder_summaries.items():
        for entity in data.get("entities", []):
            entity_map.setdefault(entity, []).append(str(folder))

    lines += ["| Entity | Folder(s) |", "| --- | --- |"]
    for entity, folders in sorted(entity_map.items()):
        safe_entity = entity.replace("|", r"\|")
        lines.append(f"| {safe_entity} | {', '.join(folders)} |")

    lines.append("")
    content = "\n".join(lines)

    if dry_run:
        return content

    index_path = Path(corpus_path) / "INDEX.md"
    index_path.write_text(content, encoding="utf-8")
    return None


def _generate_summary(
    folder: Path,
    entities: list[str],
    _mock: bool = False,
) -> str:
    """Generate a 2-3 sentence summary for a folder using Claude.

    Falls back to a plain entity list if no API key is available.
    Pass _mock=True in tests to skip API calls.
    """
    if _mock:
        name = Path(folder).name.replace("-", " ").replace("_", " ")
        return f"{name.title()} folder containing: {', '.join(entities[:5])}."

    try:
        import anthropic
        client = anthropic.Anthropic()
        entity_str = ", ".join(entities[:20])
        prompt = (
            f"Folder: {folder}\n"
            f"Entities found: {entity_str}\n\n"
            f"Write a 2-3 sentence plain-English summary of what this folder contains "
            f"and what it is for. Be specific and factual. No bullet points."
        )
        message = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=150,
            messages=[{"role": "user", "content": prompt}],
        )
        return message.content[0].text.strip()
    except Exception:
        # No API key or network error — fall back to entity list
        name = Path(folder).name.replace("-", " ").replace("_", " ")
        return f"{name.title()} folder containing: {', '.join(entities[:5])}."


def _patch_index(
    existing: str,
    summary: str,
    entities: list[str],
    cross_refs: list[dict],
) -> str:
    """Patch semantic sections in an existing INDEX.md stub.

    Replaces: Summary body, Key Entities section (creates if missing), Cross-References body.
    Preserves: Type, Owner, Status, Key Files, Subfolders, Open Items.
    Adds: last_enriched line after Last Updated.
    """
    now = datetime.date.today().isoformat()
    lines = existing.splitlines()
    out = []
    i = 0
    last_enriched_added = False
    key_entities_written = False

    while i < len(lines):
        line = lines[i]

        # Inject last_enriched after Last Updated
        if line.startswith("Last Updated:") and not last_enriched_added:
            out.append(line)
            # Remove existing last_enriched if already there
            if i + 1 < len(lines) and lines[i + 1].startswith("last_enriched:"):
                i += 1
            out.append(f"last_enriched: {now}")
            last_enriched_added = True
            i += 1
            continue

        # Replace Summary section body
        if line.strip() == "## Summary":
            out.append(line)
            out.append("")
            out.append(summary)
            out.append("")
            i += 1
            # Skip old summary lines until next ##
            while i < len(lines) and not lines[i].startswith("## "):
                i += 1
            continue

        # Replace Cross-References section body
        if line.strip() == "## Cross-References":
            out.append(line)
            i += 1
            # Skip old cross-ref lines until next ##
            while i < len(lines) and not lines[i].startswith("## "):
                i += 1
            if cross_refs:
                for ref in cross_refs:
                    conf = ref.get("confidence", "INFERRED")
                    score = ref.get("confidence_score", "")
                    score_str = f" {score:.2f}" if isinstance(score, float) else ""
                    rel = ref.get("relation", "")
                    out.append(f"- [[{ref['target']}]] — `{rel}` [{conf}{score_str}]")
            else:
                out.append("- <!-- [[RelatedFolder/INDEX]] — reason -->")
            out.append("")
            continue

        # Drop existing Key Entities section (will re-inject at the right place)
        if line.strip() == "## Key Entities":
            i += 1
            while i < len(lines) and not lines[i].startswith("## "):
                i += 1
            continue

        # Inject Key Entities before Subfolders, Cross-References, or Open Items
        if (
            entities
            and not key_entities_written
            and line.startswith("## ")
            and line.strip() in ("## Subfolders", "## Cross-References", "## Open Items")
        ):
            out.append("## Key Entities")
            out.append("")
            for entity in entities[:20]:
                out.append(f"- {entity}")
            out.append("")
            key_entities_written = True

        out.append(line)
        i += 1

    # Append Key Entities at end if no suitable injection point was found
    if entities and not key_entities_written:
        out.append("")
        out.append("## Key Entities")
        out.append("")
        for entity in entities[:20]:
            out.append(f"- {entity}")

    return "\n".join(out)


def enrich(
    corpus_path: Path,
    graph_json_path: Path | None = None,
    index_dir: Path | None = None,
    watch: bool = False,
    dry_run: bool = False,
    master_only: bool = False,
) -> None:
    """Read graph.json and write enriched INDEX.md files.

    If index_dir is provided, indexes are written there instead of into the corpus.
    When index_dir contains an existing INDEX.md stub, it is patched rather than overwritten.
    """
    import json
    from graphify.build import build_from_json

    corpus_path = Path(corpus_path)
    index_root = Path(index_dir) if index_dir else corpus_path

    if graph_json_path is None:
        graph_json_path = corpus_path / "graphify-out" / "graph.json"

    if not Path(graph_json_path).exists():
        raise FileNotFoundError(f"graph.json not found at {graph_json_path}. Run graphify first.")

    data = json.loads(Path(graph_json_path).read_text())
    G = build_from_json(data)

    groups = _group_nodes_by_folder(G, corpus_path)

    folder_summaries: dict[Path, dict] = {}

    for folder, node_ids in groups.items():
        nodes = [dict(id=nid, **G.nodes[nid]) for nid in node_ids]
        cross_edges = _cross_folder_edges(folder, node_ids, G)
        entities = [n.get("label", "") for n in nodes if n.get("label")]
        summary = _generate_summary(folder, entities)

        folder_data = {
            "folder": folder,
            "node_ids": node_ids,
            "nodes": nodes,
            "cross_edges": cross_edges,
            "summary": summary,
        }
        folder_summaries[folder] = {"summary": summary, "entities": entities}

        if not master_only:
            abs_folder = index_root / folder
            if not dry_run:
                abs_folder.mkdir(parents=True, exist_ok=True)
            existing_index = abs_folder / "INDEX.md"
            if existing_index.exists() and not dry_run:
                existing = existing_index.read_text(encoding="utf-8")
                content = _patch_index(existing, summary=summary, entities=entities, cross_refs=cross_edges)
                existing_index.write_text(content, encoding="utf-8")
            else:
                _write_subfolder_index(abs_folder, folder_data, dry_run=dry_run)

    _write_master_index(index_root, folder_summaries, dry_run=dry_run)

    if watch:
        _watch_and_enrich(corpus_path, Path(graph_json_path), master_only=master_only, index_dir=index_root)


def _watch_and_enrich(
    corpus_path: Path,
    graph_json_path: Path,
    master_only: bool = False,
    index_dir: Path | None = None,
    _enrich_fn=None,
    _stop_event=None,
    _poll_interval: float = 5.0,
) -> None:
    """Poll graph.json mtime and re-run enrichment on change.

    Runs until KeyboardInterrupt or _stop_event is set (for testing).
    _enrich_fn and _stop_event are injection points for tests.
    """
    import time
    import threading

    if _enrich_fn is None:
        _enrich_fn = lambda cp, gp, mo: enrich(cp, gp, index_dir=index_dir, watch=False, master_only=mo)

    last_mtime = Path(graph_json_path).stat().st_mtime
    print(f"[graphify enrich] watching {graph_json_path} (poll every {_poll_interval}s) ...")

    try:
        while True:
            if _stop_event is not None and _stop_event.is_set():
                break
            time.sleep(_poll_interval)
            try:
                mtime = Path(graph_json_path).stat().st_mtime
            except OSError:
                continue
            if mtime != last_mtime:
                last_mtime = mtime
                print("[graphify enrich] graph.json updated — re-enriching ...")
                _enrich_fn(corpus_path, graph_json_path, master_only)
                print("[graphify enrich] done.")
    except KeyboardInterrupt:
        print("[graphify enrich] stopped.")
