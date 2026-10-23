"""Extraction coverage for vbnet."""


from __future__ import annotations





import importlib.util as _ilu
import sys


from pathlib import Path





import pytest

from graphify.extract import extract

# tree-sitter-vb-dotnet is an optional extra, not installed by a default
# `uv sync`. Skip the grammar tests when it is absent; the missing-parser
# test below still runs because it simulates the absent grammar itself.
_needs_vbnet = pytest.mark.skipif(
    _ilu.find_spec("tree_sitter_vb_dotnet") is None,
    reason="tree-sitter-vb-dotnet not installed (optional [vbnet] extra)",
)





FIXTURE = Path(__file__).parent / "fixtures" / "new_languages" / "sample.vb"





def _edge_labels(result: dict, relation: str) -> set[tuple[str, str]]:
    labels = {node["id"]: node["label"] for node in result["nodes"]}
    return {
        (labels.get(edge["source"], edge["source"]), labels.get(edge["target"], edge["target"]))
        for edge in result["edges"]
        if edge["relation"] == relation
    }


@_needs_vbnet
def test_vbnet_class_methods_and_case_insensitive_calls(tmp_path):
    source = tmp_path / "Counter.vb"
    source.write_text(
        "Namespace Demo\n"
        " Public Class Counter\n"
        "  Public Sub Run()\n"
        "   helper()\n"
        "  End Sub\n"
        "  Private Sub Helper()\n"
        "  End Sub\n"
        " End Class\n"
        "End Namespace\n",
        encoding="utf-8",
    )

    result = extract([source], cache_root=tmp_path)

    labels = {node["label"] for node in result["nodes"]}
    assert {"Demo", "Counter", "Run()", "Helper()"} <= labels
    assert ("Run()", "Helper()") in _edge_labels(result, "calls")


@_needs_vbnet
def test_vbnet_module_qualified_call_resolves_to_the_module_method(tmp_path):
    # A call qualified by a type/module name (Helpers.Log()) — the idiomatic way
    # to reach a shared Module Sub — was dropped entirely: the invocation
    # resolver only fired for self/unqualified receivers, so the caller had no
    # edge to the module method it invoked.
    source = tmp_path / "App.vb"
    source.write_text(
        "Namespace Demo\n"
        " Public Module Helpers\n"
        "  Public Sub Log()\n"
        "  End Sub\n"
        " End Module\n"
        " Public Class Service\n"
        "  Public Sub Run()\n"
        "   Helpers.Log()\n"
        "  End Sub\n"
        " End Class\n"
        "End Namespace\n",
        encoding="utf-8",
    )

    result = extract([source], cache_root=tmp_path)

    assert ("Run()", "Log()") in _edge_labels(result, "calls")


@_needs_vbnet
def test_vbnet_call_through_a_value_receiver_stays_unresolved(tmp_path):
    # A call through a value receiver (a local variable) has no statically known
    # owner, so it must NOT be guessed into a false edge (fail-closed).
    source = tmp_path / "App.vb"
    source.write_text(
        "Public Class Other\n"
        " Public Sub Save()\n"
        " End Sub\n"
        "End Class\n"
        "Public Class Service\n"
        " Public Sub Run()\n"
        "  obj.Save()\n"
        " End Sub\n"
        "End Class\n",
        encoding="utf-8",
    )

    result = extract([source], cache_root=tmp_path)

    assert ("Run()", "Save()") not in _edge_labels(result, "calls")


