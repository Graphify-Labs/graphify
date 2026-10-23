"""Structural extraction for Visual Basic .NET source files."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from tree_sitter import Node

from graphify.extractors.base import _file_stem, _make_id, _read_source_bytes, _read_text


_TYPE_BLOCKS = {
    "class_block": "class",
    "module_block": "module",
    "interface_block": "interface",
    "structure_block": "structure",
    "enum_block": "enum",
}


_NAME = r"[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*"
_NAME_RE = re.compile(rf"^{_NAME}$")
_IDENT_RE = re.compile(r"^[A-Za-z_]\w*$")
_AS_NEW_RE = re.compile(rf"As\s+New\s+(?:Global\.)?({_NAME})\s*(.*)$", re.I | re.S)
_AS_TYPE_RE = re.compile(rf"As\s+(?:Global\.)?({_NAME})\s*(.*)$", re.I | re.S)
_NEW_RE = re.compile(rf"New\s+(?:Global\.)?({_NAME})\s*(.*)$", re.I | re.S)
_GENERIC_RE = re.compile(r"\(\s*Of\b", re.I)
_VB_TYPE_KINDS = {"class", "module", "structure"}
# a typed variable may be an interface; a name used as a qualifier (`Name.Call()`) may not
_VB_TYPED_KINDS = _VB_TYPE_KINDS | {"interface"}
_INFERRED_SCORE = 0.85


def _declared_type(as_clause: str | None, initializer: str | None) -> str | None:
    """The type a local, parameter or loop variable is declared with, as written.

    ``As New T()``, ``As T`` and (with no ``As`` clause) ``= New T()`` name a type;
    generics, arrays and anything else give None, so no call through it is guessed.
    """
    if as_clause:
        match = _AS_NEW_RE.match(as_clause.strip())
        if match:
            return None if _GENERIC_RE.match(match.group(2)) else match.group(1)
        match = _AS_TYPE_RE.match(as_clause.strip())
        return match.group(1) if match and not match.group(2).strip() else None
    if initializer:
        match = _NEW_RE.match(initializer.strip())
        if match and not _GENERIC_RE.match(match.group(2)):
            return match.group(1)
    return None


def _enclosing_namespaces(namespace: str) -> list[str]:
    parts = namespace.split(".") if namespace else []
    return [".".join(parts[:i]) for i in range(len(parts), 0, -1)]


def _is_cs_file(source_file: object) -> bool:
    return isinstance(source_file, str) and source_file.lower().endswith(".cs")


class _VbCallIndex:
    """Corpus-wide lookup tables for VB call resolution, built once per run.

    Types are keyed by ``owner`` (the namespace-qualified name, casefolded), so the
    parts of a partial type share one entry. Members come from node metadata
    (``owner``, ``name``, ``accepted_arities``) and C# targets from their ``method``
    edges, which is all an unchanged file contributes on an incremental build.
    """

    def __init__(self, all_nodes: list[dict], all_edges: list[dict]) -> None:
        self.node_by_id: dict[str, dict] = {}
        self.owner_of: dict[str, str] = {}
        self.kind: dict[str, str] = {}
        self.namespace: dict[str, str] = {}
        self.members: dict[tuple[str, str], list[tuple[str, list[int]]]] = {}
        self.module_owners: dict[str, set[str]] = {}
        self.data_node_names: dict[str, str] = {}
        self.data_node_types: dict[str, tuple[str | None, str, list[str]]] = {}
        # owner -> field/property/event name -> (declared type as written, the
        # declaring file's namespace and imports); a name declared twice has no type
        self.data_members: dict[str, dict[str, tuple[str | None, str, list[str]]]] = {}
        self.bases: dict[str, set[tuple]] = {}
        self.cs_type_ns: dict[str, str] = {}
        self.cs_full: dict[str, list[str]] = {}
        self.cs_methods: dict[str, list[tuple[str, str, str]]] = {}
        self._chain_external: dict[str, bool] = {}

        cs_candidates: dict[str, dict] = {}
        for node in all_nodes:
            nid = node.get("id")
            if not isinstance(nid, str):
                continue
            self.node_by_id[nid] = node
            metadata = node.get("metadata")
            metadata = metadata if isinstance(metadata, dict) else {}
            if metadata.get("language") == "vbnet":
                kind = metadata.get("kind")
                if kind in _VB_TYPE_KINDS or kind == "interface":
                    owner = str(metadata.get("full_name") or node.get("label") or "").casefold()
                    if owner:
                        self.owner_of[nid] = owner
                        self.kind[owner] = kind
                        self.namespace[owner] = owner.rpartition(".")[0]
                elif kind in {"method", "constructor"}:
                    owner, name = metadata.get("owner"), metadata.get("name")
                    accepted = metadata.get("accepted_arities")
                    if not isinstance(accepted, list):
                        accepted = [metadata["arity"]] if isinstance(metadata.get("arity"), int) else []
                    if isinstance(owner, str) and isinstance(name, str):
                        self.members.setdefault((owner.casefold(), name.casefold()), []).append(
                            (nid, [a for a in accepted if isinstance(a, int)])
                        )
                        if kind == "method":
                            self.module_owners.setdefault(name.casefold(), set()).add(owner.casefold())
                elif kind in {"field", "property", "event"}:
                    self.data_node_names[nid] = str(node.get("label") or "").casefold()
                    declared = metadata.get("declared_type")
                    imports = metadata.get("imports")
                    self.data_node_types[nid] = (
                        declared if isinstance(declared, str) else None,
                        str(metadata.get("namespace") or "").casefold(),
                        [str(i).casefold() for i in imports] if isinstance(imports, list) else [],
                    )
            elif (
                _is_cs_file(node.get("source_file"))
                and node.get("file_type") == "code"
                and node.get("type") != "namespace"
            ):
                label = str(node.get("label") or "")
                if _IDENT_RE.match(label) and label != Path(str(node["source_file"])).name:
                    cs_candidates[nid] = node

        # a Module's members are only reachable unqualified when the owner really is a Module
        self.module_owners = {
            name: {o for o in owners if self.kind.get(o) == "module"}
            for name, owners in self.module_owners.items()
        }

        cs_top_level: set[str] = set()
        for edge in all_edges:
            relation, source, target = edge.get("relation"), edge.get("source"), edge.get("target")
            if relation == "contains" and target in cs_candidates:
                holder = self.node_by_id.get(source) or {}
                holder_file = holder.get("source_file")
                # a C# type is declared in a file or a namespace; a property or a
                # nested member is contained by a type
                if holder.get("type") == "namespace" or (
                    holder_file and holder.get("label") == Path(str(holder_file)).name
                ):
                    cs_top_level.add(target)
            if relation == "method" and source in cs_candidates:
                method_node = self.node_by_id.get(target)
                label = str((method_node or {}).get("label") or "").lstrip(".")
                name = re.match(r"\w+", label)
                if name:
                    self.cs_methods.setdefault(source, []).append(
                        (target, name.group().casefold(), name.group())
                    )
            elif relation == "contains" and source in self.owner_of and target in self.data_node_names:
                declared_members = self.data_members.setdefault(self.owner_of[source], {})
                name = self.data_node_names[target]
                declared_members[name] = (
                    (None, "", []) if name in declared_members else self.data_node_types[target]
                )
            elif relation == "inherits" and source in self.owner_of:
                base = self.node_by_id.get(target)
                owner = self.owner_of[source]
                if base is None or not base.get("source_file"):
                    self.bases.setdefault(owner, set()).add(("ext",))
                elif target in self.owner_of:
                    self.bases.setdefault(owner, set()).add(("vb", self.owner_of[target]))
                else:
                    self.bases.setdefault(owner, set()).add(("cs", target))

        for nid, node in cs_candidates.items():
            if nid not in cs_top_level:
                continue
            metadata = node.get("metadata") if isinstance(node.get("metadata"), dict) else {}
            namespace = str(metadata.get("namespace") or "").casefold()
            self.cs_type_ns[nid] = namespace
            full = f"{namespace}.{str(node['label']).casefold()}" if namespace else str(node["label"]).casefold()
            self.cs_full.setdefault(full, []).append(nid)

    # -- scoping -------------------------------------------------------------

    @staticmethod
    def _in_scope(namespace: str, caller_namespace: str, imports: list[str]) -> bool:
        return (
            not namespace
            or namespace == caller_namespace
            or caller_namespace.startswith(namespace + ".")
            or namespace in imports
        )

    def find_types(
        self, written: str, caller_namespace: str, imports: list[str], typed: bool = False
    ) -> list[tuple]:
        """The types a written name can mean from this namespace, deduplicated.

        ``typed`` is for the type of a variable, which may be an interface; a
        qualifier (``Name.Call()``) only names a class, a Module or a structure.
        """
        kinds = _VB_TYPED_KINDS if typed else _VB_TYPE_KINDS
        name = written.casefold()
        if name.startswith("global."):
            prefixes, name = [""], name[len("global."):]
        else:
            prefixes = [""] + _enclosing_namespaces(caller_namespace) + imports
        found: list[tuple] = []
        for prefix in prefixes:
            full = f"{prefix}.{name}" if prefix else name
            if self.kind.get(full) in kinds and ("vb", full) not in found:
                found.append(("vb", full))
            for nid in self.cs_full.get(full, ()):
                if ("cs", nid) not in found:
                    found.append(("cs", nid))
        return found

    def chain_external(self, owner: str) -> bool:
        """True when the type's base chain ends in a base that is not in the corpus."""
        if owner not in self._chain_external:
            seen, stack, external = set(), [owner], False
            while stack:
                current = stack.pop()
                if current in seen:
                    continue
                seen.add(current)
                for base in self.bases.get(current, ()):
                    if base[0] == "ext":
                        external = True
                    elif base[0] == "vb":
                        stack.append(base[1])
            self._chain_external[owner] = external
        return self._chain_external[owner]

    def find_field(self, owner: str, name: str) -> tuple[str | None, str, list[str]] | None:
        """(declared type, namespace, imports) of the field, property or event ``name``.

        The type itself is searched first, then its VB bases nearest first, so a
        ``Shadows`` field in a derived type wins. None when no such member exists;
        a member with no declared type comes back with a None type.
        """
        level, seen = [owner], set()
        while level:
            following: list[str] = []
            for current in level:
                if current in seen:
                    continue
                seen.add(current)
                found = self.data_members.get(current, {}).get(name)
                if found is not None:
                    return found
                following += [b[1] for b in sorted(self.bases.get(current, ())) if b[0] == "vb"]
            level = following
        return None

    def hidden_by_member(self, owner: str, name: str) -> bool:
        """True when the type or a base declares a field, property or event called ``name``."""
        return self.find_field(owner, name) is not None

    # -- member lookup ---------------------------------------------------------

    def _named(self, ref: tuple, name: str) -> list[tuple[str, list[int] | None]]:
        if ref[0] == "vb":
            return list(self.members.get((ref[1], name), ()))
        return [(nid, None) for nid, folded, _exact in self.cs_methods.get(ref[1], ()) if folded == name]

    def lookup_member(self, start: tuple, name: str, arity: int) -> tuple[str | None, bool, int]:
        """(target, found, depth): the method ``name`` on the type or its nearest base.

        The nearest type that declares the name decides, at any arity (VB hides a
        base's or a Module's member by name). A VB target must accept the arity; a
        C# target has no arity here, so it needs to be the only method of that name.
        """
        level, seen, depth = [start], set(), 0
        while level:
            named, following = [], []
            for ref in level:
                if ref in seen:
                    continue
                seen.add(ref)
                named += self._named(ref, name)
                if ref[0] == "vb":
                    following += [b for b in self.bases.get(ref[1], ()) if b[0] != "ext"]
            if named:
                if any(accepted is None for _nid, accepted in named):
                    matches = [named[0][0]] if len(named) == 1 else []
                else:
                    matches = [nid for nid, accepted in named if arity in accepted]
                return (matches[0] if len(matches) == 1 else None), True, depth
            level, depth = following, depth + 1
        return None, False, depth

    # -- one call ----------------------------------------------------------------

    def resolve(self, call: dict) -> tuple[str, str, float, str] | None:
        """(target, confidence, score, context) for a raw call, or None."""
        name = str(call.get("callee", "")).casefold()
        arity = int(call.get("arity", -1))
        owner = str(call.get("caller_owner") or "").casefold()
        namespace = str(call.get("namespace") or "").casefold()
        imports = [str(i).casefold() for i in call.get("imports") or []]
        kind = call.get("receiver_kind")
        external = self.chain_external(owner)
        if kind in ("none", "me"):
            target, found, depth = self.lookup_member(("vb", owner), name, arity)
            if found:
                if target is None:
                    return None
                return target, "EXTRACTED", 1.0, "partial_type_call" if depth == 0 else "call"
            if kind == "me":
                return None
            # a field, property or event of that name is what `Name(...)` means (a
            # delegate field is invoked); it hides the Module's Sub like a method does
            if self.hidden_by_member(owner, name):
                return None
            modules = [
                m for m in self.module_owners.get(name, ())
                if self._in_scope(self.namespace.get(m, ""), namespace, imports)
            ]
            if len(modules) != 1:
                return None
            target, found, _depth = self.lookup_member(("vb", modules[0]), name, arity)
            return self._edge(target, external, "call")
        if kind == "mybase":
            bases = [b for b in self.bases.get(owner, ()) if b[0] != "ext"]
            if len(bases) != 1:
                return None
            target, found, _depth = self.lookup_member(bases[0], name, arity)
            return None if target is None else (target, "EXTRACTED", 1.0, "call")
        if kind in ("local", "typed"):
            declared = call.get("receiver_type")
            types = self.find_types(declared, namespace, imports, typed=True) if declared else []
            if len(types) != 1:
                return None
            target, found, _depth = self.lookup_member(types[0], name, arity)
            return None if target is None else (target, "INFERRED", _INFERRED_SCORE, "call")
        if kind in ("name", "field"):
            receiver = str(call.get("receiver") or "")
            first = receiver.split(".")[0].casefold()
            if kind == "name" and first in {str(n).casefold() for n in call.get("nested_types") or []}:
                return None
            member = self.find_field(owner, first)
            if member is not None:
                # a field, property or event of that name is the receiver: it hides a
                # type or Module of the same name, and only its declared type (read in
                # the declaring file's scope) says whose method is called
                declared, declared_namespace, declared_imports = member
                if "." in receiver or not declared:
                    return None
                types = self.find_types(declared, declared_namespace, declared_imports, typed=True)
                if len(types) != 1:
                    return None
                target, found, _depth = self.lookup_member(types[0], name, arity)
                return None if target is None else (target, "INFERRED", _INFERRED_SCORE, "call")
            if kind == "field":
                return None
            types = self.find_types(receiver, namespace, imports)
            if len(types) != 1:
                return None
            target, found, _depth = self.lookup_member(types[0], name, arity)
            if target is None:
                return None
            exact = types[0][0] == "vb" or any(
                nid == target and exact_name == call.get("callee")
                for nid, _f, exact_name in self.cs_methods.get(types[0][1], ())
            )
            if not exact:
                return target, "INFERRED", _INFERRED_SCORE, "call"
            return self._edge(target, external, "call")
        return None

    @staticmethod
    def _edge(target: str | None, external: bool, context: str) -> tuple[str, str, float, str] | None:
        if target is None:
            return None
        if external:
            # the caller's base chain leaves the corpus (a Form, a Page...): that base
            # may declare the name, which would hide this binding
            return target, "INFERRED", _INFERRED_SCORE, "external_base_may_hide"
        return target, "EXTRACTED", 1.0, context


