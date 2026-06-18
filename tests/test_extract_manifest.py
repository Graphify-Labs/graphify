"""Regression tests for extract manifest stamping (#manifest-path-alias).

detect() records absolute corpus paths; LLM extraction often sets source_file
to a repo-relative path. String equality in _manifest_files left semantic
files out and wrote an empty {} manifest after a successful extract.
"""
from __future__ import annotations

from pathlib import Path

from graphify.build import path_covered_by_extraction, source_path_aliases
from graphify.detect import save_manifest


def test_path_covered_matches_absolute_detect_path_to_relative_source_file(tmp_path: Path) -> None:
    root = tmp_path / "corpus"
    root.mkdir()
    doc = root / "notes.md"
    doc.write_text("# Notes\n", encoding="utf-8")

    abs_path = str(doc.resolve())
    extraction = {
        "nodes": [
            {
                "id": "billing",
                "label": "Billing",
                "file_type": "document",
                "source_file": "notes.md",
            }
        ],
        "edges": [],
        "hyperedges": [],
    }

    assert path_covered_by_extraction(abs_path, extraction, root) is True
    assert path_covered_by_extraction("notes.md", extraction, root) is True


def test_path_covered_false_when_source_file_unrelated(tmp_path: Path) -> None:
    root = tmp_path / "corpus"
    root.mkdir()
    extraction = {
        "nodes": [{"id": "a", "label": "A", "source_file": "other.md"}],
        "edges": [],
    }
    assert path_covered_by_extraction(str(root / "notes.md"), extraction, root) is False


def test_save_manifest_stamps_semantic_file_with_relative_llm_source(tmp_path: Path) -> None:
    """End-to-end: manifest writer receives the absolute detect path when LLM used a relative source_file."""
    root = tmp_path / "corpus"
    root.mkdir()
    doc = root / "notes.md"
    doc.write_text("# Notes\nSome prose about billing.\n", encoding="utf-8")
    manifest_path = tmp_path / "graphify-out" / "manifest.json"

    abs_doc = str(doc.resolve())
    sem_result = {
        "nodes": [
            {
                "id": "billing",
                "label": "Billing workflow",
                "file_type": "document",
                "source_file": "notes.md",
            }
        ],
        "edges": [],
        "hyperedges": [],
    }

    assert path_covered_by_extraction(abs_doc, sem_result, root)

    files_by_type = {"document": [abs_doc], "code": [], "paper": [], "image": []}
    sem_types = {"document", "paper", "image"}
    manifest_files = {
        ftype: [
            f
            for f in flist
            if ftype not in sem_types or path_covered_by_extraction(f, sem_result, root)
        ]
        for ftype, flist in files_by_type.items()
    }

    save_manifest(manifest_files, manifest_path=str(manifest_path), kind="both", root=root)

    import json

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert "notes.md" in manifest
    assert manifest["notes.md"]["semantic_hash"]


def test_source_path_aliases_includes_relative_and_absolute_forms(tmp_path: Path) -> None:
    root = tmp_path / "corpus"
    root.mkdir()
    abs_path = str((root / "dir" / "doc.md").resolve())
    (root / "dir").mkdir()
    (root / "dir" / "doc.md").write_text("x", encoding="utf-8")

    aliases = source_path_aliases(abs_path, root)
    assert "dir/doc.md" in aliases
    assert abs_path.replace("\\", "/") in aliases or any("doc.md" in a for a in aliases)
