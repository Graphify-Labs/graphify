"""Exact named C++ class scopes own qualified IDs before generic deduplication.

Global IDs retain the existing contract. A qualified owner adds a digest of its
case-sensitive source spelling: ordinary ID normalization must not conflate
namespace separators, underscores or case. No runtime or compiler is consulted.
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


def _name(value):
    return bool(value and len(value.encode()) <= 384
                and all(part.isidentifier() for part in value.split("::")))


def lexical_scope(node, source):
    """Anonymous/function-local scopes cannot establish a named native owner."""
    parts, parent = [], node.parent
    while parent:
        if parent.type in {"function_definition", "lambda_expression"}:
            return None
        if parent.type in {"namespace_definition", "class_specifier", "struct_specifier"}:
            name = _read_text(parent.child_by_field_name("name"), source) if parent.child_by_field_name("name") else ""
            if not _name(name):
                return None
            parts.append(name)
        parent = parent.parent
    return "::".join(reversed(parts))


def qualified_class_id(stem, qualified):
    """Keep plain global IDs; salt exact qualified names before case folding."""
    if "::" not in qualified or not _name(qualified):
        return _make_id(stem, qualified)
    digest = hashlib.sha256(qualified.encode()).hexdigest()
    return _make_id(stem, "cppq", digest, qualified.rsplit("::", 1)[-1][:32])


def qualified_function_id(stem, node, name, source):
    """Qualified out-of-line methods use the same actual owner ID as the header."""
    scope = lexical_scope(node, source)
    if scope is None or "::" not in name or not _name(name):
        return _make_id(stem, name)
    owner, member = name.rsplit("::", 1)
    owner = "::".join(filter(None, (scope, owner)))
    class_id = qualified_class_id(stem, owner)
    if (member == owner.rsplit("::", 1)[-1]
            and node.child_by_field_name("type") is None):
        from graphify.extractors.cpp_constructor_signature import constructor_id
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
            self.groups.setdefault(qualified, []).append(record)

    def record(self, node):
        return self.records.get(node.id)

    def bind_class(self, record, identity):
        """Remember the generic producer's allocated ID for this exact class."""
        self.declarations[record["id"]] = identity

    def declaration_id(self, record):
        """AST names keep their lexical ID; references use the actual declaration."""
        return self.declarations.get(record["id"], record["id"])

    def bind_alias(self, node, name, identity, *, original_id=None):
        """Only a produced file/namespace alias supplies lexical lookup authority."""
        scope = lexical_scope(node, self.source)
        qualified = "::".join(filter(None, (scope, name))) if scope is not None else ""
        if scope is not None and _name(qualified):
            self.aliases.setdefault(qualified, []).append((node.start_byte, identity))
            self.alias_ids.update((identity, original_id or identity))

    def owns_alias_id(self, identity):
        """A basename collision is not an alternative to lexical alias proof."""
        return identity in self.alias_ids

    def constructor(self, node, name, parent_id):
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
        return constructor_id(record["id"], name, node, self.source, record["qualified"])

    def preferred(self, record):
        group = self.groups[record["qualified"]]
        complete = [item for item in group if item["is_definition"]]
        return (complete or group)[0]

    def ambiguous(self, record):
        return sum(item["is_definition"] for item in self.groups[record["qualified"]]) > 1

    def reference(self, name, node):
        """Resolve exact in-file class scopes without borrowing a basename."""
        # The generic collector intentionally reports a qualified type's leaf.
        # Recover a direct literal spelling from its owning syntax before the
        # lexical lookup; do not guess a nested template argument's qualifier.
        if node.type == "qualified_identifier":
            written = _read_text(node, self.source)
            if _name(written.removeprefix("::")) and written.rsplit("::", 1)[-1] == name:
                name = written
        if not isinstance(name, str) or not _name(name.removeprefix("::")):
            return ""
        scope = lexical_scope(node, self.source)
        if scope is None:
            return ""
        choices = [""] if name.startswith("::") else [
            "::".join(scope.split("::")[:end]) for end in range(len(scope.split("::")), -1, -1)]
        raw = name.removeprefix("::")
        for prefix in choices:
            qualified = "::".join(filter(None, (prefix, raw)))
            visible = [record for record in self.groups.get(qualified, ())
                       if record["syntax"].start_byte <= node.start_byte]
            aliases = {identity for start, identity in self.aliases.get(qualified, ())
                       if start <= node.start_byte}
            if aliases:
                return next(iter(aliases)) if len(aliases) == 1 and not visible else ""
            if visible:
                return self.declaration_id(visible[0])
        return ""
