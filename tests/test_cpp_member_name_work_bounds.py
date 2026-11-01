"""INC-QML-111: actual member allocation reuses one bounded source census."""
from graphify.extract import extract_cpp
from graphify.extractors.base import _make_id
import graphify.extractors.cpp_member_names as member_names
from tests.cpp_member_name_helpers import owned, owner_node


def test_req_qml022_ac06_member_candidate_work_is_linear_in_real_literal_declarations(tmp_path, monkeypatch):
    """Two hundred real colliding fields survive without replanning the class per field."""
    path = tmp_path / "unit.cpp"
    fields = "".join(f"int Field{i};int field{i};" for i in range(100))
    path.write_bytes(("class Panel{public:" + fields + "};\n").encode())
    original, calls = member_names._make_id, []

    def observed(*parts):
        calls.append(parts)
        return original(*parts)

    monkeypatch.setattr(member_names, "_make_id", observed)
    result = extract_cpp(path)
    found = owned(result)
    assert len(found) == 200 and len({node["id"] for node in found}) == 200
    assert all(node.get("_callable") is not True for node in found)
    assert len(calls) <= 6 * len(found) + 20


def test_req_qml022_ac06_literal_census_and_plans_never_cross_source_runs(tmp_path, monkeypatch):
    """Removing the real partner restores the legacy ID in a fresh analysis instance."""
    path = tmp_path / "unit.cpp"
    path.write_bytes(b"class Panel{int Field;double field;};\n")
    original, instances = member_names.CppMemberNames.__init__, []

    def observed(instance, *args, **kwargs):
        original(instance, *args, **kwargs)
        instances.append(instance)

    monkeypatch.setattr(member_names.CppMemberNames, "__init__", observed)
    before = extract_cpp(path)
    old = next(node["id"] for node in owned(before) if node["label"] == "Field")
    path.write_bytes(b"class Panel{int Field;};\n")
    after = extract_cpp(path)
    node, = owned(after)
    assert node["id"] == _make_id(owner_node(after)["id"], "Field") and node["id"] != old
    assert len(instances) == 2 and instances[0] is not instances[1]
