"""INC-QML-64: source enum declarations and statically proven type value reads."""
from __future__ import annotations

import copy
import json

import pytest

from graphify.build import build_from_json
from graphify.export import to_json
from graphify.extractors.qml import extract_qml
from graphify.extractors.qml_facts import encode_metadata, qml_metadata
from graphify.paths import load_node_link_graph
from graphify.qml_relationship_lookup import RelationshipLookup
from graphify.qml_resolution import build_qml_index
from tests.qml_expression_helpers import extraction, nodes, single, target_edges


def test_req_qml022_ac02_enum_members_keep_owner_values_and_original_bytes(tmp_path):
    """Distinct enum values retain source spans after BOM/Unicode/CRLF, without evaluation."""
    source = ('\ufeffQtObject {\r\n property string title: "雪"\r\n'
              ' enum Mode { Idle, Running = 4, Next, Negative = -2, Mask = 0x10, Fraction = 1.5, Unknown, Reset = 2, After }\r\n'
              ' enum Other { Idle = 9 }\r\n}\r\n').encode()
    path = tmp_path / "Audit.qml"
    path.write_bytes(source)
    result = extract_qml(path, root=tmp_path)
    assert not result.get("error"), result
    enums = nodes(result, "enum")
    members = nodes(result, "enum_member")
    assert len(members) == 10
    assert len({n["id"] for n in members}) == 10
    expected = {"Idle": 0, "Running": 4, "Next": 5, "Negative": -2, "Mask": 16,
                "Fraction": None, "Unknown": None, "Reset": 2, "After": 3}
    mode = single(result, "enum", "Mode")
    for name, value in expected.items():
        member = [n for n in members if qml_metadata(n)["enum_id"] == mode["id"] and qml_metadata(n)["raw_name"] == name][0]
        md = qml_metadata(member)
        assert md["owner_id"] == mode["id"]
        assert md["value"] == value
        assert md["value_status"] == ("resolved" if value is not None else "unsupported")
        span = md["span"]
        assert source[span["start_byte"]:span["end_byte"]].decode().startswith(name)
        assert any(e["source"] == mode["id"] and e["target"] == member["id"] and e["relation"] == "contains" for e in result["edges"])
    assert len(enums) == 2


def test_req_qml022_ac02_static_enum_reads_use_actual_source_values(tmp_path):
    """Both Qt-documented spellings resolve; ordinary instance properties/methods do not."""
    result = extraction(tmp_path, {"Audit.qml": '''QtObject {
 enum Mode { Idle, Running = 4 }
 property int chosen: Audit.Mode.Running + Audit.Idle
 property var enumObject: Audit.Mode
 property alias rejectedAlias: Audit.Mode.Running
 property int instanceValue: 1
 function method() { return 2 }
 property int rejectedProperty: Audit.instanceValue
 property int rejectedCall: Audit.method()
}'''})
    for reference, name in [("Audit.Mode.Running", "Running"), ("Audit.Idle", "Idle")]:
        site = single(result, "read", reference)
        target = single(result, "enum_member", name)
        assert qml_metadata(site)["status"] == "resolved"
        assert target_edges(result, site)[0]["target"] == target["id"]
    for kind, reference in [("read", "Audit.instanceValue"), ("call", "Audit.method")]:
        site = single(result, kind, reference)
        assert qml_metadata(site)["status"] != "resolved"
        assert not target_edges(result, site)
    assert target_edges(result, single(result, "read", "Audit.Mode"))[0]["target"] == single(result, "enum", "Mode")["id"]
    alias = single(result, "alias", "rejectedAlias")
    assert qml_metadata(alias)["status"] != "resolved" and not target_edges(result, alias)
    graph = build_from_json(result, root=tmp_path, directed=True)
    output = tmp_path / "graph.json"
    to_json(graph, {}, str(output))
    loaded = load_node_link_graph(json.loads(output.read_text()))
    for member in nodes(result, "enum_member"):
        assert qml_metadata(loaded.nodes[member["id"]]) == qml_metadata(member)
    site = single(result, "read", "Audit.Mode.Running")
    assert loaded.has_edge(site["id"], single(result, "enum_member", "Running")["id"])


def test_req_qml022_ac02_qualified_versioned_and_inline_enum_owners(tmp_path):
    """Existing module/version/inline authority selects owners without basename guessing."""
    result = extraction(tmp_path, {"Public/Tools/qmldir": "module Public.Tools\nState 1.0 State.qml\nState 2.0 NewState.qml\ninternal Hidden Hidden.qml\n",
        "Public/Tools/State.qml": "QtObject { enum Mode { Ready = 7 } }",
        "Public/Tools/NewState.qml": "QtObject { enum Mode { Ready = 8 } }",
        "Public/Tools/Hidden.qml": "QtObject { enum Mode { Ready = 9 } }",
        "Main.qml": '''import Public.Tools 1.0 as Tools
QtObject {
 property int selected: Tools.State.Mode.Ready
 property int shortForm: Tools.State.Ready
 property int hidden: Tools.Hidden.Ready
 component Local: QtObject { enum Mode { Ready = 3 } }
 property int inlineValue: Local.Mode.Ready
}'''})
    target = single(result, "enum_member", "Ready", "Public/Tools/State.qml")
    for reference in ["Tools.State.Mode.Ready", "Tools.State.Ready"]:
        site = single(result, "read", reference)
        assert target_edges(result, site)[0]["target"] == target["id"]
    inline = single(result, "read", "Local.Mode.Ready")
    assert qml_metadata(inline)["status"] == "resolved"
    assert qml_metadata(single(result, "read", "Tools.Hidden.Ready"))["status"] != "resolved"