@_needs_vbnet
def test_vbnet_types_members_relationships_and_partial_calls(tmp_path):
    first = tmp_path / "Counter.vb"
    first.write_text(
        "Imports System.Text\n"
        "Namespace Demo\n"
        " Public Interface IWorker\n  Sub Run()\n End Interface\n"
        " Public Class BaseCounter\n End Class\n"
        " Public Partial Class Counter\n"
        "  Inherits BaseCounter\n  Implements IWorker\n"
        "  Private count As Integer\n"
        "  Public Event Changed As EventHandler\n"
        "  Public Property Value As Integer\n"
        "  Public Sub New()\n  End Sub\n"
        "  Public Sub Run() Implements IWorker.Run Handles Me.Changed\n"
        "   hElPeR()\n  End Sub\n"
        " End Class\n"
        " Public Structure Pair\n End Structure\n"
        " Public Enum State\n  OnValue\n  OffValue\n End Enum\n"
        "End Namespace\n",
        encoding="utf-8",
    )
    second = tmp_path / "Counter.Designer.vb"
    second.write_text(
        "Namespace Demo\n"
        " Partial Public Class Counter\n"
        "  Private Sub Helper(Of T)(\n"
        "      Optional value As T = Nothing)\n"
        "  End Sub\n"
        " End Class\n"
        "End Namespace\n",
        encoding="utf-8",
    )
    project = tmp_path / "Demo.vbproj"
    project.write_text(
        '<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup>'
        '<TargetFramework>net8.0</TargetFramework></PropertyGroup></Project>',
        encoding="utf-8",
    )

    result = extract([first, second, project], cache_root=tmp_path)

    labels = {node["label"] for node in result["nodes"]}
    assert {
        "Demo", "IWorker", "BaseCounter", "Counter", "Pair", "State",
        "OnValue", "OffValue", "count", "Changed", "Value", "New()",
        "Run()", "Helper()", "System.Text", "net8.0",
    } <= labels
    assert ("Counter", "BaseCounter") in _edge_labels(result, "inherits")
    assert ("Counter", "IWorker") in _edge_labels(result, "implements")
    assert ("Run()", "Helper()") in _edge_labels(result, "calls")
    assert ("Run()", "Changed") in _edge_labels(result, "handles")


@_needs_vbnet
def test_vbnet_fixture_uses_normal_extract_path(tmp_path):
    result = extract([FIXTURE], cache_root=tmp_path)

    labels = {node["label"] for node in result["nodes"]}
    assert {'Helper()', 'Fixtures', 'Run()', 'Sample'} <= labels
    assert ('Run()', 'Helper()') in _edge_labels(result, "calls")


@_needs_vbnet
def test_vbnet_malformed_tail_comments_and_strings_do_not_create_phantoms(tmp_path):
    source = tmp_path / 'Broken.vb'
    source.write_text("Class Broken\n Sub Valid()\n End Sub\nEnd Class\n???\n' Sub Ghost()\n", encoding="utf-8")

    result = extract([source], cache_root=tmp_path)

    labels = {node["label"].casefold() for node in result["nodes"]}
    assert 'valid()' in labels
    assert labels.isdisjoint({'ghost()'})


def test_vbnet_missing_parser_reports_install_hint(tmp_path, monkeypatch, capsys):
    source = tmp_path / "missing.vb"
    source.write_text('Class Missing\nEnd Class\n', encoding="utf-8")
    monkeypatch.setitem(sys.modules, 'tree_sitter_vb_dotnet', None)

    result = extract([source], cache_root=tmp_path)

    assert result["nodes"] == []
    assert 'pip install "graphifyy[vbnet]"' in capsys.readouterr().err


@_needs_vbnet
def test_vbnet_enum_members_emit_case_of_not_contains(tmp_path):
    """A VB.NET enum member is a discriminant case, so it must get a `case_of`
    edge like every other language with enums (Java #1719, C#, Swift, Scala),
    not the `contains` edge used for real fields. VB.NET was the lone outlier,
    routing enum members through the same `contains` path as class fields. The
    relation also matters to resolution: `case_of` targets are excluded from
    `New X()` constructor binding, so an enum member named like a type can no
    longer be mistaken for one.
    """
    source = tmp_path / "Enums.vb"
    source.write_text(
        "Public Enum Color\n"
        "  Red\n"
        "  Green\n"
        "  Blue\n"
        "End Enum\n"
        "Public Class Widget\n"
        "  Private count As Integer\n"
        "End Class\n",
        encoding="utf-8",
    )

    result = extract([source], cache_root=tmp_path)

    case_of = _edge_labels(result, "case_of")
    contains = _edge_labels(result, "contains")
    # Each enum member hangs off its enum via case_of, not contains.
    assert ("Color", "Red") in case_of
    assert ("Color", "Green") in case_of
    assert ("Color", "Blue") in case_of
    assert ("Color", "Red") not in contains
    # A real class field is a declaration, not a case: it keeps `contains`.
    assert ("Widget", "count") in contains
    assert ("Widget", "count") not in case_of


# ── #4570: cross-file calls in VB.NET (Module members, typed locals, VB -> C#) ──
# Expected targets come from the compiler runs in /var/tmp/vbcases (dotnet sdk 8.0), not from guesses.
# HARD = any fix must pass. PROBE = records a limit or tells fixes apart.

def _project(tmp_path, files):
    paths = []
    for name, body in files.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
        paths.append(path)
    return sorted(paths)


def _extract_files(tmp_path, files):
    return extract(_project(tmp_path, files), cache_root=tmp_path)


