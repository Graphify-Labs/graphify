"""Read-only class-field shadowing for concrete call maps.

Declaration storage never proves a callable target. Actual extracted field and
method edges own lexical membership; this per-analysis index adds no persisted
owner IDs and never resolves a dynamic callback, condition or runtime object.
"""
from __future__ import annotations

from graphify.rcfile import effective_suffix

def _name(value):
    return str(value or "").removesuffix("()").removeprefix(".").removeprefix("@")


def _storage(node):
    metadata = node.get("metadata")
    if not isinstance(metadata, dict) or not node.get("source_file"):
        return False
    # The C# member family owns data only. Damaged supplementary transport must
    # not turn that promise into call authority in a node-only borrowed view.
    if "csharp_member" in metadata:
        return True
    fact = metadata.get("cpp_declarator")
    return (isinstance(fact, dict) and type(fact.get("contract_version")) is int
            and fact["contract_version"] == 1 and fact.get("kind") == "field")


class FieldCallPolicy:
    """Build one immutable-view index from accepted source nodes/edges."""

    def __init__(self, nodes, edges, *, class_ids=None):
        by_id = {node["id"]: node for node in nodes}
        classes = (set(class_ids) if class_ids is not None else
                   {node["id"] for node in nodes if node.get("_callable_class")})
        self.storage = frozenset(node["id"] for node in nodes if _storage(node))
        # Existing C# properties share the source-owned field edge contract;
        # property storage also cannot supply a concrete delegate target.
        property_ids = {edge.get("target") for edge in edges
                        if edge.get("source") in classes and edge.get("relation") == "defines"
                        and edge.get("context") == "field" and edge.get("confidence") == "EXTRACTED"
                        and edge.get("target") in by_id
                        and effective_suffix(str(by_id[edge["target"]].get("source_file", ""))) == ".cs"
                        and edge.get("source_file") == by_id[edge["target"]].get("source_file")}
        self.storage |= property_ids
        self.fields, self.methods, self.owners, self.bases = {}, {}, {}, {}
        for edge in edges:
            owner, target = edge.get("source"), edge.get("target")
            if owner not in classes or target not in by_id:
                continue
            relation = edge.get("relation")
            if relation == "defines" and target in self.storage:
                field = by_id[target]
                if (edge.get("context") == "field" and edge.get("confidence") == "EXTRACTED"
                        and edge.get("source_file") == field.get("source_file")):
                    self.fields.setdefault(owner, set()).add(_name(field.get("label")))
                    self.owners.setdefault(target, set()).add(owner)
            elif relation == "method":
                self.methods.setdefault(owner, set()).add(_name(by_id[target].get("label")))
                self.owners.setdefault(target, set()).add(owner)
            elif relation == "inherits" and target in classes:
                self.bases.setdefault(owner, set()).add(target)
        self.classes = frozenset(classes)
        self.lexical_parents = {}
        for edge in edges:
            if (edge.get("relation") == "contains" and edge.get("context") == "csharp_local_function"
                    and edge.get("confidence") == "EXTRACTED" and edge.get("source") in by_id
                    and edge.get("target") in by_id and edge.get("source_file") == by_id[edge["target"]].get("source_file")):
                self.lexical_parents.setdefault(edge["target"], set()).add(edge["source"])

    def _roots(self, caller):
        roots, pending, visited = set(), {caller}, set()
        while pending:
            current = pending.pop()
            if current in visited:
                continue
            visited.add(current)
            roots.update(self.owners.get(current, ()))
            if current in self.classes:
                roots.add(current)
            pending.update(self.lexical_parents.get(current, ()))
        return roots

    def has_member(self, caller, callee):
        """An actual C++ member name hides free functions independently of call arity."""
        name, pending, visited = _name(callee), self._roots(caller), set()
        while pending:
            level = pending - visited
            if not level:
                return False
            visited.update(level)
            if any(name in self.fields.get(owner, ()) or name in self.methods.get(owner, ()) for owner in level):
                return True
            pending = {base for owner in level for base in self.bases.get(owner, ())}
        return False

    def shadows(self, caller, callee, *, is_member=False, receiver=None):
        """Block only bare/self field lookup, respecting a nearer actual method."""
        if is_member and receiver != "this":
            return False
        name = _name(callee)
        pending = self._roots(caller)
        visited = set()
        while pending:
            level = pending - visited
            if not level:
                break
            visited.update(level)
            if any(name in self.fields.get(owner, ()) for owner in level):
                return True
            if any(name in self.methods.get(owner, ()) for owner in level):
                return False
            pending = {base for owner in level for base in self.bases.get(owner, ())}
        return False
