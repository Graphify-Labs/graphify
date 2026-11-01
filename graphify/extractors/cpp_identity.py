"""Exact named C++ class scopes own qualified IDs before generic deduplication.

Unambiguous global IDs retain the existing contract. A qualified or colliding
owner adds a digest of its case-sensitive spelling: normalization must not
conflate namespace separators, underscores or case. No compiler is consulted.
"""
from __future__ import annotations

import hashlib

from graphify.extractors.base import _make_id, _read_text


def _walk(root):
    pending = [root]
    while pending:
        node = pending.pop()
        yield node
        pending.extend(reversed(node.named_children))


def _name(value, *, bounded=True):
    return bool(value and (not bounded or len(value.encode()) <= 384)
                and all(part.isidentifier() for part in value.split("::")))


def lexical_scope(node, source, *, bounded=True):
    """Anonymous/function-local scopes cannot establish a named native owner."""
    parts, parent = [], node.parent
    while parent:
        if parent.type in {"function_definition", "lambda_expression"}:
            return None
        if parent.type in {"namespace_definition", "class_specifier", "struct_specifier"}:
            name = _read_text(parent.child_by_field_name("name"), source) if parent.child_by_field_name("name") else ""
            if not _name(name, bounded=bounded):
                return None
            parts.append(name)
        parent = parent.parent
    return "::".join(reversed(parts))


def _reference_context(name, node, source):
    """Only owning name links carry qualification; template arguments stay local."""
    if node.type not in {"type_identifier", "identifier", "qualified_identifier", "template_type"}:
        return name, node, name.rsplit("::", 1)[-1]
    leaf = node
    while leaf.type in {"qualified_identifier", "template_type"}:
        child = leaf.child_by_field_name("name")
        if child is None:
            break
        leaf = child
    if _name(name.removeprefix("::")) and _read_text(leaf, source) != name.rsplit("::", 1)[-1]:
        return name, node, name.rsplit("::", 1)[-1]
    context = leaf
    while (context.parent is not None and context.parent.type in {"qualified_identifier", "template_type"}
           and context.parent.child_by_field_name("name") == context):
        context = context.parent
    return source[context.start_byte:leaf.end_byte].decode("utf-8", errors="replace"), context, _read_text(leaf, source)


def qualified_class_id(stem, qualified):
    """Keep plain global IDs; salt exact qualified names before case folding."""
    if "::" not in qualified or not _name(qualified):
        return _make_id(stem, qualified)
    return _exact_class_id(stem, qualified)


def _exact_class_id(stem, qualified):
    """A literal class name owns its collision domain before normalization."""
    digest = hashlib.sha256(qualified.encode()).hexdigest()
    return _make_id(stem, "cppq", digest, qualified.rsplit("::", 1)[-1][:32])


def _separate_class_candidates(records, stem, *, reserved_ids=()):
    """Reserve literal candidates before escaping actual collision domains."""
    records, buckets = tuple(records), {}
    for record in records:
        buckets.setdefault(record["id"], set()).add(record["qualified"])
    occupied, assigned = set(buckets) | set(reserved_ids), {}
    for original, names in sorted(buckets.items()):
        for qualified in sorted(names):
            candidate = original
            if len(names) > 1:
                base = _exact_class_id(stem, qualified)
                candidate, counter = base, 2
                while candidate in occupied:
                    candidate = _make_id(base, str(counter))
                    counter += 1
                occupied.add(candidate)
            assigned[(original, qualified)] = candidate
    for record in records:
        previous = record["id"]
        record["id"] = assigned[(previous, record["qualified"])]
        record["collision_identity"] = record["id"] != previous


def qualified_function_id(stem, node, name, source, *, identities=None):
    """Qualified out-of-line methods use the same actual owner ID as the header."""
    scope = lexical_scope(node, source)
    if scope is None or "::" not in name:
        return _make_id(stem, name)
    owner, member = name.rsplit("::", 1)
    owner = "::".join(filter(None, (scope, owner)))
    destructor = member == "~" + owner.rsplit("::", 1)[-1]
    if not _name(owner) or not (member.isidentifier() or destructor):
        return _make_id(stem, name)
    record = identities.owner_record(owner) if identities is not None else None
    if destructor and not (record and record["collision_identity"]):
        return _make_id(stem, name)  # Existing unambiguous destructor IDs stay literal.
    class_id = record["id"] if record else qualified_class_id(stem, owner)
    if (member == owner.rsplit("::", 1)[-1]
            and node.child_by_field_name("type") is None):
        from graphify.extractors.cpp_constructor_signature import constructor_id
        if record and identities is not None:
            class_id = identities.constructor_owner_id(record)
        return constructor_id(class_id, member, node, source, owner)
    return _make_id(class_id, member)


