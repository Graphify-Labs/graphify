"""Source-reviewed JSONLab evidence for normal MATLAB extraction."""
from collections import Counter
import hashlib
import json
from pathlib import Path
import shutil

from graphify.extract import extract
from graphify.ids import make_id


CORPUS = Path(__file__).parent / "fixtures" / "matlab" / "jsonlab"
MANIFEST = json.loads((CORPUS / "expected.json").read_text(encoding="utf-8"))


def _stage_jsonlab(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    source = root / MANIFEST["contract"]["source_file"]
    shutil.copyfile(CORPUS / source.name, source)
    return source


def _extract(paths: list[Path], root: Path, cache_root: Path) -> dict:
    return extract(paths, root=root, cache_root=cache_root, parallel=False)


def _assert_manifest_matches(result: dict, manifest: dict, source: bytes) -> None:
    definitions = manifest["definitions"]
    path = manifest["file"]["path"]
    expected_by_signature = {
        (
            definition["kind"],
            definition["name"],
            tuple(definition["scope_chain"]),
            definition["source_location"],
        ): definition["key"]
        for definition in definitions
    }
    assert len(expected_by_signature) == len(definitions)

    nodes = result["nodes"]
    assert len({node["id"] for node in nodes}) == len(nodes)
    assert all((node.get("metadata") or {}).get("language") == "matlab" for node in nodes)
    assert all(node.get("source_file") == path for node in nodes)

    file_nodes = [
        node for node in nodes
        if (node.get("metadata") or {}).get("kind") == manifest["file"]["kind"]
    ]
    assert len(file_nodes) == 1
    file_node = file_nodes[0]
    file_metadata = file_node["metadata"]
    assert file_node["label"] == Path(path).name
    assert file_metadata["matlab_file_kind"] == manifest["file"]["matlab_file_kind"]
    assert file_metadata["matlab_primary_name"] == manifest["file"]["matlab_primary_name"]

    actual_by_key = {"file": file_node}
    for node in nodes:
        if node is file_node:
            continue
        metadata = node["metadata"]
        signature = (
            metadata.get("kind"),
            node.get("label"),
            tuple(metadata.get("scope_chain", ())),
            node.get("source_location"),
        )
        assert signature in expected_by_signature, f"unexpected definition: {node}"
        key = expected_by_signature[signature]
        assert key not in actual_by_key, f"duplicate definition for manifest key {key}"
        actual_by_key[key] = node
    assert set(actual_by_key) == {"file", *(definition["key"] for definition in definitions)}

    source_lines = source.splitlines()
    for definition in definitions:
        line = source_lines[int(definition["source_location"][1:]) - 1]
        assert line.decode("utf-8") == definition["source_text"]
        assert line[definition["column"] - 1:].startswith(b"function ")

    expected_edges: Counter[tuple] = Counter()
    for edge in manifest["contains"]:
        expected_edges[("contains", edge["source"], edge["target"], edge["source_location"])] += 1

    for call in manifest["calls"]:
        line = source_lines[int(call["source_location"][1:]) - 1]
        assert line.decode("utf-8") == call["source_text"]
        target_name = next(
            definition["name"] for definition in definitions
            if definition["key"] == call["target"]
        )
        assert line[call["column"] - 1:].startswith(target_name.encode("utf-8"))
        expected_edges[(
            "calls", call["source"], call["target"], call["source_location"],
            "EXTRACTED", 1.0,
        )] += 1

    id_to_key = {node["id"]: key for key, node in actual_by_key.items()}
    actual_edges: Counter[tuple] = Counter()
    for edge in result["edges"]:
        relation = edge.get("relation")
        if relation not in {"contains", "method", "inherits", "calls"}:
            continue
        assert edge.get("source_file") == path, f"edge lost source provenance: {edge}"
        assert edge.get("source") in id_to_key, f"unknown source endpoint: {edge}"
        assert edge.get("target") in id_to_key, f"unknown target endpoint: {edge}"
        record = (
            relation,
            id_to_key[edge["source"]],
            id_to_key[edge["target"]],
            edge.get("source_location"),
        )
        if relation == "calls":
            record += (edge.get("confidence"), edge.get("weight"))
        actual_edges[record] += 1

    missing, unexpected = expected_edges - actual_edges, actual_edges - expected_edges
    assert not missing and not unexpected, (
        f"manifest relationship mismatch; missing={dict(missing)}, unexpected={dict(unexpected)}"
    )


def test_jsonlab_corpus_matches_reviewed_manifest_through_normal_extraction(tmp_path):
    source = _stage_jsonlab(tmp_path / "jsonlab")
    source_bytes = source.read_bytes()
    source_record = next(
        record for record in MANIFEST["provenance"]["files"]
        if record["path"] == MANIFEST["contract"]["source_file"]
    )
    assert len(source_bytes) == source_record["size_bytes"]
    assert hashlib.sha256(source_bytes).hexdigest() == source_record["sha256"]

    result = _extract([source], source.parent, tmp_path / "cache")
    _assert_manifest_matches(result, MANIFEST, source_bytes)

    repeated = _extract([source], source.parent, tmp_path / "cache")
    relocated_source = _stage_jsonlab(tmp_path / "relocated" / "jsonlab")
    relocated = _extract(
        [relocated_source], relocated_source.parent, tmp_path / "relocated-cache"
    )
    assert _canonical_records(repeated) == _canonical_records(result)
    assert _canonical_records(relocated) == _canonical_records(result)


def _stage_normalization_collisions(root: Path) -> list[Path]:
    source = "function entry()\n    Foo();\n    foo();\nend\nfunction Foo()\nend\nfunction foo()\nend\n"
    paths = [root / "pkg-one" / "main-v1.m", root / "pkg_one" / "main_v1.m"]
    for path in paths:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source, encoding="utf-8")
    return paths


