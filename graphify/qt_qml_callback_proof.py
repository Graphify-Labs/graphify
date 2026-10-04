"""Revalidate subscription callbacks against borrowed, source-owned QML facts.

The ordinary QML index owns nonlexical lookup. Captured JS binders remain separate
authority; neither a matching label nor another function in the component repairs
a changed subscription. No corpus source is read or executed at this boundary.
"""
from __future__ import annotations

from pathlib import Path

from graphify.extractors.qml_facts import qml_metadata
from graphify.qml_scope import QmlProjectIndex


def _span(node):
    value = qml_metadata(node).get("span", {})
    fields = ("start_byte", "end_byte", "start_row", "end_row", "start_column", "end_column")
    return value if (isinstance(value, dict) and all(type(value.get(key)) is int and value[key] >= 0 for key in fields)
                     and value["start_byte"] < value["end_byte"] and value["start_row"] <= value["end_row"]) else {}


def _within(node, owner):
    span, enclosing = _span(node), _span(owner)
    return bool(span and enclosing and enclosing["start_byte"] <= span["start_byte"]
                and span["end_byte"] <= enclosing["end_byte"])


def _ancestors(source, nodes):
    """Follow bounded lexical owners, checking source/scope containment at each hop."""
    result, child = [], source
    while qml_metadata(child).get("owner_id"):
        identity = qml_metadata(child)["owner_id"]
        if identity in result or identity not in nodes or len(result) >= 32:
            return None
        owner = nodes[identity]
        md, parent = qml_metadata(child), qml_metadata(owner)
        if (owner.get("source_file") != source.get("source_file") or not _within(child, owner)
                or md.get("component_key") != parent.get("component_key")
                or md.get("object_scope_key") != parent.get("object_scope_key")):
            return None
        result.append(identity)
        child = owner
    return result


def valid_subscription_callback(subscription, metadata, nodes):
    """Bind a derived site to its original call or its exact Connections handler."""
    # Mapping keys carry identity after JSON reload; producer dictionaries carry
    # it directly. Borrow a normalized view without changing either representation.
    by_id = {identity: {**node, "id": identity} for identity, node in nodes.items()}
    owner_id, handler_id = metadata.get("owner_id"), metadata.get("handler_target_id")
    if owner_id not in by_id or handler_id not in by_id:
        return False
    source, handler = by_id[owner_id], by_id[handler_id]
    md, hmd = qml_metadata(source), qml_metadata(handler)
    if (md.get("contract_version") != 1 or hmd.get("contract_version") != 1
            or source.get("source_file") != subscription.get("source_file")
            or handler.get("source_file") != source.get("source_file")
            or subscription.get("source_location") != source.get("source_location")
            or metadata.get("span") != _span(source)
            or hmd.get("component_key") != md.get("component_key")):
        return False
    if metadata.get("subscription_form") == "Connections":
        enclosing = by_id.get(md.get("owner_id"), {})
        short = str(md.get("raw_name") or "").rsplit(".", 1)[-1]
        return (owner_id == handler_id and md.get("kind") == "handler" and md.get("connections") is True
                and md.get("connection_supplied") is True and bool(md.get("connection_target"))
                and not md.get("disabled_reason") and not md.get("attached_prefix")
                and short.startswith("on") and short[2:3].isupper()
                and md.get("reference") == short[2:3].lower() + short[3:]
                and qml_metadata(enclosing).get("kind") == "object"
                and qml_metadata(enclosing).get("type_name") == "Connections"
                and _ancestors(source, by_id) is not None)
    if (metadata.get("subscription_form") != "signal.connect" or md.get("kind") != "call"
            or not isinstance(md.get("reference"), str) or not md["reference"].endswith(".connect")
            or type(md.get("callback_argument_count")) is not int or md["callback_argument_count"] != 1
            or not isinstance(md.get("callback_reference"), str) or not md["callback_reference"]
            or hmd.get("kind") not in {"function", "js_function"}):
        return False
    owners = _ancestors(source, by_id)
    if not owners:
        return False
    facts = [node for node in by_id.values() if node.get("source_file") == source.get("source_file")
             and qml_metadata(node).get("contract_version") == 1]
    index = QmlProjectIndex(facts, [], root=Path("."))
    file = index.paths.get(owner_id)
    # QML functions belong to an exact indexed object; local JS declarations
    # borrow their lexical owner. Both must stay inside the original source span.
    if hmd.get("kind") == "function":
        containers = index.objects.get((index.paths.get(handler_id), hmd.get("component_key"),
                                       hmd.get("object_scope_key")), [])
        if len(containers) != 1 or not _within(handler, index.nodes[containers[0]]):
            return False
    elif not _ancestors(handler, by_id):
        return False
    callback = md["callback_reference"]
    if md.get("callback_lexical_shadowed") is True:
        # Local functions and recursion have source-AST binder IDs. A formal,
        # reassigned variable or implicit native parameter has no callable binder.
        parent = hmd.get("owner_id")
        return (md.get("callback_lexical_target_id") == handler_id and callback == hmd.get("raw_name")
                and hmd.get("object_scope_key") == md.get("object_scope_key")
                and (handler_id in owners or parent in owners)
                and (handler_id in owners or parent in by_id and _within(handler, by_id[parent])))
    if md.get("callback_lexical_shadowed") is not False or md.get("callback_lexical_target_id"):
        return False
    # Resolve the literal callback in the original object/component scope. This
    # uses the same production lookup as projection, rather than a global name scan.
    return bool(file and index.resolve_member(file, md.get("component_key", ""),
                md.get("object_scope_key", ""), callback).target_id == handler_id)
