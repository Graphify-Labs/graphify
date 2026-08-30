"""Salesforce `*-meta.xml` extractor — the Salesforce subset of plain XML.

Salesforce metadata is ordinary XML, so this is one generic element walk with no
per-component-type logic: objects, fields, permission sets, layouts, flows and
everything else go through the same code path, parsed with the stdlib XML
parser and no new dependency.

What a file DECLARES comes from its filename (``Memory__c.object-meta.xml``
declares ``Memory__c``). What it REFERENCES comes from leaf element text, which
is how Salesforce spells cross-component links::

    <classAccesses>
        <apexClass>NotifyUser</apexClass>   <- a reference to an Apex class
        <enabled>true</enabled>             <- a value, not a reference
    </classAccesses>

References are emitted as sourceless placeholders, so the corpus-level rewire
binds them to the real definition — the permission set above ends up pointing
at ``NotifyUser.cls`` without this extractor knowing what a permission set is.
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path

from graphify.extractors.base import _file_stem, _make_id

_META_SUFFIX = "-meta.xml"

# Stdlib ElementTree does not cap entity expansion, so a crafted file could
# trigger a billion-laughs DoS. Mirrors the project-XML screen in extract.py;
# metadata emitted by the Salesforce CLI never declares a DTD or entity.
_MAX_BYTES = 2 * 1024 * 1024


def _unsafe_reason(src: bytes) -> str | None:
    """Why this file must not be parsed, or None when it is fine.

    The DOCTYPE/ENTITY screen matches ASCII bytes, so a UTF-16 encoded
    declaration slips straight past it while ElementTree still honours the
    encoding and expands the entity. A NUL byte is the reliable tell for
    UTF-16/32, and Salesforce source format is always UTF-8, so refusing those
    outright closes the hole without costing anything real.
    """
    if b"\x00" in src:
        return "refusing non-UTF-8 XML (NUL byte: UTF-16/32)"
    lowered = src.lower()
    if b"<!doctype" in lowered or b"<!entity" in lowered:
        return "refusing XML with DOCTYPE/ENTITY declaration"
    return None


def _local(tag: str) -> str:
    """Strip the metadata namespace every Salesforce file declares."""
    return tag.rsplit("}", 1)[-1] if tag.startswith("{") else tag


# Sidecars for a companion file graphify already extracts itself (AgentMemory.cls
# next to AgentMemory.cls-meta.xml). They carry only apiVersion/status, so parsing
# them would mint a second node for a component another extractor already owns.
# Kinds whose companion has NO extractor (a Visualforce .page, a static resource)
# are deliberately absent: their metadata file is the only handle on them.
_SIDECAR_KINDS = frozenset({"cls", "trigger", "js"})

# Element names whose text names ANOTHER component. Custom API names are
# recognised by their suffix instead (below), so this only has to cover
# references to standard components — Apex classes, pages, standard objects.
# Chosen from the element names that actually carry identifiers in real orgs.
_REFERENCE_ELEMENTS = frozenset({
    "apexClass", "apexPage", "apexTrigger", "object", "field", "fields",
    "columns", "recordType", "flow", "tab", "layout", "relatedList",
    "customPermission", "namedCredential", "externalCredential",
    "application", "controller", "extensions", "targetObject", "sobjectType",
})

# Human-facing display text, never an API name. `fullName` and `name` are NOT
# here: they usually restate the component's own name (dropped below by the
# self-reference check), but `<name>CustomSetting__c</name>` in a custom-metadata
# record is a genuine reference, so they go through the normal rules.
_SELF_NAME_ELEMENTS = frozenset({"masterLabel", "label", "description", "motif"})

# A name carrying one of these is always an API name, never an enum value, so
# it is a reference wherever it appears — no element vocabulary needed.
_CUSTOM_SUFFIXES = ("__c", "__mdt", "__e", "__x", "__b", "__r", "__Share", "__History")

_IDENTIFIER_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z][A-Za-z0-9_]*)*$")


def _is_api_name(text: str) -> bool:
    return bool(_IDENTIFIER_RE.match(text)) and not text.isupper()


def is_salesforce_meta_xml_path(path: Path) -> bool:
    """True for a Salesforce source-format metadata file this extractor owns.

    Sidecars for a file another extractor already handles (``Foo.cls-meta.xml``)
    are excluded, so dispatch and the file scan agree on one answer.
    """
    name = path.name
    if not name.endswith(_META_SUFFIX):
        return False
    return _component_of(path)[1] not in _SIDECAR_KINDS


def _component_of(path: Path) -> tuple[str, str]:
    """``(name, kind)`` a metadata file declares, read from its filename."""
    base = path.name[: -len(_META_SUFFIX)]
    name, _, kind = base.rpartition(".")
    return (name, kind) if name else (base, "")


def _parent_object(path: Path) -> str | None:
    """Owning object of a nested component (a field under ``objects/Foo/fields/``).

    Found by looking for an ancestor directory that holds its own
    ``<dir>.object-meta.xml``, so it needs no hardcoded folder names.
    """
    for ancestor in list(path.parents)[:4]:
        if (ancestor / f"{ancestor.name}.object-meta.xml").is_file():
            return ancestor.name
    return None


def extract_salesforce_meta_xml(path: Path) -> dict:
    """Extract one Salesforce ``*-meta.xml`` file."""
    name, kind = _component_of(path)
    if kind in _SIDECAR_KINDS:
        return {"nodes": [], "edges": []}

    try:
        src = path.read_bytes()
    except OSError:
        return {"nodes": [], "edges": [], "error": f"cannot read {path}"}
    if len(src) > _MAX_BYTES:
        return {"nodes": [], "edges": [], "error": "metadata file too large"}
    unsafe = _unsafe_reason(src)
    if unsafe:
        return {"nodes": [], "edges": [], "error": unsafe}
    try:
        root = ET.fromstring(src)
    except ET.ParseError as e:
        return {"nodes": [], "edges": [], "error": f"XML parse error: {e}"}

    str_path = str(path)
    stem = _file_stem(path)
    file_nid = _make_id(str_path)
    nodes: list[dict] = []
    edges: list[dict] = []
    seen_ids: set[str] = set()
    seen_edges: set[tuple[str, str, str]] = set()

    # First line each identifier appears on, so references get a location
    # without a second pass over the tree.
    line_of: dict[str, int] = {}
    for lineno, line in enumerate(src.decode("utf-8", errors="replace").splitlines(), 1):
        inner = line.strip()
        if inner.startswith("<") and ">" in inner:
            value = inner[inner.index(">") + 1:].rsplit("<", 1)[0].strip()
            if value:
                line_of.setdefault(value, lineno)

    def add_node(nid: str, label: str, line: int) -> None:
        if nid not in seen_ids:
            seen_ids.add(nid)
            nodes.append({"id": nid, "label": label, "file_type": "code",
                          "source_file": str_path, "source_location": f"L{line}"})

    def add_stub(nid: str, label: str) -> None:
        """Sourceless placeholder for a component defined in another file.

        Sourced stubs get their id salted per referencing file, which scatters
        one component across a node per reference and leaves the real
        definition unreferenced (the #1402/#2324 pattern).
        """
        if nid not in seen_ids:
            seen_ids.add(nid)
            nodes.append({"id": nid, "label": label, "file_type": "code",
                          "source_file": "", "source_location": ""})

    def add_edge(src_nid: str, tgt_nid: str, relation: str, line: int) -> None:
        key = (src_nid, tgt_nid, relation)
        if src_nid == tgt_nid or key in seen_edges:
            return
        seen_edges.add(key)
        edges.append({"source": src_nid, "target": tgt_nid, "relation": relation,
                      "confidence": "INFERRED", "source_file": str_path,
                      "source_location": f"L{line}", "weight": 1.0})

    add_node(file_nid, path.name, 1)
    comp_nid = _make_id(stem, name)
    add_node(comp_nid, name, 1)
    add_edge(file_nid, comp_nid, "contains", 1)

    owner = _parent_object(path)
    if owner and owner != name:
        owner_nid = _make_id(owner)
        add_stub(owner_nid, owner)
        add_edge(owner_nid, comp_nid, "contains", 1)

    for el in root.iter():
        if len(el):
            continue
        text = (el.text or "").strip()
        if not text or not _is_api_name(text):
            continue
        tag = _local(el.tag)
        if tag in _SELF_NAME_ELEMENTS:
            continue
        qualified = text.split(".")
        by_suffix = any(text.endswith(s) for s in _CUSTOM_SUFFIXES)
        if tag not in _REFERENCE_ELEMENTS and not by_suffix and len(qualified) == 1:
            continue
        line = line_of.get(text, 1)
        for part in qualified:
            if not _is_api_name(part) or part == name:
                continue
            ref_nid = _make_id(part)
            add_stub(ref_nid, part)
            add_edge(comp_nid, ref_nid, "references", line)

    return {"nodes": nodes, "edges": edges}
