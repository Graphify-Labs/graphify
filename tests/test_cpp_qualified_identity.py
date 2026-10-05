"""REQ-QML-008/016/017: qualified native identities survive real publication."""
from __future__ import annotations

import base64
import json

import pytest

from graphify.build import build_from_json
from graphify.export import to_json
from graphify.extract import extract_cpp
from graphify.extractors.base import _make_id, _file_stem
from graphify.extractors.qt_cpp_facts import qt_metadata
from graphify.paths import load_node_link_graph
from tests.qt_analysis_helpers import analysis, sites
from tests.test_qt_construction_authority import native


def classes(result):
    return {base64.b64decode(node["metadata"]["cpp_class"]["qualified_name_b64"]).decode(): node
            for node in result["nodes"] if node.get("metadata", {}).get("cpp_class")}


@pytest.mark.parametrize("source, names", [
    ("class Base {}; namespace Public { class Base {}; }", {"Base", "Public::Base"}),
    ("namespace A_B {class Base {};} namespace A::B {class Base {};}", {"A_B::Base", "A::B::Base"}),
    ("namespace Public {class Base {};} namespace PUBLIC {class Base {};}", {"Public::Base", "PUBLIC::Base"}),
    ("class One {public: class Base {};}; class Two {public: class Base {};};",
     {"One", "One::Base", "Two", "Two::Base"}),
])
def test_req_qml008_ac02_qualified_class_bodies_keep_distinct_portable_identities(tmp_path, source, names):
    path = tmp_path / "backend.h"
    path.write_text(source, encoding="utf-8")
    direct = extract_cpp(path)
    accepted = classes(direct)
    assert set(accepted) == names
    assert len({node["id"] for node in accepted.values()}) == len(names)
    assert all(not node["metadata"]["cpp_class"]["ambiguous"] for node in accepted.values())
    result = analysis(tmp_path, {"backend.h": source})
    assert set(classes(result)) == names
    assert all(str(tmp_path).lower().replace("\\", "_") not in node["id"] for node in classes(result).values())
    original_ids = {name: node["id"] for name, node in classes(result).items()}
    shifted = analysis(tmp_path, {"backend.h": "// source-only shift\n" + source})
    assert {name: node["id"] for name, node in classes(shifted).items()} == original_ids


def test_req_qml008_ac02_forward_facts_do_not_replace_unique_complete_body(tmp_path):
    source = "class Base; class Base; class Base { Q_OBJECT }; namespace Public { class Base; class Base { Q_OBJECT }; }"
    result = analysis(tmp_path, {"backend.h": source})
    accepted = classes(result)
    assert set(accepted) == {"Base", "Public::Base"}
    assert all(node["metadata"]["cpp_class"]["is_definition"] is True
               and node["metadata"]["cpp_class"]["ambiguous"] is False for node in accepted.values())
    qt_classes = sites(result, "class")
    assert sum(qt_metadata(node)["is_definition"] is False for node in qt_classes) == 3


def test_req_qml017_ac04_same_file_native_ancestry_uses_exact_class_not_basename(tmp_path):
    declarations = ('class Base : public QWidget { Q_OBJECT }; '
                    'namespace Public { class Base : public QObject { Q_OBJECT }; '
                    'class Backend : public Base { Q_OBJECT QML_NAMED_ELEMENT(Owned) }; }')
    result, site, links = native(tmp_path, declarations)
    assert qt_metadata(site)["status"] == "resolved" and len(links) == 1
    accepted = classes(result)
    assert accepted["Base"]["id"] != accepted["Public::Base"]["id"]
    qt_classes = {qt_metadata(node)["class_name"]: qt_metadata(node) for node in sites(result, "class")}
    assert qt_classes["Public::Backend"]["canonical_base_names"] == ["Public::Base"]
    assert qt_classes["Public::Base"]["class_id"] == accepted["Public::Base"]["id"]


