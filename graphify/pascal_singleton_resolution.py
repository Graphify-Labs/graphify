"""Cross-file resolution of Pascal/Delphi calls made through a global object.

Delphi's dominant application idiom is the global singleton: a unit declares
``var DM: TDM = nil;`` next to the data module it holds, every other unit
``uses`` it, and the work happens in ``DM.OpenPeriod``, ``PDM.Recalculate``,
``dtmTabele.Refresh``. The per-file pass cannot resolve any of it -- it
discards the qualifier and looks the bare member name up in the CALLER's own
scope (``_resolve_pascal_callee_factory``), which is the wrong object, so the
call is reported as a raw call and the business logic of the application
arrives in the graph as unconnected routines.

This resolver runs once every file is extracted, so it can see both halves:
the ``var`` block that gives ``DM`` its type, and the class that type names.
Resolution follows the compiler:

1. the qualifier must not be shadowed -- the extractor already withholds it
   when the routine declares a parameter, a local, or a class field of that
   name (a Delphi form publishes its components as plain fields, so ``Query``
   inside a form method is the component, never a global of the same name);
2. the variable must be visible: declared in the calling file itself or in a
   unit its ``uses`` clause names. Pascal identifier visibility is NOT
   transitive, so the direct uses clause is exactly the right scope;
3. the variable's type, that type's class, and the method must each resolve
   to exactly one candidate, or nothing is emitted.

Unit names are matched against the INDEXED CORPUS rather than against the
disk. The per-file ``imports`` pass resolves a unit name by scanning
``_pascal_project_root`` -- the highest ancestor directly holding ``.pas``
files -- and in the standard Delphi layout, with the ``.dpr`` in
``Projects/App/`` and units in sibling ``DataModules/`` and ``Forms/`` trees,
that root is the project subdirectory alone, so cross-directory units resolve
to nothing. Matching names against the files actually extracted sidesteps
that here without changing what the per-file pass emits.

Only ``calls`` edges are added, only for raw calls that nothing else
resolved, and only between nodes that already exist.
"""
from __future__ import annotations

import os

from graphify.extractors.base import _make_id

_PASCAL_SUFFIXES = (".pas", ".pp", ".dpr", ".dpk", ".inc")


def _is_pascal(source_file: object) -> bool:
    return isinstance(source_file, str) and source_file.lower().endswith(_PASCAL_SUFFIXES)


def _basename(path: str) -> str:
    # os.path.basename on POSIX does not split a Windows `\` separator, so a
    # Windows-style source_file (`C:\proj\Unit.pas`) would keep the whole string
    # as its "basename" and never match the relativised POSIX corpus path.
    # Normalise separators first so the match works cross-platform (#5286).
    return os.path.basename(path.replace("\\", "/"))


def _unit_stem(source_file: str) -> str:
    return _basename(source_file).rsplit(".", 1)[0].lower()


def _raw_path_of(result: dict) -> str | None:
    """The path a per-file extraction result carries, as the extractor wrote it."""
    for node in result.get("nodes", []):
        if isinstance(node, dict):
            source_file = node.get("source_file")
            if isinstance(source_file, str) and source_file:
                return source_file
    for raw_call in result.get("raw_calls", []):
        if isinstance(raw_call, dict):
            source_file = raw_call.get("source_file")
            if isinstance(source_file, str) and source_file:
                return source_file
    return None


