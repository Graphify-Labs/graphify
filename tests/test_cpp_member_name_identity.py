"""INC-QML-111: literal data/method names never share a normalized identity."""
import json

import pytest

from graphify.build import build_from_json
from graphify.export import to_json
from graphify.extract import extract_cpp
from graphify.extractors.base import _make_id
from graphify.extractors.qt_cpp_facts import qt_metadata
from graphify.paths import load_node_link_graph
from tests.cpp_member_name_helpers import facade, members, owned, owner_node, project, source, span


@pytest.mark.parametrize("owner", ["Panel", "Cpp"])
@pytest.mark.parametrize("native", [False, True])
@pytest.mark.parametrize("out_of_line", [False, True])
def test_req_qml022_ac02_literal_members_keep_exact_roles_owners_and_source_bytes(tmp_path, owner, native, out_of_line):
    """Every accepted spelling survives direct/facade and the actual native method map."""
    raw = ("\ufeff// café 雪\n" + source(owner=owner, native=native, out_of_line=out_of_line)).replace("\n", "\r\n").encode()
    path = project(tmp_path, raw, native=native)
    direct = extract_cpp(path)
    assert not direct.get("error")
    expected = {"Field", "field", "Callback", "callback", ".Run()", ".run()"}
    for phase, result in (("direct", direct), ("facade", facade(tmp_path))):
        found = owned(result, owner)
        assert {node["label"] for node in found} == expected
        assert len({node["id"] for node in found}) == 6
        for node in found:
            if node["label"] in {"Field", "field", "Callback", "callback"}:
                assert node.get("_callable") is not True
                fact = node["metadata"]["cpp_declarator"]
                assert fact["kind"] == "field" and node["label"].encode() in span(raw, fact)
        facts = members(result)
        assert len(facts) == (4 if phase == "direct" and out_of_line else 2)
        assert not any(fact["ambiguous"] for _, fact in facts)
        for _, fact in facts:
            assert span(raw, fact)
        native_calls = [edge for edge in result["edges"] if edge.get("context") == "qml_js_call"]
        if phase == "facade" and native:
            targets = {node["label"]: node["id"] for node in found if node["label"].startswith(".")}
            assert {edge["target"] for edge in native_calls} == set(targets.values()) and len(native_calls) == 2
            assert all(qt_metadata(edge)["native_endpoint"]["canonical_target_id"] == edge["target"] for edge in native_calls)
        else:
            assert not native_calls
        graph = build_from_json(result, root=tmp_path, directed=False)
        output = tmp_path / (phase + ".json")
        assert to_json(graph, {}, str(output), force=True)
        loaded = load_node_link_graph(json.loads(output.read_text(encoding="utf-8")))
        for node in found:
            assert loaded.nodes[node["id"]]["metadata"] == graph.nodes[node["id"]]["metadata"]


@pytest.mark.parametrize("text,expected", [
    ("class Panel{public:int Run;void run(){}};", {"Run", ".run()"}),
    ("class Panel{public:int value;double _value;};", {"value", "_value"}),
    ("class Panel{public:int panel;~Panel();};", {"panel", ".~Panel()"}),
    ("class Panel{public:void operator()(){}void operator[](int value){}};", {".operator()()", ".operator[]()"}),
])
def test_req_qml022_ac02_mixed_and_punctuation_names_keep_each_source_fact(tmp_path, text, expected):
    """Different admitted spellings retain data/destructor/operator roles without new semantics."""
    path = project(tmp_path, (text + "\n").encode())
    for result in (extract_cpp(path), facade(tmp_path)):
        found = owned(result)
        assert {node["label"] for node in found} == expected and len({node["id"] for node in found}) == len(expected)
        for node in found:
            if not node["label"].startswith("."):
                assert node.get("_callable") is not True


def test_req_qml022_ac06_noncolliding_and_exact_overload_ids_keep_the_prior_contract(tmp_path):
    """Identity repair cannot rewrite legacy names or choose a same-spelled overload winner."""
    path = project(tmp_path, b"class Panel{public:int value;void run(){}};\n")
    direct = extract_cpp(path)
    owner = owner_node(direct)["id"]
    assert all(node["id"] == _make_id(owner, node["label"].removeprefix(".").removesuffix("()")) for node in owned(direct))
    path.write_bytes(b"class Panel{public:void Run(int);void Run(double);};\n")
    direct = extract_cpp(path)
    node, = owned(direct)
    assert node["id"] == _make_id(owner_node(direct)["id"], "Run")
    fact, = [fact for _, fact in members(direct)]
    assert fact["ambiguous"] is True


def test_req_qml022_ac06_member_collision_ids_ignore_declaration_order_and_line_insertion(tmp_path):
    """The complete literal census decides IDs, rather than the first encountered spelling."""
    path = project(tmp_path, source().encode())
    before = {node["label"]: node["id"] for node in owned(extract_cpp(path))}
    assert len(before) == 6
    path.write_bytes(("// line insertion\n\n" + source(reverse=True)).encode())
    after = {node["label"]: node["id"] for node in owned(extract_cpp(path))}
    assert before == after
