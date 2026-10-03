"""Real QML-02 admission, project joins, workers and conservative update parity."""
from __future__ import annotations

import copy
import json

import pytest

import graphify.extract as ex
from graphify.build import build_from_json
from graphify.detect import FileType, classify_file
from graphify.export import to_json
from graphify.extractors.qml_facts import qml_metadata
from graphify.extractors.qml_metadata import extract_qmldir
from graphify.paths import load_node_link_graph
from graphify.watch import _rebuild_code
from tests.qml_test_helpers import canonical, write_qml


def project(root):
    """Two accepted providers let a qmldir-only edit change an unchanged caller's target."""
    write_qml(root, "Public/Tools/Old.qml", "QtObject { property int oldValue: 1 }\n")
    write_qml(root, "Public/Tools/New.qml", "QtObject { property int newValue: 2 }\n")
    metadata = root / "Public/Tools/qmldir"
    metadata.write_text("module Public.Tools\nButton 1.0 Old.qml\n", encoding="utf-8")
    write_qml(root, source="import Public.Tools 1.0\nButton { id: root }\n")
    return metadata


def type_target(result, file="Main.qml", label="Button"):
    """Follow the actual source-owned resolution site to its exact provider endpoint."""
    site = [node for node in result["nodes"] if node["source_file"] == file and
            qml_metadata(node).get("kind") == "type_use" and node["label"] == label]
    assert len(site) == 1 and qml_metadata(site[0])["status"] == "resolved"
    links = [edge for edge in result["edges"] if edge["source"] == site[0]["id"] and edge["relation"] == "uses"]
    assert len(links) == 1
    return links[0]["target"]


def portable_graph(graph):
    """Compare promised QML facts, excluding writer-owned community/timestamp fields."""
    nodes = {identity: qml_metadata(data) for identity, data in graph.nodes(data=True)}
    edges = {(data.get("_src", source), data.get("_tgt", target), data["relation"], data.get("context"), data["confidence"]) for source, target, data in graph.edges(data=True)}
    return nodes, edges


def test_qml002_ac02_named_qmldir_dispatch_directory_and_single_file_root(tmp_path):
    """Extensionless metadata reaches the actual adapter with the same explicit root."""
    metadata = project(tmp_path)
    assert classify_file(metadata) == FileType.CODE
    assert ex._get_extractor(metadata) is extract_qmldir
    assert ex.collect_files(metadata, root=tmp_path) == [metadata]
    files = ex.collect_files(tmp_path, root=tmp_path)
    assert metadata in files
    result = ex.extract(files, root=tmp_path, cache_root=tmp_path / "cache", parallel=False)
    target = type_target(result)
    assert next(node for node in result["nodes"] if node["id"] == target)["source_file"] == "Public/Tools/Old.qml"
    assert not result.get("qml_failures")


@pytest.mark.parametrize("ignore_file", [".gitignore", ".graphifyignore"])
def test_qml002_ac03_named_metadata_obeys_project_ignores(tmp_path, ignore_file):
    """An ignored provider cannot become visible merely because the file exists on disk."""
    metadata = project(tmp_path)
    (tmp_path / ignore_file).write_text("Public/Tools/qmldir\n", encoding="utf-8")
    files = ex.collect_files(tmp_path, root=tmp_path)
    assert metadata not in files
    result = ex.extract(files, root=tmp_path, cache_root=tmp_path / "cache", parallel=False)
    sites = [node for node in result["nodes"] if node["source_file"] == "Main.qml" and qml_metadata(node).get("kind") == "type_use"]
    assert len(sites) == 1 and qml_metadata(sites[0])["status"] != "resolved"
    assert not any(edge["source"] == sites[0]["id"] and edge["relation"] == "uses" for edge in result["edges"])


def test_qml002_ac03_explicit_single_metadata_entry_obeys_root_ignore(tmp_path):
    """Directory and single-file admission use the same approved root ignore policy."""
    metadata = project(tmp_path)
    (tmp_path / ".graphifyignore").write_text("Public/Tools/qmldir\n", encoding="utf-8")
    assert ex.collect_files(metadata, root=tmp_path) == []


