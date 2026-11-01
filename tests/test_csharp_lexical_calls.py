"""INC-QML-84: local callables and runtime data keep exact C# lexical scope."""
from __future__ import annotations

import base64

import pytest

from graphify.extract import extract, extract_csharp


def local_functions(result):
    return [node for node in result["nodes"] if node.get("metadata", {}).get("csharp_local_function")]


def calls(result):
    return [edge for edge in result["edges"] if edge["relation"] in {"calls", "indirect_call"}]


@pytest.mark.parametrize("forward", [False, True])
@pytest.mark.parametrize("field", [False, True])
def test_req_qml022_ac02_local_function_is_source_owned_callable_and_beats_field(tmp_path, forward, field):
    """A forward local declaration owns its original span and contains edge, independently of fields."""
    path = tmp_path / "Data.cs"
    declaration = "int callback(int value){return value;}"
    invocation = "callback(1);"
    raw = ("\ufeff// café 雪\r\nclass Holder{" + ("System.Action<int> callback;" if field else "")
           + "void Use(){" + (invocation + declaration if forward else declaration + invocation) + "}}").encode()
    path.write_bytes(raw)
    for result in (extract_csharp(path), extract([path], root=tmp_path, cache_root=tmp_path, parallel=False)):
        (local,) = local_functions(result)
        fact = local["metadata"]["csharp_local_function"]
        assert local["_callable"] is True and not local.get("_callable_class")
        assert fact["contract_version"] == 1 and base64.b64decode(fact["raw_name_b64"]) == b"callback"
        span = fact["span"]
        assert raw[span["start_byte"]:span["end_byte"]] == declaration.encode()
        for actual in (span, fact["scope_span"]):
            for prefix in ("start", "end"):
                before = raw[:actual[prefix + "_byte"]]
                assert actual[prefix + "_row"] == before.count(b"\n")
                assert actual[prefix + "_column"] == len(before.rsplit(b"\n", 1)[-1])
        parent = next(node["id"] for node in result["nodes"] if node["label"] == ".Use()")
        assert any(edge["source"] == parent and edge["target"] == local["id"] and edge["relation"] == "contains" for edge in result["edges"])
        assert not any(edge["target"] == local["id"] and edge["relation"] == "method" for edge in result["edges"])
        assert any(edge["source"] == parent and edge["target"] == local["id"] for edge in calls(result))


@pytest.mark.parametrize("body", [
    "void Use(System.Action callback){callback();}",
    "void Use(){System.Action callback=null;callback();}",
    "void Use(){callback();System.Action callback=null;}",
    "void Use(System.Action[] items){foreach(System.Action callback in items){callback();}}",
    "void Use(){for(System.Action callback=null;true;){callback();break;}}",
    "void Use(){try{}catch(System.Exception callback){callback();}}",
    "void Use(){using(System.IDisposable callback=null){callback();}}",
])
def test_req_qml022_ac06_data_binders_reject_global_method_fallback_without_a_field(tmp_path, body):
    """Whole-block local scope and bounded statement binders cannot borrow Other.callback()."""
    path = tmp_path / "Data.cs"
    path.write_text("class Holder{" + body + "} class Other{public void callback(){}}")
    for result in (extract_csharp(path), extract([path], root=tmp_path, cache_root=tmp_path, parallel=False)):
        caller = next(node["id"] for node in result["nodes"] if node["label"] == ".Use()")
        assert not any(edge["source"] == caller and edge["target"].endswith("callback") for edge in calls(result))


def test_req_qml022_ac06_local_functions_never_enter_another_callables_global_map(tmp_path):
    """A same-named local is visible only in its declaring method's source block."""
    path = tmp_path / "Data.cs"
    path.write_text("class Holder{void Use(){void callback(){} callback();} void Outsider(){callback();}}"
                    "class Other{void Separate(){callback();}}")
    result = extract([path], root=tmp_path, cache_root=tmp_path, parallel=False)
    (local,) = local_functions(result)
    targets = [edge for edge in calls(result) if edge["target"] == local["id"]]
    callers = {node["id"]: node["label"] for node in result["nodes"]}
    assert len(targets) == 1 and callers[targets[0]["source"]] == ".Use()"


def test_req_qml022_ac02_sibling_blocks_keep_same_named_local_declarations(tmp_path):
    """Independent lexical blocks need distinct callable IDs despite identical signatures."""
    path = tmp_path / "Data.cs"
    path.write_text("class Holder{void Use(){{void callback(){}callback();}{void callback(){}callback();}}}")
    result = extract_csharp(path)
    locals_ = local_functions(result)
    assert len(locals_) == len({node["id"] for node in locals_}) == 2
    assert {edge["target"] for edge in calls(result)} == {node["id"] for node in locals_}


@pytest.mark.parametrize("kind", ["conditional", "duplicate"])
def test_req_qml022_ac06_conditional_and_duplicate_local_declarations_retain_uncertainty(tmp_path, kind):
    """Unknown alternatives remain separate source facts and cannot choose a convenient body."""
    path = tmp_path / "Data.cs"
    declaration = ("\n#if FEATURE\nvoid callback(){}\n#else\nvoid callback(){}\n#endif\n" if kind == "conditional"
                   else "void callback(){} void callback(){}")
    path.write_text("class Holder{void Use(){" + declaration + "callback();}}")
    result = extract_csharp(path)
    locals_ = local_functions(result)
    assert len(locals_) == len({node["id"] for node in locals_}) == 2
    assert not calls(result)


def test_req_qml022_ac06_nested_bodies_own_calls_and_typed_receivers(tmp_path):
    """Nested declarations cannot move their body calls onto the enclosing method."""
    path = tmp_path / "Data.cs"
    path.write_text("class Worker{public void Run(){}} class Holder{void Use(){"
                    "void Outer(){void Inner(Worker worker){worker.Run();} Inner(new Worker());} Outer();}}")
    result = extract([path], root=tmp_path, cache_root=tmp_path, parallel=False)
    locals_ = local_functions(result)
    assert {base64.b64decode(node["metadata"]["csharp_local_function"]["raw_name_b64"]).decode() for node in locals_} == {"Outer", "Inner"}
    labels = {node["id"]: node["label"].removeprefix(".") for node in result["nodes"]}
    pairs = {(labels[edge["source"]], labels[edge["target"]]) for edge in calls(result) if edge["target"] in labels}
    assert {("Use()", "Outer()"), ("Outer()", "Inner()"), ("Inner()", "Run()")} <= pairs
    assert ("Use()", "Run()") not in pairs and ("Outer()", "Run()") not in pairs
