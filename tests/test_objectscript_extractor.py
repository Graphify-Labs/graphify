"""Extraction coverage for InterSystems ObjectScript (.cls/.mac/.inc/.rtn)."""

from __future__ import annotations

import importlib.util as _ilu
import sys
from pathlib import Path

import pytest

from graphify.extract import extract

FIXTURES = Path(__file__).parent / "fixtures"
OS_DIR = FIXTURES / "objectscript"

_needs_objectscript = pytest.mark.skipif(
    _ilu.find_spec("tree_sitter_objectscript_udl") is None
    or _ilu.find_spec("tree_sitter_objectscript_routine") is None,
    reason="tree-sitter-objectscript not installed (optional [objectscript] extra)",
)


def _edge_labels(
    result: dict, relation: str, *, confidence: str | None = None
) -> set[tuple[str, str]]:
    labels = {node["id"]: node["label"] for node in result["nodes"]}
    return {
        (labels.get(edge["source"], edge["source"]), labels.get(edge["target"], edge["target"]))
        for edge in result["edges"]
        if edge["relation"] == relation
        and (confidence is None or edge.get("confidence") == confidence)
    }


def _node_by_label(result: dict, label: str) -> dict:
    return next(n for n in result["nodes"] if n["label"] == label)


# ── Routing / registry / guard (no grammar required) ────────────────────────


def test_objectscript_dispatch_and_code_extensions(tmp_path):
    from graphify.detect import CODE_EXTENSIONS
    from graphify.extract import (
        _DISPATCH,
        collect_files,
        extract_apex,
        extract_objectscript,
        extract_pascal,
    )

    assert _DISPATCH[".mac"] is extract_objectscript
    assert _DISPATCH[".rtn"] is extract_objectscript
    assert ".int" not in _DISPATCH
    assert _DISPATCH[".cls"] is extract_apex
    assert _DISPATCH[".inc"] is extract_pascal
    for ext in (".mac", ".rtn", ".cls", ".inc"):
        assert ext in CODE_EXTENSIONS

    marker = tmp_path / "x.mac"
    marker.write_text("ROUTINE x\n Quit\n", encoding="utf-8")
    files = collect_files(tmp_path)
    assert any(p.name == "x.mac" for p in files)


def test_objectscript_extra_hint_mapping():
    from graphify.extract import _EXTRA_FOR_EXTENSION

    for ext in (".cls", ".inc", ".mac", ".rtn"):
        assert _EXTRA_FOR_EXTENSION[ext] == "objectscript"


def test_get_extractor_keeps_apex_and_pascal(tmp_path):
    from graphify.extract import _get_extractor, extract_apex, extract_pascal

    assert _get_extractor(FIXTURES / "sample.cls") is extract_apex
    assert _get_extractor(FIXTURES / "sample.trigger") is extract_apex

    consts = tmp_path / "consts.inc"
    consts.write_text("{$IFDEF FPC} const MaxItems = 10; {$ENDIF}\n", encoding="utf-8")
    assert _get_extractor(consts) is extract_pascal

    empty_inc = tmp_path / "empty.inc"
    empty_inc.write_text("", encoding="utf-8")
    assert _get_extractor(empty_inc) is extract_pascal


def test_get_extractor_routes_objectscript(tmp_path):
    from graphify.extract import _get_extractor, extract_objectscript

    assert _get_extractor(OS_DIR / "Demo.Base.cls") is extract_objectscript
    assert _get_extractor(OS_DIR / "DemoMacros.inc") is extract_objectscript

    upper = tmp_path / "Foo.CLS"
    upper.write_text(
        "Class Demo.Foo Extends %RegisteredObject\n{\n\nMethod Run()\n{\n    Quit\n}\n\n}\n",
        encoding="utf-8",
    )
    assert _get_extractor(upper) is extract_objectscript


def test_objectscript_registry_identity():
    import graphify.extract as facade
    from graphify.extractors import LANGUAGE_EXTRACTORS
    from graphify.extractors.objectscript import extract_objectscript

    assert LANGUAGE_EXTRACTORS["objectscript"] is extract_objectscript
    assert facade.extract_objectscript is extract_objectscript


