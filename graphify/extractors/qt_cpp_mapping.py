"""Map bounded C++ syntax to accepted canonical declarations, never invented IDs."""
from __future__ import annotations

import re

from graphify.qml_resolution_types import source_path
from graphify.extractors.qt_cpp_syntax import walk, source_span
from graphify.extractors.qt_cpp_facts import qt_metadata


def normalize_type(value: str) -> str:
    """Whitespace equivalence only; aliases and conversions require separate evidence."""
    return re.sub(r"\s*([*&<>,:])\s*", r"\1", re.sub(r"\s+", " ", value).strip())


def _name(unit, syntax):
    if syntax is None:
        return ""
    if syntax.type in {"identifier", "field_identifier", "type_identifier", "qualified_identifier", "destructor_name", "operator_name"}:
        return unit.text(syntax)
    child = syntax.child_by_field_name("declarator")
    if child is None and syntax.type in {"reference_declarator", "pointer_declarator", "parenthesized_declarator", "array_declarator"}:
        child = syntax.named_children[-1] if syntax.named_children else None
    return _name(unit, child) if child else ""


def _qualified(unit, syntax, name):
    scopes, parent = [], syntax.parent
    while parent:
        if parent.type in {"namespace_definition", "class_specifier", "struct_specifier"}:
            scope = unit.field(parent, "name")
            if scope:
                scopes.append(scope)
        parent = parent.parent
    return "::".join(list(reversed(scopes)) + [name])


def _line(node):
    match = re.match(r"L(\d+)", str(node.get("source_location") or ""))
    return int(match[1]) if match else None


def _label(node):
    return str(node.get("label") or "").removesuffix("()").lstrip(".").split("::")[-1]


def _parameters(unit, declarator):
    params = declarator.child_by_field_name("parameters")
    values = []
    for syntax in params.named_children if params else []:
        if syntax.type not in {"parameter_declaration", "optional_parameter_declaration", "variadic_parameter_declaration"}:
            continue
        declaration = syntax.child_by_field_name("declarator")
        name = _name(unit, declaration)
        text = unit.text(syntax).split("=", 1)[0].strip()
        if name:
            position = text.rfind(name)
            text = text[:position] + text[position + len(name):]
        values.append({"name": name, "type": normalize_type(text)})
    return [] if values == [{"name": "", "type": "void"}] else values


def _roles(unit, declaration, class_syntax):
    access = "private" if class_syntax and class_syntax.type == "class_specifier" else "public"
    roles = []
    if class_syntax:
        body = class_syntax.child_by_field_name("body")
        previous = class_syntax.start_byte
        for child in body.named_children if body else []:
            if child.start_byte >= declaration.start_byte:
                break
            if child.type == "access_specifier":
                literal = unit.code[child.start_byte:child.end_byte].decode().strip()
                access = "private" if "private" in literal else "protected" if "protected" in literal else "public"
                gap_end = unit.code.find(b":", child.end_byte)
                text = unit.code[child.start_byte:gap_end + 1].decode() if gap_end >= 0 else literal
                roles = ["signal"] if re.search(r"\b(?:signals|Q_SIGNALS)\b", text) else ["slot"] if re.search(r"\b(?:slots|Q_SLOTS)\b", text) else []
            previous = max(previous, child.end_byte)
        prefix = unit.code[previous:declaration.start_byte].decode()
        if re.search(r"\b(?:Q_SIGNAL)\b", prefix):
            roles = list(set(roles + ["signal"]))
        if re.search(r"\b(?:Q_SLOT)\b", prefix):
            roles = list(set(roles + ["slot"]))
        if re.search(r"\bQ_INVOKABLE\b", prefix):
            roles = list(set(roles + ["invokable"]))
    return sorted(roles), access


