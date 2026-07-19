"""Cross-project aggregation streamed directly between embedded Helix stores."""

from __future__ import annotations

import copy
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from .helix.persistence import DEFAULT_GLOBAL_STORE, HelixEmbeddedStore
from .helix.state import new_state


def _project_store(path: str | Path) -> Path:
    candidate = Path(path).expanduser().resolve()
    if candidate.name == "graph.helix":
        store = candidate
    elif (candidate / "graph.helix").is_dir():
        store = candidate / "graph.helix"
    else:
        store = candidate / "graphify-out" / "graph.helix"
    if not store.is_dir():
        if candidate.suffix.lower() == ".json" or candidate.is_file():
            raise ValueError(
                "legacy JSON graphs are obsolete; rebuild the project and pass "
                "its graph.helix store"
            )
        raise FileNotFoundError(f"Helix store not found: {store}")
    return store


def _state() -> dict:
    if not DEFAULT_GLOBAL_STORE.is_dir():
        return new_state(build={"kind": "global-aggregate"})
    with HelixEmbeddedStore(DEFAULT_GLOBAL_STORE, read_only=True) as store:
        return copy.deepcopy(store.read_state())


def _repos(state: dict) -> dict:
    global_state = state.setdefault("global", {})
    return global_state.setdefault("repos", {})


def _source_records(state: dict) -> list[tuple[Path, str, str]]:
    records: list[tuple[Path, str, str]] = []
    for repo, value in sorted(_repos(state).items()):
        if not isinstance(value, dict):
            raise RuntimeError(f"global repository record {repo!r} is invalid")
        source = Path(str(value.get("source_path", ""))).expanduser().resolve()
        generation = value.get("source_generation")
        if not source.is_dir() or not isinstance(generation, str):
            raise RuntimeError(
                f"global repository {repo!r} source is unavailable; re-add it"
            )
        records.append((source, generation, repo))
    return records


def _save_state(state: dict, *, retain_rollback: bool) -> None:
    with HelixEmbeddedStore(
        DEFAULT_GLOBAL_STORE, retain_rollback=retain_rollback
    ) as store:
        store.save_aggregate_sources(_source_records(state), state)


def global_add(
    source_path: Path,
    repo_tag: str,
    *,
    retain_rollback: bool = False,
) -> dict:
    """Add or replace a project by rebuilding the aggregate through native pages."""
    source = _project_store(source_path)
    with HelixEmbeddedStore(source, read_only=True) as store:
        source_generation = store.active_generation
        metadata = store._metadata(source_generation)
    state = _state()
    repos = _repos(state)
    existing = repos.get(repo_tag, {})
    if (
        existing.get("source_path") == str(source)
        and existing.get("source_generation") == source_generation
    ):
        return {
            "repo_tag": repo_tag,
            "nodes_added": 0,
            "nodes_removed": 0,
            "skipped": True,
        }
    removed = int(existing.get("node_count", 0)) if isinstance(existing, dict) else 0
    repos[repo_tag] = {
        "added_at": datetime.now(timezone.utc).isoformat(),
        "source_path": str(source),
        "source_generation": source_generation,
        "node_count": int(metadata.get("node_count", 0)),
        "edge_count": int(metadata.get("edge_count", 0)),
    }
    _save_state(state, retain_rollback=retain_rollback)
    return {
        "repo_tag": repo_tag,
        "nodes_added": int(metadata.get("node_count", 0)),
        "nodes_removed": removed,
        "skipped": False,
    }


def global_remove(repo_tag: str, *, retain_rollback: bool = False) -> int:
    if not DEFAULT_GLOBAL_STORE.is_dir():
        raise KeyError(f"repo '{repo_tag}' not in global graph")
    state = _state()
    repos = _repos(state)
    if repo_tag not in repos:
        raise KeyError(f"repo '{repo_tag}' not in global graph")
    record = repos.pop(repo_tag)
    removed = int(record.get("node_count", 0)) if isinstance(record, dict) else 0
    _save_state(state, retain_rollback=retain_rollback)
    return removed


def global_list() -> dict:
    if not DEFAULT_GLOBAL_STORE.is_dir():
        return {}
    return dict(_repos(_state()))


def global_path() -> Path:
    return DEFAULT_GLOBAL_STORE


def aggregate(
    project_stores: Iterable[str | Path],
    output: str | Path = DEFAULT_GLOBAL_STORE,
    *,
    retain_rollback: bool = False,
) -> Path:
    """Create an aggregate through bounded public Helix reads and writes."""
    sources: list[tuple[Path, str, str]] = []
    state = new_state(build={"kind": "global-aggregate"})
    repos = _repos(state)
    tags: dict[str, int] = {}
    for raw_path in project_stores:
        path = _project_store(raw_path)
        base = path.parent.parent.name or "project"
        tags[base] = tags.get(base, 0) + 1
        repo = base if tags[base] == 1 else f"{base}-{tags[base]}"
        with HelixEmbeddedStore(path, read_only=True) as store:
            generation = store.active_generation
            metadata = store._metadata(generation)
        repos[repo] = {
            "source_path": str(path),
            "source_generation": generation,
            "node_count": int(metadata.get("node_count", 0)),
            "edge_count": int(metadata.get("edge_count", 0)),
        }
        sources.append((path, generation, repo))
    destination = Path(output).expanduser().resolve()
    with HelixEmbeddedStore(
        destination, retain_rollback=retain_rollback
    ) as store:
        store.save_aggregate_sources(sources, state)
    return destination


__all__ = ["aggregate", "global_add", "global_list", "global_path", "global_remove"]