def test_objectscript_resolver_registered():
    import graphify.extract  # noqa: F401  (registers resolvers on import)
    from graphify.resolver_registry import registered_resolvers

    names = [r.name for r in registered_resolvers()]
    assert "objectscript_calls" in names


def test_pascal_resolver_ignores_objectscript_raw_calls():
    from graphify.pascal_resolution import resolve_pascal_inherited_calls

    def _base_nodes_edges():
        nodes = [
            {"id": "base_run", "label": "Run()"},
            {"id": "child_run", "label": "Run()"},
        ]
        edges = [
            {"source": "child", "target": "base", "relation": "inherits"},
            {"source": "base", "target": "base_run", "relation": "method"},
            {"source": "child", "target": "child_run", "relation": "method"},
        ]
        return nodes, edges

    # A raw call tagged language="objectscript" but living in a `.inc` file
    # (shared suffix with Pascal) must be ignored by the Pascal resolver.
    tagged_nodes, tagged_edges = _base_nodes_edges()
    tagged_per_file = [
        {
            "raw_calls": [
                {
                    "caller_nid": "child_run",
                    "callee": "run",
                    "source_file": "DemoMacros.inc",
                    "source_location": None,
                    "language": "objectscript",
                }
            ],
        }
    ]
    resolve_pascal_inherited_calls(tagged_per_file, tagged_nodes, tagged_edges)
    assert ("child_run", "base_run") not in {
        (e["source"], e["target"]) for e in tagged_edges
    }

    # A genuine, untagged Pascal `.inc` raw call must still resolve (regression
    # guard: the language check must not swallow real Pascal calls).
    plain_nodes, plain_edges = _base_nodes_edges()
    plain_per_file = [
        {
            "raw_calls": [
                {
                    "caller_nid": "child_run",
                    "callee": "run",
                    "source_file": "unit.inc",
                    "source_location": None,
                }
            ],
        }
    ]
    resolve_pascal_inherited_calls(plain_per_file, plain_nodes, plain_edges)
    assert ("child_run", "base_run") in {(e["source"], e["target"]) for e in plain_edges}


def test_apex_and_pascal_end_to_end_unchanged(tmp_path):
    result = extract([FIXTURES / "sample.cls"], cache_root=tmp_path)
    labels = {n["label"] for n in result["nodes"]}
    assert "AccountService" in labels

    result_pas = extract([FIXTURES / "sample.pas"], cache_root=tmp_path)
    assert result_pas["nodes"]


# ── Grammar-backed structural tests ──────────────────────────────────────────


@_needs_objectscript
def test_objectscript_class_members_and_inherits():
    from graphify.extract import extract_objectscript

    result = extract_objectscript(OS_DIR / "Demo.Service.cls")
    labels = {n["label"] for n in result["nodes"]}
    assert {"Service", ".Run()", ".Helper()", "Config", "ADAPTER"} <= labels

    service_node = _node_by_label(result, "Service")
    assert service_node["metadata"]["full_name"] == "Demo.Service"

    assert ("Service", "Demo.Base") in _edge_labels(result, "inherits")
    assert (".Run()", ".Helper()") in _edge_labels(result, "calls")
    assert (".Run()", "Demo.Util") in _edge_labels(result, "instantiates")
    assert ("ADAPTER", "Demo.Util") in _edge_labels(result, "references", confidence="INFERRED")

    for rc in result.get("raw_calls", []):
        assert rc["is_member_call"] is True
        assert rc["language"] == "objectscript"

    node_ids = {n["id"] for n in result["nodes"]}
    assert all(e["source"] in node_ids and e["target"] in node_ids for e in result["edges"])


@_needs_objectscript
def test_objectscript_property_types():
    from graphify.extract import extract_objectscript

    result = extract_objectscript(OS_DIR / "Demo.Base.cls")
    labels_map = {n["id"]: n["label"] for n in result["nodes"]}

    field_refs = _edge_labels(result, "references")
    assert ("Util", "Demo.Util") in field_refs
    assert not any(target == "%String" for _src, target in field_refs)

    util_edge = next(
        e
        for e in result["edges"]
        if e["relation"] == "references" and labels_map.get(e["target"]) == "Demo.Util"
    )
    assert util_edge["context"] == "field"
    assert util_edge["confidence"] == "EXTRACTED"

    tags_node = _node_by_label(result, "Tags")
    assert tags_node["metadata"]["collection"] == "list"


