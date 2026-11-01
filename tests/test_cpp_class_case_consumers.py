"""INC-QML-110: exact class owners reach constructors, body joins and QML."""
from __future__ import annotations

import base64
import hashlib
from copy import deepcopy

import pytest

from graphify.extract import extract, extract_cpp
from graphify.extractors.base import _file_stem, _make_id
from graphify.extractors.cpp_constructor_binding import id_authorized
from graphify.extractors.cpp_constructors import _fact, bind_cpp_constructors, constructor_class_authorized
from graphify.extractors.cpp_member_identity import member_fact
from graphify.extractors.qt_cpp_facts import qt_metadata
from tests.cpp_class_case_helpers import classes, member_calls, produced


def test_req_qml022_ac02_class_case_inline_constructors_and_destructors_keep_owners(tmp_path):
    """New collision prefixes retain the old exact constructor authorization suffix."""
    raw = (b"void helper(){}\nstruct Box{Box(){helper();}~Box(){helper();}};\n"
           b"struct box{box(){helper();}~box(){helper();}};\n")
    result = produced(tmp_path, raw)
    owners = classes(result)
    assert set(owners) == {"Box", "box"}
    constructors = [(node, fact) for node in result["nodes"] if (fact := _fact(node, "cpp_constructor"))]
    assert len(constructors) == 2 and len({node["id"] for node, _ in constructors}) == 2
    for node, fact in constructors:
        owner = base64.b64decode(fact["owner_b64"]).decode()
        assert id_authorized(node, owner, fact["signature"])
        assert any(edge["source"] == owners[owner]["id"] and edge["target"] == node["id"]
                   and edge.get("relation") == "method" for edge in result["edges"])
    destructors = [node for node in result["nodes"] if node["label"] in {".~Box()", ".~box()"}]
    assert len(destructors) == 2 and len({node["id"] for node in destructors}) == 2
    assert len([edge for edge in result["edges"] if edge.get("relation") == "calls"]) == 4


@pytest.mark.parametrize("damage", ["wrong_case", "foreign_prefix", "other_case_prefix"])
def test_req_qml022_ac06_collision_constructor_suffix_does_not_replace_source_ownership(tmp_path, damage):
    """The unchanged suffix predicate alone never proves actual allocated class ownership."""
    result = deepcopy(produced(tmp_path, b"struct Box{Box(){}};struct box{box(){}};"))
    node, = [node for node in result["nodes"] if node["label"] == ".Box()"]
    lower, = [node for node in result["nodes"] if node["label"] == ".box()"]
    fact = node["metadata"]["cpp_constructor"]
    assert constructor_class_authorized(node)
    if damage == "wrong_case":
        fact["owner_b64"] = base64.b64encode(b"box").decode()
    else:
        node["id"] = ("unowned_" + node["id"]) if damage == "foreign_prefix" else lower["id"]
        assert id_authorized(node, "Box", fact["signature"])
    bind_cpp_constructors(result["nodes"], result["edges"])
    assert not constructor_class_authorized(node)


@pytest.mark.parametrize("constructors", [False, True])
def test_req_qml008_ac02_class_case_sibling_header_source_keeps_both_actual_bodies(tmp_path, constructors):
    """Each source body remains distinct even when the class definitions are in an admitted header."""
    header, body = tmp_path / "panel.hpp", tmp_path / "panel.cpp"
    method = (lambda name: name) if constructors else (lambda name: "void run")
    header.write_bytes((f"struct Box{{{method('Box')}();}};\nstruct box{{{method('box')}();}};\n").encode())
    body.write_bytes(("#include \"panel.hpp\"\nvoid helper(){}\n" + "\n".join(
        (f"{name}::{name}" if constructors else f"void {name}::run") + "(){helper();}" for name in ("Box", "box"))).encode())
    direct = extract_cpp(body)
    facts = [(node, _fact(node, "cpp_constructor") if constructors else member_fact(node)) for node in direct["nodes"]]
    found = [(node, fact) for node, fact in facts if fact.get("role") == "definition"]
    assert len(found) == 2 and len({node["id"] for node, _ in found}) == 2
    result = extract([header, body], root=tmp_path, cache_root=tmp_path, parallel=False)
    assert set(classes(result)) == {"Box", "box"} and not result["failed_sources"]
    joined = [node for node in result["nodes"] if node.get("definition_file") == "panel.cpp"]
    assert len(joined) == 2 and len({node["id"] for node in joined}) == 2
    assert len([edge for edge in result["edges"] if edge.get("relation") == "calls"]) == 2


@pytest.mark.parametrize("split", [False, True])
def test_req_qml008_ac02_class_case_asymmetric_and_split_bodies_keep_exact_source_caller(tmp_path, split):
    """A partial body cohort cannot choose the other literal class or rewrite its calls."""
    header = tmp_path / "panel.hpp"
    header.write_bytes(b"struct Box{void run();};\nstruct box{void run();};\n")
    paths = [header]
    for name, suffix in ([("Box", ".cpp"), ("box", ".cc")] if split else [("box", ".cpp")]):
        path = tmp_path / ("panel" + suffix)
        path.write_bytes((f'#include "panel.hpp"\nvoid helper{name}(){{}}\nvoid {name}::run(){{helper{name}();}}\n').encode())
        paths.append(path)
    result = extract(paths, root=tmp_path, cache_root=tmp_path, parallel=False)
    owners = classes(result)
    assert set(owners) == {"Box", "box"}
    for name in (["Box", "box"] if split else ["box"]):
        method, = [edge["target"] for edge in result["edges"] if edge["source"] == owners[name]["id"] and edge.get("relation") == "method"]
        helper, = [node for node in result["nodes"] if node["label"] == f"helper{name}()"]
        assert any(edge["source"] == method and edge["target"] == helper["id"]
                   and edge.get("relation") == "calls" for edge in result["edges"])


