"""Apex extractor. Moved verbatim from graphify/extract.py."""
from __future__ import annotations


from pathlib import Path
from graphify.extractors.base import _file_stem, _make_id


def extract_apex(path: Path) -> dict:
    """Extract classes, interfaces, enums, methods, and Salesforce constructs from
    Apex .cls and .trigger files using regex (no tree-sitter grammar on PyPI)."""
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

    def add_stub(nid: str, label: str) -> None:
        """Node for a type or SObject this file only REFERENCES, not declares.

        The definition lives elsewhere, so the placeholder must stay
        SOURCELESS: a stamped ``source_file`` reads as a definition, and
        ``_disambiguate_colliding_node_ids`` then salts the id per referencing
        file, so one class becomes N unconnected nodes and no edge reaches the
        real definition (#1402/#2324, same fix as the SQL extractor). No
        ``contains`` edge either, for the same reason.

        Unlike the SQL/CommonLisp stubs this sets no ``origin_file``:
        ``_node_disambiguation_source_key`` falls back to it, which would
        re-introduce exactly the per-file salting.
        """
        if nid not in seen_ids:
            seen_ids.add(nid)
            nodes.append({
                "id": nid,
                "label": label,
                "file_type": "code",
                "source_file": "",
                "source_location": "",
            })

    def type_ref(name: str) -> str:
        """Id for a referenced type: this file's own declaration when it has
        one, otherwise a sourceless stub the corpus-level rewire resolves."""
        local_nid = _make_id(stem, name)
        if local_nid in seen_ids:
            return local_nid
        nid = _make_id(name)
        add_stub(nid, name)
        return nid

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

    _ANNOTATION = r"(?:\s*@\w+(?:\s*\([^)]*\))?\s*)*"
    # Apex puts no ordering constraint on modifiers: `public abstract with
    # sharing class Foo` and `public with sharing abstract class Foo` are both
    # legal, as is any number of them. Matching a fixed
    # access -> sharing -> modifier sequence silently dropped every declaration
    # written in another order, so the type produced no node at all.
    _MODIFIERS = (
        r"(?:(?:public|private|protected|global|webService"
        r"|abstract|virtual|override|static|final|transient|testMethod)\s+"
        r"|(?:with|without|inherited)\s+sharing\s+)*"
    )

    cls_re = _re.compile(
        rf"^{_ANNOTATION}\s*{_MODIFIERS}class\s+(\w+)"
        rf"(?:\s+extends\s+(\w+))?(?:\s+implements\s+([\w,\s]+))?\s*\{{?",
        _re.IGNORECASE,
    )
    iface_re = _re.compile(
        rf"^{_ANNOTATION}\s*{_MODIFIERS}interface\s+(\w+)"
        rf"(?:\s+extends\s+([\w,\s]+))?\s*\{{?",
        _re.IGNORECASE,
    )
    enum_re = _re.compile(
        rf"^{_ANNOTATION}\s*{_MODIFIERS}enum\s+(\w+)\s*\{{?",
        _re.IGNORECASE,
    )
    trigger_re = _re.compile(
        r"^\s*trigger\s+(\w+)\s+on\s+(\w+)\s*\(",
        _re.IGNORECASE,
    )
    method_re = _re.compile(
        rf"^{_ANNOTATION}\s*{_MODIFIERS}[\w<>\[\]]+\s+(\w+)\s*\([^)]*\)\s*(?:throws\s+\w+\s*)?\{{?",
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
            sob_nid = type_ref(sobject)
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
                add_edge(class_nid, type_ref(base), "extends", lineno,
                         confidence="INFERRED")
            if cm.group(3):
                for iface in cm.group(3).split(","):
                    iface = iface.strip()
                    if iface:
                        add_edge(class_nid, type_ref(iface), "implements",
                                 lineno, confidence="INFERRED")
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
                        add_edge(iface_nid, type_ref(parent), "extends",
                                 lineno, confidence="INFERRED")
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
            sob_nid = type_ref(sobject)
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
