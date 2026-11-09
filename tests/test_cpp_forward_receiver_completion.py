"""A field's lexical type can be completed by an explicitly included caller header."""
import importlib.util
import json

import pytest

from graphify.extract import extract

pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("tree_sitter_cpp") is None,
    reason="tree_sitter_cpp not installed",
)


def _extract(tmp_path, client, caller, worker="struct Worker { void Run(); };", extra=None):
    files = {"client.hpp": client, "worker.hpp": worker, "use.cpp": caller}
    files.update(extra or {})
    paths = []
    for name, text in files.items():
        path = tmp_path / name
        path.write_text(text, encoding="utf-8")
        paths.append(path)
    return paths, extract(paths, root=tmp_path, cache_root=tmp_path / "cache", parallel=False)


def _calls(result):
    nodes = {n["id"]: n for n in result["nodes"]}
    return {nodes[e["target"]]["source_file"]
            for e in result["edges"] if e["relation"] == "calls"
            and nodes[e["source"]]["label"] == "Tick()"
            and nodes[e["target"]]["label"] == ".Run()"}


@pytest.mark.parametrize("declaration,expression", [
    ("Worker* worker;", "c.worker->Run()"),
    ("Worker& worker;", "c.worker.Run()"),
    ("using Target = Worker*; Target worker;", "c.worker->Run()"),
    ("std::unique_ptr<Worker> worker;", "c.worker->Run()"),
])
def test_forward_field_type_is_completed_at_the_call_site(tmp_path, declaration, expression):
    _, result = _extract(tmp_path, f"#include <memory>\nstruct Worker; struct Client {{ {declaration} }};", f"""
#include "client.hpp"
#include "worker.hpp"
void Tick(Client& c) {{ {expression}; }}
""")
    assert _calls(result) == {"worker.hpp"}


def test_call_site_alias_does_not_change_a_field_alias(tmp_path):
    _, result = _extract(tmp_path, "struct Worker; using Target = Worker*; struct Client { Target worker; };", """
#include "client.hpp"
#include "worker.hpp"
struct Other { void Run(); };
void Tick(Client& c) { using Target = Other*; c.worker->Run(); }
""")
    assert _calls(result) == {"worker.hpp"}


@pytest.mark.parametrize("client,includes,extra", [
    ("struct Worker; struct Client { Worker* worker; };", '#include "client.hpp"', {}),
    ("struct Client { Worker* worker; };", '#include "client.hpp"\n#include "worker.hpp"', {}),
    ("struct Worker; struct Client { worker* worker; };", '#include "client.hpp"\n#include "worker.hpp"', {}),
    ("struct Worker; using Target = Missing*; struct Client { Target worker; };",
     '#include "client.hpp"\n#include "worker.hpp"', {}),
    ("struct Worker; struct Client { Worker* worker; };",
     '#include "client.hpp"\n#include "worker.hpp"\n#include "duplicate.hpp"',
     {"duplicate.hpp": "struct Worker { void Run(); };"}),
])
def test_completion_does_not_guess_unknown_or_ambiguous_types(tmp_path, client, includes, extra):
    _, result = _extract(tmp_path, client, includes + "\nvoid Tick(Client& c) { c.worker->Run(); }", extra=extra)
    assert _calls(result) == set()


def test_a_definition_in_an_unincluded_same_named_namespace_is_not_completion(tmp_path):
    _, result = _extract(tmp_path, "namespace app { struct Worker; struct Client { Worker* worker; }; }", """
#include "client.hpp"
#include "worker.hpp"
void Tick(app::Client& c) { c.worker->Run(); }
""", worker="namespace other { struct Worker { void Run(); }; }")
    assert _calls(result) == set()


def test_a_definition_included_after_the_call_is_not_completion(tmp_path):
    _, result = _extract(tmp_path, "struct Worker; struct Client { Worker* worker; };", """
#include "client.hpp"
void Tick(Client& c) { c.worker->Run(); }
#include "worker.hpp"
""")
    assert _calls(result) == set()


