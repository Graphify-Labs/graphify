"""Class field storage is source data, never a guessed direct callable target."""
from __future__ import annotations

import pytest

from graphify.extract import extract, extract_cpp, extract_csharp, _resolve_cpp_member_calls
from tests.test_qt_final_incremental_parity import clean, normalized, run


@pytest.mark.parametrize("language,invocation,field", [
    ("cpp", "Base::callback()", "void (*callback)();"),
    ("csharp", "base.callback()", "System.Action callback;"),
    ("csharp", "Base.callback()", "static System.Action callback;"),
])
def test_req_qml022_ac06_base_storage_calls_remain_data(tmp_path, language, invocation, field):
    """Explicit base lookup cannot turn a field into a concrete function or sibling method."""
    if language == "cpp":
        source = ("class Base{protected:" + field + "}; class Derived:public Base{void Use(){"
                  + invocation + ";}}; class Other{public:void callback(){}};")
        path, producer = tmp_path / "api.cpp", extract_cpp
    else:
        source = ("class Base{protected " + field + "} class Derived:Base{void Use(){"
                  + invocation + ";}} class Other{void callback(){}}")
        path, producer = tmp_path / "Data.cs", extract_csharp
    path.write_text(source)
    for result in (producer(path), extract([path], root=tmp_path, cache_root=tmp_path, parallel=False)):
        by_id = {node["id"]: node for node in result["nodes"]}
        callers = {node["id"] for node in result["nodes"] if node["label"].removeprefix(".") == "Use()"}
        assert not any(edge["source"] in callers and edge["relation"] in {"calls", "indirect_call"}
                       and "callback" in by_id.get(edge["target"], {}).get("label", "") for edge in result["edges"])


@pytest.mark.parametrize("corruption", ["missing", "method_kind"])
def test_req_qml022_ac06_member_fallback_needs_callable_role_after_storage_metadata_loss(tmp_path, corruption):
    """An explicit non-callable source role remains a rejection even if supplemental metadata is damaged."""
    path = tmp_path / "api.cpp"
    path.write_text("class Base{public:static void (*callback)();}; void Use(){Base::callback();}")
    result = extract_cpp(path)
    field = next(node for node in result["nodes"] if node["label"] == "callback")
    assert not field.get("_callable") and not field.get("_callable_class")
    if corruption == "missing":
        field["metadata"].pop("cpp_declarator")
    else:
        field["metadata"]["cpp_declarator"]["kind"] = "method"
    _resolve_cpp_member_calls([result], result["nodes"], result["edges"])
    assert not any(edge["relation"] == "calls" and edge["target"] == field["id"] for edge in result["edges"])


@pytest.mark.parametrize("language", ["cpp", "csharp"])
@pytest.mark.parametrize("receiver", ["bare", "self"])
@pytest.mark.parametrize("sibling", [False, True])
def test_req_qml022_ac06_field_invocation_cannot_call_storage_or_sibling_method(tmp_path, language, receiver, sibling):
    """Retaining a callback field must not add concrete call authority through a global label map."""
    if language == "cpp":
        invocation = "callback(1)" if receiver == "bare" else "this->callback(1)"
        source = "class Holder {public: void (*callback)(int); void Use(){" + invocation + ";}};"
        other = "class Other {public: void callback(int value) {}};"
        path, producer = tmp_path / "data.hpp", extract_cpp
    else:
        invocation = "callback(1)" if receiver == "bare" else "this.callback(1)"
        source = "class Holder {public System.Action<int> callback; void Use(){" + invocation + ";}}"
        other = "class Other {public void callback(int value) {}}"
        path, producer = tmp_path / "Data.cs", extract_csharp
    path.write_text(source + (other if sibling else ""), encoding="utf-8")
    result = producer(path)
    caller = next(node["id"] for node in result["nodes"] if node["label"] == ".Use()")
    assert any(node["label"] == "callback" for node in result["nodes"])
    assert not any(edge["source"] == caller and edge["relation"] == "calls" for edge in result["edges"])
    assert not [call for call in result.get("raw_calls", []) if call["caller_nid"] == caller and call["callee"] == "callback"]


@pytest.mark.parametrize("language", ["cpp", "csharp"])
def test_req_qml022_ac06_other_types_field_does_not_hide_actual_own_method(tmp_path, language):
    """Field lexical shadowing stays with its source owner; another type's field has no authority here."""
    if language == "cpp":
        source = "class Holder {public: void callback(int value){} void Use(){callback(1);}}; class Other {public: void (*callback)(int);};"
        path, producer = tmp_path / "data.hpp", extract_cpp
    else:
        source = "class Holder {void callback(int value){} void Use(){callback(1);}} class Other {System.Action<int> callback;}"
        path, producer = tmp_path / "Data.cs", extract_csharp
    path.write_text(source, encoding="utf-8")
    result = producer(path)
    caller = next(node["id"] for node in result["nodes"] if node["label"] == ".Use()")
    target = next(node["id"] for node in result["nodes"] if node["label"] == ".callback()")
    assert any(edge["source"] == caller and edge["target"] == target and edge["relation"] == "calls" for edge in result["edges"])


