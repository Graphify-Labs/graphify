"""Proven zero-argument member pairs share an identity without overload guessing."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from graphify.build import build_from_json
from graphify.export import to_json
from graphify.extract import extract


def _extract(tmp_path, files, *, reverse=False):
    paths = []
    for name, source in files.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source, encoding="utf-8")
        paths.append(path)
    return extract(paths[::-1] if reverse else paths, root=tmp_path,
                   cache_root=tmp_path, parallel=False)


def _members(result):
    return [n for n in result["nodes"]
            if n.get("label") == ".Run()" or n.get("label", "").endswith("::Run()")]


@pytest.mark.parametrize("reverse", [False, True])
def test_zero_argument_member_preserves_both_sites_and_body_calls(tmp_path, reverse):
    files = {
        "api.hpp": "namespace api { class Service { public: int Run() const & noexcept; }; }",
        "implementation.cpp": '#include "api.hpp"\nint Assist() { return 1; }\n'
                              'int api::Service::Run() const & noexcept { return Assist(); }',
        "use.cpp": '#include "api.hpp"\nint Use(api::Service& s) { return s.Run(); }',
    }
    result = _extract(tmp_path, files, reverse=reverse)
    members = _members(result)
    assert len(members) == 1
    member = members[0]
    assert member["source_file"] == "api.hpp"
    assert member["source_location"] == "L1"
    assert member["definition_file"] == "implementation.cpp"
    assert member["definition_location"] == "L3"
    assert member["label"] == ".Run()"
    labels = {n["id"]: n["label"] for n in result["nodes"]}
    calls = {(labels[e["source"]], labels[e["target"]]) for e in result["edges"]
             if e["relation"] == "calls"}
    assert ("Use()", ".Run()") in calls
    assert (".Run()", "Assist()") in calls
    again = extract([tmp_path / name for name in reversed(files)], root=tmp_path,
                    cache_root=tmp_path, parallel=False)
    assert sorted(result["nodes"], key=lambda n: n["id"]) == sorted(again["nodes"], key=lambda n: n["id"])
    graph_path = tmp_path / "graph.json"
    to_json(build_from_json(result, root=tmp_path), {}, str(graph_path))
    saved = json.loads(graph_path.read_text(encoding="utf-8"))
    assert _members(saved)[0]["definition_file"] == "implementation.cpp"
    assert _members(saved)[0]["definition_location"] == "L3"


@pytest.mark.parametrize("returns", ["void", "int", "const int*", "int&"])
def test_literal_return_shapes_and_conventional_guards_are_supported(tmp_path, returns):
    result = _extract(tmp_path, {
        "api.hpp": f"#ifndef API_HPP\n#define API_HPP\nnamespace api {{ class Service {{ public: {returns} Run() noexcept(false); }}; }}\n#endif",
        "implementation.cpp": f'#include "api.hpp"\n{returns} api::Service::Run() noexcept(false) {{ throw 1; }}',
    })
    assert len(_members(result)) == 1
    assert _members(result)[0]["definition_file"] == "implementation.cpp"


@pytest.mark.parametrize("declaration,definition", [
    ("int Run();", "long api::Service::Run() {}"),
    ("int Run() const;", "int api::Service::Run() {}"),
    ("int Run() &;", "int api::Service::Run() && {}"),
    ("int Run() noexcept;", "int api::Service::Run() noexcept(false) {}"),
    ("int* Run();", "int& api::Service::Run() {}"),
    ("int Run(); int Run(int);", "int api::Service::Run() {}"),
    ("int Run(int);", "int api::Service::Run(int n) {}"),
    ("template<class T> int Run();", "template<class T> int api::Service::Run() {}"),
    ("int Run() = 0;", "int api::Service::Run() {}"),
    ("int Run(); int _Run();", "int api::Service::Run() {}"),
    ("#ifdef FEATURE\nint Run();\n#endif", "int api::Service::Run() {}"),
])
def test_signature_family_or_condition_uncertainty_does_not_merge(tmp_path, declaration, definition):
    result = _extract(tmp_path, {
        "api.hpp": f"namespace api {{ class Service {{ public:\n{declaration}\n}}; }}",
        "implementation.cpp": '#include "api.hpp"\n' + definition,
    })
    assert not any(n.get("definition_file") for n in _members(result))


@pytest.mark.parametrize("files", [
    {"api.hpp": "namespace api { class Service { public: void Run(); }; }",
     "implementation.cpp": "void api::Service::Run() {}"},
    {"api.hpp": "namespace api { class Service { public: void Run(); }; }",
     "implementation.cpp": '#ifdef FEATURE\n#include "api.hpp"\n#endif\nvoid api::Service::Run() {}'},
    {"api.hpp": "namespace api { class Service { public: void Run(); }; }",
     "a.cpp": '#include "api.hpp"\nvoid api::Service::Run() {}',
     "b.cpp": '#include "api.hpp"\nvoid api::Service::Run() {}'},
    {"api.hpp": "namespace api { class Service { public: void Run(); }; }",
     "other.hpp": "namespace api { class Service { public: void Run(); }; }",
     "implementation.cpp": '#include "api.hpp"\n#include "other.hpp"\nvoid api::Service::Run() {}'},
])
def test_unproven_includes_multiple_definitions_and_owners_stay_separate(tmp_path, files):
    result = _extract(tmp_path, files)
    assert len(_members(result)) > 1
    assert not any(n.get("definition_file") for n in _members(result))


def test_sibling_stem_does_not_bypass_qualifier_uncertainty(tmp_path):
    result = _extract(tmp_path, {
        "service.hpp": "class Service { public: void Run() const; };",
        "service.cpp": '#include "service.hpp"\nvoid Service::Run() {}',
    })
    members = _members(result)
    assert len({n["id"] for n in members}) == 2
    assert {n["source_file"] for n in members} == {"service.hpp", "service.cpp"}
    assert not any(n.get("definition_file") for n in members)


def test_same_file_pair_keeps_both_exact_syntax_records(tmp_path):
    result = _extract(tmp_path, {"api.cpp": "class Service { public: int Run(); };\nint Service::Run() { return 1; }"})
    members = _members(result)
    assert len(members) == 1
    records = members[0]["_cpp_member_records"]
    assert [(r["kind"], r["source_location"]) for r in records] == [
        ("declaration", "L1"), ("definition", "L2"),
    ]


@pytest.mark.parametrize("definition", [
    "long Service::Run() { return 1; }",
    "int Service::Run() const { return 1; }",
    "int Service::Run() noexcept { return 1; }",
])
def test_same_file_mismatched_signatures_keep_both_uncertain_records(tmp_path, definition):
    result = _extract(tmp_path, {"api.cpp": "class Service { public: int Run(); };\n" + definition})
    members = _members(result)
    assert len(members) == 1
    records = members[0]["_cpp_member_records"]
    assert [(r["kind"], r["source_location"]) for r in records] == [
        ("declaration", "L1"), ("definition", "L2"),
    ]
    assert records[0]["signature"] != records[1]["signature"]
    assert "definition_file" not in members[0]


def test_reconciled_body_binds_its_own_member_before_a_same_named_free_function(tmp_path):
    result = _extract(tmp_path, {
        "api.hpp": "class Service { public: void Run(); void Say(); };",
        "implementation.cpp": '#include "api.hpp"\nvoid Service::Run() { Say(); }\nvoid Service::Say() {}',
        "unrelated.cpp": "void Say() {}",
    })
    nodes = {n["id"]: n for n in result["nodes"]}
    run = _members(result)[0]
    calls = [nodes[e["target"]] for e in result["edges"]
             if e["relation"] == "calls" and e["source"] == run["id"]]
    assert [n["label"] for n in calls] == [".Say()"]
    assert calls[0]["source_file"] == "api.hpp"


@pytest.mark.parametrize("update", ["cli", "watch"])
@pytest.mark.parametrize("change", ["body", "qualifier", "delete", "new-definition", "second-definition"])
def test_incremental_updates_recheck_member_proofs_and_keep_incoming_calls(tmp_path, update, change):
    project = tmp_path / "project"
    files = {
        "api.hpp": "namespace api { class Service { public: int Run(); }; }",
        "use.cpp": '#include "api.hpp"\nint Use(api::Service& s) { return s.Run(); }',
    }
    if change != "new-definition":
        files["implementation.cpp"] = '#include "api.hpp"\nint api::Service::Run() { return 1; }'
    _extract(project, files)
    env = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[1]))
    command = [sys.executable, "-m", "graphify", "extract", str(project), "--code-only", "--no-cluster"]
    initial = subprocess.run(command, env=env, cwd=tmp_path, text=True, capture_output=True)
    assert initial.returncode == 0, initial.stdout + initial.stderr
    changed = project / ("api.hpp" if change == "qualifier" else
                         "other.cpp" if change == "second-definition" else "implementation.cpp")
    if change == "delete":
        changed.unlink()
    elif change == "qualifier":
        changed.write_text("namespace api { class Service { public: int Run() const; }; }", encoding="utf-8")
    else:
        changed.write_text('#include "api.hpp"\nint api::Service::Run() { return 2; }', encoding="utf-8")
    if update == "cli":
        after = subprocess.run(command, env=env, cwd=tmp_path, text=True, capture_output=True)
        assert after.returncode == 0, after.stdout + after.stderr
    else:
        from graphify.watch import _rebuild_code
        assert _rebuild_code(project, changed_paths=[changed], no_cluster=True, acquire_lock=False)
    saved = json.loads((project / "graphify-out/graph.json").read_text(encoding="utf-8"))
    members = _members(saved)
    assert len(members) == (2 if change == "qualifier" else 3 if change == "second-definition" else 1)
    merged = change in {"body", "new-definition"}
    assert any(n.get("definition_file") for n in members) == merged
    if merged:
        assert any(e["relation"] == "calls" and e["source"] == "use_use" and e["target"] == members[0]["id"]
                   for e in saved.get("links", saved.get("edges", [])))