def _node_id(result, label, filename):
    """The one node with this label (a leading `.` of C# methods ignored) in that file."""
    hits = [n["id"] for n in result["nodes"]
            if n["label"].lstrip(".") == label and str(n.get("source_file", "")).endswith(filename)]
    assert len(hits) == 1, f"{label!r} in {filename}: {hits}"
    return hits[0]


def _calls(result, caller, caller_file):
    """(label, file) of everything the caller has a `calls` edge to."""
    source = _node_id(result, caller, caller_file)
    by_id = {n["id"]: n for n in result["nodes"]}
    return {(by_id[e["target"]]["label"].lstrip("."), Path(str(by_id[e["target"]].get("source_file", ""))).name)
            for e in result["edges"] if e["relation"] == "calls" and e["source"] == source}


def _call_edges(result, caller, caller_file):
    source = _node_id(result, caller, caller_file)
    return [e for e in result["edges"] if e["relation"] == "calls" and e["source"] == source]


_MODULE = "Public Module Helpers\n Public Sub LogIt(msg As String)\n End Sub\nEnd Module\n"
_WORKER = "Public Class Worker\n Public Sub Save()\n End Sub\nEnd Class\n"


def _caller(body, members="", inherits=""):
    return f"Public Class Caller\n{inherits}{members} Public Sub Run()\n  {body}\n End Sub\nEnd Class\n"


# H1 (compiler: c01) -- an unqualified call reaches a Module Sub declared in another file
@_needs_vbnet
def test_an_unqualified_call_reaches_a_module_sub_in_another_file(tmp_path):
    result = _extract_files(tmp_path, {"Helpers.vb": _MODULE, "Caller.vb": _caller('LogIt("x")')})
    assert ("LogIt()", "Helpers.vb") in _calls(result, "Run()", "Caller.vb")


# H2 (compiler: c02c) -- a module-qualified call reaches the Module in another file
@_needs_vbnet
def test_a_module_qualified_call_reaches_a_module_sub_in_another_file(tmp_path):
    result = _extract_files(tmp_path, {"Helpers.vb": _MODULE, "Caller.vb": _caller('Helpers.LogIt("x")')})
    assert ("LogIt()", "Helpers.vb") in _calls(result, "Run()", "Caller.vb")


# H3 (compiler: c07a, c07b) -- a local typed in its declaration statement reaches the type's method
@_needs_vbnet
@pytest.mark.parametrize("declaration", ["Dim w As New Worker()", "Dim w As Worker = New Worker()"],
                         ids=["as_new", "as_t_equals_new"])
def test_a_call_through_a_local_typed_in_its_declaration_reaches_the_types_method(tmp_path, declaration):
    result = _extract_files(tmp_path, {"Worker.vb": _WORKER, "Caller.vb": _caller(f"{declaration}\n  w.Save()")})
    assert ("Save()", "Worker.vb") in _calls(result, "Run()", "Caller.vb")


# H4 (compiler: c09) -- a VB call to a C# static method reaches it
@_needs_vbnet
def test_a_vb_call_to_a_csharp_static_method_reaches_it(tmp_path):
    cs = "public static class CsRules {\n    public static bool IsLocked(int id) { return false; }\n}\n"
    result = _extract_files(tmp_path, {"CsRules.cs": cs, "Caller.vb": _caller("Dim b = CsRules.IsLocked(1)")})
    assert ("IsLocked()", "CsRules.cs") in _calls(result, "Run()", "Caller.vb")


# H5a (compiler: c03) -- the caller's own method wins over a Module's of the same signature
@_needs_vbnet
def test_the_callers_own_method_wins_over_a_module_method_of_the_same_name(tmp_path):
    own = " Public Sub LogIt(msg As String)\n End Sub\n"
    result = _extract_files(tmp_path, {"Helpers.vb": _MODULE, "Caller.vb": _caller('LogIt("x")', members=own)})
    assert _calls(result, "Run()", "Caller.vb") == {("LogIt()", "Caller.vb")}


# H5b (compiler: c04) -- a method inherited from a base class also wins over the Module
@_needs_vbnet
def test_an_inherited_method_is_never_replaced_by_a_module_method(tmp_path):
    base = "Public Class BaseC\n Public Sub LogIt(msg As String)\n End Sub\nEnd Class\n"
    result = _extract_files(tmp_path, {"Helpers.vb": _MODULE, "BaseC.vb": base,
                                       "Caller.vb": _caller('LogIt("x")', inherits=" Inherits BaseC\n")})
    assert ("LogIt()", "Helpers.vb") not in _calls(result, "Run()", "Caller.vb")


