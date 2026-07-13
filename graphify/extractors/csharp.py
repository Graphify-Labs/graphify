"""C# cross-file resolution.

The config-driven C# *extractor* (``extract_csharp`` → ``_extract_generic``)
still lives in ``graphify/extract.py``; per ``extractors/MIGRATION.md`` the
config-driven languages cannot be ported one-by-one until the shared
``_extract_generic`` core moves as its own coordinated batch. This module is
the C# home for the parts that *are* cleanly separable — today, the cross-file
type-reference resolver below — and is where ``extract_csharp`` will land when
the core migration happens.
"""
from __future__ import annotations

import html
from pathlib import Path

from graphify.extractors.base import _make_id


def _build_csharp_type_def_index(all_nodes: list[dict]) -> dict[tuple[str, str], str]:
    """Return deterministic ``(namespace, name) -> node_id`` C# type definitions."""
    candidates: dict[tuple[str, str], list[dict]] = {}
    for node in all_nodes:
        if node.get("type") == "namespace":
            continue
        metadata = node.get("metadata") or {}
        if not isinstance(metadata, dict):
            metadata = {}
        if metadata.get("is_nested_type"):
            continue
        nid = node.get("id")
        label = node.get("label")
        if not (isinstance(nid, str) and nid and isinstance(label, str) and label):
            continue
        source_file = node.get("source_file")
        if (
            not isinstance(source_file, str)
            or not source_file.endswith(".cs")
            or node.get("file_type") != "code"
        ):
            continue
        if label.endswith(")") or label.startswith(".") or "." in label:
            continue
        namespace = metadata.get("namespace", "")
        if not isinstance(namespace, str):
            namespace = ""
        candidates.setdefault((namespace, label), []).append(node)

    return {
        key: sorted(
            nodes,
            key=lambda node: (
                str(node.get("source_file") or ""),
                str(node.get("source_location") or ""),
                str(node.get("id") or ""),
            ),
        )[0]["id"]
        for key, nodes in candidates.items()
    }


def _strip_trailing_csharp_generic_args(target_fqn: str) -> str:
    target_fqn = target_fqn.strip()
    if not target_fqn.endswith(">"):
        return target_fqn
    depth = 0
    for index in range(len(target_fqn) - 1, -1, -1):
        char = target_fqn[index]
        if char == ">":
            depth += 1
        elif char == "<":
            depth -= 1
            if depth == 0:
                return target_fqn[:index].strip()
    return target_fqn


def _resolve_cross_file_csharp_imports(
    per_file: list[dict],
    paths: list[Path],
    all_nodes: list[dict],
    all_edges: list[dict],
) -> None:
    """Re-point resolvable C# ``using`` import edges to canonical internal nodes.

    Namespace imports resolve only to canonical C# namespace nodes. Alias imports
    resolve only when the alias target's prefix is a known canonical namespace and
    the simple type name exists in the shared C# type-definition index. ``using
    static`` and nested type aliases remain deliberate gaps because they need
    member/nested-type modeling beyond this import pass.
    """
    _ = (per_file, paths)
    namespace_id_by_label: dict[str, str] = {}
    for node in sorted(
        all_nodes,
        key=lambda node: (
            str(node.get("source_file") or ""),
            str(node.get("source_location") or ""),
            str(node.get("id") or ""),
        ),
    ):
        if node.get("type") != "namespace":
            continue
        label = node.get("label")
        nid = node.get("id")
        if isinstance(label, str) and label and isinstance(nid, str) and nid:
            namespace_id_by_label.setdefault(label, nid)

    type_def_index = _build_csharp_type_def_index(all_nodes)
    if not namespace_id_by_label and not type_def_index:
        return

    repointed_from: set[str] = set()
    for edge in all_edges:
        if edge.get("relation") != "imports":
            continue
        metadata = edge.get("metadata") or {}
        if not isinstance(metadata, dict):
            continue
        using_kind = metadata.get("using_kind")
        target_fqn = metadata.get("target_fqn")
        if not using_kind or not isinstance(target_fqn, str) or not target_fqn:
            continue

        resolved = None
        if using_kind == "namespace":
            resolved = namespace_id_by_label.get(target_fqn)
        elif using_kind == "alias":
            base_fqn = _strip_trailing_csharp_generic_args(html.unescape(target_fqn))
            prefix, sep, name = base_fqn.rpartition(".")
            if sep and prefix in namespace_id_by_label:
                resolved = type_def_index.get((prefix, name))

        old_target = edge.get("target")
        if resolved and resolved != old_target:
            edge["target"] = resolved
            if isinstance(old_target, str) and old_target:
                repointed_from.add(old_target)

    if not repointed_from:
        return

    still_referenced: set[str] = set()
    for edge in all_edges:
        still_referenced.add(edge.get("source"))
        still_referenced.add(edge.get("target"))
    all_nodes[:] = [
        node for node in all_nodes
        if node.get("id") not in repointed_from or node.get("id") in still_referenced
    ]


