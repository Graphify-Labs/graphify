"""C# source-local callable identity and lexical data-shadow decisions.

The immutable AST/scope index owns lexical facts. The producer supplies actual
allocated IDs separately; no class/global label fallback can lend a local target
to another source scope. Runtime delegates/lambdas never become concrete callees.
"""
from __future__ import annotations

import base64
from collections import defaultdict
from dataclasses import dataclass, replace
import hashlib
from types import MappingProxyType

from graphify.extractors.base import _make_id, _read_text
from graphify.extractors.csharp_lexical_binders import binding_names, receiver_bindings

_FUNCTIONS = {"method_declaration", "constructor_declaration", "local_function_statement", "accessor_declaration"}
_SCOPES = _FUNCTIONS | {"compilation_unit", "namespace_declaration", "file_scoped_namespace_declaration",
    "class_declaration", "struct_declaration", "record_declaration", "interface_declaration", "block",
    "for_statement", "foreach_statement", "using_statement", "catch_clause", "lambda_expression", "switch_section"}


def _span(node):
    return {"start_byte": node.start_byte, "end_byte": node.end_byte,
            "start_row": node.start_point.row, "end_row": node.end_point.row,
            "start_column": node.start_point.column, "end_column": node.end_point.column}


def _key(name):
    return hashlib.sha256(name.removeprefix("@").encode()).hexdigest()


@dataclass(frozen=True)
class LocalFunction:
    syntax: object
    name: str
    name_key: str
    scope: int
    parent: int | None
    fingerprint: str
    signature: str
    arity: int
    type_arity: int
    minimum: int
    variadic: bool
    conditional: bool
    partial: bool
    duplicate: bool = False


def local_function_ids(nodes, edges=()):
    """Source role evidence excludes locals even if supplementary metadata is damaged."""
    by_id = {node["id"]: node for node in nodes}
    result = {node["id"] for node in nodes if isinstance(node.get("metadata"), dict)
              and "csharp_local_function" in node["metadata"]}
    result.update(edge.get("target") for edge in edges
        if edge.get("relation") == "contains" and edge.get("context") == "csharp_local_function"
        and edge.get("confidence") == "EXTRACTED" and edge.get("target") in by_id
        and edge.get("source") in by_id and edge.get("source_file") == by_id[edge["target"]].get("source_file"))
    return frozenset(result)


