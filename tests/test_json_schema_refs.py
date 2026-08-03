"""JSON Schema `$ref` resolution in the json_config extractor (#2311).

Before this, the `$ref` branch emitted an edge but never a node, so EVERY
`$ref` in a schema produced a dangling endpoint. Internal pointers must resolve
to the `$defs` node the walk already emitted; external refs must emit their own
namespaced concept node; anything unresolvable must be dropped, not dangled.
"""
import json

from graphify.extractors.json_config import _json_pointer_parts, extract_json


def _endpoints_resolve(result: dict) -> bool:
    ids = {n["id"] for n in result["nodes"]}
    return all(
        e["source"] in ids and e["target"] in ids for e in result["edges"]
    )


def _write(tmp_path, name, payload):
    p = tmp_path / name
    p.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return p


def test_json_pointer_parts_decodes_internal_pointers_only():
    assert _json_pointer_parts("#/$defs/asset") == ["$defs", "asset"]
    assert _json_pointer_parts("#") == []
    # RFC 6901 escapes: ~1 -> "/", ~0 -> "~", and ~01 round-trips to "~1"
    assert _json_pointer_parts("#/a~1b") == ["a/b"]
    assert _json_pointer_parts("#/a~0b") == ["a~b"]
    assert _json_pointer_parts("#/a~01b") == ["a~1b"]
    # Not internal pointers
    assert _json_pointer_parts("common.json#/$defs/asset") is None
    assert _json_pointer_parts("https://example.com/s.json") is None
    assert _json_pointer_parts("#namedAnchor") is None


def test_internal_ref_resolves_to_the_defs_node(tmp_path):
    schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "properties": {
            "assets": {"type": "array", "items": {"$ref": "#/$defs/asset"}},
            "events": {"type": "array", "items": {"$ref": "#/$defs/event"}},
        },
        "$defs": {
            "asset": {"type": "object", "properties": {"id": {"type": "string"}}},
            "event": {"type": "object", "properties": {"id": {"type": "string"}}},
        },
    }
    result = extract_json(_write(tmp_path, "export.schema.json", schema))

    assert _endpoints_resolve(result), "internal $ref must not dangle"
    assert "unresolved_internal_refs" not in result
    assert "external_refs" not in result

    schema_refs = [e for e in result["edges"] if e.get("context") == "schema_ref"]
    assert len(schema_refs) == 2
    targets = {e["target"] for e in schema_refs}
    ids = {n["id"] for n in result["nodes"]}
    assert targets <= ids
    # The targets are the real $defs nodes, not minted "ref_*" placeholders.
    assert all(t.endswith(("_defs_asset", "_defs_event")) for t in targets)
    assert not any(t.startswith("ref_") for t in targets)


def test_external_ref_emits_its_own_namespaced_node(tmp_path):
    schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "properties": {
            "a": {"$ref": "common.json#/$defs/shared"},
            "b": {"$ref": "https://example.com/other.schema.json"},
        },
    }
    result = extract_json(_write(tmp_path, "ext.schema.json", schema))

    assert _endpoints_resolve(result), "external $ref must emit its node"
    assert result["external_refs"] == [
        "common.json#/$defs/shared",
        "https://example.com/other.schema.json",
    ]
    # Namespaced under ref_ so they cannot hijack real code node ids (J-4).
    ext_nodes = [n for n in result["nodes"] if n["id"].startswith("ref_")]
    assert {n["file_type"] for n in ext_nodes} == {"concept"}


def test_unresolvable_internal_ref_is_dropped_not_dangled(tmp_path):
    schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "properties": {"a": {"$ref": "#/$defs/doesNotExist"}},
        "$defs": {"real": {"type": "string"}},
    }
    result = extract_json(_write(tmp_path, "missing.schema.json", schema))

    assert _endpoints_resolve(result), "a pointer at nothing must not dangle"
    assert result["unresolved_internal_refs"] == ["#/$defs/doesNotExist"]
    assert not [e for e in result["edges"] if e.get("context") == "schema_ref"]


def test_root_pointer_targets_the_file_node(tmp_path):
    schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "properties": {"self": {"$ref": "#"}},
    }
    path = _write(tmp_path, "root.schema.json", schema)
    result = extract_json(path)

    assert _endpoints_resolve(result)
    schema_refs = [e for e in result["edges"] if e.get("context") == "schema_ref"]
    assert len(schema_refs) == 1
    # The file node is the one whose label is the filename.
    file_nid = next(n["id"] for n in result["nodes"] if n["label"] == path.name)
    assert schema_refs[0]["target"] == file_nid


def test_forward_and_backward_refs_both_resolve(tmp_path):
    """Resolution is deferred, so document order must not matter."""
    schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "early": {"$ref": "#/$defs/late"},          # forward
        "$defs": {"late": {"type": "string"}, "soon": {"type": "string"}},
        "afterwards": {"$ref": "#/$defs/soon"},     # backward
    }
    result = extract_json(_write(tmp_path, "order2.schema.json", schema))
    assert _endpoints_resolve(result)
    assert "unresolved_internal_refs" not in result
    assert len([e for e in result["edges"] if e.get("context") == "schema_ref"]) == 2


def test_ref_resolution_is_deterministic_across_runs(tmp_path):
    schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "properties": {
            "z": {"$ref": "#/$defs/zebra"},
            "a": {"$ref": "#/$defs/apple"},
            "m": {"$ref": "#/$defs/mango"},
        },
        "$defs": {
            "zebra": {"type": "string"},
            "apple": {"type": "string"},
            "mango": {"type": "string"},
        },
    }
    path = _write(tmp_path, "order.schema.json", schema)
    runs = [
        [
            (e["source"], e["target"])
            for e in extract_json(path)["edges"]
            if e.get("context") == "schema_ref"
        ]
        for _ in range(3)
    ]
    assert runs[0] == runs[1] == runs[2]
    assert len(runs[0]) == 3
