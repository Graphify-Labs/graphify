"""INC-QML-73: namespace text and local aliases retain distinct lookup roles."""
from __future__ import annotations

import base64

import pytest

from graphify.extract import extract
from graphify.extractors.cpp_functions import free_definition_fact


@pytest.mark.parametrize("namespace", ["First", "first"])
@pytest.mark.parametrize("alias_kind", ["using", "typedef"])
@pytest.mark.parametrize("alias_position,rooted,expected", [("before", False, None),
    ("after", False, "namespace"), ("before", True, "namespace"), ("none", False, "namespace")])
def test_req_qml022_ac06_local_type_alias_cannot_authorize_namespace_or_foreign_class(tmp_path, namespace, alias_kind, alias_position, rooted, expected):
    """A literal local alias is a rejection barrier; global qualification bypasses it."""
    path = tmp_path / "api.cpp"
    alias = f"using {namespace}=Other::{namespace};" if alias_kind == "using" else f"typedef Other::{namespace} {namespace};"
    call = ("::" if rooted else "") + namespace + "::work(1)"
    body = (alias if alias_position == "before" else "") + f"int value={call};" + (alias if alias_position == "after" else "") + "return value;"
    path.write_text(f"namespace {namespace}{{int work(int value){{return value;}}}}"
                    f"namespace Other{{class {namespace}{{public:static int work(int value){{return value;}}}};}}"
                    f"int caller(){{{body}}}")
    result = extract([path], root=tmp_path, cache_root=tmp_path, parallel=False)
    caller = next(node for node in result["nodes"] if node["label"] == "caller()")
    by_id = {node["id"]: node for node in result["nodes"]}
    targets = [by_id[edge["target"]] for edge in result["edges"] if edge["source"] == caller["id"] and edge["relation"] == "calls"]
    if expected is None:
        assert targets == []
    else:
        assert len(targets) == 1 and free_definition_fact(targets[0])
        assert base64.b64decode(targets[0]["metadata"]["cpp_function"]["qualified_name_b64"]).decode() == namespace + "::work"


@pytest.mark.parametrize("owner", ["Checks", "checks"])
def test_req_qml022_ac06_actual_qualified_class_method_keeps_member_resolution(tmp_path, owner):
    """A namespace correction cannot remove genuine explicit class calls or depend on capitals."""
    path = tmp_path / "api.cpp"
    path.write_text(f"int work(int value){{return value;}} class {owner}{{public:static int work(int value){{return value;}}}};"
                    f"int caller(){{return {owner}::work(1);}}")
    result = extract([path], root=tmp_path, cache_root=tmp_path, parallel=False)
    caller = next(node for node in result["nodes"] if node["label"] == "caller()")
    by_id = {node["id"]: node for node in result["nodes"]}
    targets = [by_id[edge["target"]] for edge in result["edges"] if edge["source"] == caller["id"] and edge["relation"] == "calls"]
    assert len(targets) == 1 and targets[0]["metadata"].get("cpp_member")


@pytest.mark.parametrize("prefix,body,expected", [
    ("// using namespace Other;\n", "return work();", True),
    ('', 'const char *text="using namespace Other;"; return work();', True),
    ("namespace Sibling{using namespace Other;}", "return work();", True),
    ("", "{using namespace Other;} return work();", True),
    ("using namespace Other;", "return work();", False),
    ("", "using namespace Other; return ::work();", True),
])
def test_req_qml022_ac06_using_namespace_uncertainty_follows_actual_ast_visibility(tmp_path, prefix, body, expected):
    """Comments, strings, sibling scopes and explicit roots cannot act as a using directive."""
    path = tmp_path / "api.cpp"
    path.write_text("int work(){return 1;} namespace Other{int work(){return 2;}}" + prefix
                    + "int caller(){" + body + "}")
    result = extract([path], root=tmp_path, cache_root=tmp_path, parallel=False)
    caller = next(node for node in result["nodes"] if node["label"] == "caller()")
    targets = [edge for edge in result["edges"] if edge["source"] == caller["id"] and edge["relation"] == "calls"]
    assert bool(targets) is expected
