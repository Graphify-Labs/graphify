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
from dataclasses import dataclass
from pathlib import Path

from graphify.extractors.base import _make_id


_CSHARP_SCOPED_STUB_REWIRE_RELATIONS = frozenset({"inherits", "implements", "references", "imports"})


def _csharp_preserve_scoped_stub_rewire(edge: dict, remapped_id: str, by_id: dict) -> bool:
    """Return True when generic stub rewiring must not cross C# scoped resolution."""
    return (
        str(edge.get("source_file", "")).endswith(".cs")
        and edge.get("relation") in _CSHARP_SCOPED_STUB_REWIRE_RELATIONS
        and str(by_id.get(remapped_id, {}).get("source_file", "")).endswith(".cs")
    )


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


def _build_csharp_type_def_groups(all_nodes: list[dict]) -> dict[tuple[str, str], list[str]]:
    """Like _build_csharp_type_def_index but keeps ALL node ids per (namespace, name).

    Partial classes are split into multiple same-key nodes; L2 aggregates their
    `method` edges. Returns (namespace, name) -> [node_id, ...] deterministically
    sorted.
    """
    groups: dict[tuple[str, str], list[dict]] = {}
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
        groups.setdefault((namespace, label), []).append(node)
    return {
        key: [
            n["id"]
            for n in sorted(
                nodes,
                key=lambda node: (
                    str(node.get("source_file") or ""),
                    str(node.get("source_location") or ""),
                    str(node.get("id") or ""),
                ),
            )
        ]
        for key, nodes in groups.items()
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


def _csharp_base_identifier(name: str) -> str:
    """`Foo<int>` -> `Foo`; a plain identifier is returned unchanged. Prevents a
    generic method callee from colliding with a same-spelled non-generic (`Fooint`)."""
    name = name.strip()
    lt = name.find("<")
    return name[:lt].strip() if lt != -1 else name


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


@dataclass(frozen=True)
class CsharpImportEntry:
    target_fqn: str
    scope_kind: str
    scope_id: str | None
    using_kind: str
    alias: str | None = None
    target_kind: str | None = None

    @property
    def is_extern(self) -> bool:
        return self.using_kind == "extern_alias"


class CsharpNameResolver:
    """Shared, module-scope C# name resolution built from a full node+edge set."""

    def __init__(self, all_nodes, all_edges):
        safe_nodes = all_nodes if isinstance(all_nodes, list) else []
        safe_edges = all_edges if isinstance(all_edges, list) else []
        self.node_by_id = {
            node["id"]: node
            for node in safe_nodes
            if isinstance(node, dict) and isinstance(node.get("id"), str) and node.get("id")
        }
        self.type_def_index = _build_csharp_type_def_index(safe_nodes)
        self.type_def_groups = _build_csharp_type_def_groups(safe_nodes)
        self.known_namespaces = {
            node.get("label")
            for node in safe_nodes
            if isinstance(node, dict)
            and node.get("type") == "namespace"
            and isinstance(node.get("label"), str)
        }
        self.namespace_usings_by_file: dict[str, list[CsharpImportEntry]] = {}
        self.static_usings_by_file: dict[str, list[CsharpImportEntry]] = {}
        self.global_namespace_usings: list[CsharpImportEntry] = []
        self.global_static_usings: list[CsharpImportEntry] = []
        self.aliases_by_file: dict[str, dict[str, list[CsharpImportEntry]]] = {}
        self.global_aliases: dict[str, list[CsharpImportEntry]] = {}
        self.extern_aliases_by_file: dict[str, list[CsharpImportEntry]] = {}

        for edge in safe_edges:
            if not isinstance(edge, dict) or edge.get("relation") != "imports":
                continue
            source_node = self.node_by_id.get(edge.get("source"))
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
            scope_id = scope_id if isinstance(scope_id, str) else None
            using_kind = metadata.get("using_kind") or "namespace"
            target_kind = metadata.get("target_kind")
            target_kind = target_kind if target_kind in ("type", "namespace") else None
            alias = metadata.get("alias")
            alias = alias if isinstance(alias, str) and alias else None
            entry = CsharpImportEntry(
                target_fqn=target_fqn,
                scope_kind=str(scope_kind),
                scope_id=scope_id,
                using_kind=str(using_kind),
                alias=alias,
                target_kind=target_kind,
            )
            if using_kind == "namespace":
                bucket = self.global_namespace_usings if entry.scope_kind == "global" else self.namespace_usings_by_file.setdefault(source_file, [])
                if entry not in bucket:
                    bucket.append(entry)
            elif using_kind == "static":
                bucket = self.global_static_usings if entry.scope_kind == "global" else self.static_usings_by_file.setdefault(source_file, [])
                if entry not in bucket:
                    bucket.append(entry)
            elif using_kind == "alias" and alias:
                if entry.scope_kind == "global":
                    bucket = self.global_aliases.setdefault(alias, [])
                else:
                    bucket = self.aliases_by_file.setdefault(source_file, {}).setdefault(alias, [])
                if entry not in bucket:
                    bucket.append(entry)
            elif using_kind == "extern_alias" and alias:
                bucket = self.extern_aliases_by_file.setdefault(source_file, [])
                if entry not in bucket:
                    bucket.append(entry)

    def _scope_chain(self, source_node):
        if not isinstance(source_node, dict):
            return []
        chain = _metadata(source_node.get("metadata")).get("scope_chain")
        return chain if isinstance(chain, list) else []

    def _using_in_scope(self, scope_kind, scope_id, source_node):
        if scope_kind in ("global", "file"):
            return True
        return scope_id is not None and scope_id in self._scope_chain(source_node)

    def _entry_in_scope(self, entry: CsharpImportEntry, source_node) -> bool:
        return self._using_in_scope(entry.scope_kind, entry.scope_id, source_node)

    def _alias_entries(self, label, source_file):
        entries = list(self.global_aliases.get(label, []))
        entries.extend(self.aliases_by_file.get(source_file, {}).get(label, []))
        return entries

    def _extern_alias_entries(self, label, source_file):
        return [
            entry for entry in self.extern_aliases_by_file.get(source_file, [])
            if entry.alias == label
        ]

    def _scopes_for(self, source_node, source_file):
        scopes = []
        _append_unique(scopes, _namespace(source_node))
        _append_unique(scopes, "")
        for entry in self.global_namespace_usings:
            _append_unique(scopes, entry.target_fqn)
        for entry in self.namespace_usings_by_file.get(source_file, []):
            if self._entry_in_scope(entry, source_node):
                _append_unique(scopes, entry.target_fqn)
        return scopes

    def _type_candidates(self, label, source_node, source_file):
        candidates = []
        for namespace in self._scopes_for(source_node, source_file):
            hit = self.type_def_index.get((namespace, label))
            if hit and hit not in candidates:
                candidates.append(hit)
        return candidates

    def _classify_alias_entry(self, entry: CsharpImportEntry, source_node, source_file) -> tuple[str | None, str | None, str | None]:
        base_fqn = _strip_trailing_csharp_generic_args(html.unescape(entry.target_fqn))
        if base_fqn in self.known_namespaces:
            return "namespace", base_fqn, None
        namespace, sep, simple_name = base_fqn.rpartition(".")
        if sep and self.type_def_index.get((namespace, simple_name)):
            return "type", namespace, simple_name
        if sep and namespace in self.known_namespaces:
            return "type", namespace, simple_name
        if not sep:
            candidates = self._type_candidates(simple_name or namespace, source_node, source_file)
            if len(candidates) == 1:
                node = self.node_by_id.get(candidates[0])
                return "type", _namespace(node), node.get("label") if node else None
        if entry.target_kind in ("type", "namespace"):
            return entry.target_kind, namespace if entry.target_kind == "type" else base_fqn, simple_name if entry.target_kind == "type" else None
        return None, None, None

    def is_alias_in_scope(self, label, source_node, source_file) -> bool:
        scoped = [
            entry for entry in self._alias_entries(label, source_file)
            if self._entry_in_scope(entry, source_node)
        ]
        scoped.extend(
            entry for entry in self._extern_alias_entries(label, source_file)
            if self._entry_in_scope(entry, source_node)
        )
        return bool(scoped)

    def using_static_in_scope(self, source_node, source_file) -> list[CsharpImportEntry]:
        entries = list(self.global_static_usings)
        entries.extend(
            entry for entry in self.static_usings_by_file.get(source_file, [])
            if self._entry_in_scope(entry, source_node)
        )
        return entries

    def namespace_may_bind(self, label, source_node, source_file) -> bool:
        for namespace in self._scopes_for(source_node, source_file):
            candidate = f"{namespace}.{label}" if namespace else label
            if candidate in self.known_namespaces:
                return True
        return False

    def qualifier_is_namespace_in_scope(self, qualifier, source_node, source_file) -> bool:
        if not isinstance(qualifier, str) or not qualifier:
            return False
        first, sep, rest = qualifier.partition(".")
        has_alias, alias_ns = self._alias_namespace_for_leading(first, source_node, source_file)
        if has_alias:
            if not alias_ns:
                return False
            candidate = f"{alias_ns}.{rest}" if rest else alias_ns
            return not rest or candidate in self.known_namespaces
        if qualifier in self.known_namespaces:
            return True
        return self.namespace_may_bind(first, source_node, source_file)

    def resolve_alias(self, label, source_node, source_file):
        entries = [
            entry for entry in self._alias_entries(label, source_file)
            if self._entry_in_scope(entry, source_node)
        ]
        if not entries:
            return None
        hits = set()
        for entry in entries:
            target_kind, namespace, simple_name = self._classify_alias_entry(entry, source_node, source_file)
            if target_kind != "type" or not simple_name:
                continue
            hit = self.type_def_index.get((namespace or "", simple_name))
            if hit:
                hits.add(hit)
        return next(iter(hits)) if len(hits) == 1 else None

    def resolve_label(self, label, source_node, source_file):
        if self.is_alias_in_scope(label, source_node, source_file):
            resolved = self.resolve_alias(label, source_node, source_file)
            return resolved
        candidates = self._type_candidates(label, source_node, source_file)
        return candidates[0] if len(candidates) == 1 else None

    def _alias_namespace_for_leading(self, qualifier, source_node, source_file) -> tuple[bool, str | None]:
        entries = [
            entry for entry in self._alias_entries(qualifier, source_file)
            if self._entry_in_scope(entry, source_node)
        ]
        entries.extend(
            entry for entry in self._extern_alias_entries(qualifier, source_file)
            if self._entry_in_scope(entry, source_node)
        )
        if not entries:
            return False, None
        hits = set()
        for entry in entries:
            if entry.is_extern:
                return True, None
            target_kind, namespace, simple_name = self._classify_alias_entry(entry, source_node, source_file)
            if target_kind == "namespace" and namespace:
                hits.add(namespace)
            else:
                return True, None
        return True, next(iter(hits)) if len(hits) == 1 else None

    def resolve_qualified(self, label, qualifier, source_node, source_file):
        if not isinstance(qualifier, str) or not qualifier:
            return None
        first, sep, rest = qualifier.partition(".")
        has_alias, alias_ns = self._alias_namespace_for_leading(first, source_node, source_file)
        if has_alias:
            if not alias_ns:
                return None
            qualifier = f"{alias_ns}.{rest}" if rest else alias_ns
        if qualifier in self.known_namespaces:
            return self.type_def_index.get((qualifier, label))
        return None


def build_csharp_name_resolver(all_nodes, all_edges):
    return CsharpNameResolver(all_nodes, all_edges)


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
    Name resolution is delegated to the shared CsharpNameResolver (#1562 lifted).
    """
    _ = (per_file, paths)

    resolver = build_csharp_name_resolver(all_nodes, all_edges)
    node_by_id = resolver.node_by_id
    aliases_by_file = resolver.aliases_by_file

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
            resolved = resolver.resolve_qualified(
                label, metadata.get("ref_qualifier"), source_node, source_file
            )
        else:
            resolved = resolver.resolve_label(label, source_node, source_file)
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


def _canonicalize_csharp_namespace_nodes(all_nodes: list[dict], all_edges: list[dict]) -> None:
    """Collapse duplicate C# namespace node entries to one canonical node per label."""
    by_label: dict[str, list[dict]] = {}
    for node in all_nodes:
        if node.get("type") != "namespace":
            continue
        label = node.get("label")
        if isinstance(label, str):
            by_label.setdefault(label, []).append(node)

    remap: dict[str, str] = {}
    drop_node_ids: set[int] = set()
    for group in by_label.values():
        if len(group) < 2:
            continue
        canonical = sorted(
            group,
            key=lambda node: (
                str(node.get("source_file") or ""),
                str(node.get("source_location") or ""),
                str(node.get("id") or ""),
            ),
        )[0]
        canonical_id = canonical.get("id")
        for node in group:
            if node is canonical:
                continue
            drop_node_ids.add(id(node))
            dup_id = node.get("id")
            if isinstance(dup_id, str) and isinstance(canonical_id, str):
                remap[dup_id] = canonical_id

    if remap:
        for edge in all_edges:
            if edge.get("source") in remap:
                edge["source"] = remap[str(edge["source"])]
            if edge.get("target") in remap:
                edge["target"] = remap[str(edge["target"])]

    if drop_node_ids:
        all_nodes[:] = [node for node in all_nodes if id(node) not in drop_node_ids]
