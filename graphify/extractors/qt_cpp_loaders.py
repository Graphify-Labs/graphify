"""Bounded literal URL constructors; loading never executes an analyzed engine."""
from __future__ import annotations

import re
from pathlib import Path

from graphify.extractors.qt_cpp_calls import argument_ranges, closing, conditional_at, literal_string
from graphify.extractors.qt_cpp_facts import owner_scope
from graphify.extractors.qt_cpp_syntax import source_span
from graphify.extractors.qt_cpp_variables import simple_reference, variables_at

_MODES = {"QQmlComponent::PreferSynchronous", "QQmlComponent::Asynchronous"}


def loader_operation_owner(receiver_type, operation):
    """Only exact supported SDK classes own these source load/root mechanisms."""
    owners = {"load": "QQmlApplicationEngine", "loadFromModule": "QQmlApplicationEngine",
              "rootObjects": "QQmlApplicationEngine", "setInitialProperties": "QQmlApplicationEngine",
              "setSource": "QQuickView", "rootObject": "QQuickView", "loadUrl": "QQmlComponent",
              "create": "QQmlComponent", "createWithInitialProperties": "QQmlComponent"}
    kind = receiver_type.removeprefix("::")
    return kind in {"QQmlApplicationEngine", "QQuickView"} if operation == "setInitialProperties" else owners.get(operation) == kind


def literal_loader_arguments(receiver_type, operation, args, *, types=None, position=0):
    """Distinguish URL methods and literal compilation modes from other overloads."""
    kind = receiver_type.removeprefix("::")
    supported = {"load": "QQmlApplicationEngine", "loadFromModule": "QQmlApplicationEngine",
                 "setSource": "QQuickView", "loadUrl": "QQmlComponent"}
    if supported.get(operation) != kind:
        return False
    if operation == "loadFromModule":
        return len(args) == 2
    if len(args) == 1:
        return True
    return (operation == "loadUrl" and len(args) == 2 and args[1]["text"].strip() in _MODES
            and (types is None or types.resolve("QQmlComponent", position) == "QQmlComponent"))


def literal_creation_arguments(operation, args):
    """A supplied context can alter source base/ownership and remains unproved."""
    if operation in {"rootObject", "rootObjects"}:
        return not args
    if operation == "create":
        return not args or len(args) == 1 and args[0]["text"].strip() in {"nullptr", "0"}
    if operation == "createWithInitialProperties":
        return len(args) == 1 or len(args) == 2 and args[1]["text"].strip() in {"nullptr", "0"}
    return len(args) == 1


def literal_url_expression(expression, *, types=None, identities=None, position=0):
    """Keep fromLocalFile semantics: a resource URI is not an absolute file path.

    Relative file paths need the application's unknown runtime working directory;
    conservative omission avoids lending the analyzer root as that directory.
    """
    if types is not None:
        # Every stripped wrapper needs source authority; a custom callable may
        # return another URL despite having a literal written argument.
        for wrapper in re.findall(r"(?<![\w:])((?:::)?(?:QUrl|QString|QLatin1String|QByteArray|QStringLiteral))(?=\s*(?:::fromLocalFile|\())", expression):
            name = wrapper.removeprefix("::")
            if types.resolve(wrapper, position) != name or types.classes.get(name):
                return None
            if (not wrapper.startswith("::") and identities is not None
                    and identities.resolve(name, position)["status"] in {"resolved", "dynamic", "ambiguous"}):
                return None
            # A same-spelled callable can return a different URL; treating the
            # call as a constructor would invent literal argument authority.
            if types.callable_shadow(name, position, absolute=wrapper.startswith("::")):
                return None
    # Only already-authorized global wrappers lose their display qualifier for
    # the shared literal decoder; qualified custom types never reach this path.
    expression = re.sub(r"(?<![\w:])::(QString|QLatin1String|QByteArray|QStringLiteral)(?=\s*\()", r"\1", expression)
    local = re.fullmatch(r"(?:::)?QUrl::fromLocalFile\s*\((.*)\)", expression.strip(), re.S)
    if local:
        value = literal_string(local[1])
        if value is None or not Path(value).is_absolute():
            return None
        return Path(value).as_uri()
    if "fromLocalFile" in expression:
        return None
    wrapped = re.fullmatch(r"(?:::)?QUrl\s*\((.*)\)", expression.strip(), re.S)
    value = literal_string(wrapped[1] if wrapped else expression)
    # QString convenience overloads convert colon resource paths. QUrl does
    # not: its scheme/path validation must survive literal wrapper decoding.
    if wrapped and value is not None and (value.startswith(":") or re.match(r"[A-Za-z]:[/\\]", value)):
        return None
    return value


