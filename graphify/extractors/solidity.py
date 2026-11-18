"""Structural extraction for Solidity source files."""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

from tree_sitter import Node

from graphify.extractors.base import _file_stem, _make_id, _read_source_bytes, _read_text
from graphify.extractors.engine import _underscore_salted_nid


_IDENTIFIER = re.compile(r"[A-Za-z_$][A-Za-z0-9_$]*")

_TYPE_DECLARATIONS = {
    "contract_declaration": "contract",
    "interface_declaration": "interface",
    "library_declaration": "library",
}


def _unquote(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
        return value[1:-1]
    return value


def _rightmost_operand(obj: Node) -> Node:
    """The receiver of a member call whose object tree-sitter-solidity merged
    with a preceding operator (see :func:`_callee_text`)."""
    base = obj
    while True:
        unwrapped = base.named_children[0] if base.type == "expression" and base.named_children else base
        right = (
            unwrapped.child_by_field_name("right") if unwrapped.type == "binary_expression"
            else unwrapped.child_by_field_name("argument") if unwrapped.type == "unary_expression"
            else None
        )
        if right is None:
            return base
        base = right


def _member_callee(callee: Node) -> Node | None:
    """The ``member_expression`` of a member call ``recv.f(..)``, else ``None``."""
    inner = callee.named_children[0] if callee.type == "expression" and callee.named_children else callee
    return inner if inner.type == "member_expression" else None


def _callee_text(callee: Node, source: bytes) -> str:
    """The callee as written, e.g. ``super.supportsInterface`` or ``_check``.

    tree-sitter-solidity parses ``a || super.f(x)`` as a call of the member
    ``(a || super).f``: the binary expression is swallowed into the member's
    object. Read the right-most operand as the receiver instead, so the call
    is seen as ``super.f`` (and ``a && b.c(x)`` as ``b.c``). A prefix operator
    is swallowed the same way: ``!Lib.f(x)`` parses as ``(!Lib).f``.
    """
    inner = _member_callee(callee)
    if inner is not None:
        obj = inner.child_by_field_name("object")
        prop = inner.child_by_field_name("property")
        if obj is not None and prop is not None:
            base = _rightmost_operand(obj)
            if base is not obj:
                return f"{_read_text(base, source)}.{_read_text(prop, source)}"
    return _read_text(callee, source)


_SIMPLE_MEMBERS = {
    "struct_declaration": "struct",
    "enum_declaration": "enum",
    "event_definition": "event",
    "error_declaration": "error",
    "state_variable_declaration": "state_variable",
}


def _callable_signature(declaration: Node, source: bytes) -> str:
    """``arity:types`` of a function, modifier or constructor, the part of its
    id that keeps overloads apart."""
    parameters = [
        child for child in declaration.named_children
        if child.type in {"parameter", "fallback_receive_parameter"}
    ]
    types = ",".join(
        _read_text(child.child_by_field_name("type"), source)
        for child in parameters
        if child.child_by_field_name("type") is not None
    )
    return f"{len(parameters)}:{types}"


def _member_identity(member: Node, source: bytes) -> tuple[str, str, str] | None:
    """``(kind, name, signature)`` a contract member's node id is made from,
    as extract_solidity's ``add_member`` mints it; ``None`` for a member that
    gets no id there."""
    if member.type in _SIMPLE_MEMBERS:
        name_node = member.child_by_field_name("name")
        if name_node is None:
            return None
        name = _read_text(name_node, source)
        return _SIMPLE_MEMBERS[member.type], name, name
    if member.type == "constructor_definition":
        return "constructor", "constructor", _callable_signature(member, source)
    if member.type == "fallback_receive_definition":
        name = "receive" if _read_text(member, source).lstrip().startswith("receive") else "fallback"
        return name, name, _callable_signature(member, source)
    if member.type in {"function_definition", "modifier_definition"}:
        name_node = member.child_by_field_name("name")
        if name_node is None:
            return None
        kind = "modifier" if member.type == "modifier_definition" else "function"
        return kind, _read_text(name_node, source), _callable_signature(member, source)
    return None


def _collision_groups(declared: list[tuple[str, str]]) -> dict[str, set[str]]:
    """``{plain id: {names}}`` for the plain ids two or more distinct names
    would share. ``make_id`` drops a leading ``_`` and folds case, so
    ``_grantRole(bytes32,address)`` and ``grantRole(bytes32,address)`` in one
    contract mint ONE id; an overload is one name, never a collision."""
    groups: dict[str, set[str]] = {}
    for plain, name in declared:
        groups.setdefault(plain, set()).add(name)
    return {plain: names for plain, names in groups.items() if len(names) >= 2}


# A type's written text is read in the contract it was written in (its name
# and the structs/enums/value types it declares), see extract_solidity.qualify.
TypeContext = tuple[str | None, frozenset[str]]
# Variable name -> (normalized type text, context); None when ambiguous.
VariableTypes = dict[str, tuple[str, TypeContext] | None]

_ELEMENTARY_ALIASES = {"uint": "uint256", "int": "int256", "byte": "bytes1"}
_MAPPING_VALUE_NAME = re.compile(r"(.*\S) ([A-Za-z_$][A-Za-z0-9_$]*)")


def _normalize_type(text: str) -> str:
    """One spelling per type: whitespace collapsed (``mapping(a => b)`` ->
    ``mapping(a=>b)``) and the elementary aliases expanded (``uint`` ->
    ``uint256``), so a receiver's type compares equal to a ``using`` target or
    a parameter written differently."""
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r" ?([\[\]().,]|=>) ?", r"\1", text)
    return re.sub(r"\b(uint|int|byte)\b", lambda m: _ELEMENTARY_ALIASES[m.group(1)], text)


def _element_type(text: str) -> str | None:
    """The value type of ``mapping(K=>V)`` or the element type of ``T[]`` /
    ``T[n]`` (normalized text), else ``None``."""
    if text.startswith("mapping(") and text.endswith(")"):
        inner = text[len("mapping("):-1]
        depth = 0
        for index, char in enumerate(inner):
            if char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
            elif depth == 0 and inner.startswith("=>", index):
                value = inner[index + 2:]
                # A named mapping value (`mapping(address a => uint256 b)`).
                named = _MAPPING_VALUE_NAME.fullmatch(value)
                if named and named.group(2) != "payable":
                    value = named.group(1)
                return value
        return None
    if text.endswith("]"):
        depth = 0
        for index in range(len(text) - 1, -1, -1):
            if text[index] == "]":
                depth += 1
            elif text[index] == "[":
                depth -= 1
                if depth == 0:
                    return text[:index] or None
    return None


# Globals the language types itself, so `msg.sender.f()` and
# `keccak256(b).f()` are typed like a declared variable.
_BUILTIN_MEMBER_TYPES = {
    "msg.sender": "address",
    "msg.value": "uint256",
    "tx.origin": "address",
    "block.timestamp": "uint256",
    "block.number": "uint256",
    "block.chainid": "uint256",
}
_BUILTIN_CALL_TYPES = {
    "keccak256": "bytes32",
    "sha256": "bytes32",
    "blockhash": "bytes32",
    "abi.encode": "bytes",
    "abi.encodePacked": "bytes",
    "abi.encodeWithSelector": "bytes",
    "abi.encodeWithSignature": "bytes",
    "abi.encodeCall": "bytes",
}


