"""Source-owned QML bindings, subscriptions and JS use sites; never raw_calls."""
from __future__ import annotations

import hashlib

from graphify.extractors.qml_facts import field, qml_metadata
from graphify.extractors.qml_literals import literal_fields
from graphify.extractors.qml_js_scopes import FUNCTIONS, bound_names, hoisted_names, local_declarations, qualified_name, reassigned_names


class ExpressionCollector:
    """Every occurrence has its own owner/span so simple graph edges cannot collide."""

    def __init__(self, facts):
        self.facts, self.source = facts, facts.source
        self.functions = {}

    def add(self, kind, syntax, owner, name, **values):
        md = qml_metadata(owner)
        key = hashlib.sha256(f'{owner["id"]}:{kind}:{syntax.start_byte}:{syntax.end_byte}'.encode()).hexdigest()
        node = self.facts.add(kind, name, syntax, owner, semantic_key=key,
                              component_key=md.get("component_key", ""),
                              object_scope_key=md.get("object_scope_key", ""),
                              owner_id=owner["id"], script_file=md.get("script_file", ""), **values)
        # Generic global-label resolution must not mistake an occurrence/local
        # function for a shared JavaScript definition. This scoped resolver owns it.
        node["label"] = f"QML site: {kind} {name}"
        return node

    def function(self, syntax, owner, name):
        key = syntax.start_byte, owner["id"]
        if key not in self.functions:
            self.functions[key] = self.add("js_function", syntax, owner, name)
        return self.functions[key]

    def function_body(self, syntax, owner, environment=None):
        body = syntax.child_by_field_name("body")
        env = dict(environment or {})
        env.update({name: "" for name in bound_names(syntax.child_by_field_name("parameters")
                    or syntax.child_by_field_name("parameter"), self.source)})
        env.update({name: "" for name in hoisted_names(body, self.source)})
        name = field(syntax, "name", self.source)
        if name:
            env[name] = owner["id"]
        self.scan(body, owner, env)

    def scan(self, syntax, owner, environment=None):
        if syntax is None:
            return
        env = dict(environment or {})
        kind = syntax.type
        if kind == "statement_block":
            for name, function in local_declarations(syntax, self.source):
                env[name] = self.function(function, owner, name)["id"] if function else ""
            for name in reassigned_names(syntax, self.source):
                if name in env:
                    env[name] = ""
        if kind in {"for_statement", "for_in_statement"}:
            for child in syntax.named_children:
                if child.type == "lexical_declaration":
                    for declaration in child.named_children:
                        env.update({name: "" for name in bound_names(declaration.child_by_field_name("name"), self.source)})
        if kind == "for_in_statement":
            if syntax.child_by_field_name("kind") is not None:
                env.update({name: "" for name in bound_names(syntax.child_by_field_name("left"), self.source)})
            self.scan(syntax.child_by_field_name("right"), owner, env)
            self.scan(syntax.child_by_field_name("body"), owner, env)
            return
        if kind in FUNCTIONS:
            name = field(syntax, "name", self.source) or "anonymous"
            function = self.function(syntax, owner, name)
            self.function_body(syntax, function, env)
            return
        if kind in {"variable_declarator", "required_parameter", "optional_parameter"}:
            self.scan(syntax.child_by_field_name("value"), owner, env)
            return
        if kind == "catch_clause":
            env.update({name: "" for name in bound_names(syntax.child_by_field_name("parameter"), self.source)})
        if kind == "call_expression":
            callee = syntax.child_by_field_name("function")
            self.use("call", callee, syntax, owner, env)
            if qualified_name(callee, self.source) is None:
                self.scan(callee, owner, env)
            for argument in (syntax.child_by_field_name("arguments").named_children
                             if syntax.child_by_field_name("arguments") else []):
                self.scan(argument, owner, env)
            return
        if kind in {"member_expression", "subscript_expression"}:
            self.use("read", syntax, syntax, owner, env)
            if qualified_name(syntax.child_by_field_name("object"), self.source) is None:
                self.scan(syntax.child_by_field_name("object"), owner, env)
            if kind == "subscript_expression":
                self.scan(syntax.child_by_field_name("index"), owner, env)
            return
        if kind in {"identifier", "shorthand_property_identifier"}:
            self.use("read", syntax, syntax, owner, env)
            return
        if kind in {"assignment_expression", "augmented_assignment_expression"}:
            left = syntax.child_by_field_name("left")
            if kind == "augmented_assignment_expression":
                self.scan(left, owner, env)
            elif left and left.type in {"member_expression", "subscript_expression"}:
                # Computing a write address reads its receiver/index; it does
                # not read the property value being overwritten.
                self.scan(left.child_by_field_name("object"), owner, env)
                self.scan(left.child_by_field_name("index"), owner, env)
            self.scan(syntax.child_by_field_name("right"), owner, env)
            return
        if kind in {"comment", "string", "type_annotation", "type_identifier", "ui_object_definition", "ui_object_initializer"}:
            return
        for child in syntax.named_children:
            self.scan(child, owner, env)

    def use(self, kind, target, syntax, owner, env):
        reference = qualified_name(target, self.source)
        first = (reference or "").split(".")[0]
        self.add(kind, syntax, owner, reference or "dynamic", reference=reference or "",
                 lexical_names=sorted(env)[:50], lexical_shadowed=first in env,
                 lexical_target_id=env.get(first, "") if reference == first else "",
                 status="dynamic" if reference is None else "pending",
                 reason="computed_or_runtime_target" if reference is None else "")


