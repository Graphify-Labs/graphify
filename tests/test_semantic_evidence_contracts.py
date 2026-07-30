"""Public semantic-fragment evidence contracts for issue #534.

The extraction skill snapshots trusted source files before dispatch, then
``graphify merge-chunks`` validates every untrusted semantic record against
that snapshot before writing any merged output.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import graphify.__main__ as mainmod
import pytest
from graphify import llm


EDGE_RELATIONS = (
    "calls",
    "implements",
    "references",
    "cites",
    "conceptually_related_to",
    "shares_data_with",
    "semantically_similar_to",
    "rationale_for",
)
HYPEREDGE_RELATIONS = ("participate_in", "implement", "form")


def _write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value), encoding="utf-8")


def _run(monkeypatch: pytest.MonkeyPatch, argv: list[str]) -> None:
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)
    monkeypatch.setattr(mainmod.sys, "argv", argv)
    mainmod.main()


def _snapshot(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    source: Path,
) -> Path:
    files_from = tmp_path / "sources.txt"
    files_from.write_text(f"{source}\n", encoding="utf-8")
    manifest = tmp_path / "semantic-sources.json"
    _run(
        monkeypatch,
        [
            "graphify",
            "snapshot-sources",
            str(files_from),
            "--root",
            str(tmp_path),
            "--out",
            str(manifest),
        ],
    )
    return manifest


def _provenance(source: Path, location: object = "L1-L2") -> dict[str, object]:
    return {"source_file": str(source), "source_location": location}


def _valid_fragment(source: Path) -> dict:
    provenance = _provenance(source)
    nodes = [
        {
            "id": "docs_contract_alpha",
            "label": "Alpha",
            "file_type": "document",
            **provenance,
        },
        {
            "id": "docs_contract_beta",
            "label": "Beta",
            "file_type": "document",
            **provenance,
        },
        {
            "id": "docs_contract_gamma",
            "label": "Gamma",
            "file_type": "document",
            **provenance,
        },
    ]
    return {
        "nodes": nodes,
        "edges": [
            {
                "source": "docs_contract_alpha",
                "target": "docs_contract_beta",
                "relation": relation,
                "confidence": "EXTRACTED",
                "confidence_score": 1.0,
                **provenance,
            }
            for relation in EDGE_RELATIONS
        ],
        "hyperedges": [
            {
                "id": f"docs_contract_group_{index}",
                "label": relation,
                "nodes": [node["id"] for node in nodes],
                "relation": relation,
                "confidence": "EXTRACTED",
                "confidence_score": 1.0,
                **provenance,
            }
            for index, relation in enumerate(HYPEREDGE_RELATIONS)
        ],
    }


def _merge(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    fragment: dict,
    manifest: Path,
    *,
    manifest_sha256: str | None = None,
) -> Path:
    chunk = tmp_path / ".graphify_chunk_00.json"
    _write_json(chunk, fragment)
    output = tmp_path / "semantic.json"
    _run(
        monkeypatch,
        [
            "graphify",
            "merge-chunks",
            str(chunk),
            "--source-manifest",
            str(manifest),
            "--manifest-sha256",
            manifest_sha256 or hashlib.sha256(manifest.read_bytes()).hexdigest(),
            "--out",
            str(output),
        ],
    )
    return output


def _merge_semantic(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    cached: dict,
    new: dict,
    manifest: Path,
) -> Path:
    cached_path = tmp_path / "cached.json"
    new_path = tmp_path / "new.json"
    output = tmp_path / "combined.json"
    _write_json(cached_path, cached)
    _write_json(new_path, new)
    _run(
        monkeypatch,
        [
            "graphify",
            "merge-semantic",
            "--cached",
            str(cached_path),
            "--new",
            str(new_path),
            "--source-manifest",
            str(manifest),
            "--manifest-sha256",
            hashlib.sha256(manifest.read_bytes()).hexdigest(),
            "--out",
            str(output),
        ],
    )
    return output


def test_merge_accepts_closed_relation_vocabularies_and_exact_line_spans(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "contract.md"
    source.write_text("alpha\nbeta\n", encoding="utf-8")
    manifest = _snapshot(tmp_path, monkeypatch, source)

    output = _merge(tmp_path, monkeypatch, _valid_fragment(source), manifest)

    merged = json.loads(output.read_text(encoding="utf-8"))
    assert {edge["relation"] for edge in merged["edges"]} == set(EDGE_RELATIONS)
    assert {edge["relation"] for edge in merged["hyperedges"]} == set(HYPEREDGE_RELATIONS)
    expected_digest = hashlib.sha256(source.read_bytes()).hexdigest()
    for collection in ("nodes", "edges", "hyperedges"):
        assert all(record["source_sha256"] == expected_digest for record in merged[collection])
        assert all(record["source_location"] == "L1-L2" for record in merged[collection])


@pytest.mark.parametrize("relation", ["unknown_relation", "CALLS", "", None, ["calls"]])
def test_merge_rejects_unknown_or_malformed_edge_relation_before_write(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    relation: object,
) -> None:
    source = tmp_path / "contract.md"
    source.write_text("alpha\nbeta\n", encoding="utf-8")
    manifest = _snapshot(tmp_path, monkeypatch, source)
    fragment = _valid_fragment(source)
    fragment["edges"][0]["relation"] = relation
    output = tmp_path / "semantic.json"
    output.write_text('{"previous": true}', encoding="utf-8")

    with pytest.raises(SystemExit) as exc:
        _merge(tmp_path, monkeypatch, fragment, manifest)

    assert exc.value.code == 1
    assert json.loads(output.read_text(encoding="utf-8")) == {"previous": True}


@pytest.mark.parametrize("relation", ["unknown_relation", "FORM", "", None, {"form": True}])
def test_merge_rejects_unknown_or_malformed_hyperedge_relation_before_write(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    relation: object,
) -> None:
    source = tmp_path / "contract.md"
    source.write_text("alpha\nbeta\n", encoding="utf-8")
    manifest = _snapshot(tmp_path, monkeypatch, source)
    fragment = _valid_fragment(source)
    fragment["hyperedges"][0]["relation"] = relation

    with pytest.raises(SystemExit) as exc:
        _merge(tmp_path, monkeypatch, fragment, manifest)

    assert exc.value.code == 1
    assert not (tmp_path / "semantic.json").exists()


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("source_file", None),
        ("source_location", None),
        ("source_location", ""),
        ("source_location", "line 1"),
        ("source_location", "L0"),
        ("source_location", "L2-L1"),
        ("source_location", "L1-B2"),
        ("source_location", "L3"),
    ],
)
def test_merge_rejects_missing_null_malformed_or_out_of_range_provenance(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    field: str,
    value: object,
) -> None:
    source = tmp_path / "contract.md"
    source.write_text("alpha\nbeta\n", encoding="utf-8")
    manifest = _snapshot(tmp_path, monkeypatch, source)
    fragment = _valid_fragment(source)
    fragment["nodes"][0][field] = value

    with pytest.raises(SystemExit) as exc:
        _merge(tmp_path, monkeypatch, fragment, manifest)

    assert exc.value.code == 1
    assert not (tmp_path / "semantic.json").exists()


def test_merge_rejects_missing_provenance_field(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "contract.md"
    source.write_text("alpha\nbeta\n", encoding="utf-8")
    manifest = _snapshot(tmp_path, monkeypatch, source)
    fragment = _valid_fragment(source)
    del fragment["edges"][0]["source_location"]

    with pytest.raises(SystemExit) as exc:
        _merge(tmp_path, monkeypatch, fragment, manifest)

    assert exc.value.code == 1
    assert not (tmp_path / "semantic.json").exists()


def test_merge_rejects_non_resolving_provenance(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "contract.md"
    source.write_text("alpha\nbeta\n", encoding="utf-8")
    manifest = _snapshot(tmp_path, monkeypatch, source)
    fragment = _valid_fragment(source)
    fragment["nodes"][0]["source_file"] = str(tmp_path / "not-dispatched.md")

    with pytest.raises(SystemExit) as exc:
        _merge(tmp_path, monkeypatch, fragment, manifest)

    assert exc.value.code == 1
    assert not (tmp_path / "semantic.json").exists()


def test_merge_rejects_stale_provenance_when_source_changes_after_snapshot(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "contract.md"
    source.write_text("alpha\nbeta\n", encoding="utf-8")
    manifest = _snapshot(tmp_path, monkeypatch, source)
    fragment = _valid_fragment(source)
    source.write_text("changed\nbeta\n", encoding="utf-8")

    with pytest.raises(SystemExit) as exc:
        _merge(tmp_path, monkeypatch, fragment, manifest)

    assert exc.value.code == 1
    assert not (tmp_path / "semantic.json").exists()


def test_merge_accepts_exact_binary_byte_span(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "diagram.png"
    source.write_bytes(b"\x89PNG\r\n\x1a\n")
    manifest = _snapshot(tmp_path, monkeypatch, source)
    fragment = _valid_fragment(source)
    for collection in ("nodes", "edges", "hyperedges"):
        for record in fragment[collection]:
            record["source_location"] = "B0-B8"

    output = _merge(tmp_path, monkeypatch, fragment, manifest)

    merged = json.loads(output.read_text(encoding="utf-8"))
    assert merged["nodes"][0]["source_location"] == "B0-B8"


def test_merge_rejects_manifest_addressing_mode_that_disagrees_with_source(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "contract.md"
    source.write_text("alpha\nbeta\n", encoding="utf-8")
    manifest = _snapshot(tmp_path, monkeypatch, source)
    snapshot = json.loads(manifest.read_text(encoding="utf-8"))
    snapshot["sources"][str(source)]["span_kind"] = "byte"
    snapshot["sources"][str(source)]["extent"] = len(source.read_bytes())
    _write_json(manifest, snapshot)

    with pytest.raises(SystemExit) as exc:
        _merge(tmp_path, monkeypatch, _valid_fragment(source), manifest)

    assert exc.value.code == 1
    assert not (tmp_path / "semantic.json").exists()


def test_merge_rejects_manifest_rewritten_after_parent_snapshot(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "contract.md"
    source.write_text("alpha\nbeta\n", encoding="utf-8")
    manifest = _snapshot(tmp_path, monkeypatch, source)
    parent_seal = hashlib.sha256(manifest.read_bytes()).hexdigest()

    source.write_text("changed\nbeta\n", encoding="utf-8")
    rewritten = json.loads(manifest.read_text(encoding="utf-8"))
    rewritten["sources"][str(source)]["sha256"] = hashlib.sha256(
        source.read_bytes()
    ).hexdigest()
    _write_json(manifest, rewritten)

    with pytest.raises(SystemExit) as exc:
        _merge(
            tmp_path,
            monkeypatch,
            _valid_fragment(source),
            manifest,
            manifest_sha256=parent_seal,
        )

    assert exc.value.code == 1
    assert not (tmp_path / "semantic.json").exists()


def test_snapshot_sources_rejects_output_that_is_a_provenance_source(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "contract.md"
    source.write_text("source evidence\n", encoding="utf-8")
    files_from = tmp_path / "sources.txt"
    files_from.write_text(f"{source}\n", encoding="utf-8")

    with pytest.raises(SystemExit) as exc:
        _run(
            monkeypatch,
            [
                "graphify",
                "snapshot-sources",
                str(files_from),
                "--root",
                str(tmp_path),
                "--out",
                str(source),
            ],
        )

    assert exc.value.code == 1
    assert source.read_text(encoding="utf-8") == "source evidence\n"


@pytest.mark.parametrize(
    "location",
    [
        "L" + ("9" * 5_000),
        "B0-B" + ("9" * 5_000),
    ],
)
def test_merge_rejects_pathological_numeric_span_without_crashing_or_writing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    location: str,
) -> None:
    source = tmp_path / "contract.md"
    source.write_text("alpha\nbeta\n", encoding="utf-8")
    manifest = _snapshot(tmp_path, monkeypatch, source)
    fragment = _valid_fragment(source)
    fragment["nodes"][0]["source_location"] = location
    output = tmp_path / "semantic.json"
    output.write_text('{"previous": true}', encoding="utf-8")

    with pytest.raises(SystemExit) as exc:
        _merge(tmp_path, monkeypatch, fragment, manifest)

    assert exc.value.code == 1
    assert json.loads(output.read_text(encoding="utf-8")) == {"previous": True}


def test_merge_rechecks_sources_at_atomic_persistence_boundary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "contract.md"
    source.write_text("alpha\nbeta\n", encoding="utf-8")
    manifest = _snapshot(tmp_path, monkeypatch, source)
    output = tmp_path / "semantic.json"
    output.write_text('{"previous": true}', encoding="utf-8")

    import graphify.paths as paths

    real_dump = paths.json.dump

    def mutate_while_serializing(*args, **kwargs):
        result = real_dump(*args, **kwargs)
        source.write_text("changed\nbeta\n", encoding="utf-8")
        return result

    monkeypatch.setattr(paths.json, "dump", mutate_while_serializing)

    with pytest.raises(SystemExit) as exc:
        _merge(tmp_path, monkeypatch, _valid_fragment(source), manifest)

    assert exc.value.code == 1
    assert json.loads(output.read_text(encoding="utf-8")) == {"previous": True}


def test_merge_prepares_manifest_once_for_all_chunks_and_rechecks_once(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "contract.md"
    source.write_text("alpha\nbeta\n", encoding="utf-8")
    manifest = _snapshot(tmp_path, monkeypatch, source)
    seal = hashlib.sha256(manifest.read_bytes()).hexdigest()
    chunks = []
    for index in range(2):
        chunk = tmp_path / f".graphify_chunk_{index:02d}.json"
        fragment = _valid_fragment(source)
        fragment["nodes"][0]["id"] += f"_{index}"
        _write_json(chunk, fragment)
        chunks.append(chunk)

    real_open = Path.open
    source_reads = 0

    def count_source_reads(path: Path, *args, **kwargs):
        nonlocal source_reads
        if path == source:
            source_reads += 1
        return real_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", count_source_reads)
    _run(
        monkeypatch,
        [
            "graphify",
            "merge-chunks",
            *(str(chunk) for chunk in chunks),
            "--source-manifest",
            str(manifest),
            "--manifest-sha256",
            seal,
            "--out",
            str(tmp_path / "semantic.json"),
        ],
    )

    assert source_reads == 2, "prepare once, then recheck once immediately before persistence"


def test_merge_semantic_validates_cached_and_new_against_one_source_snapshot(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "contract.md"
    source.write_text("alpha\nbeta\n", encoding="utf-8")
    manifest = _snapshot(tmp_path, monkeypatch, source)
    cached = _valid_fragment(source)
    new = _valid_fragment(source)
    new["nodes"][0]["id"] = "new_alpha"

    output = _merge_semantic(
        tmp_path,
        monkeypatch,
        cached=cached,
        new=new,
        manifest=manifest,
    )

    merged = json.loads(output.read_text(encoding="utf-8"))
    expected_digest = hashlib.sha256(source.read_bytes()).hexdigest()
    assert merged["nodes"]
    assert all(node["source_sha256"] == expected_digest for node in merged["nodes"])


def test_merge_semantic_rejects_stale_cached_source_digest_before_write(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "contract.md"
    source.write_text("alpha\nbeta\n", encoding="utf-8")
    manifest = _snapshot(tmp_path, monkeypatch, source)
    cached = _valid_fragment(source)
    cached["nodes"][0]["source_sha256"] = "0" * 64
    output = tmp_path / "combined.json"
    output.write_text('{"previous": true}', encoding="utf-8")

    with pytest.raises(SystemExit) as exc:
        _merge_semantic(
            tmp_path,
            monkeypatch,
            cached=cached,
            new={"nodes": [], "edges": [], "hyperedges": []},
            manifest=manifest,
        )

    assert exc.value.code == 1
    assert json.loads(output.read_text(encoding="utf-8")) == {"previous": True}


def test_merge_semantic_rejects_unknown_cached_relation_before_write(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "contract.md"
    source.write_text("alpha\nbeta\n", encoding="utf-8")
    manifest = _snapshot(tmp_path, monkeypatch, source)
    cached = _valid_fragment(source)
    cached["edges"][0]["relation"] = "unknown_relation"
    output = tmp_path / "combined.json"
    output.write_text('{"previous": true}', encoding="utf-8")

    with pytest.raises(SystemExit) as exc:
        _merge_semantic(
            tmp_path,
            monkeypatch,
            cached=cached,
            new={"nodes": [], "edges": [], "hyperedges": []},
            manifest=manifest,
        )

    assert exc.value.code == 1
    assert json.loads(output.read_text(encoding="utf-8")) == {"previous": True}


def test_merge_chunks_rejects_combined_raw_input_over_aggregate_byte_cap(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import graphify.semantic_cleanup as cleanup

    source = tmp_path / "contract.md"
    source.write_text("alpha\n", encoding="utf-8")
    manifest = _snapshot(tmp_path, monkeypatch, source)
    provenance = _provenance(source, "L1")
    chunk_paths: list[Path] = []
    for index in range(2):
        chunk = {
            "nodes": [
                {
                    "id": f"worker_node_{index}",
                    "label": f"Worker {index}",
                    "file_type": "document",
                    **provenance,
                }
            ],
            "edges": [],
            "hyperedges": [],
        }
        chunk_path = tmp_path / f".graphify_chunk_{index:02d}.json"
        payload = json.dumps(chunk)
        assert len(payload.encode("utf-8")) < 4_500
        chunk_path.write_text(
            payload + (" " * (4_500 - len(payload.encode("utf-8")))),
            encoding="utf-8",
        )
        assert chunk_path.stat().st_size == 4_500
        chunk_paths.append(chunk_path)
    output = tmp_path / "semantic.json"
    output.write_text('{"previous": true}', encoding="utf-8")
    monkeypatch.setattr(cleanup, "MAX_SEMANTIC_AGGREGATE_BYTES", 5_000)

    with pytest.raises(SystemExit) as exc:
        _run(
            monkeypatch,
            [
                "graphify",
                "merge-chunks",
                *(str(path) for path in chunk_paths),
                "--source-manifest",
                str(manifest),
                "--manifest-sha256",
                hashlib.sha256(manifest.read_bytes()).hexdigest(),
                "--out",
                str(output),
            ],
        )

    assert exc.value.code == 1
    assert json.loads(output.read_text(encoding="utf-8")) == {"previous": True}


def test_merge_chunks_stops_reading_after_first_invalid_worker(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "contract.md"
    source.write_text("alpha\nbeta\n", encoding="utf-8")
    manifest = _snapshot(tmp_path, monkeypatch, source)
    invalid = _valid_fragment(source)
    invalid["edges"][0]["relation"] = "unknown_relation"
    first_chunk = tmp_path / ".graphify_chunk_00.json"
    second_chunk = tmp_path / ".graphify_chunk_01.json"
    _write_json(first_chunk, invalid)
    _write_json(second_chunk, _valid_fragment(source))
    output = tmp_path / "semantic.json"
    output.write_text('{"previous": true}', encoding="utf-8")
    real_open = Path.open

    def reject_second_worker_read(path: Path, *args, **kwargs):
        if path == second_chunk:
            raise AssertionError("terminal batch must not read later workers")
        return real_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", reject_second_worker_read)

    with pytest.raises(SystemExit) as exc:
        _run(
            monkeypatch,
            [
                "graphify",
                "merge-chunks",
                str(first_chunk),
                str(second_chunk),
                "--source-manifest",
                str(manifest),
                "--manifest-sha256",
                hashlib.sha256(manifest.read_bytes()).hexdigest(),
                "--out",
                str(output),
            ],
        )

    assert exc.value.code == 1
    assert json.loads(output.read_text(encoding="utf-8")) == {"previous": True}


def test_merge_chunks_rejects_serialized_output_over_aggregate_byte_cap(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import graphify.semantic_cleanup as cleanup

    source = tmp_path / "contract.md"
    source.write_text("alpha\nbeta\n", encoding="utf-8")
    manifest = _snapshot(tmp_path, monkeypatch, source)
    fragment = _valid_fragment(source)
    chunk = tmp_path / ".graphify_chunk_00.json"
    _write_json(chunk, fragment)
    raw_input_bytes = chunk.stat().st_size
    aggregate_cap = raw_input_bytes + 100
    expected = json.loads(json.dumps(fragment))
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    for collection in ("nodes", "edges", "hyperedges"):
        for record in expected[collection]:
            record["source_sha256"] = digest
    expected["input_tokens"] = 0
    expected["output_tokens"] = 0
    assert len(json.dumps(expected, ensure_ascii=False).encode("utf-8")) > aggregate_cap
    output = tmp_path / "semantic.json"
    output.write_text('{"previous": true}', encoding="utf-8")
    monkeypatch.setattr(
        cleanup,
        "MAX_SEMANTIC_AGGREGATE_BYTES",
        aggregate_cap,
    )

    with pytest.raises(SystemExit) as exc:
        _run(
            monkeypatch,
            [
                "graphify",
                "merge-chunks",
                str(chunk),
                "--source-manifest",
                str(manifest),
                "--manifest-sha256",
                hashlib.sha256(manifest.read_bytes()).hexdigest(),
                "--out",
                str(output),
            ],
        )

    assert exc.value.code == 1
    assert json.loads(output.read_text(encoding="utf-8")) == {"previous": True}


def test_merge_semantic_accepts_valid_multi_chunk_aggregate_over_worker_cap(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "contract.md"
    source.write_text("alpha\n", encoding="utf-8")
    manifest = _snapshot(tmp_path, monkeypatch, source)
    provenance = _provenance(source, "L1")
    aggregate = {
        "nodes": [
            {
                "id": f"aggregate_node_{index}",
                "label": f"Node {index} " + ("x" * 2_200),
                "file_type": "document",
                **provenance,
            }
            for index in range(12_000)
        ],
        "edges": [],
        "hyperedges": [],
    }
    assert len(json.dumps(aggregate).encode("utf-8")) > 25 * 1024 * 1024
    chunk_paths: list[Path] = []
    for index, nodes in enumerate((aggregate["nodes"][:6_000], aggregate["nodes"][6_000:])):
        chunk_path = tmp_path / f".graphify_chunk_{index:02d}.json"
        _write_json(
            chunk_path,
            {"nodes": nodes, "edges": [], "hyperedges": []},
        )
        assert chunk_path.stat().st_size < 25 * 1024 * 1024
        chunk_paths.append(chunk_path)
    new_output = tmp_path / "semantic-new.json"
    _run(
        monkeypatch,
        [
            "graphify",
            "merge-chunks",
            *(str(path) for path in chunk_paths),
            "--source-manifest",
            str(manifest),
            "--manifest-sha256",
            hashlib.sha256(manifest.read_bytes()).hexdigest(),
            "--out",
            str(new_output),
        ],
    )
    assert new_output.stat().st_size > 25 * 1024 * 1024

    output = _merge_semantic(
        tmp_path,
        monkeypatch,
        cached={"nodes": [], "edges": [], "hyperedges": []},
        new=json.loads(new_output.read_text(encoding="utf-8")),
        manifest=manifest,
    )

    merged = json.loads(output.read_text(encoding="utf-8"))
    assert len(merged["nodes"]) == 12_000


def test_merge_semantic_rejects_combined_result_over_aggregate_byte_cap(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import graphify.semantic_cleanup as cleanup

    source = tmp_path / "contract.md"
    source.write_text("alpha\nbeta\n", encoding="utf-8")
    manifest = _snapshot(tmp_path, monkeypatch, source)
    cached = {"nodes": [], "edges": [], "hyperedges": []}
    new = _valid_fragment(source)
    raw_input_bytes = len(json.dumps(cached).encode("utf-8"))
    raw_input_bytes += len(json.dumps(new).encode("utf-8"))
    aggregate_cap = raw_input_bytes + 100
    expected = json.loads(json.dumps(new))
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    for collection in ("nodes", "edges", "hyperedges"):
        for record in expected[collection]:
            record["source_sha256"] = digest
    assert len(json.dumps(expected, ensure_ascii=False).encode("utf-8")) > aggregate_cap
    output = tmp_path / "combined.json"
    output.write_text('{"previous": true}', encoding="utf-8")
    monkeypatch.setattr(
        cleanup,
        "MAX_SEMANTIC_AGGREGATE_BYTES",
        aggregate_cap,
    )

    with pytest.raises(SystemExit) as exc:
        _merge_semantic(
            tmp_path,
            monkeypatch,
            cached=cached,
            new=new,
            manifest=manifest,
        )

    assert exc.value.code == 1
    assert json.loads(output.read_text(encoding="utf-8")) == {"previous": True}


def test_merge_semantic_rejects_combined_input_over_cap_before_deduplication(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import graphify.semantic_cleanup as cleanup

    source = tmp_path / "contract.md"
    source.write_text("alpha\n", encoding="utf-8")
    manifest = _snapshot(tmp_path, monkeypatch, source)
    provenance = _provenance(source, "L1")
    duplicate = {
        "nodes": [
            {
                "id": "duplicate_node",
                "label": "Duplicate",
                "file_type": "document",
                **provenance,
            }
        ],
        "edges": [],
        "hyperedges": [],
    }
    payload = json.dumps(duplicate)
    assert len(payload.encode("utf-8")) < 4_500
    padded_payload = payload + (" " * (4_500 - len(payload.encode("utf-8"))))
    cached_path = tmp_path / "cached.json"
    new_path = tmp_path / "new.json"
    cached_path.write_text(padded_payload, encoding="utf-8")
    new_path.write_text(padded_payload, encoding="utf-8")
    assert cached_path.stat().st_size == 4_500
    assert new_path.stat().st_size == 4_500
    output = tmp_path / "combined.json"
    output.write_text('{"previous": true}', encoding="utf-8")
    monkeypatch.setattr(cleanup, "MAX_SEMANTIC_AGGREGATE_BYTES", 5_000)

    with pytest.raises(SystemExit) as exc:
        _run(
            monkeypatch,
            [
                "graphify",
                "merge-semantic",
                "--cached",
                str(cached_path),
                "--new",
                str(new_path),
                "--source-manifest",
                str(manifest),
                "--manifest-sha256",
                hashlib.sha256(manifest.read_bytes()).hexdigest(),
                "--out",
                str(output),
            ],
        )

    assert exc.value.code == 1
    assert json.loads(output.read_text(encoding="utf-8")) == {"previous": True}


def test_untrusted_semantic_files_are_read_with_a_hard_byte_bound(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import io

    from graphify.semantic_cleanup import (
        MAX_SEMANTIC_FRAGMENT_BYTES,
        load_validated_semantic_fragment,
    )

    payload = json.dumps(
        {"nodes": [], "edges": [], "hyperedges": []}
    ).encode("utf-8")
    requested_sizes: list[int] = []

    class TrackingReader(io.BytesIO):
        def read(self, size: int = -1) -> bytes:
            requested_sizes.append(size)
            return super().read(size)

    monkeypatch.setattr(
        Path,
        "open",
        lambda self, *args, **kwargs: TrackingReader(payload),
    )

    fragment, errors = load_validated_semantic_fragment(tmp_path / "chunk.json")

    assert errors == []
    assert fragment == {"nodes": [], "edges": [], "hyperedges": []}
    assert requested_sizes == [MAX_SEMANTIC_FRAGMENT_BYTES + 1]


def test_untrusted_source_manifest_is_read_with_a_hard_byte_bound(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import io

    from graphify.semantic_cleanup import load_semantic_source_manifest

    payload = b"{}"
    requested_sizes: list[int] = []

    class TrackingReader(io.BytesIO):
        def read(self, size: int = -1) -> bytes:
            requested_sizes.append(size)
            return super().read(size)

    monkeypatch.setattr(
        Path,
        "open",
        lambda self, *args, **kwargs: TrackingReader(payload),
    )

    manifest, errors = load_semantic_source_manifest(
        tmp_path / "manifest.json",
        expected_sha256=hashlib.sha256(payload).hexdigest(),
    )

    assert manifest is None
    assert errors == ["schema_version must be 1"]
    assert requested_sizes == [(25 * 1024 * 1024) + 1]


def test_source_snapshot_and_recheck_stream_instead_of_reading_whole_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "contract.md"
    source.write_text("alpha\nbeta\n", encoding="utf-8")
    real_read_bytes = Path.read_bytes

    def reject_whole_source_read(path: Path) -> bytes:
        if path == source:
            raise AssertionError("source evidence must be streamed")
        return real_read_bytes(path)

    monkeypatch.setattr(Path, "read_bytes", reject_whole_source_read)
    manifest = _snapshot(tmp_path, monkeypatch, source)

    output = _merge(tmp_path, monkeypatch, _valid_fragment(source), manifest)

    assert output.exists()


def _native_fragment(source_file: str, relation: object = "references") -> dict:
    provenance = {"source_file": source_file, "source_location": "L1-L2"}
    return {
        "nodes": [
            {
                "id": "contract_alpha",
                "label": "Alpha",
                "file_type": "document",
                **provenance,
            },
            {
                "id": "contract_beta",
                "label": "Beta",
                "file_type": "document",
                **provenance,
            },
        ],
        "edges": [
            {
                "source": "contract_alpha",
                "target": "contract_beta",
                "relation": relation,
                "confidence": "EXTRACTED",
                "confidence_score": 1.0,
                **provenance,
            }
        ],
        "hyperedges": [],
        "input_tokens": 10,
        "output_tokens": 5,
    }


def test_native_extraction_validates_and_binds_provenance_before_return(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "contract.md"
    source.write_text("alpha\nbeta\n", encoding="utf-8")
    monkeypatch.setattr(
        llm,
        "_call_openai_compat",
        lambda *args, **kwargs: _native_fragment("contract.md"),
    )

    result = llm.extract_files_direct(
        [source],
        backend="openai",
        api_key="test-key",
        root=tmp_path,
    )

    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    assert result["nodes"][0]["source_sha256"] == digest
    assert result["edges"][0]["source_sha256"] == digest


@pytest.mark.parametrize(
    "mutate",
    [
        lambda fragment: fragment["edges"][0].update(relation="unknown_relation"),
        lambda fragment: fragment["nodes"][0].pop("source_location"),
    ],
)
def test_native_extraction_rejects_invalid_fragment_before_return(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mutate,
) -> None:
    source = tmp_path / "contract.md"
    source.write_text("alpha\nbeta\n", encoding="utf-8")
    fragment = _native_fragment("contract.md")
    mutate(fragment)
    monkeypatch.setattr(
        llm,
        "_call_openai_compat",
        lambda *args, **kwargs: fragment,
    )

    with pytest.raises(ValueError, match="semantic fragment validation failed"):
        llm.extract_files_direct(
            [source],
            backend="openai",
            api_key="test-key",
            root=tmp_path,
        )


def test_native_extraction_rejects_source_changed_during_provider_call(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "contract.md"
    source.write_text("alpha\nbeta\n", encoding="utf-8")

    def change_source(*args, **kwargs):
        source.write_text("changed\nbeta\n", encoding="utf-8")
        return _native_fragment("contract.md")

    monkeypatch.setattr(llm, "_call_openai_compat", change_source)

    with pytest.raises(ValueError, match="stale"):
        llm.extract_files_direct(
            [source],
            backend="openai",
            api_key="test-key",
            root=tmp_path,
        )


def test_native_file_slice_rejects_provenance_outside_dispatched_span(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from graphify.file_slice import FileSlice

    source = tmp_path / "contract.md"
    text = "one\ntwo\nthree\nfour\n"
    source.write_text(text, encoding="utf-8")
    first_line = FileSlice(source, 0, len("one\n"), 0, 1)
    fragment = _native_fragment("contract.md")
    for collection in ("nodes", "edges"):
        for record in fragment[collection]:
            record["source_location"] = "L3"
    monkeypatch.setattr(llm, "_call_openai_compat", lambda *args, **kwargs: fragment)

    with pytest.raises(ValueError, match="outside the dispatched source span"):
        llm.extract_files_direct(
            [first_line],
            backend="openai",
            api_key="test-key",
            root=tmp_path,
        )


def test_native_file_slice_accepts_original_file_line_span(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from graphify.file_slice import FileSlice

    source = tmp_path / "contract.md"
    text = "one\ntwo\nthree\nfour\n"
    source.write_text(text, encoding="utf-8")
    start = text.index("three")
    third_line = FileSlice(source, start, start + len("three\n"), 0, 1)
    fragment = _native_fragment("contract.md")
    for collection in ("nodes", "edges"):
        for record in fragment[collection]:
            record["source_location"] = "L3"
    monkeypatch.setattr(llm, "_call_openai_compat", lambda *args, **kwargs: fragment)

    result = llm.extract_files_direct(
        [third_line],
        backend="openai",
        api_key="test-key",
        root=tmp_path,
    )

    assert result["nodes"][0]["source_location"] == "L3"


def test_native_file_slice_rejects_citation_of_unshown_line_suffix(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from graphify.file_slice import FileSlice

    source = tmp_path / "contract.md"
    source.write_text("alpha unseen suffix\nsecond\n", encoding="utf-8")
    partial_first_line = FileSlice(source, 0, len("alpha"), 0, 1)
    fragment = _native_fragment("contract.md")
    for collection in ("nodes", "edges"):
        for record in fragment[collection]:
            record["source_location"] = "L1"
    monkeypatch.setattr(llm, "_call_openai_compat", lambda *args, **kwargs: fragment)

    with pytest.raises(ValueError, match="outside the dispatched source span"):
        llm.extract_files_direct(
            [partial_first_line],
            backend="openai",
            api_key="test-key",
            root=tmp_path,
        )


def test_native_byte_addressed_slice_cannot_cite_hidden_bytes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from graphify.file_slice import FileSlice

    source = tmp_path / "contract.md"
    source.write_bytes(b"first\n\xffhidden\nlast\n")
    first_line = FileSlice(source, 0, len("first\n"), 0, 1)
    fragment = _native_fragment("contract.md")
    for collection in ("nodes", "edges"):
        for record in fragment[collection]:
            record["source_location"] = "B7-B14"
    monkeypatch.setattr(llm, "_call_openai_compat", lambda *args, **kwargs: fragment)

    with pytest.raises(ValueError, match="outside the dispatched source span"):
        llm.extract_files_direct(
            [first_line],
            backend="openai",
            api_key="test-key",
            root=tmp_path,
        )


def test_sanitizer_does_not_fold_rationale_from_uncovered_span() -> None:
    from graphify.semantic_cleanup import sanitize_semantic_fragment

    digest = "a" * 64
    fragment = {
        "nodes": [
            {
                "id": "decision",
                "label": "Decision",
                "file_type": "document",
                "source_file": "decision.md",
                "source_location": "L1",
                "source_sha256": digest,
            },
            {
                "id": "why",
                "label": (
                    "This deliberately long rationale sentence explains why "
                    "the documented decision was selected."
                ),
                "file_type": "rationale",
                "source_file": "decision.md",
                "source_location": "L10",
                "source_sha256": digest,
            },
        ],
        "edges": [
            {
                "source": "why",
                "target": "decision",
                "relation": "rationale_for",
                "source_file": "decision.md",
                "source_location": "L10",
                "source_sha256": digest,
            }
        ],
        "hyperedges": [],
    }

    sanitized = sanitize_semantic_fragment(fragment)

    assert [node["id"] for node in sanitized["nodes"]] == ["decision"]
    assert "rationale" not in sanitized["nodes"][0]
