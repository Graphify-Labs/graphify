"""REQ-QML-020 production refresh, persistence and unused-component regression."""
from __future__ import annotations

import json

import pytest

from graphify.extractors.qml_facts import qml_metadata
from tests.test_qt_final_incremental_parity import clean, normalized, run, unrelated
from tests.test_qt_graph_html_payload import payload, runtime_info


def fixture(root):
    """An uninstantiated QML component is packaged by accepted literal metadata."""
    sources = {
        "Spare.qml": "import QtQuick\nItem { id: grip; property int value: 1 }\n",
        "helper.cpp": "int helper() { return 7; }\n",
        "CMakeLists.txt": "qt_add_qml_module(app URI Public.Tools VERSION 1.0 QML_FILES Spare.qml SOURCES helper.cpp)\n",
        "ui.qrc": '<RCC><qresource prefix="/ui"><file alias="Spare.qml">Spare.qml</file></qresource></RCC>',
        "keep.py": "def helper(): return 7\n\ndef retained(): return helper()\n",
    }
    for name, source in sources.items():
        (root / name).write_bytes(source.encode())
    return root / "Spare.qml"


def memberships(graph):
    return {identity: qml_metadata(data) for identity, data in graph.nodes(data=True)
            if qml_metadata(data).get("kind") == "membership_resolution"}


