"""Append bounded Qt overlays to accepted C++; never replace generic declarations."""
from __future__ import annotations

from pathlib import Path
import re

from graphify.extractors.qt_cpp_facts import QtFacts, qt_metadata
from graphify.extractors.qt_cpp_mapping import map_cpp
from graphify.extractors.qt_cpp_properties import add_properties
from graphify.extractors.qt_cpp_registration import add_literal_registrations, add_macro_registration, conditional_offset
from graphify.extractors.qt_cpp_syntax import MAX_CPP_BYTES, QtCppError, lexical_code, read_cpp
from graphify.extractors.qt_cpp_type_aliases import add_type_dependency_facts, type_dependency_source
from graphify.extractors.qt_cpp_type_scope import NativeTypeScope
from graphify.extractors.qt_cpp_api_types import add_api_fields, return_fields

_CPP = {".cpp", ".cc", ".cxx", ".hpp", ".hh", ".hxx", ".h"}
_QT = re.compile(rb"\b(?:QML_[A-Z_]+|Q_[A-Z_]+|QObject|QQml\w*|QQuickView|qmlRegister\w*|signals|slots)\b")


def is_qt_cpp_source(path, *, class_names=()):
    if Path(path).suffix.lower() not in _CPP:
        return False
    try:
        with Path(path).open("rb") as stream:
            source = stream.read(MAX_CPP_BYTES + 1)
    except OSError as exc:
        raise QtCppError("QT_CPP_READ", "Cannot read admitted C++ source") from exc
    code = lexical_code(source)
    if _QT.search(code) or re.search(rb"\bemit\s+[A-Za-z_]", code):
        return True
    # Admission hints never bind an endpoint: parsed qualification and accepted
    # ownership subsequently prove the actual class/method relationship.
    return any(re.search(rb"\b" + re.escape(name.rsplit("::", 1)[-1].encode()) + rb"\s*::", code)
               for name in class_names)


def _failure(result, path, root, error):
    try:
        source = Path(path).resolve().relative_to(Path(root).resolve()).as_posix()
    except ValueError:
        source = ""
    result.setdefault("qml_failures", []).append({"code": error.code, "source_file": source})
    result.setdefault("diagnostics", []).append({"code": error.code, "severity": "error", "owner": "qt",
                                                "source_file": source, "message": str(error)})


def _class_facts(mapping, facts, *, classes=(), alias_nodes=None):
    # Literal source occurrences can belong to a proven callable even when no
    # Qt class definition is admitted. This is source containment only: it must
    # not supply missing class authority, endpoint roles or QML visibility.
    callables = {node["id"] for node in mapping.nodes if node.get("_callable") is True
                 and not node.get("_callable_class")}
    types = NativeTypeScope(mapping.unit, mapping, classes=classes, alias_nodes=alias_nodes)

    def source_owner(record):
        return record.get("node_id", "") if (record and record.get("status") == "resolved"
                                              and record.get("node_id") in callables) else ""

    for record in mapping.classes:
        owned = [macro for macro in record["macros"] if mapping.class_at(macro["start_byte"]) is record]
        macros = {macro["name"] for macro in owned}
        base = next((child for child in record["syntax"].named_children if child.type == "base_class_clause"), None)
        bases = [mapping.unit.text(child) for child in base.named_children
                 if child.type not in {"access_specifier", "comment"}] if base else []
        # Inheritance visibility belongs to each source base, independently of
        # member visibility. Each comma restores class/struct default access;
        # virtual and comments cannot provide or replace an access specifier.
        default_access = "public" if record["syntax"].type == "struct_specifier" else "private"
        access, base_access = default_access, []
        for child in base.children if base else ():
            if child.type == ",":
                access = default_access
            elif child.type == "access_specifier":
                access = mapping.unit.text(child)
            elif child.is_named and child.type != "comment":
                base_access.append(access)
        # Construction authority needs lexical base identities, not a Q_OBJECT
        # marker or a guessed basename. Unknown header aliases remain opaque.
        canonical_bases = [types.resolve(name, record["span"]["start_byte"]) for name in bases]
        enclosing = mapping.owner_at(record["span"]["start_byte"])
        facts.add("class", record["name"], record["span"],
                  owner=record["node_id"] or source_owner(enclosing) or None,
                  generic_target_id=record["node_id"], class_id=record["node_id"],
                  class_name=record["qualified_name"], status=record["status"],
                  is_definition=record["is_definition"],
                  api_declaration_conditional=conditional_offset(mapping.unit, record["span"]["start_byte"]),
                  is_qobject="Q_OBJECT" in macros or "QObject" in bases,
                  source_q_object="Q_OBJECT" in macros, is_gadget="Q_GADGET" in macros, bases=bases,
                  canonical_base_names=canonical_bases,
                  canonical_base_status="resolved" if all(canonical_bases) else "unavailable",
                  canonical_base_access=base_access,
                  canonical_base_access_status="resolved" if len(base_access) == len(bases)
                  and all(value in {"public", "protected", "private"} for value in base_access) else "unavailable")
        add_macro_registration(mapping, facts, record)
        add_properties(mapping.unit, mapping, facts, record, types=types)
        add_api_fields(mapping, facts, record, types)
    for record in mapping.functions:
        if not record["class_name"]:
            continue
        if len(record["parameters"]) > 50:
            raise QtCppError("QT_CPP_LIMIT", "Qt member exceeds 50 parameters")
        revisions = [macro["args"] for macro in mapping.unit.macros if macro["name"] == "Q_REVISION"
                     and macro["end_byte"] <= record["span"]["start_byte"]
                     and not mapping.unit.parsed_source[macro["end_byte"]:record["span"]["start_byte"]].strip()]
        facts.add("member", record["name"], record["span"],
                  owner=record["class_id"] or source_owner(record) or None,
                  generic_target_id=record["node_id"], class_id=record["class_id"], class_name=record["class_name"],
                  signature=record["signature"], parameter_types=record["parameter_types"],
                  parameter_names=[item["name"] for item in record["parameters"]],
                  revisions=revisions,
                  return_type=record["return_type"], roles=record["roles"], access=record["access"], status=record["status"],
                  **return_fields(mapping.unit, record, types))