class CppIdentity:
    """One immutable AST index; forward facts cannot hide a complete body."""

    def __init__(self, root, source, stem):
        self.source, self.stem = source, stem
        self.records, self.groups = {}, {}
        # Generic declaration allocation owns IDs. Borrow its accepted IDs and
        # alias scopes for this run without changing the immutable AST records.
        self.declarations, self.aliases, self.alias_ids = {}, {}, set()
        self.member_nodes = {}
        self.member_occurrences = {}
        self.reference_names = set()
        self.body_owners = {}
        for node in _walk(root):
            if node.type not in {"class_specifier", "struct_specifier"}:
                continue
            name_node = node.child_by_field_name("name")
            name = _read_text(name_node, source) if name_node else ""
            scope = lexical_scope(node, source)
            qualified = "::".join(filter(None, (scope, name))) if scope is not None else ""
            if scope is None or not _name(qualified):
                continue
            record = {"syntax": node, "name": name, "scope": scope,
                      "qualified": qualified, "id": qualified_class_id(stem, qualified),
                      "is_definition": node.child_by_field_name("body") is not None}
            self.records[node.id] = record
            self.reference_names.add(name.rsplit("::", 1)[-1])
            self.groups.setdefault(qualified, []).append(record)
        # An admitted implementation need not repeat its header's classes.
        # Qualifier spelling only separates colliding body IDs; it supplies no
        # class fact, namespace classification, header read or native authority.
        from graphify.extractors.cpp_declarators import member_declarator
        for node in _walk(root):
            if node.type != "function_definition":
                continue
            shape = member_declarator(node.child_by_field_name("declarator"), source)
            scope = lexical_scope(node, source)
            if not shape or not shape[1] or "::" not in shape[0] or scope is None:
                continue
            owner = "::".join(filter(None, (scope, shape[0].rsplit("::", 1)[0])))
            if _name(owner) and owner not in self.groups:
                self.body_owners[owner] = {"qualified": owner, "id": qualified_class_id(stem, owner)}
        # Only distinct literal class names sharing a candidate need a domain.
        # Literal lookalikes retain their old IDs, even when their spelling is a
        # generated domain. Forward/body repeats keep the same exact identity.
        ordinary_classes = {record["id"] for record in self.records.values()}
        ordinary_bodies = {record["id"] for record in self.body_owners.values()}
        _separate_class_candidates(self.records.values(), stem, reserved_ids=ordinary_bodies)
        allocated_classes = {record["id"] for record in self.records.values()}
        _separate_class_candidates(self.body_owners.values(), stem,
                                   reserved_ids=ordinary_classes | allocated_classes)

    def record(self, node):
        return self.records.get(node.id)

    def owner_record(self, qualified):
        """A real class census wins over provisional callable qualifier spelling."""
        records = self.groups.get(qualified, ())
        return records[0] if records else self.body_owners.get(qualified)

    def bind_class(self, record, identity):
        """Remember the generic producer's allocated ID for this exact class."""
        self.declarations[record["qualified"]] = identity

    def declaration_id(self, record):
        """AST names keep their lexical ID; references use the actual declaration."""
        return self.declarations.get(record["qualified"], record["id"])

    def constructor_owner_id(self, record):
        """Keep the existing authorized owner/signature suffix in a new domain.

        Collision-only source prefixes separate actual classes without adding
        an alternate constructor authorization recipe or changing its validator.
        """
        return (_make_id(record["id"], qualified_class_id("", record["qualified"]))
                if record["collision_identity"] else record["id"])

    def bind_member(self, syntax, identity):
        """Keep the real allocated callable for this exact declarator occurrence."""
        from graphify.extractors.cpp_declarators import callable_declarator
        declaration = syntax.child_by_field_name("declarator") if syntax.type == "function_definition" else syntax
        actual = callable_declarator(declaration, self.source) if declaration is not None else None
        if actual is not None:
            self.member_nodes[actual.id] = identity
            self.member_occurrences.setdefault(identity, set()).add(actual.id)

    def member_id(self, declarator):
        """Allocation belongs to one parser tree/run, never a reconstructed salt."""
        return self.member_nodes.get(declarator.id)

    def member_ambiguous(self, declarator):
        """A collapsed allocator ID does not prove one source occurrence."""
        return len(self.member_occurrences.get(self.member_id(declarator), ())) > 1

    def bind_alias(self, node, name, identity, *, original_id=None):
        """Only a produced file/namespace alias supplies lexical lookup authority."""
        scope = lexical_scope(node, self.source)
        qualified = "::".join(filter(None, (scope, name))) if scope is not None else ""
        if scope is not None and _name(qualified):
            self.aliases.setdefault(qualified, []).append((node.start_byte, identity))
            self.alias_ids.update((identity, original_id or identity))
            self.reference_names.add(name.rsplit("::", 1)[-1])

    def owns_alias_id(self, identity):
        """A basename collision is not an alternative to lexical alias proof."""
        return identity in self.alias_ids

    def constructor(self, node, name, parent_id, *, signature_source=None):
        """Inline constructors use the same exact owner/signature as prototypes."""
        parent = node.parent
        while parent and parent.type not in {"class_specifier", "struct_specifier", "translation_unit"}:
            parent = parent.parent
        record = self.record(parent) if parent else None
        if (not record or self.declaration_id(record) != parent_id or name != record["name"]
                or node.child_by_field_name("type") is not None):
            return _make_id(parent_id, name)
        from graphify.extractors.cpp_constructor_signature import constructor_id
        # Keep the established lexical owner/signature suffix. Its authorization
        # is independent of generic file/declaration collision salting; the real
        # parent edge still uses the allocated declaration ID.
        return constructor_id(self.constructor_owner_id(record), name, node, self.source if signature_source is None else signature_source, record["qualified"])

    def preferred(self, record):
        group = self.groups[record["qualified"]]
        complete = [item for item in group if item["is_definition"]]
        return (complete or group)[0]

    def ambiguous(self, record):
        return sum(item["is_definition"] for item in self.groups[record["qualified"]]) > 1

    def reference(self, name, node):
        """Resolve exact in-file class scopes without borrowing a basename."""
        return self.reference_result(name, node)[0]

    def reference_result(self, name, node, *, known_aliases=frozenset()):
        """Return one lookup decision and its source-local rejection context.

        Opaque written qualifiers can reject a known literal, never resolve its
        leaf. The caller's existing alias census supplies later declarations as
        negative evidence only; function/anonymous scopes retain legacy fallback.
        """
        if not isinstance(name, str) or not name:
            return "", False, "", None, node, ""
        lookup, context, leaf = _reference_context(name, node, self.source)
        raw_name = name if isinstance(name, str) and _name(name.removeprefix("::")) else leaf
        known = leaf in self.reference_names or leaf in known_aliases
        scope = lexical_scope(context, self.source, bounded=False)
        unavailable = ("", known and scope is not None, raw_name, scope, context, lookup)
        if scope is None:
            return unavailable
        if len(scope.encode("utf-8")) > 384 or not _name(lookup.removeprefix("::")):
            return unavailable
        choices = [""] if lookup.startswith("::") else [
            "::".join(scope.split("::")[:end]) for end in range(len(scope.split("::")), -1, -1)]
        raw = lookup.removeprefix("::")
        for prefix in choices:
            qualified = "::".join(filter(None, (prefix, raw)))
            visible = [record for record in self.groups.get(qualified, ())
                       if record["syntax"].start_byte <= node.start_byte]
            aliases = {identity for start, identity in self.aliases.get(qualified, ())
                       if start <= node.start_byte}
            if aliases:
                return (next(iter(aliases)), False, raw_name, scope, context, lookup) if len(aliases) == 1 and not visible else unavailable
            if visible:
                return self.declaration_id(visible[0]), False, raw_name, scope, context, lookup
        return unavailable