class CSharpLexicalCalls:
    """One source index and one producer-bound allocation map, without ambient state."""

    def __init__(self, root, source, stem, *, signature):
        self.source, self.stem = source, stem
        scopes, parents, fingerprints, scope_nodes = {}, {}, {}, {}
        functions, records, children, data = {}, {}, defaultdict(list), defaultdict(set)
        groups, ordinals, nodes, conditions = defaultdict(list), defaultdict(int), [], {}
        file_namespaces = [child.child_by_field_name("name") for child in root.named_children
                           if child.type == "file_scoped_namespace_declaration"]
        file_scope = hashlib.sha256("\0".join(_read_text(node, source) for node in file_namespaces if node is not None).encode()).hexdigest()
        pending = [(root, None, None, False)]
        while pending:
            node, outer_scope, owner, conditional = pending.pop()
            nodes.append(node)
            conditional |= node.type.startswith("preproc_")
            conditions[node.id] = conditional
            scope = outer_scope
            if node.type in _SCOPES:
                name_node = node.child_by_field_name("name")
                name = _read_text(name_node, source) if name_node is not None else ""
                text, meta = signature(node, source) if node.type in _FUNCTIONS else ("", {})
                if node.type in {"class_declaration", "struct_declaration", "record_declaration", "interface_declaration"}:
                    arity = sum(child.type in {"type_parameter", "identifier"} for group in node.named_children
                                if group.type == "type_parameter_list" for child in group.named_children)
                    text = "`" + str(arity)
                token = hashlib.sha256((node.type + "\0" + name + "\0" + text).encode()).hexdigest()
                count_key = (outer_scope, token)
                ordinal = ordinals[count_key]
                ordinals[count_key] += 1
                digest = hashlib.sha256((fingerprints.get(outer_scope, file_scope) + "\0" + token + "\0" + str(ordinal)).encode()).hexdigest()
                scope = node.id
                parents[scope], fingerprints[scope], scope_nodes[scope] = outer_scope, digest, node
            scopes[node.id] = scope
            if node.type == "local_function_statement":
                name_node = node.child_by_field_name("name")
                name = _read_text(name_node, source) if name_node is not None else ""
                text, meta = signature(node, source)
                if name and outer_scope is not None:
                    record = LocalFunction(node, name, _key(name), outer_scope, owner,
                        fingerprints[outer_scope], hashlib.sha256(text.encode()).hexdigest(), meta["arity"],
                        sum(param.type in {"type_parameter", "identifier"} for group in node.named_children
                            if group.type == "type_parameter_list" for param in group.named_children),
                        meta.get("min_arity", meta["arity"]), bool(meta.get("variadic")), conditional,
                        node.has_error or owner is None or functions[owner].has_error)
                    records[node.id] = record
                    children[owner].append(node)
                    groups[(outer_scope, record.name_key)].append(record)
            if node.type in _FUNCTIONS:
                owner = node.id
                functions[owner] = node
            pending.extend((child, scope, owner, conditional) for child in reversed(node.named_children))
        for group in groups.values():
            for record in group:
                records[record.syntax.id] = replace(record, duplicate=len(group) > 1)
        receiver_data = defaultdict(list)
        for node in nodes:
            parent = node
            while parent is not None and parent.type not in _FUNCTIONS:
                parent = parent.parent
            if parent is None:
                continue  # Class fields are owned by their actual source edges.
            function = parent
            scope = scopes[node.id]
            if node.type in {"declaration_pattern", "declaration_expression"}:
                parent = node.parent
                while parent is not None and parent.type not in {"block", "foreach_statement", *_FUNCTIONS}:
                    parent = parent.parent
                scope = scopes[parent.id] if parent is not None else scope
            for name in binding_names(node, source):
                data[scope].add(_key(name))
            receiver_data[function.id].extend(receiver_bindings(
                node, source, function, scope_nodes.get(scope), conditional=conditions[node.id]))
        scoped = defaultdict(list)
        for record in records.values():
            scoped[(record.scope, record.name_key)].append(record)
        self.records, self.scopes, self.parents = map(MappingProxyType, (records, scopes, parents))
        self.scope_nodes = MappingProxyType(scope_nodes)
        self.children_by_owner = MappingProxyType({key: tuple(value) for key, value in children.items()})
        self.scoped = MappingProxyType({key: tuple(value) for key, value in scoped.items()})
        self.data = MappingProxyType({key: frozenset(value) for key, value in data.items()})
        self.receiver_data = MappingProxyType({key: tuple(value) for key, value in receiver_data.items()})
        # This is the sole mutable ID table. The generic declaration allocator,
        # never the immutable AST index, supplies every accepted callable ID.
        self.allocated = {}

    def bind(self, node, identity, class_identity):
        self.allocated[node.id] = (identity, class_identity)

    def children(self, node):
        return self.children_by_owner.get(node.id, ())

    def parent_class(self, node):
        record = self.records.get(node.id)
        return self.allocated.get(record.parent, (None, None))[1] if record else None

    def describe(self, node, file_id):
        record = self.records[node.id]
        digest = hashlib.sha256((record.fingerprint + "\0" + record.name + "\0" + record.signature).encode()).hexdigest()
        identity = _make_id(self.stem, "local", record.name[:32]) + "::local-function::" + digest
        if record.duplicate:
            identity += "::declaration::" + hashlib.sha256(f"{node.start_byte}:{node.end_byte}".encode()).hexdigest()
        raw = record.name.encode()
        metadata = {"contract_version": 1, "role": "definition" if node.child_by_field_name("body") else "declaration",
            "raw_name_b64": base64.b64encode(raw).decode() if len(raw) <= 384 else "",
            "name_status": "available" if len(raw) <= 384 else "oversize", "signature": record.signature,
            "scope_fingerprint": record.fingerprint, "type_arity": record.type_arity,
            "span": _span(node), "scope_span": _span(self.scope_nodes[record.scope]),
            "conditional": record.conditional, "ambiguous": record.duplicate, "partial": record.partial}
        parent = self.allocated.get(record.parent, (file_id, None))[0]
        return identity, parent, {"csharp_local_function": metadata, "arity": record.arity,
                                 "min_arity": record.minimum, "variadic": record.variadic}

    def local_ids(self):
        return frozenset(self.allocated[key][0] for key in self.records if key in self.allocated)

    def class_owners(self):
        return {value[0]: value[1] for key, value in self.allocated.items() if key in self.records and value[1]}

    def capture_receiver_tables(self, method_scopes, tables):
        """Reuse one collector's proven types inside supported lexical captures.

        Own-body bindings remain narrower than the added local-function window.
        Missing/conditional/late/duplicate declarations and static barriers add
        None shadows, so a field or unrelated method cannot lend authority.
        Source tuples and per-file indexes are never mutated or shared globally.
        """
        typed = {}
        for key, (node, _) in method_scopes.items():
            names = defaultdict(list)
            for name, values in tables[key][0].items():
                names[name.removeprefix("@")].extend(values)
            typed[node.id] = names
        result = dict(tables)

        def is_static(node):
            return any(child.type == "modifier" and _read_text(child, self.source) == "static"
                       for child in node.children)

        for key, (node, _) in method_scopes.items():
            record = self.records.get(node.id)
            if record is None:
                continue
            ancestors, parent = [], record.parent
            while parent is not None:
                ancestors.append(parent)
                parent = self.records[parent].parent if parent in self.records else None
            allowed = []
            if not is_static(node):
                for parent in ancestors:
                    allowed.append(parent)
                    if is_static(self.scope_nodes[parent]):
                        break
            inherited = typed.get(allowed[-1], {}) if allowed else {}
            barrier, scope = None, self.scopes[node.id]
            while scope is not None:
                frame = self.scope_nodes[scope]
                if frame.type in {"local_function_statement", "lambda_expression"} and is_static(frame):
                    barrier = frame.start_byte, frame.end_byte
                    break
                scope = self.parents[scope]
            own, base = tables[key]
            bindings = defaultdict(list)
            for name, values in own.items():
                bindings[name.removeprefix("@")].extend(values)
            claims = defaultdict(list)
            for parent in ancestors:
                for binding in self.receiver_data.get(parent, ()):
                    if binding.scope[0] <= node.start_byte and node.end_byte <= binding.scope[1]:
                        claims[binding.name].append(binding)
            for name, candidates in claims.items():
                width = min(binding.scope[1] - binding.scope[0] for binding in candidates)
                nearest = [binding for binding in candidates if binding.scope[1] - binding.scope[0] == width]
                binding = nearest[0]
                accepted = (len(nearest) == 1 and binding.supported and not binding.conditional
                            and binding.declared <= node.start_byte and binding.owner in allowed
                            and (barrier is None or barrier[0] <= binding.scope[0] and binding.scope[1] <= barrier[1])
                            and not record.conditional and not record.partial)
                for suffix in ("", "[]"):
                    matches = [value for start, end, value in inherited.get(name + suffix, ())
                               if (start, end) in binding.type_windows]
                    value = matches[0] if accepted and len(matches) == 1 and isinstance(matches[0], str) else None
                    bindings[name + suffix].append((node.start_byte, node.end_byte, value))
            # Escaped/unescaped C# spellings denote the same source binder;
            # combining their rows preserves actual duplicate-declaration ties.
            aliases = {alias: list(values) for name, values in bindings.items() for alias in (name, "@" + name)}
            result[key] = aliases, dict(base)
        return result

    def lookup(self, call, name):
        """None means no lexical binding; `(None,)` forbids every global fallback."""
        scope, key = self.scopes.get(call.id), _key(name)
        while scope is not None:
            if key in self.data.get(scope, ()):
                return (None,)
            candidates = self.scoped.get((scope, key), ())
            if candidates:
                if len(candidates) != 1:
                    return (None,)
                record = candidates[0]
                arguments = call.child_by_field_name("arguments")
                count = sum(child.type == "argument" for child in arguments.children) if arguments is not None else 0
                # Source-explicit generic arguments must fit the declaration;
                # absence remains eligible for ordinary C# type inference.
                function = call.child_by_field_name("function")
                types = next((child for child in function.named_children
                              if child.type == "type_argument_list"), None) if function is not None else None
                actual = self.allocated.get(record.syntax.id)
                if (record.conditional or record.partial or record.duplicate or actual is None
                        or record.syntax.child_by_field_name("body") is None or len(record.name.encode()) > 384
                        or types is not None and len(types.named_children) != record.type_arity
                        or count < record.minimum or not record.variadic and count > record.arity):
                    return (None,)
                return (actual[0],)
            scope = self.parents[scope]
        return None
