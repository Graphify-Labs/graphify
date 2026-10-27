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


def test_multi_document_yaml_extracts_each_document(tmp_path):
    """A k8s-style multi-document stream (`---` separators) is the headline use
    case; each document must contribute distinct nodes rather than returning
    zero (safe_load_all, not safe_load)."""
    path = _write(
        tmp_path / "manifests.yaml",
        "apiVersion: apps/v1\nkind: Deployment\nmetadata:\n  name: web\n"
        "---\n"
        "apiVersion: v1\nkind: Service\nmetadata:\n  name: web-svc\n",
    )
    result = extract_yaml(path)
    assert "error" not in result and "skipped" not in result, result
    labels = {n["label"] for n in result["nodes"]}
    # both documents are present and kept distinct, labelled by kind + name
    assert "Deployment web" in labels
    assert "Service web-svc" in labels


def test_data_yaml_is_skipped(tmp_path):
    """A flat all-scalar data bundle with no config key (an i18n-style file) is
    skipped rather than minting orphan nodes, mirroring extract_json's gate."""
    result = extract_yaml(_write(
        tmp_path / "strings.yaml", "greeting: hello\nfarewell: goodbye\nthanks: cheers\n"))
    assert result.get("skipped") == "data yaml (not a config/manifest)"


def test_openapi_spec_yaml_is_skipped(tmp_path):
    """An OpenAPI/Swagger spec is data-heavy API description, not a config to walk."""
    result = extract_yaml(_write(
        tmp_path / "api.yaml",
        "openapi: 3.0.0\npaths:\n  /x:\n    get:\n      responses:\n        '200':\n          description: ok\n"))
    assert result.get("skipped") == "data yaml (not a config/manifest)"


def test_top_level_data_array_is_skipped(tmp_path):
    result = extract_yaml(_write(tmp_path / "list.yaml", "- one\n- two\n- three\n"))
    assert result.get("skipped") == "data yaml (not a config/manifest)"


def test_unsafe_yaml_tag_does_not_execute(tmp_path):
    """extract_yaml must use safe_load (never load): a `!!python/...` tag raises
    instead of executing arbitrary code on an untrusted repo."""
    marker = tmp_path / "pwned"
    path = _write(
        tmp_path / "evil.yaml",
        f"danger: !!python/object/apply:os.system ['touch {marker}']\n",
    )
    result = extract_yaml(path)
    assert "error" in result
    assert not marker.exists(), "safe_load must not execute the python tag"


def test_extract_yaml_caps_bound_output(tmp_path):
    """A config-named YAML with thousands of keys is bounded by the 500-pair cap."""
    body = "root:\n" + "".join(f"  k{i}: {i}\n" for i in range(2000))
    result = extract_yaml(_write(tmp_path / "values.yaml", body))
    assert len(result["nodes"]) <= 502  # file node + root key + at most 500 pairs
