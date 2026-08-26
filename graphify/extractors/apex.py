"""Apex extractor: tree-sitter when the grammar is installed, regex otherwise."""
from __future__ import annotations


from pathlib import Path

from graphify.extractors.base import _file_stem, _make_id
from graphify.extractors.models import LanguageConfig

# The sfapex grammar (aheber/tree-sitter-sfapex) uses the same node type and field
# names as tree-sitter-java for declarations and calls, so the shared engine walk
# drives it unchanged. Apex has no import statements, hence no import_types.
_APEX_CONFIG = LanguageConfig(
    ts_module="tree_sitter_language_pack",
    ts_language_pack_name="apex",
    class_types=frozenset({
        "class_declaration", "interface_declaration", "enum_declaration",
        "trigger_declaration",
    }),
    function_types=frozenset({"method_declaration", "constructor_declaration"}),
    call_types=frozenset({"method_invocation"}),
    call_function_field="name",
    function_boundary_types=frozenset({"method_declaration", "constructor_declaration"}),
)


def extract_apex(path: Path) -> dict:
    """Extract an Apex .cls or .trigger file.

    Prefers the real parser; falls back to the regex extractor when the grammar
    is not installed, mirroring how Pascal treats its optional grammar. The
    fallback keeps every Apex corpus working without the extra, at lower
    fidelity and with no `calls` edges.
    """
    ast = _extract_apex_ast(path)
    return ast if ast is not None else _extract_apex_regex(path)


def _extract_apex_ast(path: Path) -> dict | None:
    """Engine walk plus the Apex-only constructs the generic walk cannot know.

    Returns None when the grammar is unavailable or the file does not parse, so
    the caller can fall back rather than emit a half-empty result.
    """
    try:
        from tree_sitter_language_pack import get_parser
    except Exception:
        return None
    try:
        parser = get_parser("apex")
        source = path.read_bytes()
    except Exception:
        return None

    from graphify.extractors.engine import _extract_generic

    result = _extract_generic(path, _APEX_CONFIG)
    if result.get("error"):
        return None
    try:
        root = parser.parse(source).root_node
    except Exception:
        return None
    _add_apex_specifics(path, root, source, result)
    raw_calls = result.get("raw_calls")
    if raw_calls:
        result["raw_calls"] = [
            rc for rc in raw_calls
            if str(rc.get("callee", "")).lower() not in _APEX_BUILTIN_METHODS
        ]
    return result