def _canonical_records(result: dict) -> tuple[tuple[str, ...], tuple[str, ...]]:
    nodes = tuple(sorted(json.dumps({
        "id": node["id"],
        "label": node.get("label"),
        "source_file": node.get("source_file"),
        "source_location": node.get("source_location"),
        "metadata": node.get("metadata"),
    }, sort_keys=True) for node in result["nodes"]))
    edges = tuple(sorted(json.dumps({
        key: edge.get(key)
        for key in (
            "source", "target", "relation", "source_file", "source_location",
            "confidence", "weight",
        )
    }, sort_keys=True) for edge in result["edges"]))
    return nodes, edges


def test_normal_extraction_is_deterministic_across_repeats_relocation_and_order(tmp_path):
    assert make_id("pkg-one/main-v1") == make_id("pkg_one/main_v1")
    assert make_id("Foo") == make_id("foo")

    root = tmp_path / "first-root" / "repo"
    paths = _stage_normalization_collisions(root)
    forward = _extract(paths, root, tmp_path / "cache-forward")
    repeated = _extract(paths, root, tmp_path / "cache-forward")
    reverse = _extract(list(reversed(paths)), root, tmp_path / "cache-reverse")

    relocated_root = tmp_path / "elsewhere" / "repo"
    relocated_paths = _stage_normalization_collisions(relocated_root)
    relocated = _extract(relocated_paths, relocated_root, tmp_path / "cache-relocated")

    expected = _canonical_records(forward)
    assert _canonical_records(repeated) == expected
    assert _canonical_records(reverse) == expected
    assert _canonical_records(relocated) == expected

    assert len(forward["nodes"]) == 8
    assert len({node["id"] for node in forward["nodes"]}) == 8
    calls = [edge for edge in forward["edges"] if edge.get("relation") == "calls"]
    assert len(calls) == 4
    assert {node["source_file"] for node in forward["nodes"]} == {
        "pkg-one/main-v1.m", "pkg_one/main_v1.m",
    }
    for path in ("pkg-one/main-v1.m", "pkg_one/main_v1.m"):
        assert sum(node.get("source_file") == path for node in forward["nodes"]) == 4
        assert sum(edge.get("source_file") == path for edge in calls) == 2
