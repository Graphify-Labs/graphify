"""Qt/QML HTML fields borrow complete contracts and project readable semantics."""
from __future__ import annotations

import json

from graphify.qt_qml_search import SEARCH_NAMESPACE, search_attributes
from graphify.qt_relationship_views import relationship_label
from graphify.security import sanitize_label


def semantic_fields(data):
    metadata = data.get("metadata")
    if not isinstance(metadata, dict) or not any(isinstance(metadata.get(name), dict)
            and type(metadata[name].get("contract_version")) is int
            and metadata[name]["contract_version"] == 1 for name in ("qml", "qt")):
        return {}
    # The encoder reads these dictionaries only. Existing attributes, including
    # an occupied public search namespace, retain their authoritative values.
    attributes = search_attributes(data)
    fields = {"metadata": metadata, "attributes": attributes,
              "source_location": str(data.get("source_location") or "")}
    original = data.get("attributes")
    if SEARCH_NAMESPACE in attributes and not (isinstance(original, dict) and SEARCH_NAMESPACE in original):
        fields["qt_qml"] = attributes[SEARCH_NAMESPACE]
    return fields


def semantic_title(fields):
    value = fields.get("qt_qml")
    return "\n" + sanitize_label(json.dumps(value, ensure_ascii=False)) if value else ""


def edge_fields(data):
    fields = semantic_fields(data)
    if fields:
        fields.update(context=data.get("context", ""), source_file=data.get("source_file", ""))
    return fields


def edge_title(data):
    label = relationship_label(data)
    if not label:
        return ""
    source = str(data.get("source_file") or "") + ":" + str(data.get("source_location") or "")
    return sanitize_label(" — " + label + " at " + source)
