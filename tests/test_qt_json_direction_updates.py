"""INC-QML-31: rejected JSON direction preserves the real manual/watch cohort."""
from __future__ import annotations

from collections import Counter
import json

import pytest

import graphify.__main__ as entrypoint
import graphify.export as export
import graphify.watch as watch
from graphify.affected import affected_nodes
from graphify.cache import cache_dir
from graphify.extractors.qml_facts import qml_metadata
from graphify.paths import load_node_link_graph
from tests.qt_analysis_helpers import analysis
from tests.test_qt_final_incremental_parity import clean, normalized


PRODUCTS = ("graph.json", ".graphify_root", "manifest.json", ".qt_analysis.json", "GRAPH_REPORT.md",
            ".graphify_labels.json", ".graphify_labels.json.sig")


def snapshot(output):
    return {name: (output / name).read_bytes() for name in PRODUCTS}


def source_contract(graph, *, only_python=False):
    """Compare exact source facts while excluding the clustered display label."""
    nodes, edges = normalized(graph)

    def source_data(serialized):
        data = json.loads(serialized)
        # Cold analysis has no communities. This presentation label is supplied
        # by clustering; direction, source proof and every other fact remain.
        data.pop("community_name", None)
        return json.dumps(data, sort_keys=True, ensure_ascii=False)

    identities = {identity for identity, data in graph.nodes(data=True)
                  if not only_python or data.get("source_file") == "keep.py"}
    return ({identity: source_data(data) for identity, data in nodes.items() if identity in identities},
            Counter({(source, target, source_data(data)): count for (source, target, data), count in edges.items()
                     if source in identities and target in identities}))


def clustered(root, monkeypatch, operation, changes=None):
    """Both real entry points use clustered JSON export, not the raw no-cluster writer."""
    if operation == "manual":
        monkeypatch.setattr(entrypoint, "_check_skill_version", lambda *_: None)
        monkeypatch.setattr(entrypoint, "_refresh_stale_skills", lambda: None)
        monkeypatch.setattr(entrypoint.sys, "argv", ["graphify", "update", str(root)])
        entrypoint.main()
    else:
        assert watch._rebuild_code(root, changed_paths=changes)
    return load_node_link_graph(root / "graphify-out/graph.json")


@pytest.mark.parametrize("operation", ["manual", "watch"])
@pytest.mark.parametrize("corruption", ["foreign", "partial"])
def test_rejected_direction_clustered_publication_retains_products_cache_and_repairs(tmp_path, monkeypatch,
                                                                                   capsys, operation, corruption):
    """Only marker transport is faulted at the real graph serializer; disk publication must reject then recover."""
    analysis(tmp_path, {"Main.qml": "import QtQml\nQtObject { property int input: 1; property int output: input }",
                       "keep.py": "def helper(): return 7\n\ndef retained(): return helper()\n"})
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GRAPHIFY_NO_TIPS", "1")
    initial = clustered(tmp_path, monkeypatch, operation)
    output = tmp_path / "graphify-out"
    prior = snapshot(output)
    kept = source_contract(initial, only_python=True)
    ast = {path: path.read_bytes() for path in cache_dir(tmp_path).rglob("*.json")}
    assert ast
    source = tmp_path / "Main.qml"
    source.write_bytes(source.read_bytes().replace(b"output: input", b"output: input + 2"))
    original_export = export.to_json
    seen = []

    def corrupt_direction(graph, communities, output_path, **kwargs):
        # This seam receives the actual extraction/build result. The real JSON
        # writer below owns validation, the rejection result and durable writes.
        read = next(identity for identity, data in graph.nodes(data=True) if qml_metadata(data).get("kind") == "read")
        target = next(identity for identity, data in graph.nodes(data=True) if qml_metadata(data).get("kind") == "property"
                      and qml_metadata(data).get("raw_name") == "input")
        edge = graph.edges[read, target]
        if corruption == "foreign":
            edge["_src"] = "private-needle\nforged diagnostic"
        else:
            edge.pop("_src")
        result = original_export(graph, communities, output_path, **kwargs)
        seen.append(result)
        return result

    with monkeypatch.context() as fault:
        fault.setattr(export, "to_json", corrupt_direction)
        if operation == "manual":
            with pytest.raises(SystemExit) as rejected:
                clustered(tmp_path, monkeypatch, operation, [source])
            assert rejected.value.code == 1
        else:
            assert not watch._rebuild_code(tmp_path, changed_paths=[source])
    assert seen == [False] and snapshot(output) == prior
    assert all(path.read_bytes() == contents for path, contents in ast.items())
    diagnostic = capsys.readouterr().err
    assert "QT_EXPORT_DIRECTION" in diagnostic
    assert "private-needle" not in diagnostic and "forged diagnostic" not in diagnostic
    assert not (output / ".graph.tmp.json").exists() and not list(output.glob(".gfy-publish-*"))

    repaired = clustered(tmp_path, monkeypatch, operation, [source])
    assert source_contract(repaired) == source_contract(clean(tmp_path, tmp_path / ".clean-cache"))
    assert source_contract(repaired, only_python=True) == kept and source_contract(repaired) != source_contract(initial)
    read = next(identity for identity, data in repaired.nodes(data=True) if qml_metadata(data).get("kind") == "read")
    target = next(identity for identity, data in repaired.nodes(data=True) if qml_metadata(data).get("kind") == "property"
                  and qml_metadata(data).get("raw_name") == "input")
    assert read in {hit.node_id for hit in affected_nodes(repaired, target, depth=1)}
    current = snapshot(output)
    assert normalized(clustered(tmp_path, monkeypatch, operation, [])) == normalized(repaired)
    assert snapshot(output) == current
