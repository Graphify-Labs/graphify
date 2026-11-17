"""Template syntax preserves known member ownership without guessing receivers."""
import json

import pytest

from graphify.cache import cache_dir
from graphify.extract import extract


def _extract(tmp_path, files):
    paths = []
    for name, source in files.items():
        path = tmp_path / name
        path.write_text(source, encoding="utf-8")
        paths.append(path)
    return extract(paths, root=tmp_path, parallel=False, cache_root=tmp_path)


def _calls(result, caller):
    nodes = {n["id"]: n for n in result["nodes"]}
    caller_ids = {n["id"] for n in nodes.values() if n["label"] == caller}
    return [nodes[e["target"]] for e in result["edges"]
            if e["relation"] == "calls" and e["source"] in caller_ids]


def test_template_declarations_and_definitions_keep_their_class(tmp_path):
    result = _extract(tmp_path, {"worker.cpp": """
struct Worker {
    template<class T> void Tick();
    template<class T> T& Get();
    template<class T> void Inline() { Tick<T>(); }
};
template<class T> void Worker::Tick() {}
template<class T> T& Worker::Get() { static T value; return value; }
void Run(Worker& w) { w.Tick<int>(); }
"""})
    nodes = {n["id"]: n for n in result["nodes"]}
    owner = next(n["id"] for n in nodes.values() if n["label"] == "Worker")
    members = [nodes[e["target"]] for e in result["edges"]
               if e["relation"] == "method" and e["source"] == owner]
    assert {n["label"] for n in members} == {".Tick()", ".Get()", ".Inline()"}
    assert len({n["id"] for n in members}) == 3
    assert len([n for n in nodes.values() if "Tick" in n["label"]]) == 1
    assert [n["label"] for n in _calls(result, "Run()")] == [".Tick()"]
    assert [n["label"] for n in _calls(result, ".Inline()")] == [".Tick()"]
    assert not any(not n.get("source_file") for n in nodes.values())


@pytest.mark.parametrize("expression", [
    "w.Tick<int>()",
    "w.template Tick<int>()",
    "w.Tick<Pair<int, Pair<float, double>>>()",
    "p->Tick<int>()",
    "client.worker.Tick<int>()",
    "Worker::Tick<int>()",
])
def test_explicit_template_member_call_uses_the_known_owner(tmp_path, expression):
    result = _extract(tmp_path, {
        "worker.hpp": """
struct Worker { template<class T> static void Tick() {} };
struct Client { Worker worker; };
""",
        "use.cpp": '#include "worker.hpp"\n'
        f"void Run(Worker& w, Worker* p, Client& client) {{ {expression}; }}",
    })
    assert [n["label"] for n in _calls(result, "Run()")] == [".Tick()"]


@pytest.mark.parametrize("source", [
    "void Run() { unknown.Tick<int>(); }",
    "void Run(int& w) { w.Tick<int>(); }",
    "struct Empty {}; void Run(Empty& w) { w.Tick<int>(); }",
    "void Run() { auto w = GetWorker(); w.Tick<int>(); }",
])
def test_unknown_template_receiver_never_binds_by_member_name(tmp_path, source):
    result = _extract(tmp_path, {"use.cpp": """
struct Worker { template<class T> void Tick() {} };
template<class T> void Tick() {}
""" + source})
    assert _calls(result, "Run()") == []


def test_colliding_template_member_owners_remain_ambiguous(tmp_path):
    result = _extract(tmp_path, {
        "a.hpp": "struct Worker { template<class T> void Tick() {} };",
        "b.hpp": "struct Worker { template<class T> void Tick() {} };",
        "use.cpp": '#include "a.hpp"\n#include "b.hpp"\n'
        "void Run(Worker& w) { w.Tick<int>(); }",
    })
    assert _calls(result, "Run()") == []


def test_world_get_component_overload_family_is_owned_and_callable(tmp_path):
    result = _extract(tmp_path, {"world.hpp": """
struct World {
    template<typename T> T& GetComponent(int entity);
    template<typename T> const T& GetComponent(int entity) const;
};
template<typename T> T& World::GetComponent(int entity) { static T t; return t; }
template<typename T> const T& World::GetComponent(int entity) const { static T t; return t; }
struct Health {};
void Run(World& world) { world.GetComponent<Health>(1); }
"""})
    targets = _calls(result, "Run()")
    assert [n["label"] for n in targets] == [".GetComponent()"]
    assert len([n for n in result["nodes"] if "GetComponent" in n["label"]]) == 1