def collect_loader_constructors(unit, mapping, facts, identities, types):
    """Direct source declarations prove loaders; aliases/new/factories stay opaque.

    A component's engine-only constructor establishes identity for a later loadUrl,
    but is not itself a load. Exact original bytes own each URL occurrence.
    """
    associations = {}
    for match in re.finditer(rb"(?<![\w:])((?:::)?(?:QQmlApplicationEngine|QQmlComponent))\s+([A-Za-z_]\w*)\s*\(", unit.code):
        owner = mapping.owner_at(match.start())
        right = closing(unit.code, match.end() - 1)
        if not owner or owner.get("body") is None or right is None:
            continue
        args = [unit.source[start:end].decode().strip()
                for start, end in argument_ranges(unit.code, match.end(), right)]
        raw_kind, name = match[1].decode(), match[2].decode()
        kind = raw_kind.removeprefix("::")
        if types.resolve(raw_kind, match.start()) != kind or types.classes.get(kind):
            continue
        identity = identities.resolve(name, right + 1)
        variables = variables_at(unit, mapping, right + 1)
        if variables.get(name) != kind:
            continue
        component = kind == "QQmlComponent"
        engine = simple_reference(args[0]) if component and args else ""
        engine_identity = identities.resolve(engine, match.start()) if engine else {}
        if component and identity["status"] == "resolved":
            # An engine-only component has no load fact, but its exact constructor
            # declaration owns the engine association used by a later loadUrl.
            engine_kind = variables.get(engine, "")
            associations[identity["declaration_id"]] = {
                "engine_reference": engine, "engine_declaration_id": engine_identity.get("declaration_id", ""),
                "engine_identity_status": engine_identity.get("status", "unavailable"),
                "engine_identity_reason": engine_identity.get("reason", "component_engine_unestablished"),
                "component_engine_supported": engine_identity.get("status") == "resolved"
                    and engine_kind in {"QQmlEngine", "QQmlApplicationEngine"} and not types.classes.get(engine_kind),
            }
        if (component and (len(args) < 2 or len(args) == 2 and args[1] in {"nullptr", "0"})
                or not component and (not args or len(args) == 1 and args[0] in {"nullptr", "0"})):
            # An empty component waits for loadUrl; preserving it as a load would
            # create a false second source and prevent its root from resolving.
            continue
        url = literal_url_expression(args[1 if component else 0], types=types, identities=identities, position=match.start()) if args else None
        if component:
            tail = args[2:]
            overload = not tail or tail == ["nullptr"] or tail == ["0"] or (
                tail[0] in _MODES and (len(tail) == 1 or tail[1:] in (["nullptr"], ["0"]))
                and types.resolve("QQmlComponent", match.start()) == "QQmlComponent")
            engine_kind = variables.get(engine, "")
            engine_ok = (engine_identity.get("status") == "resolved"
                         and engine_kind in {"QQmlEngine", "QQmlApplicationEngine"}
                         and not types.classes.get(engine_kind))
        else:
            overload = len(args) == 1 or len(args) == 2 and args[1] in {"nullptr", "0"}
            engine_ok = True
        valid = identity["status"] == "resolved" and overload and engine_ok
        facts.add("qml_load", kind, source_span(unit.source, match.start(), right + 1), owner.get("node_id"),
                  receiver_reference=name, receiver_type=kind,
                  receiver_declaration_id=identity["declaration_id"],
                  receiver_identity_status=identity["status"], receiver_identity_reason=identity["reason"],
                  engine_reference=engine, engine_declaration_id=engine_identity.get("declaration_id", ""),
                  operation="component_constructor" if component else "engine_url_constructor",
                  owner_scope_key=owner_scope(unit, owner), literal_url=url,
                  loader_supported=valid, loader_reason="" if valid else "loader_constructor_identity_or_overload_unestablished",
                  assigned_handle="", conditional=conditional_at(unit, match.start()),
                  status="pending", reason="", bridge_direction="cpp_to_qml")
    return associations
