"""Narrow source-backed exceptions to generic cross-language phantom guards."""
from pathlib import Path


def allows_qml_script_edge(source: dict, target: dict, edge: dict) -> bool:
    """Only dedicated QML sites can bridge to an accepted JavaScript resource.

    A context string or matching label alone is insufficient. The ordinary
    generic JS graph remains independent from the QML script overlay.
    """
    source_qml = source.get("metadata", {}).get("qml", {})
    target_qml = target.get("metadata", {}).get("qml", {})
    if source_qml.get("contract_version") != 1 or edge.get("confidence") != "INFERRED":
        return False
    if Path(source.get("source_file") or "").suffix.lower() not in {".qml", ".js", ".mjs"}:
        return False
    if Path(target.get("source_file") or "").suffix.lower() not in {".js", ".mjs"}:
        return False
    if edge.get("relation") == "imports":
        return (source_qml.get("kind") == "import_resolution" and target.get("type") == "file"
                and edge.get("context") == "qml_import_resolution")
    if edge.get("relation") == "calls":
        return (source_qml.get("kind") == "call" and target_qml.get("kind") == "qml_script_function"
                and target_qml.get("contract_version") == 1 and edge.get("context") == "qml_script_call")
    return False
