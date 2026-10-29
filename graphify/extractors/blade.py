"""Laravel Blade template extractor and the cross-file pass that resolves its targets."""
from __future__ import annotations

import re
from collections.abc import Sequence
from pathlib import Path, PurePosixPath

from graphify.extractors.base import _make_id, _read_source_text

# `<x-…>` tags Blade itself handles: slots and the runtime-named dynamic component.
_BLADE_BUILTIN_TAGS = frozenset({"slot", "dynamic-component"})


def extract_blade(path: Path) -> dict:
    """Extract @extends, @include, <x-…> and <livewire:> components, and wire:click
    bindings from Blade templates."""
    try:
        src = _read_source_text(path)
    except OSError:
        return {"error": f"cannot read {path}"}

    file_nid = _make_id(str(path))
    nodes = [{"id": file_nid, "label": path.name, "file_type": "code",
              "source_file": str(path), "source_location": None}]
    edges = []

    # @extends('layouts.app') — template inheritance: this view renders inside
    # the named parent layout. It is the primary structural relationship in a
    # Blade view (most page templates extend a layout), so dropping it left the
    # child disconnected from its layout in the graph.
    for m in re.finditer(r"@extends\(['\"]([^'\"]+)['\"]", src):
        tgt = m.group(1).replace(".", "/")
        tgt_nid = _make_id(tgt)
        if tgt_nid not in {n["id"] for n in nodes}:
            nodes.append({"id": tgt_nid, "label": m.group(1), "file_type": "code",
                          "source_file": str(path), "source_location": None,
                          "_blade_stub": True})
        edges.append({"source": file_nid, "target": tgt_nid, "relation": "extends",
                      "confidence": "EXTRACTED", "confidence_score": 1.0,
                      "source_file": str(path), "source_location": None, "weight": 1.0,
                      "_blade_ref": {"kind": "view", "name": m.group(1)}})

    # @include('path.to.partial') or @include("path.to.partial")
    for m in re.finditer(r"@include\(['\"]([^'\"]+)['\"]", src):
        tgt = m.group(1).replace(".", "/")
        tgt_nid = _make_id(tgt)
        if tgt_nid not in {n["id"] for n in nodes}:
            nodes.append({"id": tgt_nid, "label": m.group(1), "file_type": "code",
                          "source_file": str(path), "source_location": None,
                          "_blade_stub": True})
        edges.append({"source": file_nid, "target": tgt_nid, "relation": "includes",
                      "confidence": "EXTRACTED", "confidence_score": 1.0,
                      "source_file": str(path), "source_location": None, "weight": 1.0,
                      "_blade_ref": {"kind": "view", "name": m.group(1)}})

    # <x-alert>, <x-forms.input /> — anonymous Blade components. A `x-` attribute
    # (Alpine's x-data, x-on:click) never follows `<`, so the tag form is distinct.
    # <x-slot> and <x-dynamic-component> are Blade built-ins, not component files.
    for m in re.finditer(r"<x-((?:[\w\-]+::)?[\w.\-]+)", src):
        name = m.group(1)
        if name in _BLADE_BUILTIN_TAGS:
            continue
        tgt_nid = _make_id("components/" + name.replace(".", "/"))
        if tgt_nid not in {n["id"] for n in nodes}:
            nodes.append({"id": tgt_nid, "label": f"x-{name}", "file_type": "code",
                          "source_file": str(path), "source_location": None,
                          "_blade_stub": True})
        edges.append({"source": file_nid, "target": tgt_nid, "relation": "uses_component",
                      "confidence": "EXTRACTED", "confidence_score": 1.0,
                      "source_file": str(path), "source_location": None, "weight": 1.0,
                      "_blade_ref": {"kind": "component", "name": name}})

    # <livewire:component.name /> or <livewire:component.name>
    for m in re.finditer(r"<livewire:([\w.\-]+)", src):
        tgt_nid = _make_id(m.group(1))
        if tgt_nid not in {n["id"] for n in nodes}:
            nodes.append({"id": tgt_nid, "label": m.group(1), "file_type": "code",
                          "source_file": str(path), "source_location": None})
        edges.append({"source": file_nid, "target": tgt_nid, "relation": "uses_component",
                      "confidence": "EXTRACTED", "confidence_score": 1.0,
                      "source_file": str(path), "source_location": None, "weight": 1.0})

    # wire:click="methodName" or wire:click="methodName(arg)", with an optional
    # Livewire event modifier (wire:click.prevent=, wire:click.stop=) the bare
    # `wire:click=` pattern never matched at all. A call's own arguments are not
    # part of the method's name and must not end up in the bound id; a magic
    # action ($set, $emit, $toggle, $refresh, ...) is Livewire's own runtime
    # behavior, not a method the component defines, so it is left unbound rather
    # than fabricating an edge to something that does not exist.
    for m in re.finditer(r'wire:click(?:\.\w+)*=["\']([^"\']+)["\']', src):
        raw = m.group(1).strip()
        if raw.startswith("$"):
            continue
        name_match = re.match(r"[A-Za-z_]\w*", raw)
        if not name_match:
            continue
        method_name = name_match.group(0)
        tgt_nid = _make_id(method_name)
        if tgt_nid not in {n["id"] for n in nodes}:
            nodes.append({"id": tgt_nid, "label": method_name, "file_type": "code",
                          "source_file": str(path), "source_location": None})
        edges.append({"source": file_nid, "target": tgt_nid, "relation": "binds_method",
                      "confidence": "EXTRACTED", "confidence_score": 1.0,
                      "source_file": str(path), "source_location": None, "weight": 1.0})

    return {"nodes": nodes, "edges": edges}