def _resolve_csharp_type_references(
    per_file: list[dict],
    paths: list[Path],
    all_nodes: list[dict],
    all_edges: list[dict],
) -> None:
    """Arbitrate all C# ``inherits``/``implements``/``references`` targets.

    The extractor emits provisional same-file bindings and sourceless stubs. This
    pass is the single soundness gate: it uses only graph-stamped namespace/import
    facts, keeps a binding only when the referenced simple name resolves to one
    in-scope real type definition, and otherwise leaves the edge on a dangling stub.
    """
    _ = (per_file, paths)

    def _is_cs_file(value: object) -> bool:
        return isinstance(value, str) and value.endswith(".cs")

    def _metadata(value: object) -> dict:
        return value if isinstance(value, dict) else {}

    def _namespace(node: dict | None) -> str:
        metadata = _metadata((node or {}).get("metadata"))
        namespace = metadata.get("namespace", "")
        return namespace if isinstance(namespace, str) else ""

    def _append_unique(items: list[str], value: str) -> None:
        if value not in items:
            items.append(value)

    node_by_id = {
        node["id"]: node
        for node in all_nodes
        if isinstance(node.get("id"), str) and node.get("id")
    }
    type_def_index = _build_csharp_type_def_index(all_nodes)
    known_namespaces = {
        node.get("label")
        for node in all_nodes
        if node.get("type") == "namespace" and isinstance(node.get("label"), str)
    }

    # Each using carries its lexical scope: ("file", None) applies file-wide;
    # ("namespace", scope_id) applies only where scope_id is in the ref's scope_chain.
    namespace_usings_by_file: dict[str, list[tuple[str, str, str | None]]] = {}
    aliases_by_file: dict[str, dict[str, list[tuple[str, str, str | None]]]] = {}

    for edge in all_edges:
        if edge.get("relation") != "imports":
            continue
        source_node = node_by_id.get(edge.get("source"))
        if not (
            source_node
            and isinstance(source_node.get("label"), str)
            and source_node.get("label", "").endswith(".cs")
        ):
            continue
        source_file = source_node.get("source_file")
        if not _is_cs_file(source_file):
            continue
        metadata = _metadata(edge.get("metadata"))
        target_fqn = metadata.get("target_fqn")
        if not isinstance(target_fqn, str) or not target_fqn:
            continue
        scope_kind = metadata.get("scope_kind") or "file"
        scope_id = metadata.get("scope_id")
        using_kind = metadata.get("using_kind")
        if using_kind == "namespace":
            entry = (target_fqn, scope_kind, scope_id)
            bucket = namespace_usings_by_file.setdefault(source_file, [])
            if entry not in bucket:
                bucket.append(entry)
        elif using_kind == "alias":
            alias = metadata.get("alias")
            if isinstance(alias, str) and alias:
                entry = (target_fqn, scope_kind, scope_id)
                bucket = aliases_by_file.setdefault(source_file, {}).setdefault(alias, [])
                if entry not in bucket:
                    bucket.append(entry)

    def _scope_chain(node: dict) -> list[str]:
        chain = _metadata(node.get("metadata")).get("scope_chain")
        return chain if isinstance(chain, list) else []

    def _using_in_scope(scope_kind: str, scope_id: str | None, source_node: dict) -> bool:
        if scope_kind == "file":
            return True
        return scope_id is not None and scope_id in _scope_chain(source_node)

    def _scopes_for(source_node: dict, source_file: str) -> list[str]:
        scopes: list[str] = []
        _append_unique(scopes, _namespace(source_node))
        _append_unique(scopes, "")
        for namespace, scope_kind, scope_id in namespace_usings_by_file.get(source_file, []):
            if _using_in_scope(scope_kind, scope_id, source_node):
                _append_unique(scopes, namespace)
        return scopes

    def _resolve_alias(label: str, source_node: dict, source_file: str) -> str | None:
        hits = set()
        for target_fqn, scope_kind, scope_id in aliases_by_file.get(source_file, {}).get(label, []):
            if not _using_in_scope(scope_kind, scope_id, source_node):
                continue
            base_fqn = _strip_trailing_csharp_generic_args(html.unescape(target_fqn))
            namespace, sep, simple_name = base_fqn.rpartition(".")
            if not sep:
                simple_name = namespace
                namespace = ""
            if not simple_name:
                continue
            hit = type_def_index.get((namespace, simple_name))
            if hit:
                hits.add(hit)
        return next(iter(hits)) if len(hits) == 1 else None

    def _resolve_label(label: str, source_node: dict, source_file: str) -> str | None:
        if label in aliases_by_file.get(source_file, {}):
            return _resolve_alias(label, source_node, source_file)
        candidates: list[str] = []
        for namespace in _scopes_for(source_node, source_file):
            hit = type_def_index.get((namespace, label))
            if hit and hit not in candidates:
                candidates.append(hit)
        return candidates[0] if len(candidates) == 1 else None

    def _resolve_qualified(label: str, qualifier: object, source_node: dict, source_file: str) -> str | None:
        # Sound qualified resolution: an in-scope alias for Q shadows the namespace Q. For a qualified
        # ref Q.label, look up (alias_target_namespace, label). If no in-scope alias, fall through to an
        # exact known namespace. Dangle on ambiguity / no hit / unknown qualifier.
        if not isinstance(qualifier, str) or not qualifier:
            return None
        in_scope = [
            entry for entry in aliases_by_file.get(source_file, {}).get(qualifier, [])
            if _using_in_scope(entry[1], entry[2], source_node)
        ]
        if in_scope:
            hits = set()
            for target_fqn, _scope_kind, _scope_id in in_scope:
                alias_ns = _strip_trailing_csharp_generic_args(html.unescape(target_fqn))
                hit = type_def_index.get((alias_ns, label))
                if hit:
                    hits.add(hit)
            return next(iter(hits)) if len(hits) == 1 else None
        if qualifier in known_namespaces:
            return type_def_index.get((qualifier, label))
        return None

    def _is_placeholder(node: dict | None) -> bool:
        return bool(node) and not node.get("source_file")

    def _is_csharp_relevant_target(node: dict) -> bool:
        if node.get("type") == "namespace":
            return True
        source_file = node.get("source_file")
        return not source_file or _is_cs_file(source_file)

    def _label_for_type_ref_target(target_node: dict, source_file: str) -> str | None:
        label = target_node.get("label")
        if not isinstance(label, str) or not label:
            return None
        if not label.endswith(".cs"):
            return label

        stem = label[:-3]
        for alias in aliases_by_file.get(source_file, {}):
            if alias.lower() == stem.lower() or _make_id(alias) == _make_id(stem):
                return alias
        return stem or None

    def _dangling_stub_id(label: str, current_target: object) -> str:
        current = node_by_id.get(current_target)
        if _is_placeholder(current) and current.get("label") == label:
            return str(current_target)

        for node in all_nodes:
            nid = node.get("id")
            if (
                isinstance(nid, str)
                and node.get("label") == label
                and _is_placeholder(node)
            ):
                return nid

        stem = _make_id(label)
        stub_id = stem
        if stub_id in node_by_id:
            stub_id = _make_id("csharp_type_ref", label)
            suffix = 2
            while stub_id in node_by_id:
                stub_id = _make_id("csharp_type_ref", label, str(suffix))
                suffix += 1
        node = {
            "id": stub_id,
            "label": label,
            "file_type": "code",
            "source_file": "",
            "source_location": "",
        }
        all_nodes.append(node)
        node_by_id[stub_id] = node
        return stub_id

    REPOINT_RELATIONS = {"implements", "inherits", "references"}
    repointed_from: set[str] = set()
    for edge in all_edges:
        if edge.get("relation") not in REPOINT_RELATIONS:
            continue
        source_file = edge.get("source_file")
        if not _is_cs_file(source_file):
            continue
        source_node = node_by_id.get(edge.get("source"))
        target_node = node_by_id.get(edge.get("target"))
        if not source_node or not target_node:
            continue
        if not _is_csharp_relevant_target(target_node):
            continue
        metadata = _metadata(edge.get("metadata"))
        label = metadata.get("ref_token") or _label_for_type_ref_target(target_node, source_file)
        if not label:
            continue
        if metadata.get("qualified"):
            resolved = _resolve_qualified(label, metadata.get("ref_qualifier"), source_node, source_file)
        else:
            resolved = _resolve_label(label, source_node, source_file)
        target = edge.get("target")
        desired = resolved or _dangling_stub_id(label, target)
        if desired != target:
            edge["target"] = desired
            if isinstance(target, str) and _is_placeholder(target_node):
                repointed_from.add(target)

    if not repointed_from:
        return

    still_referenced: set[str] = set()
    for edge in all_edges:
        still_referenced.add(edge.get("source"))
        still_referenced.add(edge.get("target"))
    all_nodes[:] = [
        node for node in all_nodes
        if node.get("id") not in repointed_from or node.get("id") in still_referenced
    ]