@pytest.mark.parametrize("body,reference", [
    ("enum Mode { Ready } enum Other { Ready }", "Audit.Ready"),
    ("enum Mode { Ready } enum Mode { Ready }", "Audit.Mode.Ready"),
    ("enum Mode { Ready, Ready }", "Audit.Mode.Ready"),
])
def test_req_qml022_ac02_duplicate_enum_owners_and_values_remain_ambiguous(tmp_path, body, reference):
    """No declaration collision is collapsed into a convenient single value."""
    result = extraction(tmp_path, {"Audit.qml": f"QtObject {{ {body}\n property int selected: {reference} }}"})
    site = single(result, "read", reference)
    assert qml_metadata(site)["status"] == "ambiguous"
    assert not target_edges(result, site)


def test_req_qml022_ac02_enum_lookup_preserves_lexical_and_local_shadows(tmp_path):
    """JS formals and local properties precede the otherwise valid static type path."""
    result = extraction(tmp_path, {"State.qml": "QtObject { enum Mode { Ready } }",
        "Main.qml": '''QtObject {
 property int State: 0
 property int local: State.Mode.Ready
 function check(State) { return State.Mode.Ready }
 property int unknown: Missing.Mode.Ready
}'''})
    for reference in ["State.Mode.Ready", "Missing.Mode.Ready"]:
        for site in nodes(result, "read", reference):
            assert qml_metadata(site)["status"] != "resolved"
            assert not target_edges(result, site)


def test_req_qml022_ac02_invalid_names_and_instance_enum_reads_never_gain_authority(tmp_path):
    """Grammar admission retains invalid names but grants no valid static/instance API."""
    result = extraction(tmp_path, {"Audit.qml": '''QtObject {
 id: root
 enum bad { Ready }
 enum Mode { lower, Good = 2147483647, Overflow, Reset = -2147483648 }
 property int invalidEnum: Audit.bad.Ready
 property int invalidValue: Audit.Mode.lower
 property int invalidInstance: root.Mode.Good
}'''})
    for reference in ["Audit.bad.Ready", "Audit.Mode.lower", "root.Mode.Good"]:
        site = single(result, "read", reference)
        assert qml_metadata(site)["status"] != "resolved"
        assert not target_edges(result, site)
    assert qml_metadata(single(result, "enum_member", "Overflow"))["value"] is None
    assert qml_metadata(single(result, "enum_member", "Reset"))["value"] == -(2**31)


@pytest.mark.parametrize("change", ["owner", "scope", "value", "span", "type", "span_list",
                                     "span_none", "owner_name", "owner_span", "enum_id_list",
                                     "name_list", "status_list"])
def test_req_qml022_ac06_corrupt_enum_transport_cannot_authorize_lookup(tmp_path, change):
    """The production resolver rejects corrupted enum ownership/value facts explicitly."""
    result = extraction(tmp_path, {"Audit.qml": "QtObject { enum Mode { Ready = 2 } property int selected: Audit.Ready }"})
    changed = copy.deepcopy(result)
    member = single(changed, "enum_member", "Ready")
    md = qml_metadata(member)
    if change == "owner":
        md["owner_id"] = single(changed, "component")["id"]
    elif change == "scope":
        md["object_scope_key"] = "another_scope"
    elif change == "value":
        md["value"] = 1.5
    elif change == "span":
        md["span"]["end_byte"] += 100
    elif change == "type":
        md["name_valid"] = 1
    elif change in {"span_list", "span_none"}:
        md["span"] = [] if change == "span_list" else None
    elif change in {"owner_name", "owner_span"}:
        enum = single(changed, "enum", "Mode")
        owner = qml_metadata(enum)
        if change == "owner_name":
            owner["raw_name"] = md["enum_name"] = 3
        else:
            owner["span"] = None
        enum["metadata"]["qml"] = encode_metadata({k: v for k, v in owner.items() if k != "raw_values"})
    elif change == "enum_id_list":
        md["enum_id"] = []
    elif change == "name_list":
        md["raw_name"] = []
    else:
        md["value_status"] = []
    member["metadata"]["qml"] = encode_metadata({k: v for k, v in md.items() if k != "raw_values"})
    index = build_qml_index(changed["nodes"], changed["edges"], root=tmp_path)
    with pytest.raises(ValueError, match="QML_METADATA"):
        RelationshipLookup(index)