@pytest.mark.parametrize("operation", ["manual", "watch"])
def test_req_qml020_ac03_metadata_resource_and_source_updates_remove_stale_memberships(tmp_path, monkeypatch, operation):
    """Real full/warm/manual/watch graphs agree after metadata edits and target removal."""
    target = fixture(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GRAPHIFY_NO_TIPS", "1")
    cold = clean(tmp_path, tmp_path / ".cold-cache")
    assert normalized(clean(tmp_path, tmp_path / ".cold-cache")) == normalized(cold)
    graph = run(tmp_path, monkeypatch, operation)
    assert normalized(graph) == normalized(cold)
    original = memberships(graph)
    assert len(original) == 3 and all(md["status"] == "resolved" for md in original.values())
    module = next(identity for identity, node in graph.nodes(data=True) if qml_metadata(node).get("kind") == "qt_module")
    component = next(identity for identity, node in graph.nodes(data=True) if qml_metadata(node).get("kind") == "component")
    import networkx as nx
    assert nx.has_path(graph, module, component)
    kept = unrelated(graph)

    # Renaming a resource alias replaces its source-owned resolution site,
    # without changing the accepted QML component identity or unrelated Python.
    resource = tmp_path / "ui.qrc"
    resource.write_bytes(resource.read_bytes().replace(b'alias="Spare.qml"', b'alias="renamed.qml"'))
    renamed = run(tmp_path, monkeypatch, operation, [resource])
    retired = set(original) - set(memberships(renamed))
    assert len(retired) == 1 and not retired.intersection(renamed)
    assert component in renamed and unrelated(renamed) == kept
    assert normalized(renamed) == normalized(clean(tmp_path, tmp_path / ".renamed-cache"))

    # Duplicate logical aliases invalidate both resource endpoint decisions,
    # even when both literal declarations still name the same accepted target.
    valid_resource = resource.read_bytes()
    resource.write_bytes(valid_resource.replace(b"</qresource>",
        b'<file alias="renamed.qml">Spare.qml</file></qresource>'))
    ambiguous = run(tmp_path, monkeypatch, operation, [resource])
    resource_sites = [md for md in memberships(ambiguous).values() if md.get("alias")]
    assert len(resource_sites) == 2 and all(md["status"] == "ambiguous" for md in resource_sites)
    assert all(not md.get("target_id") for md in resource_sites)
    assert normalized(ambiguous) == normalized(clean(tmp_path, tmp_path / ".ambiguous-cache"))
    resource.write_bytes(valid_resource)
    assert normalized(run(tmp_path, monkeypatch, operation, [resource])) == normalized(renamed)

    # Editing and then renaming the packaged source updates its canonical facts
    # and both metadata paths; old endpoints cannot survive their retirement.
    target.write_bytes(target.read_bytes().replace(b"value: 1", b"value: 2"))
    edited = run(tmp_path, monkeypatch, operation, [target])
    assert normalized(edited) == normalized(clean(tmp_path, tmp_path / ".edited-cache"))
    assert unrelated(edited) == kept
    old_target = target
    target = tmp_path / "Renamed.qml"
    old_target.rename(target)
    build = tmp_path / "CMakeLists.txt"
    build.write_bytes(build.read_bytes().replace(b"Spare.qml", b"Renamed.qml"))
    resource.write_bytes(resource.read_bytes().replace(b">Spare.qml<", b">Renamed.qml<"))
    renamed_target = run(tmp_path, monkeypatch, operation, [old_target, target, build, resource])
    assert component not in renamed_target
    component = next(identity for identity, node in renamed_target.nodes(data=True)
                     if qml_metadata(node).get("kind") == "component")
    assert all(md["status"] == "resolved" for md in memberships(renamed_target).values())
    assert normalized(renamed_target) == normalized(clean(tmp_path, tmp_path / ".target-renamed-cache"))
    assert unrelated(renamed_target) == kept

    # Removing an accepted target invalidates unchanged module/alias statements;
    # no fallback to a same-named source or external read can retain their edges.
    target.unlink()
    removed = run(tmp_path, monkeypatch, operation, [target])
    assert component not in removed
    remaining = memberships(removed)
    missing = [md for md in remaining.values() if md.get("status") != "resolved"]
    assert len(missing) == 2 and all(not md.get("target_id") for md in missing)
    assert normalized(removed) == normalized(clean(tmp_path, tmp_path / ".removed-cache"))
    assert unrelated(removed) == kept
    assert normalized(run(tmp_path, monkeypatch, operation, [])) == normalized(removed)


@pytest.mark.parametrize("operation", ["manual", "force", "watch"])
def test_req_qml020_ac02_failed_metadata_join_preserves_products_and_recovers(tmp_path, monkeypatch, operation):
    """An actual malformed resource preserves four durable products; byte repair is repeatable."""
    fixture(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GRAPHIFY_NO_TIPS", "1")
    mode = "manual" if operation == "force" else operation
    initial = run(tmp_path, monkeypatch, mode)
    assert memberships(initial)
    output = tmp_path / "graphify-out"
    names = ("graph.json", "manifest.json", ".qt_analysis.json", ".graphify_root")
    before = {name: (output / name).read_bytes() for name in names}
    path = tmp_path / "ui.qrc"
    valid = path.read_bytes()
    path.write_bytes(valid + b"<RCC>")
    if operation in {"manual", "force"}:
        with pytest.raises(SystemExit) as failure:
            if operation == "force":
                from tests.test_qt_cpp_upgrade_invalidation import cli
                cli(tmp_path, monkeypatch, "update", force=True)
            else:
                run(tmp_path, monkeypatch, mode, [path])
        assert failure.value.code == 1
    else:
        from graphify.watch import _rebuild_code
        assert not _rebuild_code(tmp_path, changed_paths=[path], no_cluster=True)
    assert before == {name: (output / name).read_bytes() for name in names}
    path.write_bytes(valid)
    corrected = run(tmp_path, monkeypatch, mode, [path])
    assert normalized(corrected) == normalized(initial)
    assert normalized(run(tmp_path, monkeypatch, mode, [])) == normalized(initial)
    assert json.loads((output / "graph.json").read_text(encoding="utf-8"))["nodes"]


@pytest.mark.parametrize("operation", ["extract", "update"])
def test_req_qml020_ac03_policy_upgrade_refreshes_unchanged_packaging(tmp_path, monkeypatch, operation):
    """A policy-five stamp cannot retain old decisions at the same package version."""
    import graphify.extract as extraction
    import graphify.qt_incremental as policy
    from graphify.qt_analysis_state import inspect_qt_analysis
    from tests.test_qt_cpp_upgrade_invalidation import cli

    fixture(tmp_path)
    monkeypatch.chdir(tmp_path)
    paths = [tmp_path / name for name in ("Spare.qml", "helper.cpp", "CMakeLists.txt", "ui.qrc", "keep.py")]
    with monkeypatch.context() as previous:
        previous.setattr(policy, "QT_POLICY_VERSION", 5)
        before = cli(tmp_path, previous, "extract")
        assert not inspect_qt_analysis(tmp_path, tmp_path / "graphify-out", paths).changed
    sources = {path: path.read_bytes() for path in paths}
    assert inspect_qt_analysis(tmp_path, tmp_path / "graphify-out", paths).changed
    observed, real = [], extraction._safe_extract_with_xaml_root

    def observe(extractor, path, root):
        observed.append(path)
        return real(extractor, path, root)

    monkeypatch.setattr(extraction, "_safe_extract_with_xaml_root", observe)
    current = cli(tmp_path, monkeypatch, operation)
    assert set(paths[:4]).issubset(observed)
    assert not inspect_qt_analysis(tmp_path, tmp_path / "graphify-out", paths).changed
    assert len(memberships(current)) == 3
    assert normalized(current) == normalized(before)
    assert normalized(current) == normalized(clean(tmp_path, tmp_path / ".upgrade-cache"))
    assert sources == {path: path.read_bytes() for path in paths}
    assert normalized(cli(tmp_path, monkeypatch, operation)) == normalized(current)


def test_req_qml020_ac02_join_exception_cannot_publish_partial_memberships(tmp_path, monkeypatch):
    """A failure after real scratch projection preserves graph, manifest, stamp and root."""
    import graphify.qt_project_membership as membership

    fixture(tmp_path)
    monkeypatch.chdir(tmp_path)
    initial = run(tmp_path, monkeypatch, "manual")
    output = tmp_path / "graphify-out"
    products = [output / name for name in ("graph.json", "manifest.json", ".qt_analysis.json", ".graphify_root")]
    before = {path: path.read_bytes() for path in products}
    path = tmp_path / "CMakeLists.txt"
    original = path.read_bytes()
    path.write_bytes(original + b"\n# refresh projection\n")
    real = membership.resolve_project_memberships

    def fail_after_real_join(*args, **kwargs):
        result = real(*args, **kwargs)
        assert result[0]
        raise RuntimeError("injected join completion failure")

    with monkeypatch.context() as failure:
        failure.setattr(membership, "resolve_project_memberships", fail_after_real_join)
        with pytest.raises(SystemExit) as rejected:
            run(tmp_path, failure, "manual", [path])
        assert rejected.value.code == 1
    assert before == {path: path.read_bytes() for path in products}
    path.write_bytes(original)
    assert normalized(run(tmp_path, monkeypatch, "manual", [path])) == normalized(initial)


def test_req_qml020_ac01_unused_packaged_component_survives_aggregate_export(tmp_path, monkeypatch):
    """Actual serialized facts yield aggregate links and truthful source-edge counts."""
    from graphify.export import to_html

    fixture(tmp_path)
    monkeypatch.chdir(tmp_path)
    graph = run(tmp_path, monkeypatch, "manual")
    files = sorted({node["source_file"] for _, node in graph.nodes(data=True)})
    groups = {number: [identity for identity, node in graph.nodes(data=True) if node["source_file"] == path]
              for number, path in enumerate(files)}
    number = files.index("Spare.qml")
    path = tmp_path / "aggregate.html"
    assert to_html(graph, groups, str(path), node_limit=1, learning_overlay={})
    content = path.read_text(encoding="utf-8")
    result = {"nodes": payload(content, "RAW_NODES"), "info": runtime_info(content, str(number), monkeypatch)}
    selected = next(node for node in result["nodes"] if node["id"] == str(number))
    assert selected["external_source_edges"] == 2 and selected["degree"] == 2
    assert selected["internal_source_edges"] > 0
    # Startup selection belongs to deferred REQ-QML-019-AC04; source counts remain required.
    assert "External source edges: 2" in result["info"]
    assert sum(node["internal_source_edges"] for node in result["nodes"]) + sum(
        node["external_source_edges"] for node in result["nodes"]) // 2 == graph.number_of_edges()


@pytest.mark.parametrize("invalid", [True, -1, "</div><script>bad()</script>"])
def test_req_qml020_ac01_aggregate_counts_keep_source_edges_and_reject_invalid_fields(tmp_path, monkeypatch, invalid):
    """Parallel/directed/self-loop edges count once; untrusted aggregate fields remain unavailable."""
    import copy
    import networkx as nx
    from graphify.export import to_html

    graph = nx.MultiDiGraph()
    graph.add_edges_from([("a0", "a1"), ("a1", "a0"), ("a0", "a0"), ("a0", "b0"),
                          ("b0", "a0"), ("a0", "a1"), ("a1", "b0")])
    before = copy.deepcopy(graph)
    path = tmp_path / "counts.html"
    assert to_html(graph, {0: ["a0", "a1"], 1: ["b0"]}, str(path), node_limit=1, learning_overlay={})
    nodes = {node["id"]: node for node in payload(path.read_text(encoding="utf-8"), "RAW_NODES")}
    assert nodes["0"]["internal_source_edges"] == 4 and nodes["1"]["internal_source_edges"] == 0
    assert nodes["0"]["external_source_edges"] == nodes["1"]["external_source_edges"] == 3
    assert sum(n["internal_source_edges"] for n in nodes.values()) + sum(
        n["external_source_edges"] for n in nodes.values()) // 2 == graph.number_of_edges()
    assert nx.utils.graphs_equal(graph, before)
    meta = nx.Graph([("0", "1")])
    meta.nodes["0"].update(internal_source_edges=invalid, external_source_edges=invalid)
    assert to_html(meta, {0: ["0"], 1: ["1"]}, str(path), member_counts={0: 4, 1: 2}, learning_overlay={})
    content = path.read_text(encoding="utf-8")
    assert all("internal_source_edges" not in n and "external_source_edges" not in n
               for n in payload(content, "RAW_NODES"))
    info = runtime_info(content, "0", monkeypatch)
    assert "Internal source edges: unavailable" in info and "External source edges: unavailable" in info
    assert "bad()" not in info and "Degree: 1" in info


def test_req_qml020_ac03_membership_ids_are_independent_of_checkout_location(tmp_path):
    """Accepted relative metadata and QML facts remain identical after root relocation."""
    first, second = tmp_path / "first", tmp_path / "relocated"
    first.mkdir()
    second.mkdir()
    fixture(first)
    fixture(second)
    original = clean(first, tmp_path / ".first-cache")
    relocated = clean(second, tmp_path / ".second-cache")
    assert len(memberships(original)) == 3
    assert normalized(original) == normalized(relocated)


def test_req_qml020_ac03_pipeline_publishes_replacement_without_borrowed_mutation(tmp_path):
    """Rejoining fresh metadata replaces a borrowed site before the former list boundary."""
    import copy
    from graphify.extract import extract
    from graphify.extractors.qml_resources import extract_qrc
    from graphify.qt_qml_pipeline import resolve_qt_qml

    fixture(tmp_path)
    paths = [tmp_path / name for name in ("Spare.qml", "helper.cpp", "CMakeLists.txt", "ui.qrc")]
    prior = extract(paths, root=tmp_path, cache_root=tmp_path, parallel=False)
    old_site = next(node for node in prior["nodes"] if qml_metadata(node).get("kind") == "membership_resolution"
                    and qml_metadata(node).get("alias"))
    old_id = old_site["id"]
    context = [node for node in prior["nodes"] if node["source_file"] != "Spare.qml"]
    context_ids = {node["id"] for node in context}
    context_edges = [edge for edge in prior["edges"]
                     if edge["source"] in context_ids and edge["target"] in context_ids]
    before = copy.deepcopy((context, context_edges))
    fresh = extract_qrc(paths[-1], root=tmp_path)
    nodes, edges = list(fresh["nodes"]), list(fresh["edges"])
    assert not resolve_qt_qml([paths[-1]], [fresh], nodes, edges, root=tmp_path,
                             context_nodes=context, context_edges=context_edges)
    replacement = next(node for node in nodes if node["id"] == old_id)
    assert qml_metadata(replacement)["status"] == "unavailable"
    assert qml_metadata(old_site)["status"] == "resolved"
    assert (context, context_edges) == before
    assert not any(edge["source"] == old_id for edge in edges)
    assert {node["source_file"] for node in nodes} == {"ui.qrc"}
    assert sum(node["id"] == old_id for node in nodes) == 1
