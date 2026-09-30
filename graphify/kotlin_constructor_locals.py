"""Conservative Kotlin constructor-local calls within the indexed source corpus.

This is a finite syntax proof, not Kotlin overload resolution: a direct immutable
local, a public final zero-argument class, and an applicable Boolean member.
Re-evaluate the live JVM source batch on a relevant source event; AST cache reuse
keeps this simpler than persisting symbol dependencies in the graph.
"""
from __future__ import annotations

from collections import Counter
from pathlib import Path
import re

SCHEMA = 3
GRAPH_MARKER = "kotlin_constructor_local_schema"
RESULT_MARKER = "_kotlin_constructor_local_schema"
COMPLETE = "_kotlin_constructor_local_complete"
FACTS = "kotlin_constructor_locals"
RECEIPT = "_kotlin_constructor_local_resolved"
UNSUPPORTED = "_kotlin_constructor_local_unsupported_jvm"
JVM_SUFFIXES = {".kt", ".kts", ".java", ".scala", ".groovy", ".gradle"}


def is_kotlin(path) -> bool:
    return Path(path or "").suffix.lower() in {".kt", ".kts"}


def is_jvm_source(path) -> bool:
    return Path(path or "").suffix.lower() in JVM_SUFFIXES


def is_proof_source(path) -> bool:
    return is_kotlin(path) or Path(path or "").suffix.lower() == ".java"


def select_targets(live_paths, selected_paths, removed_paths, graph_schema, *, force_refresh=False):
    """Revisit Kotlin callers with all current JVM negative evidence."""
    selected = list(dict.fromkeys(Path(p) for p in selected_paths))
    live = [Path(p) for p in live_paths if is_jvm_source(p)]
    has_kotlin = any(is_kotlin(p) for p in live)
    events = [*selected, *removed_paths]
    refresh = force_refresh or any(is_kotlin(p) for p in events) or (
        has_kotlin and (graph_schema != SCHEMA or any(is_jvm_source(p) for p in events))
    )
    if refresh:
        selected = list(dict.fromkeys([*selected, *live]))
    return selected, refresh


def cache_current(path, result) -> bool:
    return result is not None and (
        not is_kotlin(path) or (result.get(RESULT_MARKER) == SCHEMA
                                and isinstance(result.get(FACTS), dict))
    )


def _children(node):
    return [c for c in node.named_children if c.type not in {
        "line_comment", "multiline_comment", "block_comment"}]


def _walk(node):
    yield node
    for child in _children(node):
        yield from _walk(child)


def _text(node, source):
    return source[node.start_byte:node.end_byte].decode("utf-8")


def _identifier(node, source):
    if node.type != "identifier":
        return ""
    name = _text(node, source)
    return name if re.fullmatch(r"[A-Za-z_]\w*", name) else ""


def _name(node, source):
    return next((_identifier(c, source) for c in _children(node)
                 if c.type == "identifier"), "")


def _declarations(node, source):
    kinds = {"class_declaration", "object_declaration", "function_declaration",
             "type_alias", "variable_declaration", "parameter", "class_parameter"}
    return [_name(n, source) for n in _walk(node) if n.type in kinds and _name(n, source)]


def _modifiers(node, source, allowed):
    mods = [c for c in _children(node) if c.type == "modifiers"]
    return all(_children(m) and all(_text(c, source) in allowed for c in _children(m))
               for m in mods)


def _plain_class(node, source):
    if node.type != "class_declaration" or node.parent.type != "source_file":
        return False
    if not any(c.type == "class" for c in node.children):
        return False
    if not _modifiers(node, source, {"public", "final"}):
        return False
    if any(c.type not in {"modifiers", "identifier", "primary_constructor", "class_body"}
           for c in _children(node)):
        return False
    for child in _children(node):
        if child.type == "primary_constructor":
            if not _modifiers(child, source, {"public"}):
                return False
            if any(c.type not in {"modifiers", "class_parameters"} for c in _children(child)):
                return False
            if any(_children(c) for c in _children(child) if c.type == "class_parameters"):
                return False
        if child.type == "class_body" and any(
            c.type in {"secondary_constructor", "companion_object"} for c in _children(child)
        ):
            return False
    return bool(_name(node, source))


