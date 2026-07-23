"""Versioned durable state stored inside the same Helix graph generation."""

from __future__ import annotations

import hashlib
from typing import Any


STATE_SCHEMA_VERSION = 1


def new_state(**overrides: Any) -> dict[str, Any]:
    state: dict[str, Any] = {
        "schema_version": STATE_SCHEMA_VERSION,
        "build": {},
        "communities": [],
        "analysis": {},
        "incremental": {
            "files": {},
            "extractor_state": {},
            "topology_sources": [],
        },
        "learning": {},
        "semantic": {"used": False},
    }
    state.update(overrides)
    return state


def community_records(
    communities: dict[int, list[Any]],
    *,
    labels: dict[int, str] | None = None,
    cohesion: dict[int, float] | None = None,
    naming_source: str = "generated",
) -> list[dict[str, Any]]:
    labels = labels or {}
    cohesion = cohesion or {}
    from .persistence import _encode_key

    return [
        {
            "id": int(cid),
            "members": list(members),
            "name": labels.get(cid, f"Community {cid}"),
            "naming_source": naming_source,
            "signature": "sha256:" + hashlib.sha256(
                "\n".join(sorted(_encode_key(member) for member in members)).encode("utf-8")
            ).hexdigest(),
            "cohesion": cohesion.get(cid),
            "clustering": {
                "algorithm": "helix-leiden",
                "seed": 42,
                "resolution": 1.0,
                "randomness": 0.001,
                "trials": 1,
                "max_iterations": 100,
            },
        }
        for cid, members in sorted(communities.items())
    ]


def communities_from_state(state: dict[str, Any]) -> dict[int, list[Any]]:
    result: dict[int, list[Any]] = {}
    for record in state.get("communities", []):
        if isinstance(record, dict) and isinstance(record.get("id"), int):
            result[record["id"]] = list(record.get("members", []))
    return result


def labels_from_state(state: dict[str, Any]) -> dict[int, str]:
    return {
        record["id"]: record["name"]
        for record in state.get("communities", [])
        if isinstance(record, dict)
        and isinstance(record.get("id"), int)
        and isinstance(record.get("name"), str)
    }


def community_summaries(
    graph: Any,
    communities: dict[int, list[Any]],
    labels: dict[int, str],
) -> list[dict[str, Any]]:
    summaries = []
    for community_id, members in sorted(communities.items()):
        member_set = set(members)
        internal_edges = sum(
            1
            for edge in graph.edges()
            if edge.source in member_set and edge.target in member_set
        )
        summaries.append(
            {
                "id": community_id,
                "name": labels.get(community_id, f"Community {community_id}"),
                "node_count": len(members),
                "internal_edge_count": internal_edges,
            }
        )
    return summaries
