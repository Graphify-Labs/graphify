"""A reachable plain C++ forward denotes its unique class definition."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from graphify.build import build_from_json, build_merge
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


def _classes(result, name="Service"):
    return [n for n in result["nodes"]
            if n.get("_callable_class") and n.get("label") == name]


@pytest.mark.parametrize("reverse", [False, True])
def test_forward_and_reachable_definition_have_one_identity_and_all_sites(tmp_path, reverse):
    files = {
        "forward.hpp": "namespace api { class Service; }\n",
        "bridge.hpp": '#include "forward.hpp"\n',
        "service.hpp": '#include "bridge.hpp"\n'
                       'namespace api { class Service { public: void Run() {} }; }\n',
        "use.cpp": '#include "service.hpp"\nvoid Use(api::Service& s) { s.Run(); }\n',
    }
    result = _extract(tmp_path, files, reverse=reverse)
    classes = _classes(result)
    assert len(classes) == 1
    owner = classes[0]
    assert owner["source_file"] == "service.hpp"
    assert owner["_cpp_qualified"] == "api::Service"
    assert owner["metadata"]["cpp_declaration_sites"] == [
        {"source_file": "forward.hpp", "source_location": "L1"},
    ]
    assert owner["_cpp_reconcile_files"] == ["bridge.hpp", "forward.hpp", "service.hpp"]
    labels = {n["id"]: n["label"] for n in result["nodes"]}
    assert [(labels[e["source"]], labels[e["target"]]) for e in result["edges"]
            if e["relation"] == "calls"] == [("Use()", ".Run()")]
    again = extract([tmp_path / name for name in reversed(files)], root=tmp_path,
                    cache_root=tmp_path, parallel=False)
    assert sorted(result["nodes"], key=lambda n: n["id"]) == sorted(again["nodes"], key=lambda n: n["id"])
    graph_path = tmp_path / "graph.json"
    to_json(build_from_json(result, root=tmp_path), {}, str(graph_path))
    persisted = json.loads(graph_path.read_text(encoding="utf-8"))
    saved = next(n for n in persisted["nodes"] if n["id"] == owner["id"])
    assert saved["metadata"]["cpp_declaration_sites"] == owner["metadata"]["cpp_declaration_sites"]


@pytest.mark.parametrize("files,expected", [
    ({"forward.hpp": "class Service;", "service.hpp": "class Service {};"}, 2),
    ({"forward.hpp": "namespace other { class Service; }",
      "service.hpp": '#include "forward.hpp"\nnamespace api { class Service {}; }'}, 2),
    ({"forward.hpp": "class Service;",
      "a.hpp": '#include "forward.hpp"\nclass Service {};',
      "b.hpp": '#include "forward.hpp"\nclass Service {};'}, 3),
    ({"forward.hpp": "namespace { class Service; }",
      "service.hpp": '#include "forward.hpp"\nnamespace { class Service {}; }'}, 2),
    ({"forward.hpp": "template<class T> class Service;",
      "service.hpp": '#include "forward.hpp"\ntemplate<class T> class Service {};'}, 2),
    ({"forward.hpp": "#ifdef FEATURE\nclass Service;\n#endif",
      "service.hpp": '#include "forward.hpp"\nclass Service {};'}, 2),
    ({"forward.hpp": "class Service;",
      "service.hpp": '#ifdef FEATURE\n#include "forward.hpp"\n#endif\nclass Service {};'}, 2),
    ({"service.hpp": "class Service {};",
      "service.cpp": '#include "service.hpp"\nclass Service {};'}, 2),
    ({"service.hpp": "namespace api { class Service; }",
      "service.cpp": '#include "service.hpp"\nnamespace other { class Service {}; }'}, 2),
])
def test_unproven_or_ambiguous_classes_stay_separate(tmp_path, files, expected):
    assert len(_classes(_extract(tmp_path, files))) == expected


def test_sibling_stems_still_require_include_proof(tmp_path):
    result = _extract(tmp_path, {
        "service.hpp": "class Service;",
        "service.cpp": '#include "service.hpp"\nclass Service {};',
    })
    assert len(_classes(result)) == 1
    assert _classes(result)[0]["metadata"]["cpp_declaration_sites"] == [
        {"source_file": "service.hpp", "source_location": "L1"},
    ]


def test_conventional_header_guards_allow_the_same_include_proof(tmp_path):
    result = _extract(tmp_path, {
        "forward.hpp": "// guard comment\n#ifndef FORWARD_HPP\n#define FORWARD_HPP\nclass Service;\n#endif\n",
        "service.hpp": '#ifndef SERVICE_HPP\n#define SERVICE_HPP\n#include "forward.hpp"\nclass Service {};\n#endif\n',
    })
    assert len(_classes(result)) == 1
    assert _classes(result)[0]["metadata"]["cpp_declaration_sites"] == [
        {"source_file": "forward.hpp", "source_location": "L4"},
    ]


@pytest.mark.parametrize("forward", [
    "#ifndef FEATURE\nclass Service;\n#endif",
    "#ifndef FEATURE\n#define OTHER\nclass Service;\n#endif",
    "#ifndef FEATURE\n#define FEATURE\nclass Service;\n#else\nclass Other;\n#endif",
    "#ifndef FEATURE\n#define FEATURE\n#ifdef NESTED\nclass Service;\n#endif\n#endif",
    "#ifndef FEATURE\n#define FEATURE\nclass Service;\n#endif\nvoid Outside();",
    "#ifndef FEATURE\n#define FEATURE\n# undef FEATURE\nclass Service;\n#endif",
])
def test_other_conditions_do_not_masquerade_as_header_guards(tmp_path, forward):
    result = _extract(tmp_path, {
        "forward.hpp": forward,
        "service.hpp": '#include "forward.hpp"\nclass Service {};',
    })
    assert len(_classes(result)) == 2


def test_changed_forward_rebuilds_only_its_group_and_preserves_incoming_edges(tmp_path):
    result = _extract(tmp_path, {
        "include/forward.hpp": "class Service;",
        "include/service.hpp": '#include "forward.hpp"\nclass Service { public: void Run() {} };',
        "use.cpp": '#include "include/service.hpp"\nvoid Use(Service& s) { s.Run(); }',
    })
    graph_path = tmp_path / "graph.json"
    to_json(build_from_json(result, root=tmp_path), {}, str(graph_path))
    saved = json.loads(graph_path.read_text(encoding="utf-8"))
    caller = next(n for n in saved["nodes"] if n["label"] == "Use()")
    method = next(n for n in saved["nodes"] if n["label"] == ".Run()")
    owner = next(n for n in saved["nodes"] if n.get("_callable_class") and n["label"] == "Service")
    path = tmp_path / "include/forward.hpp"
    path.write_text("class Other;", encoding="utf-8")
    updated = extract(
        [path], root=tmp_path, cache_root=tmp_path, parallel=False,
        resolution_context_nodes=[n for n in saved["nodes"] if n.get("source_file") != "include/forward.hpp"],
        resolution_context_edges=[e for e in saved["links"] if e.get("source_file") != "include/forward.hpp"],
    )
    assert {n["source_file"] for n in updated["nodes"]} == {"include/forward.hpp", "include/service.hpp"}
    assert "cpp_declaration_sites" not in _classes(updated)[0].get("metadata", {})
    merged = build_merge([updated], graph_path=graph_path, root=tmp_path)
    assert len([n for _, n in merged.nodes(data=True)
                if n.get("label") == "Service" and n.get("_callable_class")]) == 1
    assert [(s, t, e.get("source_file"), e.get("source_location"))
            for s, t, e in merged.edges(data=True) if e.get("relation") == "calls"] == [
        (caller["id"], method["id"], "use.cpp", "L2"),
    ]
    assert merged.nodes[caller["id"]] == {k: v for k, v in caller.items() if k != "id"}
    assert merged.edges[owner["id"], method["id"]]["relation"] == "method"
    assert all(n.get("label") for _, n in merged.nodes(data=True))


def test_group_refresh_stays_inside_the_permitted_corpus_and_handles_deletions(tmp_path):
    from graphify.extractors.resolution import _cpp_reconciliation_paths

    for name in ("forward.hpp", "service.hpp", "excluded.hpp", "unrelated.hpp"):
        (tmp_path / name).write_text("class Service;", encoding="utf-8")
    nodes = [{"_cpp_reconcile_files": ["forward.hpp", "service.hpp", "excluded.hpp", "../outside.hpp"]}]
    paths = _cpp_reconciliation_paths(
        [], nodes, tmp_path,
        available_paths=[tmp_path / "forward.hpp", tmp_path / "unrelated.hpp"],
        changed_paths=[tmp_path / "service.hpp"],
    )
    assert paths == [tmp_path / "forward.hpp"]


@pytest.mark.parametrize("included", [False, True])
def test_external_cache_anchor_keeps_distinct_source_and_include_identities(tmp_path, included):
    source = tmp_path / "source"
    source.mkdir()
    forward = source / "forward.hpp"
    definition = source / "service.hpp"
    forward.write_text("class Service;", encoding="utf-8")
    definition.write_text(('#include "forward.hpp"\n' if included else '')
                          + "class Service {};", encoding="utf-8")
    result = extract([forward, definition], cache_root=tmp_path / "cache", parallel=False)
    owners = _classes(result)
    assert len(owners) == (1 if included else 2)
    if included:
        assert owners[0]["metadata"]["cpp_declaration_sites"] == [
            {"source_file": "../source/forward.hpp", "source_location": "L1"},
        ]
        assert owners[0]["_cpp_reconcile_files"] == ["../source/forward.hpp", "../source/service.hpp"]


@pytest.mark.parametrize("source,target", [("", ""), ("", "known.hpp"), ("known.hpp", "")])
def test_unknown_include_endpoints_never_prove_symbol_equivalence(source, target):
    from graphify.extractors.resolution import _cpp_include_path

    assert _cpp_include_path({source: {target}}, source, target) == []


@pytest.mark.parametrize("update", ["cli", "watch"])
@pytest.mark.parametrize("change", ["forward", "definition", "proof", "delete"])
def test_persisted_graph_rechecks_the_group_when_a_source_or_proof_changes(tmp_path, update, change):
    project = tmp_path / "project"
    _extract(project, {
        "forward.hpp": "class Service;",
        "bridge.hpp": '#include "forward.hpp"',
        "service.hpp": '#include "bridge.hpp"\nclass Service {};',
    })
    env = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[1]))
    command = [sys.executable, "-m", "graphify", "extract", str(project), "--code-only", "--no-cluster"]
    before = subprocess.run(command, env=env, cwd=tmp_path, text=True, capture_output=True)
    assert before.returncode == 0, before.stdout + before.stderr
    graph_path = project / "graphify-out/graph.json"
    assert len(_classes(json.loads(graph_path.read_text(encoding="utf-8")))) == 1
    changed = project / {"forward": "forward.hpp", "definition": "service.hpp",
                         "proof": "bridge.hpp", "delete": "service.hpp"}[change]
    if change == "delete":
        changed.unlink()
    else:
        changed.write_text({"forward": "class Other;", "definition": "class Service {};",
                            "proof": "// include removed"}[change], encoding="utf-8")
    if update == "cli":
        after = subprocess.run(command, env=env, cwd=tmp_path, text=True, capture_output=True)
        assert after.returncode == 0, after.stdout + after.stderr
    else:
        from graphify.watch import _rebuild_code
        assert _rebuild_code(project, changed_paths=[changed], no_cluster=True, acquire_lock=False)
    saved = json.loads(graph_path.read_text(encoding="utf-8"))
    classes = _classes(saved)
    assert len(classes) == (1 if change in {"forward", "delete"} else 2)
    assert all("cpp_declaration_sites" not in n.get("metadata", {}) for n in classes)


@pytest.mark.parametrize("update", ["cli", "watch"])
@pytest.mark.parametrize("change", ["new-forward", "second-definition"])
def test_updates_form_new_groups_and_split_new_ambiguities(tmp_path, update, change):
    project = tmp_path / "project"
    _extract(project, {
        "forward.hpp": "// no forward yet" if change == "new-forward" else "class Service;",
        "service.hpp": '#include "forward.hpp"\nclass Service {};',
    })
    env = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[1]))
    command = [sys.executable, "-m", "graphify", "extract", str(project), "--code-only", "--no-cluster"]
    initial = subprocess.run(command, env=env, cwd=tmp_path, text=True, capture_output=True)
    assert initial.returncode == 0, initial.stdout + initial.stderr
    changed = project / ("forward.hpp" if change == "new-forward" else "other.hpp")
    changed.write_text("class Service;" if change == "new-forward" else "class Service {};", encoding="utf-8")
    if update == "cli":
        after = subprocess.run(command, env=env, cwd=tmp_path, text=True, capture_output=True)
        assert after.returncode == 0, after.stdout + after.stderr
    else:
        from graphify.watch import _rebuild_code
        assert _rebuild_code(project, changed_paths=[changed], no_cluster=True, acquire_lock=False)
    saved = json.loads((project / "graphify-out/graph.json").read_text(encoding="utf-8"))
    classes = _classes(saved)
    assert len(classes) == (1 if change == "new-forward" else 3)
    assert bool(classes[0].get("metadata", {}).get("cpp_declaration_sites")) == (change == "new-forward")


def test_scoped_watch_paths_rebase_both_forward_sites_and_include_proofs(tmp_path):
    from graphify.watch import _rebase_relative_source_files

    payload = {"nodes": [{"source_file": "service.hpp", "_cpp_reconcile_files": ["forward.hpp", "service.hpp"],
                          "metadata": {"cpp_declaration_sites": [{"source_file": "forward.hpp", "source_location": "L2"}]}}]}
    _rebase_relative_source_files(payload, tmp_path / "include", tmp_path)
    node = payload["nodes"][0]
    assert node["_cpp_reconcile_files"] == ["include/forward.hpp", "include/service.hpp"]
    assert node["metadata"]["cpp_declaration_sites"] == [
        {"source_file": "include/forward.hpp", "source_location": "L2"},
    ]


def test_same_stem_conflicts_keep_distinct_class_member_ids_and_provenance_after_export(tmp_path):
    result = _extract(tmp_path, {
        "service.hpp": "class Service { public: void Run() {} };",
        "service.cpp": '#include "service.hpp"\nclass Service { public: void Run() {} };',
    })
    graph_path = tmp_path / "graph.json"
    to_json(build_from_json(result, root=tmp_path), {}, str(graph_path))
    saved = json.loads(graph_path.read_text(encoding="utf-8"))
    owners = _classes(saved)
    assert len({n["id"] for n in owners}) == 2
    assert {n["source_file"] for n in owners} == {"service.hpp", "service.cpp"}
    nodes = {n["id"]: n for n in saved["nodes"]}
    members = [e for e in saved["links"] if e["relation"] == "method"]
    assert len({e["target"] for e in members}) == 2
    assert all(nodes[e["source"]]["source_file"] == nodes[e["target"]]["source_file"]
               for e in members)


def test_recovered_conditional_facts_do_not_become_equivalence_evidence(tmp_path):
    from graphify.extractors.resolution import _merge_cpp_forward_classes

    condition = [{"group_line": 1, "branch": 0}]
    nodes = [
        {"id": "forward", "source_file": "forward.hpp", "_callable_class": True,
         "_cpp_qualified": "Service", "_cpp_class_kind": "forward", "metadata": {"cpp_conditions": condition}},
        {"id": "definition", "source_file": "service.hpp", "_callable_class": True,
         "_cpp_qualified": "Service", "_cpp_class_kind": "definition"},
    ]
    edges = [{"source": "file", "target": "forward-file", "source_file": "service.hpp",
              "target_file": "forward.hpp", "relation": "imports", "_cpp_include_proof": True}]
    _merge_cpp_forward_classes(nodes, edges, [], nodes, [], tmp_path)
    assert len(nodes) == 2
    assert nodes[0]["metadata"]["cpp_conditions"] == condition
