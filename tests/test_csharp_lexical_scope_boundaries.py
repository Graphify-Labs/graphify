"""INC-QML-84: paired visibility, identifier and body-owner boundaries."""
from __future__ import annotations

import base64

import pytest

from graphify.extract import extract, extract_csharp
from tests.test_csharp_lexical_calls import calls, local_functions


@pytest.mark.parametrize("statement", [
    "foreach(System.Action callback in values){\ncallback();\n}",
    "for(System.Action callback=null;true;){\ncallback();break;\n}",
    "using(System.IDisposable callback=null){\ncallback();\n}",
    "try{}catch(System.Exception callback){\ncallback();\n}",
    "{System.Action callback=null;\ncallback();\n}",
])
def test_req_qml022_ac06_data_binding_rejection_ends_at_its_actual_scope(tmp_path, statement):
    """Reject inner runtime data while preserving the later actual class-method call and its line."""
    path = tmp_path / "Data.cs"
    source = "class Holder{void callback(){} void Use(System.Action[] values){\n" + statement + "\ncallback();\n}}"
    path.write_text(source)
    expected_line = "L" + str(source[:source.rfind("callback();")].count("\n") + 1)
    result = extract([path], root=tmp_path, cache_root=tmp_path, parallel=False)
    target = next(node["id"] for node in result["nodes"] if node["label"] == ".callback()")
    matching = [edge for edge in calls(result) if edge["target"] == target]
    assert len(matching) == 1 and matching[0]["source_location"] == expected_line


@pytest.mark.parametrize("parameter", ["callback", "(callback)"])
def test_req_qml022_ac06_lambda_parameter_is_data_without_runtime_dispatch(tmp_path, parameter):
    """A source lambda binder cannot lend Other.callback() to its containing method."""
    path = tmp_path / "Data.cs"
    path.write_text("class Holder{void Use(){System.Action<System.Action> apply=" + parameter
                    + "=>callback();}}class Other{void callback(){}}")
    result = extract_csharp(path)
    assert not calls(result)


@pytest.mark.parametrize("name", ["@callback", "_", "réparer"])
def test_req_qml022_ac02_new_local_role_ids_preserve_literal_identifier_without_prefix_collapse(tmp_path, name):
    """The new scoped ID role safely retains escapes/Unicode/underscore without changing legacy globals."""
    path = tmp_path / "Data.cs"
    path.write_text("class Holder{void Use(){void " + name + "(){} " + name.removeprefix("@") + "();}}")
    result = extract_csharp(path)
    (local,) = local_functions(result)
    assert base64.b64decode(local["metadata"]["csharp_local_function"]["raw_name_b64"]).decode() == name
    assert "::local-function::" in local["id"]
    assert any(edge["target"] == local["id"] for edge in calls(result))


def test_req_qml022_ac06_local_and_class_member_calls_keep_their_source_roles(tmp_path):
    """A local body sees its containing class; locals never become ordinary class members."""
    path = tmp_path / "Data.cs"
    path.write_text("class Holder{System.Action callback;void Helper(){} void Use(){"
                    "void Local(){callback();Helper();} Local();}} class Other{void Helper(){}void callback(){}}")
    result = extract([path], root=tmp_path, cache_root=tmp_path, parallel=False)
    (local,) = local_functions(result)
    by_id = {node["id"]: node for node in result["nodes"]}
    owned = [edge for edge in calls(result) if edge["source"] == local["id"]]
    assert len(owned) == 1 and by_id[owned[0]["target"]]["label"] == ".Helper()"
    parent = next(edge["source"] for edge in result["edges"] if edge["target"] == owned[0]["target"] and edge["relation"] == "method")
    assert by_id[parent]["label"] == "Holder"


def test_req_qml022_ac02_constructor_local_uses_existing_constructor_owner(tmp_path):
    """Existing C# constructor bodies belong to their type; no invented constructor node is needed."""
    path = tmp_path / "Data.cs"
    path.write_text("class Holder{public Holder(){void Local(){} Local();}}")
    result = extract_csharp(path)
    (local,) = local_functions(result)
    owner = next(node["id"] for node in result["nodes"] if node["label"] == "Holder")
    assert any(edge["source"] == owner and edge["target"] == local["id"] and edge["relation"] == "contains" for edge in result["edges"])
    assert any(edge["source"] == owner and edge["target"] == local["id"] for edge in calls(result))


def test_req_qml022_ac02_file_scoped_namespace_is_part_of_local_source_identity(tmp_path):
    """A file-scoped namespace owns following sibling classes even without an AST body wrapper."""
    path = tmp_path / "Data.cs"
    source = "namespace First; class Holder{void Use(){void Local(){}Local();}}"
    path.write_text(source)
    (first,) = local_functions(extract_csharp(path))
    path.write_text(source.replace("First", "Second"))
    (second,) = local_functions(extract_csharp(path))
    assert first["id"] != second["id"]
    assert first["metadata"]["csharp_local_function"]["scope_fingerprint"] != second["metadata"]["csharp_local_function"]["scope_fingerprint"]


def test_req_qml022_ac02_generic_type_arity_keeps_local_identity_when_source_order_changes(tmp_path):
    """Two genuine generic owner types cannot exchange local identities when declarations reorder."""
    path = tmp_path / "Data.cs"
    bodies = ["class Holder<T>{void Use(){void Local(){}Local();}}",
              "class Holder<T,U>{void Use(){void Local(){}Local();}}"]

    def owners(result):
        parent = {edge["target"]: edge["source"] for edge in result["edges"] if edge["relation"] == "method"}
        return {parent[edge["source"]]: edge["target"] for edge in result["edges"]
                if edge.get("context") == "csharp_local_function"}

    path.write_text("".join(bodies))
    initial = owners(extract_csharp(path))
    path.write_text("".join(reversed(bodies)))
    assert owners(extract_csharp(path)) == initial


