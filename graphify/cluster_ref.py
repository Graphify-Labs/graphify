"""Member-side cluster memberships (``graphify-out/cluster-ref.json``).

``graphify cluster build`` upserts one entry in this committable marker for
each member.  A repository can belong to several clusters; every entry avoids
absolute paths and is resolved independently on the current machine.

This module is deliberately stdlib-only because hook nudges import it on a hot,
fail-open path.  Readers therefore return an empty list instead of raising.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

CLUSTER_REF_NAME = "cluster-ref.json"
CLUSTER_REF_VERSION = 1
_MAX_REF_BYTES = 1_000_000


def load_cluster_refs(out_dir: "Path | str") -> list[dict]:
    """Return all valid memberships from the collection marker.

    The Cluster feature is unreleased, so this intentionally accepts only the
    collection schema and does not carry a compatibility path for the former
    single-membership draft — regenerate old markers with ``cluster build``.
    """
    path = Path(out_dir) / CLUSTER_REF_NAME
    try:
        if not path.is_file() or path.stat().st_size > _MAX_REF_BYTES:
            return []
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    if not isinstance(data, dict) or data.get("version") != CLUSTER_REF_VERSION:
        return []
    raw_refs = data.get("clusters")
    if not isinstance(raw_refs, list):
        return []

    refs: list[dict] = []
    names: set[str] = set()
    for ref in raw_refs:
        if not isinstance(ref, dict):
            return []
        name = ref.get("cluster_name")
        if not isinstance(name, str) or not name or name in names:
            return []
        if not isinstance(ref.get("self_tag"), str) or not ref["self_tag"]:
            return []
        names.add(name)
        refs.append(ref)
    return refs


def select_cluster_ref(refs: list[dict], name: str | None = None) -> dict:
    """Select one membership or raise ``ValueError`` with an actionable error."""
    names = sorted(_clean(ref["cluster_name"]) for ref in refs)
    if name is not None:
        for ref in refs:
            if ref["cluster_name"] == name:
                return ref
        cleaned_matches = [
            ref for ref in refs if _clean(ref["cluster_name"]) == name
        ]
        if len(cleaned_matches) == 1:
            return cleaned_matches[0]
        available = ", ".join(names) or "none"
        raise ValueError(f"unknown cluster {name!r}; available clusters: {available}")
    if len(refs) == 1:
        return refs[0]
    if not refs:
        raise ValueError("this repo has no cluster memberships")
    raise ValueError(
        "this repo belongs to multiple clusters; choose one with --cluster NAME "
        f"({', '.join(names)})"
    )


def _clean(value) -> str:
    """Sanitize one marker field for assistant/terminal-facing text.

    The marker is a committed file that travels with clones, so its fields are
    untrusted. security.py is stdlib-only, so the lazy import preserves this
    module's light-import contract for the hook path.
    """
    from .security import sanitize_label

    return sanitize_label(str(value))


def member_count(ref: dict) -> "int | str":
    raw = ref.get("member_count", 0)
    try:
        count = int(raw)
    except (TypeError, ValueError):
        return "?"
    if isinstance(raw, bool) or not 1 <= count <= 100_000:
        return "?"
    return count


def cluster_hint_line(refs: list[dict]) -> str:
    """One-line member hint appended to no-match/empty results."""
    if not refs:
        return ""
    if len(refs) == 1:
        ref = refs[0]
        return (
            f"note: this repo is member '{_clean(ref['self_tag'])}' of cluster "
            f"'{_clean(ref['cluster_name'])}' ({member_count(ref)} members) — "
            "cross-repo answers may need the cluster graph; re-run with --cluster"
        )
    names = ", ".join(sorted(_clean(ref["cluster_name"]) for ref in refs))
    return (
        f"note: this repo belongs to {len(refs)} clusters ({names}) — cross-repo "
        "answers may need a cluster graph; re-run with --cluster NAME"
    )


def unresolvable_message(ref: dict) -> str:
    """Actionable message when one selected cluster is unavailable locally."""
    name = _clean(ref["cluster_name"])
    base = (
        f"this repo is member '{_clean(ref['self_tag'])}' of cluster "
        f"'{name}' ({member_count(ref)} members) "
        "but the cluster isn't available locally"
    )
    url = _clean(ref.get("cluster_url") or "")
    if url:
        return (
            f"{base}; clone {url} next to this repo and run "
            f"'graphify cluster build' there, then re-run with "
            f"--cluster {name}"
        )
    return (
        f"{base} and has no recorded remote; create it with "
        f"'graphify cluster init <dir> --name {name}', add the "
        "members, and run 'graphify cluster build'"
    )


def _spec_name_at(candidate: Path, want_name: str) -> bool:
    from .cluster_graph import find_spec_file, load_spec

    try:
        return find_spec_file(candidate) is not None and load_spec(candidate).name == want_name
    except Exception:
        return False


def resolve_cluster_dir(ref: dict, member_root: "Path | str") -> Path | None:
    """Resolve one membership via its hint, then sibling discovery."""
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
        if child != resolved_root and _spec_name_at(child, want_name):
            return child
    return None