def test_req_qml016_ac04_header_definition_events_keep_qualified_canonical_owners(tmp_path):
    header = '''class Base : public QObject { Q_OBJECT
public: void run(); signals: void changed(); };
namespace Public { class Base : public QObject { Q_OBJECT
public: void run(); signals: void changed(); }; }
'''
    implementation = '#include "backend.h"\nvoid Base::run() { emit changed(); }\nvoid Public::Base::run() { emit changed(); }\n'
    result = analysis(tmp_path, {"backend.h": header, "backend.cpp": implementation})
    accepted = classes(result)
    assert set(accepted) == {"Base", "Public::Base"}
    run = [node for node in result["nodes"] if node.get("definition_file") == "backend.cpp"]
    assert len(run) == 2 and len({node["id"] for node in run}) == 2
    owner_links = [edge for edge in result["edges"] if edge.get("relation") == "method"
                   and edge["target"] in {node["id"] for node in run}]
    assert {edge["source"] for edge in owner_links} == {node["id"] for node in accepted.values()}
    emissions = sites(result, "emission")
    assert len(emissions) == 2 and all(qt_metadata(node)["status"] == "resolved" for node in emissions)
    graph = build_from_json(result, root=tmp_path)
    output = tmp_path / "proof.json"
    assert to_json(graph, {}, str(output), force=True)
    payload = json.loads(output.read_text(encoding="utf-8"))
    restored = load_node_link_graph(payload)
    for site in emissions:
        md = qt_metadata(site)
        assert (tmp_path / "backend.cpp").read_bytes()[md["span"]["start_byte"]:md["span"]["end_byte"]] == b"changed()"
        assert md["explicit_emit"] is True
        links = [edge for edge in payload["links"] if edge["source"] == site["id"] and edge.get("context") == "qt_signal_emit"]
        assert len(links) == 1
        edge = restored.edges[links[0]["source"], links[0]["target"]]
        assert (edge["_src"], edge["_tgt"]) == (links[0]["source"], links[0]["target"])


def test_req_qml008_ac02_conflicting_complete_bodies_remain_ambiguous(tmp_path):
    result = analysis(tmp_path, {"backend.h": 'namespace Public { class Base {}; class Base {}; }'})
    accepted = classes(result)
    assert accepted["Public::Base"]["metadata"]["cpp_class"]["ambiguous"] is True


@pytest.mark.parametrize("filename", ["backend.h", "b" * 205 + ".h"])
def test_req_qml008_ac02_long_qualified_discriminator_survives_real_graph_transport(tmp_path, filename):
    prefix = "N" * 330
    source = f"namespace {prefix} {{class Base {{public: void run() {{}};}};}} namespace {prefix.lower()} {{class Base {{public: void run() {{}};}};}}"
    result = analysis(tmp_path, {filename: source})
    names = {prefix + "::Base", prefix.lower() + "::Base"}
    accepted = classes(result)
    assert set(accepted) == names and len({node["id"] for node in accepted.values()}) == 2
    graph = build_from_json(result, root=tmp_path)
    output = tmp_path / "proof.json"
    assert to_json(graph, {}, str(output), force=True)
    restored = load_node_link_graph(json.loads(output.read_text(encoding="utf-8")))
    published = {base64.b64decode(data["metadata"]["cpp_class"]["qualified_name_b64"]).decode(): identity
                 for identity, data in restored.nodes(data=True) if data.get("metadata", {}).get("cpp_class")}
    assert set(published) == names and len(set(published.values())) == 2
    for name in names:
        assert published[name] == accepted[name]["id"]
        assert any(source == published[name] and data.get("relation") == "method"
                   for source, _, data in restored.edges(published[name], data=True))


def test_req_qml008_ac02_global_class_and_member_ids_retain_existing_contract(tmp_path):
    path = tmp_path / "backend.h"
    path.write_text("class Base {public: void run() {}};", encoding="utf-8")
    result = extract_cpp(path)
    owner = classes(result)["Base"]
    assert owner["id"] == _make_id(_file_stem(path), "Base")
    method = next(node for node in result["nodes"] if node.get("label") == ".run()")
    assert method["id"] == _make_id(owner["id"], "run")


def test_req_qml008_ac02_inheritance_cannot_borrow_later_namespace_class_body(tmp_path):
    result = analysis(tmp_path, {"backend.h": "class Base {}; namespace Public { class Derived : public Base {}; class Base {}; }"})
    accepted = classes(result)
    edge = next(edge for edge in result["edges"] if edge["source"] == accepted["Public::Derived"]["id"]
                and edge["relation"] == "inherits")
    assert edge["target"] == accepted["Base"]["id"] != accepted["Public::Base"]["id"]


def test_req_qml008_ac02_original_bom_crlf_unicode_spans_survive_qualified_member_join(tmp_path):
    header = '\ufeff// π原\r\nnamespace Public {\r\nclass Base : public QObject { Q_OBJECT\r\npublic: void run(); signals: void changed(); }; }\r\n'
    implementation = '\ufeff// π原\r\n#include "backend.h"\r\nvoid Public::Base::run() { emit changed(); }\r\n'
    result = analysis(tmp_path, {"backend.h": header, "backend.cpp": implementation})
    owner = classes(result)["Public::Base"]
    span = owner["metadata"]["cpp_class"]["span"]
    assert header.encode()[span["start_byte"]:span["end_byte"]].startswith(b"class Base")
    method = next(node for node in result["nodes"] if node.get("definition_file") == "backend.cpp")
    assert method["definition_location"] == "L3"
    emission = sites(result, "emission")[0]
    md = qt_metadata(emission)
    assert md["owner_id"] == method["id"] and md["status"] == "resolved"
    assert implementation.encode()[md["span"]["start_byte"]:md["span"]["end_byte"]] == b"changed()"
