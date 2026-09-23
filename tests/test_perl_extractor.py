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


def test_perl_fixture_uses_normal_extract_path(tmp_path):
    result = extract([FIXTURE], cache_root=tmp_path)

    labels = {node["label"] for node in result["nodes"]}
    assert {"Sample", "run()", "helper()"} <= labels
    assert ("run()", "helper()") in _edge_labels(result, "calls")


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
