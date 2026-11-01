"""Source-role guards and ordered access effects for accepted Qt annotations."""
from __future__ import annotations

import re

ACCESS_RESETS = {"Q_OBJECT", "Q_GADGET", "Q_GADGET_EXPORT"}
EXPORT_ANNOTATIONS = {"Q_GADGET_EXPORT", "Q_NAMESPACE_EXPORT"}
FUNCTION_ANNOTATIONS = {"Q_DECL_NONALLOCATING_FUNCTION", "Q_DECL_NONBLOCKING_FUNCTION"}
_DECLARATIONS = {"declaration", "field_declaration", "function_definition",
                 "parameter_declaration", "optional_parameter_declaration"}
_NAMED = {"class_specifier", "struct_specifier", "enum_specifier", "namespace_definition",
          "alias_declaration", "enumerator"}
_EXPRESSIONS = {"expression_statement", "return_statement", "condition_clause"}


def ordinary_spans(source, tree, *, walk, macro):
    """Protect clean declarator/expression names; parser errors cannot grant roles.

    A Qt marker often parses as a type followed by another marker with a missing
    semicolon. That incomplete declaration is deliberately not ordinary-name
    authority. Conversely, a complete typed member/function may legally share
    any annotation spelling and must retain its original bytes.
    """
    protected, nodes = set(), list(walk(tree))
    declared_types = {source[name.start_byte:name.end_byte] for node in nodes if node.type in _NAMED
                      and (name := node.child_by_field_name("name")) is not None and not name.has_error}
    for node in nodes:
        if node.type not in {"identifier", "field_identifier", "type_identifier", "namespace_identifier"}:
            continue
        token = source[node.start_byte:node.end_byte]
        if not macro.fullmatch(token):
            continue
        owner = node.parent
        while owner and owner.type not in _DECLARATIONS | _NAMED | _EXPRESSIONS:
            owner = owner.parent
        if owner is None or owner.has_error:
            continue
        if owner.type in _NAMED:
            name = owner.child_by_field_name("name")
            ordinary = name is not None and name.start_byte == node.start_byte and name.end_byte == node.end_byte
        elif owner.type in _DECLARATIONS:
            type_node = owner.child_by_field_name("type")
            ordinary = (type_node is not None
                        and (not macro.fullmatch(source[type_node.start_byte:type_node.end_byte])
                             or token in declared_types))
            if type_node is None:
                # Constructors/destructors have no return-type node. Their
                # actual enclosing class name proves the declarator role.
                scope = owner.parent
                while scope and scope.type not in {"class_specifier", "struct_specifier"}:
                    scope = scope.parent
                name = scope.child_by_field_name("name") if scope else None
                ordinary = name is not None and source[name.start_byte:name.end_byte] == token
        else:
            # Actual metadata lives at class/namespace declaration scope, not
            # inside a clean executable expression. SIGNAL/SLOT call payloads
            # remain Qt's separately supported legacy selector mechanism.
            parent = owner.parent
            ordinary = (parent is not None and parent.type not in {"declaration_list", "field_declaration_list"}
                        and token not in {b"SIGNAL", b"SLOT"})
        if ordinary:
            protected.add((node.start_byte, node.end_byte))
    return protected


def _directive_view(code):
    """Only an initial UTF-8 signature is whitespace in directive discovery.

    Three spaces preserve every original offset. A later BOM is not admitted as
    preprocessing whitespace, and neither original source buffer is changed.
    """
    return b"   " + code[3:] if code.startswith(b"\xef\xbb\xbf") else code


def annotation_code(code):
    """Mask complete preprocessing directives, including continued definition lines."""
    result, continued, offset = bytearray(code), False, 0
    for line in _directive_view(code).splitlines(keepends=True):
        directive = continued or line.lstrip().startswith(b"#")
        if directive:
            result[offset:offset + len(line)] = re.sub(rb"[^\r\n]", b" ", line)
        continued = directive and line.rstrip(b"\r\n").endswith(b"\\")
        offset += len(line)
    return bytes(result)


def annotation_overrides(code, macro):
    """A local define/undef defeats SDK spelling authority without preprocessing."""
    overrides = {}
    for match in re.finditer(rb"(?m)^\s*#\s*(?:define|undef)\s+([A-Za-z_]\w*)\b", _directive_view(code)):
        if macro.fullmatch(match[1]):
            overrides.setdefault(match[1].decode(), match.start())
    return overrides


def annotation_scopes(tree, *, walk):
    """Keep declaration versus executable-body ownership independent of text gaps."""
    scopes = []
    for node in walk(tree):
        if node.type in {"class_specifier", "struct_specifier", "namespace_definition",
                         "function_definition", "lambda_expression"}:
            body = node.child_by_field_name("body")
            if body:
                scopes.append((body.start_byte, body.end_byte, node.type))
    return scopes


