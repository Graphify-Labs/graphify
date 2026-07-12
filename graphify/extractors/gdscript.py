"""GDScript extractor for Godot ``.gd`` source files."""
from __future__ import annotations

import os

from pathlib import Path
from typing import Any

from graphify.extractors.base import _file_stem, _make_id, _read_text


# Engine-provided base and value types are useful while parsing, but they are not
# project definitions. Suppressing their stubs prevents ubiquitous Godot types
# from becoming misleading graph hubs.
_GDSCRIPT_BUILTIN_TYPES = frozenset({
    "Object", "RefCounted", "Reference", "Resource", "Node", "Node2D", "Node3D",
    "Control", "CanvasItem", "Spatial", "Sprite", "Sprite2D", "Sprite3D",
    "Area2D", "Area3D", "RigidBody2D", "RigidBody3D", "CharacterBody2D",
    "CharacterBody3D", "StaticBody2D", "StaticBody3D", "CollisionShape2D",
    "CollisionShape3D", "Camera2D", "Camera3D", "Button", "Label", "Panel",
    "Timer", "Tween", "AnimationPlayer", "SceneTree", "Viewport", "Window",
    "String", "StringName", "NodePath", "Variant", "RID", "Callable", "Signal",
    "Vector2", "Vector2i", "Vector3", "Vector3i", "Vector4", "Vector4i",
    "Color", "Rect2", "Rect2i", "Transform2D", "Transform3D", "Basis",
    "Quaternion", "Plane", "AABB", "Projection", "Array", "Dictionary",
    "PackedByteArray", "PackedInt32Array", "PackedInt64Array",
    "PackedFloat32Array", "PackedFloat64Array", "PackedStringArray",
    "PackedVector2Array", "PackedVector3Array", "PackedColorArray",
    "Thread", "Mutex", "Semaphore", "Image", "RegEx", "RandomNumberGenerator",
    "StreamPeer", "StreamPeerBuffer", "FileAccess", "DirAccess", "JSON",
    "Time", "OS", "Engine", "Input",
})

# Built-in functions and common Object/Node methods are not project call targets.
_GDSCRIPT_CALL_SKIP = frozenset({
    "preload", "load", "print", "printerr", "print_debug", "push_error",
    "push_warning", "assert", "range", "len", "str", "int", "float", "bool",
    "abs", "min", "max", "clamp", "round", "floor", "ceil", "sign", "sqrt",
    "super", "connect", "emit", "call", "call_deferred", "get_node", "has_node",
    "instantiate", "instance", "queue_free", "is_instance_valid",
})


def _gdscript_project_root(path: Path) -> Path | None:
    """Return the directory that owns ``project.godot`` for ``path``."""
    for ancestor in path.parents:
        try:
            if (ancestor / "project.godot").is_file():
                return ancestor
        except OSError:
            continue
    return None


