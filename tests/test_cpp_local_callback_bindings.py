"""INC-QML-108: local callback data cannot become a global function target."""
import json

import pytest

from graphify.build import build_from_json
from graphify.export import to_json
from graphify.paths import load_node_link_graph
from tests.cpp_local_callback_helpers import callback_sites, extracted, helper_edges, payload, source


@pytest.mark.parametrize("member", [False, True])
@pytest.mark.parametrize("declaration,call", [
    ("void (*helper)()=nullptr;", "helper();"),
    ("void (*helper)();", "helper();"),
    ("int (*helper)()=nullptr;", "helper();"),
    ("void ((*helper))()=nullptr;", "helper();"),
    ("void (*helper) /* original comment */ ()=nullptr;", "helper();"),
    ("void (*helper)(int)=nullptr;", "helper(1);"),
])
def test_req_qml022_ac06_callback_binding_blocks_direct_and_facade_guesses(tmp_path, member, declaration, call):
    """An original primitive callback binder supplies a rejection-only lexical name."""
    path = tmp_path / "unit.cpp"
    raw = ("\ufeff// café 雪\n" + source(declaration + call + "other();", member=member)).replace("\n", "\r\n").encode()
    path.write_bytes(raw)
    for phase, result in zip(("direct", "facade"), extracted(path)):
        assert not helper_edges(result)
        sites = callback_sites(result)
        if phase == "direct":
            assert sites and all(site["cpp_free_call"]["shadowed"] for site in sites)
        for site in sites:
            fact = site["cpp_free_call"]
            span = fact["span"]
            assert raw[span["start_byte"]:span["end_byte"]] == call.removesuffix(";").encode()
            prefix = raw[:span["start_byte"]]
            assert (span["start_row"], span["start_column"]) == (prefix.count(b"\n"), len(prefix.rsplit(b"\n", 1)[-1]))
        assert not any(node["label"] == "helper" for node in result["nodes"])
        graph = build_from_json(result, root=tmp_path, directed=False)
        output = tmp_path / (phase + ".json")
        assert to_json(graph, {}, str(output), force=True)
        assert not helper_edges(payload(load_node_link_graph(json.loads(output.read_text(encoding="utf-8")))))


@pytest.mark.parametrize("declaration", ["void (*helper)()", "void (*helper)(int)"])
def test_req_qml022_ac06_callback_point_of_declaration_precedes_own_initializer(tmp_path, declaration):
    """Calling a newly declared, uninitialized callback does not call a global namesake."""
    path = tmp_path / "unit.cpp"
    path.write_bytes(source(declaration + "=helper();").encode())
    for result in extracted(path):
        assert not helper_edges(result)
        if "raw_calls" in result:
            assert callback_sites(result) and all(site["cpp_free_call"]["shadowed"] for site in callback_sites(result))


@pytest.mark.parametrize("body,expected", [
    ("helper();void (*helper)()=nullptr;", [False]),
    ("{void (*helper)()=nullptr;helper();}helper();", [True, False]),
    ("for(void (*helper)()=nullptr;keep();){helper();}helper();", [True, False]),
    ("auto action=[](){void (*helper)()=nullptr;helper();};helper();", [True, False]),
    ("auto action=[](void (*helper)()){helper();};helper();", [True, False]),
    ("class Inner{void method(int helper){}};helper();", [False]),
    ("class Inner{void (*helper)();};helper();", [False]),
    ("void (*callback)(int helper)=nullptr;helper();", [False]),
    ("void other(int helper);helper();", [False]),
    ("if(keep()) void (*helper)()=nullptr; else helper();helper();", [False, False]),
    ("while(keep()) void (*helper)()=nullptr;helper();", [False]),
    ("do void (*helper)()=nullptr; while(keep());helper();", [False]),
    ("void (*callbacks[1])()={nullptr};for(auto helper:callbacks){helper();}helper();", [True, False]),
    ("struct Callback{void operator()()const;};try{}catch(Callback helper){helper();}helper();", [True, False]),
])
def test_req_qml022_ac06_callback_shadow_stays_in_actual_order_and_scope(tmp_path, body, expected):
    """A nested binder cannot retire a global call before declaration or outside its scope."""
    path = tmp_path / "unit.cpp"
    path.write_bytes(source(body).encode())
    for result in extracted(path):
        assert len(helper_edges(result)) == 1
        if "raw_calls" in result:
            assert [site["cpp_free_call"]["shadowed"] for site in callback_sites(result)] == expected


def test_req_qml022_ac06_callback_parameter_remains_data_and_explicit_global_bypasses_local(tmp_path):
    """Existing parameter binding and actual absolute qualification retain their roles."""
    path = tmp_path / "unit.cpp"
    path.write_bytes(source("helper();::helper();", parameter="void (*helper)()").encode())
    for result in extracted(path):
        assert len(helper_edges(result)) == 1
        if "raw_calls" in result:
            assert [site["cpp_free_call"]["shadowed"] for site in callback_sites(result)] == [True, False]


@pytest.mark.parametrize("prefix", [
    'const char *text="void (*helper)()=nullptr;";',
    '/* void (*helper)()=nullptr; */',
    '\n#define TEXT void (*helper)()=nullptr;\n',
    'chooser(*helper)();',
])
def test_req_qml022_ac06_callback_lookalikes_cannot_create_a_binding(tmp_path, prefix):
    """Only the exact typed declaration role matters; opaque text and expressions do not."""
    path = tmp_path / "unit.cpp"
    path.write_bytes(source(prefix + "helper();").encode())
    for result in extracted(path):
        assert len(helper_edges(result)) == 1
        if "raw_calls" in result:
            assert callback_sites(result) and not any(site["cpp_free_call"]["shadowed"] for site in callback_sites(result))


def test_req_qml022_ac06_compound_assignment_is_not_a_callback_declaration(tmp_path):
    """A grammar-accepted nondeclaration cannot lend the new rejection-only binder."""
    path = tmp_path / "unit.cpp"
    path.write_bytes(source("void (*helper)()+=nullptr;helper();").encode())
    direct, _ = extracted(path)
    assert callback_sites(direct) and not any(site["cpp_free_call"]["shadowed"] for site in callback_sites(direct))


@pytest.mark.parametrize("prefix", ["int(*helper, other)();", "auto value=int(*helper)();"])
def test_req_qml022_ac06_nonstatement_or_multiple_argument_shape_lends_no_binder(tmp_path, prefix):
    """Grammar-accepted malformed expressions stay outside the declaration-only profile.

    This checks rejection-only source facts, without asserting compilation or
    runtime call behavior for these deliberately unsupported expressions.
    """
    path = tmp_path / "unit.cpp"
    path.write_bytes(source(prefix + "helper();").encode())
    direct, _ = extracted(path)
    assert callback_sites(direct) and not any(site["cpp_free_call"]["shadowed"] for site in callback_sites(direct))