def test_generic_template_owner_does_not_attach_to_an_unrelated_class(tmp_path):
    result = _extract(tmp_path, {"use.cpp": """
struct Worker { template<class T> void Tick(); };
template<class T> void Other<T>::Tick() {}
void Run(Worker& w) { w.Tick<int>(); }
"""})
    targets = _calls(result, "Run()")
    assert [n["label"] for n in targets] == [".Tick()"]
    assert not any(n["label"] == "Other<T>::Tick()" for n in targets)


@pytest.mark.parametrize("primary_parameters, parameters, arguments", [
    ("class A", "class T", "T"),
    ("class A", "typename Value", "Value"),
    ("class A, class B", "class First, typename Second", "First, Second"),
])
def test_primary_template_definition_reuses_its_declared_member(
    tmp_path, primary_parameters, parameters, arguments,
):
    result = _extract(tmp_path, {"box.cpp": f"""
template<{primary_parameters}> struct Box {{
    void Run();
    void Next();
}};
template<{parameters}> void Box<{arguments}>::Run() {{ Next(); }}
"""})
    nodes = {n["id"]: n for n in result["nodes"]}
    owner = next(n["id"] for n in nodes.values() if n["label"] == "Box")
    run = [n for n in nodes.values() if "Run" in n["label"]]
    assert [n["label"] for n in run] == [".Run()"]
    assert any(e["source"] == owner and e["target"] == run[0]["id"]
               and e["relation"] == "method" for e in result["edges"])
    assert [n["label"] for n in _calls(result, ".Run()")] == [".Next()"]
    assert all(n.get("source_file") for n in run)


@pytest.mark.parametrize("declaration, definition", [
    ("template<class T> struct Box { void Run(); };", "template<> void Box<int>::Run() {}"),
    ("template<class T> struct Box { void Run(); };", "template<class T> void Box<T*>::Run() {}"),
    ("template<class T, class U> struct Box { void Run(); };",
     "template<class T, class U> void Box<U, T>::Run() {}"),
    ("template<class T> struct Box { void Run(); void Run(int); };",
     "template<class T> void Box<T>::Run() {}"),
    ("template<class T> struct Box { void _Run(); void Run(); };",
     "template<class T> void Box<T>::Run() {}"),
    ("template<class T> struct Box { void Run(); void _Run(); };",
     "template<class T> void Box<T>::Run() {}"),
    ("template<class T> struct Box { T Run(); };", "template<class T> T Box<T>::Run() {}"),
    ("template<class T> struct Box { void Run(); };", "template<class T> int Box<T>::Run() {}"),
    ("template<class T> struct Box { void Run() const; };", "template<class T> void Box<T>::Run() {}"),
    ("template<class T> struct Box { template<class U> void Run(); };",
     "template<class T> template<class U> void Box<T>::Run() {}"),
    ("struct Box { void Run(); };", "template<class T> void Box<T>::Run() {}"),
    ("template<class T> struct Box { void Run(); }; struct Outer { struct Box { void Run(); }; };",
     "template<class T> void Box<T>::Run() {}"),
    ("namespace Left { template<class T> struct Box { void Run(); }; }",
     "namespace Right { template<class T> void Box<T>::Run() {} }"),
    ("template<class T = int> struct Box { void Run(); };", "template<class T> void Box<T>::Run() {}"),
    ("template<class... T> struct Box { void Run(); };", "template<class T> void Box<T>::Run() {}"),
    ("template<class T> struct Box { void Run(); };",
     "template<class T> requires Ready<T> void Box<T>::Run() {}"),
])
def test_unproven_template_owner_keeps_its_separate_definition(tmp_path, declaration, definition):
    result = _extract(tmp_path, {"box.cpp": declaration + "\n" + definition})
    nodes = {n["id"]: n for n in result["nodes"]}
    definitions = {n["id"] for n in nodes.values() if "::Run()" in n["label"]}
    assert len(definitions) == 1
    assert not any(e["relation"] == "method" and e["target"] in definitions
                   for e in result["edges"])


