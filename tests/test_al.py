from pathlib import Path
import builtins
import importlib.util
import sys

import pytest

from graphify.detect import CODE_EXTENSIONS, FileType, classify_file
from graphify.extract import _get_extractor, extract
from graphify.extractors.al import _mask_al_comments_and_strings, extract_al


def test_al_extension_is_detected_case_insensitively():
    assert ".al" in CODE_EXTENSIONS
    assert classify_file(Path("Comment.Codeunit.al")) == FileType.CODE
    assert classify_file(Path("Comment.Codeunit.AL")) == FileType.CODE


def test_al_extension_dispatches_to_al_extractor():
    assert _get_extractor(Path("Comment.Codeunit.al")) is extract_al
    assert _get_extractor(Path("Comment.Codeunit.AL")) is extract_al


def test_al_mask_preserves_offsets_and_newlines_across_lexical_states():
    source = "code // comment\nnext /* block\ncomment */ more 'it''s' end"

    masked = _mask_al_comments_and_strings(source)

    assert len(masked) == len(source)
    assert [index for index, char in enumerate(masked) if char == "\n"] == [
        index for index, char in enumerate(source) if char == "\n"
    ]
    assert masked.replace(" ", "") == "code\nnext\nmoreend"


def test_al_missing_parser_reports_optional_extra(tmp_path, capsys, monkeypatch):
    monkeypatch.setitem(sys.modules, "tree_sitter_al", None)
    source = tmp_path / "Comment.Codeunit.al"
    source.write_text('codeunit 75000 "Comment Mgt." { }', encoding="utf-8")

    result = extract([source], cache_root=tmp_path)
    err = capsys.readouterr().err

    assert "used fallback extraction" in err
    assert "tree_sitter_al not installed" in err
    assert 'graphifyy[al]' in err
    assert result["failed_sources"] == []
    assert any(node.get("object_kind") == "codeunit" for node in result["nodes"])


def test_al_parser_load_failure_is_not_reported_as_missing(tmp_path, monkeypatch):
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

    error = extract_al(source).get("error") or ""
    assert "installed but failed to load" in error
    assert "incompatible AL parser binary" in error
    assert "not installed" not in error
    assert "pip install" not in error


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
        "query", "xmlport", "permissionset",
    }
    assert {"procedure", "field", "enum_value"} <= member_kinds
    on_validate = [node for node in result["nodes"] if node["label"] == "OnValidate()"]
    assert len(on_validate) == 2
    assert len({node["id"] for node in on_validate}) == 2
    assert all(node["extraction_tier"] == "tree_sitter" for node in result["nodes"])
    assert not result.get("syntax_errors")


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
    assert (nodes["Worker Impl"], nodes["IWorker"], "implements", "interface") in relations
    assert (nodes["Standard"], nodes["IWorker"], "implements", "enum_implementation") in relations
    assert (nodes["Standard"], nodes["Worker Impl"], "references", "enum_implementation") in relations
    assert (nodes["HandleWorked()"], nodes["OnWorked()"], "references", "event_subscription") in relations
    assert any(
        target == nodes["OnWorked()"] and relation == "calls"
        for _, target, relation, _ in relations
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
    [HandlerFunctions('ConfirmHandler')]
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


def test_al_corpus_continues_after_one_file_fails(tmp_path):
    pytest.importorskip("tree_sitter_al")
    valid = tmp_path / "valid.al"
    missing = tmp_path / "missing.al"
    valid.write_text('codeunit 1 Valid { procedure Run() begin end; }', encoding="utf-8")

    result = extract([missing, valid], cache_root=tmp_path)

    assert any(node["label"] == "Valid" for node in result["nodes"])
    assert result["failed_sources"] == [str(missing)]