def _ordinary_function(node, source):
    if not _modifiers(node, source, {"public", "final"}):
        return False
    children = _children(node)
    if any(c.type not in {"modifiers", "identifier", "function_value_parameters",
                          "function_body", "user_type", "nullable_type"} for c in children):
        return False
    # A receiver type before the function name is an extension, not a member.
    name = next((c for c in children if c.type == "identifier"), None)
    return name is not None and not any(
        c.start_byte < name.start_byte and c.type != "modifiers" for c in children
    )


def _boolean_member(node, source):
    if not _ordinary_function(node, source):
        return False
    params = next((c for c in _children(node) if c.type == "function_value_parameters"), None)
    if params is None or len(_children(params)) != 1:
        return False
    param = _children(params)[0]
    return (param.type == "parameter"
            and [c.type for c in _children(param)] == ["identifier", "user_type"]
            and _text(_children(param)[1], source) == "Boolean")


def collect(root, source):
    """Return portable file facts and transient call-offset proof records."""
    package = next((c for c in _children(root) if c.type == "package_header"), None)
    package_name = ""
    if package is not None:
        parts = _children(package)
        if len(parts) == 1 and parts[0].type == "qualified_identifier":
            package_name = _text(parts[0], source)
    imports = any(c.type in {"import", "import_header", "file_annotation"} for c in _children(root))
    top_names = []
    classes = []
    for node in _children(root):
        if node.type == "property_declaration":
            top_names.extend(_name(c, source) for c in _children(node)
                             if c.type == "variable_declaration")
        elif node.type in {"class_declaration", "object_declaration", "function_declaration", "type_alias"}:
            top_names.append(_name(node, source))
        if node.type != "class_declaration":
            continue
        body = next((c for c in _children(node) if c.type == "class_body"), None)
        members = _children(body) if body else []
        names = []
        for member in members:
            if member.type == "property_declaration":
                names.extend(_name(c, source) for c in _children(member)
                             if c.type == "variable_declaration")
            else:
                names.append(_name(member, source))
        counts = Counter(names)
        classes.append({
            "name": _name(node, source), "line": node.start_point[0] + 1,
            "eligible": bool(package_name) and not imports and _plain_class(node, source),
            "members": [{"name": _name(m, source), "line": m.start_point[0] + 1}
                        for m in members if m.type == "function_declaration"
                        and counts[_name(m, source)] == 1 and "Boolean" not in counts
                        and _boolean_member(m, source)],
        })
    facts = {"package": package_name, "names": top_names, "classes": classes}
    calls = {}
    for function in _walk(root):
        if function.type != "function_declaration":
            continue
        fb = next((c for c in _children(function) if c.type == "function_body"), None)
        block = next((c for c in _children(fb) if c.type == "block"), None) if fb else None
        if block is None:
            continue
        parent = function.parent
        caller_ok = parent.type == "source_file" or (
            parent.type == "class_body" and _plain_class(parent.parent, source)
        )
        caller_ok = caller_ok and _ordinary_function(function, source) and not imports and bool(package_name)
        scope_names = Counter(_declarations(function, source))
        direct_names = Counter(
            _name(c, source)
            for prop in _children(block) if prop.type == "property_declaration"
            for c in _children(prop) if c.type == "variable_declaration"
        )
        owner_names = set()
        if parent.type == "class_body":
            # Include member factories, values and classifiers, but not names
            # local to another method (unnecessary whole-class poisoning).
            for m in _children(parent):
                if m.type == "property_declaration":
                    owner_names.update(_name(c, source) for c in _children(m)
                                       if c.type == "variable_declaration")
                else:
                    owner_names.add(_name(m, source))
        bindings = {}
        for prop in _children(block):
            if prop.type != "property_declaration":
                continue
            pc = _children(prop)
            variable = next((c for c in pc if c.type == "variable_declaration"), None)
            if variable is None:
                continue
            name = _name(variable, source)
            if not name:
                continue
            # Recognizing a local value is separate from proving its type.
            # An annotation/qualified initializer must not restore object or
            # global-name fallback for a capitalized local receiver.
            bindings[name] = ("", prop.end_byte, False)
            if len(pc) != 2 or pc[0] != variable or pc[1].type != "call_expression":
                continue
            cc = _children(pc[1])
            ctor = _identifier(cc[0], source) if cc else ""
            if not ctor:
                continue
            eligible = (caller_ok and prop.children[0].type == "val"
                        and len(_children(variable)) == 1 and len(cc) == 2
                        and cc[1].type == "value_arguments" and not _children(cc[1])
                        and direct_names[name] == 1 and ctor not in scope_names and ctor not in owner_names)
            bindings[name] = (ctor, prop.end_byte, eligible)
        for call in _walk(block):
            if call.type != "call_expression":
                continue
            cc = _children(call)
            if not cc or cc[0].type != "navigation_expression":
                continue
            nav = _children(cc[0])
            if len(nav) != 2 or any(n.type != "identifier" for n in nav):
                continue
            receiver = _identifier(nav[0], source)
            if receiver not in bindings:
                continue
            ctor, end, eligible = bindings[receiver]
            # A later local does not shadow an object at this earlier use site.
            if call.start_byte <= end:
                continue
            args = _children(cc[1]) if len(cc) == 2 and cc[1].type == "value_arguments" else []
            literal = len(args) == 1 and _text(args[0], source) in {"true", "false"}
            # A deferred record also suppresses the old bare-name/object path
            # when this syntax is recognizable but outside the proof domain.
            calls[call.start_byte] = {
                "class": ctor,
                "eligible": bool(eligible and call.parent == block and call.start_byte > end
                                 and literal and any(c.type == "." for c in cc[0].children)),
            }
    return facts, calls


