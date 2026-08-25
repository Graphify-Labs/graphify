from pathlib import Path
import builtins
import importlib.util
import sys
from types import SimpleNamespace

import pytest

from graphify.detect import CODE_EXTENSIONS, FileType, classify_file
from graphify.extract import _get_extractor, extract
from graphify.al_resolution import _same_source, _unique_member_id
from graphify.extractors.al import (
    _extract_al_fallback,
    _mask_al_comments_and_strings,
    _matching_brace,
    extract_al,
)


def test_al_extension_is_detected_case_insensitively():
    assert ".al" in CODE_EXTENSIONS
    assert classify_file(Path("Comment.Codeunit.al")) == FileType.CODE
    assert classify_file(Path("Comment.Codeunit.AL")) == FileType.CODE


def test_al_extension_dispatches_to_al_extractor():
    assert _get_extractor(Path("Comment.Codeunit.al")) is extract_al
    assert _get_extractor(Path("Comment.Codeunit.AL")) is extract_al


def test_al_source_matching_uses_complete_path_components():
    assert _same_source("app/foo.al", "C:/repo/app/foo.al")
    assert _same_source("APP\\FOO.AL", "c:/repo/app/foo.al")
    assert not _same_source("app/foo.al", "C:/repo/myapp/foo.al")
    assert not _same_source("foo.al", "C:/repo/notfoo.al")


def test_al_unique_member_id_deduplicates_string_ids_without_selecting_ambiguity():
    assert _unique_member_id(["member", "member"]) == "member"
    assert _unique_member_id(["first", "second"]) is None
    assert _unique_member_id([]) is None


def test_al_mask_preserves_offsets_and_newlines_across_lexical_states():
    source = "code // comment\nnext /* block\ncomment */ more 'it''s' end"

    masked = _mask_al_comments_and_strings(source)

    assert len(masked) == len(source)
    assert [index for index, char in enumerate(masked) if char == "\n"] == [
        index for index, char in enumerate(source) if char == "\n"
    ]
    assert masked.replace(" ", "") == "code\nnext\nmoreend"


def test_al_mask_preserves_comment_markers_inside_quoted_identifiers():
    source = (
        'codeunit 1 "Name // Part" { } // comment\n'
        'codeunit 2 "Name /* Part" { }\n'
        'codeunit 3 "A""//""B" { }\n'
    )

    masked = _mask_al_comments_and_strings(source)

    assert '"Name // Part"' in masked
    assert '"Name /* Part"' in masked
    assert '"A""//""B"' in masked
    assert "// comment" not in masked


def test_al_mask_preserves_every_quoted_identifier_character():
    identifiers = ['"Name // Part"', '"Name /* Part"', '"A""//""B"']
    source = " ".join(identifiers) + " // trailing comment"

    masked = _mask_al_comments_and_strings(source)

    for identifier in identifiers:
        start = source.index(identifier)
        assert masked[start:start + len(identifier)] == identifier


def test_al_fallback_preserves_comment_markers_inside_quoted_identifiers():
    result = _extract_al_fallback(
        Path("quoted.al"),
        'codeunit 1 "Name // Part" '
        '{ procedure "Run /* Now"() begin end; }',
    )

    labels = {node["label"] for node in result["nodes"]}

    assert "Name // Part" in labels
    assert "Run /* Now()" in labels


def test_al_matching_brace_uses_masked_comments_and_strings():
    source = "{ value := '{'; /* } */ nested { } } trailing"
    masked = _mask_al_comments_and_strings(source)

    closing = _matching_brace(masked, 0)

    assert closing == source.index("} trailing")


def test_al_missing_parser_reports_optional_extra(tmp_path, capsys, monkeypatch):
    monkeypatch.setitem(sys.modules, "tree_sitter_al", None)
    source = tmp_path / "Comment.Codeunit.al"
    source.write_text('codeunit 75000 "Comment Mgt." { }', encoding="utf-8")

    result = extract([source], cache_root=tmp_path)
    err = capsys.readouterr().err

    assert "used fallback extraction" in err
    assert "tree_sitter_al not installed" in err
    # The published distribution is intentionally named graphifyy.
    assert 'graphifyy[al]' in err
    assert result["failed_sources"] == []
    assert any(node.get("object_kind") == "codeunit" for node in result["nodes"])