@pytest.mark.parametrize("follow", [False, True])
def test_qml004_ac04_external_symlink_metadata_never_expands_corpus(tmp_path, follow):
    """Even explicit symlink following cannot grant an outside module provider access."""
    root, external = tmp_path / "accepted", tmp_path / "outside"
    root.mkdir()
    external.mkdir()
    outside = external / "qmldir"
    outside.write_text("module Public.Tools\nButton 1.0 Button.qml\n", encoding="utf-8")
    link = root / "qmldir"
    try:
        link.symlink_to(outside)
    except (OSError, NotImplementedError):
        pytest.skip("Host does not permit creating symlinks")
    assert ex.collect_files(root, root=root, follow_symlinks=follow) == []
    assert ex.collect_files(link, root=root, follow_symlinks=follow) == []
    assert extract_qmldir(link, root=root).get("error")


def test_qml010_ac01_real_process_pool_and_warm_order_match_sequential(tmp_path, monkeypatch):
    """More than twenty public sources exercise the actual pool, not its sequential fallback."""
    paths = [write_qml(tmp_path, f"components/Panel{index}.qml", f"Item {{ id: root; property int value: {index} }}\n") for index in range(24)]
    pool_results = []
    real_pool = ex._extract_parallel

    def observe_pool(*args, **kwargs):
        ran = real_pool(*args, **kwargs)
        pool_results.append(ran)
        return ran

    monkeypatch.setattr(ex, "_extract_parallel", observe_pool)
    parallel = ex.extract(paths, root=tmp_path, cache_root=tmp_path / "pool-cache", parallel=True, max_workers=2)
    assert pool_results == [True]
    sequential = ex.extract(list(reversed(paths)), root=tmp_path, cache_root=tmp_path / "serial-cache", parallel=False)
    warm = ex.extract(paths, root=tmp_path, cache_root=tmp_path / "serial-cache", parallel=False)
    assert canonical(parallel) == canonical(sequential) == canonical(warm)


def test_qml004_project_join_borrows_unchanged_context_without_mutating_or_returning_it(tmp_path):
    """A changed caller resolves through accepted provider context while its owners stay borrowed."""
    project(tmp_path)
    paths = ex.collect_files(tmp_path, root=tmp_path)
    full = ex.extract(paths, root=tmp_path, cache_root=tmp_path / "full-cache", parallel=False)
    context_nodes = [node for node in full["nodes"] if node["source_file"] != "Main.qml"]
    context_ids = {node["id"] for node in context_nodes}
    context_edges = [edge for edge in full["edges"] if edge["source"] in context_ids and edge["target"] in context_ids]
    before = copy.deepcopy((context_nodes, context_edges))
    caller = ex.extract([tmp_path / "Main.qml"], root=tmp_path, cache_root=tmp_path / "caller-cache", parallel=False,
                        resolution_context_nodes=context_nodes, resolution_context_edges=context_edges)
    assert (context_nodes, context_edges) == before
    assert all(node["source_file"] == "Main.qml" for node in caller["nodes"])
    assert type_target(caller) == type_target(full)
    assert type_target(caller) in context_ids


def test_qml011_ac02_qmldir_only_update_refreshes_unchanged_caller_and_matches_clean_build(tmp_path, monkeypatch):
    """Real update publishes the new provider, removes its old edge and rechecks the live corpus."""
    metadata = project(tmp_path)
    assert _rebuild_code(tmp_path, no_cluster=True, acquire_lock=False)
    graph_path = tmp_path / "graphify-out/graph.json"
    initial = json.loads(graph_path.read_text(encoding="utf-8"))
    before_target = type_target({"nodes": initial["nodes"], "edges": initial.get("edges", initial.get("links"))})
    metadata.write_text("module Public.Tools\nButton 1.0 New.qml\n", encoding="utf-8")
    called = []
    real_extract = ex.extract

    def observe_extract(paths, **kwargs):
        called.extend(paths)
        return real_extract(paths, **kwargs)

    monkeypatch.setattr(ex, "extract", observe_extract)
    assert _rebuild_code(tmp_path, changed_paths=[metadata], no_cluster=True, acquire_lock=False)
    assert tmp_path / "Main.qml" in called and metadata in called
    updated = json.loads(graph_path.read_text(encoding="utf-8"))
    updated_edges = updated.get("edges", updated.get("links"))
    after_target = type_target({"nodes": updated["nodes"], "edges": updated_edges})
    assert after_target != before_target
    assert next(node for node in updated["nodes"] if node["id"] == after_target)["source_file"] == "Public/Tools/New.qml"
    clean = real_extract(ex.collect_files(tmp_path, root=tmp_path), root=tmp_path, cache_root=tmp_path / "clean-cache", parallel=False)
    assert portable_graph(load_node_link_graph(updated)) == portable_graph(build_from_json(clean, root=tmp_path))


