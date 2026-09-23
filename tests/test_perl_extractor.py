"""Extraction coverage for perl."""
from __future__ import annotations

import sys
from pathlib import Path

from graphify.extract import extract


FIXTURE = Path(__file__).parent / "fixtures" / "new_languages" / "sample.pl"


def _edge_labels(result: dict, relation: str) -> set[tuple[str, str]]:
    labels = {node["id"]: node["label"] for node in result["nodes"]}
    return {
        (labels.get(edge["source"], edge["source"]), labels.get(edge["target"], edge["target"]))
        for edge in result["edges"]
        if edge["relation"] == relation
    }


def test_perl_subs_resolve_within_same_package(tmp_path):
    source = tmp_path / "worker.pl"
    source.write_text(
        "package Worker;\n"
        "sub run {\n"
        "    return helper();\n"
        "}\n"
        "sub helper {\n"
        "    return 1;\n"
        "}\n",
        encoding="utf-8",
    )

    result = extract([source], cache_root=tmp_path)

    labels = {node["label"] for node in result["nodes"]}
    assert {"Worker", "run()", "helper()"} <= labels
    assert ("run()", "helper()") in _edge_labels(result, "calls")


def test_perl_use_require_and_inheritance(tmp_path):
    other = tmp_path / "Other.pm"
    other.write_text(
        "package Other;\n"
        "sub go {\n"
        "    return 1;\n"
        "}\n",
        encoding="utf-8",
    )
    source = tmp_path / "Worker.pm"
    source.write_text(
        "package Worker;\n"
        "use strict;\n"
        "use warnings;\n"
        "use Some::Module;\n"
        "use parent -norequire, 'Base::Class';\n"
        "\n"
        "sub run {\n"
        "    Other::go();\n"
        "    Some::Module::do_thing();\n"
        "    return 1;\n"
        "}\n",
        encoding="utf-8",
    )

    result = extract([source, other], cache_root=tmp_path)

    labels = {node["label"] for node in result["nodes"]}
    assert {"Worker", "Other", "Some::Module", "Base::Class", "run()", "go()"} <= labels
    assert "strict" not in labels
    assert "warnings" not in labels
    assert ("Worker", "Some::Module") in _edge_labels(result, "imports")
    assert ("Worker", "Base::Class") in _edge_labels(result, "inherits")
    assert ("run()", "go()") in _edge_labels(result, "calls")


def test_perl_isa_inheritance(tmp_path):
    source = tmp_path / "hierarchy.pl"
    source.write_text(
        "package Animal;\n"
        "sub speak { return 'noise'; }\n"
        "\n"
        "package Dog;\n"
        "our @ISA = ('Animal');\n"
        "\n"
        "sub bark { return 'woof'; }\n",
        encoding="utf-8",
    )

    result = extract([source], cache_root=tmp_path)

    labels = {node["label"] for node in result["nodes"]}
    assert {"Animal", "Dog", "speak()", "bark()"} <= labels
    assert ("Dog", "Animal") in _edge_labels(result, "inherits")


def test_perl_qw_list_inheritance(tmp_path):
    # qw() parses as a quoted_word_list, not a string_literal — the most
    # common spelling of both `use base`/`use parent` and @ISA.
    source = tmp_path / "qw_hierarchy.pl"
    source.write_text(
        "package Puppy;\n"
        "use base qw(Base::One Base::Two);\n"
        "our @ISA = qw(Animal Dog);\n"
        "sub bark { return 1; }\n",
        encoding="utf-8",
    )

    result = extract([source], cache_root=tmp_path)

    labels = {node["label"] for node in result["nodes"]}
    assert {"Base::One", "Base::Two", "Animal", "Dog"} <= labels
    inherits = _edge_labels(result, "inherits")
    assert ("Puppy", "Base::One") in inherits
    assert ("Puppy", "Base::Two") in inherits
    assert ("Puppy", "Animal") in inherits
    assert ("Puppy", "Dog") in inherits


def test_perl_fixture_uses_normal_extract_path(tmp_path):
    result = extract([FIXTURE], cache_root=tmp_path)

    labels = {node["label"] for node in result["nodes"]}
    assert {"Sample", "run()", "helper()"} <= labels
    assert ("run()", "helper()") in _edge_labels(result, "calls")


def test_perl_statement_package_is_scoped_to_enclosing_block(tmp_path):
    source = tmp_path / "scoped.pl"
    source.write_text(
        "package Outer {\n"
        "    sub first { return 1; }\n"
        "    package Inner;\n"
        "    sub second { return 2; }\n"
        "}\n"
        "sub third { return 3; }\n"
        "package Later;\n"
        "sub fourth { return 4; }\n",
        encoding="utf-8",
    )

    result = extract([source], cache_root=tmp_path)

    contains = _edge_labels(result, "contains")
    assert ("Outer", "first()") in contains
    assert ("Inner", "second()") in contains
    assert ("scoped.pl", "third()") in contains
    assert ("Later", "fourth()") in contains
    assert ("Inner", "third()") not in contains
    assert ("Outer", "second()") not in contains


