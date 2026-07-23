"""Atomic operations over an existing active Helix generation."""

from __future__ import annotations

import copy
from pathlib import Path

from .analyze import god_nodes, surprising_connections, suggest_questions
from .cluster import cluster, remap_communities_to_previous, score_all
from .helix.persistence import DEFAULT_PROJECT_STORE, HelixEmbeddedStore
from .helix.state import (
    communities_from_state,
    community_records,
    community_summaries,
    labels_from_state,
)


def recluster(store_path: str | Path = DEFAULT_PROJECT_STORE) -> dict[int, list]:
    """Replace community records and node membership in one generation."""
    with HelixEmbeddedStore(store_path) as store:
        loaded = store.load()
        graph = loaded.graph
        previous_state = dict(loaded.state)
        state = copy.deepcopy(previous_state)
        communities = cluster(graph)
        previous_membership = {
            member: community_id
            for community_id, members in communities_from_state(state).items()
            for member in members
        }
        if previous_membership:
            communities = remap_communities_to_previous(
                communities, previous_membership
            )
        cohesion = score_all(graph, communities)
        previous_labels = labels_from_state(state)
        labels = {
            community_id: previous_labels.get(
                community_id, f"Community {community_id}"
            )
            for community_id in communities
        }
        state["communities"] = community_records(
            communities,
            labels=labels,
            cohesion=cohesion,
            naming_source="preserved" if previous_labels else "generated",
        )
        store.replace_state(
            state, previous_state=previous_state, snapshot=loaded
        )
    return communities


def reanalyze(store_path: str | Path = DEFAULT_PROJECT_STORE) -> dict:
    """Replace analysis records while preserving topology and other state."""
    with HelixEmbeddedStore(store_path) as store:
        loaded = store.load()
        graph = loaded.graph
        previous_state = dict(loaded.state)
        state = copy.deepcopy(previous_state)
        communities = communities_from_state(state)
        labels = labels_from_state(state)
        analysis = state.get("analysis", {})
        report_inputs = analysis.get("report_inputs", {}) if isinstance(analysis, dict) else {}
        refreshed = {
            "god_nodes": god_nodes(graph),
            "surprises": surprising_connections(graph, communities),
            "suggested_questions": suggest_questions(graph, communities, labels),
            "community_summaries": community_summaries(graph, communities, labels),
            "report_inputs": report_inputs,
        }
        state["analysis"] = refreshed
        store.replace_state(
            state, previous_state=previous_state, snapshot=loaded
        )
    return refreshed


def relabel(
    store_path: str | Path = DEFAULT_PROJECT_STORE,
    *,
    backend: str | None = None,
    model: str | None = None,
    missing_only: bool = False,
    max_concurrency: int = 4,
    batch_size: int = 100,
) -> dict[int, str]:
    """Name native communities and activate the labels with the same topology."""
    from .cluster import label_communities_by_hub
    from .llm import detect_backend, label_communities

    with HelixEmbeddedStore(store_path) as store:
        loaded = store.load()
        graph = loaded.graph
        previous_state = dict(loaded.state)
        state = copy.deepcopy(previous_state)
        communities = communities_from_state(state)
        previous = labels_from_state(state)
        selected = backend or detect_backend()
        to_label = {
            cid: members
            for cid, members in communities.items()
            if not (
                missing_only
                and cid in previous
                and not previous[cid].startswith("Community ")
            )
        }
        if selected and to_label:
            generated = label_communities(
                graph,
                to_label,
                backend=selected,
                model=model,
                gods=state.get("analysis", {}).get("god_nodes", []),
                max_concurrency=max_concurrency,
                batch_size=batch_size,
            )
        elif to_label:
            generated = label_communities_by_hub(graph, to_label)
        else:
            generated = {}
        labels = {
            cid: (
                previous[cid]
                if missing_only
                and cid in previous
                and not previous[cid].startswith("Community ")
                else generated.get(cid, f"Community {cid}")
            )
            for cid in communities
        }
        cohesion = {
            record["id"]: float(record["cohesion"])
            for record in state.get("communities", [])
            if isinstance(record, dict)
            and isinstance(record.get("id"), int)
            and isinstance(record.get("cohesion"), (int, float))
        }
        state["communities"] = community_records(
            communities,
            labels=labels,
            cohesion=cohesion,
            naming_source=selected or "native-hub",
        )
        store.replace_state(
            state, previous_state=previous_state, snapshot=loaded
        )
    return labels


__all__ = ["reanalyze", "recluster", "relabel"]