# H5c (compiler: c06a) -- a same-named method on the caller's class hides the Module's, whatever its arity
@_needs_vbnet
def test_a_same_named_method_on_the_callers_class_hides_the_module_method_whatever_its_arity(tmp_path):
    own = " Public Sub LogIt(msg As String, n As Integer)\n End Sub\n"
    result = _extract_files(tmp_path, {"Helpers.vb": _MODULE, "Caller.vb": _caller('LogIt("x")', members=own)})
    assert ("LogIt()", "Helpers.vb") not in _calls(result, "Run()", "Caller.vb")


# H6 (compiler: c05, c05b) -- two Modules with the same member name: ambiguous, so no edge to either
@_needs_vbnet
@pytest.mark.parametrize("second_signature", ["msg As String", "msg As String, n As Integer"], ids=["same_arity", "other_arity"])
def test_two_modules_declaring_the_same_name_give_no_edge_to_either(tmp_path, second_signature):
    second = f"Public Module Helpers2\n Public Sub LogIt({second_signature})\n End Sub\nEnd Module\n"
    result = _extract_files(tmp_path, {"Helpers.vb": _MODULE, "Helpers2.vb": second, "Caller.vb": _caller('LogIt("x")')})
    assert _calls(result, "Run()", "Caller.vb") == set()


# H7 -- a receiver without a declared type (late bound) gets no edge to a random same-named method
@_needs_vbnet
def test_a_call_through_an_object_typed_receiver_binds_to_no_method(tmp_path):
    decoy = "Public Class Decoy\n Public Sub Save()\n End Sub\nEnd Class\n"
    body = "Dim o As Object = New Worker()\n  o.Save()"
    result = _extract_files(tmp_path, {"Worker.vb": _WORKER, "Decoy.vb": decoy, "Caller.vb": _caller(body)})
    assert _calls(result, "Run()", "Caller.vb") == set()


# H8 -- a VB call never binds to a same-named function in a file of another language
@_needs_vbnet
def test_a_vb_call_never_binds_to_a_same_named_python_function(tmp_path):
    py = "def LogIt(msg):\n    pass\n\n\ndef logit(msg):\n    pass\n"
    result = _extract_files(tmp_path, {"helpers.py": py, "Caller.vb": _caller('LogIt("x")\n  logit("x")')})
    assert not {c for c in _calls(result, "Run()", "Caller.vb") if c[1].endswith(".py")}


# H9 (compiler: c01b) -- VB is case-insensitive: every spelling of the call binds to the Module's LogIt
@_needs_vbnet
def test_the_case_of_a_call_does_not_change_what_it_binds_to(tmp_path):
    for spelling in ("LogIt", "logit", "LOGIT"):
        sub = tmp_path / spelling
        sub.mkdir()
        result = _extract_files(sub, {"Helpers.vb": _MODULE, "Caller.vb": _caller(f'{spelling}("x")')})
        assert ("LogIt()", "Helpers.vb") in _calls(result, "Run()", "Caller.vb"), spelling


# H10 -- same-file calls and partial-class calls are unchanged
@_needs_vbnet
def test_same_file_and_partial_class_calls_keep_their_edges_and_evidence(tmp_path):
    same_file = (" Public Sub A_SameFileSelf()\n  B_Target()\n End Sub\n"
                 " Public Sub B_Target()\n End Sub\n")
    first = "Public Partial Class Counter\n Public Sub Run()\n  Helper()\n End Sub\nEnd Class\n"
    second = "Partial Public Class Counter\n Private Sub Helper()\n End Sub\nEnd Class\n"
    result = _extract_files(tmp_path, {"Caller.vb": f"Public Class Caller\n{same_file}End Class\n",
                                       "Counter.vb": first, "Counter.Designer.vb": second})
    (same,) = _call_edges(result, "A_SameFileSelf()", "Caller.vb")
    assert (same["confidence"], same.get("context")) == ("EXTRACTED", None)
    (partial,) = _call_edges(result, "Run()", "Counter.vb")
    assert (partial["confidence"], partial["context"]) == ("EXTRACTED", "partial_type_call")
    assert _calls(result, "Run()", "Counter.vb") == {("Helper()", "Counter.Designer.vb")}


