"""Validate accepted declaration-type hops for a context provider's public API."""
from __future__ import annotations

from graphify.extractors.qt_cpp_facts import qt_metadata
from graphify.extractors.qt_cpp_api_shape import api_shape
from graphify.extractors.cpp_class_proof import class_fact
from graphify.extractors.cpp_constructors import _decoded
from graphify.extractors.cpp_member_identity import member_fact


def _api_kind(member):
    shape = api_shape(qt_metadata(member).get("api_type_spelling"))
    return shape[1] if shape else ""


class DeclaredProviderIndex:
    """One run owns borrowed type evidence; no source reads or global name guesses."""
    def __init__(self, nodes):
        # NetworkX stores identity in mapping keys; raw extraction stores it in
        # each dictionary. Borrow data without mutating either representation.
        self.nodes = ({identity: {**node, "id": identity} for identity, node in nodes.items()}
                      if hasattr(nodes, "items") else {node["id"]: node for node in nodes})
        self.classes, self.members, self.accessors = {}, {}, {}
        for node in self.nodes.values():
            md = qt_metadata(node)
            if md.get("kind") == "class" and md.get("is_definition") is True:
                self.classes.setdefault(md.get("class_id"), []).append(node)
            elif md.get("kind") in {"member", "api_field", "property"}:
                self.members.setdefault((md.get("class_id"), md.get("raw_name")), []).append(node)
            elif md.get("kind") == "property_accessor":
                self.accessors.setdefault((md.get("property_id"), md.get("accessor_role")), []).append(node)

    def class_record(self, identity, *, qobject=False):
        records = self.classes.get(identity, [])
        if (len(records) != 1 or identity not in self.nodes
                or self.nodes[identity].get("_callable_class") is not True):
            return None
        md = qt_metadata(records[0])
        canonical = self.nodes[identity]
        fact = class_fact(canonical)
        if (md.get("status") != "resolved" or md.get("api_declaration_conditional") is not False
                or (qobject and not md.get("is_qobject")) or not fact or fact.get("ambiguous")
                or fact.get("is_definition") is not True or md.get("owner_id") != identity
                or md.get("span") != fact.get("span")
                or records[0].get("source_file") != canonical.get("source_file")
                or md.get("class_name") != _decoded(fact.get("qualified_name_b64"))):
            return None
        return records[0]

    def source_owned(self, declaration):
        """Borrow exact original class/member proof; no corpus rereads or name repair."""
        md = qt_metadata(declaration)
        parent = self.class_record(md.get("class_id"))
        if parent is None or md.get("owner_id") != md.get("class_id") or md.get("status") != "resolved":
            return False
        owner, span = qt_metadata(parent), md.get("span", {})
        bounds = owner.get("span", {})
        if (not isinstance(span, dict) or any(type(span.get(key)) is not int or span[key] < 0 for key in bounds)
                or declaration.get("source_file") != parent.get("source_file")
                or md.get("class_name") != owner.get("class_name")
                or not bounds["start_byte"] < span["start_byte"] < span["end_byte"] < bounds["end_byte"]
                or not (bounds["start_row"], bounds["start_column"]) < (span["start_row"], span["start_column"])
                or not (span["end_row"], span["end_column"]) < (bounds["end_row"], bounds["end_column"])
                or declaration.get("source_location") != f"L{span['start_row'] + 1}-L{span['end_row'] + 1}"):
            return False
        if md.get("kind") == "member":
            target = self.nodes.get(md.get("generic_target_id"), {})
            fact = member_fact(target)
            return bool(fact and not fact.get("ambiguous") and fact.get("role") == "declaration"
                        and fact.get("span") == span and target.get("source_file") == declaration.get("source_file")
                        and _decoded(fact.get("owner_b64")) == md.get("class_name")
                        and _decoded(fact.get("member_b64")) == md.get("raw_name"))
        return md.get("kind") in {"api_field", "property"}

    def accessor_owned(self, accessor, property_node, role):
        """Accessor links repeat the annotation's exact owner, name, file and span."""
        md, prop = qt_metadata(accessor), qt_metadata(property_node)
        return bool(self.source_owned(property_node) and md.get("kind") == "property_accessor"
                    and md.get("status") == "resolved" and md.get("accessor_role") == role
                    and md.get("owner_id") == property_node["id"] and md.get("property_id") == property_node["id"]
                    and isinstance(prop.get(role), str) and md.get("raw_name") == prop[role]
                    and md.get("span") == prop.get("span")
                    and accessor.get("source_file") == property_node.get("source_file")
                    and accessor.get("source_location") == property_node.get("source_location"))

    def binding_valid(self, binding):
        """Typed bindings retain the original lexical declaration and expression proof."""
        md = qt_metadata(binding)
        owner = self.nodes.get(md.get("owner_id"))
        if owner is None:
            return False
        source = qt_metadata(owner)
        if source.get("kind") != "context_exposure" or source.get("provider_type_status") is None:
            return True  # Initial-property and earlier direct-provider contracts.
        provider = self.provider(source)
        return bool(provider and qt_metadata(provider[0]).get("class_id") == md.get("provider_target_id")
                    and source.get("provider_declaration_id") == md.get("provider_declaration_id")
                    and source.get("provider_identity_status") == "resolved"
                    and isinstance(md.get("provider_type_evidence"), list)
                    and set(provider[1]) <= set(md["provider_type_evidence"]))

    def api_type(self, member):
        md = qt_metadata(member)
        raw, target = md.get("api_type_spelling"), md.get("api_type_target_id")
        position = md.get("api_type_position")
        owner = self.class_record(md.get("class_id"))
        if (md.get("status") != "resolved" or md.get("api_type_status") != "resolved"
                or api_shape(raw) is None or not self.source_owned(member)
                or not isinstance(position, int) or isinstance(position, bool)
                or owner is None or not qt_metadata(owner)["span"]["start_byte"] < position <= md.get("span", {}).get("start_byte", -1)
                or self.class_record(target, qobject=True) is None):
            return ""
        return target

    def provider(self, metadata):
        root = metadata.get("provider_root_type_id")
        steps = metadata.get("provider_expression_steps")
        shape = api_shape(metadata.get("provider_root_type_spelling"), allow_value=True)
        address_of = metadata.get("provider_root_address_of")
        if (metadata.get("provider_type_status") != "resolved" or self.class_record(root) is None
                or shape is None or not isinstance(address_of, bool)):
            return None
        if not isinstance(steps, list) or len(steps) > 8:
            return None
        current, evidence, visited, current_shape = root, [root], set(), shape[1]
        if address_of and (steps or current_shape == "pointer"):
            return None
        for step in steps:
            if not isinstance(step, dict) or set(step) != {"name", "role", "operator"}:
                return None
            if step["operator"] != ("->" if current_shape == "pointer" else "."):
                return None
            if step["role"] not in {"call", "field"} or not isinstance(step["name"], str):
                return None
            candidates = self.members.get((current, step["name"]), [])
            candidates = [node for node in candidates if qt_metadata(node).get("kind") ==
                          ("member" if step["role"] == "call" else "api_field")]
            if len(candidates) != 1 or (current, step["name"]) in visited:
                return None
            member, md = candidates[0], qt_metadata(candidates[0])
            if md.get("access") != "public" or (step["role"] == "call" and
                    (md.get("parameter_types") != [] or md.get("generic_target_id") not in self.nodes)):
                return None
            current = self.api_type(member)
            if not current:
                return None
            current_shape = _api_kind(member)
            visited.add((md["class_id"], step["name"]))
            evidence.extend((member["id"], current))
        if not steps and not address_of and current_shape != "pointer":
            return None
        record = self.class_record(current, qobject=True)
        return (record, list(dict.fromkeys(evidence + [record["id"]]))) if record is not None else None

    def property_type(self, property_node):
        """Q_PROPERTY and its accepted accessor/member must agree on the API type."""
        md = qt_metadata(property_node)
        target = self.api_type(property_node)
        if not target:
            return "", []
        if isinstance(md.get("read"), str):
            links = self.accessors.get((property_node["id"], "read"), [])
            if len(links) != 1 or not self.accessor_owned(links[0], property_node, "read"):
                return "", []
            accessor = qt_metadata(links[0]).get("generic_target_id")
            methods = [node for node in self.members.get((md["class_id"], md["read"]), [])
                       if qt_metadata(node).get("generic_target_id") == accessor]
            if (len(methods) != 1 or qt_metadata(methods[0]).get("parameter_types") != []
                    or self.api_type(methods[0]) != target
                    or _api_kind(methods[0]) != _api_kind(property_node)):
                return "", []
            return target, [property_node["id"], links[0]["id"], methods[0]["id"], target]
        if isinstance(md.get("member"), str):
            fields = [node for node in self.members.get((md["class_id"], md["member"]), [])
                      if qt_metadata(node).get("kind") == "api_field"]
            if (len(fields) == 1 and self.api_type(fields[0]) == target
                    and _api_kind(fields[0]) == _api_kind(property_node)):
                return target, [property_node["id"], fields[0]["id"], target]
        return "", []
