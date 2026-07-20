"""QML extractor: object trees, id references, embedded JS calls.

QML (Qt Quick) files declare a tree of typed objects, e.g.::

    Item {
        id: root
        property string title: "hello"
        Text { text: root.title }
    }

The QML engine itself enforces that type names (real child objects, e.g.
``Text``) start uppercase and property/grouped-binding names (e.g.
``anchors { ... }``) start lowercase, so that single check reliably tells a
real nested component apart from a grouped-binding block without any
heuristics.

A ``.qml`` file is itself a reusable component named after its filename
(``LiquidGlassTabsView.qml`` defines a component usable elsewhere as
``LiquidGlassTabsView { ... }``), so the root object becomes the file's
"component" node, and instantiations of known-custom (non-builtin) type
names become sourceless stubs that graphify's existing corpus-wide
stub-rewire pass resolves onto the real cross-file definition when the
label is unique.
"""
from __future__ import annotations

import re

from pathlib import Path
from graphify.extractors.base import _LANGUAGE_BUILTIN_GLOBALS, _file_stem, _make_id, _read_text

# Common Qt Quick / Qt Quick Controls / Qt Quick Layouts built-in type names.
# Instantiating one of these should never produce a cross-file stub node --
# they aren't defined anywhere in the corpus, so the stub would just be an
# inert (or, worse, an accidental god-) node. Anything NOT in this list is
# treated as a possible custom, in-repo component.
_QML_BUILTIN_TYPES: frozenset[str] = frozenset({
    # QtQuick basics
    "Item", "Rectangle", "Text", "TextInput", "TextEdit", "Image",
    "BorderImage", "AnimatedImage", "MouseArea", "TapHandler", "PinchHandler",
    "DragHandler", "HoverHandler", "WheelHandler", "FocusScope", "QtObject",
    "Component", "Loader", "Repeater", "Timer", "Binding", "PropertyChanges",
    "SystemPalette", "Shortcut", "Action",
    # Positioners / layouts
    "Column", "Row", "Grid", "Flow", "ColumnLayout", "RowLayout",
    "GridLayout", "StackLayout", "Layout", "Positioner",
    # Views
    "ListView", "GridView", "PathView", "TableView", "Flickable",
    "ScrollView", "SwipeView", "StackView", "ListModel", "ListElement",
    "XmlListModel", "DelegateModel", "VisualDataModel",
    # States/animations/transforms
    "State", "Transition", "StateGroup", "PropertyAnimation",
    "NumberAnimation", "ColorAnimation", "RotationAnimation", "Vector3dAnimation",
    "SpringAnimation", "SmoothedAnimation", "SequentialAnimation",
    "ParallelAnimation", "PauseAnimation", "ScriptAction", "PropertyAction",
    "Behavior", "AnchorAnimation", "AnchorChanges", "ParentAnimation",
    "ParentChange", "Transform", "Translate", "Scale", "Rotation", "Matrix4x4",
    # Shapes / graphics / effects
    "Canvas", "Shape", "ShapePath", "ShaderEffect", "ShaderEffectSource",
    "Gradient", "GradientStop", "LinearGradient", "RadialGradient",
    "ConicalGradient", "OpacityMask", "MultiEffect", "Particle",
    "ParticleSystem", "Emitter", "ImageParticle",
    # Input / controls (Qt Quick Controls 1/2)
    "Button", "Label", "CheckBox", "RadioButton", "Switch", "Slider",
    "RangeSlider", "Dial", "SpinBox", "ComboBox", "TextArea", "TextField",
    "ProgressBar", "BusyIndicator", "Tumbler", "ScrollBar", "ScrollIndicator",
    "ToolBar", "ToolButton", "ToolSeparator", "TabBar", "TabButton",
    "Menu", "MenuItem", "MenuSeparator", "MenuBar", "MenuBarItem",
    "Popup", "Dialog", "DialogButtonBox", "Drawer", "Page", "PageIndicator",
    "ApplicationWindow", "Window", "Frame", "GroupBox", "Pane", "Control",
    "Container", "SplitView", "Overlay", "Tooltip", "RoundButton",
    "DelayButton", "IconLabel",
    # Connections / signals plumbing
    "Connections",
    # Fonts / palettes / misc value-ish objects that still appear as UI objects
    "FontLoader", "FontMetrics", "TextMetrics", "Screen", "Settings",
    "ApplicationWindowAttached", "Icon",
})