# H11 -- C# -> VB (case G of the issue) keeps resolving
@_needs_vbnet
def test_a_csharp_call_to_a_vb_module_function_keeps_its_edge(tmp_path):
    cs = 'public class CsCaller {\n    public void G_CsToVb() { Helpers.LogIt("x"); }\n}\n'
    result = _extract_files(tmp_path, {"Helpers.vb": _MODULE, "CsCaller.cs": cs})
    (edge,) = _call_edges(result, "G_CsToVb()", "CsCaller.cs")
    assert _node_id(result, "LogIt()", "Helpers.vb") == edge["target"]
    assert edge["confidence"] == "EXTRACTED"


# H12 (added; compiler: c02a) -- a Module in a namespace that is not imported is not in scope
@_needs_vbnet
def test_an_unqualified_call_does_not_reach_a_module_in_a_namespace_that_is_not_imported(tmp_path):
    module = "Namespace Acme\n" + _MODULE + "End Namespace\n"
    result = _extract_files(tmp_path, {"Helpers.vb": module, "Caller.vb": _caller('LogIt("x")')})
    assert _calls(result, "Run()", "Caller.vb") == set()


# H13 (added) -- an unqualified call never binds to a same-named method of an unrelated class, VB or C#
@_needs_vbnet
@pytest.mark.parametrize("name,body", [
    ("Worker.vb", _WORKER),
    ("CsWorker.cs", "public class CsWorker {\n    public void Save() { }\n}\n"),
], ids=["vb_class", "csharp_class"])
def test_an_unqualified_call_never_binds_to_a_method_of_an_unrelated_class(tmp_path, name, body):
    result = _extract_files(tmp_path, {name: body, "Caller.vb": _caller("Save()")})
    assert _calls(result, "Run()", "Caller.vb") == set()


# H14 (added; compiler: c06b, c06c) -- a field or a nested type named like the Module shadows it
@_needs_vbnet
def test_a_field_named_like_the_module_hides_it(tmp_path):
    result = _extract_files(tmp_path, {"Helpers.vb": _MODULE,
                                       "Caller.vb": _caller('Helpers.LogIt("x")', members=" Private Helpers As Integer\n")})
    assert ("LogIt()", "Helpers.vb") not in _calls(result, "Run()", "Caller.vb")


@_needs_vbnet
def test_a_nested_class_named_like_the_module_hides_it(tmp_path):
    nested = " Public Class Helpers\n  Public Shared Sub LogIt(msg As String)\n  End Sub\n End Class\n"
    result = _extract_files(tmp_path, {"Helpers.vb": _MODULE, "Caller.vb": _caller('Helpers.LogIt("x")', members=nested)})
    assert ("LogIt()", "Helpers.vb") not in _calls(result, "Run()", "Caller.vb")


# P1 (compiler: c07c) -- an inferred local: `Dim w = New Worker()`
@_needs_vbnet
def test_probe_a_call_through_an_inferred_local_reaches_the_types_method(tmp_path):
    result = _extract_files(tmp_path, {"Worker.vb": _WORKER, "Caller.vb": _caller("Dim w = New Worker()\n  w.Save()")})
    assert ("Save()", "Worker.vb") in _calls(result, "Run()", "Caller.vb")


# P2 (compiler: c08a, c08b) -- a field or a parameter typed As Worker
@_needs_vbnet
@pytest.mark.parametrize("caller_source", [
    pytest.param(
        _caller("_w = New Worker()\n  _w.Save()", members=" Private _w As Worker\n"),
        id="field",
        marks=pytest.mark.xfail(strict=True, reason="limitation: field-typed receivers are not tracked"),
    ),
    pytest.param(
        "Public Class Caller\n Public Sub Run(x As Worker)\n  x.Save()\n End Sub\nEnd Class\n",
        id="parameter",
    ),
])
def test_probe_a_call_through_a_field_or_parameter_typed_as_the_class_reaches_its_method(tmp_path, caller_source):
    result = _extract_files(tmp_path, {"Worker.vb": _WORKER, "Caller.vb": caller_source})
    assert ("Save()", "Worker.vb") in _calls(result, "Run()", "Caller.vb")


# P3 (compiler: c02b) -- a Module in another namespace reached through Imports
@_needs_vbnet
def test_probe_an_unqualified_call_reaches_a_module_in_an_imported_namespace(tmp_path):
    module = "Namespace Acme\n" + _MODULE + "End Namespace\n"
    result = _extract_files(tmp_path, {"Helpers.vb": module, "Caller.vb": "Imports Acme\n" + _caller('LogIt("x")')})
    assert ("LogIt()", "Helpers.vb") in _calls(result, "Run()", "Caller.vb")