@_needs_objectscript
def test_objectscript_routine_labels_and_local_calls():
    from graphify.extract import extract_objectscript

    result = extract_objectscript(OS_DIR / "DemoRtn.mac")
    labels = {n["label"] for n in result["nodes"]}
    assert {"Main()", "Init()", "DemoRtn"} <= labels

    call_labels = _edge_labels(result, "calls")
    assert ("Main()", "Init()") in call_labels
    assert ("DemoRtn", "Init()") in call_labels

    assert ("DemoRtn.mac", "DemoMacros") in _edge_labels(result, "includes")


@_needs_objectscript
def test_objectscript_include_macros():
    from graphify.extract import extract_objectscript

    result = extract_objectscript(OS_DIR / "DemoMacros.inc")
    include_node = _node_by_label(result, "DemoMacros")
    assert include_node["metadata"]["kind"] == "include"

    labels = {n["label"] for n in result["nodes"]}
    assert {"$$$DEMOOK", "$$$DEMOFAIL"} <= labels

    contains_labels = _edge_labels(result, "contains")
    assert ("DemoMacros", "$$$DEMOOK") in contains_labels
    assert ("DemoMacros", "$$$DEMOFAIL") in contains_labels


@_needs_objectscript
def test_objectscript_cross_file_end_to_end(tmp_path):
    result = extract(sorted(OS_DIR.glob("*")), cache_root=tmp_path)
    labels_map = {n["id"]: n["label"] for n in result["nodes"]}

    run_start_edges = [
        e
        for e in result["edges"]
        if e["relation"] == "calls"
        and labels_map.get(e["source"]) == ".Run()"
        and labels_map.get(e["target"]) == ".Start()"
    ]
    assert len(run_start_edges) == 1
    assert run_start_edges[0]["confidence"] == "EXTRACTED"
    assert run_start_edges[0]["context"] == "class_method_call"

    call_labels = _edge_labels(result, "calls")
    assert (".Run()", "Calc()") in call_labels
    assert ("Main()", "Calc()") in call_labels

    assert ("Service", "Base") in _edge_labels(result, "inherits")

    all_labels = {n["label"] for n in result["nodes"]}
    assert "Demo.Base" not in all_labels
    assert "Demo.Util" not in all_labels
    stub_labels = {
        n["label"] for n in result["nodes"] if n.get("metadata", {}).get("kind") == "external_class"
    }
    assert "Demo.Base" not in stub_labels
    assert "Demo.Util" not in stub_labels

    include_edges = [e for e in result["edges"] if e["relation"] == "includes"]
    assert len(include_edges) == 2
    assert len({e["target"] for e in include_edges}) == 1
    assert labels_map[include_edges[0]["target"]] == "DemoMacros"

    uses_inferred = _edge_labels(result, "uses", confidence="INFERRED")
    assert (".Run()", "$$$DEMOOK") in uses_inferred
    assert ("Main()", "$$$DEMOOK") in uses_inferred


@_needs_objectscript
def test_objectscript_xdata_reference_is_inferred_not_extracted():
    from graphify.extract import extract_objectscript

    result = extract_objectscript(OS_DIR / "Demo.Service.cls")
    labels_map = {n["id"]: n["label"] for n in result["nodes"]}

    dtmap_edges = [
        e
        for e in result["edges"]
        if e["relation"] == "references" and labels_map.get(e["target"]) == "Demo.DT.Map"
    ]
    assert dtmap_edges
    for e in dtmap_edges:
        assert e["confidence"] in ("INFERRED", "AMBIGUOUS")
        assert e["context"] == "value"
        assert e["metadata"]["attribute"] == "targetClass"
        assert e["confidence"] != "EXTRACTED"


