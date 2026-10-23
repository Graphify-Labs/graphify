"""Structural YAML extraction (#2214).

YAML was previously classified as a document, so AST-only / code-only runs
(``graphify update``) produced zero nodes from config-heavy repositories
(Helm charts, Kubernetes manifests, CI pipelines). These tests pin the new
structural path: ``.yaml``/``.yml`` classify as code and ``extract_yaml``
emits deterministic file/key nodes.
"""

from __future__ import annotations

from pathlib import Path

from graphify.detect import FileType, classify_file
from graphify.extractors.yaml_config import extract_yaml


def _write(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


def test_yaml_and_yml_classify_as_code(tmp_path):
    assert classify_file(_write(tmp_path / "values.yaml", "a: 1\n")) is FileType.CODE
    assert classify_file(_write(tmp_path / "deploy.yml", "a: 1\n")) is FileType.CODE


def test_extract_yaml_top_level_keys(tmp_path):
    path = _write(
        tmp_path / "values.yaml",
        "replicaCount: 2\nimage:\n  tag: latest\nservice:\n  port: 80\n",
    )
    result = extract_yaml(path)

    assert "error" not in result
    labels = {n["label"] for n in result["nodes"]}
    assert {"values.yaml", "replicaCount", "image", "service"} <= labels


def test_extract_yaml_nested_keys_are_contains_edges(tmp_path):
    path = _write(tmp_path / "values.yaml", "image:\n  tag: latest\n  pullPolicy: Always\n")
    result = extract_yaml(path)

    contains = [(e["source"], e["target"]) for e in result["edges"] if e["relation"] == "contains"]
    assert any("image" in source and "tag" in target for source, target in contains)
    assert any("image" in source and "pullpolicy" in target for source, target in contains)


def test_extract_yaml_ids_are_stable_across_runs(tmp_path):
    path = _write(tmp_path / "values.yaml", "a: 1\nb:\n  c: 2\n")
    first = extract_yaml(path)
    second = extract_yaml(path)
    assert [n["id"] for n in first["nodes"]] == [n["id"] for n in second["nodes"]]


def test_extract_yaml_scalar_document_is_skipped(tmp_path):
    result = extract_yaml(_write(tmp_path / "scalar.yaml", "just-a-string\n"))
    assert result.get("skipped") == "scalar yaml"


def test_extract_yaml_empty_document(tmp_path):
    result = extract_yaml(_write(tmp_path / "empty.yaml", ""))
    assert result.get("skipped") == "scalar yaml"