# P3b (added; compiler: c02d) -- a Module in an enclosing namespace needs no Imports
@_needs_vbnet
def test_probe_an_unqualified_call_reaches_a_module_in_an_enclosing_namespace(tmp_path):
    module = "Namespace Acme\n" + _MODULE + "End Namespace\n"
    caller_source = "Namespace Acme.Sub1\n" + _caller('LogIt("x")') + "End Namespace\n"
    result = _extract_files(tmp_path, {"Helpers.vb": module, "Caller.vb": caller_source})
    assert ("LogIt()", "Helpers.vb") in _calls(result, "Run()", "Caller.vb")


# P4 -- the evidence level each form is given. Records what is produced; only the vocabulary is asserted.
@_needs_vbnet
@pytest.mark.parametrize("form", ["unqualified_module", "module_qualified", "typed_local", "csharp_static"])
def test_probe_edge_confidence_of_each_cross_file_form(tmp_path, form):
    cases = {
        "unqualified_module": ({"Helpers.vb": _MODULE, "Caller.vb": _caller('LogIt("x")')}, "LogIt()"),
        "module_qualified": ({"Helpers.vb": _MODULE, "Caller.vb": _caller('Helpers.LogIt("x")')}, "LogIt()"),
        "typed_local": ({"Worker.vb": _WORKER, "Caller.vb": _caller("Dim w As New Worker()\n  w.Save()")}, "Save()"),
        "csharp_static": ({"CsRules.cs": "public static class CsRules { public static bool IsLocked(int id) { return false; } }\n",
                           "Caller.vb": _caller("Dim b = CsRules.IsLocked(1)")}, "IsLocked()"),
    }
    files, callee = cases[form]
    result = _extract_files(tmp_path, files)
    edges = [e for e in _call_edges(result, "Run()", "Caller.vb")
             if next(n for n in result["nodes"] if n["id"] == e["target"])["label"].lstrip(".") == callee]
    assert len(edges) == 1, "no edge to measure"
    print(f"P4 {form}: confidence={edges[0]['confidence']} score={edges[0].get('confidence_score')} context={edges[0].get('context')}")
    assert edges[0]["confidence"] in {"EXTRACTED", "INFERRED"}


# P5 (added) -- a C# call to an overloaded VB Module Sub reaches the overload with the call's arity
@_needs_vbnet
def test_probe_a_csharp_call_to_an_overloaded_vb_module_sub_reaches_the_overload_with_its_arity(tmp_path):
    module = ("Public Module Helpers\n Public Sub LogIt(a As String)\n End Sub\n"
              " Public Sub LogIt(a As String, n As Integer)\n End Sub\nEnd Module\n")
    cs = 'public class CsCaller {\n    public void M() { Helpers.LogIt("x"); }\n}\n'
    result = _extract_files(tmp_path, {"Helpers.vb": module, "CsCaller.cs": cs})
    (edge,) = _call_edges(result, "M()", "CsCaller.cs")
    target = next(n for n in result["nodes"] if n["id"] == edge["target"])
    assert target["metadata"]["arity"] == 1


# P6 (added; compiler: c06c) -- the nested class is the target. v8 does not extract nested VB types at all.
@_needs_vbnet
@pytest.mark.xfail(strict=True, reason="separate bug: nested VB types are not extracted")
def test_probe_a_qualified_call_reaches_a_nested_class_named_like_the_module(tmp_path):
    nested = " Public Class Helpers\n  Public Shared Sub LogIt(msg As String)\n  End Sub\n End Class\n"
    result = _extract_files(tmp_path, {"Helpers.vb": _MODULE, "Caller.vb": _caller('Helpers.LogIt("x")', members=nested)})
    assert _calls(result, "Run()", "Caller.vb") == {("LogIt()", "Caller.vb")}


# P7 (compiler: c04) -- an unqualified call reaches the method the caller inherits from a base class in another file
@_needs_vbnet
def test_probe_an_unqualified_call_reaches_the_method_inherited_from_a_base_class(tmp_path):
    base = "Public Class BaseC\n Public Sub LogIt(msg As String)\n End Sub\nEnd Class\n"
    result = _extract_files(tmp_path, {"Helpers.vb": _MODULE, "BaseC.vb": base,
                                       "Caller.vb": _caller('LogIt("x")', inherits=" Inherits BaseC\n")})
    assert _calls(result, "Run()", "Caller.vb") == {("LogIt()", "BaseC.vb")}