def test_a_forward_base_is_not_completed_after_the_derived_declaration(tmp_path):
    _, result = _extract(tmp_path, "struct Worker; struct Client : Worker {};", """
#include "client.hpp"
#include "worker.hpp"
void Tick(Client& c) { c.Run(); }
""")
    assert _calls(result) == set()


@pytest.mark.parametrize("before", [True, False])
def test_same_file_completion_respects_the_definition_position(tmp_path, before):
    definition = "struct Worker { void Run(); };"
    call = "void Tick(Client& c) { c.worker->Run(); }"
    source = "struct Worker; struct Client { Worker* worker; }; " + (
        definition + call if before else call + definition)
    _, result = _extract(tmp_path, "", source, worker="")
    assert _calls(result) == ({"use.cpp"} if before else set())


def test_same_file_duplicate_definitions_do_not_become_one_completion(tmp_path):
    _, result = _extract(tmp_path, "struct Worker; struct Client { Worker* worker; };", """
#include "client.hpp"
struct Worker { void Run() {} }; struct Worker { void Run() {} };
void Tick(Client& c) { c.worker->Run(); }
""", worker="")
    assert _calls(result) == set()


@pytest.mark.parametrize("scope", ["namespace other", "struct Scope", "void IncludeOnly()"])
def test_scoped_includes_do_not_complete_a_global_forward_type(tmp_path, scope):
    _, result = _extract(tmp_path, "struct Worker; struct Client { Worker* worker; };", f"""
#include "client.hpp"
{scope} {{
#include "worker.hpp"
}};
void Tick(Client& c) {{ c.worker->Run(); }}
""")
    assert _calls(result) == set()


def test_a_linkage_wrapper_does_not_change_an_includes_lexical_scope(tmp_path):
    _, result = _extract(tmp_path, "struct Worker; struct Client { Worker* worker; };", """
#include "client.hpp"
extern "C" {
#include "worker.hpp"
}
void Tick(Client& c) { c.worker->Run(); }
""")
    assert _calls(result) == {"worker.hpp"}


def test_a_namespace_injected_definition_does_not_complete_an_outer_type(tmp_path):
    _, result = _extract(tmp_path, "struct Worker; struct Client { Worker* worker; };", """
#include "client.hpp"
namespace other {
#include "worker.hpp"
void Tick(Client& c) { c.worker->Run(); }
}
""")
    assert _calls(result) == set()


@pytest.mark.parametrize("before", [True, False])
def test_base_alias_completion_stops_at_the_base_specifier(tmp_path, before):
    definition = "struct Worker { void Run(); };"
    derived = "struct Client : Parent {};"
    client = "struct Worker; using Parent = Worker; " + (
        definition + derived if before else derived + definition)
    _, result = _extract(tmp_path, client, """
#include "client.hpp"
void Tick(Client& c) { c.Run(); }
""", worker="")
    assert _calls(result) == ({"client.hpp"} if before else set())


def test_persisted_forward_field_facts_use_the_changed_callers_includes(tmp_path):
    paths, original = _extract(tmp_path, "struct Worker; struct Client { Worker* worker; };", """
#include "client.hpp"
#include "worker.hpp"
void Tick(Client& c) { c.worker->Run(); }
""")
    original = json.loads(json.dumps(original))
    caller = paths[2]
    caller.write_text(caller.read_text(encoding="utf-8") + "\n// edit\n", encoding="utf-8")
    fresh = extract([caller], root=tmp_path, cache_root=tmp_path / "cache", parallel=False,
                    resolution_context_nodes=[n for n in original["nodes"] if n.get("source_file") != "use.cpp"],
                    resolution_context_edges=[e for e in original["edges"] if e.get("source_file") != "use.cpp"])
    combined = {"nodes": original["nodes"] + fresh["nodes"], "edges": fresh["edges"]}
    assert _calls(combined) == {"worker.hpp"}
