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
                # A forward declaration is source evidence, not a competing
                # definition. Missing legacy completeness is also unproven.
                if metadata.get("is_definition") is True:
                    self.classes.setdefault(metadata.get("class_name"), []).append(node)
            elif metadata.get("kind") == "member":
                self.members.setdefault((metadata.get("class_name"), metadata.get("raw_name")), []).append(node)
            elif metadata.get("kind") == "callable":
                self.callables.setdefault((node.get("source_file"), metadata.get("callable_name")), []).append(node)

    def class_name(self, name):
        if (name in self.classes and len(self.classes[name]) == 1
                and qt_metadata(self.classes[name][0]).get("status") == "resolved"):
            return name
        return ""

    def _bases(self, name):
        """Only the producer's lexical base identity can authorize traversal."""
        metadata = qt_metadata(self.classes[name][0])
        bases, raw = metadata.get("canonical_base_names"), metadata.get("bases")
        if (metadata.get("canonical_base_status") != "resolved" or not isinstance(bases, list)
                or not isinstance(raw, list) or len(bases) != len(raw) or len(bases) > 50
                or not all(isinstance(base, str) and base for base in bases)):
            return None
        return bases

    def _base_access(self, name, bases):
        """Legacy or malformed facts never acquire a C++ inheritance default."""
        metadata = qt_metadata(self.classes[name][0])
        access = metadata.get("canonical_base_access")
        if (metadata.get("canonical_base_access_status") != "resolved" or not isinstance(access, list)
                or len(access) != len(bases) or not all(isinstance(value, str)
                and value in {"public", "protected", "private"} for value in access)):
            return None
        return access

    def _lookup_members(self, declared, name, *, public_only=False):
        """Stop each branch at its first declaration before filtering its role.

        A hidden or incompatible declaration shadows ancestors just as a signal
        does. Traversal owns one bounded run-local memo; failed or missing base
        proof cannot select a convenient declaration from another branch.
        """
        memo, visited = {}, set()

        def visit(owner, path):
            owner = self.class_name(owner)
            if not owner:
                return [], "inheritance_identity_unavailable"
            if owner in path:
                return [], "inheritance_cycle_or_limit"
            if owner in memo:
                return memo[owner]
            if len(visited) >= 32:
                return [], "inheritance_cycle_or_limit"
            visited.add(owner)
            candidates = list(self.members.get((owner, name), []))
            if candidates:
                memo[owner] = candidates, ""
                return memo[owner]
            bases = self._bases(owner)
            if bases is None:
                return [], "inheritance_identity_unavailable"
            access = self._base_access(owner, bases) if public_only else ["public"] * len(bases)
            if access is None:
                return [], "inheritance_access_unavailable"
            for base, visibility in zip(bases, access):
                inherited, reason = visit(base, path | {owner})
                if reason:
                    return [], reason
                if public_only and inherited and visibility != "public":
                    return [], "inheritance_access_unavailable"
                candidates.extend(inherited)
            memo[owner] = candidates, ""
            return memo[owner]

        return visit(declared, frozenset())

    def inherits(self, actual, declared, seen=None, *, public_only=False):
        actual, declared = self.class_name(actual), self.class_name(declared)
        if not actual or not declared:
            return False
        if actual == declared:
            return True
        seen = set() if seen is None else seen
        if actual in seen or len(seen) >= 32:
            return False
        seen.add(actual)
        bases = self._bases(actual)
        if bases is None:
            return False
        access = self._base_access(actual, bases) if public_only else ["public"] * len(bases)
        return bool(access is not None and any(self.inherits(base, declared, seen, public_only=public_only)
                    for base, visibility in zip(bases, access) if visibility == "public"))

    def member(self, endpoint, actual_type, *, role=None, owner_class=""):
        if endpoint.get("form") not in {"legacy", "member_pointer"}:
            return Resolution("dynamic", reason="dynamic_endpoint")
        actual = self.class_name(actual_type)
        declared = self.class_name(endpoint.get("class_name") or actual_type)
        if not actual or not declared:
            return Resolution("unavailable", reason="unestablished_object_type")
        public_only = endpoint.get("form") == "member_pointer"
        if not self.inherits(actual, declared):
            return Resolution("unavailable", reason="object_member_type_mismatch")
        if public_only and not self.inherits(actual, declared, public_only=True):
            return Resolution("unavailable", reason="inheritance_access_unavailable")
        candidates, reason = self._lookup_members(declared, endpoint.get("member_name"), public_only=public_only)
        if reason:
            return Resolution("unavailable", reason=reason)
        grouped = {}
        for node in candidates:
            metadata = qt_metadata(node)
            key = (metadata.get("generic_target_id") or node["id"], metadata.get("signature"))
            grouped.setdefault(key, []).append(node)
        candidates = [min(group, key=lambda node: (qt_metadata(node).get("access") == "public", not bool(qt_metadata(node).get("roles")), node["id"])) for group in grouped.values()]
        # Distinct declaring classes are ambiguous even if a selector or role
        # happens to match only one branch. Repeated diamond paths to the exact
        # same canonical declaration have already deduplicated above.
        if len({qt_metadata(node).get("class_name") for node in candidates}) > 1:
            return answer([node["id"] for node in candidates], evidence=("source_type",))
        candidates = [node for node in candidates if qt_metadata(node).get("status") == "resolved"]
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