# P8 (compiler: c11) -- VB is case-insensitive on the C# side too: `csrules.islocked(1)` compiles and binds
@_needs_vbnet
def test_probe_a_lowercase_vb_call_reaches_a_csharp_static_method(tmp_path):
    cs = "public static class CsRules {\n    public static bool IsLocked(int id) { return false; }\n}\n"
    result = _extract_files(tmp_path, {"CsRules.cs": cs, "Caller.vb": _caller("Dim b = csrules.islocked(1)")})
    assert ("IsLocked()", "CsRules.cs") in _calls(result, "Run()", "Caller.vb")


# H15 (compiler: c10) -- `Helpers` is declared by two Modules in two namespaces and the caller imports neither:
# the name is not declared, so the call binds to no Module
@_needs_vbnet
def test_a_module_name_declared_in_two_unimported_namespaces_binds_to_neither(tmp_path):
    first = "Namespace NsA\n" + _MODULE + "End Namespace\n"
    second = "Namespace NsB\n" + _MODULE + "End Namespace\n"
    result = _extract_files(tmp_path, {"HelpersA.vb": first, "HelpersB.vb": second, "Caller.vb": _caller('Helpers.LogIt("x")')})
    assert _calls(result, "Run()", "Caller.vb") == set()


# H16 (#2406) -- rebuilding only the changed caller still binds its call into the unchanged Module file
@_needs_vbnet
def test_an_incremental_rebuild_of_only_the_caller_keeps_its_call_into_an_unchanged_module(tmp_path):
    import json

    from graphify.watch import _rebuild_code

    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "Helpers.vb").write_text(_MODULE, encoding="utf-8")
    caller = corpus / "Caller.vb"
    caller.write_text(_caller('LogIt("x")'), encoding="utf-8")
    assert _rebuild_code(corpus, no_cluster=True, acquire_lock=False) is True
    caller.write_text(_caller('LogIt("x")', members=" Public Sub Other()\n End Sub\n"), encoding="utf-8")
    assert _rebuild_code(corpus, changed_paths=[caller], no_cluster=True, acquire_lock=False) is True

    graph = json.loads((corpus / "graphify-out" / "graph.json").read_text(encoding="utf-8"))
    by_id = {n["id"]: n for n in graph["nodes"]}
    called = {(by_id[e["target"]]["label"], by_id[e["target"]].get("source_file"))
              for e in graph["links"]
              if e["relation"] == "calls" and by_id[e["source"]]["label"] == "Run()"}
    assert ("LogIt()", "Helpers.vb") in called


# Cache (#4570): VB raw calls changed shape, so entries written before are not served.
@_needs_vbnet
def test_a_cache_entry_from_before_cross_file_vb_calls_is_not_served(tmp_path, monkeypatch):
    import graphify.cache as cache_mod
    from graphify.cache import save_cached

    path = tmp_path / "Caller.vb"
    path.write_text(_caller('LogIt("x")'), encoding="utf-8")
    current = cache_mod._AST_CACHE_SCHEMA
    monkeypatch.setattr(cache_mod, "_AST_CACHE_SCHEMA", 20)  # the schema before this fix (v8, 0.9.93)
    stale = {"nodes": [{"id": "stale_sentinel", "label": "STALE", "file_type": "code",
                        "source_file": str(path), "source_location": "L1"}], "edges": [], "raw_calls": []}
    save_cached(path, stale, tmp_path, cache_root=tmp_path)
    monkeypatch.setattr(cache_mod, "_AST_CACHE_SCHEMA", current)
    result = extract([path], cache_root=tmp_path)
    assert "stale_sentinel" not in {n["id"] for n in result["nodes"]}


# H17 (#4570) -- a class whose base leaves the corpus (a Form, a Page) may inherit a member of that name:
# the Module call is still made, but as INFERRED with that reason
@_needs_vbnet
@pytest.mark.parametrize("call", ['LogIt("x")', 'Helpers.LogIt("x")'], ids=["unqualified", "qualified"])
def test_a_call_from_a_class_with_an_external_base_reaches_the_module_as_inferred(tmp_path, call):
    caller = _caller(call, inherits=" Inherits System.Windows.Forms.Form\n")
    result = _extract_files(tmp_path, {"Helpers.vb": _MODULE, "Caller.vb": caller})
    edges = _call_edges(result, "Run()", "Caller.vb")
    assert len(edges) == 1
    assert edges[0]["target"] == _node_id(result, "LogIt()", "Helpers.vb")
    assert (edges[0]["confidence"], edges[0]["confidence_score"], edges[0]["context"]) == (
        "INFERRED", 0.85, "external_base_may_hide")


