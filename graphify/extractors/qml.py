"""Dedicated Qt 6 QML extractor with safe failures and explicit scan roots."""
from __future__ import annotations

from pathlib import Path

from graphify.extractors.qml_ast import QmlInputError, failure, parse_source
from graphify.extractors.qml_declarations import Declarations
from graphify.extractors.qml_facts import FactBuilder


def extract_qml(path: Path, *, root: Path | None = None) -> dict:
    try:
        if root is not None:
            try:
                path.resolve().relative_to(root.resolve())
            except ValueError as exc:
                raise QmlInputError("QML_ROOT", "QML source is outside the explicit scan root") from exc
        source, program, empty = parse_source(path)
        facts = FactBuilder(path, root, source)
        Declarations(facts).extract(program)
        result = {"nodes": facts.nodes, "edges": facts.edges, "diagnostics": []}
        if empty:
            result["diagnostics"].append({"code": "QML_EMPTY", "severity": "info",
                                          "source_file": facts.relative_file,
                                          "owner": "qml", "message": "Empty editor file has no declarations",
                                          "recovery": "Add a component to enable semantic analysis."})
        return result
    except (QmlInputError, ValueError) as exc:
        return failure(path, root, exc)
