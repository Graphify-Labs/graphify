"""Pascal_forms extractor. Moved verbatim from graphify/extract.py."""
from __future__ import annotations


from pathlib import Path
from typing import Any
from graphify.extractors.base import _file_stem, _make_id


def extract_lazarus_form(path: Path) -> dict:
    """Extract component hierarchy from Lazarus .lfm form files.

    .lfm is a text-based declarative format for UI component trees, structured as:
        object ComponentName: TClassName
          PropertyName = Value
          OnEvent = HandlerName
          object ChildName: TChildClass
            ...
          end
        end

    Produces nodes for:
    - The form file itself
    - Each component class encountered (TForm1, TButton, TPanel, ...)
    - Event handler names referenced by OnXxx properties

    Produces edges for:
    - file --contains--> root form class
    - parent component --contains--> child component class
    - component --references--> event handler (context: "event")
    """
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        return {"nodes": [], "edges": [], "error": str(e)}

    import re
    str_path = str(path)
    stem = _file_stem(path)
    nodes: list[dict] = []
    edges: list[dict] = []
    seen_ids: set[str] = set()
    seen_edge_pairs: set[tuple[str, str, str]] = set()

    def add_node(nid: str, label: str, line: int) -> None:
        if nid not in seen_ids:
            seen_ids.add(nid)
            nodes.append({
                "id": nid, "label": label, "file_type": "code",
                "source_file": str_path, "source_location": f"L{line}",
            })

    def add_edge(
        src: str, tgt: str, relation: str, line: int,
        context: str | None = None,
    ) -> None:
        key = (src, tgt, relation)
        if key in seen_edge_pairs:
            return
        seen_edge_pairs.add(key)
        edge: dict[str, Any] = {
            "source": src, "target": tgt, "relation": relation,
            "confidence": "EXTRACTED", "source_file": str_path,
            "source_location": f"L{line}", "weight": 1.0,
        }
        if context:
            edge["context"] = context
        edges.append(edge)

    file_nid = _make_id(str(path))
    add_node(file_nid, path.name, 1)

    obj_re = re.compile(r"^\s*object\s+\w+\s*:\s*(\w+)", re.IGNORECASE)
    event_re = re.compile(r"^\s*On\w+\s*=\s*(\w+)", re.IGNORECASE)
    end_re = re.compile(r"^\s*end\s*$", re.IGNORECASE)

    # Stack of node IDs representing the nesting of object...end blocks
    stack: list[str] = [file_nid]

    for lineno, line in enumerate(text.splitlines(), 1):
        m = obj_re.match(line)
        if m:
            class_name = m.group(1)
            nid = _make_id(stem, class_name)
            add_node(nid, class_name, lineno)
            add_edge(stack[-1], nid, "contains", lineno)
            stack.append(nid)
            continue

        m = event_re.match(line)
        if m and len(stack) > 1:
            handler = m.group(1)
            handler_nid = _make_id(stem, handler)
            add_node(handler_nid, f"{handler}()", lineno)
            add_edge(stack[-1], handler_nid, "references", lineno, context="event")
            continue

        if end_re.match(line) and len(stack) > 1:
            stack.pop()

    return {"nodes": nodes, "edges": edges, "input_tokens": 0, "output_tokens": 0}

def extract_delphi_form(path: Path) -> dict:
    """Extract component hierarchy from Delphi .dfm form files.

    .dfm files come in two formats:
    - Text (same `object Name: TClassName ... end` syntax as .lfm)
    - Binary (starts with a TPF0/FF0A magic header — unreadable as text)

    Binary .dfm files are skipped gracefully: an empty result is returned
    so the rest of the pipeline is unaffected.  Convert binary forms to
    text in the Delphi IDE via File → Save As (Text DFM) if you want them
    indexed.

    Text .dfm files are parsed identically to .lfm: component containment
    (`contains`) and event handler references (`references`, context "event").
    """
    try:
        raw = path.read_bytes()
    except Exception as e:
        return {"nodes": [], "edges": [], "error": str(e)}

    # Detect binary DFM: Delphi binary resource streams start with FF 0A
    if raw[:2] == b"\xff\x0a":
        return {
            "nodes": [], "edges": [],
            "error": f"binary DFM (convert to text in Delphi IDE to index): {path.name}",
        }

    # Text DFM — delegate to the shared form parser (same syntax as .lfm)
    try:
        text = raw.decode("utf-8", errors="replace")
    except Exception as e:
        return {"nodes": [], "edges": [], "error": str(e)}

    import re
    str_path = str(path)
    stem = _file_stem(path)
    nodes: list[dict] = []
    edges: list[dict] = []
    seen_ids: set[str] = set()
    seen_edge_pairs: set[tuple[str, str, str]] = set()

    def add_node(nid: str, label: str, line: int) -> None:
        if nid not in seen_ids:
            seen_ids.add(nid)
            nodes.append({
                "id": nid, "label": label, "file_type": "code",
                "source_file": str_path, "source_location": f"L{line}",
            })

    def add_edge(
        src: str, tgt: str, relation: str, line: int,
        context: str | None = None,
    ) -> None:
        key = (src, tgt, relation)
        if key in seen_edge_pairs:
            return
        seen_edge_pairs.add(key)
        edge: dict[str, Any] = {
            "source": src, "target": tgt, "relation": relation,
            "confidence": "EXTRACTED", "source_file": str_path,
            "source_location": f"L{line}", "weight": 1.0,
        }
        if context:
            edge["context"] = context
        edges.append(edge)

    file_nid = _make_id(str(path))
    add_node(file_nid, path.name, 1)

    obj_re   = re.compile(r"^\s*object\s+\w+\s*:\s*(\w+)", re.IGNORECASE)
    event_re = re.compile(r"^\s*On\w+\s*=\s*(\w+)", re.IGNORECASE)
    end_re   = re.compile(r"^\s*end\s*$", re.IGNORECASE)
    stack: list[str] = [file_nid]

    for lineno, line in enumerate(text.splitlines(), 1):
        m = obj_re.match(line)
        if m:
            class_name = m.group(1)
            nid = _make_id(stem, class_name)
            add_node(nid, class_name, lineno)
            add_edge(stack[-1], nid, "contains", lineno)
            stack.append(nid)
            continue
        m = event_re.match(line)
        if m and len(stack) > 1:
            handler = m.group(1)
            handler_nid = _make_id(stem, handler)
            add_node(handler_nid, f"{handler}()", lineno)
            add_edge(stack[-1], handler_nid, "references", lineno, context="event")
            continue
        if end_re.match(line) and len(stack) > 1:
            stack.pop()

    return {"nodes": nodes, "edges": edges, "input_tokens": 0, "output_tokens": 0}