def test_primary_template_owner_preserves_qualifiers_namespace_and_guards(tmp_path):
    result = _extract(tmp_path, {"box.cpp": """namespace ns {
template<class T> struct Box { bool Run() const & noexcept; void Next(); };
template<class T> bool Box<T>::Run() const & noexcept {
    int values[] = {
#if FEATURE
Next(),
#else
0,
#endif
    };
    return true;
}
}
"""})
    nodes = {n["id"]: n for n in result["nodes"]}
    run = next(n for n in nodes.values() if n["label"] == ".Run()")
    assert run["_cpp_qualified"] == "ns::Box::Run"
    assert len([n for n in nodes.values() if "Run" in n["label"]]) == 1
    calls = [e for e in result["edges"] if e["relation"] == "calls" and e["source"] == run["id"]]
    assert [nodes[e["target"]]["label"] for e in calls] == [".Next()"]
    assert calls[0]["metadata"]["cpp_conditions"] == [{"group_line": 5, "branch": 0}]
    assert calls[0]["source_file"] == "box.cpp"
    assert calls[0]["source_location"] == "L6"


def test_primary_template_owner_records_are_order_and_cache_stable(tmp_path):
    files = {
        "box.cpp": "template<class T> struct Box { void Run(); void Next(); };\n"
        "template<class T> void Box<T>::Run() { Next(); }",
        "other.cpp": "void Run() {}",
    }
    cold = _extract(tmp_path, files)
    warm = _extract(tmp_path, dict(reversed(list(files.items()))))
    entries = list(cache_dir(tmp_path).glob("*.json"))
    assert entries
    for entry in entries:
        entry.unlink()
    reverse_cold = _extract(tmp_path, dict(reversed(list(files.items()))))

    def records(result):
        return {key: sorted(json.dumps(record, sort_keys=True) for record in result[key])
                for key in ("nodes", "edges")}

    assert records(cold) == records(warm) == records(reverse_cold)


@pytest.mark.parametrize("source, caller", [
    ("template<class T> void Run(T& x) { x.template Tick<int>(); }", "Run()"),
    ("template<class T> void Run(T* x) { x->template Tick<int>(); }", "Run()"),
    ("template<class T> void Run(std::unique_ptr<T>& x) { x->template Tick<int>(); }", "Run()"),
    ("template<class T> void Run(std::shared_ptr<T>& x) { x->template Tick<int>(); }", "Run()"),
    ("template<class T = int> void Run(T& x) { x.template Tick<int>(); }", "Run()"),
    ("template<class T> void Run() { T::template Tick<int>(); }", "Run()"),
    ("template<class T> struct Holder { T value; "
     "void Run() { value.template Tick<int>(); } };", ".Run()"),
])
def test_dependent_receiver_does_not_bind_to_a_global_template_parameter_name(tmp_path, source, caller):
    result = _extract(tmp_path, {"use.cpp":
        "struct T { template<class U> void Tick() {} };\n" + source})
    assert _calls(result, caller) == []


@pytest.mark.parametrize("parameters, dependent_type", [
    ("class A", "typename A::Type"),
    ("template<class> class A", "typename A<int>::Type"),
    ("template<class> class A = Default", "typename A<int>::Type"),
])
@pytest.mark.parametrize("pointer", [False, True])
def test_dependent_nested_parameter_never_uses_a_same_named_concrete_type(
    tmp_path, parameters, dependent_type, pointer,
):
    result = _extract(tmp_path, {"use.cpp":
        "namespace A { struct Type { void Work(); }; }\n"
        f"template<{parameters}> void Run({dependent_type}{'*' if pointer else '&'} x) "
        f"{{ x{'->' if pointer else '.'}Work(); }}"})
    assert _calls(result, "Run()") == []
    assert not any(n.get("metadata", {}).get("unresolved_calls") for n in result["nodes"])


@pytest.mark.parametrize("parameters, dependent_type", [
    ("class A", "typename A::Type"),
    ("template<class> class A", "typename A<int>::Type"),
])
def test_dependent_nested_field_keeps_its_unknown_type(tmp_path, parameters, dependent_type):
    result = _extract(tmp_path, {"use.cpp":
        "namespace A { struct Type { void Work(); }; }\n"
        f"template<{parameters}> struct Holder {{ {dependent_type} value; "
        "void Run() { value.Work(); } };"})
    assert _calls(result, ".Run()") == []