@_needs_objectscript
def test_objectscript_no_dangling_edges_end_to_end(tmp_path):
    result = extract(sorted(OS_DIR.glob("*")), cache_root=tmp_path)
    node_ids = {n["id"] for n in result["nodes"]}
    for e in result["edges"]:
        assert e["source"] in node_ids, f"dangling source: {e}"
        assert e["target"] in node_ids, f"dangling target: {e}"


@_needs_objectscript
def test_objectscript_folder_layout_matches_dotted_layout(tmp_path):
    from graphify.extract import extract_objectscript

    nested = tmp_path / "Demo" / "Util.cls"
    nested.parent.mkdir(parents=True)
    nested.write_text((OS_DIR / "Demo.Util.cls").read_text(encoding="utf-8"), encoding="utf-8")

    flat_result = extract_objectscript(OS_DIR / "Demo.Util.cls")
    nested_result = extract_objectscript(nested)

    flat_class = _node_by_label(flat_result, "Util")
    nested_class = _node_by_label(nested_result, "Util")
    assert flat_class["metadata"]["full_name"] == "Demo.Util"
    assert nested_class["metadata"]["full_name"] == "Demo.Util"


@_needs_objectscript
def test_objectscript_strings_and_garbage_do_not_create_phantoms(tmp_path):
    from graphify.extract import extract_objectscript

    broken = tmp_path / "Broken.cls"
    broken.write_text(
        "Class Demo.Broken Extends %RegisteredObject\n"
        "{\n\n"
        "Method Valid() As %Status\n"
        "{\n"
        '    Set msg = "Method Ghost() should not exist"\n'
        "    Quit $$$OK\n"
        "}\n\n"
        "}\n"
        "??? garbage {{{\n",
        encoding="utf-8",
    )

    result = extract_objectscript(broken)
    labels_cf = {n["label"].casefold() for n in result["nodes"]}
    assert ".valid()" in labels_cf
    assert "ghost()" not in labels_cf
    assert any(n["label"] == "Broken" for n in result["nodes"])
    assert isinstance(result["parse_errors"]["first_error_line"], int)


def test_objectscript_missing_grammar_reports_install_hint(tmp_path, monkeypatch, capsys):
    monkeypatch.setitem(sys.modules, "tree_sitter_objectscript_udl", None)
    monkeypatch.setitem(sys.modules, "tree_sitter_objectscript_routine", None)

    mac = tmp_path / "missing.mac"
    mac.write_text("ROUTINE missing\n Quit\n", encoding="utf-8")
    result = extract([mac], cache_root=tmp_path)
    assert result["nodes"] == []
    assert 'pip install "graphifyy[objectscript]"' in capsys.readouterr().err

    cls = tmp_path / "Missing.cls"
    cls.write_text(
        "Class Demo.Missing Extends %RegisteredObject\n"
        "{\n\nMethod Run()\n{\n    Quit\n}\n\n}\n",
        encoding="utf-8",
    )
    result2 = extract([cls], cache_root=tmp_path)
    assert result2["nodes"] == []
    assert 'pip install "graphifyy[objectscript]"' in capsys.readouterr().err


# ── Adversarial-review regression coverage ───────────────────────────────────


def test_is_objectscript_include_rejects_plain_c_header(tmp_path):
    # A C-style header guard uses the exact same preprocessor vocabulary
    # (#ifndef/#define/#include/#endif) as ObjectScript macro syntax, but has
    # no InterSystems-specific marker anywhere in it. It must not be routed
    # to the ObjectScript extractor, which would fabricate phantom nodes
    # (e.g. a "label" for a C function prototype) out of non-ObjectScript
    # content.
    from graphify.extractors.objectscript import _is_objectscript_include

    c_header = tmp_path / "cstyle.inc"
    c_header.write_text(
        "#ifndef FOO_H\n#define FOO_H\n#include <stdio.h>\nvoid foo(void);\n#endif\n",
        encoding="utf-8",
    )
    assert _is_objectscript_include(c_header) is False

    # A genuine ObjectScript include (uses a `$$$` macro body, an
    # InterSystems-specific signal) must still be recognized.
    os_inc = tmp_path / "os.inc"
    os_inc.write_text(
        '#define OK 1\n#define FAIL(%msg) $$$ERROR($$$GeneralError,%msg)\n', encoding="utf-8"
    )
    assert _is_objectscript_include(os_inc) is True


