"""INC-QML-111: constructor-owned IDs never turn literal field data callable."""
import json

import pytest

from graphify.build import build_from_json
from graphify.export import to_json
from graphify.extract import extract_cpp
from graphify.extractors.base import _make_id
from graphify.extractors.cpp_constructors import _fact
from graphify.extractors.qt_cpp_facts import qt_metadata
from graphify.paths import load_node_link_graph
from tests.cpp_member_name_helpers import facade, owned, owner_node, project, span


def constructor_field(root, *, field_first=False, overload=False, parameter="int value", native=False):
    """Derive a real colliding literal from actual producer signature proof."""
    marker = "Q_OBJECT QML_NAMED_ELEMENT(CaseOwner) " if native else ""
    base = ":public QObject" if native else ""
    constructor = f"Panel({parameter}){{}}"
    prefix = f"class Panel{base}{{{marker}public:"
    suffix = ("Q_INVOKABLE void ping(){}" if native else "") + "};\n"
    path = project(root, (prefix + constructor + suffix).encode(), native=native)
    baseline = extract_cpp(path)
    node, = [node for node in baseline["nodes"] if _fact(node, "cpp_constructor")]
    signature = _fact(node, "cpp_constructor")["signature"]
    field = "panel_cppctor_" + signature
    expected = node["id"]
    assert _make_id(owner_node(baseline)["id"], field) == expected
    data = "int " + field + ";"
    ctors = constructor + ("Panel(double value){}" if overload else "")
    with_ctor = (prefix + (data + ctors if field_first else ctors + data) + suffix).encode()
    without_ctor = (prefix + data + suffix).encode()
    path.write_bytes(with_ctor)
    return path, field, expected, with_ctor, without_ctor


@pytest.mark.parametrize("field_first", [False, True])
@pytest.mark.parametrize("overload", [False, True])
def test_req_qml022_ac06_literal_field_cannot_steal_or_borrow_constructor_signature(tmp_path, field_first, overload):
    """Each actual constructor keeps its source recipe while data stays noncallable."""
    path, field, expected, raw, _ = constructor_field(tmp_path, field_first=field_first, overload=overload)
    for phase, result in (("direct", extract_cpp(path)), ("facade", facade(tmp_path))):
        found = owned(result)
        data, = [node for node in found if node["label"] == field]
        assert data.get("_callable") is not True and not _fact(data, "cpp_constructor")
        assert data["metadata"]["cpp_declarator"]["kind"] == "field"
        assert field.encode() in span(raw, data["metadata"]["cpp_declarator"])
        ctors = [node for node in found if _fact(node, "cpp_constructor")]
        assert len(ctors) == (2 if overload else 1) and len({node["id"] for node in found}) == len(ctors) + 1
        if phase == "direct":
            assert expected in {node["id"] for node in ctors} and data["id"] != expected
        assert all(node.get("_callable") is True and _fact(node, "cpp_constructor")["type_authorized"] for node in ctors)
        assert not any(qt_metadata(edge).get("native_endpoint") for edge in result["edges"])
        graph = build_from_json(result, root=tmp_path)
        output = tmp_path / (phase + ".json")
        assert to_json(graph, {}, str(output), force=True)
        loaded = load_node_link_graph(json.loads(output.read_text(encoding="utf-8")))
        assert loaded.nodes[data["id"]].get("_callable") is not True
        assert not _fact(loaded.nodes[data["id"]], "cpp_constructor")


def test_req_qml022_ac06_constructor_reservation_uses_original_unnamed_pointer_signature(tmp_path):
    """The source pointer operator survives its admitted equal-byte parser view."""
    path, field, expected, _, _ = constructor_field(tmp_path, field_first=True, parameter="int * = nullptr")
    result = extract_cpp(path)
    data, = [node for node in owned(result) if node["label"] == field]
    ctor, = [node for node in owned(result) if _fact(node, "cpp_constructor")]
    assert ctor["id"] == expected and data["id"] != expected
    assert data.get("_callable") is not True and not _fact(data, "cpp_constructor")
