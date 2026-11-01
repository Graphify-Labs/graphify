"""INC-QML-114: named-scope rejection cannot become a unique-label target."""
from __future__ import annotations

import base64
import json

import pytest

from graphify.build import build_from_json
from graphify.export import to_json
from graphify.paths import load_node_link_graph
from tests.cpp_type_reference_helpers import produce, source, unavailable, uses


@pytest.mark.parametrize("kind", ["class", "alias"])
@pytest.mark.parametrize("mode", ["direct", "facade"])
@pytest.mark.parametrize("newline", ["\n", "\r\n"], ids=["LF", "BOM-CRLF"])
def test_req_qml014_ac03_named_rejection_survives_real_source_and_transport(tmp_path, kind, mode, newline):
    """Actual source lookup rejection persists without poisoning a legitimate parameter use."""
    raw = source(kind, newline=newline)
    result = produce(tmp_path, raw, mode)
    edge, target = uses(result)[0]
    assert not target["source_file"]
    assert edge["cpp_type_reference_version"] == 1
    fact = edge["metadata"]["cpp_type_reference"]
    assert fact["contract_version"] == 1 and fact["resolution"] == "unavailable"
    assert fact["scope_complete"] is True
    name = "Count" if kind == "alias" else "Thing"
    assert base64.b64decode(fact["raw_name_b64"]) == name.encode()
    assert base64.b64decode(fact["lexical_scope_b64"]) == b"Right::Holder"
    span = fact["type_span"]
    assert raw[span["start_byte"]:span["end_byte"]] == name.encode()
    assert raw[:span["start_byte"]].count(b"\n") == span["start_row"]
    assert span["start_column"] == span["start_byte"] - raw.rfind(b"\n", 0, span["start_byte"]) - 1
    parameter = uses(result, "allowed()")
    assert len(parameter) == 1 and "cpp_type_reference_version" not in parameter[0][0]
    if mode == "facade":
        assert parameter[0][1]["source_file"] and parameter[0][1]["id"] != target["id"]
    for directed in (False, True):
        graph = build_from_json(result, root=tmp_path, directed=directed)
        output = tmp_path / f"{directed}.json"
        assert to_json(graph, {}, str(output), force=True)
        restored = load_node_link_graph(json.loads(output.read_text(encoding="utf-8")))
        marked = [data for _, _, data in restored.edges(data=True) if "cpp_type_reference_version" in data]
        assert len(marked) == 1 and marked[0]["metadata"]["cpp_type_reference"] == fact
        assert target["id"] in restored and not restored.nodes[target["id"]]["source_file"]


@pytest.mark.parametrize("kind", ["class", "alias"])
@pytest.mark.parametrize("mode", ["direct", "facade"])
def test_req_qml014_ac03_explicit_qualified_type_remains_positive(tmp_path, kind, mode):
    """The restriction never replaces an accepted exact qualified source target."""
    result = produce(tmp_path, source(kind, qualified=True), mode)
    edge, target = uses(result)[0]
    assert target["source_file"] and "cpp_type_reference_version" not in edge
    assert not unavailable(result)


@pytest.mark.parametrize("kind", ["class", "alias"])
def test_req_qml014_ac03_case_mismatch_does_not_invent_a_literal_rejection(tmp_path, kind):
    """Normalized-ID coincidence cannot create source spelling or rejection authority."""
    result = produce(tmp_path, source(kind, spelling="count" if kind == "alias" else "thing"))
    edge, target = uses(result)[0]
    assert not target["source_file"] and "cpp_type_reference_version" not in edge


@pytest.mark.parametrize("kind", ["class", "alias"])
def test_req_qml014_ac03_crossfile_type_without_known_local_literal_keeps_fallback(tmp_path, kind):
    """An external admitted type is not a failed in-file named-scope lookup."""
    from graphify.extract import extract
    provider, user = tmp_path / "types.hpp", tmp_path / "user.hpp"
    name = "Count" if kind == "alias" else "Thing"
    provider.write_text("using Count=int;\n" if kind == "alias" else "class Thing {};\n", encoding="utf-8")
    user.write_text(f'#include "types.hpp"\nclass Holder{{{name} value;}};\n', encoding="utf-8")
    result = extract([provider, user], root=tmp_path, cache_root=tmp_path, parallel=False)
    edge, target = uses(result)[0]
    assert target["source_file"] == "types.hpp" and "cpp_type_reference_version" not in edge
