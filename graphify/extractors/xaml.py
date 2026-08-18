"""XAML extractor. Moved verbatim from graphify/extract.py."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from graphify.extractors.base import (
    _PROJECT_XML_MAX_BYTES,
    _file_stem,
    _make_id,
    _project_xml_is_safe,
)
from graphify.extractors.csharp import extract_csharp


def _xml_local_name(name: str) -> str:
    return name.rsplit("}", 1)[-1] if name.startswith("{") else name


# A .NET event handler has the signature `(object sender, <T>EventArgs e)`. Used
# to tell a real event handler in the code-behind apart from an ordinary method
# whose name a XAML attribute value happens to match. Tolerates `object?`, a
# namespace-qualified args type, and a generic `EventArgs<T>`.
_EVENT_HANDLER_SIGNATURE_RE = re.compile(
    r"\(\s*object\??\s+\w+\s*,\s*[\w.]*EventArgs(?:<[^>]*>)?\s+\w+\s*\)"
)

# XAML attribute names that carry free-form strings or identifiers and never name
# an event handler. They are skipped when matching attribute values to code-behind
# methods so e.g. Content="Save" or Tag="Refresh" can't fabricate an event edge.
_XAML_NON_EVENT_ATTRS = frozenset({
    "Name", "Content", "Text", "Title", "Tag", "ToolTip", "Header",
    "Class", "Key", "Uid", "DataContext", "Style", "Source",
})

# A handler attribute value is a bare method name (e.g. Click="Save_Click"), not
# markup, a path, or a sentence. Used to skip values like "{Binding ...}" or
# free-form content before looking them up as code-behind methods.
_XAML_IDENT_RE = re.compile(r"[A-Za-z_]\w*")
_XAML_DESIGN_INSTANCE_TYPE_RE = re.compile(
    r"\bType\s*=\s*(?:\{x:Type\s+)?(?P<type>[\w.:+]+)"
)


def _xaml_markup_extension(value: str) -> tuple[str, str] | None:
    value = value.strip()
    if not (value.startswith("{") and value.endswith("}")):
        return None
    inner = value[1:-1].strip()
    if not inner or inner.startswith("}"):
        return None
    name, _, args = inner.partition(" ")
    return name, args.strip()


def _xaml_split_markup_args(args: str) -> list[str]:
    parts: list[str] = []
    start = 0
    depth = 0
    for idx, ch in enumerate(args):
        if ch == "{":
            depth += 1
        elif ch == "}" and depth:
            depth -= 1
        elif ch == "," and depth == 0:
            parts.append(args[start:idx].strip())
            start = idx + 1
    tail = args[start:].strip()
    if tail:
        parts.append(tail)
    return parts


def _xaml_static_resource_key(value: str) -> str | None:
    markup = _xaml_markup_extension(value)
    if not markup:
        return None
    name, args = markup
    if name != "StaticResource":
        return None
    for part in _xaml_split_markup_args(args):
        if "=" not in part:
            return part.strip() or None
        key, resource = part.split("=", 1)
        if key.strip() == "ResourceKey":
            return resource.strip() or None
    return None


def _xaml_binding_refs(value: str) -> tuple[str | None, str | None]:
    markup = _xaml_markup_extension(value)
    if not markup:
        return None, None
    name, args = markup
    if name != "Binding":
        return None, None

    path_ref = None
    converter_ref = None
    for part in _xaml_split_markup_args(args):
        if not part:
            continue
        if "=" not in part:
            if path_ref is None:
                path_ref = part.strip()
            continue
        key, raw_value = part.split("=", 1)
        key = key.strip()
        raw_value = raw_value.strip()
        if key == "Path":
            path_ref = raw_value
        elif key == "Converter":
            converter_ref = _xaml_static_resource_key(raw_value)

    if path_ref and ("{" in path_ref or "}" in path_ref):
        path_ref = None
    return path_ref or None, converter_ref or None


def _xaml_codebehind_path(path: Path) -> Path | None:
    expected = path.with_suffix(path.suffix + ".cs")
    if expected.exists():
        return expected
    try:
        for sibling in path.parent.iterdir():
            if sibling.name.casefold() == expected.name.casefold():
                return sibling
    except OSError:
        return None
    return None


def _xaml_codebehind_symbols(
    path: Path,
    class_name: str | None,
) -> tuple[dict | None, dict[str, dict], list[dict]]:
    codebehind = _xaml_codebehind_path(path)
    if not codebehind:
        return None, {}, []
    result = extract_csharp(codebehind)
    if result.get("error"):
        return None, {}, []

    class_simple = class_name.rsplit(".", 1)[-1] if class_name else None
    class_node = None
    if class_simple:
        for node in result.get("nodes", []):
            if node.get("label") == class_simple:
                class_node = node
                break

    class_method_edges: list[dict] = []
    if class_node:
        class_id = class_node.get("id")
        for edge in result.get("edges", []):
            if edge.get("source") == class_id and edge.get("relation") == "method":
                class_method_edges.append(edge)
    method_ids = {edge.get("target") for edge in class_method_edges} if class_node else None

    # Only methods with a .NET event-handler signature -- (object sender,
    # <T>EventArgs e) -- are eligible to be wired to a XAML attribute as an
    # event. Without this gate, any attribute whose value happens to match a
    # method name (e.g. Content="Save" next to a business method Save()) would
    # produce a spurious "event" edge. The C# extractor does not record the
    # parameter list on method nodes, so we read it from the code-behind source
    # at the method's recorded line.
    try:
        cb_lines = codebehind.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        cb_lines = []

    def _has_event_handler_signature(node: dict) -> bool:
        loc = str(node.get("source_location") or "")
        m = re.match(r"L(\d+)", loc)
        if not m or not cb_lines:
            return False
        start = int(m.group(1)) - 1
        # Join a few lines so a signature split across lines still matches.
        snippet = " ".join(cb_lines[start:start + 3])
        return _EVENT_HANDLER_SIGNATURE_RE.search(snippet) is not None

    methods: dict[str, dict] = {}
    for node in result.get("nodes", []):
        if method_ids is not None and node.get("id") not in method_ids:
            continue
        label = str(node.get("label", ""))
        if label.startswith(".") and label.endswith("()") and _has_event_handler_signature(node):
            methods[label.strip("()").lstrip(".")] = node
    return class_node, methods, class_method_edges


def _xaml_type_simple_name(type_ref: str) -> str | None:
    type_ref = type_ref.strip().strip("{}")
    if not type_ref:
        return None
    type_ref = type_ref.split(",", 1)[0].strip()
    if type_ref.startswith("x:Type "):
        type_ref = type_ref[len("x:Type "):].strip()
    if ":" in type_ref:
        type_ref = type_ref.rsplit(":", 1)[-1]
    if "." in type_ref:
        type_ref = type_ref.rsplit(".", 1)[-1]
    if "+" in type_ref:
        type_ref = type_ref.rsplit("+", 1)[-1]
    return type_ref if _XAML_IDENT_RE.fullmatch(type_ref) else None


def _xaml_explicit_viewmodel_names(tree) -> tuple[bool, list[str]]:
    has_data_context = False
    names: list[str] = []
    for elem in tree.iter():
        elem_type = _xml_local_name(elem.tag)
        if elem_type.endswith(".DataContext") or elem_type == "DataContext":
            has_data_context = True
            for child in list(elem):
                vm_name = _xaml_type_simple_name(_xml_local_name(child.tag))
                if vm_name and vm_name not in names:
                    names.append(vm_name)
        for key, value in elem.attrib.items():
            if _xml_local_name(key) != "DataContext" or not value:
                continue
            has_data_context = True
            match = _XAML_DESIGN_INSTANCE_TYPE_RE.search(value)
            if match:
                vm_name = _xaml_type_simple_name(match.group("type"))
                if vm_name and vm_name not in names:
                    names.append(vm_name)
    return has_data_context, names


def _xaml_prism_autowire_viewmodel(tree) -> bool:
    for elem in tree.iter():
        for key, value in elem.attrib.items():
            if (
                _xml_local_name(key).endswith("ViewModelLocator.AutoWireViewModel")
                and value.strip().lower() == "true"
            ):
                return True
    return False


def _xaml_inferred_viewmodel_names(view_name: str | None) -> list[str]:
    if not view_name:
        return []
    names: list[str] = []

    def add(name: str) -> None:
        if name.endswith("ViewModel") and name not in names:
            names.append(name)

    if view_name == "MainWindow":
        add("MainWindowViewModel")
        add("MainViewModel")
    for suffix in ("UserControl", "View", "Page", "Control"):
        if view_name.endswith(suffix) and len(view_name) > len(suffix):
            add(view_name[:-len(suffix)] + "ViewModel")
            break
    return names


def _xaml_project_root(path: Path) -> Path:
    project_markers = (".csproj", ".fsproj", ".vbproj", ".sln", ".slnx")
    root = path.parent
    for directory in (path.parent, *path.parent.parents):
        try:
            if any(child.suffix in project_markers for child in directory.iterdir()):
                root = directory
                break
        except OSError:
            continue
    if _XAML_ACTIVE_EXTRACT_ROOT is None:
        return root
    boundary = _XAML_ACTIVE_EXTRACT_ROOT.resolve()
    try:
        root.resolve().relative_to(boundary)
        return root
    except ValueError:
        return boundary


def _xaml_csharp_class_nodes(path: Path) -> dict[str, list[dict]]:
    from graphify.detect import _is_ignored, _is_noise_dir, _load_graphifyignore
    root = _xaml_project_root(path)
    cache_key = str(root.resolve()) if _XAML_ACTIVE_EXTRACT_ROOT is not None else None
    if cache_key and cache_key in _XAML_CSHARP_CLASS_CACHE:
        return _XAML_CSHARP_CLASS_CACHE[cache_key]
    classes: dict[str, list[dict]] = {}
    patterns = _load_graphifyignore(root)
    ignore_cache: dict[Path, bool] = {}
    # Prune noise/hidden dirs DURING traversal (not after) so the scan never
    # descends into node_modules/.venv/.git/build/..., and CAP the number of
    # directories visited. rglob("*.cs") used to walk the entire tree first,
    # which on a mis-resolved or huge root (e.g. a .xaml under a shared temp dir
    # or a giant monorepo, where _xaml_project_root climbs to a broad ancestor)
    # scanned millions of paths and effectively hung. A real .NET project sits
    # well under the cap; a runaway root is bounded to a fast, partial scan
    # instead of hanging.
    import os as _os
    _DIR_CAP = 20000
    cs_files: list[Path] = []
    visited = 0
    try:
        for dirpath, dirnames, filenames in _os.walk(root):
            dirnames[:] = [
                d for d in dirnames if not d.startswith(".") and not _is_noise_dir(d)
            ]
            for fn in filenames:
                if fn.endswith(".cs"):
                    cs_files.append(Path(dirpath) / fn)
            visited += 1
            if visited >= _DIR_CAP:
                break
    except OSError:
        return classes
    cs_files.sort()
    for cs_path in cs_files:
        if patterns and _is_ignored(cs_path, root, patterns, _cache=ignore_cache):
            continue
        result = extract_csharp(cs_path)
        if result.get("error"):
            continue
        for node in result.get("nodes", []):
            label = str(node.get("label", ""))
            if not label.endswith("ViewModel") or not _XAML_IDENT_RE.fullmatch(label):
                continue
            if node.get("source_file"):
                classes.setdefault(label, []).append(node)
    if cache_key:
        _XAML_CSHARP_CLASS_CACHE[cache_key] = classes
    return classes


def _xaml_pascal_name(name: str) -> str | None:
    name = name.strip().lstrip("_")
    if name.startswith("m_"):
        name = name[2:]
    return name[:1].upper() + name[1:] if _XAML_IDENT_RE.fullmatch(name) else None


_XAML_TOOLKIT_FIELD_RE = re.compile(r"\b(?P<name>_?m?_?[A-Za-z_]\w*)\s*(?:=.*)?;")
_XAML_TOOLKIT_METHOD_RE = re.compile(r"\b(?P<name>[A-Za-z_]\w*)\s*\(")
_XAML_ACTIVE_EXTRACT_ROOT: Path | None = None
_XAML_CSHARP_CLASS_CACHE: dict[str, dict[str, list[dict]]] = {}


def _xaml_communitytoolkit_members(vm_node: dict) -> tuple[dict[str, dict], list[dict]]:
    source_file = vm_node.get("source_file")
    vm_id = vm_node.get("id")
    if not source_file or not vm_id:
        return {}, []
    try:
        # errors="replace" so a non-UTF8 code-behind can't raise UnicodeDecodeError
        # and abort the whole extract_xaml (matches every other reader here).
        lines = Path(source_file).read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return {}, []

    members: dict[str, dict] = {}
    edges: list[dict] = []

    def add_member(label: str, line_no: int, context: str) -> None:
        nid = _make_id(vm_id, label)
        members[label] = {
            "id": nid,
            "label": label,
            "file_type": "code",
            "source_file": source_file,
            "source_location": f"L{line_no}",
        }
        edges.append({
            "source": vm_id,
            "target": nid,
            "relation": "defines",
            "confidence": "INFERRED",
            "source_file": source_file,
            "source_location": f"L{line_no}",
            "weight": 1.0,
            "context": context,
        })

    pending: tuple[str, int] | None = None
    for line_no, line in enumerate(lines, 1):
        remainder = line.split("]", 1)[1].strip() if "]" in line else ""
        if "[" in line and "ObservableProperty" in line:
            pending = ("property", line_no)
            if not remainder:
                continue
            line = remainder
        if "[" in line and "RelayCommand" in line:
            pending = ("command", line_no)
            if not remainder:
                continue
            line = remainder
        if not pending or not line.strip() or line.lstrip().startswith("["):
            continue

        kind, attr_line = pending
        pending = None
        if kind == "property":
            match = _XAML_TOOLKIT_FIELD_RE.search(line)
            label = _xaml_pascal_name(match.group("name")) if match else None
            if label:
                add_member(label, attr_line, "communitytoolkit_observable_property")
        else:
            match = _XAML_TOOLKIT_METHOD_RE.search(line)
            if match:
                method = match.group("name").removesuffix("Async")
                add_member(f"{method}Command", attr_line, "communitytoolkit_relay_command")

    return members, edges


def extract_xaml(path: Path) -> dict:
    """Extract WPF/XAML structure, bindings, x:Class, and event handler references."""
    import xml.etree.ElementTree as ET

    try:
        src = path.read_bytes()
    except OSError:
        return {"nodes": [], "edges": [], "error": f"cannot read {path}"}

    if len(src) > _PROJECT_XML_MAX_BYTES:
        return {"nodes": [], "edges": [], "error": "xaml file too large"}
    if not _project_xml_is_safe(src):
        return {"nodes": [], "edges": [],
                "error": "refusing XML with DOCTYPE/ENTITY declaration"}

    try:
        tree = ET.fromstring(src)
    except ET.ParseError as e:
        return {"nodes": [], "edges": [], "error": f"XML parse error: {e}"}

    text = src.decode("utf-8", errors="replace")
    lines = text.splitlines()
    str_path = str(path)
    stem = _file_stem(path)
    file_nid = _make_id(str(path))
    root_type = _xml_local_name(tree.tag)
    root_nid = _make_id(stem, root_type)
    nodes: list[dict] = []
    edges: list[dict] = []
    seen_ids: set[str] = set()
    seen_edges: set[tuple[str, str, str, str | None]] = set()

    def line_for(value: str | None) -> int:
        if value:
            for idx, line in enumerate(lines, 1):
                if value in line:
                    return idx
        return 1

    def add_node(
        nid: str,
        label: str,
        line: int | None,
        *,
        file_type: str = "code",
        source_file: str = str_path,
    ) -> None:
        if nid in seen_ids:
            return
        seen_ids.add(nid)
        nodes.append({
            "id": nid, "label": label, "file_type": file_type,
            "source_file": source_file,
            "source_location": f"L{line}" if line else None,
        })

    def add_existing_node(node: dict | None) -> None:
        if not node:
            return
        nid = node.get("id")
        if not nid or nid in seen_ids:
            return
        seen_ids.add(nid)
        nodes.append(dict(node))

    def add_edge(
        src_nid: str,
        tgt_nid: str,
        relation: str,
        line: int,
        *,
        context: str | None = None,
        source_file: str = str_path,
        confidence: str = "EXTRACTED",
    ) -> None:
        key = (src_nid, tgt_nid, relation, context)
        if key in seen_edges:
            return
        seen_edges.add(key)
        edge = {
            "source": src_nid, "target": tgt_nid, "relation": relation,
            "confidence": confidence, "source_file": source_file,
            "source_location": f"L{line}", "weight": 1.0,
        }
        if context:
            edge["context"] = context
        edges.append(edge)

    def add_existing_edge(edge: dict) -> None:
        key = (edge.get("source"), edge.get("target"), edge.get("relation"), edge.get("context"))
        if key in seen_edges:
            return
        seen_edges.add(key)
        edges.append(dict(edge))

    add_node(file_nid, path.name, 1)
    add_node(root_nid, root_type, 1)
    add_edge(file_nid, root_nid, "contains", 1)

    class_name = None
    for key, value in tree.attrib.items():
        if _xml_local_name(key) == "Class" and value:
            class_name = value.strip()
            break

    class_node, codebehind_methods, class_method_edges = _xaml_codebehind_symbols(path, class_name)
    if class_name:
        if class_node:
            class_nid = class_node["id"]
            add_existing_node(class_node)
        else:
            class_label = class_name.rsplit(".", 1)[-1]
            class_nid = _make_id(stem, class_label)
            add_node(class_nid, class_label, line_for(class_name))
        add_edge(root_nid, class_nid, "references", line_for(class_name), context="x_class")

    has_data_context, vm_names = _xaml_explicit_viewmodel_names(tree)
    prism_autowire = _xaml_prism_autowire_viewmodel(tree)
    vm_confidence = "EXTRACTED"
    if not has_data_context:
        view_name = class_name.rsplit(".", 1)[-1] if class_name else None
        view_name = view_name or (path.stem if prism_autowire else None)
        vm_names = _xaml_inferred_viewmodel_names(view_name)
        vm_confidence = "INFERRED"
    generated_members: dict[str, dict] = {}
    generated_member_edges: list[dict] = []
    if vm_names:
        csharp_classes = _xaml_csharp_class_nodes(path)
        vm_candidates = []
        for vm_name in vm_names:
            vm_candidates.extend(csharp_classes.get(vm_name, []))
        by_id = {node.get("id"): node for node in vm_candidates if node.get("id")}
        if len(by_id) == 1:
            vm_node = next(iter(by_id.values()))
            add_existing_node(vm_node)
            add_edge(
                root_nid,
                vm_node["id"],
                "references",
                line_for(vm_node["label"]),
                context="view_model",
                confidence=vm_confidence,
            )
            generated_members, generated_member_edges = _xaml_communitytoolkit_members(vm_node)
            for member in generated_members.values():
                add_existing_node(member)
            for member_edge in generated_member_edges:
                add_existing_edge(member_edge)

    for elem in tree.iter():
        elem_type = _xml_local_name(elem.tag)
        elem_name = None
        for key, value in elem.attrib.items():
            if _xml_local_name(key) == "Name" and value:
                elem_name = value.strip()
                break
        owner_nid = root_nid
        if elem_name:
            owner_nid = _make_id(stem, elem_name)
            add_node(owner_nid, elem_name, line_for(elem_name))
            add_edge(root_nid, owner_nid, "contains", line_for(elem_name))
            type_nid = _make_id("xaml", elem_type)
            add_node(type_nid, elem_type, line_for(elem_name), file_type="concept")
            add_edge(owner_nid, type_nid, "references", line_for(elem_name), context="type")

        for key, value in elem.attrib.items():
            value = value or ""
            # Event wiring: an attribute references a handler only when its local
            # name isn't a known free-form/identity property, its value is a bare
            # identifier (a method name, not markup or a sentence), and the matched
            # code-behind method actually has an event-handler signature (the gate
            # in _xaml_codebehind_symbols). This stops Content="Save" / Tag="..."
            # from fabricating event edges against same-named ordinary methods.
            attr_local = _xml_local_name(key)
            if attr_local not in _XAML_NON_EVENT_ATTRS and _XAML_IDENT_RE.fullmatch(value):
                method = codebehind_methods.get(value)
                if method:
                    add_existing_node(method)
                    add_edge(owner_nid, method["id"], "references", line_for(value), context="event")
                    for method_edge in class_method_edges:
                        if method_edge.get("target") == method["id"]:
                            add_existing_node(class_node)
                            add_existing_edge(method_edge)
                            break
            binding_path, binding_converter = _xaml_binding_refs(value)
            if binding_path:
                bind_nid = _make_id("binding", binding_path)
                add_node(bind_nid, binding_path, line_for(value), file_type="concept")
                binding_context = (
                    "binding_command"
                    if attr_local == "Command" or attr_local.endswith(".Command")
                    else "binding_path"
                )
                add_edge(owner_nid, bind_nid, "references", line_for(value), context=binding_context)
                generated_member = generated_members.get(binding_path)
                if generated_member:
                    add_existing_node(generated_member)
                    add_edge(
                        owner_nid,
                        generated_member["id"],
                        "references",
                        line_for(value),
                        context=binding_context,
                        confidence="INFERRED",
                    )
            if binding_converter:
                converter_nid = _make_id("binding_converter", binding_converter)
                add_node(converter_nid, binding_converter, line_for(value), file_type="concept")
                add_edge(owner_nid, converter_nid, "references", line_for(value), context="binding_converter")
            if elem_type == "Binding" and attr_local == "Path":
                direct_path = value.strip()
                if direct_path and "{" not in direct_path and "}" not in direct_path:
                    bind_nid = _make_id("binding", direct_path)
                    add_node(bind_nid, direct_path, line_for(value), file_type="concept")
                    add_edge(owner_nid, bind_nid, "references", line_for(value), context="binding_path")
            if elem_type == "Binding" and attr_local == "Converter":
                direct_converter = _xaml_static_resource_key(value)
                if direct_converter:
                    converter_nid = _make_id("binding_converter", direct_converter)
                    add_node(converter_nid, direct_converter, line_for(value), file_type="concept")
                    add_edge(owner_nid, converter_nid, "references", line_for(value), context="binding_converter")

    return {"nodes": nodes, "edges": edges}