def _inherited_call(
    caller_id: str, callee: str, arity: int | None, kind: str, source_file: str, node: Node,
) -> dict[str, Any]:
    """A call or modifier the contract itself does not declare, for
    :func:`resolve_solidity_inherited_calls`. ``kind`` is ``inherited`` (bare
    ``f()`` / ``this.f()``, ``emit E()``, ``revert Err()``), ``super``
    (``super.f()``), ``modifier`` or ``qualified`` (``Lib.f()``,
    ``revert Errors.Err()``, with a ``qualifier``)."""
    return {
        "caller_nid": caller_id,
        "callee": callee,
        "arity": arity,
        "solidity_call": kind,
        "language": "solidity",
        "source_file": source_file,
        "source_location": f"L{node.start_point[0] + 1}",
    }


def _c3_linearization(type_id: str, bases: dict[str, list[str]]) -> list[str]:
    """Solidity's C3 linearization of ``type_id``, most derived first.

    ``bases`` lists each type's direct bases in declaration order
    (``contract C is A, B`` -> ``[A, B]``); Solidity treats the LAST one as
    the most derived, so they are merged right to left. Falls back to a
    right-to-left depth-first order when the bases cannot be merged (a cycle
    or an inconsistent hierarchy), so a broken graph still resolves.
    """
    memo: dict[str, list[str]] = {}

    def linearize(tid: str, active: frozenset[str]) -> list[str] | None:
        if tid in memo:
            return memo[tid]
        if tid in active:
            return None
        parents = list(reversed(bases.get(tid, [])))
        sequences: list[list[str]] = []
        for parent in parents:
            lin = linearize(parent, active | {tid})
            if lin is None:
                return None
            sequences.append(list(lin))
        sequences.append(list(parents))
        result = [tid]
        while any(sequences):
            head = None
            for seq in sequences:
                if seq and not any(seq[0] in other[1:] for other in sequences):
                    head = seq[0]
                    break
            if head is None:
                return None
            result.append(head)
            for seq in sequences:
                if seq and seq[0] == head:
                    del seq[0]
        memo[tid] = result
        return result

    linear = linearize(type_id, frozenset())
    if linear is not None:
        return linear
    order: list[str] = []
    stack = [type_id]
    while stack:
        tid = stack.pop()
        if tid in order:
            continue
        order.append(tid)
        stack.extend(bases.get(tid, []))
    return order


