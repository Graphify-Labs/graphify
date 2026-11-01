"""INC-QML-104: legacy type constness remains raw, typed tooling evidence."""
from copy import deepcopy
import json

import pytest

from graphify.build import build_from_json
from graphify.export import to_json
from graphify.extract import extract
from graphify.extractors.qml_types import extract_qmltypes, parse_qmltypes
from graphify.paths import load_node_link_graph
from graphify.qt_project_index import QtProjectIndex
from graphify.security import sanitize_metadata
from tests.qml_types_legacy_helpers import OWNERS, constants, field_owner, graph_payload, module, point, records


@pytest.mark.parametrize("owner", OWNERS)
@pytest.mark.parametrize("value", [True, False])
@pytest.mark.parametrize("bom,newline", [("", "\n"), ("\ufeff", "\r\n")])
def test_req_qml022_ac04_legacy_type_constant_preserves_owner_value_and_bytes(tmp_path, owner, value, bom, newline):
    """All five generator owners survive direct/cold/warm/sanitized/durable paths."""
    literal = str(value).lower()
    raw = (bom + module(owner, literal)).replace("\n", newline).encode()
    path = tmp_path / "plugins.qmltypes"
    path.write_bytes(raw)
    direct = extract_qmltypes(path, root=tmp_path)
    assert not direct.get("error"), direct.get("qml_failures")
    (field, fact), = constants(direct)
    assert fact["value"] is value and fact["generated"] is True
    owner_fact = field_owner(direct, field)
    assert owner_fact["kind"] == ("qmltypes_parameter" if owner == "Parameter" else "qmltypes_member")
    assert f"isConstant: {literal}".encode() in raw[fact["span"]["start_byte"]:fact["span"]["end_byte"]]
    if owner != "Parameter":
        assert owner_fact["member_kind"] == owner.lower()
    for node in direct["nodes"]:
        metadata = node["metadata"]["qml"]
        span = metadata["span"]
        for prefix in ("start", "end"):
            assert point(raw, span[prefix + "_byte"]) == (span[prefix + "_row"], span[prefix + "_column"])
    seen = []
    for phase in ("cold", "warm"):
        result = extract([path], root=tmp_path, cache_root=tmp_path / "cache", parallel=False)
        assert not result["failed_sources"] and not result["qml_failures"]
        payload = json.loads(json.dumps(result))
        for item in payload["nodes"] + payload["edges"]:
            item["metadata"] = sanitize_metadata(item.get("metadata", {}))
        assert [md for _, md in constants(payload)] == [fact]
        assert field_owner(payload, constants(payload)[0][0]) == owner_fact
        graph = build_from_json(payload, root=tmp_path, directed=True)
        output = tmp_path / (phase + ".json")
        assert to_json(graph, {}, str(output), force=True)
        durable = load_node_link_graph(json.loads(output.read_text(encoding="utf-8")))
        (persisted, metadata), = constants(graph_payload(durable))
        assert metadata == fact
        assert field_owner(graph_payload(durable), persisted) == owner_fact
        seen.append(persisted["id"])
    assert seen[0] == seen[1]
    assert not list((tmp_path / "cache/graphify-out/cache/ast").rglob("*.json"))


def test_req_qml022_ac04_legacy_constant_is_not_modern_member_constant():
    """Old ambiguous spelling cannot acquire modern method/property semantics."""
    result = parse_qmltypes(module(extra="isTypeConstant: false; isMethodConstant: false"))
    assert not result.get("error")
    values = {metadata["field_name"]: metadata["value"] for _, metadata in records(result, "qmltypes_field")}
    assert values["isConstant"] is True and values["isTypeConstant"] is False and values["isMethodConstant"] is False
    property_result = parse_qmltypes(module("Property", extra='write: "set"; notify: "changed"; isReadonly: false'))
    assert not property_result.get("error")
    assert records(property_result, "qmltypes_member")[0][1]["readonly"] is False
    for extra in ('write: "set"', 'notify: "changed"', 'isReadonly: false'):
        rejected = parse_qmltypes(module("Property", extra="isPropertyConstant: true; " + extra))
        assert rejected["nodes"] == []
        assert rejected["qml_failures"][0]["reason"] == "conflicting_constant_property_fields"


@pytest.mark.parametrize("owner", OWNERS)
@pytest.mark.parametrize("value", ['1', '"true"', 'null', '[true]'])
def test_req_qml022_ac04_legacy_constant_rejects_nonboolean_values(owner, value):
    """Literal truthiness never substitutes for the source boolean contract."""
    result = parse_qmltypes(module(owner, value))
    assert result["nodes"] == [] and result["edges"] == []
    assert result["qml_failures"][0]["code"] == "QML_TYPES_UNSUPPORTED"


# Owner/duplicate roles provide durable IDs even when pytest shortens source values.
@pytest.mark.parametrize("source", [
    'Module { isConstant: true }',
    'Module { Component { name: "Wrong"; isConstant: true } }',
    module(extra="isConstant: false"),
    module("Parameter", extra="isMethodConstant: true"),
], ids=["module-owner", "component-owner", "duplicate-member-constant", "parameter-method-constant"])
def test_req_qml022_ac04_legacy_constant_rejects_wrong_owners_and_duplicates(source):
    """Shared type ownership does not admit flags on modules/components or repeated keys."""
    result = parse_qmltypes(source)
    assert result["nodes"] == [] and result["edges"] == []
    assert result["qml_failures"][0]["code"] == "QML_TYPES_UNSUPPORTED"


def test_req_qml022_ac04_legacy_constant_tooling_cannot_authorize_native_reads(tmp_path, monkeypatch):
    """Even exported QObject-shaped hints retain source-only tooling authority."""
    path = tmp_path / "plugins.qmltypes"
    path.write_bytes(module().encode())
    original_open = type(path).open

    def admitted_only(open_path, *args, **kwargs):
        assert open_path == path, "tooling file hints cannot authorize corpus discovery"
        return original_open(open_path, *args, **kwargs)

    monkeypatch.setattr(type(path), "open", admitted_only)
    result = extract_qmltypes(path, root=tmp_path)
    assert not result.get("error")
    before = deepcopy(result)
    index = QtProjectIndex(result["nodes"], result["edges"], root=tmp_path)
    assert index.resolve_component("Public.Legacy", "Widget").target_id is None
    assert result == before
    assert not any("qt" in node.get("metadata", {}) for node in result["nodes"])
