from __future__ import annotations

from pathlib import Path

import pytest

from graphify.extract import extract
from graphify.rcfile import activate_language_overrides, generated_sources_for, load_graphifyrc


def _write_project(root: Path) -> tuple[Path, Path, Path]:
    src = root / "src"
    deploy = root / "deploy"
    src.mkdir()
    deploy.mkdir()
    a = src / "a.js"
    b = src / "b.js"
    bundle = deploy / "bundle.js"
    a.write_text("function caller() { return helper(); }\n", encoding="utf-8")
    b.write_text("function helper() { return 42; }\n", encoding="utf-8")
    bundle.write_text(
        "function caller() { return helper(); }\n"
        "function helper() { return 42; }\n",
        encoding="utf-8",
    )
    (root / ".graphifyrc").write_text(
        "generated.deploy/bundle.js=src/a.js,src/b.js\n",
        encoding="utf-8",
    )
    return a, b, bundle


def test_graphifyrc_parses_generated_sources(tmp_path):
    (tmp_path / ".graphifyrc").write_text(
        "generated.deploy/bundle.js=src/a.js, src/b.js\n",
        encoding="utf-8",
    )
    assert load_graphifyrc(tmp_path) == {
        "generated": {"deploy/bundle.js": ["src/a.js", "src/b.js"]}
    }


@pytest.mark.parametrize(
    "line",
    [
        "generated../bundle.js=src/a.js\n",
        "generated./abs.js=C:/src/a.js\n",
        "generated.dist/*.js=src/a.js\n",
        "generated.deploy/bundle.js=../src/a.js\n",
        "generated.deploy/bundle.js=src/*.js\n",
        "generated.deploy/bundle.js=\n",
    ],
)
def test_graphifyrc_rejects_unsafe_generated_paths(tmp_path, line):
    (tmp_path / ".graphifyrc").write_text(line, encoding="utf-8")
    with pytest.raises(ValueError):
        load_graphifyrc(tmp_path)


def test_generated_artifact_absolute_paths_under_symlinked_root(tmp_path):
    real_root = tmp_path / "real"
    real_root.mkdir()
    _write_project(real_root)
    linked_root = tmp_path / "linked"
    try:
        linked_root.symlink_to(real_root, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"symlinks unavailable: {exc}")

    result = extract(
        [
            linked_root / "src" / "a.js",
            linked_root / "src" / "b.js",
            linked_root / "deploy" / "bundle.js",
        ],
        root=linked_root,
        cache_root=linked_root,
        parallel=False,
    )

    generated_nodes = [
        node for node in result["nodes"]
        if node.get("source_file") == "deploy/bundle.js"
    ]
    assert [node.get("label") for node in generated_nodes] == ["bundle.js"]
    assert generated_nodes[0]["generated"] is True


def test_generated_sources_for_accepts_cwd_relative_path(tmp_path, monkeypatch):
    root = tmp_path / "project"
    root.mkdir()
    _write_project(root)
    activate_language_overrides(root)
    try:
        monkeypatch.chdir(tmp_path)
        candidate = Path(root.name) / "deploy" / "bundle.js"
        assert generated_sources_for(candidate) == ("src/a.js", "src/b.js")
    finally:
        activate_language_overrides(tmp_path)


def test_generated_artifact_keeps_file_node_but_not_copied_symbols(tmp_path):
    a, b, bundle = _write_project(tmp_path)

    result = extract(
        [a, b, bundle],
        root=tmp_path,
        cache_root=tmp_path,
        parallel=False,
    )

    generated_nodes = [
        node for node in result["nodes"]
        if node.get("source_file") == "deploy/bundle.js"
    ]
    assert len(generated_nodes) == 1
    assert generated_nodes[0]["label"] == "bundle.js"
    assert generated_nodes[0]["generated"] is True

    canonical_labels = {
        node.get("label")
        for node in result["nodes"]
        if node.get("source_file") in {"src/a.js", "src/b.js"}
    }
    assert "caller()" in canonical_labels
    assert "helper()" in canonical_labels

    provenance = [
        edge for edge in result["edges"]
        if edge.get("relation") == "generated_from"
    ]
    assert len(provenance) == 2
    assert {edge["source_file"] for edge in provenance} == {"deploy/bundle.js"}
    assert {edge["target"] for edge in provenance} == {"src_a", "src_b"}
    assert all(edge.get("confidence") == "EXTRACTED" for edge in provenance)

    assert set(result["extracted_sources"]) == {str(a), str(b), str(bundle)}


def test_generated_artifact_incremental_result_preserves_provenance(tmp_path):
    a, b, bundle = _write_project(tmp_path)
    full = extract(
        [a, b, bundle],
        root=tmp_path,
        cache_root=tmp_path,
        parallel=False,
    )
    canonical_context = [
        node for node in full["nodes"]
        if node.get("source_file") in {"src/a.js", "src/b.js"}
    ]

    result = extract(
        [bundle],
        root=tmp_path,
        cache_root=tmp_path,
        parallel=False,
        resolution_context_nodes=canonical_context,
    )

    assert [node.get("label") for node in result["nodes"]] == ["bundle.js"]
    assert {edge["target"] for edge in result["edges"] if edge.get("relation") == "generated_from"} == {
        "src_a",
        "src_b",
    }
    assert result["extracted_sources"] == [str(bundle)]