def resolve_solidity_inherited_calls(
    per_file: list[dict], all_nodes: list[dict], all_edges: list[dict]
) -> None:
    """Bind calls, ``super`` calls and modifiers a contract inherits.

    The extractor binds ``f()`` and ``onlyX`` only inside the declaring
    contract, so a call to a function or modifier declared in a base contract
    (often in another file) got no edge. Runs after
    :func:`resolve_solidity_type_references` has bound each ``inherits`` edge
    to the base's real node, and walks the caller contract's C3 linearization
    as the compiler does: the first contract that declares a matching member
    wins (``super.f()`` starts after the caller's own contract, as the plain
    lookup does once the extractor found nothing there); several same-arity
    overloads in that contract are ambiguous and get no edge.

    A qualified call (``Lib.f()``, ``Base.f()``, ``revert Errors.Err()``) binds
    to the member of the one library/contract/interface of that name the
    caller's file declares or imports directly; no edge when the name or the
    (name, arity) is ambiguous.

    A call on a receiver of a contract or interface type (``IERC20 token;
    token.transfer()``, ``IERC20(a).transfer()``, ``Ownable(x).owner()``,
    ``token().clock()``) binds by name and arity through that type's
    linearization, as the compiler looks it up: an interface method links to
    the interface's own declaration, never to a guessed implementer. No edge
    when the receiver's type is unknown, is not exactly one visible
    contract/interface, when the name/arity is ambiguous, or when a public
    state variable of that name (its getter) comes first.

    A call attached by a ``using`` directive (``using SafeCast for uint256;
    x.toUint48()``, ``using EnumerableSet for EnumerableSet.AddressSet;
    _set.add(a)``) binds to the library or free function it attaches: the
    directives of the caller's contract and file, and the ``global`` ones of
    the receiver's type, whose target is ``*`` or the receiver's declared
    type, offering a function of that name with one more parameter than the
    call passes (the receiver) and the receiver's type as its first. Only a
    single such function is linked; no edge when the receiver's type is
    unknown, a directive's library is ambiguous, or two functions fit.
    """
    calls = [
        rc
        for result in per_file
        for rc in result.get("raw_calls", []) or []
        if rc.get("solidity_call")
    ]
    if not calls:
        return
    node_by_id = {node.get("id"): node for node in all_nodes}

    def meta(nid: Any) -> dict:
        node = node_by_id.get(nid)
        value = node.get("metadata") if node else None
        return value if isinstance(value, dict) else {}

    type_kinds = set(_TYPE_DECLARATIONS.values())
    owner: dict[str, str] = {}
    functions: dict[str, dict[str, list[tuple[str, Any]]]] = {}
    modifiers: dict[str, dict[str, list[str]]] = {}
    bases: dict[str, list[str]] = {}
    using: dict[str, list[dict]] = {}
    state_variables: dict[str, dict[str, str]] = {}
    existing: set[tuple[Any, Any, Any]] = set()
    for edge in all_edges:
        source, target, relation = edge.get("source"), edge.get("target"), edge.get("relation")
        existing.add((source, target, relation))
        if not isinstance(source, str) or not isinstance(target, str):
            continue
        source_meta = meta(source)
        if source_meta.get("language") != "solidity" or source_meta.get("kind") not in type_kinds:
            continue
        if isinstance(source_meta.get("using"), list):
            using[source] = source_meta["using"]
        if relation == "method":
            member = meta(target)
            name = str(node_by_id.get(target, {}).get("label", ""))
            name = name[:-2] if name.endswith("()") else name
            owner[target] = source
            if member.get("kind") == "function":
                functions.setdefault(source, {}).setdefault(name, []).append(
                    (target, member.get("arity"))
                )
            elif member.get("kind") == "modifier":
                modifiers.setdefault(source, {}).setdefault(name, []).append(target)
        elif relation == "contains" and meta(target).get("kind") == "state_variable":
            state_variables.setdefault(source, {})[str(node_by_id.get(target, {}).get("label", ""))] = target
        elif relation == "contains" and meta(target).get("kind") in {"event", "error"}:
            # An event/error is a call target too (`emit E()`, `revert Err()`).
            functions.setdefault(source, {}).setdefault(
                str(node_by_id.get(target, {}).get("label", "")), []
            ).append((target, meta(target).get("arity")))
        elif relation == "inherits" and meta(target).get("kind") in type_kinds:
            bases.setdefault(source, []).append(target)

    def find(linear: list[str], name: str, arity: Any, kind: str) -> str | None:
        for type_id in linear:
            if kind == "member" and name in state_variables.get(type_id, {}):
                # `x.name()` reads a public state variable's getter.
                return None
            if kind == "modifier":
                found = modifiers.get(type_id, {}).get(name, [])
            else:
                found = [
                    nid for nid, declared in functions.get(type_id, {}).get(name, [])
                    if (arity is None or declared is None or declared == arity)
                    # A value's members are its functions, not its events/errors.
                    and (kind != "member" or meta(nid).get("kind") == "function")
                ]
            if found:
                return found[0] if len(found) == 1 else None
        return None

    # `Errors.Err` names a type the caller's file declares or imports directly,
    # the scope resolve_solidity_type_references binds base names in.
    types_by_file: dict[tuple[str, str], list[str]] = {}
    file_by_id: dict[Any, str] = {}
    imported: dict[str, set[str]] = {}
    # `using` directives at file level, and the `global` ones by type.
    file_using: dict[str, list[dict]] = {}
    global_using: list[tuple[dict, str]] = []
    # Free functions by (file, name), for `using {f} for T`.
    free_functions: dict[tuple[str, str], list[str]] = {}
    if any(rc["solidity_call"] in {"qualified", "member"} for rc in calls):
        for node in all_nodes:
            node_file = node.get("source_file")
            if not node_file:
                continue
            if node.get("label") == Path(str(node_file)).name:
                file_by_id[node.get("id")] = str(node_file)
                directives = meta(node.get("id")).get("using")
                if isinstance(directives, list):
                    file_using[str(node_file)] = directives
                    global_using.extend((d, str(node_file)) for d in directives if d.get("global"))
            elif meta(node.get("id")).get("kind") in type_kinds:
                types_by_file.setdefault((str(node_file), str(node.get("label", ""))), []).append(node["id"])
        for edge in all_edges:
            if edge.get("relation") == "imports_from":
                importer = file_by_id.get(edge.get("source"))
                imported_file = file_by_id.get(edge.get("target"))
                if importer and imported_file:
                    imported.setdefault(importer, set()).add(imported_file)
            elif (
                edge.get("relation") == "contains"
                and edge.get("source") in file_by_id
                and meta(edge.get("target")).get("kind") == "function"
            ):
                name = str(node_by_id.get(edge.get("target"), {}).get("label", ""))
                free_functions.setdefault(
                    (file_by_id[edge["source"]], name[:-2] if name.endswith("()") else name), [],
                ).append(str(edge["target"]))

    reachable_cache: dict[str, list[str]] = {}

    def reachable(caller_file: str) -> list[str]:
        """Every file ``caller_file`` imports, directly or through the files
        it imports (`import {IERC20} from "./ERC20.sol"` re-exports a type
        ERC20.sol itself imports)."""
        if caller_file not in reachable_cache:
            seen: set[str] = set()
            stack = sorted(imported.get(caller_file, set()))
            while stack:
                current = stack.pop()
                if current in seen or current == caller_file:
                    continue
                seen.add(current)
                stack.extend(sorted(imported.get(current, set())))
            reachable_cache[caller_file] = sorted(seen)
        return reachable_cache[caller_file]

    def visible_types(caller_file: str, name: str, transitive: bool = False) -> list[str]:
        """The types named ``name`` that ``caller_file`` declares or imports
        directly; with ``transitive``, when there is none, those of every
        file it reaches through its imports."""
        found = types_by_file.get((caller_file, name), []) + [
            type_id
            for imported_file in sorted(imported.get(caller_file, set()))
            for type_id in types_by_file.get((imported_file, name), [])
        ]
        if found or not transitive:
            return found
        return [
            type_id
            for reached in reachable(caller_file)
            for type_id in types_by_file.get((reached, name), [])
        ]

    linear_cache: dict[str, list[str]] = {}

    def linearization(type_id: str) -> list[str]:
        if type_id not in linear_cache:
            linear_cache[type_id] = _c3_linearization(type_id, bases)
        return linear_cache[type_id]

    def receiver_types(rc: dict) -> list[tuple[str, str]]:
        """``(type, file)`` readings of a member call's receiver, best first:
        the type the extractor read (a local, parameter, own state variable
        or conversion), a base contract's state variable of the receiver's
        name, or the declared return type of the function ``g`` in
        ``g(..).f()``. ``file`` is the file whose scope names the type."""
        caller = rc.get("caller_nid")
        readings: list[tuple[str, str]] = []
        caller_file = str(node_by_id.get(caller, {}).get("source_file", ""))
        if rc.get("receiver_type"):
            readings.append((str(rc["receiver_type"]), caller_file))
        contract = owner.get(str(caller))
        if not contract:
            return readings
        linear = linearization(contract)
        variable = rc.get("qualifier") if rc["solidity_call"] == "qualified" else None
        if variable:
            # Not a local or own state variable (the extractor checked), so
            # maybe a base contract's.
            for type_id in linear[1:]:
                nid = state_variables.get(type_id, {}).get(str(variable))
                if nid is not None:
                    declared = meta(nid).get("declared_type")
                    if declared:
                        readings.append((str(declared), str(node_by_id[nid].get("source_file", ""))))
                    break
        result_of = rc.get("receiver_call")
        if isinstance(result_of, list) and len(result_of) == 2:
            function = find(linear, str(result_of[0]), result_of[1], "inherited")
            returned = meta(function).get("returns") if function else None
            if function and returned:
                readings.append((str(returned), str(node_by_id[function].get("source_file", ""))))
        return readings

    def typed_member(rc: dict, name: str) -> str | None:
        """``recv.name()`` bound through the receiver's contract/interface
        type, the first reading of it that names a visible type."""
        for type_name, scope_file in receiver_types(rc):
            scope = visible_types(scope_file, type_name, transitive=True)
            if not scope:
                # Not a type here (`uint256`, or `g(x)` was a call, not a
                # conversion): try the next reading.
                continue
            # Fail closed when the type is ambiguous or a library (a value
            # never has a library type).
            if len(scope) != 1 or meta(scope[0]).get("kind") not in {"contract", "interface"}:
                return None
            return find(linearization(scope[0]), name, rc.get("arity"), "member")

    def visible_free_functions(scope_file: str, name: str) -> list[str]:
        direct = free_functions.get((scope_file, name), []) + [
            nid
            for imported_file in sorted(imported.get(scope_file, set()))
            for nid in free_functions.get((imported_file, name), [])
        ]
        return direct or [
            nid for reached in reachable(scope_file) for nid in free_functions.get((reached, name), [])
        ]

    def attached_functions(directive: dict, scope_file: str, name: str) -> list[str] | None:
        """The functions named ``name`` that ``directive`` attaches, read in
        ``scope_file``; ``None`` when its library is ambiguous."""
        if "library" in directive:
            libraries = visible_types(scope_file, str(directive["library"]), transitive=True)
            if not libraries:
                return []  # a library outside the corpus
            if len(libraries) != 1 or meta(libraries[0]).get("kind") != "library":
                return None
            return [nid for nid, _arity in functions.get(libraries[0], {}).get(name, [])]
        attached: list[str] = []
        for bound in directive.get("functions", []):
            qualifier, _, function = str(bound).rpartition(".")
            if function != name:
                continue
            if not qualifier:
                attached.extend(visible_free_functions(scope_file, function))
                continue
            libraries = visible_types(scope_file, qualifier, transitive=True)
            if len(libraries) > 1:
                return None
            if libraries:
                attached.extend(nid for nid, _arity in functions.get(libraries[0], {}).get(function, []))
        return attached

    def using_member(rc: dict, name: str) -> str | None:
        """``recv.name()`` bound to the one function a ``using`` directive in
        scope attaches to the receiver's type, if there is exactly one."""
        caller = str(rc.get("caller_nid"))
        caller_file = str(node_by_id.get(caller, {}).get("source_file", ""))
        contract = owner.get(caller)
        scoped = [(d, caller_file) for d in using.get(contract or "", [])] + [
            (d, caller_file) for d in file_using.get(caller_file, []) if not d.get("global")
        ]
        arity = rc.get("arity")
        if not isinstance(arity, int):
            return None
        for type_name, _scope_file in receiver_types(rc):
            directives = scoped + [(d, f) for d, f in global_using if d.get("for") == type_name]
            found: set[str] = set()
            for directive, scope_file in directives:
                if directive.get("for") not in {"*", type_name}:
                    continue
                attached = attached_functions(directive, scope_file, name)
                if attached is None:
                    return None
                found.update(
                    nid for nid in attached
                    if meta(nid).get("arity") == arity + 1
                    and meta(nid).get("first_param_type") == type_name
                )
            if found:
                return next(iter(found)) if len(found) == 1 else None
        return None

    for rc in calls:
        caller = rc.get("caller_nid")
        name = rc.get("callee")
        if not caller or not name:
            continue
        kind = rc["solidity_call"]
        contract = owner.get(caller)
        if kind == "member":
            # A type's own member beats a `using`-attached function (Solidity
            # resolution precedence), so try the typed receiver first.
            target = typed_member(rc, name) or using_member(rc, name)
        elif kind == "qualified":
            # `Lib.f()` names its type, so it needs no owning contract (a free
            # function calls libraries too).
            caller_file = str(node_by_id.get(caller, {}).get("source_file", ""))
            scope = visible_types(caller_file, str(rc.get("qualifier", "")))
            # Fail closed when the name is not visible or is ambiguous. A
            # name that is no type may be a base contract's state variable
            # (`hevm.prank()`), or a value with a `using`-attached function
            # (`_checkpoints.push()`).
            target = (
                find(scope, name, rc.get("arity"), kind) if len(scope) == 1
                else (typed_member(rc, name) or using_member(rc, name)) if not scope
                else None
            )
        elif not contract:
            continue
        else:
            # The extractor already looked in the caller's own contract.
            target = find(linearization(contract)[1:], name, rc.get("arity"), kind)
        if target is None or target == caller:
            continue
        relation = "uses" if kind == "modifier" else "calls"
        if (caller, target, relation) in existing:
            continue
        existing.add((caller, target, relation))
        all_edges.append({
            "source": caller,
            "target": target,
            "relation": relation,
            "confidence": "EXTRACTED",
            "source_file": rc.get("source_file"),
            "source_location": rc.get("source_location"),
            "weight": 1.0,
        })