@pytest.mark.parametrize("marker", ["", "Q_INVOKABLE"])
def test_req_qml022_ac02_class_case_native_qml_members_use_actual_class_ids(tmp_path, marker):
    """Separate source names do not relax ordinary-member or native/provider gates."""
    source = "#include <QObject>\n" + "\n".join(
        f"class {owner}:public QObject{{Q_OBJECT QML_NAMED_ELEMENT({exported}) public:{marker} void run(){{}}}};"
        for owner, exported in [("Box", "Upper"), ("box", "Lower")])
    cpp = tmp_path / "panel.cpp"
    cpp.write_bytes(source.encode())
    qml = []
    for name in ("Upper", "Lower"):
        path = tmp_path / (name + "Use.qml")
        path.write_bytes((f"import Public.Case 1.0\n{name}{{function invoke(){{run()}}}}\n").encode())
        qml.append(path)
    cmake = tmp_path / "CMakeLists.txt"
    cmake.write_bytes(b"qt_add_qml_module(app URI Public.Case VERSION 1.0 QML_FILES UpperUse.qml LowerUse.qml SOURCES panel.cpp)\n")
    result = extract([cpp, cmake, *qml], root=tmp_path, cache_root=tmp_path, parallel=False)
    owners = classes(result)
    assert set(owners) == {"Box", "box"} and not result["qml_failures"]
    links = [edge for edge in result["edges"] if edge.get("context") == "qml_js_call"]
    assert len(links) == (2 if marker else 0)
    if marker:
        assert {qt_metadata(edge)["native_endpoint"]["class_id"] for edge in links} == {node["id"] for node in owners.values()}
    assert not member_calls(result)


@pytest.mark.parametrize("constructors", [False, True])
def test_req_qml008_ac02_body_owner_domains_reserve_literal_qualifier_candidates(tmp_path, constructors):
    """Header-free callable spelling separates IDs without fabricating class authority."""
    lookalike = "cppq_" + hashlib.sha256(b"Box").hexdigest() + "_Box"
    names = ["Box", "box", lookalike]
    header, body = tmp_path / "panel.hpp", tmp_path / "panel.cpp"
    header.write_bytes("".join(f"struct {name}{{" + (name if constructors else "void run") + "();};\n"
                               for name in names).encode())
    body.write_bytes(("void helper(){}\n" + "".join((f"{name}::{name}" if constructors else f"void {name}::run")
                     + "(){helper();}\n" for name in reversed(names))).encode())
    direct = extract_cpp(body)
    facts = [(node, _fact(node, "cpp_constructor") if constructors else member_fact(node)) for node in direct["nodes"]]
    definitions = [node for node, fact in facts if fact.get("role") == "definition"]
    assert len(definitions) == 3 and len({node["id"] for node in definitions}) == 3
    assert not classes(direct)
    result = extract([header, body], root=tmp_path, cache_root=tmp_path, parallel=False)
    assert set(classes(result)) == set(names) and not result["failed_sources"]
    assert len([node for node in result["nodes"] if node.get("definition_file") == "panel.cpp"]) == 3
    assert len([edge for edge in result["edges"] if edge.get("relation") == "calls"]) == 3


@pytest.mark.parametrize("constructors", [False, True])
def test_req_qml008_ac02_class_collision_domain_reserves_provisional_body_owner(tmp_path, constructors):
    """A parsed qualifier reserves its ordinary spelling without becoming a class fact."""
    lookalike = "cppq_" + hashlib.sha256(b"Box").hexdigest() + "_Box"
    header, body = tmp_path / "panel.hpp", tmp_path / "panel.cpp"
    header.write_bytes((f"struct {lookalike}{{" + (lookalike if constructors else "void run") + "();};").encode())
    raw = '#include "panel.hpp"\nvoid helper(){}\n'
    raw += "".join(f"struct {name}{{" + (name if constructors else "void run") + "(){helper();}};\n" for name in ("Box", "box"))
    raw += (f"{lookalike}::{lookalike}" if constructors else f"void {lookalike}::run") + "(){helper();}\n"
    body.write_bytes(raw.encode())
    direct = extract_cpp(body)
    owners = classes(direct)
    assert set(owners) == {"Box", "box"}
    reserved = _make_id(_file_stem(body), lookalike)
    assert all(node["id"] != reserved for node in owners.values())
    facts = [(node, _fact(node, "cpp_constructor") if constructors else member_fact(node)) for node in direct["nodes"]]
    callables = [node for node, fact in facts if fact]
    assert len(callables) == 3 and len({node["id"] for node in callables}) == 3
    assert len([fact for _, fact in facts if fact.get("role") == "definition"]) == (3 if constructors else 1)
    result = extract([header, body], root=tmp_path, cache_root=tmp_path, parallel=False)
    assert set(classes(result)) == {"Box", "box", lookalike} and not result["failed_sources"]
    assert len([edge for edge in result["edges"] if edge.get("relation") == "calls"]) == 3