def test_perl_use_and_require_are_reached_in_every_scope(tmp_path):
    helpers = tmp_path / "helpers.pl"
    helpers.write_text("sub help { return 1; }\n", encoding="utf-8")
    source = tmp_path / "loader.pl"
    source.write_text(
        "package Loader;\n"
        "use Top::Module;\n"
        "require Bare::Module;\n"
        "require 'helpers.pl';\n"
        "package Block {\n"
        "    use Block::Module;\n"
        "    require Block::Required;\n"
        "}\n",
        encoding="utf-8",
    )

    result = extract([source, helpers], cache_root=tmp_path)

    imports = _edge_labels(result, "imports")
    assert ("Loader", "Top::Module") in imports
    assert ("Loader", "Bare::Module") in imports
    assert ("Block", "Block::Module") in imports
    assert ("Block", "Block::Required") in imports
    assert ("Loader", "helpers.pl") in _edge_labels(result, "imports_from")


def test_perl_malformed_file_does_not_create_phantoms(tmp_path):
    source = tmp_path / "broken.pl"
    source.write_text(
        "package Broken;\nsub valid { return 1; }\n# sub ghost { return 1; }\nsub invalid(\n",
        encoding="utf-8",
    )

    result = extract([source], cache_root=tmp_path)

    labels = {node["label"].casefold() for node in result["nodes"]}
    assert "valid()" in labels
    assert labels.isdisjoint({"ghost()"})


def test_perl_missing_parser_reports_install_hint(tmp_path, monkeypatch, capsys):
    source = tmp_path / "missing.pl"
    source.write_text("package Missing;\n", encoding="utf-8")
    monkeypatch.setitem(sys.modules, "tree_sitter_language_pack", None)

    result = extract([source], cache_root=tmp_path)

    assert result["nodes"] == []
    assert 'pip install "graphifyy[perl]"' in capsys.readouterr().err


def test_perl_package_defined_after_reference_is_source_backed(tmp_path):
    source = tmp_path / "zoo.pl"
    source.write_text(
        "package Dog;\n"
        "use parent -norequire, 'Animal';\n"
        "sub bark { return Animal::speak(); }\n"
        "package Animal;\n"
        "sub speak { return 1; }\n",
        encoding="utf-8",
    )

    result = extract([source], cache_root=tmp_path)

    animal = next(node for node in result["nodes"] if node["label"] == "Animal")
    dog = next(node for node in result["nodes"] if node["label"] == "Dog")
    assert animal["source_file"] == dog["source_file"]
    assert animal["source_location"] == "L4"
    assert animal["metadata"]["package"] == "Animal"
    assert ("Dog", "Animal") in _edge_labels(result, "inherits")
    assert ("zoo.pl", "Animal") in _edge_labels(result, "contains")


def test_perl_extractor_module_imports_without_tree_sitter(monkeypatch):
    import importlib

    monkeypatch.setitem(sys.modules, "tree_sitter", None)
    monkeypatch.delitem(sys.modules, "graphify.extractors.perl", raising=False)
    module = importlib.import_module("graphify.extractors.perl")
    assert callable(module.extract_perl)


def test_perl_main_qualified_calls_resolve_to_implicit_main_subs(tmp_path):
    source = tmp_path / "script.pl"
    source.write_text(
        "sub helper { return 1; }\n"
        "sub other { return 2; }\n"
        "package Worker;\n"
        "sub run { main::helper(); ::other(); }\n",
        encoding="utf-8",
    )

    result = extract([source], cache_root=tmp_path)

    calls = _edge_labels(result, "calls")
    assert ("run()", "helper()") in calls
    assert ("run()", "other()") in calls


def test_perl_qualified_method_invocants_keep_their_package(tmp_path):
    lib = tmp_path / "Lib.pm"
    lib.write_text(
        "package Foo::Bar;\n"
        "sub create { return 1; }\n"
        "sub method { return 2; }\n"
        "sub quoted { return 3; }\n"
        "package Other;\n"
        "sub create { return 4; }\n"
        "sub method { return 5; }\n"
        "sub quoted { return 6; }\n",
        encoding="utf-8",
    )
    source = tmp_path / "app.pl"
    source.write_text(
        "package App;\n"
        "sub go {\n"
        "    my $o = Foo::Bar::->create();\n"
        "    $o->Foo::Bar::method();\n"
        "    'Foo::Bar'->quoted();\n"
        "}\n",
        encoding="utf-8",
    )

    result = extract([source, lib], cache_root=tmp_path)

    ids = {node["id"]: node for node in result["nodes"]}
    targets = {
        (ids[edge["target"]]["label"], ids[edge["target"]]["metadata"]["package"])
        for edge in result["edges"]
        if edge["relation"] == "calls" and ids[edge["source"]]["label"] == "go()"
    }
    assert targets == {
        ("create()", "Foo::Bar"), ("method()", "Foo::Bar"), ("quoted()", "Foo::Bar"),
    }