def resolve_solidity_type_references(
    _per_file: list[dict], all_nodes: list[dict], all_edges: list[dict]
) -> None:
    """Bind inheritance and using references to types in the file or its imports."""
    node_by_id = {node.get("id"): node for node in all_nodes}
    file_id_by_source = {
        str(node["source_file"]): node["id"]
        for node in all_nodes
        if node.get("source_file")
        and node.get("label") == Path(str(node["source_file"])).name
    }
    source_by_file_id = {nid: source for source, nid in file_id_by_source.items()}
    imported_sources: dict[str, set[str]] = {}
    for edge in all_edges:
        if edge.get("relation") != "imports_from":
            continue
        source_file = source_by_file_id.get(edge.get("source"))
        target_file = source_by_file_id.get(edge.get("target"))
        if source_file and target_file:
            imported_sources.setdefault(source_file, set()).add(target_file)

    types: dict[tuple[str, str], list[str]] = {}
    for node in all_nodes:
        metadata = node.get("metadata")
        if not isinstance(metadata, dict) or metadata.get("kind") not in _TYPE_DECLARATIONS.values():
            continue
        source_file = node.get("source_file")
        if source_file:
            types.setdefault((str(source_file), str(node.get("label", ""))), []).append(node["id"])

    for edge in all_edges:
        context = edge.get("context")
        if not isinstance(context, str) or not context.startswith("solidity_type:"):
            continue
        source_node = node_by_id.get(edge.get("source"))
        if not source_node or not source_node.get("source_file"):
            continue
        source_file = str(source_node["source_file"])
        name = context.split(":", 1)[1]
        candidates = list(types.get((source_file, name), []))
        for imported in imported_sources.get(source_file, set()):
            candidates.extend(types.get((imported, name), []))
        if len(candidates) == 1:
            edge["target"] = candidates[0]