def test_template_template_inner_parameter_does_not_shadow_a_corpus_type(tmp_path):
    result = _extract(tmp_path, {"use.cpp": """
struct Inner { void Work(); };
template<template<class Inner> class A> void Run(Inner& x) { x.Work(); }
"""})
    assert [n["label"] for n in _calls(result, "Run()")] == [".Work()"]


def test_template_template_parameter_stays_a_local_binding(tmp_path):
    result = _extract(tmp_path, {"use.cpp":
        "template<template<class> class A> struct Holder { A<int> value; };"})
    assert not any(n["label"] == "A" for n in result["nodes"])


@pytest.mark.parametrize("declaration, expression", [
    ("typename A<int>::Type x, y;", "x.Work(); y.Work();"),
    ("t x;", "x.Work();"),
    ("Container<t> x;", "x.Work();"),
    ("std::unique_ptr<t> x;", "x->Work();"),
])
def test_dependent_local_shapes_never_use_the_in_file_member_fallback(tmp_path, declaration, expression):
    result = _extract(tmp_path, {"use.cpp":
        "namespace A { struct Type { void Work(); }; }\n"
        f"template<template<class> class A, class t> void Run() {{ {declaration} {expression} }}"})
    assert _calls(result, "Run()") == []


def test_dependent_binding_does_not_suppress_another_functions_auto_receiver(tmp_path):
    result = _extract(tmp_path, {"use.cpp": """
struct Known { void Paint(); }; Known Make();
template<class t> void Other(t& x) { x.Paint(); }
void Run() { auto x = Make(); x.Paint(); }
"""})
    assert _calls(result, "Other()") == []
    assert [n["label"] for n in _calls(result, "Run()")] == [".Paint()"]


def test_auto_local_shadows_an_unknown_dependent_field(tmp_path):
    result = _extract(tmp_path, {"use.cpp": """
struct Known { void Paint(); }; Known Make();
template<class t> struct Holder {
    t value;
    void Run() { auto value = Make(); value.Paint(); }
};
"""})
    assert [n["label"] for n in _calls(result, ".Run()")] == [".Paint()"]


def test_qualified_concrete_template_argument_stays_known_with_a_shadowing_parameter(tmp_path):
    result = _extract(tmp_path, {
        "global.hpp": "struct T { template<class U> void Tick() {} };",
        "types.hpp": "namespace ns { struct T { template<class U> void Tick() {} }; }",
        "use.cpp": '#include "global.hpp"\n#include "types.hpp"\n'
        "template<class T> void Run(std::unique_ptr<ns::T>& x) { x->template Tick<int>(); }",
    })
    targets = _calls(result, "Run()")
    assert [n["label"] for n in targets] == [".Tick()"]
    nodes = {n["id"]: n for n in result["nodes"]}
    owners = [nodes[e["source"]] for e in result["edges"]
              if e["relation"] == "method" and e["target"] == targets[0]["id"]]
    assert [n["_cpp_qualified"] for n in owners] == ["ns::T"]


def test_local_callable_shadows_a_free_template_function(tmp_path):
    result = _extract(tmp_path, {"use.cpp": """
template<class T> void Tick() {}
void Run() { auto Tick = [] {}; Tick<int>(); }
"""})
    assert _calls(result, "Run()") == []


def test_incremental_template_call_uses_serialized_header_context(tmp_path):
    result = _extract(tmp_path, {
        "worker.hpp": "struct Worker { template<class T> void Tick() {} };",
        "use.cpp": '#include "worker.hpp"\nvoid Run(Worker& w) { w.Tick<int>(); }',
    })
    result = json.loads(json.dumps(result))
    caller = tmp_path / "use.cpp"
    caller.write_text(caller.read_text(encoding="utf-8") + "\n// edit\n", encoding="utf-8")
    updated = extract(
        [caller], root=tmp_path, cache_root=tmp_path, parallel=False,
        resolution_context_nodes=[n for n in result["nodes"] if n.get("source_file") != "use.cpp"],
        resolution_context_edges=[e for e in result["edges"] if e.get("source_file") != "use.cpp"],
    )
    nodes = {n["id"]: n for n in [*result["nodes"], *updated["nodes"]]}
    targets = [nodes[e["target"]]["label"] for e in updated["edges"]
               if e["relation"] == "calls"]
    assert targets == [".Tick()"]
    assert not any(n.get("source_file") == "worker.hpp" for n in updated["nodes"])
