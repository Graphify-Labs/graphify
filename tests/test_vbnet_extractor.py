"""Extraction coverage for vbnet."""


from __future__ import annotations





import importlib.util as _ilu
import sys


from pathlib import Path





import pytest

from graphify.extract import extract
from graphify.validate import validate_extraction

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
def test_vbnet_imported_namespaces_are_valid_global_stubs(tmp_path):
    source = tmp_path / "Caller.vb"
    source.write_text(
        "Imports System.Collections.Generic\n"
        "Public Class Caller\n"
        " Inherits ExternalBase\n"
        " Public Function Run() As String\n"
        '  Return "x"\n'
        " End Function\n"
        "End Class\n",
        encoding="utf-8",
    )
    other = tmp_path / "Other.vb"
    other.write_text(
        "Imports System.Collections.Generic\n"
        "Public Class Other\n"
        " Inherits ExternalBase\n"
        "End Class\n",
        encoding="utf-8",
    )

    result = extract([source, other], cache_root=tmp_path)

    namespaces = [
        node for node in result["nodes"] if node["label"] == "System.Collections.Generic"
    ]
    assert len({node["id"] for node in namespaces}) == 1
    assert {node["source_file"] for node in namespaces} == {""}
    assert {node["source_location"] for node in namespaces} == {""}
    imports = [edge for edge in result["edges"] if edge["relation"] == "imports"]
    assert {edge["source_file"] for edge in imports} == {source.name, other.name}
    assert {edge["target"] for edge in imports} == {namespaces[0]["id"]}

    external_types = [
        node for node in result["nodes"] if node["label"] == "ExternalBase"
    ]
    assert len({node["id"] for node in external_types}) == 1
    assert {node["source_file"] for node in external_types} == {""}
    assert {node["source_location"] for node in external_types} == {""}
    inherits = [edge for edge in result["edges"] if edge["relation"] == "inherits"]
    assert {edge["target"] for edge in inherits} == {external_types[0]["id"]}

    assert validate_extraction(result) == []


@_needs_vbnet
def test_vbnet_pre_fix_ast_cache_is_not_served(tmp_path, monkeypatch):
    import graphify.cache as cache_mod
    from graphify.cache import save_cached
    from graphify.extract import cache_salt
    from graphify.extractors.vbnet import extract_vbnet

    source = tmp_path / "Caller.vb"
    source.write_text(
        "Imports System.Text\nPublic Class Caller\nEnd Class\n",
        encoding="utf-8",
    )
    current_schema = cache_mod._AST_CACHE_SCHEMA
    monkeypatch.setattr(cache_mod, "_AST_CACHE_SCHEMA", 25)
    monkeypatch.setattr(cache_mod, "_cleaned_ast_dirs", set())
    stale = extract_vbnet(source)
    for node in stale["nodes"]:
        if node.get("metadata", {}).get("kind") == "external_namespace":
            node.pop("source_file", None)
            node.pop("source_location", None)
    save_cached(
        source,
        stale,
        root=tmp_path,
        cache_root=tmp_path,
        kind="ast",
        salt=cache_salt(source),
    )

    monkeypatch.setattr(cache_mod, "_AST_CACHE_SCHEMA", current_schema)
    monkeypatch.setattr(cache_mod, "_cleaned_ast_dirs", set())
    result = extract(
        [source], root=tmp_path, cache_root=tmp_path, parallel=False
    )

    assert validate_extraction(result) == []
    namespace = next(node for node in result["nodes"] if node["label"] == "System.Text")
    assert namespace["source_file"] == ""
    assert namespace["source_location"] == ""


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


@_needs_vbnet
def test_vbnet_operator_declaration_gets_a_node_and_its_calls_resolve(tmp_path):
    """An `Operator` declaration is a member form the extractor's member loop
    never recognized at all -- it checked only for `method_declaration` and
    `constructor_declaration`, so a class that overloads an operator lost the
    operator entirely: no node, no `method` edge from the class, and since its
    body was never walked either, a call made from inside it (a common shape,
    delegating to a named helper) vanished with no edge and no raw_call."""
    source = tmp_path / "Vector.vb"
    source.write_text(
        "Public Class Vector\n"
        "  Public Shared Operator +(a As Vector, b As Vector) As Vector\n"
        "    Return BuildSum(a, b)\n"
        "  End Operator\n"
        "  Public Shared Function BuildSum(a As Vector, b As Vector) As Vector\n"
        "    Return New Vector()\n"
        "  End Function\n"
        "End Class\n",
        encoding="utf-8",
    )

    result = extract([source], cache_root=tmp_path)

    labels = {node["label"] for node in result["nodes"]}
    assert "+()" in labels
    assert ("Vector", "+()") in _edge_labels(result, "method")
    assert ("+()", "BuildSum()") in _edge_labels(result, "calls")


@_needs_vbnet
def test_vbnet_a_class_with_no_operator_is_unaffected(tmp_path):
    """Control: a plain class with only Sub/Function members keeps resolving
    exactly as before the operator fix."""
    source = tmp_path / "Plain.vb"
    source.write_text(
        "Public Class Plain\n"
        "  Public Sub Run()\n"
        "   Helper()\n"
        "  End Sub\n"
        "  Private Sub Helper()\n"
        "  End Sub\n"
        "End Class\n",
        encoding="utf-8",
    )

    result = extract([source], cache_root=tmp_path)

    labels = {node["label"] for node in result["nodes"]}
    assert {"Plain", "Run()", "Helper()"} <= labels
    assert ("Run()", "Helper()") in _edge_labels(result, "calls")