def extract_solidity(path: Path) -> dict:
    try:
        import tree_sitter_solidity
        from tree_sitter import Language, Parser
    except ImportError:
        return {"nodes": [], "edges": [], "error": "tree-sitter-solidity not installed"}

    try:
        source = _read_source_bytes(path)
        root = Parser(Language(tree_sitter_solidity.language())).parse(source).root_node
    except Exception as exc:
        return {"nodes": [], "edges": [], "error": f"Solidity grammar failed to load: {exc}"}

    source_file = str(path)
    stem = _file_stem(path)
    file_id = _make_id(source_file)
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    raw_calls: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    seen_edges: set[tuple[str, str, str]] = set()

    def add_node(
        nid: str,
        label: str,
        node: Node,
        *,
        kind: str,
        source_backed: bool = True,
        callable_node: bool = False,
        arity: int | None = None,
        extra: dict[str, Any] | None = None,
    ) -> str:
        if nid not in seen_ids:
            seen_ids.add(nid)
            metadata: dict[str, Any] = {"language": "solidity", "kind": kind}
            if arity is not None:
                # Parameter count, so the cross-contract pass can pick the
                # same overload the in-contract lookup does (name, arity).
                metadata["arity"] = arity
            if extra:
                metadata.update(extra)
            item: dict[str, Any] = {
                "id": nid,
                "label": label,
                "file_type": "code",
                "source_location": f"L{node.start_point[0] + 1}",
                "metadata": metadata,
            }
            if source_backed:
                item["source_file"] = source_file
            if callable_node:
                item["_callable"] = True
            nodes.append(item)
        return nid

    def add_edge(
        source_id: str,
        target_id: str,
        relation: str,
        node: Node,
        *,
        context: str | None = None,
        target_file: str | None = None,
    ) -> None:
        key = (source_id, target_id, relation)
        if not source_id or not target_id or source_id == target_id or key in seen_edges:
            return
        seen_edges.add(key)
        item: dict[str, Any] = {
            "source": source_id,
            "target": target_id,
            "relation": relation,
            "confidence": "EXTRACTED",
            "source_file": source_file,
            "source_location": f"L{node.start_point[0] + 1}",
            "weight": 1.0,
        }
        if context:
            item["context"] = context
        if target_file:
            item["target_file"] = target_file
        edges.append(item)

    add_node(file_id, path.name, root, kind="file")

    def type_stub(name: str, node: Node) -> str:
        name = name.split(".")[-1]
        nid = _make_id("solidity", "type", name)
        add_node(nid, name, node, kind="external_type", source_backed=False)
        return nid

    def qualified_call(caller_id: str, qualifier: str, member: str, arity: int, node: Node) -> None:
        """Park ``Qualifier.member(..)`` for resolve_solidity_inherited_calls,
        which binds it through a type the file declares or imports."""
        call = _inherited_call(caller_id, member, arity, "qualified", source_file, node)
        call["qualifier"] = import_aliases.get(qualifier, qualifier)
        raw_calls.append(call)

    def member_call(
        caller_id: str, member: str, arity: int, node: Node,
        receiver: str | None, receiver_call: tuple[str, int] | None,
    ) -> None:
        """Park ``recv.member(..)`` for resolve_solidity_inherited_calls, with
        the receiver's declared type and/or, for ``g(..).member()``, the call
        whose result it is (typed there from ``g``'s return type)."""
        call = _inherited_call(caller_id, member, arity, "member", source_file, node)
        if receiver:
            call["receiver_type"] = receiver
        if receiver_call:
            call["receiver_call"] = list(receiver_call)
        raw_calls.append(call)

    def split_qualified(written: str) -> tuple[str, str] | None:
        """``("Lib", "f")`` for ``Lib.f``; ``None`` for ``a.b.f``, ``x[i].f``,
        ``f().g``, ``super.f`` or ``this.f``."""
        qualifier, _, member = written.partition(".")
        if (
            qualifier in {"super", "this"}
            or not _IDENTIFIER.fullmatch(qualifier)
            or not _IDENTIFIER.fullmatch(member)
        ):
            return None
        return qualifier, member

    # `import {A as B} from "./A.sol";` makes `B.f()` call `A.f`.
    import_aliases: dict[str, str] = {}
    for declaration in root.named_children:
        if declaration.type != "import_directive":
            continue
        imported_name: str | None = None
        for index, child in enumerate(declaration.children):
            field = declaration.field_name_for_child(index)
            if field == "import_name":
                imported_name = _read_text(child, source)
            elif field == "alias" and imported_name is not None:
                # A namespace alias (`import "./x.sol" as X;`) has no
                # import_name before it and is not a type.
                import_aliases[_read_text(child, source)] = imported_name
                imported_name = None
            elif child.type == ",":
                imported_name = None
        source_node = declaration.child_by_field_name("source")
        if source_node is None:
            continue
        relative = _unquote(_read_text(source_node, source))
        if not relative or relative.startswith(("http:", "https:")):
            continue
        # `../utils/Errors.sol` must name the real file, not `proxy/utils/Errors.sol`.
        target = Path(os.path.normpath(path.parent / relative))
        add_edge(
            file_id,
            _make_id(str(target)),
            "imports_from",
            declaration,
            target_file=str(target),
        )

    # `contract Pair` / `contract _Pair` in one file would share an id too.
    type_groups = _collision_groups([
        (_make_id(stem, _TYPE_DECLARATIONS[declaration.type], _read_text(name_node, source)),
         _read_text(name_node, source))
        for declaration in root.named_children
        if declaration.type in _TYPE_DECLARATIONS
        and (name_node := declaration.child_by_field_name("name")) is not None
        and declaration.child_by_field_name("body") is not None
    ])

    # Receiver typing: the declared type of `recv` in `recv.f(..)`, so a call
    # on a typed value can be bound through that type. A type is kept as its
    # normalized text plus the contract it was written in (`TypeContext`), so
    # a struct, enum or value type declared in a contract reads as
    # `Contract.Name` everywhere, as callers in other files must write it.
    file_context: TypeContext = (None, frozenset())
    contract_contexts: dict[int, TypeContext] = {}
    # Struct fields by qualified struct name, for `s.field.f()`.
    struct_fields: dict[str, tuple[TypeContext, dict[str, str]]] = {}

    def field_types(struct: Node) -> dict[str, str]:
        struct_body = struct.child_by_field_name("body")
        fields: dict[str, str] = {}
        for field in struct_body.named_children if struct_body is not None else []:
            field_type = field.child_by_field_name("type")
            field_name = field.child_by_field_name("name")
            if field.type == "struct_member" and field_type is not None and field_name is not None:
                fields[_read_text(field_name, source)] = _normalize_type(_read_text(field_type, source))
        return fields

    for declaration in root.named_children:
        if declaration.type == "struct_declaration":
            name_node = declaration.child_by_field_name("name")
            if name_node is not None:
                struct_fields[_read_text(name_node, source)] = (file_context, field_types(declaration))
            continue
        if declaration.type not in _TYPE_DECLARATIONS:
            continue
        name_node = declaration.child_by_field_name("name")
        body = declaration.child_by_field_name("body")
        if name_node is None or body is None:
            continue
        owner_name = _read_text(name_node, source)
        local_types = frozenset(
            _read_text(member.child_by_field_name("name"), source)
            for member in body.named_children
            if member.type in {"struct_declaration", "enum_declaration", "user_defined_type_definition"}
            and member.child_by_field_name("name") is not None
        )
        context: TypeContext = (owner_name, local_types)
        contract_contexts[declaration.id] = context
        for member in body.named_children:
            member_name = member.child_by_field_name("name")
            if member.type == "struct_declaration" and member_name is not None:
                struct_fields[f"{owner_name}.{_read_text(member_name, source)}"] = (
                    context, field_types(member),
                )

    def qualify(text: str, context: TypeContext) -> str:
        """``text`` as written in ``context``, with its leading type name
        qualified (``Trace208`` in library Checkpoints -> ``Checkpoints.Trace208``)
        and an import alias replaced by the name it imports."""
        match = _IDENTIFIER.match(text)
        if match is None:
            return text
        head, rest = match.group(0), text[match.end():]
        owner_name, local_types = context
        if not rest.startswith(".") and owner_name and head in local_types:
            return f"{owner_name}.{head}{rest}"
        return import_aliases.get(head, head) + rest

    def using_directives(scope: Node, context: TypeContext) -> list[dict[str, Any]]:
        """The ``using A for T;`` / ``using A for *;`` / ``using {f, L.g} for
        T [global];`` directives directly in ``scope`` (a contract body or the
        file), for the resolver: ``{"for": T or "*", "library": A}`` or
        ``{"for": T, "functions": [..]}``, plus ``"global": True``. ``T`` is
        qualified like a receiver type so the two compare equal. An operator
        binding (`using {eq as ==} for T`) attaches no member and is skipped."""
        directives: list[dict[str, Any]] = []
        for directive in scope.named_children:
            if directive.type != "using_directive":
                continue
            target = directive.child_by_field_name("source")
            if target is None:
                continue
            item: dict[str, Any] = {
                "for": "*" if target.type == "any_source_type"
                else qualify(_normalize_type(_read_text(target, source)), context),
            }
            library = next((child for child in directive.named_children if child.type == "type_alias"), None)
            if library is not None:
                item["library"] = qualify(_normalize_type(_read_text(library, source)), file_context)
            else:
                functions = [
                    _normalize_type(_read_text(bound, source))
                    for alias in directive.named_children
                    if alias.type == "using_alias" and not any(child.type == "as" for child in alias.children)
                    for bound in alias.named_children
                    if bound.type == "user_defined_type"
                ]
                if not functions:
                    continue
                item["functions"] = [qualify(function, file_context) for function in functions]
            if any(child.type == "global" for child in directive.children):
                item["global"] = True
            directives.append(item)
        return directives

    def first_parameter_type(callable_node: Node, context: TypeContext) -> dict[str, Any]:
        """``{"first_param_type": T}`` for a library or free function, the
        type a ``using`` directive attaches it to (``x.f()`` passes ``x``)."""
        first = next((child for child in callable_node.named_children if child.type == "parameter"), None)
        type_node = first.child_by_field_name("type") if first is not None else None
        if type_node is None:
            return {}
        return {"first_param_type": qualify(_normalize_type(_read_text(type_node, source)), context)}

    def declared_types(callable_node: Node, context: TypeContext, inherited: VariableTypes) -> VariableTypes:
        """Parameter, return and local variable types visible in a function
        or modifier, over ``inherited`` (the contract's state variables). A
        name declared twice with different types (sibling blocks) is
        ambiguous and maps to ``None``."""
        found: dict[str, set[str]] = {}
        stack = [callable_node]
        while stack:
            current = stack.pop()
            if current.type in {"parameter", "variable_declaration"}:
                type_node = current.child_by_field_name("type")
                name_node = current.child_by_field_name("name")
                if type_node is not None and name_node is not None:
                    found.setdefault(_read_text(name_node, source), set()).add(
                        _normalize_type(_read_text(type_node, source))
                    )
            stack.extend(current.named_children)
        scope: VariableTypes = dict(inherited)
        for name, types in found.items():
            scope[name] = (next(iter(types)), context) if len(types) == 1 else None
        return scope

    def unwrap(node: Node) -> Node:
        while node.type in {"expression", "parenthesized_expression"} and len(node.named_children) == 1:
            node = node.named_children[0]
        return node

    def typed_receiver(
        callee: Node, scope: VariableTypes, context: TypeContext, local_functions: set[str],
    ) -> str | None:
        """The qualified declared type of the receiver of the member call
        ``callee``: a typed variable, an element of a typed mapping/array, a
        field of a struct declared in this file, a conversion (`IERC20(a)`,
        `uint256(x)`) or a builtin. ``None`` (fail closed) for anything else,
        including `super`, `this` and a type name (`Lib.f()`)."""
        member = _member_callee(callee)
        obj = member.child_by_field_name("object") if member is not None else None
        if obj is None:
            return None
        typed = typed_expression(unwrap(_rightmost_operand(obj)), scope, context, local_functions)
        return qualify(*typed) if typed is not None else None

    def member_receiver(
        callee: Node, scope: VariableTypes, context: TypeContext, local_functions: set[str],
    ) -> tuple[str | None, tuple[str, int] | None] | None:
        """``(declared type, (g, arity))`` of a member call's receiver, either
        part ``None`` when unknown; ``None`` when both are."""
        typed = typed_receiver(callee, scope, context, local_functions)
        result_of = call_receiver(callee, scope)
        return (typed, result_of) if typed or result_of else None

    def call_receiver(callee: Node, scope: VariableTypes) -> tuple[str, int] | None:
        """``(g, arity)`` when the receiver of the member call ``callee`` is
        the result of a bare call ``g(..)``, which the resolver types from
        ``g``'s declared return type."""
        member = _member_callee(callee)
        obj = member.child_by_field_name("object") if member is not None else None
        receiver = unwrap(_rightmost_operand(obj)) if obj is not None else None
        if receiver is None or receiver.type != "call_expression":
            return None
        function = receiver.child_by_field_name("function")
        name = _read_text(unwrap(function), source) if function is not None else ""
        if not _IDENTIFIER.fullmatch(name) or name in scope or name in _BUILTIN_CALL_TYPES:
            return None
        return name, sum(child.type == "call_argument" for child in receiver.named_children)

    def typed_expression(
        node: Node, scope: VariableTypes, context: TypeContext, local_functions: set[str],
    ) -> tuple[str, TypeContext] | None:
        if node.type == "identifier":
            return scope.get(_read_text(node, source))
        if node.type == "array_access":
            base = node.child_by_field_name("base")
            typed = typed_expression(unwrap(base), scope, context, local_functions) if base is not None else None
            element = _element_type(typed[0]) if typed is not None else None
            return (element, typed[1]) if typed is not None and element else None
        if node.type == "member_expression":
            written = _read_text(node, source)
            if written in _BUILTIN_MEMBER_TYPES:
                return _BUILTIN_MEMBER_TYPES[written], file_context
            obj = node.child_by_field_name("object")
            prop = node.child_by_field_name("property")
            typed = typed_expression(unwrap(obj), scope, context, local_functions) if obj is not None else None
            struct = struct_fields.get(qualify(*typed)) if typed is not None else None
            field = struct[1].get(_read_text(prop, source)) if struct is not None and prop is not None else None
            return (field, struct[0]) if struct is not None and field else None
        if node.type == "type_cast_expression":
            type_node = next((child for child in node.named_children if child.type == "primitive_type"), None)
            return (_normalize_type(_read_text(type_node, source)), file_context) if type_node is not None else None
        if node.type == "payable_conversion_expression":
            return "address payable", file_context
        if node.type == "call_expression":
            function = node.child_by_field_name("function")
            if function is None:
                return None
            written = _normalize_type(_read_text(unwrap(function), source))
            if written in _BUILTIN_CALL_TYPES:
                return _BUILTIN_CALL_TYPES[written], file_context
            arguments = sum(child.type == "call_argument" for child in node.named_children)
            # `T(x)`: a conversion to the type `T`. A function of the caller's
            # own contract or a variable is not a type; any other name is
            # checked against the declared types by the resolver.
            if (
                arguments == 1
                and _IDENTIFIER.fullmatch(written)
                and written not in scope
                and written not in local_functions
            ):
                return written, context
        return None

    file_using = using_directives(root, file_context)
    if file_using:
        # File-level directives apply to every contract and free function of
        # the file; a `global` one to every use of its type.
        nodes[0]["metadata"]["using"] = file_using

    for declaration in root.named_children:
        type_kind = _TYPE_DECLARATIONS.get(declaration.type)
        if type_kind is None:
            continue
        name_node = declaration.child_by_field_name("name")
        body = declaration.child_by_field_name("body")
        if name_node is None or body is None:
            continue
        type_name = _read_text(name_node, source)
        contract_using = using_directives(body, contract_contexts[declaration.id])
        type_id = add_node(
            _underscore_salted_nid(_make_id(stem, type_kind, type_name), type_name, type_groups),
            type_name,
            declaration,
            kind=type_kind,
            callable_node=type_kind == "contract",
            # Read by the resolver to bind `x.f()` through `using A for T`.
            extra={"using": contract_using} if contract_using else None,
        )
        add_edge(file_id, type_id, "contains", declaration)

        for child in declaration.named_children:
            if child.type != "inheritance_specifier":
                continue
            ancestor = child.child_by_field_name("ancestor")
            if ancestor is None:
                continue
            base_name = _read_text(ancestor, source).split(".")[-1]
            add_edge(
                type_id,
                type_stub(base_name, child),
                "inherits",
                child,
                context=f"solidity_type:{base_name}",
            )

        functions: dict[tuple[str, int], list[str]] = {}
        modifiers: dict[str, str] = {}
        reference_targets: dict[tuple[str, int], str] = {}
        bodies: list[tuple[Node, str, Node]] = []
        type_context = contract_contexts[declaration.id]
        state_types: VariableTypes = {}
        pending_modifiers: list[tuple[str, str, Node]] = []

        # Members whose names differ only by a leading `_` (or by case) share a
        # plain id; the one public name keeps it and the others are salted,
        # as Python and C# do (#3302, #4415). A member that collides with
        # nothing keeps its id.
        member_groups = _collision_groups([
            (_make_id(type_id, kind, name, signature), name)
            for member in body.named_children
            if (identity := _member_identity(member, source)) is not None
            for kind, name, signature in [identity]
        ])

        def add_member(
            member: Node,
            name: str,
            label: str,
            kind: str,
            *,
            relation: str = "contains",
            signature: str = "",
            callable_node: bool = False,
            arity: int | None = None,
            extra: dict[str, Any] | None = None,
        ) -> str:
            # Callables carry an arity:types signature (distinguishes overloads).
            # Non-callable members (struct/enum/event/error/state-var) have no
            # signature; discriminate on the name — which is unique per kind
            # within a contract scope — rather than the line number, so a node's
            # id stays stable when the member moves (avoids incremental id churn).
            member_id = _underscore_salted_nid(
                _make_id(type_id, kind, name, signature or name), name, member_groups,
            )
            add_node(
                member_id,
                label,
                member,
                kind=kind,
                callable_node=callable_node,
                arity=arity,
                extra=extra,
            )
            add_edge(type_id, member_id, relation, member)
            return member_id

        for member in body.named_children:
            kind = member.type
            if kind == "using_directive":
                # `using Lib for T;` names the library directly as a child.
                # `using {f1, f2} for T;` (free functions bound as members,
                # legal since 0.8.13) wraps each one in its own `using_alias`
                # child instead, so the direct-child scan below saw nothing
                # and silently dropped the whole directive.
                alias_nodes = [
                    child for child in member.named_children
                    if child.type in {"type_alias", "identifier", "user_defined_type"}
                ]
                for child in member.named_children:
                    if child.type == "using_alias":
                        alias_nodes.extend(
                            grandchild for grandchild in child.named_children
                            if grandchild.type in {"type_alias", "identifier", "user_defined_type"}
                        )
                for alias_node in alias_nodes:
                    alias = _read_text(alias_node, source)
                    if not alias:
                        continue
                    name = alias.split(".")[-1]
                    add_edge(
                        type_id,
                        type_stub(name, member),
                        "uses",
                        member,
                        context=f"solidity_type:{name}",
                    )
                continue

            if kind == "struct_declaration":
                member_name_node = member.child_by_field_name("name")
                struct_body = member.child_by_field_name("body")
                if member_name_node is None:
                    continue
                name = _read_text(member_name_node, source)
                struct_id = add_member(member, name, name, "struct")
                if struct_body is not None:
                    for field in struct_body.named_children:
                        if field.type != "struct_member":
                            continue
                        field_name_node = field.child_by_field_name("name")
                        if field_name_node is None:
                            continue
                        field_name = _read_text(field_name_node, source)
                        field_id = _make_id(struct_id, "field", field_name)
                        add_node(field_id, field_name, field, kind="field")
                        add_edge(struct_id, field_id, "contains", field)
                continue

            if kind == "enum_declaration":
                member_name_node = member.child_by_field_name("name")
                enum_body = member.child_by_field_name("body")
                if member_name_node is None:
                    continue
                name = _read_text(member_name_node, source)
                enum_id = add_member(member, name, name, "enum")
                if enum_body is not None:
                    for value in enum_body.named_children:
                        if value.type != "enum_value":
                            continue
                        value_name = _read_text(value, source)
                        value_id = _make_id(enum_id, value_name)
                        add_node(value_id, value_name, value, kind="enum_value")
                        # An enum value is a discriminant case, not a declared
                        # field, so it gets `case_of` like every other language
                        # with enums (Java #1719, C#, Swift, Rust, VB.NET). The
                        # relation also matters to resolution: `case_of` targets
                        # are excluded from constructor binding, so an enum value
                        # named like a type can no longer be mistaken for one.
                        add_edge(enum_id, value_id, "case_of", value)
                continue

            simple_kinds = {
                "event_definition": "event",
                "error_declaration": "error",
                "state_variable_declaration": "state_variable",
            }
            if kind in simple_kinds:
                member_name_node = member.child_by_field_name("name")
                if member_name_node is None:
                    continue
                name = _read_text(member_name_node, source)
                arity = sum(
                    child.type in {"event_parameter", "error_parameter", "parameter"}
                    for child in member.named_children
                )
                if kind == "state_variable_declaration":
                    type_node = member.child_by_field_name("type")
                    declared: dict[str, Any] = {}
                    if type_node is not None:
                        state_type = _normalize_type(_read_text(type_node, source))
                        state_types[name] = (state_type, type_context)
                        # Read by the resolver for a receiver that is a base
                        # contract's state variable (`hevm.prank()`).
                        declared["declared_type"] = qualify(state_type, type_context)
                    reference_targets[(name, arity)] = add_member(
                        member, name, name, "state_variable", extra=declared,
                    )
                else:
                    # `emit E(..)`, `revert Err(..)` and `require(c, Err(..))`
                    # call the event/error, like Python's `raise Err()`: bind
                    # it as a call target by (name, arity).
                    member_id = add_member(member, name, name, simple_kinds[kind], arity=arity)
                    functions.setdefault((name, arity), []).append(member_id)
                continue

            if kind not in {
                "function_definition", "constructor_definition", "modifier_definition",
                "fallback_receive_definition",
            }:
                continue

            name_node = member.child_by_field_name("name")
            if kind == "constructor_definition":
                name = "constructor"
                callable_kind = "constructor"
            elif kind == "fallback_receive_definition":
                text = _read_text(member, source).lstrip()
                name = "receive" if text.startswith("receive") else "fallback"
                callable_kind = name
            else:
                if name_node is None:
                    continue
                name = _read_text(name_node, source)
                callable_kind = "modifier" if kind == "modifier_definition" else "function"

            parameters = [
                child for child in member.named_children
                if child.type in {"parameter", "fallback_receive_parameter"}
            ]
            signature = ",".join(
                _read_text(child.child_by_field_name("type"), source)
                for child in parameters
                if child.child_by_field_name("type") is not None
            )
            arity = len(parameters)
            returned: dict[str, Any] = {}
            return_types = [
                parameter.child_by_field_name("type")
                for returns in member.named_children
                if returns.type == "return_type_definition"
                for parameter in returns.named_children
                if parameter.type == "parameter"
            ]
            if type_kind == "library" and callable_kind == "function":
                returned.update(first_parameter_type(member, type_context))
            if len(return_types) == 1 and return_types[0] is not None:
                # Read by the resolver for a receiver that is this function's
                # result (`token().clock()`).
                returned["returns"] = qualify(
                    _normalize_type(_read_text(return_types[0], source)), type_context,
                )
            member_id = add_member(
                member,
                name,
                f"{name}()",
                callable_kind,
                relation="method",
                signature=f"{arity}:{signature}",
                callable_node=True,
                arity=arity,
                extra=returned,
            )
            if callable_kind == "modifier":
                modifiers[name] = member_id
            else:
                functions.setdefault((name, arity), []).append(member_id)
            member_body = member.child_by_field_name("body")
            if member_body is not None:
                bodies.append((member_body, member_id, member))
            if callable_kind != "modifier":
                for child in member.named_children:
                    if child.type != "modifier_invocation":
                        continue
                    modifier_name = next(
                        (
                            _read_text(item, source)
                            for item in child.named_children
                            if item.type == "identifier"
                        ),
                        "",
                    )
                    if modifier_name:
                        pending_modifiers.append((member_id, modifier_name, child))

        for caller_id, modifier_name, modifier_node in pending_modifiers:
            target = modifiers.get(modifier_name)
            if target:
                add_edge(caller_id, target, "uses", modifier_node)
            else:
                # Declared in a base contract (`onlyOwner` from Ownable), or a
                # base-constructor call (`ERC20("n", "s")`), which the
                # inheritance pass finds no modifier for and drops.
                raw_calls.append(_inherited_call(
                    caller_id, modifier_name, None, "modifier", source_file, modifier_node,
                ))

        own_functions = {name for name, _arity in functions}
        for function_body, caller_id, callable_node in bodies:
            scope = declared_types(callable_node, type_context, state_types)
            stack = [function_body]
            while stack:
                node = stack.pop()
                if node.type == "call_expression":
                    callee_node = node.child_by_field_name("function")
                    if callee_node is not None:
                        written = _callee_text(callee_node, source)
                        callee = written.split(".")[-1]
                        arity = sum(child.type == "call_argument" for child in node.named_children)
                        candidates: list[str] = []
                        if "." not in written or written.startswith("this."):
                            candidates = functions.get((callee, arity), [])
                        if len(candidates) == 1:
                            add_edge(caller_id, candidates[0], "calls", node)
                        else:
                            referenced = reference_targets.get((callee, arity))
                            if referenced is not None and "." not in written:
                                add_edge(caller_id, referenced, "references", node)
                            elif not candidates and callee and (
                                "." not in written or written.startswith("this.")
                            ):
                                # Not declared in this contract: an inherited
                                # function (`_msgSender()` from Context), bound
                                # by resolve_solidity_inherited_calls through
                                # the contract's linearized bases.
                                raw_calls.append(_inherited_call(
                                    caller_id, callee, arity, "inherited", source_file, node,
                                ))
                            elif written.startswith("super.") and written.count(".") == 1:
                                raw_calls.append(_inherited_call(
                                    caller_id, callee, arity, "super", source_file, node,
                                ))
                            elif callee and (
                                receiver := member_receiver(callee_node, scope, type_context, own_functions)
                            ):
                                member_call(caller_id, callee, arity, node, *receiver)
                            elif callee and (qualified := split_qualified(written)):
                                # `Lib.f(..)` / `Base.f(..)` / `Errors.Err(..)`.
                                # A value receiver (`token.transfer()`) names no
                                # type, so the resolver binds nothing for it.
                                qualified_call(caller_id, *qualified, arity, node)
                            elif callee and "." in written:
                                raw_calls.append({
                                    "caller_nid": caller_id,
                                    "callee": callee,
                                    "is_member_call": True,
                                    "language": "solidity",
                                    "source_file": source_file,
                                    "source_location": f"L{node.start_point[0] + 1}",
                                })
                elif node.type in {"emit_statement", "revert_statement"}:
                    # `emit E(..)` / `revert Err(..)` are statements, not
                    # call_expressions; `revert()` / `revert("msg")` name none.
                    emitted = node.child_by_field_name(
                        "name" if node.type == "emit_statement" else "error"
                    )
                    if emitted is not None and emitted.type == "expression" and emitted.named_children:
                        emitted = emitted.named_children[0]
                    args = node if node.type == "emit_statement" else next(
                        (child for child in node.named_children if child.type == "revert_arguments"), None,
                    )
                    arity = sum(child.type == "call_argument" for child in args.named_children) if args else 0
                    if emitted is not None and emitted.type == "identifier":
                        callee = _read_text(emitted, source)
                        candidates = functions.get((callee, arity), [])
                        if len(candidates) == 1:
                            add_edge(caller_id, candidates[0], "calls", node)
                        elif not candidates:
                            # Declared in a base contract (an interface's event,
                            # a base's error): bound through the linearization.
                            raw_calls.append(_inherited_call(
                                caller_id, callee, arity, "inherited", source_file, node,
                            ))
                    elif emitted is not None and emitted.type == "member_expression":
                        qualifier = emitted.child_by_field_name("object")
                        prop = emitted.child_by_field_name("property")
                        if qualifier is not None and prop is not None and qualifier.type == "identifier":
                            # `revert Errors.Err(..)`: declared in a library or
                            # contract the file declares or imports.
                            qualified_call(
                                caller_id, _read_text(qualifier, source), _read_text(prop, source), arity, node,
                            )
                stack.extend(reversed(node.named_children))

    # Free (file-level) functions live at source-unit scope, outside any
    # contract/library/interface. Solidity >=0.7 allows them, but the
    # type-declaration loop above only descends into named type declarations,
    # so a free function — and every call it makes — was dropped entirely.
    free_functions: dict[tuple[str, int], list[str]] = {}
    free_groups = _collision_groups([
        (_make_id(stem, "function", _read_text(name_node, source), _callable_signature(declaration, source)),
         _read_text(name_node, source))
        for declaration in root.named_children
        if declaration.type == "function_definition"
        and (name_node := declaration.child_by_field_name("name")) is not None
    ])
    free_bodies: list[tuple[Node, str, Node]] = []
    for declaration in root.named_children:
        if declaration.type != "function_definition":
            continue
        name_node = declaration.child_by_field_name("name")
        if name_node is None:
            continue
        name = _read_text(name_node, source)
        parameters = [
            child for child in declaration.named_children
            if child.type == "parameter"
        ]
        signature = ",".join(
            _read_text(child.child_by_field_name("type"), source)
            for child in parameters
            if child.child_by_field_name("type") is not None
        )
        arity = len(parameters)
        func_id = add_node(
            _underscore_salted_nid(_make_id(stem, "function", name, f"{arity}:{signature}"), name, free_groups),
            f"{name}()",
            declaration,
            kind="function",
            callable_node=True,
            arity=arity,
            extra=first_parameter_type(declaration, file_context),
        )
        add_edge(file_id, func_id, "contains", declaration)
        free_functions.setdefault((name, arity), []).append(func_id)
        body = declaration.child_by_field_name("body")
        if body is not None:
            free_bodies.append((body, func_id, declaration))

    # Resolve calls made from free-function bodies. Only an unambiguous
    # same-file free function is linked directly; a qualified call (Lib.f())
    # is left for resolve_solidity_inherited_calls. Contract methods stay out
    # of scope so we never guess a relationship across a scope we cannot see
    # (fail-closed).
    free_names = {name for name, _arity in free_functions}
    for function_body, caller_id, callable_node in free_bodies:
        scope = declared_types(callable_node, file_context, {})
        stack = [function_body]
        while stack:
            node = stack.pop()
            if node.type == "call_expression":
                callee_node = node.child_by_field_name("function")
                if callee_node is not None:
                    written = _callee_text(callee_node, source)
                    callee = written.split(".")[-1]
                    arity = sum(child.type == "call_argument" for child in node.named_children)
                    if "." not in written:
                        candidates = free_functions.get((callee, arity), [])
                        if len(candidates) == 1:
                            add_edge(caller_id, candidates[0], "calls", node)
                    elif callee and (receiver := member_receiver(callee_node, scope, file_context, free_names)):
                        member_call(caller_id, callee, arity, node, *receiver)
                    elif callee and (qualified := split_qualified(written)):
                        qualified_call(caller_id, *qualified, arity, node)
                    elif callee:
                        raw_calls.append({
                            "caller_nid": caller_id,
                            "callee": callee,
                            "is_member_call": True,
                            "language": "solidity",
                            "source_file": source_file,
                            "source_location": f"L{node.start_point[0] + 1}",
                        })
            stack.extend(reversed(node.named_children))

    clean_edges = [
        edge for edge in edges
        if edge["source"] in seen_ids
        and (edge["target"] in seen_ids or edge["relation"] == "imports_from")
    ]
    return {"nodes": nodes, "edges": clean_edges, "raw_calls": raw_calls}
