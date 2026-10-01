"""Extraction coverage for vbnet."""


from __future__ import annotations





import sys


from pathlib import Path





from graphify.extract import extract





FIXTURE = Path(__file__).parent / "fixtures" / "new_languages" / "sample.vb"





def _edge_labels(result: dict, relation: str) -> set[tuple[str, str]]:
    labels = {node["id"]: node["label"] for node in result["nodes"]}
    return {
        (labels.get(edge["source"], edge["source"]), labels.get(edge["target"], edge["target"]))
        for edge in result["edges"]
        if edge["relation"] == relation
    }


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


def test_vbnet_fixture_uses_normal_extract_path(tmp_path):
    result = extract([FIXTURE], cache_root=tmp_path)

    labels = {node["label"] for node in result["nodes"]}
    assert {'Helper()', 'Fixtures', 'Run()', 'Sample'} <= labels
    assert ('Run()', 'Helper()') in _edge_labels(result, "calls")


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