def test_req_qml022_ac06_deconstruction_retains_every_data_binder_without_binding_discard(tmp_path):
    """All tuple declarations reject global callbacks; `_` pattern discard preserves a real local `_()`."""
    path = tmp_path / "Data.cs"
    path.write_text("class Holder{void Use(){void _(){} var(callback,other)=Pair();callback();other();"
                    "var(_,last)=Pair();_();}}class Other{void callback(){}void other(){}}")
    result = extract_csharp(path)
    (local,) = local_functions(result)
    matching = [edge for edge in calls(result) if edge["target"] != local["id"]]
    by_id = {node["id"]: node for node in result["nodes"]}
    assert not any(by_id.get(edge["target"], {}).get("label") in {".callback()", ".other()"} for edge in matching)
    assert any(edge["target"] == local["id"] for edge in calls(result))


def test_req_qml022_ac06_local_type_parameter_cannot_borrow_an_unrelated_class(tmp_path):
    """A local function's T is a type parameter, even when a source class is also named T."""
    path = tmp_path / "Data.cs"
    path.write_text("class T{public void Run(){}}class Holder{void Use(){"
                    "void Local<T>(T worker){worker.Run();}Local(1);}}")
    result = extract([path], root=tmp_path, cache_root=tmp_path, parallel=False)
    (local,) = local_functions(result)
    assert not any(edge["source"] == local["id"] for edge in calls(result))


@pytest.mark.parametrize("body", ["T worker=default;worker.Run();",
                                       "foreach(T worker in values){worker.Run();}"])
def test_req_qml022_ac06_local_generic_data_has_no_concrete_receiver_authority(tmp_path, body):
    """Local declarations and loop binders share the local callable's actual generic scope."""
    path = tmp_path / "Data.cs"
    path.write_text("class T{public void Run(){}}class Holder{void Use(){"
                    "void Local<T>(T[] values){" + body + "}Local(null);}}")
    result = extract([path], root=tmp_path, cache_root=tmp_path, parallel=False)
    (local,) = local_functions(result)
    assert not any(edge["source"] == local["id"] for edge in calls(result))


def test_req_qml022_ac06_local_concrete_parameter_retains_its_receiver(tmp_path):
    """Rejecting generic data preserves a source-proven concrete receiver inside the local body."""
    path = tmp_path / "Data.cs"
    path.write_text("class Worker{public void Run(){}}class Holder{void Use(){"
                    "void Local<T>(Worker worker){worker.Run();}Local<int>(null);}}")
    result = extract([path], root=tmp_path, cache_root=tmp_path, parallel=False)
    (local,) = local_functions(result)
    target = next(node["id"] for node in result["nodes"] if node["label"] == ".Run()")
    assert any(edge["source"] == local["id"] and edge["target"] == target for edge in calls(result))


@pytest.mark.parametrize("declaration,call,accepted", [
    ("void Local<T>(){}", "Local<int>();", True),
    ("void Local<T>(){}", "Local<int,string>();", False),
    ("void Local(){}", "Local<int>();", False),
])
def test_req_qml022_ac06_explicit_local_type_arguments_match_source_arity(tmp_path, declaration, call, accepted):
    """An explicitly incompatible type-argument list cannot lend concrete source-call authority."""
    path = tmp_path / "Data.cs"
    path.write_text("class Holder{void Use(){" + declaration + call + "}}")
    result = extract_csharp(path)
    (local,) = local_functions(result)
    assert any(edge["target"] == local["id"] for edge in calls(result)) is accepted


def test_req_qml022_ac06_oversize_local_spelling_retains_fact_without_lookup_authority(tmp_path):
    """A bounded display contract cannot truncate a large raw identifier into a concrete call target."""
    path = tmp_path / "Data.cs"
    name = "callback" + "x" * 400
    path.write_text("class Holder{void Use(){void " + name + "(){}" + name + "();}}")
    for result in (extract_csharp(path), extract([path], root=tmp_path, cache_root=tmp_path, parallel=False)):
        (local,) = local_functions(result)
        fact = local["metadata"]["csharp_local_function"]
        assert fact["name_status"] == "oversize" and fact["raw_name_b64"] == ""
        assert len(fact["scope_fingerprint"]) == 64 and name not in local["id"]
        assert len(local["id"].split("::local-function::", 1)[1]) == 64
        assert not any(edge["target"] == local["id"] for edge in calls(result))


def test_req_qml022_ac06_partial_enclosing_body_keeps_local_fact_but_rejects_binding(tmp_path):
    """An incomplete owner cannot authorize a positive local call just because the inner body is clean."""
    path = tmp_path / "Data.cs"
    path.write_text("class Holder{void Use(){void Local(){}Local();")
    result = extract_csharp(path)
    (local,) = local_functions(result)
    assert local["metadata"]["csharp_local_function"]["partial"] is True
    assert not any(edge["target"] == local["id"] for edge in calls(result))


def test_req_qml022_ac06_typed_foreach_deconstruction_data_ends_at_the_loop(tmp_path):
    """Each actual typed loop binder rejects delegate dispatch without hiding a later class method."""
    path = tmp_path / "Data.cs"
    path.write_text("class Holder{void callback(){}void Use((System.Action,System.Action)[] values){\n"
                    "foreach((System.Action callback,System.Action other) in values){callback();other();}\n"
                    "callback();\n}}")
    result = extract_csharp(path)
    target = next(node["id"] for node in result["nodes"] if node["label"] == ".callback()")
    matching = [edge for edge in calls(result) if edge["target"] == target]
    assert len(matching) == 1 and matching[0]["source_location"] == "L3"