def _extract_apex_regex(path: Path) -> dict:
    """Extract classes, interfaces, enums, methods, and Salesforce constructs from
    Apex .cls and .trigger files using regex. Fallback for a missing grammar."""
    import re as _re
    try:
        source = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return {"nodes": [], "edges": []}

    str_path = str(path)
    stem = _file_stem(path)
    file_nid = _make_id(str_path)

    nodes: list[dict] = []
    edges: list[dict] = []
    seen_ids: set[str] = set()

    def add_node(nid: str, label: str, line: int) -> None:
        if nid not in seen_ids:
            seen_ids.add(nid)
            nodes.append({
                "id": nid,
                "label": label,
                "file_type": "code",
                "source_file": str_path,
                "source_location": f"L{line}",
            })

    def add_edge(src: str, tgt: str, relation: str, line: int,
                 confidence: str = "EXTRACTED") -> None:
        edges.append({
            "source": src,
            "target": tgt,
            "relation": relation,
            "confidence": confidence,
            "source_file": str_path,
            "source_location": f"L{line}",
            "weight": 1.0,
        })

    add_node(file_nid, path.name, 1)

    lines = source.splitlines()

    _ACCESS = r"(?:public|private|protected|global|webService)?"
    _SHARING = r"(?:\s+(?:with|without|inherited)\s+sharing)?"
    _MOD = r"(?:\s+(?:abstract|virtual|override|static|final|transient|testMethod))?"
    _ANNOTATION = r"(?:\s*@\w+(?:\s*\([^)]*\))?\s*)*"

    cls_re = _re.compile(
        rf"^{_ANNOTATION}\s*{_ACCESS}{_SHARING}{_MOD}\s*class\s+(\w+)"
        rf"(?:\s+extends\s+(\w+))?(?:\s+implements\s+([\w,\s]+))?\s*\{{?",
        _re.IGNORECASE,
    )
    iface_re = _re.compile(
        rf"^{_ANNOTATION}\s*{_ACCESS}{_SHARING}{_MOD}\s*interface\s+(\w+)"
        rf"(?:\s+extends\s+([\w,\s]+))?\s*\{{?",
        _re.IGNORECASE,
    )
    enum_re = _re.compile(
        rf"^{_ANNOTATION}\s*{_ACCESS}{_SHARING}{_MOD}\s*enum\s+(\w+)\s*\{{?",
        _re.IGNORECASE,
    )
    trigger_re = _re.compile(
        r"^\s*trigger\s+(\w+)\s+on\s+(\w+)\s*\(",
        _re.IGNORECASE,
    )
    method_re = _re.compile(
        rf"^{_ANNOTATION}\s*{_ACCESS}{_MOD}\s*(?:static\s+)?[\w<>\[\]]+\s+(\w+)\s*\([^)]*\)\s*(?:throws\s+\w+\s*)?\{{?",
        _re.IGNORECASE,
    )
    annotation_re = _re.compile(r"@(\w+)", _re.IGNORECASE)
    soql_re = _re.compile(r"\[\s*SELECT\b[^\]]+FROM\s+(\w+)", _re.IGNORECASE)
    dml_re = _re.compile(r"\b(insert|update|delete|upsert|merge|undelete)\s+\w", _re.IGNORECASE)

    _CONTROL_FLOW = frozenset({
        "if", "else", "for", "while", "do", "switch", "try", "catch",
        "finally", "return", "throw", "new", "void", "null",
        "true", "false", "this", "super", "class", "interface", "enum",
        "trigger", "on",
    })

    current_class_nid: str | None = None
    pending_annotations: list[str] = []

    for lineno, line_text in enumerate(lines, start=1):
        stripped = line_text.strip()

        if stripped.startswith("@"):
            for m in annotation_re.finditer(stripped):
                pending_annotations.append(m.group(1).lower())
            continue

        tm = trigger_re.match(stripped)
        if tm:
            trig_name, sobject = tm.group(1), tm.group(2)
            trig_nid = _make_id(stem, trig_name)
            add_node(trig_nid, trig_name, lineno)
            add_edge(file_nid, trig_nid, "contains", lineno)
            sob_nid = _make_id(sobject)
            if sob_nid not in seen_ids:
                add_node(sob_nid, sobject, lineno)
            add_edge(trig_nid, sob_nid, "uses", lineno, confidence="INFERRED")
            current_class_nid = trig_nid
            pending_annotations = []
            continue

        cm = cls_re.match(stripped)
        if cm:
            class_name = cm.group(1)
            if class_name.lower() in _CONTROL_FLOW:
                pending_annotations = []
                continue
            class_nid = _make_id(stem, class_name)
            add_node(class_nid, class_name, lineno)
            add_edge(file_nid, class_nid, "contains", lineno)
            if cm.group(2):
                base = cm.group(2).strip()
                base_nid = _make_id(stem, base)
                if base_nid not in seen_ids:
                    base_nid = _make_id(base)
                if base_nid not in seen_ids:
                    add_node(base_nid, base, lineno)
                add_edge(class_nid, base_nid, "extends", lineno, confidence="INFERRED")
            if cm.group(3):
                for iface in cm.group(3).split(","):
                    iface = iface.strip()
                    if iface:
                        iface_nid = _make_id(stem, iface)
                        if iface_nid not in seen_ids:
                            iface_nid = _make_id(iface)
                        if iface_nid not in seen_ids:
                            add_node(iface_nid, iface, lineno)
                        add_edge(class_nid, iface_nid, "implements", lineno, confidence="INFERRED")
            current_class_nid = class_nid
            pending_annotations = []
            continue

        im = iface_re.match(stripped)
        if im:
            iface_name = im.group(1)
            if iface_name.lower() in _CONTROL_FLOW:
                pending_annotations = []
                continue
            iface_nid = _make_id(stem, iface_name)
            add_node(iface_nid, iface_name, lineno)
            add_edge(file_nid if current_class_nid is None else current_class_nid,
                     iface_nid, "contains", lineno)
            if im.group(2):
                for parent in im.group(2).split(","):
                    parent = parent.strip()
                    if parent:
                        parent_nid = _make_id(stem, parent)
                        if parent_nid not in seen_ids:
                            parent_nid = _make_id(parent)
                        if parent_nid not in seen_ids:
                            add_node(parent_nid, parent, lineno)
                        add_edge(iface_nid, parent_nid, "extends", lineno, confidence="INFERRED")
            pending_annotations = []
            continue

        em = enum_re.match(stripped)
        if em:
            enum_name = em.group(1)
            if enum_name.lower() in _CONTROL_FLOW:
                pending_annotations = []
                continue
            enum_nid = _make_id(stem, enum_name)
            add_node(enum_nid, enum_name, lineno)
            add_edge(file_nid if current_class_nid is None else current_class_nid,
                     enum_nid, "contains", lineno)
            pending_annotations = []
            continue

        if current_class_nid is not None:
            mm = method_re.match(stripped)
            if mm:
                method_name = mm.group(1)
                if method_name.lower() not in _CONTROL_FLOW:
                    method_nid = _make_id(current_class_nid, method_name)
                    method_label = f".{method_name}()"
                    add_node(method_nid, method_label, lineno)
                    add_edge(current_class_nid, method_nid, "method", lineno)
                    if "auraenabled" in pending_annotations or "invocablemethod" in pending_annotations:
                        add_edge(file_nid, method_nid, "contains", lineno, confidence="INFERRED")
                    pending_annotations = []
                    continue

        pending_annotations = []

        for sm in soql_re.finditer(line_text):
            sobject = sm.group(1)
            sob_nid = _make_id(sobject)
            if sob_nid not in seen_ids:
                add_node(sob_nid, sobject, lineno)
            src = current_class_nid or file_nid
            add_edge(src, sob_nid, "uses", lineno, confidence="INFERRED")

        for dm in dml_re.finditer(line_text):
            dml_op = dm.group(1).lower()
            dml_nid = _make_id(f"dml_{dml_op}")
            if dml_nid not in seen_ids:
                add_node(dml_nid, dml_op, lineno)
            src = current_class_nid or file_nid
            add_edge(src, dml_nid, "uses", lineno, confidence="INFERRED")

    return {"nodes": nodes, "edges": edges}