def test_is_objectscript_include_recognizes_ro_export_and_dollar_functions(tmp_path):
    # Three real-world ObjectScript includes that carry no `$$$`/`#dim`/`##`
    # marker at all, so the C-header guard above would otherwise reject them.
    from graphify.extractors.objectscript import _is_objectscript_include

    # 1. Legacy `%RO` export container (Studio "Save for Source Control"):
    #    banner line, `%RO`, `Name^INC`, then the routine body.
    ro = tmp_path / "Legacy.inc"
    ro.write_text(
        "^INC^Save for Source Control^^~Format=Cache.S~^UTF8\n%RO\nTSL.Legacy^INC\n"
        "#define LEGACY 1\n",
        encoding="utf-8",
    )
    assert _is_objectscript_include(ro) is True

    # 2. `#define` whose value calls an intrinsic `$Function(`: `$` is not an
    #    identifier character in C and Pascal never puts `$` before `(`.
    dollar = tmp_path / "Dollar.inc"
    dollar.write_text('#define NOW $ZDateTime($Horolog, 3)\n', encoding="utf-8")
    assert _is_objectscript_include(dollar) is True

    # 3. Macro parameters must start with `%` in ObjectScript; C never does.
    pct = tmp_path / "Pct.inc"
    pct.write_text("#define TWICE(%x) (%x*2)\n", encoding="utf-8")
    assert _is_objectscript_include(pct) is True

    # A plain C header with a function-like macro is still rejected.
    c_header = tmp_path / "c.inc"
    c_header.write_text("#ifndef X_H\n#define X_H\n#define TWICE(x) ((x)*2)\n#endif\n", encoding="utf-8")
    assert _is_objectscript_include(c_header) is False


@_needs_objectscript
def test_objectscript_ro_export_include_keeps_packaged_routine_name(tmp_path):
    # In a `%RO` export the routine name lives on the third line
    # (`TSL.Legacy^INC^^^0`), not at byte 0; the include node must carry the
    # packaged name so `#include TSL.Legacy` elsewhere can retarget to it.
    from graphify.extract import extract_objectscript

    ro = tmp_path / "Legacy.inc"
    ro.write_text(
        "^INC^Save for Source Control^^~Format=Cache.S~^UTF8\n%RO\nTSL.Legacy^INC^^^0\n"
        "#define LEGACY 1\n",
        encoding="utf-8",
    )
    r = extract_objectscript(ro)
    assert "error" not in r and not r.get("parse_errors")
    include = _node_by_label(r, "TSL.Legacy")
    assert include["metadata"]["kind"] == "include"
    assert include["metadata"]["routine"] == "TSL.Legacy"
    assert "$$$LEGACY" in {n["label"] for n in r["nodes"]}


def test_is_objectscript_class_detects_minimal_undotted_class(tmp_path):
    # A class with no package-qualified name and no typed member still uses
    # no substring in _OS_CLASS_MARKERS; the sniff must not silently
    # misroute it to the Apex extractor just because it happens to have a
    # short, undotted name.
    from graphify.extractors.objectscript import _is_objectscript_class

    minimal = tmp_path / "MyClass.cls"
    minimal.write_text("Class MyClass\n{\n\nMethod Run()\n{\n    Quit\n}\n\n}\n", encoding="utf-8")
    assert _is_objectscript_class(minimal) is True

    # The Apex fixture must still be correctly rejected (lowercase `class`,
    # not line-anchored).
    assert _is_objectscript_class(FIXTURES / "sample.cls") is False


