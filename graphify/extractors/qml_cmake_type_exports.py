"""Literal build-declared QML exports, separate from filenames/resource aliases.

Qt's generated qmldir uses source type-name/version/internal properties before
module creation. This producer records that declaration without running CMake
or claiming a generated qmldir, plugin or QML component actually executed.
"""
from __future__ import annotations

from pathlib import PurePosixPath
import re

QML_TYPE_PROPERTIES = {"QT_QML_SOURCE_TYPENAME", "QT_QML_SOURCE_VERSIONS", "QT_QML_INTERNAL_TYPE"}
_TRUE = {"TRUE", "ON", "1"}
_FALSE = {"FALSE", "OFF", "0", "NO", "N", "IGNORE", "NOTFOUND"}
_NAME = re.compile(r"[A-Z][A-Za-z0-9_]*")
_VERSION = re.compile(r"(\d{1,6})\.(\d{1,6})")


def source_versions(value):
    """One explicit entry per version avoids relying on sanitized display lists."""
    parts = value.split(";")
    if len(parts) > 10_000 or len(set(parts)) != len(parts):
        return None
    result = []
    for part in parts:
        match = _VERSION.fullmatch(part)
        if match is None:
            return None
        result.append((int(match[1]), int(match[2])))
    return result if len(set(result)) == len(result) else None


def valid_type_properties(updates):
    """The admitted subset is flat, literal and uses actual QML component names."""
    name = updates.get("QT_QML_SOURCE_TYPENAME")
    if name is not None and (not _NAME.fullmatch(name) or name in _FALSE or name.endswith("-NOTFOUND")):
        return False
    versions = updates.get("QT_QML_SOURCE_VERSIONS")
    return versions is None or source_versions(versions) is not None


def literal_version_token(token, source):
    """Only a quoted/bracket literal version list may cross the semicolon barrier."""
    if source_versions(token.value) is None:
        return False
    spelling = source[token.start:token.end]
    if spelling == '"' + token.value + '"':
        return True
    bracket = re.fullmatch(r"\[(=*)\[(.*?)\]\1\]", spelling, re.DOTALL)
    return bool(bracket and bracket[2] == token.value)


def export_plan(token, properties, major):
    """A resource alias never changes type identity; internal exports have no version."""
    physical = PurePosixPath(token.value.replace("\\", "/")).name
    default = physical.removesuffix(".ui.qml").removesuffix(".qml")
    name = properties.get("QT_QML_SOURCE_TYPENAME", default)
    internal = properties.get("QT_QML_INTERNAL_TYPE") in _TRUE
    singleton = properties.get("QT_QML_SINGLETON_TYPE") in _TRUE
    if internal and singleton:
        return None
    versions = source_versions(properties["QT_QML_SOURCE_VERSIONS"]) if "QT_QML_SOURCE_VERSIONS" in properties else [(major, 0 if major is not None else None)]
    # Lower-case source files remain admitted resources, but Qt does not emit a
    # public type entry for them. A declared override was validated separately.
    if not _NAME.fullmatch(name):
        versions = []
    elif internal:
        versions = [(None, None)]
    return {"name": name, "versions": versions, "internal": internal, "singleton": singleton}


def source_export_fields(plan):
    """The scalar count makes missing/extra transported export facts detectable."""
    return {"qml_export_contract": 1, "qml_export_name": plan["name"] if plan else "",
            "qml_export_count": len(plan["versions"]) if plan else 0}


def add_type_exports(facts, source, module, key, token, plan):
    """Each export keeps its source declaration, exact version and module owner."""
    if plan is None:
        return
    for major, minor in plan["versions"]:
        facts.add_chars("qt_qml_export", (source["id"], plan["name"], major, minor), plan["name"],
                        token.start, token.end, owner=source, source_id=source["id"],
                        module_id=module["id"], module_key=key, raw_name=plan["name"],
                        major=major, minor=minor, internal=plan["internal"], singleton=plan["singleton"],
                        generated=False, evidence_role="build_declaration")
