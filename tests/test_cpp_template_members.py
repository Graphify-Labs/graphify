"""Template syntax preserves known member ownership without guessing receivers."""
import json

import pytest

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