def test_qml010_ac02_default_undirected_export_reload_keeps_qml_direction(tmp_path):
    """Default graph consumers retain each QML relationship's actual source and target."""
    project(tmp_path)
    result = ex.extract(ex.collect_files(tmp_path, root=tmp_path), root=tmp_path,
                        cache_root=tmp_path / "cache", parallel=False)
    graph = build_from_json(result, root=tmp_path)
    assert not graph.is_directed()
    target = tmp_path / "default-graph.json"
    assert to_json(graph, {}, str(target))
    serialized = json.loads(target.read_text(encoding="utf-8"))
    # The JSON source/target direction and the reloaded consumer direction are
    # independent boundaries: an undirected adjacency iteration is insufficient.
    expected = {(edge["source"], edge["target"], edge["relation"], edge.get("context")) for edge in result["edges"]}
    assert {(edge["source"], edge["target"], edge["relation"], edge.get("context")) for edge in serialized["links"]} == expected
    restored = load_node_link_graph(serialized)
    assert not restored.is_directed()
    assert portable_graph(restored) == portable_graph(graph)


@pytest.mark.parametrize("extension", ["js", "mjs"])
@pytest.mark.parametrize("same_stem", [False, True])
def test_qml010_ac02_literal_script_import_keeps_generic_file_endpoint_after_build_reload(tmp_path, extension, same_stem):
    """A resolved QML import must survive the cross-language graph projection guard."""
    filename = f"helpers.{extension}"
    source = "function help() { return 1; }\n" if extension == "js" else "export function help() { return 1; }\n"
    helper = write_qml(tmp_path, filename, source)
    caller = write_qml(tmp_path, source=f'import "{filename}" as Helpers\nQtObject {{ property int value: Helpers.help() }}\n')
    paths = [caller, helper]
    if same_stem:
        other_extension = "mjs" if extension == "js" else "js"
        paths.append(write_qml(tmp_path, f"helpers.{other_extension}", "function help() { return 2; }\n"))
    result = ex.extract(paths, root=tmp_path, cache_root=tmp_path / "cache", parallel=False)
    targets = [node for node in result["nodes"] if node["source_file"] == filename and node["label"] == filename]
    sites = [node for node in result["nodes"] if node["source_file"] == "Main.qml" and qml_metadata(node).get("kind") == "import_resolution"]
    assert len(targets) == len(sites) == 1
    assert qml_metadata(sites[0])["status"] == "resolved"
    expected = [edge for edge in result["edges"] if edge["source"] == sites[0]["id"] and edge["target"] == targets[0]["id"]]
    assert len(expected) == 1 and expected[0]["relation"] == "imports"
    graph = build_from_json(result, directed=True, root=tmp_path)
    assert graph.has_edge(sites[0]["id"], targets[0]["id"])
    target = tmp_path / "roundtrip.json"
    assert to_json(graph, {}, str(target))
    restored = load_node_link_graph(json.loads(target.read_text(encoding="utf-8")))
    # Directed JSON deliberately carries direction in its source/target fields;
    # its writer need not retain the auxiliary undirected loader markers.
    assert restored.is_directed()
    edge = restored.edges[sites[0]["id"], targets[0]["id"]]
    assert (edge["relation"], edge["confidence"]) == ("imports", "INFERRED")
    assert edge.get("_src", sites[0]["id"]) == sites[0]["id"]
    assert edge.get("_tgt", targets[0]["id"]) == targets[0]["id"]
