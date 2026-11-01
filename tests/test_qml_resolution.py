"""QML-004 production lookup/projection acceptance and corpus-boundary negatives."""

import copy
import json
from pathlib import Path

import pytest

from graphify.extractors.qml_facts import qml_metadata
from graphify.qml_resolution import build_qml_index, resolve_qml_project
from tests.qml_resolution_helpers import component_key, index_for, module, named


def test_aliased_directory_and_uri_imports_do_not_cross_bind(tmp_path):
    """AC01/02: same-label exports remain distinct under document-local aliases."""
    sources = {**module("Public.One"), **module("Public.Two"),
               "local/Button.qml": "QtObject {}",
               "Main.qml": 'import Public.One 1.0 as One\nimport Public.Two 1.0 as Two\nimport "local" as Local\nOne.Button {}',
               "Other.qml": "QtObject {}"}
    index, _, nodes, _ = index_for(tmp_path, sources)
    scope = component_key(nodes)
    for qualified, target in [("One.Button", "Public/One/Button.qml"),
                              ("Two.Button", "Public/Two/Button.qml"), ("Local.Button", "local/Button.qml")]:
        result = index.resolve_type("Main.qml", scope, qualified)
        assert result.target_id == named(nodes, target, "component")["id"]
        assert result.evidence
    assert index.resolve_type("Main.qml", scope, "Button").status == "unavailable"
    assert index.resolve_type("Other.qml", component_key(nodes, "Other.qml"), "One.Button").status == "unavailable"


def test_version_availability_and_latest_compatible_export(tmp_path):
    """AC01/02/03: available module version precedes per-type introduction lookup."""
    sources = {"Public/Tools/qmldir": "module Public.Tools\nButton 1.0 Old.qml\nButton 1.1 New.qml\nWindow 1.2 Window.qml",
               "Public/Tools/Old.qml": "QtObject {}", "Public/Tools/New.qml": "QtObject {}",
               "Public/Tools/Window.qml": "QtObject {}", "Main.qml": "QtObject {}"}
    index, _, nodes, _ = index_for(tmp_path, sources)
    for major, minor, target in [(1, 0, "Old.qml"), (1, 2, "New.qml"), (1, None, "New.qml"), (None, None, "New.qml")]:
        result = index.module_type("Public.Tools", major, minor, "Button", importer="Main.qml")
        assert result.target_id == named(nodes, "Public/Tools/" + target, "component")["id"]
    for major, minor in [(1, 3), (2, 0)]:
        result = index.module_type("Public.Tools", major, minor, "Button", importer="Main.qml")
        assert result.status == "unavailable"
        assert result.reason == "module_version_unavailable"


def test_competing_providers_and_missing_modules_have_no_target_edges(tmp_path):
    """AC03: source-owned unresolved sites survive, arbitrary targets never do."""
    sources = {**module("Public.One"), **module("Public.Two"),
               "Main.qml": "import Public.One 1.0\nimport Public.Two 1.0\nimport Missing.Api 1.0\nButton {}"}
    _, per_file, nodes, edges = index_for(tmp_path, sources)
    resolve_qml_project(per_file, nodes, edges, root=tmp_path)
    site = named(nodes, "Main.qml", "type_use")
    assert qml_metadata(site)["status"] == "ambiguous"
    assert len(qml_metadata(site)["candidates"]) == 2
    assert not any(edge["source"] == site["id"] and edge["relation"] == "uses" for edge in edges)
    missing = [node for node in nodes if qml_metadata(node).get("kind") == "import_resolution" and
               node["label"] == "Missing.Api"][0]
    assert qml_metadata(missing)["reason"] == "module_not_in_import_roots"
    assert not any(edge["source"] == missing["id"] and edge["relation"] == "imports" for edge in edges)