@_needs_objectscript
def test_objectscript_resolver_prefers_extracted_over_inferred_call(tmp_path):
    # Two raw_calls can target the identical (caller, callee) edge with
    # different evidence strength: an inherited `..M()` self_call
    # (INFERRED/inherited_call) and a qualified `##class(X).M()` class_call
    # (EXTRACTED/class_method_call) for the exact same call. Whichever is
    # processed first must not permanently lock in the weaker edge -- the
    # stronger, qualified evidence must win regardless of statement order.
    from graphify.extract import extract_objectscript
    from graphify.extract import resolve_objectscript_calls as resolve_objectscript_calls_

    base = tmp_path / "Demo.Base.cls"
    base.write_text(
        "Class Demo.Base Extends %RegisteredObject\n"
        "{\n\nMethod Start() As %Status\n{\n\tQuit $$$OK\n}\n\n}\n",
        encoding="utf-8",
    )

    def _resolved_confidence(body: str) -> tuple[str, str, int]:
        svc = tmp_path / "Demo.Service.cls"
        svc.write_text(
            f"Class Demo.Service Extends Demo.Base\n{{\n\nMethod Run() As %Status\n{{\n{body}"
            "\tQuit $$$OK\n}\n\n}\n",
            encoding="utf-8",
        )
        per_file = [extract_objectscript(base), extract_objectscript(svc)]
        all_nodes: list[dict] = []
        all_edges: list[dict] = []
        for r in per_file:
            all_nodes.extend(r["nodes"])
            all_edges.extend(r["edges"])
        resolve_objectscript_calls_(per_file, all_nodes, all_edges)
        labels = {n["id"]: n["label"] for n in all_nodes}
        run_start = [
            e
            for e in all_edges
            if e["relation"] == "calls"
            and labels.get(e["source"]) == ".Run()"
            and labels.get(e["target"]) == ".Start()"
        ]
        assert len(run_start) == 1, run_start
        return run_start[0]["confidence"], run_start[0]["context"], len(run_start)

    # Self-call (masked/weak evidence) written BEFORE the qualified call --
    # this is the order that reproduced the bug (first-writer-wins emit()).
    conf, ctx, count = _resolved_confidence("\tDo ..Start()\n\tDo ##class(Demo.Base).Start()\n")
    assert (conf, ctx, count) == ("EXTRACTED", "class_method_call", 1)

    # Qualified call written first (the order the shipped fixtures already
    # used, which happened to mask the bug) must still resolve correctly.
    conf2, ctx2, count2 = _resolved_confidence("\tDo ##class(Demo.Base).Start()\n\tDo ..Start()\n")
    assert (conf2, ctx2, count2) == ("EXTRACTED", "class_method_call", 1)


@_needs_objectscript
def test_objectscript_xdata_bare_call_routes_to_self_call(tmp_path):
    # A.5: a bare same-class production `Call="MethodName"` (no `ClassName:`
    # prefix) must route to on_self_call, not be silently dropped just
    # because it lacks the qualified `Cls:Method` form.
    from graphify.extract import extract_objectscript

    cls = tmp_path / "Demo.Xd.cls"
    cls.write_text(
        "Class Demo.Xd Extends %RegisteredObject\n"
        "{\n\nClassMethod Helper()\n{\n\tQuit\n}\n\n"
        'XData Config\n{\n<Production>\n<Item Call="Helper"></Item>\n</Production>\n}\n\n}\n',
        encoding="utf-8",
    )
    result = extract_objectscript(cls)
    call_edges = _edge_labels(result, "calls")
    assert ("Config", ".Helper()") in call_edges
    confidences = {
        e["confidence"]
        for e in result["edges"]
        if e["relation"] == "calls"
        and {n["id"]: n["label"] for n in result["nodes"]}.get(e["target"]) == ".Helper()"
    }
    assert confidences == {"INFERRED"}


@_needs_objectscript
def test_objectscript_class_keyword_multi_value_references_all_classes(tmp_path):
    # `DependsOn = (Demo.A, Demo.B)` parses as one `class_keyword` node with
    # TWO `class_name` children; every one of them must get a `references`
    # edge, not just the first (class_extends, a few lines above in the same
    # function, already loops all its class_name children correctly).
    from graphify.extract import extract_objectscript

    cls = tmp_path / "Demo.DependsMulti.cls"
    cls.write_text("Class Demo.DependsMulti [ DependsOn = (Demo.A, Demo.B) ]\n{\n}\n", encoding="utf-8")
    result = extract_objectscript(cls)
    refs = _edge_labels(result, "references")
    assert ("DependsMulti", "Demo.A") in refs
    assert ("DependsMulti", "Demo.B") in refs


