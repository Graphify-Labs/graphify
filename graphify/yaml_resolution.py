"""Resolve YAML value references against the scanned corpus (#5225).

``extract_yaml`` reports each literal reference it reads from a value (a
workflow's ``pnpm run check``, a compose bind mount's ``./settings.yaml``) as a
``raw_calls`` entry tagged ``language: "yaml"``, with the target as a path
relative to the YAML file's folder. Only now, with every file extracted, can
the target be checked against what was actually scanned:

* ``ref_kind: "file"`` links the key that holds the value to the scanned
  file's node. A file that exists on disk but was not scanned (ignored,
  excluded, outside the root) gets no edge.
* ``ref_kind: "script"`` links it to the script's key node in the named
  ``package.json``: the ``scripts`` key's child carrying the script's name.
  No such package, or no such script, gets no edge.

The edge is ``references`` and EXTRACTED: the YAML spells the target out, and
the target was found, not inferred. The shared cross-file call pass skips
these raw calls, so a script name never becomes a ``calls`` edge to a
same-named function.
"""
from __future__ import annotations

import posixpath
from typing import Any

from graphify.extractors.base import active_scan_root as _active_scan_root

YAML_REF_SUFFIXES = frozenset({".yaml", ".yml"})


def _norm(path: str, root: Any) -> str:
    """A scanned file's path, absolute and POSIX, as the resolver keys it."""
    p = path.replace("\\", "/")
    if not posixpath.isabs(p) and root is not None:
        p = posixpath.join(str(root).replace("\\", "/"), p)
    return posixpath.normpath(p)


def resolve_yaml_value_refs(
    per_file: list[dict], all_nodes: list[dict], all_edges: list[dict]
) -> None:
    """Turn ``language: "yaml"`` raw calls into ``references`` edges in place."""
    calls = [
        rc for result in per_file if isinstance(result, dict)
        for rc in result.get("raw_calls") or []
        if isinstance(rc, dict) and rc.get("language") == "yaml"
    ]
    if not calls:
        return
    root = _active_scan_root()

    # File nodes only: a file node's label is its path's last segment. The
    # endswith test is a cheap filter so the path split runs only on
    # candidates, not on every symbol in the corpus.
    file_nid: dict[str, str] = {}
    label: dict[str, str] = {}
    for n in all_nodes:
        sf, nid, lb = n.get("source_file"), n.get("id"), str(n.get("label", ""))
        if not nid:
            continue
        label[nid] = lb
        if sf and lb and str(sf).endswith(lb) \
                and lb == posixpath.basename(str(sf).replace("\\", "/")):
            file_nid.setdefault(_norm(str(sf), root), nid)

    # `contains` children, kept only under package.json files and their
    # `scripts` key: the one chain a script reference walks.
    packages = {nid for nid in file_nid.values() if label.get(nid) == "package.json"}
    # Two passes, so the result does not depend on edge order.
    contains = [e for e in all_edges if e.get("relation") == "contains"]
    scripts_of = {
        e.get("source"): e.get("target") for e in contains
        if e.get("source") in packages and label.get(e.get("target")) == "scripts"
    }
    script_keys = set(scripts_of.values())
    by_script_name: dict[str, dict[str, str]] = {}
    for e in contains:
        if e.get("source") in script_keys:
            by_script_name.setdefault(e.get("source"), {}).setdefault(
                label.get(e.get("target"), ""), e.get("target"))

    seen = {(e.get("source"), e.get("target"), e.get("relation")) for e in all_edges}
    for rc in calls:
        caller, holder_file = rc.get("caller_nid"), rc.get("source_file")
        target_path = rc.get("target_path")
        if not caller or not holder_file or not target_path:
            continue
        here = posixpath.dirname(_norm(str(holder_file), root))
        target_file = file_nid.get(posixpath.normpath(posixpath.join(here, target_path)))
        if target_file is None:
            continue
        if rc.get("ref_kind") == "script":
            scripts = scripts_of.get(target_file)
            target = by_script_name.get(scripts, {}).get(str(rc.get("callee") or "")) if scripts else None
        else:
            target = target_file
        if not target or target == caller or (caller, target, "references") in seen:
            continue
        seen.add((caller, target, "references"))
        all_edges.append({
            "source": caller, "target": target, "relation": "references",
            "context": "yaml_value", "confidence": "EXTRACTED",
            "source_file": holder_file, "source_location": rc.get("source_location"),
            "weight": 1.0,
        })
