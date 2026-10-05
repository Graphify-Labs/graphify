"""Accepted AST type shadows for the bounded constructor QObject signature.

File facts retain literal includes and namespace/class shadows before canonical
joins. The corpus lookup consumes only admitted nodes; it discovers no files,
opens no headers and does not emulate preprocessing or resolve alias targets.
"""
from __future__ import annotations

import base64
import binascii
import posixpath
import re

from graphify.extractors.base import _read_text
from graphify.extractors.cpp_identity import lexical_scope


def _walk(root):
    pending = [root]
    while pending:
        node = pending.pop()
        yield node
        pending.extend(reversed(node.named_children))


def _encode(value):
    return base64.b64encode(value.encode()).decode()


def _decode(value):
    if not isinstance(value, str) or len(value) > 480:
        return None
    try:
        decoded = base64.b64decode(value, validate=True).decode("utf-8")
    except (ValueError, UnicodeError, binascii.Error):
        return None
    return decoded if len(decoded.encode()) <= 360 else None


def source_facts(root, source, nodes, path):
    """The direct generic producer owns the transport, not the Qt facade."""
    from graphify.extractors.cpp_constructors import _span
    files = [node for node in nodes if node.get("source_file") == str(path)
             and node.get("source_location") == "L1" and node.get("label") == path.name
             and not node.get("_callable") and not node.get("_callable_class")]
    if len(files) != 1:
        return
    shadows, includes, complete = [], [], not root.has_error
    for syntax in _walk(root):
        if syntax.type == "preproc_include":
            literal = _read_text(syntax.child_by_field_name("path"), source)
            kind = "quoted" if literal.startswith('"') and literal.endswith('"') else "angle" if literal.startswith("<") and literal.endswith(">") else ""
            if kind:
                value = literal[1:-1]
                if (not value or len(value.encode()) > 360 or "\\" in value or ":" in value
                        or value.startswith("/") or "\0" in value or kind == "angle" and ".." in value.split("/")):
                    complete = False
                else:
                    includes.append({"literal_b64": _encode(value), "kind": kind,
                                     "end_byte": syntax.end_byte, "span": _span(syntax)})
            else:
                complete = False
            continue
        if syntax.type not in {"alias_declaration", "type_definition", "using_declaration", "class_specifier", "struct_specifier"}:
            continue
        names = syntax.children_by_field_name("declarator") if syntax.type == "type_definition" else [
            syntax.child_by_field_name("name")]
        if syntax.type == "using_declaration":
            literal = _read_text(syntax, source).removeprefix("using").strip().removesuffix(";").strip()
            names = []
            if literal.startswith("namespace "):
                complete = False  # A namespace import may supply an unseen alias.
            elif literal.rsplit("::", 1)[-1] == "QObject":
                names = [syntax]
        for name in names:
            leaf = name
            while leaf and leaf.type not in {"identifier", "type_identifier", "using_declaration"}:
                leaf = leaf.child_by_field_name("declarator") or next(iter(leaf.named_children), None)
            spelling = _read_text(leaf, source) if leaf else ""
            if spelling != "QObject" and not (leaf and leaf.type == "using_declaration"):
                continue
            scope = lexical_scope(syntax, source)
            ancestor = syntax.parent
            while ancestor and ancestor.type not in {"function_definition", "lambda_expression", "translation_unit"}:
                ancestor = ancestor.parent
            if ancestor and ancestor.type in {"function_definition", "lambda_expression"}:
                continue  # A body-local type cannot shadow its constructor parameter clause.
            if scope is None or len(scope.encode()) > 360:
                complete = False
            else:
                parent = syntax.parent
                while parent and parent.type not in {"class_specifier", "struct_specifier", "namespace_definition", "translation_unit"}:
                    parent = parent.parent
                shadows.append({"scope_b64": _encode(scope), "start_byte": syntax.start_byte,
                                "class_scope": bool(parent and parent.type in {"class_specifier", "struct_specifier"}),
                                "span": _span(syntax)})
    if len(includes) > 50 or len(shadows) > 50:
        complete = False
    metadata = dict(files[0].get("metadata") or {})
    metadata["cpp_constructor_types"] = {"contract_version": 1, "complete": complete, "source_size": len(source),
                                           "includes": includes[:50], "shadows": shadows[:50]}
    files[0]["metadata"] = metadata