def test_declared_roots_and_remote_import_never_expand_corpus(tmp_path, monkeypatch):
    """AC04: accepted facts are the complete source set, independent of disk files."""
    sources = {"src/Public/Tools/qmldir": "module Public.Tools\nButton 1.0 Button.qml",
               "src/Public/Tools/Button.qml": "QtObject {}",
               "unrelated/Button.qml": "QtObject {}",
               "Main.qml": 'import Public.Tools 1.0\nimport "https://invalid.example/source" as Remote\nButton {}'}
    index, per_file, nodes, edges = index_for(tmp_path, sources)
    scope = component_key(nodes)
    assert index.resolve_type("Main.qml", scope, "Button").status == "unavailable"
    index = build_qml_index(nodes, edges, root=tmp_path, import_roots=["src", "../outside"])
    assert index.resolve_type("Main.qml", scope, "Button").target_id == named(nodes, "src/Public/Tools/Button.qml", "component")["id"]
    def forbidden(*args, **kwargs):
        raise AssertionError("Resolver attempted source expansion")
    monkeypatch.setattr(Path, "read_text", forbidden)
    monkeypatch.setattr(Path, "read_bytes", forbidden)
    import socket
    monkeypatch.setattr(socket, "create_connection", forbidden)
    resolve_qml_project(per_file, nodes, edges, root=tmp_path, import_roots=["src"])
    remote = [node for node in nodes if qml_metadata(node).get("kind") == "import_resolution" and
              node["label"].startswith("https:")][0]
    assert qml_metadata(remote)["reason"] == "import_outside_corpus"


def test_projection_is_repeatable_owned_and_json_portable(tmp_path):
    """Derived sites preserve roles without changing borrowed declarations/context."""
    _, per_file, nodes, edges = index_for(tmp_path, {**module("Public.One"),
        "Main.qml": "import Public.One 1.0\nButton {}"})
    before = copy.deepcopy(nodes)
    fresh = {path: value for path, value in per_file.items() if path.name == "Main.qml"}
    resolve_qml_project(fresh, nodes, edges, root=tmp_path)
    assert nodes[:len(before)] == before
    count = (len(nodes), len(edges))
    resolve_qml_project(fresh, nodes, edges, root=tmp_path)
    assert (len(nodes), len(edges)) == count
    payload = json.loads(json.dumps({"nodes": nodes, "edges": edges}))
    index = build_qml_index(payload["nodes"], payload["edges"], root=tmp_path / "relocated")
    assert index.resolve_type("Main.qml", component_key(nodes), "Button").status == "resolved"
    endpoints = {node["id"] for node in nodes}
    assert all(edge["source"] in endpoints and edge["target"] in endpoints for edge in edges)
    assert all(qml_metadata(node).get("kind") not in {"type_use", "import_resolution"} or
               node["source_file"] == "Main.qml" for node in nodes)


def test_module_import_auto_visibility_and_dependency_non_visibility(tmp_path):
    """Imported module exports enter the namespace; packaging depends does not."""
    sources = {**module("Public.Base"), "Public/Facade/qmldir": "module Public.Facade\nMarker 1.0 Marker.qml\nimport Public.Base auto",
               "Public/Facade/Marker.qml": "QtObject {}", "Public/OnlyDepends/qmldir":
               "module Public.OnlyDepends\nMarker 1.0 Marker.qml\ndepends Public.Base 1.0",
               "Public/OnlyDepends/Marker.qml": "QtObject {}", "Main.qml": "QtObject {}"}
    index, _, nodes, _ = index_for(tmp_path, sources)
    expected = named(nodes, "Public/Base/Button.qml", "component")["id"]
    assert index.module_type("Public.Facade", 1, 0, "Button", importer="Main.qml").target_id == expected
    assert index.module_type("Public.OnlyDepends", 1, 0, "Button", importer="Main.qml").status == "unavailable"


def test_versioned_layout_and_missing_version_evidence(tmp_path):
    """Declared versioned roots and exact module-version evidence govern selection."""
    sources = {"Public/Tools.1/qmldir": "module Public.Tools\nButton 1.0 Major.qml",
               "Public/Tools.1/Major.qml": "QtObject {}", "Public/Tools.1.0/qmldir":
               "module Public.Tools\nButton 1.0 Exact.qml", "Public/Tools.1.0/Exact.qml": "QtObject {}",
               "Public/Unversioned/qmldir": "module Public.Unversioned\nButton Button.qml",
               "Public/Unversioned/Button.qml": "QtObject {}", "Main.qml": "QtObject {}"}
    index, _, nodes, _ = index_for(tmp_path, sources)
    assert index.module_type("Public.Tools", 1, 0, "Button", importer="Main.qml").target_id == named(nodes, "Public/Tools.1.0/Exact.qml", "component")["id"]
    assert index.module_type("Public.Unversioned", 1, 0, "Button", importer="Main.qml").reason == "module_version_unavailable"
    assert index.module_type("Public.Unversioned", None, None, "Button", importer="Main.qml").status == "resolved"