# H18 (compiler: c12) -- `.Save()` inside `With w` calls w's Save, not the caller's own Save
@_needs_vbnet
def test_a_member_call_inside_a_with_block_is_not_a_call_on_the_callers_own_type(tmp_path):
    own = " Public Sub Save()\n End Sub\n"
    body = "Dim w As New Worker()\n  With w\n   .Save()\n  End With"
    result = _extract_files(tmp_path, {"Worker.vb": _WORKER, "Caller.vb": _caller(body, members=own)})
    assert ("Save()", "Caller.vb") not in _calls(result, "Run()", "Caller.vb")


# H19 (compiler: c13) -- a local delegate hides a method of the same name: `handler(1)` invokes the local
@_needs_vbnet
def test_a_call_of_a_local_delegate_is_not_a_call_of_a_same_named_method(tmp_path):
    own = " Public Sub handler(x As Integer)\n End Sub\n"
    body = "Dim handler As Action(Of Integer) = Sub(i As Integer) Console.WriteLine(i)\n  handler(1)"
    result = _extract_files(tmp_path, {"Caller.vb": _caller(body, members=own)})
    assert _calls(result, "Run()", "Caller.vb") == set()


# H20 (compiler: c14a, c14b, c14c) -- a property, field or delegate field named like the Module's Sub hides it
@_needs_vbnet
@pytest.mark.parametrize("member", [
    " Public Property LogIt As String\n",
    " Private LogIt As String\n",
    " Private LogIt As Action(Of String)\n",
], ids=["property", "field", "delegate_field"])
def test_a_property_or_field_named_like_a_module_sub_hides_it(tmp_path, member):
    result = _extract_files(tmp_path, {"Helpers.vb": _MODULE, "Caller.vb": _caller('LogIt("x")', members=member)})
    assert ("LogIt()", "Helpers.vb") not in _calls(result, "Run()", "Caller.vb")


# P9 (compiler: c12) -- `.Save()` inside `With w` reaches w's class
@_needs_vbnet
@pytest.mark.xfail(strict=True, reason="limitation: With-block targets are not tracked")
def test_probe_a_member_call_inside_a_with_block_reaches_the_with_objects_method(tmp_path):
    body = "Dim w As New Worker()\n  With w\n   .Save()\n  End With"
    result = _extract_files(tmp_path, {"Worker.vb": _WORKER, "Caller.vb": _caller(body)})
    assert ("Save()", "Worker.vb") in _calls(result, "Run()", "Caller.vb")


from graphify.build import build_from_json


def _graph_calls(result, caller, caller_file):
    """(label, file) of everything the caller calls in the BUILT graph: build.py's
    cross-language phantom filter runs there, not in extract."""
    graph = build_from_json(result)
    source = _node_id(result, caller, caller_file)
    return {(graph.nodes[t]["label"].lstrip("."), Path(str(graph.nodes[t].get("source_file", ""))).name)
            for s, t, d in graph.edges(source, data=True)
            if d.get("relation") == "calls" and source in (s, t) and t != source}


_CS_RULES = ("namespace Acme.Rules {\n"
             "    public static class NsRules { public static bool Check(int x) { return x > 0; } }\n"
             "    public class Inst { public void Run() { } }\n"
             "}\n")


# H19 (#4570 review) -- an INFERRED VB -> C# call survives the cross-language phantom filter
@_needs_vbnet
@pytest.mark.parametrize("body, inherits, callee", [
    ("Acme.Rules.NsRules.Check(1)", " Inherits System.Windows.Forms.Form\n", "Check()"),
    ("Dim r As New Acme.Rules.Inst()\n  r.Run()", "", "Run()"),
], ids=["external_base", "typed_local"])
def test_an_inferred_vb_call_into_csharp_is_kept_in_the_built_graph(tmp_path, body, inherits, callee):
    result = _extract_files(tmp_path, {"NsRules.cs": _CS_RULES, "Caller.vb": _caller(body, inherits=inherits)})
    assert (callee, "NsRules.cs") in _graph_calls(result, "Run()", "Caller.vb")


# H20 (#4570 review) -- C# cannot call a VB Module member by its bare name: the shared
# name pass still matches it, and the filter must still drop that edge
@_needs_vbnet
def test_a_csharp_bare_name_never_reaches_a_vb_module_member_in_the_built_graph(tmp_path):
    cs = 'public class CsCaller {\n    public void P_CsBare() { LogIt("x"); }\n}\n'
    result = _extract_files(tmp_path, {"Helpers.vb": _MODULE, "CsCaller.cs": cs})
    assert ("LogIt()", "Helpers.vb") not in _graph_calls(result, "P_CsBare()", "CsCaller.cs")
