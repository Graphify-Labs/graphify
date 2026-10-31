"""INC-QML-111: repaired member domains respect literal and cross-domain facts."""
import hashlib
import json

import pytest

from graphify.build import build_from_json
from graphify.export import to_json
from graphify.extract import extract_cpp
from graphify.extractors.base import _file_stem, _make_id
from graphify.extractors.cpp_constructor_signature import constructor_id
from graphify.extractors.cpp_identity import CppIdentity
from graphify.extractors.cpp_functions import CppFunctions
from graphify.extractors.cpp_member_names import CppMemberNames
from graphify.extractors.qt_cpp_facts import qt_metadata
from graphify.extractors.qt_cpp_syntax import read_cpp, walk
from graphify.paths import load_node_link_graph
from tests.cpp_member_name_helpers import facade, members, owned, owner_node, project, span


def test_req_qml022_ac06_literal_generated_name_reservations_do_not_choose_a_winner(tmp_path):
    """A real field resembling every initial repaired candidate keeps its plain ID."""
    digest = hashlib.sha256(b"Field").hexdigest()
    reserved = ["cppmember_" + digest + suffix for suffix in ("", "_1", "_2")]
    entries = ["int Field;", "double field;", *("int " + name + ";" for name in reserved)]
    path = tmp_path / "unit.cpp"
    snapshots = []
    for parts in (entries, list(reversed(entries))):
        path.write_bytes(("class Panel{public:" + "".join(parts) + "};\n").encode())
        result = extract_cpp(path)
        found = {node["label"]: node for node in owned(result)}
        assert set(found) == {"Field", "field", *reserved} and len({node["id"] for node in found.values()}) == 5
        owner = owner_node(result)["id"]
        assert all(found[name]["id"] == _make_id(owner, name) for name in reserved)
        assert found["Field"]["id"] == _make_id(owner, "cppmember", digest, "3")
        assert all(node.get("_callable") is not True for node in found.values())
        snapshots.append({name: node["id"] for name, node in found.items()})
    assert snapshots[0] == snapshots[1]


@pytest.mark.parametrize("alias_first", [False, True])
def test_req_qml022_ac06_ordinary_alias_reserves_the_repaired_member_domain(tmp_path, alias_first):
    """An actual source alias keeps its own ID and cannot swallow the repaired Field fact."""
    alias = "Panel_cppmember_" + hashlib.sha256(b"Field").hexdigest()
    declaration = f"using {alias}=int;\n"
    body = "struct Panel{int Field;double field;};\n"
    path = project(tmp_path, ((declaration + body) if alias_first else (body + declaration)).encode())
    for phase, result in (("direct", extract_cpp(path)), ("facade", facade(tmp_path))):
        found = owned(result)
        assert {node["label"] for node in found} == {"Field", "field"}
        alias_node, = [node for node in result["nodes"] if node["label"] == alias]
        if phase == "direct":
            assert alias_node["id"] == _make_id(_file_stem(path), alias)
        assert alias_node["id"] not in {node["id"] for node in found}
        graph = build_from_json(result, root=tmp_path)
        output = tmp_path / (phase + ".json")
        assert to_json(graph, {}, str(output), force=True)
        restored = load_node_link_graph(json.loads(output.read_text(encoding="utf-8")))
        assert restored.nodes[alias_node["id"]]["label"] == alias
        for node in found:
            assert restored.nodes[node["id"]]["metadata"]["cpp_declarator"]["kind"] == "field"


def test_req_qml022_ac06_constructor_signature_domain_is_not_a_member_name_collision(tmp_path):
    """The real constructor keeps its established signature recipe beside lowercase data."""
    path = project(tmp_path, b"class Panel{public:Panel(int value){} int panel;int Field;double field;};\n")
    result = extract_cpp(path)
    owner = owner_node(result)["id"]
    unit = read_cpp(path, tmp_path)
    syntax, = [node for node in walk(unit.tree) if node.type == "function_definition"]
    expected = constructor_id(owner, "Panel", syntax, unit.source, "Panel")
    constructors = [node for node in result["nodes"] if node.get("metadata", {}).get("cpp_constructor")]
    assert len(constructors) == 1 and constructors[0]["id"] == expected
    assert next(node for node in owned(result) if node["label"] == "panel").get("_callable") is not True


def test_req_qml022_ac06_same_spelling_overloads_do_not_poison_distinct_lowercase_slot(tmp_path):
    """Unknown overload choice stays unavailable while the independently named slot resolves."""
    raw = ("class Panel:public QObject{Q_OBJECT QML_NAMED_ELEMENT(CaseOwner) public:"
           "Q_INVOKABLE void Run(int);Q_INVOKABLE void Run(double);Q_SLOT void run(){}};\n").encode()
    project(tmp_path, raw, native=True)
    qml = tmp_path / "Main.qml"
    qml.write_bytes(qml.read_bytes().replace(b"Run();", b"Run(1);"))
    result = facade(tmp_path)
    facts = {node["label"]: fact for node, fact in members(result)}
    assert facts[".Run()"]["ambiguous"] is True and facts[".run()"]["ambiguous"] is False
    expected, = [node["id"] for node in owned(result) if node["label"] == ".run()"]
    native = [edge for edge in result["edges"] if edge.get("context") == "qml_js_call"]
    assert len(native) == 1 and native[0]["target"] == expected