def enrich_qt_cpp(paths, per_file, *, root, accepted_nodes=None, accepted_edges=None):
    """Use final canonical aggregate IDs; mutate fresh result slices only.

    Failure facts share the QML safety channel so update can reject incomplete Qt
    overlays. Borrowed aggregate/context dictionaries are never annotated.
    """
    paths, per_file = list(paths), list(per_file)
    nodes = list(accepted_nodes) if accepted_nodes is not None else [node for result in per_file for node in result.get("nodes", [])]
    edges = list(accepted_edges) if accepted_edges is not None else [edge for result in per_file for edge in result.get("edges", [])]
    units, pending = [], []
    for path, result in zip(paths, per_file):
        try:
            if Path(path).suffix.lower() not in _CPP:
                continue
            try:
                Path(path).resolve().relative_to(Path(root).resolve())
            except ValueError as exc:
                raise QtCppError("QT_CPP_ROOT", "Qt C++ source is outside the scan root") from exc
            if not is_qt_cpp_source(path):
                pending.append((path, result))
                continue
            unit = read_cpp(Path(path), Path(root))
            units.append((map_cpp(unit, nodes, edges, root=Path(root)), result))
        except QtCppError as error:
            _failure(result, path, root, error)
    classes = [record for mapping, _ in units for record in mapping.classes]
    # Borrowed complete bodies retain their source/span identity so binding can
    # deduplicate the same accepted body reconstructed by the canonical mapper.
    classes.extend({"node_id": md["class_id"], "qualified_name": md["class_name"],
                    "source_file": node.get("source_file"), "span": md.get("span", {}),
                    "is_definition": md.get("is_definition")}
                   for node in nodes if (md := qt_metadata(node)).get("kind") == "class"
                   and md.get("class_id") and md.get("class_name"))
    for path, result in pending:
        try:
            if (is_qt_cpp_source(path, class_names=[item["qualified_name"] for item in classes])
                    or ((units or classes) and type_dependency_source(path))):
                unit = read_cpp(Path(path), Path(root))
                units.append((map_cpp(unit, nodes, edges, root=Path(root)), result))
        except QtCppError as error:
            _failure(result, path, root, error)
    # All accepted header shadows must exist before any source registration is
    # resolved. This run-owned snapshot adds no include discovery or execution.
    alias_nodes = list(nodes)
    for mapping, result in units:
        dependencies = QtFacts(mapping.unit)
        try:
            add_type_dependency_facts(mapping, dependencies)
        except (QtCppError, ValueError):
            _failure(result, mapping.unit.path, root, QtCppError("QT_CPP_LIMIT", "Type dependency facts are unavailable"))
            continue
        result.setdefault("nodes", []).extend(dependencies.nodes)
        alias_nodes.extend(dependencies.nodes)
    for mapping, result in units:
        mapping.bind_classes(classes)
        facts = QtFacts(mapping.unit)
        try:
            _class_facts(mapping, facts, classes=classes, alias_nodes=alias_nodes)
            # Forward declarations remain source facts, but only a parsed body
            # establishes a registration provider; old metadata proves neither.
            add_literal_registrations(mapping, facts, [item for item in classes if item.get("is_definition") is True],
                                      alias_nodes=alias_nodes)
        except QtCppError as error:
            _failure(result, mapping.unit.path, root, error)
            continue
        except ValueError:
            _failure(result, mapping.unit.path, root, QtCppError("QT_CPP_LIMIT", "Qt metadata exceeds transport bounds"))
            continue
        result.setdefault("nodes", []).extend(facts.nodes)
        result.setdefault("edges", []).extend(facts.edges)
    return {"nodes": [node for _, result in units for node in result.get("nodes", [])
                      if "qt" in node.get("metadata", {})],
            "failures": [failure for result in per_file for failure in result.get("qml_failures", [])
                         if failure.get("code", "").startswith("QT_CPP_")]}
