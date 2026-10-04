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
    return _make_id(qualified_class_id(stem, owner), member)


class CppIdentity:
    """One immutable AST index; forward facts cannot hide a complete body."""

    def __init__(self, root, source, stem):
        self.source, self.stem = source, stem
        self.records, self.groups = {}, {}
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

    def preferred(self, record):
        group = self.groups[record["qualified"]]
        complete = [item for item in group if item["is_definition"]]
        return (complete or group)[0]

    def ambiguous(self, record):
        return sum(item["is_definition"] for item in self.groups[record["qualified"]]) > 1

    def reference(self, name, node):
        """Resolve exact in-file class scopes without borrowing a basename."""
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
            if visible:
                return visible[0]["id"]
        return ""
