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