class CppMapping:
    """Borrowed generic nodes remain unchanged; source records retain ambiguity."""

    def __init__(self, unit, nodes, edges, *, root):
        self.unit, self.nodes, self.edges = unit, list(nodes), list(edges)
        self.classes, self.functions = [], []
        self.paths = {id(node): source_path(node, root) for node in self.nodes}
        self.definition_paths = {id(node): source_path({"source_file": node.get("definition_file")}, root)
                                 for node in self.nodes}
        self.parents = {}
        self.class_parents = {}
        accepted = {node["id"]: node for node in self.nodes}
        for edge in self.edges:
            if edge.get("relation") in {"method", "contains"}:
                self.parents.setdefault(edge["target"], set()).add(edge["source"])
                parent = accepted.get(edge["source"], {})
                if (edge.get("confidence") == "EXTRACTED" and parent.get("_callable_class") is True
                        and source_path(edge, root) == source_path(parent, root)):
                    self.class_parents.setdefault(edge["target"], set()).add(edge["source"])
        syntax_nodes = list(walk(unit.tree))
        for syntax in syntax_nodes:
            if syntax.type not in {"class_specifier", "struct_specifier"}:
                continue
            name = unit.field(syntax, "name")
            matches = [node["id"] for node in self.nodes if self.paths[id(node)] == unit.relative_file
                       and _label(node) == name and _line(node) == syntax.start_point.row + 1
                       and (node.get("_callable_class") or node.get("type") in {"class", "struct"})]
            record = self._record(syntax, name, _qualified(unit, syntax, name), matches)
            record["class_id"] = record["node_id"]
            record["is_definition"] = syntax.child_by_field_name("body") is not None
            record["macros"] = [macro for macro in unit.macros if syntax.start_byte <= macro["start_byte"] < syntax.end_byte]
            self.classes.append(record)
        # A generic producer collision is not evidence that two namespaces are one.
        for record in self.classes:
            others = [item for item in self.classes if item["node_id"] == record["node_id"] and item["qualified_name"] != record["qualified_name"]]
            if record["node_id"] and others:
                record.update(status="ambiguous", node_id="", class_id="")
        for syntax in syntax_nodes:
            if syntax.type != "function_declarator":
                continue
            self._function(syntax)

    def _record(self, syntax, name, qualified, matches):
        candidates = sorted(set(matches))
        return {"syntax": syntax, "span": source_span(self.unit.source, syntax.start_byte, syntax.end_byte),
                "name": name, "qualified_name": qualified, "source_file": self.unit.relative_file,
                "node_id": candidates[0] if len(candidates) == 1 else "",
                "status": "resolved" if len(candidates) == 1 else "ambiguous" if candidates else "unavailable",
                "candidates": candidates[:50]}

    def _function(self, declarator):
        declaration = declarator.parent
        while declaration and declaration.type not in {"function_definition", "field_declaration", "declaration"}:
            declaration = declaration.parent
        if declaration is None:
            return
        name = _name(self.unit, declarator.child_by_field_name("declarator"))
        if not name:
            return
        class_record = self.class_at(declaration.start_byte)
        short, class_id = name.split("::")[-1], class_record["node_id"] if class_record else ""
        matches = [node["id"] for node in self.nodes if _label(node) == short and node.get("_callable")
                   and ((class_id and class_id in self.parents.get(node["id"], ())) or
                        (not class_id and self.paths[id(node)] == self.unit.relative_file and _line(node) == declarator.start_point.row + 1))]
        # Canonical header merges retain the implementation's exact file/line.
        # That source identity is stronger than a name-only class lookup, and
        # avoids losing ownership after source_file moves back to the header.
        definition_matches = [node["id"] for node in self.nodes if _label(node) == short
                              and node.get("_callable") is True and not node.get("_callable_class")
                              and self.definition_paths[id(node)] == self.unit.relative_file
                              and _line({"source_location": node.get("definition_location")}) == declaration.start_point.row + 1]
        if not class_id and definition_matches:
            matches = definition_matches
        if not class_id and "::" in name and not definition_matches:
            owners = {owner for candidate in matches for owner in self.parents.get(candidate, ())}
            wanted = name.split("::")[-2]
            owners = {node["id"] for node in self.nodes if node["id"] in owners and _label(node) == wanted and node.get("_callable_class")}
            class_id = next(iter(owners)) if len(owners) == 1 else ""
        qualified = _qualified(self.unit, declaration, name)
        record = self._record(declaration, short, qualified, matches)
        parameters = _parameters(self.unit, declarator)
        roles, access = _roles(self.unit, declaration, class_record["syntax"] if class_record else None)
        record.update(class_id=class_id, class_name=class_record["qualified_name"] if class_record else qualified.rsplit("::", 1)[0] if "::" in qualified else "",
                      definition_owners=sorted({owner for candidate in definition_matches for owner in self.class_parents.get(candidate, ())}),
                      parameters=parameters, parameter_types=[item["type"] for item in parameters],
                      return_type=normalize_type(self.unit.field(declaration, "type")), roles=roles, access=access,
                      body=declaration.child_by_field_name("body"), signature=short + "(" + ",".join(item["type"] for item in parameters) + ")")
        self.functions.append(record)

    def owner_at(self, byte):
        matches = [record for record in self.functions if record["span"]["start_byte"] <= byte < record["span"]["end_byte"]]
        return min(matches, key=lambda record: record["span"]["end_byte"] - record["span"]["start_byte"]) if matches else None

    def bind_classes(self, classes):
        """Join exact implementation evidence to a sole accepted complete class.

        Forward declarations remain source facts but do not compete with bodies.
        Legacy metadata without an explicit body flag cannot prove completeness.
        """
        definitions = {}
        for item in list(classes) + [
            {"node_id": md.get("class_id"), "qualified_name": md.get("class_name"),
             "source_file": node.get("source_file"), "span": md.get("span", {}),
             "is_definition": md.get("is_definition")}
            for node in self.nodes if (md := qt_metadata(node)).get("kind") == "class"
        ]:
            if item.get("is_definition") is not True or not item.get("node_id"):
                continue
            span = item.get("span", {})
            identity = (item["node_id"], item["qualified_name"], item.get("source_file"),
                        span.get("start_byte"), span.get("end_byte"))
            definitions[identity] = item
        for record in self.functions:
            if record["class_id"] or not record["class_name"]:
                continue
            owners = record["definition_owners"]
            found = [item for item in definitions.values()
                     if (item["node_id"] in owners if owners else item["qualified_name"] == record["class_name"])]
            if len(found) != 1:
                continue
            definition = found[0]
            # A conflicting real body invalidates an apparently unique parent;
            # explicit foreign qualification cannot reuse another class's owner.
            name = definition["qualified_name"]
            if (sum(item["qualified_name"] == name for item in definitions.values()) != 1
                    or (record["class_name"] != name and ("::" in record["class_name"]
                        or record["class_name"] != name.rsplit("::", 1)[-1]))):
                continue
            class_id = definition["node_id"]
            candidates = {node["id"] for node in self.nodes if node.get("_callable") and _label(node) == record["name"]
                          and class_id in self.class_parents.get(node["id"], ())}
            if owners:
                candidates.intersection_update(record["candidates"])
            record.update(class_id=class_id, class_name=name, node_id=next(iter(candidates)) if len(candidates) == 1 else "",
                          status="resolved" if len(candidates) == 1 else "ambiguous" if candidates else "unavailable")

    def class_at(self, byte):
        matches = [record for record in self.classes if record["span"]["start_byte"] <= byte < record["span"]["end_byte"]]
        if matches:
            return min(matches, key=lambda record: record["span"]["end_byte"] - record["span"]["start_byte"])
        return None


def map_cpp(unit, accepted_nodes, accepted_edges, *, root):
    return CppMapping(unit, accepted_nodes, accepted_edges, root=root)
