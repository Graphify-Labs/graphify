"""Conventional file-wide inclusion guards in the static C++ source profile.

This predicate recognizes source admission syntax, not a compiler environment.
Feature branches and unfamiliar layouts remain conditional. No preprocessor,
external define, additional header or project script is evaluated.
"""
from __future__ import annotations


class IncludeGuardIndex:
    """One immutable syntax tree owns its already validated guard identities.

    Consumers may check every local declaration without rescanning a whole
    guarded file. No global cache or cross-tree spelling can lend authority.
    """

    def __init__(self, root):
        self.root = root
        self.guards = {node.id: node for node in root.named_children if is_include_guard(node)}

    def accepts(self, node):
        accepted = self.guards.get(node.id)
        return accepted is not None and accepted == node and node.parent == self.root


def is_include_guard(node):
    """Recognize only a whole-file #ifndef with a matching first plain define."""
    if node.type != "preproc_ifdef" or node.parent is None or node.parent.type != "translation_unit":
        return False
    children = node.children
    if (not children or children[0].type != "#ifndef" or children[-1].type != "#endif"
            or children[0].is_missing or children[-1].is_missing):
        return False
    name = node.child_by_field_name("name")
    if name is None or name.is_missing:
        return False
    body = [child for child in node.named_children if child != name and child.type != "comment"]
    if not body or body[0].type != "preproc_def":
        return False
    defined = body[0].child_by_field_name("name")
    value = body[0].child_by_field_name("value")
    if (defined is None or defined.text != name.text
            or (value is not None and value.text.strip() not in {b"", b"1"})
            or any(child.type in {"preproc_else", "preproc_elif", "preproc_elifdef"} for child in body)):
        return False
    # A conventional guard owns one definition for this whole file. Later
    # writes, even inside an unknown feature branch, defeat that source profile.
    # Walk the immutable tree without compiler evaluation or an ambient cache;
    # a define embedded in a string/comment is not a preprocessor declaration.
    pending = list(node.named_children)
    while pending:
        nested = pending.pop()
        if nested.type in {"preproc_def", "preproc_function_def"} and nested != body[0]:
            symbol = nested.child_by_field_name("name")
            if symbol is not None and symbol.text == name.text:
                return False
        elif nested.type == "preproc_call":
            directive = nested.child_by_field_name("directive")
            argument = nested.child_by_field_name("argument")
            if (directive is not None and directive.text.removeprefix(b"#").strip() == b"undef"
                    and argument is not None and argument.text.strip() == name.text):
                return False
        pending.extend(nested.named_children)
    # Includes/comments and pragma-once may surround a conventional guard, but
    # another declaration or definition cannot borrow its inclusion identity.
    for sibling in node.parent.named_children:
        if sibling == node or sibling.type in {"comment", "preproc_include"}:
            continue
        if sibling.type == "preproc_call" and sibling.text.strip() == b"#pragma once":
            continue
        return False
    return True