def _connection_target(syntax, source):
    initializer = syntax.child_by_field_name("initializer")
    for child in initializer.named_children if initializer else []:
        if child.type == "ui_binding" and field(child, "name", source) == "target":
            value = child.child_by_field_name("value")
            value = value.named_children[0] if value and value.type == "expression_statement" else value
            return qualified_name(value, source) or "", True
    return "", False


def _signal_parameters(declarations, owner, signal_name, connection_target):
    """Source-declared implicit signal parameters participate in JS shadowing."""
    md = qml_metadata(owner)
    scope = md.get("object_scope_key")
    if connection_target:
        objects = [node for _, node in declarations.objects if qml_metadata(node).get("object_id") == connection_target
                   and qml_metadata(node).get("component_key") == md.get("component_key")]
        scope = qml_metadata(objects[0]).get("object_scope_key") if len(objects) == 1 else None
    for syntax, node in declarations.members:
        member = qml_metadata(node)
        if member.get("kind") == "signal" and member.get("raw_name") == signal_name and member.get("object_scope_key") == scope:
            parameters = syntax.child_by_field_name("parameters")
            return {field(p, "name", declarations.source): "" for p in parameters.named_children} if parameters else {}
    return {}


def collect_relationships(declarations) -> None:
    """Collect facts only; project lookup is a separate run-scoped resolver."""
    collector = ExpressionCollector(declarations.facts)
    members = {(qml_metadata(node).get("object_scope_key"), qml_metadata(node)["raw_name"]): node
               for _, node in declarations.members}
    objects = {node["id"]: syntax for syntax, node in declarations.objects}
    owners = {qml_metadata(node).get("object_scope_key"): node for _, node in declarations.objects}
    for syntax, owner in declarations.objects:
        initializer = syntax.child_by_field_name("initializer")
        for child in initializer.named_children if initializer else []:
            if child.type != "ui_binding" or field(child, "name", collector.source) == "id":
                continue
            name, value = field(child, "name", collector.source), child.child_by_field_name("value")
            if value is None or value.type in {"ui_object_definition", "ui_object_array"}:
                continue
            short = name.split(".")[-1]
            if short.startswith("on") and len(short) > 2 and short[2].isupper():
                _handler(declarations, collector, child, owner, name, value, syntax)
            else:
                member = members.get((qml_metadata(owner).get("object_scope_key"), name), owner)
                binding = collector.add("binding", child, member, name, reference=name, **literal_fields(value, collector.source))
                collector.scan(value, binding)
    for syntax, member in declarations.members:
        md = qml_metadata(member)
        owner = owners.get(md.get("object_scope_key"), member)
        name = md["raw_name"]
        if md["kind"] == "property":
            value = syntax.child_by_field_name("value")
            if value is None or value.type == "ui_object_definition":
                continue
            if md.get("raw_type") == "alias":
                expression = value.named_children[0] if value.type == "expression_statement" and value.named_children else value
                reference = qualified_name(expression, collector.source)
                collector.add("alias", value, member, name, reference=reference or "",
                              status="pending" if reference else "dynamic", reason="" if reference else "alias_not_static")
            else:
                binding = collector.add("binding", value, member, name, **literal_fields(value, collector.source))
                collector.scan(value, binding)
        elif md["kind"] == "function":
            if qml_metadata(owner).get("type_name") == "Connections" and name.startswith("on"):
                _handler(declarations, collector, syntax, owner, name, syntax.child_by_field_name("body"), objects[owner["id"]], syntax)
            else:
                collector.function_body(syntax, member)


def _handler(declarations, collector, syntax, owner, name, body, object_syntax, function=None):
    short = name.split(".")[-1]
    signal = short[2:3].lower() + short[3:]
    connections = qml_metadata(owner).get("type_name") == "Connections"
    target, supplied = _connection_target(object_syntax, collector.source) if connections else ("", False)
    initializer = object_syntax.child_by_field_name("initializer")
    legacy = any(child.type == "ui_binding" and field(child, "name", collector.source).startswith("on")
                 and field(child, "name", collector.source)[2:3].isupper()
                 for child in initializer.named_children) if initializer else False
    # Only legacy code blocks inherit signal declaration names. Function and
    # arrow handlers bind their own formals, which need not use those names.
    implicit_parameters = function is None and body is not None and body.type == "statement_block"
    handler = collector.add("handler", syntax, owner, name, reference=signal,
                            connection_target=target, connection_supplied=supplied,
                            connections=connections, attached_prefix=name[:-len(short)].rstrip("."),
                            implicit_parameters=implicit_parameters,
                            disabled_reason="connections_mixed_handler_styles" if connections and function and legacy else "")
    env = _signal_parameters(declarations, owner, signal, target) if implicit_parameters else {}
    if function:
        collector.function_body(function, handler, env)
    else:
        collector.scan(body, handler, env)