def resolve_vbnet_calls(
    per_file: list[dict], all_nodes: list[dict], all_edges: list[dict]
) -> None:
    """Resolve VB calls whose callee is declared in another file.

    Covers a partial type's other parts, a base class, a Module member called
    unqualified or by name, a typed local's methods, and a C# type's methods. The
    shared name pass never sees these calls: it matches bare names, and VB scoping
    (the caller's own type and bases hide a Module's member, two in-scope Modules
    are ambiguous, a Module is only in scope through its namespace) is not a name
    match. Only a unique target makes an edge.
    """
    index = _VbCallIndex(all_nodes, all_edges)
    existing = {
        (edge.get("source"), edge.get("target"))
        for edge in all_edges
        if edge.get("relation") == "calls"
    }
    for result in per_file:
        for call in result.get("raw_calls", []):
            if call.get("language") != "vbnet" or not call.get("receiver_kind"):
                continue
            resolved = index.resolve(call)
            caller = call.get("caller_nid")
            if resolved is None or resolved[0] == caller or (caller, resolved[0]) in existing:
                continue
            target, confidence, score, context = resolved
            existing.add((caller, target))
            all_edges.append({
                "source": caller,
                "target": target,
                "relation": "calls",
                "context": context,
                "confidence": confidence,
                "confidence_score": score,
                "source_file": call.get("source_file", ""),
                "source_location": call.get("source_location"),
                "weight": 1.0,
                # a unique binding, not a name match: build.py's cross-language
                # phantom filter keeps it although .vb and .cs are separate families
                "_vbnet_resolved": True,
            })


