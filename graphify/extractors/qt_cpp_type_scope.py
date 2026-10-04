"""Source-local native type authority without preprocessing or compiler emulation.

Lexical bindings own their declaration scope and source order. A shadowing alias
that cannot be proved blocks outer lookup; it never falls back to an unrelated
global class. Accepted class identities remain owned by the canonical producer.
"""
from __future__ import annotations

from dataclasses import dataclass
import re

from graphify.extractors.qt_cpp_facts import qt_metadata
from graphify.extractors.qt_cpp_syntax import walk
from graphify.extractors.qt_cpp_type_aliases import IncludedAliasShadows

_NAME = re.compile(r"(?:::)?[A-Za-z_]\w*(?:::[A-Za-z_]\w*)*")
_CONDITIONAL = {"if_statement", "switch_statement", "for_statement", "while_statement",
                "do_statement", "conditional_expression", "preproc_if", "preproc_ifdef", "preproc_else"}


@dataclass(frozen=True)
class TypeLookup:
    name: str = ""
    reason: str = ""
    source_declared: bool = False


class NativeTypeScope:
    """Immutable per-unit lexical index; external spellings are not class proof."""

    def __init__(self, unit, mapping=None, *, classes=(), alias_nodes=None):
        self.unit, self.mapping = unit, mapping
        self.syntax = tuple(walk(unit.tree))
        self.bindings = {}
        self.classes = {}
        self.included = IncludedAliasShadows(unit, alias_nodes if alias_nodes is not None
                                            else mapping.nodes if mapping is not None else ())
        records = list(classes) + (list(mapping.classes) if mapping is not None else [])
        if mapping is not None:
            records += [{"qualified_name": md.get("class_name"), "node_id": md.get("class_id"),
                         "is_definition": md.get("is_definition")}
                        for node in mapping.nodes if (md := qt_metadata(node)).get("kind") == "class"]
        for record in records:
            name, target = record.get("qualified_name"), record.get("node_id")
            if name and target and record.get("is_definition") is True:
                self.classes.setdefault(name, set()).add(target)
        self.namespaces = {name.rsplit("::", 1)[0] for name in self.classes if "::" in name}
        self.namespaces |= {prefix for name in tuple(self.namespaces)
                            for prefix in self._prefixes(name)}
        # Alias/type bindings are independent of generic graph nodes. Missing
        # canonical identity may reject a target but cannot erase a shadow.
        for node in self.syntax:
            kind, name, target = node.type, "", ""
            if kind == "alias_declaration":
                name, target = unit.field(node, "name"), unit.field(node, "type")
            elif kind == "type_definition":
                # Each declarator introduces a separate shadow, including
                # unsupported pointer/function aliases and comma-separated names.
                owner = mapping.owner_at(node.start_byte) if mapping is not None else None
                scopes = self._scopes(node.parent, owner)
                for declarator in node.children_by_field_name("declarator"):
                    leaf = declarator
                    while leaf and leaf.type not in {"type_identifier", "identifier"}:
                        leaf = leaf.child_by_field_name("declarator") or next(iter(leaf.named_children), None)
                    name = unit.text(leaf) if leaf else ""
                    target = unit.field(node, "type") if leaf == declarator else ""
                    if re.fullmatch(r"[A-Za-z_]\w*", name):
                        self.bindings.setdefault((scopes, name), []).append((node, target, kind, self._conditional(node)))
                continue
            elif kind == "using_declaration":
                literal = unit.text(node).removeprefix("using").strip().removesuffix(";").strip()
                if not literal.startswith("namespace ") and _NAME.fullmatch(literal):
                    name, target = literal.rsplit("::", 1)[-1], literal
            elif kind in {"class_specifier", "struct_specifier"}:
                name = unit.field(node, "name")
                target = self._qualified(self._scopes(node.parent), name)
            elif kind == "namespace_definition":
                name = unit.field(node, "name")
                if name and "::" not in name:
                    target = self._qualified(self._scopes(node.parent), name)
                    self.namespaces.add(target)
            elif kind == "namespace_alias_definition":
                name = unit.field(node, "name")
                target = unit.text(node).split("=", 1)[-1].strip().removesuffix(";").strip()
            if not name or not re.fullmatch(r"[A-Za-z_]\w*", name):
                continue
            owner = mapping.owner_at(node.start_byte) if mapping is not None else None
            scopes = self._scopes(node.parent, owner)
            record = (node, target, kind, self._conditional(node))
            self.bindings.setdefault((scopes, name), []).append(record)

    @staticmethod
    def _prefixes(name):
        parts = name.split("::")
        return ["::".join(parts[:end]) for end in range(1, len(parts) + 1)]

    def _scopes(self, node, owner=None):
        ancestors = []
        while node is not None:
            ancestors.append(node)
            node = node.parent
        scopes, qualified = [], ""
        for ancestor in reversed(ancestors):
            if ancestor.type in {"namespace_definition", "class_specifier", "struct_specifier"}:
                name = self.unit.field(ancestor, "name")
                if name:
                    qualified = "::".join(filter(None, (qualified, name)))
                    scopes.append(("class" if ancestor.type != "namespace_definition" else "namespace", qualified))
            elif ancestor.type == "compound_statement":
                # Out-of-line bodies retain their accepted class scope, while
                # block keys isolate disjoint local aliases with the same name.
                if owner and owner.get("class_name") and not any(key[0] == "class" for key in scopes):
                    scopes.append(("class", owner["class_name"]))
                scopes.append(("block", ancestor.start_byte, ancestor.end_byte))
        return tuple(scopes)

    @staticmethod
    def _qualified(scopes, name):
        prefix = next((scope[1] for scope in reversed(scopes) if scope[0] != "block"), "")
        return "::".join(filter(None, (prefix, name)))

    @staticmethod
    def _conditional(node):
        node = node.parent
        while node is not None:
            if node.type in _CONDITIONAL:
                return True
            node = node.parent
        return False

    def _at(self, byte, owner):
        enclosing = [node for node in self.syntax if node.start_byte <= byte < node.end_byte]
        node = min(enclosing, key=lambda item: item.end_byte - item.start_byte) if enclosing else self.unit.tree
        return self._scopes(node, owner)

    def lookup(self, raw_type, byte, *, owner=None):
        """Resolve a literal type spelling, rejecting uncertainty before fallback."""
        if not isinstance(raw_type, str) or len(raw_type.encode()) > 384 or not _NAME.fullmatch(raw_type):
            return TypeLookup(reason="native_type_expression_unsupported")
        if owner is None and self.mapping is not None:
            owner = self.mapping.owner_at(byte)
        return self._lookup(raw_type, byte, self._at(byte, owner), frozenset())

    def _lookup(self, name, byte, scopes, seen):
        absolute, name = name.startswith("::"), name.removeprefix("::")
        head, separator, tail = name.partition("::")
        choices = [()] if absolute else [scopes[:end] for end in range(len(scopes), -1, -1)]
        for scope in choices:
            if self.included.blocks(scope, head, byte):
                return TypeLookup(reason="native_type_included_alias_unavailable")
            records = [record for record in self.bindings.get((scope, head), ()) if record[0].start_byte <= byte]
            if records:
                direct = {target for _, target, kind, _ in records
                          if kind in {"class_specifier", "struct_specifier", "namespace_definition"}}
                if len(records) != 1 and not (len(direct) == 1 and all(
                        kind in {"class_specifier", "struct_specifier", "namespace_definition"}
                        for _, _, kind, _ in records)):
                    return TypeLookup(reason="native_type_binding_ambiguous")
                node, target, kind, condition = records[0]
                if condition:
                    return TypeLookup(reason="native_type_binding_conditional")
                if kind in {"class_specifier", "struct_specifier", "namespace_definition"}:
                    result = TypeLookup(target, source_declared=True)
                else:
                    identity = (node.start_byte, node.end_byte)
                    if identity in seen or len(seen) >= 32:
                        return TypeLookup(reason="native_type_alias_cycle_or_limit")
                    if not _NAME.fullmatch(target):
                        return TypeLookup(reason="native_type_alias_unsupported")
                    result = self._lookup(target, node.start_byte - 1, scope, seen | {identity})
                return TypeLookup(result.name + separator + tail, result.reason, result.source_declared) if result.name else result
            if scope and scope[-1][0] == "class" and self.bindings.get((scope, head)):
                return TypeLookup(reason="native_type_declaration_not_visible")
            candidate = self._qualified(scope, head)
            # Included source declarations block SDK fallback even without a
            # complete mapped body. Native target lookup still requires the
            # existing accepted complete-class inventory; this adds no provider.
            if self.included.class_declared(scope, head, byte):
                return TypeLookup(candidate + separator + tail, source_declared=True)
            if (not scope or scope[-1][0] != "block") and (candidate in self.classes or candidate in self.namespaces):
                return TypeLookup(candidate + separator + tail, source_declared=True)
        # A later local alias cannot authorize an earlier use. Retaining an
        # unshadowed external spelling preserves SDK input for its own guards.
        if any(self.bindings.get((scope, head)) for scope in choices):
            return TypeLookup(reason="native_type_declaration_not_visible")
        return TypeLookup(name)

    def resolve(self, raw_type, byte, *, owner=None):
        return self.lookup(raw_type, byte, owner=owner).name

    def sdk_type(self, raw_type, byte, expected):
        """Authorize an external SDK type, never a same-spelled source declaration.

        Source-body identity is deliberately unnecessary for rejection: a forward
        declaration or unmapped class still shadows the SDK spelling. Absolute
        lookup bypasses local aliases but retains global source shadowing.
        """
        result = self.lookup(raw_type, byte)
        return result.name == expected and not result.reason and not result.source_declared

    def callable_shadow(self, name, byte, *, absolute=False):
        """Visible source callables cannot inherit SDK type-conversion semantics."""
        if self.mapping is None:
            return False
        scopes = self._at(byte, self.mapping.owner_at(byte))
        names = {name} if absolute else {name} | {
            scope[1] + "::" + name for scope in scopes if scope[0] != "block"}
        return any(record.get("qualified_name") in names for record in self.mapping.functions)

    def resolve_class(self, raw_type, byte, *, owner=None):
        result = self.lookup(raw_type, byte, owner=owner)
        ids = sorted(self.classes.get(result.name, ())) if result.name else []
        return ids, (result.reason or ("" if len(ids) == 1 else "class_mapping_ambiguous_or_unavailable" if ids else "class_not_in_corpus"))
