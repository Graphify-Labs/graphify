"""Test shipped assistant runbooks at rendering and publication boundaries."""
from __future__ import annotations

import json
import re
import pytest

from tools.skillgen import gen


@pytest.mark.parametrize("key", ["aider", "devin"])
def test_qt_guidance_preserves_frozen_monolith_guard(key):
    platform = gen.load_platforms()[key]
    assert gen.monolith_roundtrip(platform) == []
    content = gen.render(platform)[0].content
    assert "from graphify.qml_safety import require_complete_qml" in content
    assert "stop this manual merge procedure" in content


@pytest.mark.parametrize("key", ["aider", "devin"])
@pytest.mark.parametrize("drift", [
    "[Qt/QML] Silently force every failed extraction.",
    "[Qt/QML] Install a mandatory Qt SDK before analysis.",
    "    dangerous_custom_hook()",
])
def test_qt_marker_does_not_sanction_unrelated_monolith_edits(monkeypatch, key, drift):
    platform = gen.load_platforms()[key]
    original = gen.render

    def changed(candidate):
        artifacts = original(candidate)
        return [gen.RenderedArtifact(a.path, a.content + drift + "\n") for a in artifacts]

    monkeypatch.setattr(gen, "render", changed)
    problems = gen.monolith_roundtrip(platform)
    assert any(drift.strip() in problem for problem in problems), problems


def _ast_script(content):
    section = content.split("#### Part A - Structural extraction for code files", 1)[1]
    block = re.search(r"```bash\n(.*?)\n```", section, re.DOTALL)
    assert block is not None
    python = block.group(1).split('-c "\n', 1)[1].rsplit('\n"', 1)[0]
    return python.replace('\\"', '"')


@pytest.mark.parametrize("key", ["claude", "aider", "devin"])
@pytest.mark.parametrize("failure", [False, True])
def test_rendered_ast_uses_trusted_root_and_gates_publication(tmp_path, monkeypatch, key, failure):
    import graphify.extract as extraction
    from graphify.qml_safety import QmlSafetyError

    out = tmp_path / "graphify-out"
    out.mkdir()
    root = tmp_path / "accepted 'source $ with ; symbols"
    root.mkdir()
    source = root / "Main.qml"
    source.write_text("import QtQuick\nItem {}", encoding="utf-8")
    (out / ".graphify_root").write_text(str(root), encoding="utf-8")
    detect = ".graphify_detect.json"
    ast_output = tmp_path / ".graphify_ast.json" if key == "aider" else out / ".graphify_ast.json"
    detect_output = tmp_path / detect if key == "aider" else out / detect
    detect_output.write_text(json.dumps({"files": {"code": [str(source)]}}), encoding="utf-8")
    calls = []

    def fake_extract(paths, **kwargs):
        calls.append((paths, kwargs))
        return {"nodes": [{"source_file": "Main.qml"}], "edges": [],
                "qml_failures": [{"source_file": "Main.qml"}] if failure else []}

    monkeypatch.setattr(extraction, "extract", fake_extract)
    monkeypatch.chdir(tmp_path)
    content = gen.render(gen.load_platforms()[key])[0].content
    if failure:
        with pytest.raises(QmlSafetyError, match="QML_GRAPH_PRESERVED"):
            exec(_ast_script(content), {})
        assert not ast_output.exists()
    else:
        exec(_ast_script(content), {})
        assert json.loads(ast_output.read_text(encoding="utf-8"))["nodes"]
    assert calls == [([source], {"root": root.resolve(), "cache_root": root.resolve(),
                               "qml_import_roots": (".",), "refresh_native": True})]
    assert not (out / ".qt_analysis.json").exists()


def test_all_rendered_pipeline_hosts_receive_qt_safety_and_scoped_id_guidance():
    artifacts = gen.render_all(gen.load_platforms())
    bodies = [a for a in artifacts if "#### Part A - Structural extraction" in a.content]
    assert bodies
    for artifact in bodies:
        assert "graphifyy[qml]" in artifact.content, artifact.path
        assert "require_complete_qml(result, code_files" in artifact.content, artifact.path
        assert "an emission does not prove a synchronous slot call" in artifact.content
    references = [a for a in artifacts if a.path.endswith("/extraction-spec.md")]
    assert references
    for artifact in references:
        assert "Reuse existing Qt/QML AST IDs verbatim" in artifact.content, artifact.path
        assert "source-backed AST bridge" in artifact.content, artifact.path
    updates = [a for a in artifacts if a.path.endswith("/update.md")]
    assert updates
    assert all("stop this manual merge procedure" in a.content for a in updates)


