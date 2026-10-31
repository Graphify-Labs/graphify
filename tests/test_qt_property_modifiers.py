"""REQ-QML-022-AC04/06: source Q_PROPERTY modifiers preserve accessor identities."""
import json

import pytest

from graphify.extractors.qt_cpp_facts import qt_metadata
from graphify.extractors.qt_cpp_properties import property_fields
from graphify.extract import extract
from graphify.security import sanitize_metadata
from tests.qt_cpp_test_helpers import HEADER, collect, facts
from tests.qml_persistence_helpers import protected_snapshot
from tests.test_qml_types_qt612_updates import run_update


@pytest.mark.parametrize("modifier", ["VIRTUAL", "OVERRIDE"])
@pytest.mark.parametrize("role,name", [("READ", "count"), ("MEMBER", "m_count")])
def test_req_qml022_ac04_property_modifiers_do_not_swallow_accessor_names(modifier, role, name):
    """The modifier follows a value-bearing property clause, rather than joining its name."""
    result = property_fields({"args": [f"int count {role} {name} {modifier}"]})
    assert result["status"] == "resolved"
    assert result[role.lower()] == name
    assert result[modifier.lower()] is True


@pytest.mark.parametrize("spelling", ["VIRTUAL", "OVERRIDE"])
def test_req_qml022_ac04_identifiers_spelled_like_modifiers_remain_identifiers(spelling):
    """Neither a property name nor an accessor/MEMBER value becomes a modifier token."""
    parsed = property_fields({"args": [f"int {spelling} READ {spelling} WRITE setValue"]})
    assert parsed["raw_name"] == spelling and parsed["read"] == spelling
    assert spelling.lower() not in parsed
    member = property_fields({"args": [f"int count MEMBER {spelling} VIRTUAL"]})
    assert member["member"] == spelling and member["virtual"] is True


@pytest.mark.parametrize("modifier", ["VIRTUAL", "OVERRIDE"])
@pytest.mark.parametrize("suffix", [" {0}", "(true)"])
def test_req_qml022_ac04_duplicate_or_value_bearing_modifiers_remain_unsupported(modifier, suffix):
    """Repeated flags and values are malformed annotation syntax, not runtime judgments."""
    tail = suffix.format(modifier)
    parsed = property_fields({"args": [f"int count READ count {modifier}{tail}"]})
    assert parsed["status"] == "unsupported"


@pytest.mark.parametrize("modifier", ["VIRTUAL", "OVERRIDE"])
def test_req_qml022_ac06_real_property_accessor_links_and_transport_are_preserved(tmp_path, modifier):
    """A real Qt property retains its READ/WRITE/NOTIFY joins and original macro bytes."""
    original = "Q_PROPERTY(int value READ value WRITE setValue NOTIFY valueChanged)"
    changed = original[:-1] + " " + modifier + ")"
    source = HEADER.replace(original, changed)
    result = collect(tmp_path, {"backend.hpp": source})
    prop = qt_metadata(facts(result, "property", "value")[0])
    assert prop[modifier.lower()] is True and prop["read"] == "value"
    assert source.encode()[prop["span"]["start_byte"]:prop["span"]["end_byte"]] == changed.encode()
    links = [qt_metadata(n) for n in facts(result, "property_accessor")]
    assert {m["accessor_role"]: m["status"] for m in links} == {
        "read": "resolved", "write": "resolved", "notify": "resolved"}
    assert len([e for e in result["edges"] if e.get("context") == "qt_property_accessor"]) == 3
    payload = json.loads(json.dumps(result))
    for item in payload["nodes"] + payload["edges"]:
        item["metadata"] = sanitize_metadata(item.get("metadata", {}))
    assert qt_metadata(facts(payload, "property", "value")[0])[modifier.lower()] is True


def test_req_qml022_ac06_property_modifier_update_removes_stale_flag_and_matches_full(tmp_path, monkeypatch):
    """A valid source-only modifier mutation reaches persisted graph and fresh extraction alike."""
    macro = "Q_PROPERTY(int value READ value WRITE setValue NOTIFY valueChanged)"
    path = tmp_path / "backend.hpp"
    path.write_text(HEADER.replace(macro, macro[:-1] + " VIRTUAL)"), encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    assert run_update(tmp_path, monkeypatch) == 0
    output = tmp_path / "graphify-out/graph.json"
    initial = json.loads(output.read_text(encoding="utf-8"))
    assert qt_metadata(facts(initial, "property", "value")[0])["virtual"] is True
    path.write_text(HEADER.replace(macro, macro[:-1] + " OVERRIDE)"), encoding="utf-8")
    assert run_update(tmp_path, monkeypatch) == 0
    changed = json.loads(output.read_text(encoding="utf-8"))
    prop = qt_metadata(facts(changed, "property", "value")[0])
    assert prop["override"] is True and "virtual" not in prop
    direct = extract([path], root=tmp_path, cache_root=tmp_path / "fresh-cache", parallel=False)
    assert qt_metadata(facts(direct, "property", "value")[0]) == prop
    assert {qt_metadata(n)["accessor_role"]: qt_metadata(n)["status"]
            for n in facts(changed, "property_accessor")} == {
                "read": "resolved", "write": "resolved", "notify": "resolved"}
    settled = protected_snapshot(tmp_path / "graphify-out")
    assert run_update(tmp_path, monkeypatch) == 0
    assert protected_snapshot(tmp_path / "graphify-out") == settled
