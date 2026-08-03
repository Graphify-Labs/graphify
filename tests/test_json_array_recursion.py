"""Objects nested in JSON arrays are walked — inside the existing guardrails (#2311).

The array-object recursion that makes Icon Composer descriptors extractable has
the broadest potential blast radius of the #2311 work: lockfiles, generated
JSON, fixtures and large arrays all funnel through the same walk. These tests
pin the containment: the data-JSON gate, the 1 MiB read cap, the depth cap and
the 500-pair cap all apply to array elements exactly as they do to objects, and
arrays nested directly inside arrays are not descended into at all.
"""
import json

from graphify.extractors.json_config import extract_json


def _write(tmp_path, name, payload, parent=None):
    directory = tmp_path if parent is None else tmp_path / parent
    directory.mkdir(parents=True, exist_ok=True)
    p = directory / name
    p.write_text(json.dumps(payload), encoding="utf-8")
    return p


def _icon_payload():
    return {
        "fill": {"solid": "srgb:0.2,0.2,0.2,1"},
        "groups": [
            {
                "layers": [
                    {"image-name": "lifted.svg", "name": "lifted"},
                ],
            },
            {
                "layers": [
                    {"image-name": "set-front.svg", "name": "front"},
                    {"image-name": "set-back.svg", "name": "back"},
                ],
            },
        ],
        "supported-platforms": {"circles": ["watchOS"], "squares": "shared"},
    }


def test_icon_composer_descriptor_produces_asset_edges(tmp_path):
    """AppIcon.icon/icon.json -> nodes for the descriptor, edges to each asset."""
    path = _write(tmp_path, "icon.json", _icon_payload(), parent="AppIcon.icon")
    result = extract_json(path)

    assert result.get("skipped") is None
    assert result["nodes"], "the descriptor must produce nodes"

    labels = {n["label"] for n in result["nodes"]}
    assert {"lifted.svg", "set-front.svg", "set-back.svg"} <= labels

    asset_edges = [e for e in result["edges"] if e.get("context") == "asset"]
    ids = {n["id"] for n in result["nodes"]}
    assert len(asset_edges) == 3
    assert all(e["source"] in ids and e["target"] in ids for e in asset_edges)


def test_icon_json_outside_an_icon_bundle_is_still_data(tmp_path):
    """Only `<name>.icon/icon.json` is a descriptor; a stray icon.json is data."""
    path = _write(tmp_path, "icon.json", _icon_payload())
    result = extract_json(path)
    assert result["nodes"] == []
    assert str(result.get("skipped", "")).startswith("data json")


def test_data_json_gate_still_blocks_arrays_of_objects(tmp_path):
    """An API-response fixture full of objects is skipped before any walk."""
    fixture = {"results": [{"id": i, "payload": {"deep": {"deeper": i}}} for i in range(200)]}
    result = extract_json(_write(tmp_path, "api_fixture.json", fixture))
    assert result["nodes"] == []
    assert str(result.get("skipped", "")).startswith("data json")


def test_top_level_array_is_never_walked(tmp_path):
    result = extract_json(_write(tmp_path, "rows.json", [{"$ref": "#/x"}] * 50))
    assert result["nodes"] == []
    assert str(result.get("skipped", "")).startswith("data json")


def test_pair_cap_bounds_a_config_with_a_huge_object_array(tmp_path):
    """A config-shaped file with 10k array objects stops at the 500-pair cap."""
    payload = {
        "compilerOptions": {"strict": True},
        "entries": [{f"k{i}": {"nested": i}} for i in range(10_000)],
    }
    result = extract_json(_write(tmp_path, "big.config.json", payload))
    # file node + at most 500 key nodes (per-pair cap, J-3)
    assert len(result["nodes"]) <= 501
    assert len(result["edges"]) <= 501


def test_depth_cap_applies_through_array_objects(tmp_path):
    payload: dict = {"compilerOptions": {}}
    cursor = payload
    for i in range(12):
        nxt: dict = {}
        cursor["level"] = [nxt]  # alternate through an array at every level
        cursor = nxt
    cursor["bottom"] = "unreachable"
    result = extract_json(_write(tmp_path, "deep.config.json", payload))
    labels = {n["label"] for n in result["nodes"]}
    assert "bottom" not in labels, "depth cap must hold through arrays"


def test_arrays_nested_directly_in_arrays_are_not_descended(tmp_path):
    payload = {
        "compilerOptions": {},
        "matrix": [[{"inner": {"$ref": "#/compilerOptions"}}]],
    }
    result = extract_json(_write(tmp_path, "matrix.config.json", payload))
    labels = {n["label"] for n in result["nodes"]}
    assert "inner" not in labels, "array-of-arrays must not be recursed"
    # And nothing dangles because of it.
    ids = {n["id"] for n in result["nodes"]}
    assert all(e["source"] in ids and e["target"] in ids for e in result["edges"])


def test_oversized_json_is_rejected_before_parsing(tmp_path):
    p = tmp_path / "huge.config.json"
    filler = "x" * 1_100_000
    p.write_text('{"compilerOptions": {"pad": "%s"}}' % filler, encoding="utf-8")
    result = extract_json(p)
    assert result["nodes"] == []
    assert "too large" in result.get("error", "")


def test_asset_edges_resolve_endpoints(tmp_path):
    """No dangling endpoints anywhere in an Icon Composer extraction."""
    path = _write(tmp_path, "icon.json", _icon_payload(), parent="AppIcon.icon")
    result = extract_json(path)
    ids = {n["id"] for n in result["nodes"]}
    for e in result["edges"]:
        assert e["source"] in ids, e
        assert e["target"] in ids, e
