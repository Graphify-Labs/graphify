"""Standalone MATLAB extraction contract; normal dispatch is tested separately."""

from pathlib import Path

import pytest

from graphify.build import build
from graphify.extract import extract
from graphify.extractors.base import set_active_scan_root
from graphify.extractors.matlab import extract_matlab


def extract_source(tmp_path, source, name="main.m"):
    path = tmp_path / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source)
    previous = set_active_scan_root(tmp_path)
    try:
        return extract_matlab(path)
    finally:
        set_active_scan_root(previous)


def extract_fixture(tmp_path, filename, name):
    fixture = Path(__file__).parent / "fixtures" / "matlab" / "frontend" / filename
    return extract_source(tmp_path, fixture.read_text(), name)


def definitions(result):
    return [node for node in result["nodes"] if node["metadata"]["kind"] != "matlab_file"]


def call_sites(result):
    labels = {node["id"]: node["label"] for node in result["nodes"]}
    return [(labels[edge["source"]], labels[edge["target"]], edge["source_location"])
            for edge in result["edges"] if edge["relation"] == "calls"]


def test_structure_owns_methods_and_nested_functions(tmp_path):
    result = extract_fixture(tmp_path, "structure.m", "+pkg/C.m")
    found = {node["label"]: node for node in definitions(result)}
    assert set(found) == {"C", "declared", "run", "nested", "helper"}
    assert found["C"]["metadata"]["matlab_superclasses"] == [
        {"name": "pkg.Base", "source_location": "L1"},
        {"name": "handle", "source_location": "L1"},
    ]
    assert found["declared"]["metadata"]["matlab_declaration_only"] is True
    assert found["nested"]["metadata"]["scope_chain"] == ["C", "run"]
    assert found["helper"]["metadata"]["scope_chain"] == []
    assert all(node["metadata"]["language"] == "matlab" for node in result["nodes"])
    assert result["nodes"][0]["metadata"]["matlab_file_kind"] == "class"
    assert result["nodes"][0]["metadata"]["matlab_primary_name"] == "C"
    assert found["C"]["metadata"]["namespace"] == "pkg"
    ownership = {(edge["source"], edge["target"], edge["relation"])
                 for edge in result["edges"] if edge["relation"] in {"contains", "method"}}
    assert (found["C"]["id"], found["run"]["id"], "method") in ownership
    assert (found["C"]["id"], found["run"]["id"], "contains") not in ownership
    assert (found["run"]["id"], found["nested"]["id"], "contains") in ownership
    assert not result.get("raw_calls")


def test_identities_include_owner_and_declaration_location(tmp_path):
    source = """function main()
 function Foo()
 end
 function foo()
 end
 function left()
  function same()
  end
 end
 function right()
  function same()
  end
 end
end
"""
    first = extract_source(tmp_path / "one", source)
    second = extract_source(tmp_path / "two", source)
    assert len({node["id"] for node in definitions(first)}) == 7
    assert [node["id"] for node in first["nodes"]] == [node["id"] for node in second["nodes"]]


@pytest.mark.parametrize(("name", "namespace"), [
    ("src/+tools/+io/main.m", "tools.io"),
    ("+outer/plain/+inner/main.m", "inner"),
    ("+outer/plain/main.m", ""),
])
def test_namespace_is_contiguous_directory_context(tmp_path, name, namespace):
    result = extract_source(tmp_path, "function main()\nend\n", name)
    assert definitions(result)[0]["metadata"].get("namespace", "") == namespace


