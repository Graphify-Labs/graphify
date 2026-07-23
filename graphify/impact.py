"""Pull-request/file impact analysis over an active Helix generation."""

from __future__ import annotations

from pathlib import Path
import subprocess
from typing import Iterable

from .helix.model import LoadedGraph, node_attributes


def changed_files(base: str, *, cwd: str | Path = ".") -> list[str]:
    """Return files changed from ``base`` to HEAD without invoking a shell."""
    result = subprocess.run(
        ["git", "diff", "--name-only", "--diff-filter=ACMRD", f"{base}...HEAD"],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    )
    return [line for line in result.stdout.splitlines() if line]


def analyze_impact(
    loaded: LoadedGraph,
    files: Iterable[str | Path],
    *,
    depth: int = 2,
) -> dict:
    """Return nodes, dependencies, and communities affected by source files."""
    graph = loaded.graph
    requested = {Path(file).as_posix() for file in files}
    requested_names = {Path(file).name for file in requested}
    if loaded.query is None:
        raise RuntimeError("impact analysis requires the native Helix query interface")
    candidates = loaded.query.candidate_ids(sorted(requested | requested_names))
    seeds = {
        node_id
        for node_id in candidates
        if (attrs := node_attributes(graph, node_id)) is not None
        if (source := attrs.get("source_file"))
        and (
            Path(str(source)).as_posix() in requested
            or Path(str(source)).name in requested_names
            or any(Path(str(source)).as_posix().endswith(f"/{item}") for item in requested)
        )
    }
    impacted = set(seeds)
    traversed: list[tuple] = []
    if seeds:
        from helixdb.graph import TraversalOptions

        result = graph.traverse(TraversalOptions(
            seeds=tuple(sorted(seeds, key=repr)),
            max_depth=max(0, depth),
            direction="both",
        ))
        impacted = {visit.node_id for visit in result.visits}
        traversed = [(edge.source, edge.target) for edge in result.discovery_edges]

    membership = {
        member: record.get("id")
        for record in loaded.state.get("communities", [])
        if isinstance(record, dict)
        for member in record.get("members", [])
    }
    communities = sorted({
        community_id
        for node in impacted
        if isinstance((community_id := membership.get(node)), int)
    })
    return {
        "changed_files": sorted(requested),
        "seed_nodes": sorted(seeds, key=str),
        "impacted_nodes": sorted(impacted, key=str),
        "impacted_communities": communities,
        "traversed_edges": [list(edge) for edge in traversed],
        "depth": depth,
    }


__all__ = ["analyze_impact", "changed_files"]