def resolve(per_file, all_nodes, all_edges):
    """Stage exact inferred targets, then commit once and receipt the batch."""
    results = [r for r in per_file if FACTS in r]
    if not results or any(not r.get(COMPLETE) for r in results):
        return
    if any(r.get(UNSUPPORTED) for r in results):
        for result in results:
            result[RECEIPT] = True
        return
    # Java declarations are negative evidence only. A global veto intentionally
    # sacrifices recall instead of inventing cross-language package resolution.
    java_names = {n.get("label") for r in per_file for n in r.get("nodes", [])
                  if Path(n.get("source_file") or "").suffix.lower() == ".java"}
    namespaces = {}
    providers = {}
    for result in results:
        facts = result[FACTS]
        pkg = facts["package"]
        namespaces.setdefault(pkg, Counter()).update(facts["names"])
        for cls in facts["classes"]:
            providers.setdefault((pkg, cls["name"]), []).append((result, cls))
    current_nodes = {id(n) for n in all_nodes}
    methods = {(e["source"], e["target"]) for e in all_edges if e.get("relation") == "method"}
    pairs = {(e["source"], e["target"]) for e in all_edges if e.get("relation") == "calls"}
    staged = []
    for result in results:
        pkg = result[FACTS]["package"]
        for rc in result.get("raw_calls", []):
            proof = rc.get("kotlin_constructor_local", {})
            if not proof.get("eligible") or not pkg:
                continue
            name = proof["class"]
            candidates = providers.get((pkg, name), [])
            if (len(candidates) != 1 or namespaces[pkg][name] != 1 or namespaces[pkg]["Boolean"]
                    or name in java_names or "Boolean" in java_names):
                continue
            provider, cls = candidates[0]
            if not cls["eligible"]:
                continue
            members = [m for m in cls["members"] if m["name"] == rc["callee"]]
            if len(members) != 1:
                continue
            owned = [n for n in provider["nodes"] if id(n) in current_nodes and n.get("source_file")]
            classes = [n for n in owned if n.get("label") == name
                       and n.get("source_location") == f'L{cls["line"]}' and n.get("_callable_class")]
            if len(classes) != 1:
                continue
            targets = [n for n in owned if n.get("label") == f'.{rc["callee"]}()'
                       and n.get("source_location") == f'L{members[0]["line"]}'
                       and n.get("source_file") == classes[0].get("source_file")
                       and (classes[0]["id"], n["id"]) in methods]
            if len(targets) != 1:
                continue
            pair = (rc["caller_nid"], targets[0]["id"])
            if pair in pairs or pair[0] == pair[1]:
                continue
            pairs.add(pair)
            staged.append({"source": pair[0], "target": pair[1], "relation": "calls",
                           "context": "call", "confidence": "INFERRED", "confidence_score": 0.85,
                           "source_file": rc.get("source_file", ""),
                           "source_location": rc.get("source_location"), "weight": 0.85})
    all_edges.extend(staged)
    for result in results:
        result[RECEIPT] = True
