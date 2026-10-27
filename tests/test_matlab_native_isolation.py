"""MATLAB provenance never enters shared/native name resolution candidates."""
from copy import deepcopy

import pytest

from graphify.extract import (
    _merge_swift_extensions,
    _resolve_cpp_member_calls,
    _resolve_objc_member_calls,
    _resolve_swift_member_calls,
    _rewire_unique_stub_nodes,
    extract,
)


def _node(nid, label, source_file, *, matlab=False, **flags):
    node = {
        "id": nid, "label": label, "source_file": source_file,
        "file_type": "code", "source_location": "L1", **flags,
    }
    if matlab:
        node["metadata"] = {"language": "matlab"}
    return node


@pytest.mark.parametrize("label", ["Widget", "helper()"])
@pytest.mark.parametrize("native_present", [False, True])
def test_stub_rewiring_excludes_matlab_before_uniqueness(label, native_present):
    nodes = [
        _node("caller", "caller()", "caller.cpp"),
        _node("stub", label.strip("()"), ""),
        _node("matlab", label, "symbol.m", matlab=True),
    ]
    if native_present:
        nodes.append(_node("native", label, "symbol.cpp"))
    edges = [{"source": "caller", "target": "stub", "relation": "references",
              "source_file": "caller.cpp"}]

    _rewire_unique_stub_nodes(nodes, edges)

    assert edges[0]["target"] == ("native" if native_present else "stub")
    assert any(n["id"] == "matlab" for n in nodes)


def test_stub_rewiring_preserves_matlab_source_edges():
    nodes = [
        _node("matlab", "caller()", "caller.m", matlab=True),
        _node("native", "Widget", "widget.cpp"),
        _node("stub", "Widget", ""),
        _node("caller", "caller()", "caller.cpp"),
    ]
    edges = [
        {"source": "matlab", "target": "stub", "relation": "references",
         "source_file": "caller.m"},
        {"source": "caller", "target": "stub", "relation": "references",
         "source_file": "caller.cpp"},
    ]
    matlab_edge = deepcopy(edges[0])

    _rewire_unique_stub_nodes(nodes, edges)

    assert edges[0] == matlab_edge
    assert edges[1]["target"] == "native"


@pytest.mark.parametrize("language,resolver,suffix", [
    ("cpp", _resolve_cpp_member_calls, ".cpp"),
    ("objc", _resolve_objc_member_calls, ".m"),
    ("swift", _resolve_swift_member_calls, ".swift"),
])
@pytest.mark.parametrize("native_present", [False, True])
def test_native_member_candidates_exclude_matlab(language, resolver, suffix, native_present):
    caller_file = "caller" + suffix
    nodes = [
        _node("caller", "caller()", caller_file),
        _node("matlab_class", "Widget", "Widget.m", matlab=True, _callable_class=True),
        _node("matlab_method", ".work()", "Widget.m", matlab=True, _callable=True),
    ]
    edges = [
        {"source": "matlab_file", "target": "matlab_class", "relation": "contains"},
        {"source": "matlab_class", "target": "matlab_method", "relation": "method"},
    ]
    if native_present:
        nodes.extend([
            _node("native_class", "Widget", "native" + suffix, _callable_class=True),
            _node("native_method", ".work()", "native" + suffix, _callable=True),
        ])
        edges.extend([
            {"source": "native_file", "target": "native_class", "relation": "contains"},
            {"source": "native_class", "target": "native_method", "relation": "method"},
        ])
    original_edges = deepcopy(edges)
    per_file = [{
        "raw_calls": [{"caller_nid": "caller", "callee": "work", "receiver": "Widget",
                       "is_member_call": True, "lang": language, "source_file": caller_file}],
        language + "_type_table": {"path": caller_file, "table": {}},
    }]

    resolver(per_file, nodes, edges)

    assert edges[:len(original_edges)] == original_edges
    calls = [e for e in edges if e.get("source") == "caller"]
    assert [(e["relation"], e["target"]) for e in calls] == (
        [("calls", "native_method")] if native_present else []
    )