def _corpus_path_matcher(corpus_files: set[str]):
    """Map an extractor path onto the one the merged graph uses.

    A per-file result keeps the path the extractor was handed -- absolute, in
    the platform's own separators -- while the id-remap pass relativises
    `source_file` on the merged nodes. The two therefore never compare equal,
    and `extract.py` says as much where it builds its own call index: *key on
    stable node ids, not source_file strings*. Call sites here do exactly
    that, via `caller_nid`; a unit that only DECLARES globals has no call to
    anchor on, so its path is matched instead -- by basename, then by
    requiring the corpus path to be a tail of the extractor's, which is what
    relativising leaves behind. An ambiguous match yields nothing.
    """
    by_name: dict[str, list[str]] = {}
    for source_file in corpus_files:
        by_name.setdefault(_basename(source_file).lower(), []).append(source_file)

    def match(raw_path: str) -> str | None:
        candidates = by_name.get(_basename(raw_path).lower())
        if not candidates:
            return None
        if len(candidates) == 1:
            return candidates[0]
        normalised = raw_path.replace("\\", "/").lower()
        tails = [
            c for c in candidates
            if normalised.endswith("/" + c.replace("\\", "/").lower())
        ]
        return tails[0] if len(tails) == 1 else None

    return match


def resolve_pascal_singleton_calls(
    per_file: list[dict],
    all_nodes: list[dict],
    all_edges: list[dict],
) -> None:
    """Resolve ``Global.Method()`` calls to the method of the global's class.

    Purely additive: every edge emitted is a ``calls`` edge for a raw call the
    per-file pass could not resolve, and each requires an unambiguous
    variable, type and method. Ambiguity produces no edge rather than a guess.
    """
    node_by_id = {n.get("id"): n for n in all_nodes}

    # A unit name can only be matched to a file that was actually extracted,
    # and only when that name is unique in the corpus: two `Data.pas` in
    # different trees make `uses Data` genuinely ambiguous from here.
    corpus_files: set[str] = set()
    files_by_stem: dict[str, list[str]] = {}
    for node in all_nodes:
        source_file = node.get("source_file")
        if _is_pascal(source_file) and source_file not in corpus_files:
            corpus_files.add(str(source_file))
            files_by_stem.setdefault(_unit_stem(str(source_file)), []).append(str(source_file))
    if not corpus_files:
        return

    # A `uses` entry the per-file pass could not find on disk leaves an edge
    # pointing at `_make_id(unit_name)`, and NO node: the external stub for it
    # is materialised when the graph is assembled, which is after this runs.
    # So the unit name has to be recovered from the edge's target id. Only
    # unit names unique in the corpus are kept, since `uses Data` cannot name
    # two different `Data.pas`.
    file_by_unit_id: dict[str, str] = {
        _make_id(stem): candidates[0]
        for stem, candidates in files_by_stem.items() if len(candidates) == 1
    }

    # --- what each file declares --------------------------------------------
    to_corpus_path = _corpus_path_matcher(corpus_files)
    globals_of: dict[str, dict[str, str]] = {}
    for result in per_file:
        if not isinstance(result, dict):
            continue
        declared = result.get("global_vars")
        if not isinstance(declared, dict) or not declared:
            continue
        raw_path = _raw_path_of(result)
        source_file = to_corpus_path(raw_path) if raw_path else None
        if source_file is not None:
            globals_of.setdefault(source_file, {}).update(declared)
    if not globals_of:
        return

    declared_ids: set[str] = set()
    uses_of: dict[str, set[str]] = {}
    methods_of: dict[str, dict[str, set[str]]] = {}
    bases_of: dict[str, list[str]] = {}
    for edge in all_edges:
        relation = edge.get("relation")
        if relation == "contains":
            declared_ids.add(edge.get("target"))
        elif relation == "imports":
            source_file = node_by_id.get(edge.get("source"), {}).get("source_file")
            if not _is_pascal(source_file):
                continue
            target_node = node_by_id.get(edge.get("target"), {})
            target_file = target_node.get("source_file")
            if _is_pascal(target_file):
                # The per-file pass found the unit on disk, so the edge
                # already points at its file node.
                uses_of.setdefault(str(source_file), set()).add(str(target_file))
                continue
            # Otherwise the unit was not found on disk. The node that will
            # carry its name does not exist yet, so match the edge's target id
            # -- which IS the normalised unit name -- against the corpus.
            used = file_by_unit_id.get(str(edge.get("target")))
            if used is None:
                # It may still be a stub that already has a node, labelled
                # with the bare unit name ("Data") or a file name ("Data.pas").
                label = str(target_node.get("label", ""))
                candidates = files_by_stem.get(_unit_stem(label)) if label else None
                used = candidates[0] if candidates and len(candidates) == 1 else None
            if used is not None and used != source_file:
                uses_of.setdefault(str(source_file), set()).add(used)
        elif relation == "method":
            method_node = node_by_id.get(edge.get("target"))
            if method_node is None:
                continue
            name = str(method_node.get("label", "")).removesuffix("()").lower()
            methods_of.setdefault(edge.get("source"), {}).setdefault(name, set()).add(
                edge.get("target")
            )
        elif relation == "inherits":
            bases_of.setdefault(edge.get("source"), []).append(edge.get("target"))

    types_by_name: dict[str, list[str]] = {}
    for node in all_nodes:
        nid = node.get("id")
        if nid not in declared_ids or not _is_pascal(node.get("source_file")):
            continue
        label = str(node.get("label", ""))
        if not label or label.endswith("()"):
            continue  # routines render as `Name()`; a variable's type is not one
        types_by_name.setdefault(label.lower(), []).append(nid)
    if not types_by_name:
        return

    def _visible_type(qualifier: str, from_file: str) -> str | None:
        """The type of the global *qualifier* as seen from *from_file*."""
        found: set[str] = set()
        for unit in (from_file, *uses_of.get(from_file, ())):
            type_name = globals_of.get(unit, {}).get(qualifier)
            if type_name:
                found.add(type_name)
        return found.pop() if len(found) == 1 else None

    def _class_for(type_name: str, from_file: str) -> str | None:
        candidates = types_by_name.get(type_name)
        if not candidates:
            return None
        if len(candidates) == 1:
            return candidates[0]
        visible = uses_of.get(from_file, set())
        scoped = [
            nid for nid in candidates
            if node_by_id.get(nid, {}).get("source_file") in visible
        ]
        return scoped[0] if len(scoped) == 1 else None

    def _method_for(class_nid: str, name: str) -> str | None:
        """*name* on the class or, failing that, on its nearest ancestor."""
        seen: set[str] = set()
        queue = [class_nid]
        while queue:
            current = queue.pop(0)
            if current in seen:
                continue
            seen.add(current)
            candidates = methods_of.get(current, {}).get(name)
            if candidates:
                return next(iter(candidates)) if len(candidates) == 1 else None
            queue.extend(bases_of.get(current, []))
        return None

    existing_pairs = {
        (e.get("source"), e.get("target"))
        for e in all_edges if e.get("relation") == "calls"
    }
    for result in per_file:
        if not isinstance(result, dict):
            continue
        for raw_call in result.get("raw_calls", []):
            if not isinstance(raw_call, dict):
                continue
            qualifier = raw_call.get("qualifier")
            caller = raw_call.get("caller_nid")
            callee = raw_call.get("callee")
            if not qualifier or not caller or not callee:
                continue
            caller_node = node_by_id.get(caller)
            if caller_node is None:
                continue
            # The caller's OWN node carries the relativised path the rest of
            # this graph is keyed by; `raw_call["source_file"]` still holds
            # the path the extractor was handed, which would match nothing.
            source_file = caller_node.get("source_file")
            if not _is_pascal(source_file):
                continue
            type_name = _visible_type(str(qualifier), str(source_file))
            if not type_name:
                continue
            class_nid = _class_for(type_name, str(source_file))
            if class_nid is None:
                continue
            target = _method_for(class_nid, str(callee))
            if not target or target == caller:
                continue
            pair = (caller, target)
            if pair in existing_pairs:
                continue
            existing_pairs.add(pair)
            all_edges.append({
                "source": caller,
                "target": target,
                "relation": "calls",
                "context": "global object call",
                "confidence": "EXTRACTED",
                "confidence_score": 1.0,
                "source_file": source_file,
                "source_location": raw_call.get("source_location"),
                "weight": 1.0,
            })