# The name the resolver registry and older imports know it by.
resolve_vbnet_partial_calls = resolve_vbnet_calls


def extract_vbnet(path: Path) -> dict:
    try:
        import tree_sitter_vb_dotnet
        from tree_sitter import Language, Parser
    except ImportError:
        return {"nodes": [], "edges": [], "error": "tree-sitter-vb-dotnet not installed"}

    try:
        source = _read_source_bytes(path)
        root = Parser(Language(tree_sitter_vb_dotnet.language())).parse(source).root_node
    except Exception as exc:
        return {"nodes": [], "edges": [], "error": f"VB.NET grammar failed to load: {exc}"}

    source_file = str(path)
    stem = _file_stem(path)
    file_id = _make_id(source_file)
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    raw_calls: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    seen_edges: set[tuple[str, str, str]] = set()
    types_by_name: dict[str, str] = {}
    # Short type/module name -> its owner_key, so a qualified call such as
    # Helpers.Log() can be resolved back to the owner that keys `methods`
    # (which is the namespace-qualified name, not the bare receiver token).
    owner_by_short: dict[str, str] = {}
    methods: dict[tuple[str, str, int], list[str]] = {}
    # owner_key -> casefolded names of the fields, properties and events this file declares
    data_names: dict[str, set[str]] = {}
    events: dict[tuple[str, str], str] = {}
    bodies: list[tuple[Node, str, str, str, str, list[str]]] = []
    pending_handles: list[tuple[str, str, str, Node]] = []

    def add_node(
        nid: str,
        label: str,
        node: Node,
        *,
        kind: str,
        source_backed: bool = True,
        callable_node: bool = False,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        if nid not in seen_ids:
            seen_ids.add(nid)
            details: dict[str, Any] = {"language": "vbnet", "kind": kind}
            if metadata:
                details.update(metadata)
            item: dict[str, Any] = {
                "id": nid,
                "label": label,
                "file_type": "code",
                "source_location": f"L{node.start_point[0] + 1}",
                "metadata": details,
            }
            if source_backed:
                item["source_file"] = source_file
            if callable_node:
                item["_callable"] = True
            nodes.append(item)
        return nid

    def add_edge(source_id: str, target_id: str, relation: str, node: Node) -> None:
        key = (source_id, target_id, relation)
        if not source_id or not target_id or source_id == target_id or key in seen_edges:
            return
        seen_edges.add(key)
        edges.append({
            "source": source_id,
            "target": target_id,
            "relation": relation,
            "confidence": "EXTRACTED",
            "source_file": source_file,
            "source_location": f"L{node.start_point[0] + 1}",
            "weight": 1.0,
        })

    add_node(file_id, path.name, root, kind="file")

    # Namespaces this file imports, for the cross-file resolver. An alias import
    # (`Imports G = System.Collections.Generic`) brings no namespace into scope.
    file_imports: list[str] = []
    for statement in (node for node in root.named_children if node.type == "imports_statement"):
        namespace_node = next(
            (child for child in statement.named_children if child.type == "namespace_name"),
            None,
        )
        if namespace_node is None:
            continue
        namespace = _read_text(namespace_node, source)
        if statement.child_by_field_name("alias") is None and namespace not in file_imports:
            file_imports.append(namespace)
        target = add_node(
            _make_id("vbnet", "namespace", namespace.casefold()),
            namespace,
            namespace_node,
            kind="external_namespace",
            source_backed=False,
        )
        add_edge(file_id, target, "imports", statement)

    def type_reference(name: str, node: Node) -> str:
        short_name = name.split(".")[-1]
        target = types_by_name.get(short_name.casefold())
        if target is not None:
            return target
        return add_node(
            _make_id("vbnet", "type", name.casefold()),
            short_name,
            node,
            kind="external_type",
            source_backed=False,
        )

    def add_data_member(
        type_id: str,
        member: Node,
        name: str,
        kind: str,
        relation: str = "contains",
        metadata: dict[str, Any] | None = None,
    ) -> str:
        member_id = add_node(
            _make_id(type_id, kind, name.casefold(), str(member.start_point[0])),
            name,
            member,
            kind=kind,
            metadata=metadata,
        )
        add_edge(type_id, member_id, relation, member)
        return member_id

    def data_metadata(as_clause: Node | None, owner_key: str, namespace: str) -> dict[str, Any]:
        """Owner and declared type of a field or property, for the cross-file resolver.

        Only ``As T`` and ``As New T()`` give a type: Option Infer does not apply to
        fields, so ``= New T()`` alone leaves the member untyped. The declaring
        file's namespace and imports travel with the type, since they decide which
        ``T`` it names.
        """
        details: dict[str, Any] = {"owner": owner_key}
        declared = _declared_type(_read_text(as_clause, source), None) if as_clause is not None else None
        if declared:
            details.update(declared_type=declared, namespace=namespace, imports=list(file_imports))
        return details

    def process_type(block: Node, parent_id: str, namespace: str) -> None:
        kind = _TYPE_BLOCKS[block.type]
        name_node = block.child_by_field_name("name")
        if name_node is None:
            return
        name = _read_text(name_node, source)
        full_name = f"{namespace}.{name}" if namespace else name
        owner_key = full_name.casefold()
        type_id = add_node(
            _make_id(stem, "type", owner_key),
            name,
            block,
            kind=kind,
            callable_node=kind in {"class", "structure"},
            metadata={"name": name, "full_name": full_name},
        )
        add_edge(parent_id, type_id, "contains", block)
        types_by_name[name.casefold()] = type_id
        owner_by_short.setdefault(name.casefold(), owner_key)

        for clause in block.named_children:
            if clause.type not in {"inherits_clause", "implements_clause"}:
                continue
            relation = "inherits" if clause.type == "inherits_clause" else "implements"
            for type_node in (child for child in clause.named_children if child.type == "type"):
                referenced = _read_text(type_node, source)
                add_edge(type_id, type_reference(referenced, type_node), relation, clause)

        field_names = data_names.setdefault(owner_key, set())
        nested_types: list[str] = []
        for child in block.named_children:
            inner = child.named_children[0] if child.type == "type_declaration" and child.named_children else child
            if inner.type in _TYPE_BLOCKS:
                inner_name = inner.child_by_field_name("name")
                if inner_name is not None:
                    nested_types.append(_read_text(inner_name, source).casefold())

        for member in block.named_children:
            if member.type == "enum_member":
                member_name = member.child_by_field_name("name")
                if member_name is not None:
                    # An enum member is a discriminant case, not a contained
                    # declaration: it gets a `case_of` edge like every other
                    # language with enums (Java #1719, C#, Swift, Scala, ...),
                    # not the `contains` edge used for real fields. The relation
                    # also matters to resolution — case_of targets are excluded
                    # from `New X()` constructor binding (see _member_nids).
                    add_data_member(
                        type_id, member, _read_text(member_name, source),
                        "enum_member", relation="case_of",
                    )
                continue
            if member.type == "field_declaration":
                for declarator in (
                    child for child in member.named_children
                    if child.type == "variable_declarator"
                ):
                    member_name = declarator.child_by_field_name("name")
                    if member_name is not None:
                        field_names.add(_read_text(member_name, source).casefold())
                        add_data_member(
                            type_id,
                            declarator,
                            _read_text(member_name, source),
                            "field",
                            metadata=data_metadata(
                                next((c for c in declarator.named_children if c.type == "as_clause"), None),
                                owner_key,
                                namespace,
                            ),
                        )
                continue
            if member.type in {"property_declaration", "event_declaration"}:
                member_name = member.child_by_field_name("name")
                if member_name is not None:
                    data_name = _read_text(member_name, source)
                    field_names.add(data_name.casefold())
                    is_property = member.type == "property_declaration"
                    member_id = add_data_member(
                        type_id,
                        member,
                        data_name,
                        "property" if is_property else "event",
                        metadata=data_metadata(
                            next((c for c in member.named_children if c.type == "as_clause"), None)
                            if is_property else None,
                            owner_key,
                            namespace,
                        ),
                    )
                    if member.type == "event_declaration":
                        events[(owner_key, data_name.casefold())] = member_id
                continue
            if member.type not in {"method_declaration", "constructor_declaration"}:
                continue

            if member.type == "constructor_declaration":
                method_name = "New"
                method_kind = "constructor"
            else:
                method_name_node = member.child_by_field_name("name")
                if method_name_node is None:
                    continue
                method_name = _read_text(method_name_node, source)
                method_kind = "method"
            parameters = member.child_by_field_name("parameters")
            parameter_nodes = (
                [child for child in parameters.named_children if child.type == "parameter"]
                if parameters is not None
                else []
            )
            arity = len(parameter_nodes)
            required_arity = sum(
                not _read_text(parameter, source).lstrip().casefold().startswith("optional ")
                for parameter in parameter_nodes
            )
            accepted_arities = list(range(required_arity, arity + 1))
            method_id = add_node(
                _make_id(
                    type_id,
                    method_kind,
                    method_name.casefold(),
                    str(arity),
                    str(member.start_point[0]),
                ),
                f"{method_name}()",
                member,
                kind=method_kind,
                callable_node=True,
                metadata={
                    "owner": owner_key,
                    "name": method_name,
                    "arity": arity,
                    "accepted_arities": accepted_arities,
                },
            )
            add_edge(type_id, method_id, "method", member)
            for accepted_arity in accepted_arities:
                methods.setdefault(
                    (owner_key, method_name.casefold(), accepted_arity), []
                ).append(method_id)
            for clause in (
                child for child in member.named_children if child.type == "handles_clause"
            ):
                for handled in (
                    child for child in clause.named_children if child.type == "namespace_name"
                ):
                    pending_handles.append((
                        method_id,
                        owner_key,
                        _read_text(handled, source),
                        handled,
                    ))
            bodies.append((member, method_id, owner_key, name, namespace, nested_types))

    def scan(node: Node, parent_id: str, namespace: str) -> None:
        if node.type == "imports_statement":
            return
        if node.type == "namespace_block":
            name_node = node.child_by_field_name("name")
            if name_node is None:
                return
            local_name = _read_text(name_node, source)
            full_namespace = f"{namespace}.{local_name}" if namespace else local_name
            namespace_id = add_node(
                _make_id(stem, "namespace", full_namespace.casefold()),
                local_name,
                node,
                kind="namespace",
                metadata={"full_name": full_namespace},
            )
            add_edge(parent_id, namespace_id, "contains", node)
            for child in node.named_children:
                if child != name_node:
                    scan(child, namespace_id, full_namespace)
            return
        if node.type in _TYPE_BLOCKS:
            process_type(node, parent_id, namespace)
            # Nested type declarations are the only child containers that still
            # need recursion after processing this type's own members.
            for child in node.named_children:
                if child.type == "type_declaration":
                    scan(child, parent_id, namespace)
            return
        for child in node.named_children:
            scan(child, parent_id, namespace)

    scan(root, file_id, "")

    for method_id, owner_key, written, handled_node in pending_handles:
        event_name = written.split(".")[-1]
        target = events.get((owner_key, event_name.casefold()))
        if target is None:
            target = add_node(
                _make_id("vbnet", "event", written.casefold()),
                written,
                handled_node,
                kind="external_event",
                source_backed=False,
            )
        add_edge(method_id, target, "handles", handled_node)

    def method_locals(body: Node) -> dict[str, str | None]:
        """Names declared in a method (parameters, locals, loop and catch variables).

        Each maps to its declared type as written, or None when it has none or is
        declared twice (a rebinding poisons the name, as in the C# table).
        """
        table: dict[str, str | None] = {}

        def declare(identifier: Node, as_clause: Node | None, initializer: Node | None) -> None:
            key = _read_text(identifier, source).casefold()
            declared = _declared_type(
                _read_text(as_clause, source) if as_clause is not None else None,
                _read_text(initializer, source) if initializer is not None else None,
            )
            table[key] = None if key in table else declared

        def first(node: Node, kind: str) -> Node | None:
            return next((child for child in node.named_children if child.type == kind), None)

        parameters = body.child_by_field_name("parameters")
        for parameter in (parameters.named_children if parameters is not None else []):
            name_node = first(parameter, "identifier")
            if parameter.type == "parameter" and name_node is not None:
                declare(name_node, first(parameter, "as_clause"), None)
        pending = [body]
        while pending:
            node = pending.pop()
            if node != body and node.type in {
                "method_declaration", "constructor_declaration", "property_declaration"
            }:
                continue
            if node.type == "dim_statement":
                initializer = first(node, "expression")
                for identifier in (c for c in node.named_children if c.type == "identifier"):
                    declare(identifier, first(node, "as_clause"), initializer)
            elif node.type in {"for_each_statement", "for_statement", "using_statement"}:
                identifier = first(node, "identifier")
                if identifier is not None:
                    declare(identifier, first(node, "as_clause"), None)
            elif node.type == "catch_block":
                identifier = first(node, "identifier")
                if identifier is not None:
                    declare(identifier, None, None)
            pending.extend(node.named_children)
        return table

    def with_target(statement: Node) -> tuple[str, str] | None:
        """What a ``With`` statement's ``.Member`` calls are made on.

        ``("text", name)`` for a name or ``Me.name`` (resolved like the call
        ``name.Member()``), ``("new", T)`` for ``New T(...)``, None for anything
        else (a call result, a chain): its type is not known.
        """
        expression = statement.child_by_field_name("target")
        if expression is None:
            return None
        written = _read_text(expression, source).strip()
        if _NAME_RE.match(written):
            return ("text", written)
        creation = expression.named_children[0] if expression.named_children else None
        if creation is not None and creation.type == "new_expression":
            type_node = creation.child_by_field_name("type")
            if type_node is not None and _NAME_RE.match(_read_text(type_node, source)):
                return ("new", _read_text(type_node, source))
        return None

    for body, caller_id, owner_key, type_name, namespace, nested_types in bodies:
        locals_table = method_locals(body)
        # (node, the With target `.Member` refers to there): the innermost With wins, a
        # lambda inside it sees it, and a nested method or property declaration does not
        stack: list[tuple[Node, tuple[str, str] | None | bool]] = [(body, False)]
        while stack:
            node, within = stack.pop()
            if node != body and node.type in {
                "method_declaration", "constructor_declaration", "property_declaration"
            }:
                continue
            if node.type == "with_statement":
                # the expression is evaluated outside the block; its statements inside
                inner = with_target(node)
                target_expression = node.child_by_field_name("target")
                stack.extend(
                    (child, within if child == target_expression else inner)
                    for child in reversed(node.named_children)
                )
                continue
            if node.type == "invocation":
                target_node = node.child_by_field_name("target")
                arguments = node.child_by_field_name("arguments")
                if target_node is not None:
                    written = _read_text(target_node, source)
                    typed_receiver = None
                    # `.Save()` inside a With block calls on the With object: read it as
                    # the call it stands for. With no known object it names no method.
                    if written.startswith("."):
                        if within and _IDENT_RE.match(written[1:]):
                            if within[0] == "text":
                                written = within[1] + written
                            else:
                                typed_receiver = within[1]
                        else:
                            written = ""
                    parts = written.split(".")
                    receiver_text = ".".join(parts[:-1])
                    receiver = receiver_text.casefold()
                    callee = parts[-1]
                    first_segment = receiver.split(".")[0]
                    # `handler(x)` where `handler` is a local calls a value, not a method
                    value_call = not written or (
                        not receiver and typed_receiver is None and callee.casefold() in locals_table
                    )
                    is_local = first_segment in locals_table
                    self_receiver = not value_call and typed_receiver is None and (
                        not receiver
                        or receiver in {"me", "myclass", type_name.casefold()}
                    )
                    # `Me.field`, `MyClass.field` and `OwnType.field` (a Shared field) read
                    # a member of the caller's own type
                    own_member = (
                        not value_call and typed_receiver is None and not is_local
                        and len(parts) == 3
                        and first_segment in {"me", "myclass", type_name.casefold()}
                    )
                    # A self/unqualified call targets the caller's own type; a
                    # qualified call (Helpers.Log(), OtherType.Foo()) targets the
                    # named receiver type/module declared in this file. Anything
                    # else is left to the cross-file resolver (resolve_vbnet_calls).
                    target_owner = None
                    if value_call or typed_receiver is not None or own_member:
                        pass
                    elif self_receiver:
                        target_owner = owner_key
                    elif not is_local and first_segment not in data_names.get(owner_key, ()):
                        target_owner = owner_by_short.get(receiver.split(".")[-1])
                    arity = len(arguments.named_children) if arguments is not None else 0
                    if target_owner is not None:
                        candidates = methods.get(
                            (target_owner, callee.casefold(), arity), []
                        )
                        if len(candidates) == 1:
                            add_edge(caller_id, candidates[0], "calls", node)
                            stack.extend((child, within) for child in reversed(node.named_children))
                            continue
                    if value_call or not _IDENT_RE.match(callee) or (
                        receiver_text and not _NAME_RE.match(receiver_text)
                    ):
                        stack.extend((child, within) for child in reversed(node.named_children))
                        continue
                    if typed_receiver is not None:
                        receiver_kind = "typed"
                    elif not receiver:
                        receiver_kind = "none"
                    elif self_receiver:
                        receiver_kind = "me"
                    elif receiver == "mybase":
                        receiver_kind = "mybase"
                    elif own_member:
                        receiver_kind = "field"
                        receiver_text = parts[1]
                    elif is_local:
                        receiver_kind = "local" if receiver == first_segment else "value"
                    elif first_segment in {"me", "mybase"}:
                        receiver_kind = "value"
                    else:
                        receiver_kind = "name"
                    if receiver_kind != "value":
                        raw_call = {
                            "caller_nid": caller_id,
                            "callee": callee,
                            "arity": arity,
                            "owner": target_owner,
                            "is_member_call": True,
                            "language": "vbnet",
                            "source_file": source_file,
                            "source_location": f"L{node.start_point[0] + 1}",
                            "caller_owner": owner_key,
                            "receiver": receiver_text,
                            "receiver_kind": receiver_kind,
                            "namespace": namespace,
                            "imports": file_imports,
                        }
                        if receiver_kind == "local" and locals_table.get(receiver):
                            raw_call["receiver_type"] = locals_table[receiver]
                        if typed_receiver is not None:
                            raw_call["receiver_type"] = typed_receiver
                        if nested_types:
                            raw_call["nested_types"] = nested_types
                        raw_calls.append(raw_call)
            stack.extend((child, within) for child in reversed(node.named_children))

    clean_edges = [
        edge for edge in edges
        if edge["source"] in seen_ids and edge["target"] in seen_ids
    ]
    return {"nodes": nodes, "edges": clean_edges, "raw_calls": raw_calls}
