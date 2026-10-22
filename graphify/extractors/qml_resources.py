"""Bounded QRC source declarations without DTD/entity expansion or target reads."""
from __future__ import annotations

import posixpath
from pathlib import Path
from xml.parsers import expat

from graphify.extractors.qml_project_read import (
    MetadataError, ProjectFacts, extract_project, failure, literal_path,
)


def resource_url(prefix: str, alias: str) -> str | None:
    """Accept exact portable resource paths; traversal is never normalized away."""
    prefix, alias = prefix.replace("\\", "/"), alias.replace("\\", "/")
    if not alias or alias.startswith("/") or any(char in prefix + alias for char in ":%?#\x00"):
        return None
    joined = prefix.rstrip("/") + "/" + alias
    if any(part in {".", ".."} for part in joined.split("/")):
        return None
    return "qrc:/" + joined.lstrip("/")


def parse_qrc(source: bytes | str, *, relative_file="resources.qrc") -> dict:
    try:
        facts = ProjectFacts(source, relative_file, "qrc")
        parser = expat.ParserCreate("UTF-8")
        parser.SetParamEntityParsing(expat.XML_PARAM_ENTITY_PARSING_NEVER)
        stack, record = [], None
        prefix, locale = "/", ""

        def forbidden(*_args):
            raise MetadataError("QML_QRC_ENTITY", "xml_dtd_or_entity_forbidden")

        def start(name, attributes):
            nonlocal prefix, locale, record
            if len(stack) > 16:
                raise MetadataError("QML_PROJECT_LIMIT", "qrc_depth_limit")
            if name == "RCC" and not stack:
                if set(attributes) - {"version"}:
                    facts.reject("unsupported_qrc_attribute")
            elif name == "qresource" and stack == ["RCC"]:
                if set(attributes) - {"prefix", "lang"}:
                    facts.reject("unsupported_qresource_attribute")
                prefix, locale = attributes.get("prefix", "/"), attributes.get("lang", "")
            elif name == "file" and stack == ["RCC", "qresource"]:
                if set(attributes) - {"alias", "compress", "compression-algorithm", "threshold", "empty"}:
                    facts.reject("unsupported_qrc_file_attribute")
                record = {"start": parser.CurrentByteIndex, "alias": attributes.get("alias"),
                          "parts": [], "empty": attributes.get("empty", "false")}
            else:
                facts.reject("unsupported_qrc_structure")
            stack.append(name)

        def data(value):
            if record is not None and stack == ["RCC", "qresource", "file"]:
                record["parts"].append(value)
            elif value.strip():
                facts.reject("unexpected_qrc_text")

        def close(name):
            nonlocal record
            if name == "file" and record is not None:
                target = "".join(record["parts"]).strip()
                alias = record["alias"] if record["alias"] is not None else target
                logical = resource_url(prefix, alias)
                path = literal_path(relative_file, target)
                end = facts.raw.find(b">", parser.CurrentByteIndex) + 1
                if logical is None or path is None:
                    facts.reject("resource_path_escape_or_invalid_alias", record["start"], end,
                                 code="QML_QRC_PATH")
                elif record["empty"] == "true":
                    facts.reject("empty_resource_has_no_source_content", record["start"], end)
                else:
                    facts.add("resource_alias", (logical, target, locale), logical,
                              record["start"], end, logical_url=logical,
                              target_path=path, value=target, prefix=prefix, alias=alias,
                              locale=locale, origin="qrc", generated=False)
                record = None
            stack.pop()

        parser.StartDoctypeDeclHandler = forbidden
        parser.EntityDeclHandler = forbidden
        parser.ExternalEntityRefHandler = forbidden
        parser.StartElementHandler, parser.EndElementHandler = start, close
        parser.CharacterDataHandler = data
        parser.Parse(facts.raw, True)
        if not facts.raw.strip() or not facts.nodes:
            facts.reject("missing_qrc_root")
        return facts.result()
    except (expat.ExpatError, UnicodeError, ValueError) as exc:
        if isinstance(exc, expat.ExpatError):
            exc = MetadataError("QML_QRC_SYNTAX", "invalid_resource_xml")
        return failure(relative_file, "qrc", exc)


def extract_qrc(path: Path, *, root: Path | None = None) -> dict:
    return extract_project(path, root, "qrc", parse_qrc)