def extract_gdscript(path: Path) -> dict:
    """Extract declarations and high-confidence relationships from GDScript.

    A script with ``class_name`` gets a named class node; otherwise its file node
    acts as the implicit script class. The extractor records functions, members,
    signals, enums, inner classes, inheritance, resource loads, local calls, and
    ``Type.new()`` instantiations. Unresolved bare calls are left for Graphify's
    ambiguity-aware cross-file resolver.
    """
    try:
        from tree_sitter_language_pack import get_parser
    except ImportError:
        return {
            "nodes": [],
            "edges": [],
            "error": "tree_sitter_language_pack not installed",
        }

    try:
        source = path.read_bytes()
        tree = get_parser("gdscript").parse(source)
        root = tree.root_node
    except Exception as exc:
        return {"nodes": [], "edges": [], "error": str(exc)}

    stem = _file_stem(path)
    str_path = str(path)
    nodes: list[dict] = []
    edges: list[dict] = []
    raw_calls: list[dict] = []
    seen_ids: set[str] = set()
    seen_edges: set[tuple[str, str, str]] = set()
    function_bodies: list[tuple[str, str, Any]] = []
    functions_by_container: dict[str, dict[str, list[str]]] = {}

    def add_node(
        nid: str,
        label: str,
        line: int | None,
        *,
        source_file: str | None = str_path,
        callable_node: bool = False,
    ) -> None:
        if not nid or nid in seen_ids:
            return
        seen_ids.add(nid)
        node = {
            "id": nid,
            "label": label,
            "file_type": "code",
            "source_file": source_file,
            "source_location": f"L{line}" if line else None,
        }
        if callable_node:
            node["_callable"] = True
        nodes.append(node)

    def add_edge(
        source_nid: str,
        target_nid: str,
        relation: str,
        line: int | None,
        *,
        context: str | None = None,
    ) -> None:
        if not source_nid or not target_nid or source_nid == target_nid:
            return
        key = (source_nid, target_nid, relation)
        if key in seen_edges:
            return
        seen_edges.add(key)
        edge = {
            "source": source_nid,
            "target": target_nid,
            "relation": relation,
            "confidence": "EXTRACTED",
            "confidence_score": 1.0,
            "source_file": str_path,
            "source_location": f"L{line}" if line else None,
            "weight": 1.0,
        }
        if context:
            edge["context"] = context
        edges.append(edge)

    def child(node, field: str, node_type: str | None = None):
        found = node.child_by_field_name(field)
        if found is not None:
            return found
        expected = node_type or field
        return next((item for item in node.children if item.type == expected), None)

    def name_text(node) -> str:
        name_node = child(node, "name")
        return _read_text(name_node, source) if name_node is not None else ""

    def type_name(type_node) -> str:
        """Return the most specific identifier in a GDScript type expression."""
        identifiers: list[str] = []

        def walk(node) -> None:
            if node.type == "identifier":
                identifiers.append(_read_text(node, source))
            for item in node.named_children:
                walk(item)

        walk(type_node)
        if identifiers:
            return identifiers[-1]
        return _read_text(type_node, source).split(".")[-1].strip()

    file_nid = _make_id(str(path))
    add_node(file_nid, path.name, 1)
    project_root = _gdscript_project_root(path)

    def resolve_resource(ref: str) -> str | None:
        """Resolve a Godot resource path to the target file node when it exists."""
        ref = ref.strip().strip('"').strip("'")
        if not ref or ref.startswith("user://"):
            return None
        if ref.startswith("res://"):
            if project_root is None:
                return None
            target = project_root / ref[len("res://"):]
        elif "://" in ref:
            return None
        else:
            target = path.parent / ref
        try:
            if target.is_file():
                # Keep lexical path identity so this ID matches the target's own
                # file node even when an ancestor is a symlink.
                return _make_id(os.path.normpath(str(target)))
        except OSError:
            pass
        return None

    class_name = ""
    class_line = 1
    extends_node = None
    for item in root.children:
        if item.type == "class_name_statement":
            class_name = name_text(item)
            class_line = item.start_point[0] + 1
        elif item.type == "extends_statement":
            extends_node = item

    if class_name:
        script_nid = _make_id(stem, class_name)
        add_node(script_nid, class_name, class_line)
        add_edge(file_nid, script_nid, "defines", class_line)
    else:
        script_nid = file_nid

    if extends_node is not None:
        line = extends_node.start_point[0] + 1
        base_type = child(extends_node, "type")
        if base_type is not None:
            base_name = type_name(base_type)
            if base_name and base_name not in _GDSCRIPT_BUILTIN_TYPES:
                # Keep unresolved type IDs out of the file-node namespace. A
                # class named Actor commonly lives in actor.gd; using bare
                # ``actor`` for both would make collision disambiguation treat
                # the stub as the file node before the shared rewire pass runs.
                base_nid = _make_id("gdscript_type", base_name)
                add_node(base_nid, base_name, None, source_file=None)
                add_edge(script_nid, base_nid, "inherits", line)
        else:
            path_node = next(
                (item for item in extends_node.named_children if item.type == "string"),
                None,
            )
            if path_node is not None:
                target_nid = resolve_resource(_read_text(path_node, source))
                if target_nid:
                    add_edge(
                        script_nid,
                        target_nid,
                        "inherits",
                        line,
                        context="extends_path",
                    )

    def add_type_reference(container_nid: str, type_node, line: int) -> None:
        if type_node is None:
            return
        referenced_type = type_name(type_node)
        if (
            not referenced_type
            or not referenced_type[:1].isupper()
            or referenced_type in _GDSCRIPT_BUILTIN_TYPES
        ):
            return
        type_nid = _make_id("gdscript_type", referenced_type)
        add_node(type_nid, referenced_type, None, source_file=None)
        add_edge(
            container_nid,
            type_nid,
            "references",
            line,
            context="member_type",
        )

    def handle_declaration(node, container_nid: str) -> None:
        line = node.start_point[0] + 1

        if node.type == "function_definition":
            function_name = name_text(node)
            if not function_name:
                return
            function_nid = _make_id(container_nid, function_name)
            add_node(
                function_nid,
                f"{function_name}()",
                line,
                callable_node=True,
            )
            relation = "contains" if container_nid == file_nid else "method"
            add_edge(container_nid, function_nid, relation, line)
            functions_by_container.setdefault(container_nid, {}).setdefault(
                function_name, []
            ).append(function_nid)
            body = child(node, "body")
            if body is not None:
                function_bodies.append((function_nid, container_nid, body))
            return

        if node.type in ("variable_statement", "const_statement"):
            member_name = name_text(node)
            if not member_name:
                return
            member_nid = _make_id(container_nid, member_name)
            add_node(member_nid, member_name, line)
            add_edge(container_nid, member_nid, "defines", line)
            add_type_reference(container_nid, child(node, "type"), line)
            return

        if node.type == "signal_statement":
            signal_name = name_text(node)
            if not signal_name:
                return
            signal_nid = _make_id(container_nid, "signal", signal_name)
            add_node(signal_nid, signal_name, line)
            add_edge(
                container_nid,
                signal_nid,
                "defines",
                line,
                context="signal",
            )
            return

        if node.type == "enum_definition":
            enum_name = name_text(node)
            if not enum_name:
                return
            enum_nid = _make_id(container_nid, enum_name)
            add_node(enum_nid, enum_name, line)
            add_edge(container_nid, enum_nid, "defines", line)
            enum_body = child(node, "body", "enumerator_list")
            if enum_body is not None:
                for enumerator in enum_body.named_children:
                    if enumerator.type != "enumerator":
                        continue
                    enum_case = next(
                        (item for item in enumerator.named_children if item.type == "identifier"),
                        None,
                    )
                    if enum_case is None:
                        continue
                    case_name = _read_text(enum_case, source)
                    case_line = enumerator.start_point[0] + 1
                    case_nid = _make_id(enum_nid, case_name)
                    add_node(case_nid, case_name, case_line)
                    add_edge(enum_nid, case_nid, "case_of", case_line)
            return

        if node.type == "class_definition":
            inner_name = name_text(node)
            if not inner_name:
                return
            inner_nid = _make_id(container_nid, inner_name)
            add_node(inner_nid, inner_name, line)
            add_edge(container_nid, inner_nid, "defines", line)
            class_body = child(node, "body", "class_body")
            if class_body is not None:
                for member in class_body.named_children:
                    handle_declaration(member, inner_nid)

    for item in root.named_children:
        if item.type not in ("class_name_statement", "extends_statement"):
            handle_declaration(item, script_nid)

    def emit_call(
        caller_nid: str,
        container_nid: str,
        callee: str,
        line: int,
        *,
        is_member_call: bool,
    ) -> None:
        if not callee or callee in _GDSCRIPT_CALL_SKIP:
            return
        local_targets = functions_by_container.get(container_nid, {}).get(callee, [])
        if len(local_targets) == 1 and local_targets[0] != caller_nid:
            add_edge(caller_nid, local_targets[0], "calls", line, context="call")
            return
        raw_calls.append({
            "caller_nid": caller_nid,
            "callee": callee,
            "is_member_call": is_member_call,
            "lang": "gdscript",
            "source_file": str_path,
            "source_location": f"L{line}",
        })

    def walk_calls(node, caller_nid: str, container_nid: str) -> None:
        if node.type == "function_definition":
            return
        if node.type == "call":
            function_node = node.named_children[0] if node.named_children else None
            if function_node is not None and function_node.type == "identifier":
                emit_call(
                    caller_nid,
                    container_nid,
                    _read_text(function_node, source),
                    node.start_point[0] + 1,
                    is_member_call=False,
                )
        elif node.type == "attribute":
            receiver = node.named_children[0] if node.named_children else None
            attribute_call = next(
                (item for item in node.named_children if item.type == "attribute_call"),
                None,
            )
            if receiver is not None and attribute_call is not None:
                method_node = next(
                    (item for item in attribute_call.named_children if item.type == "identifier"),
                    None,
                )
                method_name = _read_text(method_node, source) if method_node is not None else ""
                receiver_name = (
                    _read_text(receiver, source) if receiver.type == "identifier" else ""
                )
                line = node.start_point[0] + 1
                if method_name == "new" and receiver_name[:1].isupper():
                    if receiver_name not in _GDSCRIPT_BUILTIN_TYPES:
                        class_nid = _make_id("gdscript_type", receiver_name)
                        add_node(class_nid, receiver_name, None, source_file=None)
                        add_edge(
                            caller_nid,
                            class_nid,
                            "instantiates",
                            line,
                            context="call",
                        )
                elif receiver_name == "self":
                    emit_call(
                        caller_nid,
                        container_nid,
                        method_name,
                        line,
                        is_member_call=False,
                    )
        for item in node.named_children:
            walk_calls(item, caller_nid, container_nid)

    for caller_nid, container_nid, body in function_bodies:
        walk_calls(body, caller_nid, container_nid)

    def walk_resource_loads(node) -> None:
        if node.type == "call":
            function_node = node.named_children[0] if node.named_children else None
            if (
                function_node is not None
                and function_node.type == "identifier"
                and _read_text(function_node, source) in ("preload", "load")
            ):
                arguments = child(node, "arguments")
                if arguments is not None:
                    for argument in arguments.named_children:
                        if argument.type != "string":
                            continue
                        target_nid = resolve_resource(_read_text(argument, source))
                        if target_nid:
                            add_edge(
                                file_nid,
                                target_nid,
                                "imports_from",
                                node.start_point[0] + 1,
                                context="preload",
                            )
        for item in node.named_children:
            walk_resource_loads(item)

    walk_resource_loads(root)
    return {"nodes": nodes, "edges": edges, "raw_calls": raw_calls}