def test_al_missing_tree_sitter_core_uses_fallback(tmp_path, monkeypatch):
    source = tmp_path / "Comment.Codeunit.al"
    source.write_text('codeunit 75000 "Comment Mgt." { }', encoding="utf-8")
    original_import = builtins.__import__

    def broken_import(name, *args, **kwargs):
        if name == "tree_sitter":
            raise ImportError("core unavailable")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", broken_import)

    result = extract_al(source)

    assert "tree_sitter failed to load" in result.get("dependency_warning", "")
    assert any(node.get("object_kind") == "codeunit" for node in result["nodes"])


def test_al_parser_load_failure_uses_fallback(tmp_path, monkeypatch):
    source = tmp_path / "Comment.Codeunit.al"
    source.write_text('codeunit 75000 "Comment Mgt." { }', encoding="utf-8")
    original_import = builtins.__import__
    original_find_spec = importlib.util.find_spec

    def broken_import(name, *args, **kwargs):
        if name == "tree_sitter_al":
            raise ImportError("incompatible AL parser binary")
        return original_import(name, *args, **kwargs)

    def installed_spec(name, *args, **kwargs):
        if name == "tree_sitter_al":
            return object()
        return original_find_spec(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", broken_import)
    monkeypatch.setattr(importlib.util, "find_spec", installed_spec)

    result = extract_al(source)
    warning = result.get("dependency_warning") or ""
    assert "tree_sitter_al failed to load" in warning
    assert "incompatible AL parser binary" in warning
    assert not result.get("error")
    assert any(node.get("object_kind") == "codeunit" for node in result["nodes"])


def test_al_parser_initialization_failure_uses_fallback(tmp_path, monkeypatch):
    source = tmp_path / "Comment.Codeunit.al"
    source.write_text('codeunit 75000 "Comment Mgt." { }', encoding="utf-8")

    class BrokenLanguage:
        def __init__(self, *_args, **_kwargs):
            raise TypeError("incompatible language capsule")

    monkeypatch.setitem(
        sys.modules,
        "tree_sitter",
        SimpleNamespace(Language=BrokenLanguage, Parser=object),
    )
    monkeypatch.setitem(
        sys.modules,
        "tree_sitter_al",
        SimpleNamespace(language=lambda: object()),
    )

    result = extract_al(source)

    assert "failed to initialize" in result.get("dependency_warning", "")
    assert not result.get("error")
    assert any(node.get("object_kind") == "codeunit" for node in result["nodes"])


def test_al_fallback_extracts_objects_procedures_and_triggers(monkeypatch):
    monkeypatch.setitem(sys.modules, "tree_sitter_al", None)
    fixture = Path(__file__).parent / "fixtures" / "sample.al"

    result = extract_al(fixture)
    labels = {node["label"] for node in result["nodes"]}
    objects = {node["label"]: node for node in result["nodes"] if node.get("object_kind")}

    assert {"Comment Entry", "Customer Comments"} <= labels
    assert {"OnInsert()", "Initialize()", "AddComment()"} <= labels
    assert objects["Comment Entry"]["object_id"] == "75000"
    assert objects["Comment Entry"]["qualified_name"] == "Acme.Comments.Comment Entry"
    assert objects["Customer Comments"]["object_kind"] == "tableextension"
    assert all(node.get("extraction_tier") == "fallback" for node in result["nodes"])
    assert {edge["relation"] for edge in result["edges"]} == {"contains"}


def test_al_fallback_extracts_permission_sets():
    result = _extract_al_fallback(
        Path("Sample.permissionset.al"),
        'permissionset 70000 "Sample Admin"\n{\n}\n',
    )

    permission_set = next(
        node for node in result["nodes"] if node.get("object_kind") == "permissionset"
    )
    assert permission_set["label"] == "Sample Admin"
    assert permission_set["object_id"] == "70000"


def test_al_fallback_extracts_permission_set_extensions():
    result = _extract_al_fallback(
        Path("Sample.permissionsetextension.al"),
        'permissionsetextension 70001 "Extra Sample Rights" '
        'extends "Sample Rights"\n{\n}\n',
    )

    extension = next(
        node
        for node in result["nodes"]
        if node.get("object_kind") == "permissionsetextension"
    )
    assert extension["label"] == "Extra Sample Rights"
    assert extension["object_id"] == "70001"


def test_al_fallback_extracts_controladdins():
    result = _extract_al_fallback(
        Path("Sample.ControlAddin.al"),
        "controladdin SampleControl\n"
        "{\n"
        "    procedure Run(Value: Text);\n"
        "}\n",
    )

    controladdin = next(
        node for node in result["nodes"]
        if node.get("object_kind") == "controladdin"
    )

    assert controladdin["label"] == "SampleControl"
    assert "Run()" in {node["label"] for node in result["nodes"]}


def test_al_fallback_preserves_spelling_and_casefolds_lookup(monkeypatch, tmp_path):
    monkeypatch.setitem(sys.modules, "tree_sitter_al", None)
    source = tmp_path / "Mixed.AL"
    source.write_text(
        'codeunit 75002 "Mixed ""Case""" { local procedure DoWork() begin end; }',
        encoding="utf-8",
    )

    result = extract_al(source)
    object_node = next(node for node in result["nodes"] if node.get("object_kind"))
    callable_node = next(node for node in result["nodes"] if node.get("member_kind"))

    assert object_node["label"] == 'Mixed "Case"'
    assert object_node["lookup_key"] == 'mixed "case"'
    assert callable_node["label"] == "DoWork()"
    assert callable_node["lookup_key"] == "dowork"


def test_al_fallback_accepts_utf8_bom(monkeypatch, tmp_path):
    monkeypatch.setitem(sys.modules, "tree_sitter_al", None)
    source = tmp_path / "Bom.Codeunit.al"
    source.write_text(
        '\ufeffcodeunit 70220 "Posting Sample"\n'
        "{\n"
        "    procedure Execute()\n"
        "    begin\n"
        "    end;\n"
        "}\n",
        encoding="utf-8",
    )

    result = extract_al(source)
    labels = {node["label"] for node in result["nodes"]}

    assert "Posting Sample" in labels
    assert "Execute()" in labels


def test_al_fallback_preserves_quoted_special_identifiers(monkeypatch):
    monkeypatch.setitem(sys.modules, "tree_sitter_al", None)
    fixture = Path(__file__).parent / "fixtures" / "special_identifiers.al"

    result = extract_al(fixture)
    labels = {node["label"] for node in result["nodes"]}

    assert "Übernahme-Plan (Nord & Süd)" in labels
    assert "Planübersicht (Täglich)" in labels
    assert "Setze Prüfstatus()" in labels
    assert "Prüfe & Starte (Auswahl)()" in labels
    assert "Prüfliste (Regionen)" in labels
    assert "Sammle Ergebnis()" in labels
    assert len([node for node in result["nodes"] if node["label"] == "OnAction()"]) == 2
    assert len(
        [node for node in result["nodes"] if node["label"] == "OnAfterGetRecord()"]
    ) == 2


def test_al_fallback_preserves_duplicate_triggers(monkeypatch):
    monkeypatch.setitem(sys.modules, "tree_sitter_al", None)
    fixture = Path(__file__).parent / "fixtures" / "semantic.al"

    result = extract_al(fixture)
    triggers = [node for node in result["nodes"] if node["label"] == "OnValidate()"]
    trigger_ids = {node["id"] for node in triggers}
    trigger_edges = [
        edge for edge in result["edges"]
        if edge["relation"] == "contains" and edge["target"] in trigger_ids
    ]

    assert len(triggers) == 2
    assert len(trigger_ids) == 2
    assert len(trigger_edges) == 2


def test_al_fallback_reports_read_errors(monkeypatch, tmp_path):
    monkeypatch.setitem(sys.modules, "tree_sitter_al", None)
    result = extract_al(tmp_path / "missing.al")
    assert result["nodes"] == []
    assert result["edges"] == []
    assert result.get("error")


def test_al_tree_sitter_extracts_supported_objects_and_members():
    pytest.importorskip("tree_sitter_al")
    fixture = Path(__file__).parent / "fixtures" / "semantic.al"

    result = extract_al(fixture)
    object_nodes = [node for node in result["nodes"] if node.get("object_kind")]
    kinds = {node["object_kind"] for node in object_nodes}
    member_kinds = {node.get("member_kind") for node in result["nodes"]}

    assert kinds == {
        "codeunit", "table", "tableextension", "page", "pageextension",
        "enum", "enumextension", "interface", "report", "reportextension",
        "query", "xmlport", "permissionset", "permissionsetextension",
    }
    assert {"procedure", "field", "enum_value"} <= member_kinds
    on_validate = [node for node in result["nodes"] if node["label"] == "OnValidate()"]
    assert len(on_validate) == 2
    assert len({node["id"] for node in on_validate}) == 2
    assert all(node["extraction_tier"] == "tree_sitter" for node in result["nodes"])
    assert not result.get("syntax_errors")


def test_al_tree_sitter_resolves_quoted_special_identifiers():
    pytest.importorskip("tree_sitter_al")
    fixture = Path(__file__).parent / "fixtures" / "special_identifiers.al"

    result = extract([fixture], cache_root=fixture.parent)
    nodes = {node["label"]: node for node in result["nodes"]}
    action_triggers = [node for node in result["nodes"] if node["label"] == "OnAction()"]
    dataitem_triggers = [
        node for node in result["nodes"] if node["label"] == "OnAfterGetRecord()"
    ]
    relations = {
        (edge["source"], edge["target"], edge["relation"])
        for edge in result["edges"]
    }

    assert nodes["Übernahme-Plan (Nord & Süd)"]["lookup_key"] == (
        "übernahme-plan (nord & süd)"
    )
    assert nodes["Externe Nr. (Alt)"]["member_kind"] == "field"
    assert nodes["Prüfe & Starte (Auswahl)()"]["lookup_key"] == (
        "prüfe & starte (auswahl)"
    )
    assert len(action_triggers) == 2
    assert len({node["id"] for node in action_triggers}) == 2
    assert len(dataitem_triggers) == 2
    assert len({node["id"] for node in dataitem_triggers}) == 2
    assert any(
        (trigger["id"], nodes["Prüfe & Starte (Auswahl)()"]["id"], "calls")
        in relations
        for trigger in action_triggers
    )
    assert (
        nodes["Prüfe & Starte (Auswahl)()"]["id"],
        nodes["Setze Prüfstatus()"]["id"],
        "calls",
    ) in relations
    assert all(
        (trigger["id"], nodes["Sammle Ergebnis()"]["id"], "calls") in relations
        for trigger in dataitem_triggers
    )


def test_al_tree_sitter_preserves_callable_and_field_metadata():
    pytest.importorskip("tree_sitter_al")
    fixture = Path(__file__).parent / "fixtures" / "semantic.al"

    result = extract_al(fixture)
    run = next(node for node in result["nodes"] if node["label"] == "Run()" and node.get("_callable"))
    field = next(node for node in result["nodes"] if node.get("member_kind") == "field")
    publisher = next(node for node in result["nodes"] if node["label"] == "OnWorked()")

    assert run["parameters"][0]["name"] == "Target"
    assert run["return_type"] == "Boolean"
    assert field["member_id"] == "1"
    assert field["data_type"] == "Integer"
    assert publisher["visibility"] == "local"
    assert publisher["attributes"][0]["name"] == "IntegrationEvent"


def test_al_tree_sitter_collects_resolution_facts_without_error_nodes():
    pytest.importorskip("tree_sitter_al")
    fixture = Path(__file__).parent / "fixtures" / "semantic.al"

    result = extract_al(fixture)
    facts = result["al_facts"]

    assert facts["namespace"] == "Example.App"
    assert facts["usings"] == ["Example.Shared"]
    assert any(item["base"] == "Work Item" for item in facts["objects"])
    assert any(item["interfaces"] == ["IWorker"] for item in facts["objects"])
    assert any(call["receiver_type"] == "Worker Impl" for call in facts["calls"])
    assert facts["event_publishers"][0]["name"] == "OnWorked"
    assert facts["enum_mappings"] == [{
        "source": next(node["id"] for node in result["nodes"] if node["label"] == "Standard"),
        "interface": "IWorker",
        "implementation": "Worker Impl",
        "line": 14,
    }]
    assert not any(node.get("label") == "ERROR" for node in result["nodes"])


def test_al_resolver_emits_language_relationships(tmp_path):
    pytest.importorskip("tree_sitter_al")
    source = tmp_path / "semantic.al"
    source.write_text(
        (Path(__file__).parent / "fixtures" / "semantic.al").read_text(encoding="utf-8"),
        encoding="utf-8",
    )

    result = extract([source], cache_root=tmp_path)
    nodes = {node["label"]: node["id"] for node in result["nodes"]}
    relations = {
        (edge["source"], edge["target"], edge["relation"], edge.get("context"))
        for edge in result["edges"]
    }

    assert (nodes["Work Item Ext"], nodes["Work Item"], "extends", "extension") in relations
    assert (
        nodes["Extra Work Permissions"],
        nodes["Work Permissions"],
        "extends",
        "extension",
    ) in relations
    assert (nodes["Worker Impl"], nodes["IWorker"], "implements", "interface") in relations
    assert (nodes["Standard"], nodes["IWorker"], "implements", "enum_implementation") in relations
    assert (nodes["Standard"], nodes["Worker Impl"], "references", "enum_implementation") in relations
    assert (nodes["HandleWorked()"], nodes["OnWorked()"], "references", "event_subscription") in relations
    assert any(
        target == nodes["OnWorked()"] and relation == "calls"
        for _, target, relation, _ in relations
    )


def test_al_resolver_preserves_all_implemented_interfaces(tmp_path):
    pytest.importorskip("tree_sitter_al")
    source = tmp_path / "interfaces.al"
    source.write_text(
        "interface FirstContract { }\n"
        "interface SecondContract { }\n"
        "codeunit 1 Worker implements FirstContract, SecondContract { }\n",
        encoding="utf-8",
    )

    result = extract([source], cache_root=tmp_path)
    nodes = {node["label"]: node["id"] for node in result["nodes"]}
    implemented = {
        edge["target"]
        for edge in result["edges"]
        if edge["source"] == nodes["Worker"]
        and edge["relation"] == "implements"
    }

    assert implemented == {nodes["FirstContract"], nodes["SecondContract"]}


def test_al_resolves_usercontrols_and_controladdin_calls(tmp_path):
    pytest.importorskip("tree_sitter_al")
    source = tmp_path / "controls.al"
    source.write_text(
        "controladdin DemoAddIn\n"
        "{\n"
        "    procedure Run(Value: Text);\n"
        "    event OnRaised(Value: Text);\n"
        "}\n"
        "page 1 DemoPage\n"
        "{\n"
        "    layout\n"
        "    {\n"
        "        area(Content)\n"
        "        {\n"
        "            usercontrol(FirstHost; DemoAddIn)\n"
        "            {\n"
        "                trigger OnRaised(Value: Text)\n"
        "                begin\n"
        "                    CurrPage.FirstHost.Run(Value);\n"
        "                end;\n"
        "            }\n"
        "            usercontrol(SecondHost; DemoAddIn)\n"
        "            {\n"
        "                trigger OnRaised(Value: Text)\n"
        "                begin\n"
        "                end;\n"
        "            }\n"
        "        }\n"
        "    }\n"
        "}\n",
        encoding="utf-8",
    )

    result = extract([source], cache_root=tmp_path)
    controladdin = next(
        node for node in result["nodes"]
        if node.get("object_kind") == "controladdin"
    )
    usercontrols = [
        node for node in result["nodes"]
        if node.get("member_kind") == "usercontrol"
    ]
    triggers = [
        node for node in result["nodes"]
        if node["label"] == "OnRaised()" and node.get("member_kind") == "trigger"
    ]
    run = next(node for node in result["nodes"] if node["label"] == "Run()")
    event = next(
        node for node in result["nodes"]
        if node["label"] == "OnRaised()" and node.get("member_kind") == "event"
    )
    relations = {
        (edge["source"], edge["target"], edge["relation"], edge.get("context"))
        for edge in result["edges"]
    }

    assert {node["label"] for node in usercontrols} == {"FirstHost", "SecondHost"}
    assert all(node["data_type"] == "DemoAddIn" for node in usercontrols)
    assert len({node["id"] for node in triggers}) == 2
    assert all(
        (node["id"], controladdin["id"], "references", "type") in relations
        for node in usercontrols
    )
    assert any(
        (trigger["id"], run["id"], "calls", "call") in relations
        for trigger in triggers
    )
    assert all(
        (
            trigger["id"],
            event["id"],
            "references",
            "control_addin_event",
        ) in relations
        for trigger in triggers
    )


def test_al_resolver_is_case_insensitive_and_avoids_ambiguous_targets(tmp_path):
    pytest.importorskip("tree_sitter_al")
    first = tmp_path / "first.al"
    second = tmp_path / "second.al"
    caller = tmp_path / "caller.al"
    first.write_text('namespace One; codeunit 1 Worker { procedure Run() begin end; }', encoding="utf-8")
    second.write_text('namespace Two; codeunit 2 WORKER { procedure Run() begin end; }', encoding="utf-8")
    caller.write_text(
        'codeunit 3 Caller { procedure Start() var W: Codeunit worker; begin W.Run(); end; }',
        encoding="utf-8",
    )

    result = extract([first, second, caller], cache_root=tmp_path)
    start = next(node["id"] for node in result["nodes"] if node["label"] == "Start()")
    assert not any(edge["source"] == start and edge["relation"] == "calls" for edge in result["edges"])


def test_al_resolver_preserves_and_resolves_procedure_overloads(tmp_path):
    pytest.importorskip("tree_sitter_al")
    source = tmp_path / "overloads.al"
    source.write_text(
        '''codeunit 1 Worker
{
    procedure Start()
    begin
        Run(1);
    end;

    local procedure Run()
    begin
    end;

    local procedure Run(Value: Integer)
    begin
    end;
}''',
        encoding="utf-8",
    )

    result = extract([source], cache_root=tmp_path)
    run_nodes = [node for node in result["nodes"] if node["label"] == "Run()"]
    start = next(node for node in result["nodes"] if node["label"] == "Start()")
    one_parameter = next(node for node in run_nodes if len(node["parameters"]) == 1)

    assert len(run_nodes) == 2
    assert len({node["id"] for node in run_nodes}) == 2
    assert any(
        edge["source"] == start["id"]
        and edge["target"] == one_parameter["id"]
        and edge["relation"] == "calls"
        for edge in result["edges"]
    )


def test_al_resolver_uses_namespace_imports_and_manifest_context(tmp_path):
    pytest.importorskip("tree_sitter_al")
    (tmp_path / "app.json").write_text(
        '{"id":"app-id","name":"Example App","dependencies":[]}', encoding="utf-8"
    )
    worker = tmp_path / "worker.al"
    caller = tmp_path / "caller.al"
    worker.write_text(
        'namespace Shared; codeunit 1 Worker { procedure Run() begin end; }', encoding="utf-8"
    )
    caller.write_text(
        'namespace Main; using Shared; codeunit 2 Caller { procedure Start() var W: Codeunit Worker; begin W.run(); end; }',
        encoding="utf-8",
    )

    result = extract([worker, caller], cache_root=tmp_path)
    nodes = {node["label"]: node for node in result["nodes"]}
    assert nodes["Worker"]["application_id"] == "app-id"
    assert nodes["Caller"]["application_name"] == "Example App"
    assert any(
        edge["source"] == nodes["Start()"]["id"]
        and edge["target"] == nodes["Run()"]["id"]
        and edge["relation"] == "calls"
        for edge in result["edges"]
    )


def test_al_resolution_is_independent_of_file_order(tmp_path):
    pytest.importorskip("tree_sitter_al")
    worker = tmp_path / "worker.al"
    caller = tmp_path / "caller.al"
    worker.write_text(
        "namespace Shared; codeunit 1 Worker { procedure Run() begin end; }",
        encoding="utf-8",
    )
    caller.write_text(
        "namespace Main; using Shared; codeunit 2 Caller "
        "{ procedure Start() var W: Codeunit Worker; begin W.Run(); end; }",
        encoding="utf-8",
    )

    relationships = []
    for index, files in enumerate(([worker, caller], [caller, worker])):
        result = extract(files, cache_root=tmp_path / f"cache-{index}")
        labels = {node["id"]: node["label"] for node in result["nodes"]}
        relationships.append({
            (
                labels.get(edge["source"]),
                labels.get(edge["target"]),
                edge["relation"],
                edge.get("context"),
            )
            for edge in result["edges"]
            if edge["relation"] in {"calls", "references"}
        })

    assert relationships[0] == relationships[1]
    assert ("Start()", "Run()", "calls", "call") in relationships[0]


def test_al_resolver_connects_test_app_targets_handlers_and_dependency(tmp_path):
    pytest.importorskip("tree_sitter_al")
    main = tmp_path / "MainApp"
    tests = tmp_path / "TestApp"
    main.mkdir()
    tests.mkdir()
    (main / "app.json").write_text(
        '{"id":"main-id","name":"Main App","dependencies":[]}', encoding="utf-8"
    )
    (tests / "app.json").write_text(
        '{"id":"test-id","name":"Test App","dependencies":'
        '[{"id":"main-id","name":"Main App"}]}',
        encoding="utf-8",
    )
    (main / "Card.Page.al").write_text(
        'page 1 "Example Card" { }', encoding="utf-8"
    )
    (tests / "CardTest.Codeunit.al").write_text(
        '''codeunit 2 "Example Tests"
{
    Subtype = Test;

    [Test]
    [HandlerFunctions('ConfirmHandler, SecondHandler')]
    procedure OpensCard()
    var
        Card: TestPage "Example Card";
    begin
        Card.OpenView();
    end;

    [ConfirmHandler]
    procedure ConfirmHandler(Question: Text; var Reply: Boolean)
    begin
        Reply := false;
    end;

    [ConfirmHandler]
    procedure SecondHandler(Question: Text; var Reply: Boolean)
    begin
        Reply := true;
    end;
}''',
        encoding="utf-8",
    )

    files = sorted(path for path in tmp_path.rglob("*") if path.is_file())
    result = extract(files, cache_root=tmp_path)
    nodes = {node["label"]: node["id"] for node in result["nodes"]}
    relations = {
        (edge["source"], edge["target"], edge["relation"], edge.get("context"))
        for edge in result["edges"]
    }
    manifests = {
        Path(node["source_file"]).parent.name: node["id"]
        for node in result["nodes"]
        if str(node.get("source_file", "")).endswith("app.json")
        and str(node.get("label", "")).endswith("app.json")
    }

    assert (nodes["OpensCard()"], nodes["Example Card"], "references", "test_target") in relations
    assert (
        nodes["OpensCard()"], nodes["ConfirmHandler()"], "references", "test_handler"
    ) in relations
    assert (
        nodes["OpensCard()"], nodes["SecondHandler()"], "references", "test_handler"
    ) in relations
    assert (
        manifests["TestApp"], manifests["MainApp"], "depends_on", "application"
    ) in relations
    assert not any(
        edge["source"] == nodes["OpensCard()"] and edge["relation"] == "calls"
        for edge in result["edges"]
    )


def test_al_resolver_tolerates_invalid_manifest(tmp_path):
    pytest.importorskip("tree_sitter_al")
    (tmp_path / "app.json").write_text("not-json", encoding="utf-8")
    source = tmp_path / "simple.al"
    source.write_text('codeunit 1 Simple { procedure Run() begin end; }', encoding="utf-8")
    result = extract([source], cache_root=tmp_path)
    assert any(node["label"] == "Simple" for node in result["nodes"])


@pytest.mark.parametrize("manifest", ["[]", '"not-an-object"', "null"])
def test_al_resolver_tolerates_non_object_manifest(tmp_path, manifest):
    pytest.importorskip("tree_sitter_al")
    (tmp_path / "app.json").write_text(manifest, encoding="utf-8")
    source = tmp_path / "simple.al"
    source.write_text('codeunit 1 Simple { procedure Run() begin end; }', encoding="utf-8")

    result = extract([source], cache_root=tmp_path)

    assert any(node["label"] == "Simple" for node in result["nodes"])


def test_al_corpus_continues_after_one_file_fails(tmp_path):
    pytest.importorskip("tree_sitter_al")
    valid = tmp_path / "valid.al"
    missing = tmp_path / "missing.al"
    valid.write_text('codeunit 1 Valid { procedure Run() begin end; }', encoding="utf-8")

    result = extract([missing, valid], cache_root=tmp_path)

    assert any(node["label"] == "Valid" for node in result["nodes"])
    assert result["failed_sources"] == [str(missing)]