def valid_source_transport(value):
    """Validate file transport without granting its incomplete record type authority.

    Both constructor joins and Qt file-role consumers use the same immutable,
    bounded include/shadow validation. This predicate reads only accepted facts.
    """
    if (not isinstance(value, dict) or type(value.get("contract_version")) is not int
            or value["contract_version"] != 1 or type(value.get("complete")) is not bool
            or type(value.get("source_size")) is not int or value["source_size"] < 0):
        return False
    for key in ("includes", "shadows"):
        values = value.get(key)
        if not isinstance(values, list) or len(values) > 50:
            return False
        for item in values:
            text_key, byte_key = ("literal_b64", "end_byte") if key == "includes" else ("scope_b64", "start_byte")
            if (not isinstance(item, dict) or _decode(item.get(text_key)) is None
                    or type(item.get(byte_key)) is not int or item[byte_key] < 0):
                return False
            span = item.get("span")
            if (not isinstance(span, dict) or any(type(span.get(field)) is not int or span[field] < 0
                    for field in ("start_byte", "end_byte", "start_row", "end_row", "start_column", "end_column"))
                    or not span["start_byte"] < span["end_byte"] <= value["source_size"]
                    or span["start_row"] > span["end_row"] or item[byte_key] != span[byte_key]
                    or (span["start_row"] == span["end_row"]
                        and span["end_column"] - span["start_column"] != span["end_byte"] - span["start_byte"])):
                return False
            text = _decode(item[text_key])
            if key == "shadows" and text and not all(part.isidentifier() for part in text.split("::")):
                return False
            if key == "shadows" and type(item.get("class_scope")) is not bool:
                return False
            if key == "includes" and (not text or "\\" in text or ":" in text or text.startswith("/") or "\0" in text
                    or item.get("kind") not in {"quoted", "angle"}
                    or item["kind"] == "angle" and ".." in text.split("/")):
                return False
    return True


class ConstructorTypeAuthority:
    """Immutable admitted-source inventory; bounded conservative include walk."""

    def __init__(self, nodes):
        self.files = {}
        for node in nodes:
            if node.get("source_file") and not node.get("_callable") and not node.get("_callable_class"):
                file = self._file(node["source_file"])
                metadata = node.get("metadata")
                if (isinstance(metadata, dict) and "cpp_constructor_types" in metadata
                        or node.get("source_location") == "L1" and node.get("label") == posixpath.basename(file)):
                    self.files.setdefault(self._file(node["source_file"]), []).append(node)

    @staticmethod
    def _file(value):
        return posixpath.normpath(str(value).replace("\\", "/"))

    def _source_record(self, file):
        """File bounds remain usable when include/type proof is conservatively incomplete."""
        found = self.files.get(file, ())
        if len(found) != 1:
            return None
        node = found[0]
        metadata = node.get("metadata")
        value = metadata.get("cpp_constructor_types") if isinstance(metadata, dict) else None
        if (not isinstance(value, dict) or type(value.get("contract_version")) is not int
                or value["contract_version"] != 1 or type(value.get("complete")) is not bool
                or type(value.get("source_size")) is not int or value["source_size"] < 0
                or node.get("source_location") != "L1" or node.get("label") != posixpath.basename(file)
                or node.get("file_type") != "code" or node.get("_origin") not in {None, "ast"}):
            return None
        return value

    def source_span_authorized(self, node, fact):
        """Transported class/constructor spans must stay inside one admitted original file."""
        record = self._source_record(self._file(node.get("source_file", "")))
        span = fact.get("span")
        fields = ("start_byte", "end_byte", "start_row", "end_row", "start_column", "end_column")
        return bool(record is not None and isinstance(span, dict)
                    and all(type(span.get(field)) is int and 0 <= span[field] <= record["source_size"]
                            for field in fields)
                    and span["start_byte"] < span["end_byte"]
                    and (span["start_row"], span["start_column"]) <= (span["end_row"], span["end_column"]))

    def _fact(self, file):
        value = self._source_record(file)
        if value is None or value["complete"] is not True:
            return None
        return value if valid_source_transport(value) else None

    def authorized(self, node, fact):
        if not self.source_span_authorized(node, fact):
            return False
        encoded = fact.get("signature_b64", "")
        payload = _decode(encoded)
        if payload is None or not re.search(r"(?<![:\w])QObject(?!\w)", payload):
            return payload is not None
        owner = _decode(fact.get("owner_b64"))
        if owner is None:
            return False
        scopes = {"::".join(owner.split("::")[:end]) for end in range(len(owner.split("::")) + 1)}
        current = self._file(node["source_file"])
        pending, seen = [(current, fact["span"]["start_byte"])], set()
        while pending:
            file, position = pending.pop()
            if file in seen:
                continue
            seen.add(file)
            if len(seen) > 128 or (record := self._fact(file)) is None:
                return False
            if any(_decode(item["scope_b64"]) in scopes and (item["class_scope"] or item["start_byte"] <= position)
                   for item in record["shadows"]):
                return False
            for include in record["includes"]:
                if include["end_byte"] > position:
                    continue
                literal = _decode(include["literal_b64"])
                if not literal:
                    return False
                if include["kind"] == "angle":
                    # Configured compiler include search is unavailable here.
                    # Any admitted suffix candidate could supply a source alias,
                    # even when its transport is missing, corrupt or duplicated.
                    suffix = posixpath.normpath(literal).casefold()
                    if any(candidate.casefold() == suffix or candidate.casefold().endswith("/" + suffix)
                           for candidate in self.files):
                        return False
                    continue  # An unavailable external SDK header grants no new source shadow.
                target = posixpath.normpath(posixpath.join(posixpath.dirname(file), literal))
                if target not in self.files:
                    return False  # Missing quoted source cannot establish type identity.
                pending.append((target, 2**63 - 1))
        return True
