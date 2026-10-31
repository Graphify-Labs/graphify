"""Plan literal C++ member candidates before normalized allocation drops facts.

This per-source index owns names and collision reservations only. The existing
producer supplies actual owner/candidate IDs; class, signature, body and native
authority remain with their source-proof owners. Exact same-name declarations
retain their existing overload/duplicate policy, and unrelated IDs stay intact.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
import hashlib

from graphify.extractors.base import _make_id, _read_text
from graphify.extractors.cpp_declarators import member_declarator, is_destructor_prototype
from graphify.extractors.cpp_identity import lexical_scope, qualified_class_id
from graphify.extractors.cpp_constructors import constructor_candidate_ids
from graphify.ids import normalize_id


_CONTAINERS = {"class_specifier", "struct_specifier", "union_specifier"}


def _walk(root):
    pending = [root]
    while pending:
        node = pending.pop()
        yield node
        pending.extend(reversed(node.named_children))


def _owner(node):
    parent = node.parent
    while parent is not None:
        if parent.type in _CONTAINERS:
            return parent
        if parent.type in {"function_definition", "lambda_expression", "translation_unit", "namespace_definition"}:
            return None
        parent = parent.parent
    return None


@dataclass(frozen=True)
class _Member:
    name: str
    domain: object
    record: object
    definition: bool
    prefixes: tuple[str, ...] = ()


class CppMemberNames:
    """One source census and deterministic plan, with no ambient project state."""

    def __init__(self, identities, functions, *, reserved_ids=()):
        self.identities = identities
        source, stem = identities.source, identities.stem
        entries, groups = {}, defaultdict(lambda: defaultdict(set))
        names = defaultdict(set)
        reserved = set(reserved_ids)
        reserved.update(record["id"] for record in identities.records.values())
        reserved.update(record["id"] for record in identities.body_owners.values())
        reserved.update(record["id"] for record in functions.records.values())
        # Constructor syntax/signature ownership stays with its existing query;
        # these IDs reject data collisions and never rewrite the constructor.
        reserved.update(constructor_candidate_ids(functions.root, functions.source, identities))

        def retain(syntax, name, container, *, definition=False, prefixes=(), domain=None):
            record = identities.record(container) if container is not None else None
            owner_name = _read_text(container.child_by_field_name("name"), source) if container is not None and container.child_by_field_name("name") else ""
            # Constructors already have a signature-owned ID domain. A member
            # name collision cannot rewrite that independent authorization.
            declaration = syntax if syntax.type == "function_definition" else syntax.parent
            if (name == owner_name and declaration is not None
                    and declaration.child_by_field_name("type") is None):
                return
            domain = (record["qualified"] if record else ("container", container.id) if container is not None else domain)
            if domain is None:
                return
            entries[syntax.id] = _Member(name, domain, record, definition, tuple(prefixes))
            groups[domain][normalize_id(name)].add(name)
            names[domain].add(name)

        for node in _walk(functions.root):
            if node.type == "field_declaration" or is_destructor_prototype(node, source):
                container = _owner(node)
                if container is None or node.has_error:
                    continue
                for declarator in node.children_by_field_name("declarator"):
                    shape = member_declarator(declarator, source)
                    if shape is not None:
                        retain(declarator, shape[0], container)
            elif node.type == "function_definition":
                declarator = node.child_by_field_name("declarator")
                shape = member_declarator(declarator, source) if declarator is not None else None
                if shape is None or not shape[1]:
                    continue
                name = shape[0]
                container = _owner(node)
                if container is not None:
                    retain(node, name, container)
                    continue
                # A namespace function has an independent accepted identity.
                # Qualified spelling alone is not a new native/class decision.
                if functions.identity(node) is not None or "::" not in name:
                    continue
                scope = lexical_scope(node, source)
                if scope is None:
                    continue
                raw_owner, leaf = name.rsplit("::", 1)
                qualified = "::".join(filter(None, (scope, raw_owner)))
                if leaf == raw_owner.rsplit("::", 1)[-1] and node.child_by_field_name("type") is None:
                    continue
                records = identities.groups.get(qualified, ())
                # These are existing source identity recipes, not a basename
                # search. candidate() requires exact owner/candidate equality.
                prefixes = [record["id"] for record in records]
                actual_owner = identities.owner_record(qualified)
                if actual_owner is not None:
                    prefixes.append(actual_owner["id"])
                prefixes.extend((qualified_class_id(stem, qualified), _make_id(stem, raw_owner)))
                retain(node, leaf, None, definition=True, prefixes=prefixes, domain=qualified)

        self.entries = entries
        self.groups = {domain: {key: frozenset(value) for key, value in values.items()}
                       for domain, values in groups.items()}
        self.names = {domain: frozenset(value) for domain, value in names.items()}
        self.reserved = frozenset(reserved)
        self._plans = {}

    def _plan(self, domain, owner_id):
        key = domain, owner_id
        if key in self._plans:
            return self._plans[key]
        names = self.names[domain]
        occupied = {owner_id} | {_make_id(owner_id, name) for name in names}
        plan = {}
        # Sorting literal names only affects the vanishing digest-collision
        # tie; declaration order/lines never decide who retains a candidate.
        for name in sorted(names):
            normal = _make_id(owner_id, name)
            if (len(self.groups[domain][normalize_id(name)]) == 1
                    and normal != owner_id and normal not in self.reserved):
                plan[name] = normal
                continue
            digest = hashlib.sha256(name.encode("utf-8")).hexdigest()
            base = _make_id(owner_id, "cppmember", digest)
            candidate, escape = base, 0
            # Every candidate in this sequence differs; the finite reservation
            # set bounds the search. Real literal lookalikes keep their ID.
            while candidate in occupied or candidate in self.reserved:
                escape += 1
                candidate = _make_id(base, str(escape))
            plan[name] = candidate
            occupied.add(candidate)
        self._plans[key] = plan
        return plan

    def candidate(self, syntax, legacy_candidate, *, owner_id=None):
        """Repair a source collision only after exact owner/candidate agreement.

        No underscore/basename split recovers an owner. The caller may forward
        its real allocated owner; otherwise existing source identity records
        supply candidates and exactly one prefix must reproduce the legacy ID.
        """
        entry = self.entries.get(syntax.id)
        if entry is None or not isinstance(legacy_candidate, str):
            return legacy_candidate
        if owner_id is not None:
            prefixes = (owner_id,) if isinstance(owner_id, str) else ()
        elif entry.record is not None and not entry.definition:
            prefixes = (self.identities.declaration_id(entry.record),)
        else:
            prefixes = entry.prefixes
        accepted = {prefix for prefix in prefixes
                    if _make_id(prefix, entry.name) == legacy_candidate}
        if len(accepted) != 1:
            return legacy_candidate
        owner = next(iter(accepted))
        return self._plan(entry.domain, owner)[entry.name]