def test_incremental_merge_evicts_preexisting_generated_symbols(tmp_path):
    import json

    from graphify.build import merge_raw_extraction

    src = tmp_path / "src"
    deploy = tmp_path / "deploy"
    src.mkdir()
    deploy.mkdir()
    a = src / "a.js"
    b = src / "b.js"
    bundle = deploy / "bundle.js"
    a.write_text("function caller() { return helper(); }\n", encoding="utf-8")
    b.write_text("function helper() { return 42; }\n", encoding="utf-8")
    bundle.write_text(
        "function caller() { return helper(); }\n"
        "function helper() { return 42; }\n",
        encoding="utf-8",
    )

    baseline = extract(
        [a, b, bundle],
        root=tmp_path,
        cache_root=tmp_path,
        parallel=False,
    )
    assert sum(
        node.get("source_file") == "deploy/bundle.js"
        for node in baseline["nodes"]
    ) == 3

    graph_path = tmp_path / "graph.json"
    graph_path.write_text(
        json.dumps({
            "directed": False,
            "nodes": baseline["nodes"],
            "links": baseline["edges"],
        }),
        encoding="utf-8",
    )

    (tmp_path / ".graphifyrc").write_text(
        "generated.deploy/bundle.js=src/a.js,src/b.js\n",
        encoding="utf-8",
    )
    canonical_context = [
        node for node in baseline["nodes"]
        if node.get("source_file") in {"src/a.js", "src/b.js"}
    ]
    fresh = extract(
        [bundle],
        root=tmp_path,
        cache_root=tmp_path,
        parallel=False,
        resolution_context_nodes=canonical_context,
    )
    merged = merge_raw_extraction(fresh, graph_path, root=tmp_path)

    generated_nodes = [
        node for node in merged["nodes"]
        if node.get("source_file") == "deploy/bundle.js"
    ]
    assert [node["label"] for node in generated_nodes] == ["bundle.js"]
    assert generated_nodes[0]["generated"] is True
    assert {node["id"] for node in merged["nodes"] if node.get("source_file") == "src/a.js"} >= {
        "src_a",
        "src_a_caller",
    }
    assert {node["id"] for node in merged["nodes"] if node.get("source_file") == "src/b.js"} >= {
        "src_b",
        "src_b_helper",
    }
    assert {
        (edge["source"], edge["target"])
        for edge in merged["edges"]
        if edge.get("relation") == "generated_from"
    } == {
        ("deploy_bundle", "src_a"),
        ("deploy_bundle", "src_b"),
    }


def test_generated_config_transition_requeues_only_the_artifact(tmp_path):
    from graphify.detect import detect_incremental, save_manifest

    src = tmp_path / "src"
    deploy = tmp_path / "deploy"
    src.mkdir()
    deploy.mkdir()
    a = src / "a.js"
    b = src / "b.js"
    bundle = deploy / "bundle.js"
    a.write_text("function caller() { return helper(); }\n", encoding="utf-8")
    b.write_text("function helper() { return 42; }\n", encoding="utf-8")
    bundle.write_text("function caller() { return helper(); }\nfunction helper() { return 42; }\n", encoding="utf-8")
    files = {"code": [str(a), str(b), str(bundle)]}
    manifest = tmp_path / "graphify-out" / "manifest.json"

    save_manifest(files, str(manifest), kind="both", root=tmp_path)
    assert detect_incremental(tmp_path, str(manifest), kind="ast")["new_files"]["code"] == []

    rc = tmp_path / ".graphifyrc"
    rc.write_text("generated.deploy/bundle.js=src/a.js,src/b.js\n", encoding="utf-8")
    pending = {
        Path(path).relative_to(tmp_path).as_posix()
        for path in detect_incremental(tmp_path, str(manifest), kind="ast")["new_files"]["code"]
    }
    assert pending == {"deploy/bundle.js"}

    save_manifest(files, str(manifest), kind="both", root=tmp_path)
    assert detect_incremental(tmp_path, str(manifest), kind="ast")["new_files"]["code"] == []

    rc.write_text("generated.deploy/bundle.js=src/b.js\n", encoding="utf-8")
    changed_sources = {
        Path(path).relative_to(tmp_path).as_posix()
        for path in detect_incremental(tmp_path, str(manifest), kind="ast")["new_files"]["code"]
    }
    assert changed_sources == {"deploy/bundle.js"}

    save_manifest(files, str(manifest), kind="both", root=tmp_path)
    rc.unlink()
    removed = {
        Path(path).relative_to(tmp_path).as_posix()
        for path in detect_incremental(tmp_path, str(manifest), kind="ast")["new_files"]["code"]
    }
    assert removed == {"deploy/bundle.js"}



def test_missing_generated_artifact_is_not_fabricated(tmp_path):
    missing = tmp_path / "deploy" / "bundle.js"
    (tmp_path / "deploy").mkdir()
    (tmp_path / ".graphifyrc").write_text(
        "generated.deploy/bundle.js=src/a.js\n",
        encoding="utf-8",
    )

    result = extract(
        [missing],
        root=tmp_path,
        cache_root=tmp_path,
        parallel=False,
    )

    assert not any(node.get("source_file") == "deploy/bundle.js" for node in result["nodes"])
    assert not any(edge.get("relation") == "generated_from" for edge in result["edges"])


def test_missing_declared_source_omits_dangling_provenance(tmp_path, capsys):
    deploy = tmp_path / "deploy"
    deploy.mkdir()
    bundle = deploy / "bundle.js"
    bundle.write_text("function generatedOnly() {}\n", encoding="utf-8")
    (tmp_path / ".graphifyrc").write_text(
        "generated.deploy/bundle.js=src/missing.js\n",
        encoding="utf-8",
    )

    result = extract(
        [bundle],
        root=tmp_path,
        cache_root=tmp_path,
        parallel=False,
    )

    generated = [node for node in result["nodes"] if node.get("source_file") == "deploy/bundle.js"]
    assert len(generated) == 1
    assert generated[0]["generated"] is True
    assert not any(edge.get("relation") == "generated_from" for edge in result["edges"])
    assert "src/missing.js" in capsys.readouterr().err