def test_nearest_lexical_tiers_and_recursion(tmp_path):
    result = extract_source(tmp_path, """function main()
 helper();
 main();
 function helper()
  helper();
  sibling();
 end
 function sibling()
  function deeper()
   helper();
  end
 end
end
function helper()
 helper();
end
function independent()
 sibling();
 helper();
end
""")
    assert call_sites(result) == [
        ("main", "helper", "L2"), ("main", "main", "L3"),
        ("helper", "helper", "L5"), ("helper", "sibling", "L6"),
        ("deeper", "helper", "L10"), ("helper", "helper", "L15"),
        ("independent", "helper", "L19"),
    ]
    calls = [edge for edge in result["edges"] if edge["relation"] == "calls"]
    assert calls[0]["target"] != calls[-1]["target"]
    assert all(edge["confidence"] == "EXTRACTED" and edge["weight"] == 1.0 for edge in calls)


def test_duplicate_tier_vetoes_instead_of_falling_back(tmp_path):
    result = extract_source(tmp_path, """function main()
 helper();
 function helper()
 end
 function helper()
 end
end
function helper()
end
""")
    assert len(definitions(result)) == 4
    assert call_sites(result) == []


def test_case_sensitive_lookup_and_primary_identity(tmp_path):
    result = extract_source(tmp_path, """function wrong()
 wrong();
 helper();
 Helper();
 HELPER();
end
function helper()
end
function Helper()
end
""")
    assert call_sites(result) == [("wrong", "helper", "L3"), ("wrong", "Helper", "L4")]
    assert result["nodes"][0]["metadata"]["matlab_file_kind"] == "function"
    assert result["nodes"][0]["metadata"]["matlab_primary_name"] == "wrong"


def test_methods_call_functions_but_not_methods_or_constructors(tmp_path):
    result = extract_source(tmp_path, """classdef C
 methods
  function run(obj)
   other(); C(); helper();
  end
  function other(obj)
  end
 end
end
function helper()
end
function other()
end
""", "C.m")
    assert call_sites(result) == [("run", "helper", "L4")]


def test_repeated_call_sites_remain_distinct(tmp_path):
    result = extract_source(tmp_path, "function main()\n helper();\n helper();\nend\nfunction helper()\nend\n")
    assert call_sites(result) == [("main", "helper", "L2"), ("main", "helper", "L3")]


def test_fixture_lexical_visibility_and_local_function_scope(tmp_path):
    result = extract_fixture(tmp_path, "scopes.m", "scopes.m")
    assert call_sites(result) == [
        ("entry", "local", "L2"),
        ("local", "sibling", "L4"),
        ("sibling", "local", "L7"),
        ("public", "local", "L12"),
    ]
    assert not result.get("raw_calls")


@pytest.mark.parametrize(("header", "prefix", "body"), [
    ("function caller(helper)", "", ""),
    ("function [helper, output] = caller()", "", ""),
    ("function caller()", "arguments\n helper (1, 1) double\nend\n", ""),
    ("function caller()", "", "helper = 1;"),
    ("function caller()", "", "[helper, other] = deal(1, 2);"),
    ("function caller()", "", "helper(1) = 1;"),
    ("function caller()", "", "helper{1} = 1;"),
    ("function caller()", "", "helper.field = 1;"),
    ("function caller()", "", "for helper = 1:2\n end"),
    ("function caller()", "", "parfor helper = 1:2\n end"),
    ("function caller()", "", "try\n catch helper\n end"),
    ("function caller()", "", "global helper;"),
    ("function caller()", "", "persistent helper;"),
    ("function caller()", "", "if true\n helper = 1;\n end"),
])
def test_whole_scope_bindings_veto_calls(tmp_path, header, prefix, body):
    source = (
        f"{header}\n{prefix} helper();\n{body}\nend\n"
        "function helper()\nend\n"
    )
    assert call_sites(extract_source(tmp_path, source)) == []


def test_field_name_is_not_a_variable_binding(tmp_path):
    result = extract_source(tmp_path, """function caller()
 object.helper = 1;
 helper();
end
function helper()
end
""")
    assert call_sites(result) == [("caller", "helper", "L3")]


