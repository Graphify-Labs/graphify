import json
from pathlib import Path

import pytest

from graphify.external import load_extractions
from graphify.watch import _rebuild_code


def _payload(source: str, suffix: str) -> dict:
    source_id = f"external::{suffix}"
    return {
        "nodes": [
            {
                "id": source_id,
                "label": suffix,
                "file_type": "code",
                "source_file": source,
            }
        ],
        "edges": [],
        "hyperedges": [],
        "source_files": [source],
    }


def test_load_extraction_normalizes_sources_and_merges_fragments(tmp_path: Path):
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"
    first.write_text(json.dumps(_payload("config/one.cfg", "one")), encoding="utf-8")
    second.write_text(json.dumps(_payload("config/two.cfg", "two")), encoding="utf-8")

    merged = load_extractions([first, second], root=tmp_path)

    assert [node["label"] for node in merged["nodes"]] == ["one", "two"]
    assert merged["source_files"] == ["config/one.cfg", "config/two.cfg"]


def test_load_extraction_rejects_invalid_schema(tmp_path: Path):
    path = tmp_path / "invalid.json"
    path.write_text(json.dumps({"nodes": [], "edges": [{"source": "missing"}]}), encoding="utf-8")

    with pytest.raises(ValueError, match="missing required field"):
        load_extractions([path], root=tmp_path)


def test_update_replaces_and_prunes_external_sources(tmp_path: Path):
    source = tmp_path / "external" / "config.source"
    source.parent.mkdir()
    source.write_text("live", encoding="utf-8")
    payload = tmp_path / "graphify-out" / "payload.json"
    payload.parent.mkdir()

    payload.write_text(json.dumps(_payload("external/config.source", "first")), encoding="utf-8")
    assert _rebuild_code(
        tmp_path,
        external_extractions=[payload],
        no_cluster=True,
        acquire_lock=False,
    )
    graph = json.loads((tmp_path / "graphify-out/graph.json").read_text(encoding="utf-8"))
    assert {node["label"] for node in graph["nodes"]} == {"first"}

    payload.write_text(json.dumps(_payload("external/config.source", "second")), encoding="utf-8")
    assert _rebuild_code(
        tmp_path,
        external_extractions=[payload],
        no_cluster=True,
        acquire_lock=False,
    )
    graph = json.loads((tmp_path / "graphify-out/graph.json").read_text(encoding="utf-8"))
    assert {node["label"] for node in graph["nodes"]} == {"second"}

    source.unlink()
    payload.write_text(json.dumps({"nodes": [], "edges": [], "hyperedges": [], "source_files": []}), encoding="utf-8")
    assert _rebuild_code(
        tmp_path,
        external_extractions=[payload],
        no_cluster=True,
        acquire_lock=False,
    )
    graph = json.loads((tmp_path / "graphify-out/graph.json").read_text(encoding="utf-8"))
    assert graph["nodes"] == []