@pytest.mark.parametrize("native_present", [False, True])
def test_swift_extensions_do_not_merge_into_matlab(native_present):
    nodes = [
        _node("extension", "Widget", "extension.swift"),
        _node("matlab", "Widget", "Widget.m", matlab=True),
    ]
    edges = [{"source": "matlab_file", "target": "matlab", "relation": "contains"},
             {"source": "extension", "target": "method", "relation": "method"}]
    if native_present:
        nodes.append(_node("native", "Widget", "Widget.swift"))
        edges.append({"source": "native_file", "target": "native", "relation": "contains"})
    per_file = [{"swift_extensions": [{"nid": "extension", "label": "Widget"}]}]

    _merge_swift_extensions(per_file, nodes, edges)

    assert next(e for e in edges if e["relation"] == "method")["source"] == (
        "native" if native_present else "extension"
    )
    assert any(n["id"] == "matlab" for n in nodes)


@pytest.mark.parametrize("native_location", ["absent", "fresh", "unchanged"])
@pytest.mark.parametrize("suffix,caller_body,native_body,matlab_label", [
    (".c", "void caller() { helper(); }", "void helper() {}", "helper()"),
    (".php", "<?php function caller() { helper(); }",
     "<?php function Helper() {}", "helper()"),
])
def test_direct_calls_ignore_matlab_context_before_selection(
    tmp_path, native_location, suffix, caller_body, native_body, matlab_label,
):
    caller = tmp_path / ("caller" + suffix)
    caller.write_text(caller_body)
    paths = [caller]
    context = [_node("matlab", matlab_label, "helper.m", matlab=True, _callable=True)]
    context_edges = []
    if native_location != "absent":
        native = tmp_path / ("native" + suffix)
        native.write_text(native_body)
        if native_location == "fresh":
            paths.append(native)
        else:
            unchanged = extract([native], root=tmp_path, cache_root=tmp_path, parallel=False)
            context.extend(unchanged["nodes"])
            context_edges.extend(unchanged["edges"])
    original_context = deepcopy(context)

    result = extract(paths, root=tmp_path, cache_root=tmp_path, parallel=False,
                     resolution_context_nodes=context, resolution_context_edges=context_edges)

    labels = {n["id"]: n["label"] for n in result["nodes"] + context}
    calls = [e for e in result["edges"] if e["relation"] == "calls"
             and labels.get(e["source"]) == "caller()"]
    assert all(e["target"] != "matlab" for e in calls)
    assert [labels[e["target"]] for e in calls] == (
        [] if native_location == "absent" else ["Helper()" if suffix == ".php" else "helper()"]
    )
    assert context == original_context
    assert not any(n["id"] == "matlab" for n in result["nodes"])


@pytest.mark.parametrize("native_location", ["absent", "fresh", "unchanged"])
def test_indirect_calls_ignore_matlab_callable_before_selection(tmp_path, native_location):
    caller = tmp_path / "caller.py"
    caller.write_text("def schedule(pool):\n    pool.submit(helper)\n")
    paths = [caller]
    context = [_node("matlab", "helper()", "helper.m", matlab=True, _callable=True)]
    context_edges = []
    if native_location != "absent":
        native = tmp_path / "helper.py"
        native.write_text("def helper(value):\n    return value\n")
        if native_location == "fresh":
            paths.append(native)
        else:
            unchanged = extract([native], root=tmp_path, cache_root=tmp_path, parallel=False)
            context.extend(unchanged["nodes"])
            context_edges.extend(unchanged["edges"])

    result = extract(
        paths, root=tmp_path, cache_root=tmp_path, parallel=False,
        resolution_context_nodes=context, resolution_context_edges=context_edges,
    )
    labels = {n["id"]: n["label"] for n in result["nodes"] + context}
    calls = [e for e in result["edges"] if e["relation"] == "indirect_call"
             and labels.get(e["source"]) == "schedule()"]

    assert [labels[e["target"]] for e in calls] == (
        [] if native_location == "absent" else ["helper()"]
    )
    assert not any(e["target"] == "matlab" for e in calls)
