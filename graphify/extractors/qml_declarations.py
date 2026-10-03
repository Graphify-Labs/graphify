"""Lexical QML declaration scopes; grouped properties are not instances."""
from __future__ import annotations

from graphify.extractors.qml_facts import FactBuilder, field, make_scope_key, text


class Declarations:
    def __init__(self, facts: FactBuilder):
        self.facts = facts
        self.source = facts.source
        self.objects: list[tuple] = []
        self.members: list[tuple] = []

    def extract(self, program):
        facts = self.facts
        file = facts.add("file", facts.path.name, program, empty=not bool(self.source.strip()))
        singleton = any(child.type == "ui_pragma" and field(child, "name", self.source) == "Singleton"
                        for child in program.named_children)
        for ordinal, syntax in enumerate(program.named_children):
            if syntax.type == "ui_import":
                value = field(syntax, "source", self.source)
                quoted = value[:1] in ("'", '"')
                version = syntax.child_by_field_name("version")
                major = field(version, "major", self.source) if version else ""
                minor = field(version, "minor", self.source) if version else ""
                facts.add("import", value.strip("\"'"), syntax, file,
                          semantic_key=f"import:{ordinal}:{value}",
                          import_kind="script" if quoted and value.strip("\"'").endswith(".js") else "directory" if quoted else "module",
                          value=value.strip("\"'"), qualifier=field(syntax, "alias", self.source) or None,
                          major=int(major) if major else None, minor=int(minor) if minor else None)
            elif syntax.type == "ui_object_definition":
                name = facts.path.name.removesuffix(".ui.qml").removesuffix(".qml")
                component_key = make_scope_key(facts.relative_file, name)
                component = facts.add("component", name, syntax, file,
                                      component_key=component_key, type_name=field(syntax, "type_name", self.source),
                                      singleton=singleton)
                self.object(syntax, component, component_key, "", 0)
        return file

    def object(self, syntax, owner, component_key, parent_scope, ordinal):
        facts = self.facts
        type_name = field(syntax, "type_name", self.source)
        initializer = syntax.child_by_field_name("initializer")
        object_id = ""
        for child in initializer.named_children if initializer else []:
            if child.type == "ui_binding" and field(child, "name", self.source) == "id":
                value = child.child_by_field_name("value")
                if value and value.named_children and value.named_children[0].type == "identifier":
                    object_id = text(value.named_children[0], self.source)
        group = bool(type_name) and type_name.split(".")[0][:1].islower()
        kind = "property_group" if group else "object"
        anchor = f"{component_key}:{parent_scope}:{kind}:{object_id or type_name + ':' + str(ordinal)}"
        scope = make_scope_key(facts.relative_file, anchor)
        node = facts.add(kind, type_name if group else object_id or type_name, syntax, owner,
                         semantic_key=anchor, component_key=component_key,
                         object_scope_key=scope, parent_scope_key=parent_scope,
                         type_name=type_name, object_id=object_id)
        self.objects.append((syntax, node))
        for index, child in enumerate(initializer.named_children if initializer else []):
            if child.type == "ui_object_definition":
                self.object(child, node, component_key, scope, index)
            elif child.type == "ui_inline_component":
                name = field(child, "name", self.source)
                nested_key = make_scope_key(facts.relative_file, f"{component_key}:inline:{name}")
                inline = facts.add("inline_component", name, child, node,
                                   semantic_key=f"{component_key}:inline:{name}", component_key=nested_key,
                                   enclosing_component_key=component_key, parent_scope_key=scope)
                nested = child.child_by_field_name("component")
                if nested:
                    self.object(nested, inline, nested_key, "", 0)
            elif child.type in ("ui_property", "ui_signal", "function_declaration", "enum_declaration"):
                self.member(child, node, component_key, scope)

    def member(self, syntax, owner, component_key, scope):
        facts = self.facts
        kind = {"ui_property": "property", "ui_signal": "signal",
                "function_declaration": "function", "enum_declaration": "enum"}[syntax.type]
        name = field(syntax, "name", self.source)
        parameters = syntax.child_by_field_name("parameters")
        modifiers = [text(c, self.source) for c in syntax.named_children if c.type == "ui_property_modifier"]
        node = facts.add(kind, name, syntax, owner, semantic_key=f"{scope}:{kind}:{name}",
                         component_key=component_key, object_scope_key=scope,
                         parent_scope_key=scope, raw_type=field(syntax, "type", self.source),
                         modifiers=modifiers, signature=text(parameters, self.source),
                         return_type=field(syntax, "return_type", self.source))
        self.members.append((syntax, node))
        value = syntax.child_by_field_name("value")
        if value and value.type == "ui_object_definition":
            self.object(value, node, component_key, scope, 0)