# QML property "type" tokens that are language built-in value types, not
# custom in-repo type references (so `property int foo` shouldn't try to
# resolve `int` as a cross-file symbol).
_QML_VALUE_TYPES: frozenset[str] = frozenset({
    "int", "bool", "real", "double", "string", "url", "color", "var",
    "variant", "alias", "date", "point", "rect", "size", "font",
    "list", "vector2d", "vector3d", "vector4d", "quaternion", "matrix4x4",
})


def _last_segment(name: str) -> str:
    """`A.B.C` (a nested_identifier's text) -> `C`."""
    return name.rsplit(".", 1)[-1] if name else name


def _is_component_type(name: str) -> bool:
    seg = _last_segment(name)
    return bool(seg) and seg[0].isupper()


def _import_label(source_text: str, is_string_import: bool) -> str:
    if is_string_import:
        # Directory-style import: import "../common" -- use the trailing
        # path segment as the module label.
        return source_text.strip('"').rstrip("/").rsplit("/", 1)[-1] or source_text
    return source_text


def extract_qml(path: Path) -> dict:
    """Extract components, object trees, id references, and embedded-JS calls from a .qml file."""
    try:
        import tree_sitter_qmljs as tsqml
        from tree_sitter import Language, Parser
    except ImportError:
        return {"nodes": [], "edges": [], "error": "tree-sitter-qmljs not installed (optional [qml] extra)"}

    try:
        language = Language(tsqml.language())
        parser = Parser(language)
        source = path.read_bytes()
        tree = parser.parse(source)
        root = tree.root_node
    except Exception as e:
        return {"nodes": [], "edges": [], "error": str(e)}

    stem = _file_stem(path)
    str_path = str(path)
    component_label = path.stem

    nodes: list[dict] = []
    edges: list[dict] = []
    seen_ids: set[str] = set()
    seen_edge_keys: set[tuple] = set()
    id_table: dict[str, str] = {}       # QML `id:` value -> node id
    func_table: dict[str, str] = {}     # function/signal name -> node id (last decl wins on same-name collision)
    func_owner: dict[str, str] = {}     # function/signal node id -> the object node id it's defined on
    deferred_exprs: list[tuple[str, object, str]] = []  # (owner_nid, expr_node, context)
    raw_calls: list[dict] = []

    def add_node(nid: str, label: str, line: int, *, sourceless: bool = False) -> None:
        if nid in seen_ids:
            return
        seen_ids.add(nid)
        node: dict = {
            "id": nid,
            "label": label,
            "file_type": "code",
            "source_file": "" if sourceless else str_path,
            "source_location": "" if sourceless else f"L{line}",
        }
        if sourceless:
            node["origin_file"] = str_path
        nodes.append(node)

    def add_edge(src: str, tgt: str, relation: str, line: int,
                 confidence: str = "EXTRACTED", weight: float = 1.0,
                 context: str | None = None) -> None:
        key = (src, tgt, relation, context)
        if key in seen_edge_keys:
            return
        seen_edge_keys.add(key)
        edge: dict = {
            "source": src,
            "target": tgt,
            "relation": relation,
            "confidence": confidence,
            "source_file": str_path,
            "source_location": f"L{line}",
            "weight": weight,
        }
        if context:
            edge["context"] = context
        edges.append(edge)

    def ensure_type_stub(type_name: str, line: int) -> str | None:
        """Sourceless stub for a possible cross-file custom-component reference.

        Returns None for known Qt Quick builtins (they're never defined in the
        corpus, so a stub would just be inert noise or an accidental god-node).
        """
        seg = _last_segment(type_name)
        if not seg or seg in _QML_BUILTIN_TYPES:
            return None
        nid = _make_id(seg)
        add_node(nid, seg, line, sourceless=True)
        return nid

    file_nid = _make_id(str(path))
    add_node(file_nid, path.name, 1)

    def find_binding(init_node, name: str):
        """First direct `ui_binding` child of an initializer with the given name."""
        if init_node is None:
            return None
        for m in init_node.named_children:
            if m.type == "ui_binding":
                nm = m.child_by_field_name("name")
                if nm is not None and _read_text(nm, source) == name:
                    return m.child_by_field_name("value")
        return None

    def unwrap_expr(value_node):
        """`ui_binding`/`ui_property` values wrap the real JS expr in expression_statement."""
        if value_node is not None and value_node.type == "expression_statement" and value_node.named_child_count == 1:
            return value_node.named_children[0]
        return value_node

    def walk_object(obj_node, parent_nid: str, *, is_root: bool = False, forced_name: str | None = None) -> None:
        # ui_annotated_object wraps a real definition behind a "definition" field.
        if obj_node.type == "ui_annotated_object":
            inner = obj_node.child_by_field_name("definition")
            if inner is not None:
                walk_object(inner, parent_nid, is_root=is_root, forced_name=forced_name)
            return

        type_name_node = obj_node.child_by_field_name("type_name")
        if type_name_node is None:
            return
        type_name = _read_text(type_name_node, source)
        line = obj_node.start_point[0] + 1
        init = obj_node.child_by_field_name("initializer")

        if not is_root and forced_name is None and not _is_component_type(type_name):
            # Grouped binding, e.g. `anchors { left: parent.left }` -- not a
            # real child object. Attribute its members to the parent instead.
            if init is not None:
                walk_members(init, parent_nid)
            return

        id_value = None
        id_val_node = find_binding(init, "id")
        if id_val_node is not None:
            expr = unwrap_expr(id_val_node)
            if expr is not None and expr.type == "identifier":
                id_value = _read_text(expr, source)

        if forced_name is not None:
            nid, label = _make_id(stem, forced_name), forced_name
        elif id_value:
            nid, label = _make_id(stem, id_value), id_value
        else:
            # Column, not just line, disambiguates two same-typed anonymous
            # siblings that start on the same source line (e.g. a compact
            # `Row { Text{} Text{} }` one-liner, or array-literal children)
            # -- keying by line alone would collapse them into one node (#2).
            col = obj_node.start_point[1]
            nid = _make_id(stem, type_name, f"L{line}C{col}")
            label = _last_segment(type_name)

        add_node(nid, label, line)
        if id_value:
            id_table[id_value] = nid
        add_edge(parent_nid, nid, "contains", line)

        stub = ensure_type_stub(type_name, line)
        if stub is not None and stub != nid:
            add_edge(nid, stub, "inherits" if is_root else "instantiates", line)

        if init is not None:
            walk_members(init, nid)

    def walk_behavior(node, parent_nid: str) -> None:
        # `Behavior on width { NumberAnimation { ... } }` -- always a real
        # anonymous child object (its own type_name, e.g. NumberAnimation),
        # never a grouped binding.
        type_name_node = node.child_by_field_name("type_name")
        line = node.start_point[0] + 1
        col = node.start_point[1]
        type_name = _read_text(type_name_node, source) if type_name_node else "Behavior"
        nid = _make_id(stem, type_name, f"L{line}C{col}")
        add_node(nid, _last_segment(type_name), line)
        add_edge(parent_nid, nid, "contains", line)
        stub = ensure_type_stub(type_name, line)
        if stub is not None and stub != nid:
            add_edge(nid, stub, "instantiates", line)
        init = node.child_by_field_name("initializer")
        if init is not None:
            walk_members(init, nid)

    def add_property_type_ref(owner_nid: str, type_node, line: int) -> None:
        if type_node is None:
            return
        if type_node.type == "ui_list_property_type":
            for c in type_node.named_children:
                add_property_type_ref(owner_nid, c, line)
            return
        text = _read_text(type_node, source)
        seg = _last_segment(text)
        if not seg or seg in _QML_VALUE_TYPES:
            return
        tgt = ensure_type_stub(seg, line)
        if tgt is not None and tgt != owner_nid:
            add_edge(owner_nid, tgt, "references", line, context="type")

    def walk_members(init_node, owner_nid: str) -> None:
        for m in init_node.named_children:
            t = m.type
            if t == "ui_annotated_object_member":
                inner = m.child_by_field_name("definition") or m.child_by_field_name("member")
                if inner is not None:
                    walk_members_single(inner, owner_nid)
                continue
            walk_members_single(m, owner_nid)

    def walk_members_single(m, owner_nid: str) -> None:
        t = m.type
        line = m.start_point[0] + 1

        if t == "ui_object_definition":
            walk_object(m, owner_nid)
            return

        if t == "ui_object_definition_binding":
            walk_behavior(m, owner_nid)
            return

        if t == "ui_binding":
            name_node = m.child_by_field_name("name")
            name = _read_text(name_node, source) if name_node else ""
            val = m.child_by_field_name("value")
            if name == "id":
                return  # already consumed when the owner object was created
            if val is None:
                return
            if val.type == "ui_object_definition":
                walk_object(val, owner_nid)
                return
            if val.type == "ui_object_array":
                for el in val.named_children:
                    if el.type == "ui_object_definition":
                        walk_object(el, owner_nid)
                return
            ctx = "event" if re.match(r"^on[A-Z]", name) else "value"
            deferred_exprs.append((owner_nid, unwrap_expr(val), ctx))
            return

        if t == "ui_property":
            name_node = m.child_by_field_name("name")
            if name_node is None:
                return
            pname = _read_text(name_node, source)
            pnid = _make_id(owner_nid, pname)
            add_node(pnid, pname, line)
            add_edge(owner_nid, pnid, "defines", line)
            add_property_type_ref(pnid, m.child_by_field_name("type"), line)
            val = m.child_by_field_name("value")
            if val is not None:
                if val.type == "ui_object_definition":
                    walk_object(val, owner_nid)
                else:
                    deferred_exprs.append((pnid, unwrap_expr(val), "value"))
            return

        if t == "ui_signal":
            name_node = m.child_by_field_name("name")
            if name_node is None:
                return
            name = _read_text(name_node, source)
            nid = _make_id(owner_nid, name)
            add_node(nid, f"{name}()", line)
            add_edge(owner_nid, nid, "defines", line, context="signal")
            func_table[name] = nid
            func_owner[nid] = owner_nid
            params = m.child_by_field_name("parameters")
            if params is not None:
                for p in params.named_children:
                    if p.type == "ui_signal_parameter":
                        add_property_type_ref(nid, p.child_by_field_name("type"), line)
            return

        if t in ("function_declaration", "generator_function_declaration"):
            name_node = m.child_by_field_name("name")
            if name_node is None:
                return
            name = _read_text(name_node, source)
            nid = _make_id(owner_nid, name)
            add_node(nid, f"{name}()", line)
            add_edge(owner_nid, nid, "defines", line)
            func_table[name] = nid
            func_owner[nid] = owner_nid
            body = m.child_by_field_name("body")
            if body is not None:
                deferred_exprs.append((nid, body, "value"))
            return

        if t == "ui_inline_component":
            # `component Foo: Rectangle { ... }` -- Foo's underlying object is a
            # real object definition (id/type-stub/members all apply exactly as
            # for any other child object), just named by the component
            # declaration rather than by an `id:` binding or its type name.
            name_node = m.child_by_field_name("name")
            comp_node = m.child_by_field_name("component")
            if name_node is not None and comp_node is not None and comp_node.type == "ui_object_definition":
                name = _read_text(name_node, source)
                walk_object(comp_node, owner_nid, is_root=True, forced_name=name)
            return

        if t == "enum_declaration":
            name_node = m.child_by_field_name("name")
            if name_node is not None:
                name = _read_text(name_node, source)
                nid = _make_id(owner_nid, name)
                add_node(nid, name, line)
                add_edge(owner_nid, nid, "defines", line)
            return

        # ui_required, ui_pragma, variable_declaration, comments, etc. --
        # no graph-worthy content.
        return

    # ---- locate import statements + the root object ----
    root_object = None
    for child in root.named_children:
        if child.type == "ui_import":
            src_node = child.child_by_field_name("source")
            if src_node is None:
                continue
            is_string = src_node.type == "string"
            raw = _read_text(src_node, source).strip('"') if is_string else _read_text(src_node, source)
            label = _import_label(raw, is_string)
            if not label:
                continue
            line = child.start_point[0] + 1
            tgt_nid = _make_id(label)
            add_node(tgt_nid, label, line, sourceless=True)
            add_edge(file_nid, tgt_nid, "imports_from", line, context="import")
        elif child.type in ("ui_object_definition", "ui_annotated_object") and root_object is None:
            root_object = child

    if root_object is not None:
        walk_object(root_object, file_nid, is_root=True, forced_name=component_label)

    # ---- pass 2: scan deferred JS expressions for id references + calls ----
    def scan_expr(owner_nid: str, node, ctx: str) -> None:
        if node is None:
            return
        t = node.type

        if t == "call_expression":
            func_node = node.child_by_field_name("function")
            callee_name: str | None = None
            is_member_call = False
            receiver_nid: str | None = None
            if func_node is not None:
                if func_node.type == "identifier":
                    callee_name = _read_text(func_node, source)
                elif func_node.type == "member_expression":
                    is_member_call = True
                    obj_node = func_node.child_by_field_name("object")
                    prop_node = func_node.child_by_field_name("property")
                    if prop_node is not None:
                        callee_name = _read_text(prop_node, source)
                    # If the receiver is a known id, emit a references edge to
                    # it (e.g. `root.refresh()` references `root`) before
                    # treating the call itself.
                    if obj_node is not None and obj_node.type == "identifier":
                        recv = _read_text(obj_node, source)
                        receiver_nid = id_table.get(recv)
                        if receiver_nid and receiver_nid != owner_nid:
                            line = node.start_point[0] + 1
                            add_edge(owner_nid, receiver_nid, "references", line, context=ctx)
            line = node.start_point[0] + 1
            if callee_name and callee_name not in _LANGUAGE_BUILTIN_GLOBALS:
                tgt_nid = func_table.get(callee_name)
                # For a member call (`x.method()`), only trust the same-file
                # name lookup when `method` is actually defined ON the node
                # `x` resolved to -- func_table is a flat, whole-file dict, so
                # without this check two same-named methods on different
                # objects/components in the same file would let one silently
                # shadow the other and produce a wrong `calls` edge (#1).
                owner_matches = not is_member_call or (receiver_nid is not None and func_owner.get(tgt_nid) == receiver_nid)
                if tgt_nid and tgt_nid != owner_nid and owner_matches:
                    add_edge(owner_nid, tgt_nid, "calls", line, context="call")
                elif not is_member_call:
                    raw_calls.append({
                        "caller_nid": owner_nid,
                        "callee": callee_name,
                        "is_member_call": is_member_call,
                        "source_file": str_path,
                        "source_location": f"L{line}",
                    })
            # Still scan call arguments for nested id references/calls.
            args = node.child_by_field_name("arguments")
            if args is not None:
                for c in args.named_children:
                    scan_expr(owner_nid, c, ctx)
            return

        if t == "member_expression":
            obj_node = node.child_by_field_name("object")
            if obj_node is not None and obj_node.type == "identifier":
                recv = _read_text(obj_node, source)
                tgt = id_table.get(recv)
                if tgt and tgt != owner_nid:
                    line = node.start_point[0] + 1
                    add_edge(owner_nid, tgt, "references", line, context=ctx)
                return  # leftmost identifier handled; don't also treat it as a bare identifier below
            if obj_node is not None:
                scan_expr(owner_nid, obj_node, ctx)
            return

        if t == "identifier":
            name = _read_text(node, source)
            # Prefer an id match; fall back to a function reference so a
            # by-reference assignment with no call parens (e.g.
            # `onClicked: doSomethingWithoutParens`, a valid QML idiom) still
            # links to its target instead of silently producing no edge (#3).
            tgt = id_table.get(name) or func_table.get(name)
            if tgt and tgt != owner_nid:
                line = node.start_point[0] + 1
                add_edge(owner_nid, tgt, "references", line, context=ctx)
            return

        for c in node.named_children:
            scan_expr(owner_nid, c, ctx)

    for owner_nid, expr_node, ctx in deferred_exprs:
        scan_expr(owner_nid, expr_node, ctx)

    valid_ids = seen_ids
    clean_edges = []
    for edge in edges:
        src, tgt = edge["source"], edge["target"]
        if src in valid_ids and (tgt in valid_ids or edge["relation"] == "imports_from"):
            clean_edges.append(edge)

    return {"nodes": nodes, "edges": clean_edges, "raw_calls": raw_calls}