def test_ancestor_bindings_apply_but_sibling_bindings_do_not_leak(tmp_path):
    result = extract_source(tmp_path, """function main()
 helper = 1;
 function nested()
  helper();
 end
 function sibling()
  helper();
 end
end
function assigned()
 helper();
 helper = 1;
end
function independent()
 helper();
end
function clean()
 helper();
end
function helper()
end
""")
    assert call_sites(result) == [
        ("independent", "helper", "L15"),
        ("clean", "helper", "L18"),
    ]


def test_script_workspace_is_not_a_calling_scope(tmp_path):
    result = extract_source(tmp_path, """helper();
helper = 1;
function local()
 helper();
end
function helper()
end
""")
    assert result["nodes"][0]["metadata"]["matlab_file_kind"] == "script"
    assert call_sites(result) == [("local", "helper", "L4")]


@pytest.mark.parametrize("barrier", [
    "import pkg.helper",
    "run_script arg",
    "eval('x');",
    "evalin('base', 'x');",
    "assignin('base', 'x', 1);",
    "load('data.mat');",
    "clear helper",
])
def test_workspace_barriers_suppress_the_entire_callable_scope(tmp_path, barrier):
    result = extract_source(tmp_path, f"""function caller()
 helper();
 {barrier}
 helper();
end
function helper()
end
""")
    assert call_sites(result) == []


def test_workspace_barrier_flows_to_nested_functions_only(tmp_path):
    result = extract_source(tmp_path, """function main()
 eval('x');
 function child()
  helper();
 end
end
function independent()
 helper();
end
function helper()
end
""")
    assert call_sites(result) == [("independent", "helper", "L8")]


def test_unqualified_call_argument_inside_member_call_survives_build(tmp_path):
    path = tmp_path / "main.m"
    path.write_text(
        "function main(obj)\nobj.run(helper());\nend\nfunction helper()\nend\n"
    )
    extraction = extract(
        [path], root=tmp_path, cache_root=tmp_path / "cache", parallel=False,
    )
    assert call_sites(extraction) == [("main", "helper", "L2")]

    graph = build([extraction], dedup=False, root=tmp_path)
    main = next(node["id"] for node in extraction["nodes"] if node["label"] == "main")
    helper = next(node["id"] for node in extraction["nodes"] if node["label"] == "helper")
    assert graph.edges[main, helper]["relation"] == "calls"


def test_indexing_qualified_dynamic_and_handle_forms_are_not_calls(tmp_path):
    result = extract_source(tmp_path, """function caller()
 A = [1, 2];
 A(1);
 A{1};
 indexed(1) = 2;
 pkg.helper();
 obj.helper();
 feval('helper');
 callback = @helper;
 anonymous = @(x) helper(x);
 helper();
end
function A()
end
function indexed()
end
function helper()
end
""")
    assert call_sites(result) == [("caller", "helper", "L11")]


def test_parser_error_is_contained_to_its_callable_scope(tmp_path):
    result = extract_source(tmp_path, """function broken()
 helper();
 value = ;
end
function clean()
 helper();
end
function helper()
end
""")
    assert {node["label"] for node in definitions(result)} == {"broken", "clean", "helper"}
    assert call_sites(result) == [("clean", "helper", "L6")]


def test_file_paths_keep_same_named_definitions_distinct(tmp_path):
    source = "function main()\n helper();\nend\nfunction helper()\nend\n"
    left = extract_source(tmp_path, source, "left/main.m")
    right = extract_source(tmp_path, source, "right/main.m")
    left_ids = {node["id"] for node in definitions(left)}
    right_ids = {node["id"] for node in definitions(right)}
    assert left_ids.isdisjoint(right_ids)
    assert call_sites(left) == [("main", "helper", "L2")]
    assert call_sites(right) == [("main", "helper", "L2")]


def test_cell_indexing_is_never_a_call_even_without_a_local_binding(tmp_path):
    result = extract_source(tmp_path, """function caller()
 A{1};
end
function A()
end
""")
    assert call_sites(result) == []