# ── Apex constructs the generic engine walk has no concept of ─────────────────

_DML_TYPES = frozenset({"insert", "update", "delete", "upsert", "merge", "undelete"})

# Annotations that make a method an entry point reachable from outside Apex.
_ENTRY_POINT_ANNOTATIONS = frozenset({"auraenabled", "invocablemethod"})

# Collection and primitive constructors. `new List<Account>()` appears in nearly
# every method, so treating it as a call site builds a god-node that collects an
# edge from the whole codebase and tells you nothing — the same reason
# base.py filters language built-ins. Platform types that do carry meaning
# (HttpRequest, and any custom type) are deliberately NOT filtered.
# Collection and Map/Set/String methods. These are the receiver's methods, not a
# user method, but the cross-file call resolver matches unresolved calls by bare
# name — so `rows.add(x)` in twenty classes all bind to a user class that happens
# to define `add`, inventing twenty dependencies. Same-file calls are resolved
# against real declarations before this applies, so a class calling its own
# `add()` keeps its edge. Deliberately conservative: `execute` and `send` are NOT
# here, because they are commonly real user methods.
# Note the asymmetry that makes this necessary: a name defined by MANY classes is
# already safe, because the resolver refuses to bind an ambiguous name. The
# damage comes from a name defined by exactly ONE class — `send` in one class
# collects every `new Http().send(req)` in the codebase. `execute` is left out
# for exactly that reason: it is declared by every invocable class, so it is
# ambiguous and only ever resolves within a file.
_APEX_BUILTIN_METHODS = frozenset({
    # Collections and Map/Set
    "add", "addall", "get", "put", "putall", "size", "isempty", "clear",
    "contains", "containskey", "keyset", "values", "remove", "indexof", "sort",
    "deepclone", "clone",
    # Http/HttpRequest/HttpResponse
    "send", "getbody", "setbody", "getstatuscode", "setstatuscode",
    "setheader", "getheader", "setendpoint", "setmethod",
    # JSON, String, Object
    "serialize", "deserialize", "deserializeuntyped", "escapesinglequotes",
    "isblank", "isnotblank", "valueof", "tostring", "equals", "hashcode",
})