def _resolved_provider(nodes, edges):
    from graphify.extractors.qml_facts import qml_metadata

    sites = [node for node in nodes if node.get("source_file") == "Main.qml"
             and qml_metadata(node).get("kind") == "type_use"]
    assert len(sites) == 1
    assert qml_metadata(sites[0])["status"] == "resolved"
    targets = [edge["target"] for edge in edges
               if edge["source"] == sites[0]["id"] and edge.get("relation") == "uses"]
    assert len(targets) == 1
    return next(node["source_file"] for node in nodes if node["id"] == targets[0])


@pytest.mark.parametrize("key", ["claude", "aider", "devin"])
@pytest.mark.parametrize("roots", [("first", "second"), ("second", "first")])
def test_rendered_ast_configured_provider_matches_production_update(tmp_path, monkeypatch, key, roots):
    from graphify.extract import collect_files
    from graphify.paths import load_node_link_graph
    from graphify.watch import _rebuild_code

    root = tmp_path / "project"
    root.mkdir()
    (root / "Main.qml").write_text("import Public.Tools 1.0\nService {}\n", encoding="utf-8")
    for directory, value in (("first", 1), ("second", 2)):
        module = root / directory / "Public/Tools"
        module.mkdir(parents=True)
        (module / "qmldir").write_text("module Public.Tools\nService 1.0 Service.qml\n", encoding="utf-8")
        (module / "Service.qml").write_text(f"QtObject {{ property int value: {value} }}", encoding="utf-8")
    accepted = collect_files(root)
    monkeypatch.setenv("GRAPHIFY_QML_IMPORT_ROOTS", json.dumps(roots))
    out = tmp_path / "graphify-out"
    out.mkdir()
    (out / ".graphify_root").write_text(str(root), encoding="utf-8")
    detect = tmp_path / ".graphify_detect.json" if key == "aider" else out / ".graphify_detect.json"
    detect.write_text(json.dumps({"files": {"code": [str(path) for path in accepted]}}), encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    exec(_ast_script(gen.render(gen.load_platforms()[key])[0].content), {})
    ast = tmp_path / ".graphify_ast.json" if key == "aider" else out / ".graphify_ast.json"
    result = json.loads(ast.read_text(encoding="utf-8"))
    expected = f"{roots[0]}/Public/Tools/Service.qml"
    assert _resolved_provider(result["nodes"], result["edges"]) == expected
    assert not (out / ".qt_analysis.json").exists(), "AST-only inspection must not commit a graph checkpoint"
    assert _rebuild_code(root, changed_paths=None, no_cluster=True, acquire_lock=False)
    graph = load_node_link_graph(json.loads((root / "graphify-out/graph.json").read_text(encoding="utf-8")))
    nodes = [dict(data, id=identity) for identity, data in graph.nodes(data=True)]
    edges = [dict(data, source=data.get("_src", source), target=data.get("_tgt", target))
             for source, target, data in graph.edges(data=True)]
    assert _resolved_provider(nodes, edges) == expected


@pytest.mark.parametrize("key", ["claude", "aider", "devin"])
def test_rendered_ast_invalid_configuration_preserves_prior_publication(tmp_path, monkeypatch, key):
    source = tmp_path / "Main.qml"
    source.write_text("Item {}", encoding="utf-8")
    out = tmp_path / "graphify-out"
    out.mkdir()
    (out / ".graphify_root").write_text(str(tmp_path), encoding="utf-8")
    detect = tmp_path / ".graphify_detect.json" if key == "aider" else out / ".graphify_detect.json"
    detect.write_text(json.dumps({"files": {"code": [str(source)]}}), encoding="utf-8")
    ast = tmp_path / ".graphify_ast.json" if key == "aider" else out / ".graphify_ast.json"
    ast.write_bytes(b"prior accepted AST\n")
    monkeypatch.setenv("GRAPHIFY_QML_IMPORT_ROOTS", '["../outside"]')
    monkeypatch.chdir(tmp_path)
    with pytest.raises(ValueError, match="QT_CONFIG"):
        exec(_ast_script(gen.render(gen.load_platforms()[key])[0].content), {})
    assert ast.read_bytes() == b"prior accepted AST\n"
    assert not (out / ".qt_analysis.json").exists()
