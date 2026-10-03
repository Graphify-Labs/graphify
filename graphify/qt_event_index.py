"""Exact accepted Qt member lookup and deliberately bounded compatibility proof."""
from __future__ import annotations

from graphify.extractors.qt_cpp_facts import qt_metadata
from graphify.extractors.qt_cpp_mapping import normalize_type
from graphify.qml_resolution_types import Resolution, answer
import re


def value_type(value):
    value = normalize_type(value)
    if "*" in value or "&&" in value:
        return value
    const = bool(re.search(r"\bconst\b", value))
    value = re.sub(r"\bconst\b", "", value)
    return normalize_type(value.replace("&", "") if const else value)


class QtEventIndex:
    """Class-qualified declarations, never a repository-wide member-name table."""

    def __init__(self, nodes):
        self.nodes = {node["id"]: node for node in nodes}
        self.classes, self.members, self.callables = {}, {}, {}
        for node in nodes:
            metadata = qt_metadata(node)
            if metadata.get("kind") == "class":
                self.classes.setdefault(metadata.get("class_name"), []).append(node)
            elif metadata.get("kind") == "member":
                self.members.setdefault((metadata.get("class_name"), metadata.get("raw_name")), []).append(node)
            elif metadata.get("kind") == "callable":
                self.callables.setdefault((node.get("source_file"), metadata.get("callable_name")), []).append(node)

    def class_name(self, name):
        if name in self.classes and len(self.classes[name]) == 1:
            return name
        return ""

    def inherits(self, actual, declared, seen=None):
        actual, declared = self.class_name(actual), self.class_name(declared)
        if not actual or not declared:
            return False
        if actual == declared:
            return True
        seen = set() if seen is None else seen
        if actual in seen or len(seen) >= 32:
            return False
        seen.add(actual)
        metadata = qt_metadata(self.classes[actual][0])
        return any(self.inherits(base, declared, seen) for base in metadata.get("bases", []))

    def member(self, endpoint, actual_type, *, role=None, owner_class=""):
        if endpoint.get("form") not in {"legacy", "member_pointer"}:
            return Resolution("dynamic", reason="dynamic_endpoint")
        actual = self.class_name(actual_type)
        declared = self.class_name(endpoint.get("class_name") or actual_type)
        if not actual or not declared:
            return Resolution("unavailable", reason="unestablished_object_type")
        if not self.inherits(actual, declared):
            return Resolution("unavailable", reason="object_member_type_mismatch")
        candidates = list(self.members.get((declared, endpoint.get("member_name")), []))
        if not candidates:
            bases = qt_metadata(self.classes[declared][0]).get("bases", [])
            candidates = [node for base in bases for node in self.members.get((self.class_name(base), endpoint.get("member_name")), [])]
        grouped = {}
        for node in candidates:
            metadata = qt_metadata(node)
            key = (metadata.get("generic_target_id") or node["id"], metadata.get("signature"))
            grouped.setdefault(key, []).append(node)
        candidates = [min(group, key=lambda node: (qt_metadata(node).get("access") == "public", not bool(qt_metadata(node).get("roles")), node["id"])) for group in grouped.values()]
        if role:
            candidates = [node for node in candidates if role in qt_metadata(node).get("roles", [])]
        if endpoint.get("selector"):
            normalizer = value_type if endpoint.get("form") == "legacy" else normalize_type
            wanted = [normalizer(value) for value in endpoint.get("parameter_types", [])]
            candidates = [node for node in candidates if [normalizer(value) for value in qt_metadata(node).get("parameter_types", [])] == wanted]
        if endpoint.get("form") == "member_pointer":
            candidates = [node for node in candidates if qt_metadata(node).get("access") == "public"
                          or qt_metadata(node).get("class_name") == owner_class]
        return answer([node["id"] for node in candidates], reason="member_not_proven", evidence=("source_type", "declared_signature"))

    def emission(self, metadata):
        expression = {"form": "legacy", "member_name": metadata.get("member_name"), "selector": False}
        result = self.member(expression, metadata.get("receiver_type") or "", role="signal")
        if result.status == "resolved":
            parameters = qt_metadata(self.nodes[result.target_id]).get("parameter_types", [])
            if len(parameters) != metadata.get("argument_count"):
                return Resolution("unavailable", reason="signal_argument_count_mismatch")
        return result

    def compatible(self, signal_id, receiver_id=None, parameters=None):
        offered = qt_metadata(self.nodes[signal_id]).get("parameter_types", [])
        required = parameters if parameters is not None else qt_metadata(self.nodes[receiver_id]).get("parameter_types", [])
        if len(required) > len(offered):
            return False
        # This profile proves exact normalized types only. Compiler conversions,
        # typedefs, and templated callable deduction stay explicitly unsupported.
        return all(value_type(left) == value_type(right) for left, right in zip(offered, required))

    def callable(self, site):
        metadata = qt_metadata(site)
        if metadata.get("callable_form") == "functor":
            declared = self.class_name(metadata.get("callable_type", ""))
            candidates = self.members.get((declared, "operator()"), [])
            candidates = [node for node in candidates if qt_metadata(node).get("access") == "public"]
        else:
            candidates = self.callables.get((site.get("source_file"), metadata.get("callable_reference")), [])
        return answer([node["id"] for node in candidates], reason="callable_signature_unestablished", evidence=("source_callable",))
