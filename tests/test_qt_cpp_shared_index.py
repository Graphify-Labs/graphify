"""INC-QML-96: native enrichment retains one accepted-cohort index, not one per unit."""
from __future__ import annotations

import copy

import graphify.extractors.qt_cpp_exposure as exposure
import graphify.extractors.qt_cpp_accepted_index as index_module
from graphify.extract import extract
from graphify.extractors.qt_cpp_facts import qt_metadata
from graphify.extractors.qt_cpp_mapping import CppMapping, map_cpp
from graphify.extractors.qt_cpp_syntax import read_cpp


def project(root):
    """Real mixed-language producers supply unrelated facts and both native mapping loops."""
    sources = {f"owner{index}.hpp": f"""class Owner{index} : public QObject {{
 Q_OBJECT
public:
 void run();
}};
""" for index in range(3)}
    sources["owner0.cpp"] = '#include "owner0.hpp"\nvoid Owner0::run() {}\n'
    sources["keep.py"] = "def retained(): return 1\n"
    paths = []
    for name, source in sources.items():
        path = root / name
        path.write_text(source, encoding="utf-8")
        paths.append(path)
    return paths


def test_req_qml022_ac06_enrichment_indexes_unrelated_corpus_fact_once_across_all_units(tmp_path, monkeypatch):
    """Four actual native units share path/provenance indexing without changing accepted facts."""
    paths = project(tmp_path)
    real_enrich, real_source_path = exposure.enrich_qt_cpp, index_module.source_path
    real_factory = exposure._accepted_cpp_mapper
    watched, calls, cohort, mappings = [], [], [], []

    def factory(*args, **kwargs):
        actual = real_factory(*args, **kwargs)

        def map_unit(unit):
            result = actual(unit)
            mappings.append(result)
            return result

        return map_unit

    def source_path(node, root):
        if watched and node is watched[0]:
            calls.append(node)
        return real_source_path(node, root)

    def enrich(*args, **kwargs):
        nodes = kwargs["accepted_nodes"]
        watched.append(next(node for node in nodes if node.get("_callable") is True
                            and node.get("source_file") == "keep.py"))
        cohort.append(copy.deepcopy((nodes, kwargs["accepted_edges"])))
        try:
            result = real_enrich(*args, **kwargs)
        finally:
            watched.clear()
        assert (nodes, kwargs["accepted_edges"]) == cohort[-1]
        return result

    monkeypatch.setattr(index_module, "source_path", source_path)
    monkeypatch.setattr(exposure, "enrich_qt_cpp", enrich)
    monkeypatch.setattr(exposure, "_accepted_cpp_mapper", factory)
    result = extract(paths, root=tmp_path, cache_root=tmp_path, parallel=False)
    assert not result["failed_sources"] and not result.get("qml_failures")
    assert len(cohort) == 1
    assert len(calls) == 1
    assert {mapping.unit.relative_file for mapping in mappings} == {"owner0.hpp", "owner1.hpp", "owner2.hpp", "owner0.cpp"}
    for field in ("nodes", "edges", "paths", "definition_paths", "accepted", "parents", "class_parents"):
        assert len({id(getattr(mapping, field)) for mapping in mappings}) == 1
    assert len({id(mapping.classes) for mapping in mappings}) == len({id(mapping.functions) for mapping in mappings}) == 4
    classes = {qt_metadata(node)["class_name"] for node in result["nodes"] if qt_metadata(node).get("kind") == "class"}
    assert classes == {"Owner0", "Owner1", "Owner2"}
    method = next(node for node in result["nodes"] if node.get("definition_file") == "owner0.cpp")
    body = next(node for node in result["nodes"] if qt_metadata(node).get("kind") == "member" and node["source_file"] == "owner0.cpp")
    assert qt_metadata(body)["generic_target_id"] == method["id"]
    assert qt_metadata(body)["class_name"] == "Owner0"


def test_req_qml022_ac06_shared_mapping_matches_public_direct_constructor_and_definition_provenance(tmp_path):
    """All three mapping entry paths retain actual canonical declarations and body ownership."""
    paths = project(tmp_path)
    result = extract(paths, root=tmp_path, cache_root=tmp_path, parallel=False)
    nodes, edges = result["nodes"], result["edges"]
    before = copy.deepcopy((nodes, edges))
    mapper = index_module._accepted_cpp_mapper(nodes, edges, root=tmp_path)
    units = [read_cpp(path, tmp_path) for path in paths if path.suffix != ".py"]
    shared = [mapper(unit) for unit in units]
    classes = [record for mapping in shared for record in mapping.classes]
    for unit, mapping in zip(units, shared):
        direct = map_cpp(unit, nodes, edges, root=tmp_path)
        constructor = CppMapping(unit, nodes, edges, root=tmp_path)
        assert mapping.classes == direct.classes == constructor.classes
        assert mapping.functions == direct.functions == constructor.functions
        assert mapping.paths == direct.paths == constructor.paths
        assert mapping.definition_paths == direct.definition_paths == constructor.definition_paths
        assert mapping.parents == direct.parents == constructor.parents
        assert mapping.class_parents == direct.class_parents == constructor.class_parents
        mapping.bind_classes(classes)
        direct.bind_classes(classes)
        constructor.bind_classes(classes)
        assert mapping.functions == direct.functions == constructor.functions
        assert mapping.paths is not direct.paths and direct.paths is not constructor.paths
    assert (nodes, edges) == before