# A view or component name Laravel maps onto a file path: dot- or slash-separated
# segments. Namespaced names (`mail::message`, `vendor::pkg.view`) live outside
# resources/views and are deliberately left unresolved.
_BLADE_NAME_RE = re.compile(r"[\w\-]+(?:[./][\w\-]+)*")


def _is_blade_path(path: Path) -> bool:
    # Same test as the extractor dispatch in extract.py.
    return path.name.lower().endswith(".blade.php")


def _blade_candidates(ref: dict) -> list[str]:
    """Corpus-relative paths a Blade reference may name, in Laravel's lookup order."""
    name = ref.get("name", "")
    if not isinstance(name, str) or not _BLADE_NAME_RE.fullmatch(name):
        return []
    rel = name.replace(".", "/")
    if ref.get("kind") == "view":
        return [f"resources/views/{rel}.blade.php"]
    if ref.get("kind") == "component":
        return [f"resources/views/components/{rel}.blade.php",
                f"resources/views/components/{rel}/index.blade.php"]
    return []


def resolve_blade_references(per_file: list[dict], nodes: list[dict], edges: list[dict]) -> None:
    """Point @extends / @include / <x-…> edges at the Blade file they name.

    Per-file extraction can only name the target, so each edge first points at a
    stub. Here, with every scanned file known, an edge whose target matches exactly
    one Blade file node (equal to, or a path suffix of, its source_file: a scan root
    above the Laravel root still resolves) is retargeted to it. No match, or more
    than one (two Laravel apps in one corpus), keeps the stub: never guess. Only
    files already in `nodes` are candidates, so the disk is never walked.
    """
    from graphify.build import _is_file_node_label

    fresh_files = {
        node["id"] for result in per_file for node in result.get("nodes", [])
        if not node.get("_blade_stub") and _is_blade_path(Path(node.get("source_file") or ""))
    }
    by_basename: dict[str, dict[str, set[str]]] = {}
    for node in nodes:
        source_file = node.get("source_file")
        if (node.get("_blade_stub") or node.get("file_type") != "code" or not source_file
                or not _is_blade_path(Path(source_file))
                or not _is_file_node_label(node.get("label"), source_file)):
            continue
        posix = Path(source_file).as_posix()
        by_basename.setdefault(Path(source_file).name, {}).setdefault(posix, set()).add(node["id"])

    refs = [edge for edge in edges if "_blade_ref" in edge]
    for edge in sorted(refs, key=lambda e: (str(e.get("source_file", "")), str(e["target"]))):
        ref = edge.pop("_blade_ref")
        if not isinstance(ref, dict) or edge["source"] not in fresh_files:
            continue
        for candidate in _blade_candidates(ref):
            matches = {
                nid
                for posix, nids in by_basename.get(PurePosixPath(candidate).name, {}).items()
                if posix == candidate or posix.endswith("/" + candidate)
                for nid in nids
            }
            if matches:
                # The first candidate that names any file decides, even when it is
                # ambiguous: falling through would pick a lower-priority file.
                if len(matches) == 1:
                    edge["target"] = next(iter(matches))
                break

    # Drop the stubs no edge reaches any more. On an incremental run `nodes` is a
    # scratch copy, so extract() also drops the `_blade_orphan` dicts from its own
    # list; every stub still in use loses its marker.
    referenced = {edge.get(key) for edge in edges for key in ("source", "target")}
    kept: list[dict] = []
    for node in nodes:
        if node.get("_blade_stub") and node["id"] not in referenced:
            node["_blade_orphan"] = True
            continue
        node.pop("_blade_stub", None)
        kept.append(node)
    nodes[:] = kept


def refresh_blade_paths(
    changed: list[Path], corpus: list[Path], invalidated: Sequence[Path] = (),
) -> list[Path]:
    """Re-extract every Blade view when the set of Blade files may have changed.

    Views resolve their targets against the scanned Blade files, so adding,
    deleting or ignoring one can retarget an UNCHANGED view's edge. Callers pass
    only the permitted, live corpus; unchanged views are served from the AST cache.
    """
    if not any(_is_blade_path(p) or p.name in (".gitignore", ".graphifyignore")
               for p in [*changed, *invalidated]):
        return changed
    return list(dict.fromkeys([*changed, *(p for p in corpus if _is_blade_path(p))]))