def test_req_qml022_ac06_namespaced_header_body_pairs_keep_exact_case_endpoints(tmp_path):
    """Separate actual source files bind each case-specific body to its own declaration."""
    header = ("namespace Public{class Panel:public QObject{Q_OBJECT QML_NAMED_ELEMENT(CaseOwner)"
              "public:Q_INVOKABLE void Run();Q_SLOT void run();};}\n").encode()
    body = b"void upper(){}void lower(){}namespace Public{void Panel::Run(){upper();}void Panel::run(){lower();}}\n"
    project(tmp_path, b"// actual body supplied separately\n", native=True)
    (tmp_path / "unit.h").write_bytes(header)
    (tmp_path / "unit.cpp").write_bytes(body)
    metadata = tmp_path / "CMakeLists.txt"
    metadata.write_bytes(metadata.read_bytes().replace(b"SOURCES unit.cpp", b"SOURCES unit.h unit.cpp"))
    result = facade(tmp_path)
    methods = {node["label"]: node for node in owned(result)}
    assert set(methods) == {".Run()", ".run()"} and len({node["id"] for node in methods.values()}) == 2
    native = [edge for edge in result["edges"] if edge.get("context") == "qml_js_call"]
    assert {edge["target"] for edge in native} == {node["id"] for node in methods.values()}
    labels = {node["id"]: node["label"] for node in result["nodes"]}
    calls = {(labels[edge["source"]], labels[edge["target"]]) for edge in result["edges"] if edge["relation"] == "calls"}
    assert (".Run()", "upper()") in calls and (".run()", "lower()") in calls
    for node in methods.values():
        assert node["source_file"] == "unit.h" and node["definition_file"] == "unit.cpp"
        assert span(header, node["metadata"]["cpp_member"])


def test_req_qml022_ac06_body_only_owner_and_member_collisions_compose_without_fact_loss(tmp_path):
    """Four actual qualified bodies retain both literal class and member distinctions."""
    header = ("class Box{public:void Run();void run();};\n"
              "class box{public:void Run();void run();};\n").encode()
    body = ("#include \"unit.h\"\nvoid upper(){}void lower(){}\n"
            "void Box::Run(){upper();}\nvoid Box::run(){lower();}\n"
            "void box::Run(){upper();}\nvoid box::run(){lower();}\n").encode()
    path = project(tmp_path, body)
    (tmp_path / "unit.h").write_bytes(header)
    direct = extract_cpp(path)
    found = members(direct)
    assert len(found) == 4 and len({node["id"] for node, _ in found}) == 4
    assert all(fact["role"] == "definition" and not fact["ambiguous"] for _, fact in found)
    result = facade(tmp_path)
    canonical = members(result)
    assert len(canonical) == 4 and len({node["id"] for node, _ in canonical}) == 4
    for node, fact in canonical:
        assert fact["role"] == "declaration" and node["definition_file"] == "unit.cpp"
        assert span(header, fact)
    for name in ("Box", "box"):
        selected = {node["label"]: node["id"] for node in owned(result, name)}
        assert set(selected) == {".Run()", ".run()"}
        labels = {node["id"]: node["label"] for node in result["nodes"]}
        pairs = {(edge["source"], labels[edge["target"]]) for edge in result["edges"] if edge["relation"] == "calls"}
        assert (selected[".Run()"], "upper()") in pairs and (selected[".run()"], "lower()") in pairs
    output = tmp_path / "accepted.json"
    assert to_json(build_from_json(result, root=tmp_path), {}, str(output), force=True)
    restored = load_node_link_graph(json.loads(output.read_text(encoding="utf-8")))
    assert all(restored.nodes[node["id"]]["definition_file"] == "unit.cpp" for node, _ in canonical)


def test_req_qml022_ac06_source_candidate_cannot_borrow_a_foreign_allocated_owner(tmp_path):
    """Actual parsed entries and legacy candidates reject wrong owner correspondence."""
    path = project(tmp_path, b"class Panel{int Field;double field;};\n")
    unit = read_cpp(path, tmp_path)
    identities = CppIdentity(unit.tree, unit.source, _file_stem(path))
    functions = CppFunctions(unit.tree, unit.source, _file_stem(path))
    index = CppMemberNames(identities, functions)
    record, = identities.records.values()
    field, = [node for node in walk(unit.tree) if node.type == "field_identifier" and unit.text(node) == "Field"]
    plain = _make_id(record["id"], "Field")
    repaired = index.candidate(field, plain)
    assert repaired != plain and repaired == index.candidate(field, plain, owner_id=record["id"])
    assert index.candidate(field, plain, owner_id="foreign") == plain
    assert index.candidate(field, plain, owner_id=[]) == plain