@pytest.mark.parametrize("directed", [False, True])
def test_projection_graph_build_export_reload_preserves_all_site_roles(tmp_path, directed):
    """Independent import/type sites survive the actual simple graph and JSON export."""
    from graphify.build import build_from_json
    from graphify.export import to_json
    from graphify.paths import load_node_link_graph
    _, per_file, nodes, edges = index_for(tmp_path, {**module("Public.One"),
        "Main.qml": "import Public.One 1.0\nButton { Button {} }"})
    resolve_qml_project(per_file, nodes, edges, root=tmp_path)
    graph = build_from_json({"nodes": nodes, "edges": edges}, directed=directed, root=tmp_path)
    def mechanism(source, target, relation):
        endpoints = (source, target) if directed else tuple(sorted((source, target)))
        return endpoints, relation
    expected = {mechanism(edge["source"], edge["target"], edge["relation"]) for edge in edges}
    assert {mechanism(source, target, data["relation"]) for source, target, data in graph.edges(data=True)} == expected
    target = tmp_path / "roundtrip.json"
    assert to_json(graph, {}, str(target))
    restored = load_node_link_graph(json.loads(target.read_text()))
    assert {mechanism(source, target, data["relation"]) for source, target, data in restored.edges(data=True)} == expected
    assert len([nid for nid in restored if qml_metadata(restored.nodes[nid]).get("kind") == "type_use" and
                restored.nodes[nid]["source_file"] == "Main.qml"]) == 2


def test_directory_and_script_projection_and_ignored_disk_provider(tmp_path):
    """Import roles select accepted namespaces/files; ignored disk data stays invisible."""
    sources = {"local/Widget.qml": "QtObject {}", "helpers.js": "function answer() { return 42; }",
               "Main.qml": 'import "local" as Local\nimport "helpers.js" as Helpers\nimport Ignored.Api 1.0\nLocal.Widget {}'}
    _, per_file, nodes, edges = index_for(tmp_path, sources)
    excluded = tmp_path / "Ignored/Api"
    excluded.mkdir(parents=True)
    (excluded / "qmldir").write_text("module Ignored.Api\nWidget 1.0 Widget.qml")
    (excluded / "Widget.qml").write_text("QtObject {}")
    resolve_qml_project(per_file, nodes, edges, root=tmp_path)
    for literal, target_kind in [("local", "directory_namespace"), ("helpers.js", None)]:
        site = [node for node in nodes if qml_metadata(node).get("kind") == "import_resolution" and node["label"] == literal][0]
        resolved = [edge["target"] for edge in edges if edge["source"] == site["id"] and edge["relation"] == "imports"]
        assert len(resolved) == 1
        target = next(node for node in nodes if node["id"] == resolved[0])
        assert qml_metadata(target).get("kind") == target_kind
    ignored = [node for node in nodes if qml_metadata(node).get("kind") == "import_resolution" and node["label"] == "Ignored.Api"][0]
    assert qml_metadata(ignored)["status"] == "unavailable"


def test_recursive_module_queries_are_bounded_and_resource_prefer_is_explicit(tmp_path, monkeypatch):
    """Metadata cycles, branch limits and resource redirection never guess providers."""
    sources = {**module("Public.Base"), "Public/Facade/qmldir": "module Public.Facade\nMarker 1.0 Marker.qml\nimport Public.Base auto",
               "Public/Facade/Marker.qml": "QtObject {}", "Public/Resources/qmldir":
               "module Public.Resources\nWidget 1.0 Widget.qml\nprefer :/resources/", "Public/Resources/Widget.qml": "QtObject {}"}
    index, _, _, _ = index_for(tmp_path, sources)
    assert index.module_type("Public.Resources", 1, 0, "Widget", importer="Main.qml").reason == "preferred_path_requires_resource_index"
    monkeypatch.setattr("graphify.qml_module_index.MAX_MODULE_RESOLUTION_STEPS", 1)
    assert index.module_type("Public.Facade", 1, 0, "Button", importer="Main.qml").reason == "module_resolution_work_limit"


def test_module_script_exports_have_separate_lookup_roles(tmp_path):
    """A script namespace cannot satisfy an object type use with the same spelling."""
    sources = {"Public/Tools/qmldir": "module Public.Tools\nHelpers 1.0 helpers.js",
               "Public/Tools/helpers.js": "function answer() { return 42; }", "Main.qml": "QtObject {}"}
    index, _, _, _ = index_for(tmp_path, sources)
    assert index.module_type("Public.Tools", 1, 0, "Helpers", importer="Main.qml").status == "unavailable"
    assert index.module_script("Public.Tools", 1, 0, "Helpers", importer="Main.qml").status == "resolved"
