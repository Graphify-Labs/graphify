"""QML-01 identity contracts: raw spelling, owner scope and explicit scan root."""
from __future__ import annotations

import json

import pytest

from graphify.extractors.qml import extract_qml
from tests.qml_test_helpers import assert_contains, by_kind, canonical, one, qml, write_qml


def test_qml003_ac04_relocated_root_and_cwd_preserve_all_facts(tmp_path, monkeypatch):
    """Explicit root is authoritative even when process cwd and absolute checkout change."""
    first_root, second_root, cwd = (tmp_path / name for name in ("first-checkout", "second-checkout", "elsewhere"))
    first = write_qml(first_root, "ui/Main.qml")
    second = write_qml(second_root, "ui/Main.qml")
    cwd.mkdir()
    before = extract_qml(first, root=first_root)
    monkeypatch.chdir(cwd)
    after = extract_qml(second, root=second_root)
    assert canonical(before) == canonical(after)
    assert all(node["source_file"] == "ui/Main.qml" for node in before["nodes"])
    assert all(edge["source_file"] == "ui/Main.qml" for edge in before["edges"])
    assert first_root.as_posix() not in canonical(before)
    assert second_root.as_posix() not in canonical(after)


def test_qml003_ac04_comment_insert_changes_spans_but_not_named_identity(tmp_path):
    """Moving a declaration down a line does not replace its graph identity."""
    source = 'Item { id: root; property int count: 1; function bump() { return count; } }\n'
    path = write_qml(tmp_path, source=source)
    before = extract_qml(path, root=tmp_path)
    write_qml(tmp_path, source="// Added line only\n" + source)
    after = extract_qml(path, root=tmp_path)
    assert {node["id"] for node in before["nodes"]} == {node["id"] for node in after["nodes"]}
    for kind, name in (("property", "count"), ("function", "bump")):
        old, new = one(before, kind, name), one(after, kind, name)
        assert old["id"] == new["id"]
        assert qml(new)["span"]["start_row"] == qml(old)["span"]["start_row"] + 1
        assert qml(old)["component_key"] == qml(new)["component_key"]
        assert qml(old)["object_scope_key"] == qml(new)["object_scope_key"]


def test_qml003_ac02_duplicate_basename_uses_full_relative_path(tmp_path):
    """Same file/member names under different directories cannot share identities."""
    results = [extract_qml(write_qml(tmp_path, relative), root=tmp_path) for relative in ("left/widgets/Panel.qml", "right/widgets/Panel.qml")]
    identities = [{node["id"] for node in result["nodes"]} for result in results]
    assert identities[0].isdisjoint(identities[1])
    assert qml(one(results[0], "component"))["component_key"] != qml(one(results[1], "component"))["component_key"]


@pytest.mark.parametrize("first_name,second_name", [("Panel.qml", "panel.qml"), ("a-b.qml", "a_b.qml"), ("a.b.qml", "a_b.qml"), ("Ａ.qml", "A.qml")])
def test_qml010_ac01_filename_normalization_collisions_keep_distinct_ids(tmp_path, first_name, second_name):
    """Separate roots permit case-distinct path spelling checks on Windows filesystems."""
    results = []
    for index, name in enumerate((first_name, second_name)):
        root = tmp_path / f"checkout-{index}"
        results.append(extract_qml(write_qml(root, name), root=root))
    assert {node["id"] for node in results[0]["nodes"]}.isdisjoint({node["id"] for node in results[1]["nodes"]})
    assert one(results[0], "file")["source_file"] == first_name
    assert one(results[1], "file")["source_file"] == second_name


def test_qml003_ac02_unicode_normalization_colliding_members_remain_distinct(tmp_path):
    """NFKC-equivalent original identifier spellings must retain separate facts."""
    source = 'Item { property int café: 1; property int cafe\u0301: 2 }\n'
    result = extract_qml(write_qml(tmp_path, source=source), root=tmp_path)
    assert not result.get("error")
    properties = by_kind(result, "property")
    assert [qml(node)["raw_name"] for node in properties] == ["café", "cafe\u0301"]
    assert len({node["id"] for node in properties}) == 2


def test_qml003_ac02_inline_component_equal_ids_and_members_have_separate_owners(tmp_path):
    """Equal IDs in root/inline component namespaces are not global property names."""
    source = '''Item {
    id: shared
    property int value: 1
    function run() { return value; }
    component Tile: Item {
        id: shared
        property int value: 2
        function run() { return value; }
    }
}
'''
    result = extract_qml(write_qml(tmp_path, source=source), root=tmp_path)
    assert not result.get("error")
    inline = one(result, "inline_component", "Tile")
    objects = by_kind(result, "object")
    assert len(objects) == 2 and all(qml(node)["object_id"] == "shared" for node in objects)
    assert len({qml(node)["component_key"] for node in objects}) == 2
    assert len({qml(node)["object_scope_key"] for node in objects}) == 2
    inner = next(node for node in objects if qml(node)["component_key"] == qml(inline)["component_key"])
    assert_contains(result, inline, inner)
    for kind in ("property", "function"):
        members = by_kind(result, kind)
        assert len(members) == 2 and len({node["id"] for node in members}) == 2
        assert {qml(node)["parent_scope_key"] for node in members} == {qml(node)["object_scope_key"] for node in objects}
    assert not any(qml(node)["raw_name"] == "id" for node in by_kind(result, "property"))


def test_qml01_ui_suffix_names_component_without_losing_filename_identity(tmp_path):
    """Designer .ui.qml exports Panel while keeping Panel.qml's file scope separate."""
    normal = extract_qml(write_qml(tmp_path, "Panel.qml"), root=tmp_path)
    designer = extract_qml(write_qml(tmp_path, "Panel.ui.qml"), root=tmp_path)
    assert qml(one(normal, "component"))["raw_name"] == qml(one(designer, "component"))["raw_name"] == "Panel"
    assert one(designer, "file")["source_file"] == "Panel.ui.qml"
    assert {node["id"] for node in normal["nodes"]}.isdisjoint({node["id"] for node in designer["nodes"]})


def test_qml010_ac02_metadata_and_keys_survive_json_round_trip_without_paths(tmp_path):
    """Nested scope facts are plain portable values, not Path objects or machine roots."""
    result = extract_qml(write_qml(tmp_path, "ui/Main.qml"), root=tmp_path)
    encoded = json.dumps(result, ensure_ascii=False)
    reloaded = json.loads(encoded)
    assert canonical(reloaded) == canonical(result)
    for node in reloaded["nodes"]:
        data = qml(node)
        for key in ("component_key", "object_scope_key", "parent_scope_key"):
            value = data.get(key)
            if value is not None:
                assert tmp_path.as_posix() not in value and str(tmp_path) not in value