_APEX_BUILTIN_CONSTRUCTORS = frozenset({
    "list", "set", "map", "blob", "object",
    "string", "integer", "long", "double", "decimal", "boolean",
    "date", "datetime", "time", "id",
})


def _apex_text(node, source: bytes) -> str:
    return source[node.start_byte:node.end_byte].decode("utf-8", errors="replace")


def _add_apex_specifics(path: Path, root, source: bytes, result: dict) -> None:
    """Add inheritance, SObject usage, DML and entry points to an engine result.

    The engine walk covers declarations and calls, which are shaped like Java.
    Everything here is Apex-only: `extends`/`implements` (the engine's handling
    is gated on the Java grammar), the SObject a trigger fires on, the SObject
    behind a SOQL `FROM` or SOSL `RETURNING`, and DML statements. Node ids reuse
    the engine's scheme so the two halves land on the same nodes.
    """
    str_path = str(path)
    stem = _file_stem(path)
    file_nid = _make_id(str_path)
    nodes: list[dict] = result["nodes"]
    edges: list[dict] = result["edges"]
    seen_ids: set[str] = {n["id"] for n in nodes if n.get("id")}
    seen_edges = {(e.get("source"), e.get("target"), e.get("relation")) for e in edges}

    def add_stub(nid: str, label: str) -> None:
        """Sourceless placeholder — see the note in _extract_apex_regex."""
        if nid not in seen_ids:
            seen_ids.add(nid)
            nodes.append({"id": nid, "label": label, "file_type": "code",
                          "source_file": "", "source_location": ""})

    def add_edge(src: str, tgt: str, relation: str, line: int) -> None:
        key = (src, tgt, relation)
        if src == tgt or key in seen_edges:
            return
        seen_edges.add(key)
        edges.append({"source": src, "target": tgt, "relation": relation,
                      "confidence": "INFERRED", "source_file": str_path,
                      "source_location": f"L{line}", "weight": 1.0})

    def type_ref(name: str) -> str:
        local = _make_id(stem, name)
        if local in seen_ids:
            return local
        nid = _make_id(name)
        add_stub(nid, name)
        return nid

    def named(node, name: str):
        return node.child_by_field_name(name)

    def enclosing_callable(node) -> str:
        """Nearest enclosing method/constructor node id, else the type or file."""
        cur = node.parent
        while cur is not None:
            if cur.type in ("method_declaration", "constructor_declaration"):
                name_node = named(cur, "name")
                if name_node is not None:
                    nid = _make_id(enclosing_owner(cur),
                                   _apex_text(name_node, source))
                    if nid in seen_ids:
                        return nid
            cur = cur.parent
        return enclosing_owner(node)

    def enclosing_owner(node) -> str:
        """Nearest enclosing type or trigger node id, else the file node."""
        cur = node.parent
        while cur is not None:
            if cur.type in ("class_declaration", "interface_declaration",
                            "enum_declaration", "trigger_declaration"):
                name_node = named(cur, "name")
                if name_node is not None:
                    nid = _make_id(stem, _apex_text(name_node, source))
                    if nid in seen_ids:
                        return nid
            cur = cur.parent
        return file_nid

    stack = [root]
    while stack:
        node = stack.pop()
        stack.extend(node.children)
        t = node.type
        line = node.start_point[0] + 1

        if t in ("class_declaration", "interface_declaration"):
            name_node = named(node, "name")
            if name_node is None:
                continue
            owner = _make_id(stem, _apex_text(name_node, source))
            if owner not in seen_ids:
                continue
            for child in node.children:
                if child.type == "superclass":
                    for sub in child.children:
                        if sub.type in ("type_identifier", "scoped_type_identifier"):
                            add_edge(owner, type_ref(_apex_text(sub, source)),
                                     "extends", line)
                elif child.type in ("interfaces", "extends_interfaces"):
                    for sub in child.named_children:
                        for entry in (sub.named_children if sub.type == "type_list" else [sub]):
                            if entry.type in ("type_identifier", "scoped_type_identifier",
                                              "generic_type"):
                                raw = _apex_text(entry, source).split("<", 1)[0].strip()
                                relation = ("extends" if t == "interface_declaration"
                                            else "implements")
                                add_edge(owner, type_ref(raw), relation, line)

        elif t == "trigger_declaration":
            name_node, obj_node = named(node, "name"), named(node, "object")
            if name_node is not None and obj_node is not None:
                trig = _make_id(stem, _apex_text(name_node, source))
                if trig in seen_ids:
                    add_edge(trig, type_ref(_apex_text(obj_node, source)), "uses", line)

        elif t == "storage_identifier" and node.parent is not None \
                and node.parent.type == "from_clause":
            add_edge(enclosing_owner(node),
                     type_ref(_apex_text(node, source).split(".")[0]), "uses", line)

        elif t == "sobject_return":
            for sub in node.children:
                if sub.type == "identifier":
                    add_edge(enclosing_owner(node),
                             type_ref(_apex_text(sub, source)), "uses", line)
                    break

        elif t == "object_creation_expression":
            # `new Other()` is a call site whose callee sits in the `type` field,
            # so the shared call walk (which reads `name`) never sees it.
            type_node = named(node, "type")
            if type_node is not None:
                raw = _apex_text(type_node, source).split("<", 1)[0].strip()
                if (raw and raw[:1].isalpha()
                        and raw.lower() not in _APEX_BUILTIN_CONSTRUCTORS):
                    add_edge(enclosing_callable(node), type_ref(raw), "calls", line)

        elif t == "dml_type":
            op = _apex_text(node, source).strip().lower()
            if op in _DML_TYPES:
                dml_nid = _make_id(f"dml_{op}")
                if dml_nid not in seen_ids:
                    seen_ids.add(dml_nid)
                    nodes.append({"id": dml_nid, "label": op, "file_type": "code",
                                  "source_file": str_path,
                                  "source_location": f"L{line}"})
                add_edge(enclosing_owner(node), dml_nid, "uses", line)

        elif t in ("method_declaration", "constructor_declaration"):
            name_node = named(node, "name")
            if name_node is None:
                continue
            owner = enclosing_owner(node)
            method_nid = _make_id(owner, _apex_text(name_node, source))
            if method_nid not in seen_ids:
                continue
            for mods in node.children:
                if mods.type != "modifiers":
                    continue
                for anno in mods.children:
                    if anno.type != "annotation":
                        continue
                    raw = _apex_text(anno, source).lstrip("@").split("(")[0].strip().lower()
                    if raw in _ENTRY_POINT_ANNOTATIONS:
                        add_edge(file_nid, method_nid, "contains", line)
