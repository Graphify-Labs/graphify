"""Deterministic Swift Package Manager manifest extraction."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from graphify.extractors.base import _file_stem, _make_id, _read_text


def _child(node, type_name: str):
    return next((c for c in node.children if c.type == type_name), None)


def _call_name(node, source: bytes) -> str:
    if node.type != "call_expression" or not node.children:
        return ""
    callee = node.children[0]
    if callee.type == "simple_identifier":
        return _read_text(callee, source).strip()
    if callee.type == "prefix_expression":
        ids = [c for c in callee.children if c.type == "simple_identifier"]
        return _read_text(ids[-1], source).strip() if ids else ""
    return ""


def _string_value(node, source: bytes) -> str | None:
    if node is None or node.type != "line_string_literal":
        return None
    text = _read_text(node, source).strip()
    return text[1:-1] if len(text) >= 2 and text[0] == text[-1] == '"' else text


def _string_array(node, source: bytes) -> list[str]:
    if node is None or node.type != "array_literal":
        return []
    out: list[str] = []
    for child in node.children:
        value = _string_value(child, source)
        if value is not None:
            out.append(value)
    return out


def _dependency_array(node, source: bytes) -> list[str]:
    """Target dependency strings plus `.product(name:)`/`.target(name:)` entries."""
    out = _string_array(node, source)
    if node is None or node.type != "array_literal":
        return out
    for child in node.children:
        if child.type != "call_expression":
            continue
        args = _arguments(child, source)
        name = _string_value(args.get("name"), source)
        if name:
            out.append(name)
    return out


def _arguments(call, source: bytes) -> dict[str, Any]:
    suffix = _child(call, "call_suffix")
    values = _child(suffix, "value_arguments") if suffix is not None else None
    out: dict[str, Any] = {}
    if values is None:
        return out
    for argument in values.children:
        if argument.type != "value_argument":
            continue
        name_node = argument.child_by_field_name("name")
        value_node = argument.child_by_field_name("value")
        if name_node is None or value_node is None:
            continue
        out[_read_text(name_node, source).strip()] = value_node
    return out


def _walk_calls(node):
    if node.type == "call_expression":
        yield node
    for child in node.children:
        yield from _walk_calls(child)


_SWIFTPM_SOURCE_SUFFIXES = frozenset({
    ".swift", ".c", ".h", ".cc", ".cpp", ".cxx", ".hpp",
    ".m", ".mm", ".s", ".S",
})


def link_swift_package_sources(per_file: list[dict], paths: list[Path]) -> None:
    """Link manifest targets to the already accepted extraction corpus.

    Source discovery must not walk the filesystem from a cached Package.swift
    result: doing so bypasses ignore rules and makes membership stale when a
    source is added or deleted without changing the manifest. This post-pass
    consumes only ``paths`` selected by the caller and re-evaluates target
    ``path``/``sources``/``exclude`` facts on every extraction.
    """
    memberships: dict[Path, list[dict[str, Any]]] = {}

    def _under(candidate: Path, root: Path) -> bool:
        try:
            candidate.relative_to(root)
            return True
        except ValueError:
            return False

    accepted: list[tuple[Path, Path, str]] = []
    for candidate, result in zip(paths, per_file):
        if (
            candidate.name == "Package.swift"
            or candidate.suffix not in _SWIFTPM_SOURCE_SUFFIXES
        ):
            continue
        expected_id = _make_id(str(candidate))
        file_node = next(
            (
                node
                for node in result.get("nodes", [])
                if str(node.get("id", "")) == expected_id
                and str(node.get("source_file", "")) == str(candidate)
            ),
            None,
        )
        if file_node is not None:
            accepted.append((candidate, candidate.resolve(), str(file_node["id"])))

    for result, manifest_path in zip(per_file, paths):
        specs = list(result.pop("swiftpm_targets", []) or [])
        target_ids = dict(result.pop("swiftpm_target_ids", {}) or {})
        if manifest_path.name != "Package.swift" or not specs:
            continue
        manifest_root = manifest_path.parent.resolve()
        seen_edges = {
            (str(edge.get("source")), str(edge.get("target")), str(edge.get("relation")))
            for edge in result.get("edges", [])
        }
        for spec in specs:
            name = str(spec.get("name", ""))
            target_nid = str(spec.get("nid", ""))
            if not name or not target_nid:
                continue
            explicit = spec.get("path")
            if explicit:
                source_root = (manifest_root / str(explicit)).resolve()
            elif spec.get("kind") == "testTarget":
                source_root = (manifest_root / "Tests" / name).resolve()
            else:
                source_root = (manifest_root / "Sources" / name).resolve()
            source_filters = [
                (source_root / str(value)).resolve()
                for value in spec.get("sources", []) or []
            ]
            excluded = [
                (source_root / str(value)).resolve()
                for value in spec.get("exclude", []) or []
            ]
            for _source_path, resolved_source, source_nid in accepted:
                if not _under(resolved_source, source_root):
                    continue
                if source_filters and not any(
                    resolved_source == selected or _under(resolved_source, selected)
                    for selected in source_filters
                ):
                    continue
                if any(
                    resolved_source == ignored or _under(resolved_source, ignored)
                    for ignored in excluded
                ):
                    continue
                key = (target_nid, source_nid, "contains")
                if key not in seen_edges:
                    seen_edges.add(key)
                    result.setdefault("edges", []).append({
                        "source": target_nid,
                        "target": source_nid,
                        "relation": "contains",
                        "context": "target_source",
                        "confidence": "EXTRACTED",
                        "confidence_score": 1.0,
                        "source_file": str(manifest_path),
                        "source_location": f"L{int(spec.get('line', 1))}",
                        "weight": 1.0,
                        "language": "swift",
                        "language_family": "native",
                    })
                memberships.setdefault(resolved_source, []).append({
                    "target_ids": target_ids,
                })

    # Internal imports use package-qualified target ids. Rewire only when the
    # importing file belongs unambiguously to one manifest; external imports keep
    # the existing shared module anchor.
    for result, source_path in zip(per_file, paths):
        owners = memberships.get(source_path.resolve(), [])
        if len(owners) != 1:
            continue
        target_ids = owners[0]["target_ids"]
        module_labels = {
            str(node.get("id")): str(node.get("label", ""))
            for node in result.get("nodes", [])
            if node.get("type") == "module"
        }
        rewired_old_ids: set[str] = set()
        for edge in result.get("edges", []):
            if edge.get("relation") != "imports":
                continue
            old_target = str(edge.get("target", ""))
            new_target = target_ids.get(module_labels.get(old_target, ""))
            if new_target and new_target != old_target:
                edge["target"] = new_target
                rewired_old_ids.add(old_target)
        if rewired_old_ids:
            referenced = {
                str(endpoint)
                for edge in result.get("edges", [])
                for endpoint in (edge.get("source"), edge.get("target"))
            }
            result["nodes"] = [
                node
                for node in result.get("nodes", [])
                if node.get("id") not in rewired_old_ids
                or str(node.get("id")) in referenced
            ]


def extract_swift_package_manifest(path: Path) -> dict:
    """Extract package, product, target, dependency and source membership edges."""
    try:
        from tree_sitter import Language, Parser
        import tree_sitter_swift

        source = path.read_bytes()
        root = Parser(Language(tree_sitter_swift.language())).parse(source).root_node
    except Exception as exc:
        return {"nodes": [], "edges": [], "error": str(exc)}

    str_path = str(path)
    nodes: list[dict] = []
    edges: list[dict] = []
    seen_nodes: set[str] = set()
    seen_edges: set[tuple[str, str, str]] = set()

    def add_node(nid: str, label: str, line: int, node_type: str, **extra: Any) -> None:
        if nid in seen_nodes:
            return
        seen_nodes.add(nid)
        node = {
            "id": nid,
            "label": label,
            "file_type": "code",
            "type": node_type,
            "source_file": str_path,
            "source_location": f"L{line}",
            "language": "swift",
            "language_family": "native",
        }
        node.update({k: v for k, v in extra.items() if v not in (None, "", [], {})})
        nodes.append(node)

    def add_edge(src: str, tgt: str, relation: str, line: int, context: str | None = None) -> None:
        key = (src, tgt, relation)
        if key in seen_edges:
            return
        seen_edges.add(key)
        edge = {
            "source": src,
            "target": tgt,
            "relation": relation,
            "confidence": "EXTRACTED",
            "confidence_score": 1.0,
            "source_file": str_path,
            "source_location": f"L{line}",
            "weight": 1.0,
            "language": "swift",
            "language_family": "native",
        }
        if context:
            edge["context"] = context
        edges.append(edge)

    file_nid = _make_id(str(path))
    add_node(file_nid, path.name, 1, "file")

    calls = list(_walk_calls(root))
    package_call = next((call for call in calls if _call_name(call, source) == "Package"), None)
    if package_call is None:
        return {
            "nodes": nodes,
            "edges": edges,
            "language": "swift",
            "language_family": "native",
        }
    package_args = _arguments(package_call, source)
    package_name = _string_value(package_args.get("name"), source) or path.parent.name
    package_nid = _make_id("pkg", package_name)
    add_node(package_nid, package_name, package_call.start_point[0] + 1, "package", ecosystem="swiftpm")
    add_edge(file_nid, package_nid, "contains", package_call.start_point[0] + 1)

    target_specs: dict[str, dict[str, Any]] = {}
    product_specs: list[tuple[str, str, list[str], int]] = []
    dependency_names: list[tuple[str, int]] = []
    for call in calls:
        kind = _call_name(call, source)
        args = _arguments(call, source)
        line = call.start_point[0] + 1
        if kind in (
            "target",
            "executableTarget",
            "testTarget",
            "systemLibrary",
            "binaryTarget",
            "plugin",
            "macro",
        ):
            name = _string_value(args.get("name"), source)
            if not name:
                continue
            target_specs[name] = {
                "kind": kind,
                "dependencies": _dependency_array(args.get("dependencies"), source),
                "path": _string_value(args.get("path"), source),
                "sources": _string_array(args.get("sources"), source),
                "exclude": _string_array(args.get("exclude"), source),
                "line": line,
            }
        elif kind in ("library", "executable"):
            name = _string_value(args.get("name"), source)
            if name:
                product_specs.append((kind, name, _string_array(args.get("targets"), source), line))
        elif kind == "package":
            raw = (
                _string_value(args.get("name"), source)
                or _string_value(args.get("id"), source)
                or _string_value(args.get("url"), source)
                or _string_value(args.get("path"), source)
            )
            if raw:
                tail = raw.rstrip("/").rsplit("/", 1)[-1]
                dependency_names.append((tail.removesuffix(".git"), line))

    manifest_scope = _file_stem(path)
    target_nids = {
        name: _make_id(manifest_scope, "swift_target", name)
        for name in target_specs
    }
    for name, spec in target_specs.items():
        target_nid = target_nids[name]
        add_node(
            target_nid,
            name,
            int(spec["line"]),
            "module",
            swiftpm_kind=spec["kind"],
            package=package_name,
        )
        add_edge(package_nid, target_nid, "contains", int(spec["line"]), context="target")
        for dep in spec["dependencies"]:
            if dep not in target_specs:
                dependency_nid = _make_id("swift_external_module", dep)
                add_node(
                    dependency_nid,
                    dep,
                    int(spec["line"]),
                    "module",
                    swiftpm_kind="dependency",
                    external=True,
                )
            else:
                dependency_nid = target_nids[dep]
            add_edge(
                target_nid,
                dependency_nid,
                "depends_on",
                int(spec["line"]),
                context="target_dependency",
            )

    for kind, name, targets, line in product_specs:
        product_nid = _make_id(manifest_scope, "swift_product", name)
        add_node(product_nid, name, line, "product", swiftpm_kind=kind, package=package_name)
        add_edge(package_nid, product_nid, "contains", line, context="product")
        for target in targets:
            target_nid = target_nids.get(target)
            if target_nid is None:
                target_nid = _make_id("swift_external_module", target)
                add_node(
                    target_nid,
                    target,
                    line,
                    "module",
                    swiftpm_kind="dependency",
                    external=True,
                )
            add_edge(product_nid, target_nid, "contains", line, context="product_target")

    for dependency, line in dependency_names:
        dependency_nid = _make_id("pkg", dependency)
        add_node(
            dependency_nid,
            dependency,
            line,
            "package",
            ecosystem="swiftpm",
            external=True,
        )
        add_edge(package_nid, dependency_nid, "depends_on", line, context="dependency")

    return {
        "nodes": nodes,
        "edges": edges,
        "swiftpm_targets": [
            {
                "name": name,
                "nid": target_nids[name],
                "kind": spec["kind"],
                "path": spec.get("path"),
                "sources": list(spec.get("sources") or []),
                "exclude": list(spec.get("exclude") or []),
                "line": int(spec["line"]),
            }
            for name, spec in target_specs.items()
        ],
        "swiftpm_target_ids": target_nids,
        "language": "swift",
        "language_family": "native",
    }