@_needs_objectscript
def test_objectscript_pound_if_expression_body_is_not_dropped(tmp_path):
    # `#if <expr>` (unlike `#ifdef`/`#ifndef`) parses to a leaf node with raw,
    # unparsed body text -- calls inside it must not be silently lost.
    from graphify.extract import extract_objectscript

    mac = tmp_path / "PoundIf.mac"
    mac.write_text(
        "ROUTINE PoundIf\nMain\n#if 1\n Do Inner\n#endif\n Quit\nInner\n Quit\n", encoding="utf-8"
    )
    result = extract_objectscript(mac)
    call_edges = _edge_labels(result, "calls")
    assert ("Main()", "Inner()") in call_edges

    # Same gap, but for a `##class(...)` call and a `$$$MACRO` use.
    mac2 = tmp_path / "PoundIf2.mac"
    mac2.write_text(
        "ROUTINE PoundIf2\nMain\n#if 1\n Do ##class(Demo.Other).Foo()\n"
        " Set x=$$$MYMACRO\n#endif\n Quit\n",
        encoding="utf-8",
    )
    result2 = extract_objectscript(mac2)
    assert any(
        rc.get("kind") == "class_call" and rc.get("callee") == "Foo"
        for rc in result2.get("raw_calls", [])
    )
    assert any(
        rc.get("kind") == "macro_use" and rc.get("callee") == "MYMACRO"
        for rc in result2.get("raw_calls", [])
    )

    # Also unparsed inside a UDL method body (`..Method()` self-call).
    cls = tmp_path / "Demo.CondUdl.cls"
    cls.write_text(
        "Class Demo.CondUdl Extends %RegisteredObject\n"
        "{\n\nClassMethod Helper()\n{\n\tQuit\n}\n\n"
        "ClassMethod Run()\n{\n#if 1\n\tDo ..Helper()\n#endif\n\tQuit\n}\n\n}\n",
        encoding="utf-8",
    )
    result3 = extract_objectscript(cls)
    assert (".Run()", ".Helper()") in _edge_labels(result3, "calls")


@_needs_objectscript
def test_objectscript_codemode_expression_body_is_walked(tmp_path):
    # `[ CodeMode = expression ]` bodies are a single `expression` node
    # directly under the method container, never `statement` children --
    # calls inside them were never walked at all.
    from graphify.extract import extract_objectscript

    cls = tmp_path / "Demo.CodeModeExpr.cls"
    cls.write_text(
        "Class Demo.CodeModeExpr Extends %RegisteredObject\n"
        "{\n\nMethod Calc() As %Integer [ CodeMode = expression ]\n"
        "{\n##class(Demo.Other).Foo()\n}\n\n}\n",
        encoding="utf-8",
    )
    result = extract_objectscript(cls)
    assert any(
        rc.get("kind") == "class_call" and rc.get("callee") == "Foo"
        and rc.get("target_class") == "Demo.Other"
        for rc in result.get("raw_calls", [])
    )
    calc_node = _node_by_label(result, ".Calc()")
    assert calc_node["metadata"]["codemode"] == "expression"


@_needs_objectscript
def test_objectscript_quoted_class_name_full_name_recovered(tmp_path):
    # tree-sitter-objectscript 1.9.22 cannot parse a delimited class-name
    # segment (`Demo."My Class"`): it emits only the unquoted prefix as
    # `class_name`, with the rest folded into a sibling ERROR node. The
    # class must not be silently mis-identified as just "Demo".
    from graphify.extract import extract_objectscript

    cls = tmp_path / "quoted.cls"
    cls.write_text(
        'Class Demo."My Class" Extends %RegisteredObject\n{\n\nMethod M()\n{\n\tQuit\n}\n\n}\n',
        encoding="utf-8",
    )
    result = extract_objectscript(cls)
    class_nodes = [n for n in result["nodes"] if n.get("metadata", {}).get("kind") == "class"]
    assert len(class_nodes) == 1
    full = class_nodes[0]["metadata"]["full_name"]
    assert full == 'Demo."My Class"'
    assert full != "Demo"
