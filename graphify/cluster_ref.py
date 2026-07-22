"""Member-side cluster back-references (`graphify-out/cluster-ref.json`).

`graphify cluster build` writes this marker into every resolved member repo so
tooling running INSIDE a member knows the repo belongs to a multi-repo cluster
(see graphify/cluster_graph.py). The marker is committable — graphify-out/ is
meant to be committed — so it carries no absolute paths: the cluster is
re-found per machine via a relative `dir_hint` and origin-style discovery, and
when it can't be found the marker still lets tooling say "this repo is member
X of cluster Y (N members); clone <url> to get the cluster graph".

This module is deliberately stdlib-only: it is imported on hot, fail-open
paths (the hook-guard nudge) that must never pay the networkx import cost.
Everything here fails soft — readers return None/"" rather than raising.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

CLUSTER_REF_NAME = "cluster-ref.json"
CLUSTER_REF_VERSION = 1

# Refuse to parse absurdly large marker files (they're ~1 KB in practice).
_MAX_REF_BYTES = 1_000_000


def load_cluster_ref(out_dir: "Path | str") -> dict | None:
    """Read a member's cluster-ref marker. Returns None instead of raising.

    None on: missing file, oversized file, unreadable/invalid JSON, non-dict
    payload, missing required keys, or a marker from a future schema version.
    """
    path = Path(out_dir) / CLUSTER_REF_NAME
    try:
        if not path.is_file() or path.stat().st_size > _MAX_REF_BYTES:
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    if not data.get("cluster_name") or not data.get("self_tag"):
        return None
    try:
        if int(data.get("version", 1)) > CLUSTER_REF_VERSION:
            return None
    except (TypeError, ValueError):
        return None
    return data


def cluster_hint_line(ref: dict) -> str:
    """The one-line member hint appended to no-match/empty results."""
    return (
        f"note: this repo is member '{ref['self_tag']}' of cluster "
        f"'{ref['cluster_name']}' ({ref.get('member_count', '?')} members) — "
        f"cross-repo answers may need the cluster graph; re-run with --cluster"
    )


def unresolvable_message(ref: dict) -> str:
    """Actionable message when the cluster isn't available on this machine."""
    base = (
        f"this repo is member '{ref['self_tag']}' of cluster "
        f"'{ref['cluster_name']}' ({ref.get('member_count', '?')} members) "
        f"but the cluster isn't available locally"
    )
    url = ref.get("cluster_url") or ""
    if url:
        return (
            f"{base}; clone {url} next to this repo and run "
            f"'graphify cluster build' there, then re-run with --cluster"
        )
    return (
        f"{base} and has no recorded remote; create it with "
        f"'graphify cluster init <dir> --name {ref['cluster_name']}', add the "
        f"members, and run 'graphify cluster build'"
    )


def _spec_name_at(candidate: Path, want_name: str) -> bool:
    """True if `candidate` holds a cluster spec whose name matches."""
    from .cluster_graph import find_spec_file, load_spec

    try:
        if find_spec_file(candidate) is None:
            return False
        return load_spec(candidate).name == want_name
    except Exception:
        return False


def resolve_cluster_dir(ref: dict, member_root: "Path | str") -> Path | None:
    """Find the cluster directory for a member's marker on this machine.

    Order: the marker's relative `dir_hint` (verified against the spec name),
    then a scan of the member repo's parent's child directories for a cluster
    spec with the matching name. Returns None when nothing matches.
    """
    member_root = Path(member_root)
    want_name = ref["cluster_name"]

    hint = ref.get("dir_hint") or ""
    if hint:
        candidate = Path(os.path.normpath(member_root / hint))
        if _spec_name_at(candidate, want_name):
            return candidate

    try:
        parent = member_root.resolve().parent
        children = sorted(c for c in parent.iterdir() if c.is_dir())
    except OSError:
        return None
    resolved_root = member_root.resolve()
    for child in children:
        if child == resolved_root:
            continue
        if _spec_name_at(child, want_name):
            return child
    return None