def valid_annotation_scope(name, offset, scopes):
    """Class and namespace markers cannot create authority from a function body."""
    owners = [item for item in scopes if item[0] <= offset < item[1]]
    scope = min(owners, key=lambda item: item[1] - item[0])[2] if owners else ""
    if name in ACCESS_RESETS or name in {"Q_PROPERTY", "Q_INVOKABLE", "Q_SIGNAL", "Q_SLOT"}:
        return scope in {"class_specifier", "struct_specifier"}
    if name in {"Q_NAMESPACE", "Q_NAMESPACE_EXPORT"}:
        return scope == "namespace_definition"
    if name in {"QML_ELEMENT", "QML_NAMED_ELEMENT", "QML_ANONYMOUS", "QML_SINGLETON"}:
        return scope in {"class_specifier", "struct_specifier", "namespace_definition"}
    return True


def valid_new_annotation(name, args, *, parenthesized):
    """Validate only the newly admitted forms; existing owners validate old ones."""
    if name in EXPORT_ANNOTATIONS:
        return parenthesized and len(args) == 1 and bool(re.fullmatch(r"[A-Za-z_]\w*", args[0]))
    if name == "Q_NAMESPACE" or name in FUNCTION_ANNOTATIONS:
        return not parenthesized
    return True


def class_annotations(unit, syntax, *, walk):
    """Only the innermost class owns a marker; nested declarations cannot reset it."""
    nested = [node for node in walk(syntax) if node != syntax
              and node.type in {"class_specifier", "struct_specifier"}]
    return [item for item in unit.macros if syntax.start_byte <= item["start_byte"] < syntax.end_byte
            and not any(node.start_byte <= item["start_byte"] < node.end_byte for node in nested)]


def member_roles(unit, declaration, syntax, *, walk):
    """Merge actual macro resets with explicit access labels in source order."""
    access = "private" if syntax and syntax.type == "class_specifier" else "public"
    roles = []
    if syntax is None:
        return roles, access
    body = syntax.child_by_field_name("body")
    annotations = class_annotations(unit, syntax, walk=walk)
    events = [(item["start_byte"], "reset", item) for item in annotations
              if item["name"] in ACCESS_RESETS and item["start_byte"] < declaration.start_byte]
    previous = syntax.start_byte
    for child in body.named_children if body else ():
        if child.start_byte >= declaration.start_byte:
            break
        if child.type == "access_specifier":
            events.append((child.start_byte, "access", child))
        previous = max(previous, child.end_byte)
    for _, kind, value in sorted(events, key=lambda item: item[0]):
        if kind == "reset":
            access, roles = "private", []
            continue
        literal = unit.code[value.start_byte:value.end_byte].decode().strip()
        access = "private" if "private" in literal else "protected" if "protected" in literal else "public"
        colon = unit.code.find(b":", value.end_byte)
        section = unit.code[value.start_byte:colon + 1].decode() if colon >= 0 else literal
        roles = (["signal"] if re.search(r"\b(?:signals|Q_SIGNALS)\b", section) else
                 ["slot"] if re.search(r"\b(?:slots|Q_SLOTS)\b", section) else [])
    prefixes = {item["name"] for item in annotations
                if previous <= item["start_byte"] and item["end_byte"] <= declaration.start_byte}
    roles.extend(role for name, role in [("Q_SIGNAL", "signal"), ("Q_SLOT", "slot"), ("Q_INVOKABLE", "invokable")]
                 if name in prefixes)
    return sorted(set(roles)), access


def add_namespace_annotations(mapping, facts, *, walk):
    """Record namespace markers without synthesizing a canonical native owner."""
    unit = mapping.unit
    namespaces = [node for node in walk(unit.tree) if node.type == "namespace_definition"]
    for macro in unit.macros:
        if macro["name"] not in {"Q_NAMESPACE", "Q_NAMESPACE_EXPORT"}:
            continue
        owners = [node for node in namespaces if node.start_byte <= macro["start_byte"] < node.end_byte]
        if not owners:
            continue
        owner = min(owners, key=lambda node: node.end_byte - node.start_byte)
        # A class nested in a namespace cannot grant namespace annotation roles.
        if mapping.class_at(macro["start_byte"]) is not None:
            continue
        name = unit.field(owner, "name")
        # Namespace blocks can be nested or use compact N::M syntax. Preserve
        # actual lexical qualification without treating it as a native target.
        parts, parent = [name], owner.parent
        while parent:
            if parent.type == "namespace_definition":
                parts.append(unit.field(parent, "name"))
            parent = parent.parent
        qualified = "::".join(reversed(parts)) if all(parts) else ""
        facts.add("namespace", name, macro["span"], status="source_only", source_q_namespace=True,
                  qualified_name=qualified, namespace_identity_status="named" if qualified else "anonymous",
                  annotation=macro["name"], export_macro=macro["args"][0] if macro["args"] else "",
                  namespace_span={"start_byte": owner.start_byte, "end_byte": owner.end_byte})