@pytest.mark.parametrize("property_storage", [False, True])
def test_req_qml022_ac06_escaped_delegate_storage_and_parameters_stay_data(tmp_path, property_storage):
    """C# escaping and a runtime parameter cannot lend another class's callback method."""
    storage = "public System.Action<int> @callback" + (" {get;set;}" if property_storage else ";")
    path = tmp_path / "Data.cs"
    path.write_text("class Holder {" + storage + " void Use(System.Action<int> callback){callback(1);}}"
                    "class Other {void callback(int value){}}", encoding="utf-8")
    result = extract_csharp(path)
    caller = next(node["id"] for node in result["nodes"] if node["label"] == ".Use()")
    assert not any(edge["source"] == caller and edge["relation"] == "calls" for edge in result["edges"])
    assert not [call for call in result.get("raw_calls", []) if call["caller_nid"] == caller]


@pytest.mark.parametrize("language", ["cpp", "csharp"])
@pytest.mark.parametrize("nearer_method", [False, True])
def test_req_qml022_ac06_inherited_storage_and_nearer_methods_keep_lexical_roles(tmp_path, language, nearer_method):
    """An inherited callback blocks guessing, while a nearer actual method legitimately hides it."""
    if language == "cpp":
        source = "class Base {public: void (*callback)(int);}; class Holder:public Base {public: "
        method = "void callback(int value){} "
        other = "class Other {public: void callback(int value){}};"
        end, path, producer = "};", tmp_path / "data.hpp", extract_cpp
    else:
        source = "class Base {public System.Action<int> callback;} class Holder:Base {"
        method = "new void callback(int value){} "
        other = "class Other {public void callback(int value){}}"
        end, path, producer = "}", tmp_path / "Data.cs", extract_csharp
    path.write_text(source + (method if nearer_method else "") + "void Use(){callback(1);}" + end + other, encoding="utf-8")
    result = producer(path)
    caller = next(node["id"] for node in result["nodes"] if node["label"] == ".Use()")
    edges = [edge for edge in result["edges"] if edge["source"] == caller and edge["relation"] == "calls"]
    assert len(edges) == int(nearer_method)
    if nearer_method:
        parent = next(edge["source"] for edge in result["edges"] if edge["target"] == caller and edge["relation"] == "method")
        assert any(edge["source"] == parent and edge["target"] == edges[0]["target"] and edge["relation"] == "method" for edge in result["edges"])


@pytest.mark.parametrize("operation", ["manual", "watch"])
def test_req_qml022_ac06_cached_partial_class_field_blocks_changed_caller_fallback(tmp_path, monkeypatch, operation):
    """Actual unchanged field edges must govern a changed partial-class caller through persistence."""
    (tmp_path / "Data.cs").write_text("namespace App {partial class Holder {public System.Action<int> callback;}}", encoding="utf-8")
    path = tmp_path / "Use.cs"
    source = "namespace App {partial class Holder {void Use(){callback(1);}}}"
    path.write_text(source, encoding="utf-8")
    (tmp_path / "Other.cs").write_text("class Other {void callback(int value){}}", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GRAPHIFY_NO_TIPS", "1")
    initial = run(tmp_path, monkeypatch, operation)
    for graph in (initial,):
        caller = next(identity for identity, data in graph.nodes(data=True) if data["label"].endswith(".Use()"))
        assert not any(data.get("relation") == "calls" for _, _, data in graph.edges(caller, data=True))
    path.write_text(source.replace("callback(1);", "callback(1); callback(2);"), encoding="utf-8")
    updated = run(tmp_path, monkeypatch, operation, [path])
    caller = next(identity for identity, data in updated.nodes(data=True) if data["label"].endswith(".Use()"))
    assert not any(data.get("relation") == "calls" for _, _, data in updated.edges(caller, data=True))
    assert normalized(updated) == normalized(clean(tmp_path, tmp_path / ".cold"))


@pytest.mark.parametrize("mode", ["unconditional", "parameter", "local"])
def test_req_qml022_ac06_known_receiver_fields_and_lexical_bindings_remain_resolvable(tmp_path, mode):
    """Unavailable conditional storage cannot poison an actual typed local/parameter receiver."""
    known = "class First {public void Run(){}} class Second {public void Run(){}}\n"
    if mode == "unconditional":
        field, method, target = "First worker;", "void Use(){worker.Run();}", "First"
    else:
        field = "\n#if FLAG\nFirst worker;\n#else\nSecond worker;\n#endif\n"
        method = ("void Use(Second worker){worker.Run();}" if mode == "parameter" else
                  "void Use(){Second worker=new Second();worker.Run();}")
        target = "Second"
    path = tmp_path / "Receivers.cs"
    path.write_text(known + "class Holder {" + field + method + "}", encoding="utf-8")
    result = extract([path], root=tmp_path, cache_root=tmp_path, parallel=False)
    caller = next(node["id"] for node in result["nodes"] if node["label"] == ".Use()")
    owner = next(node["id"] for node in result["nodes"] if node["label"] == target)
    methods = {edge["target"] for edge in result["edges"] if edge["source"] == owner and edge["relation"] == "method"}
    assert any(edge["source"] == caller and edge["target"] in methods and edge["relation"] == "calls" for edge in result["edges"])
