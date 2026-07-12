"""GDScript extraction and pipeline integration tests."""
from __future__ import annotations

import importlib.util
import sys

from pathlib import Path

import pytest

from graphify.detect import CODE_EXTENSIONS, FileType, classify_file
from graphify.extract import extract
from graphify.extractors.gdscript import extract_gdscript


FIXTURES = Path(__file__).parent / "fixtures"
_HAS_GDSCRIPT_GRAMMAR = importlib.util.find_spec("tree_sitter_language_pack") is not None
needs_gdscript_grammar = pytest.mark.skipif(
    not _HAS_GDSCRIPT_GRAMMAR,
    reason="tree-sitter-language-pack not installed (optional [gdscript] extra)",
)


def _labels(result: dict) -> set[str]:
    return {str(node.get("label", "")) for node in result["nodes"]}


def _edge_labels(result: dict, relation: str) -> set[tuple[str, str]]:
    labels = {node["id"]: str(node.get("label", "")) for node in result["nodes"]}
    return {
        (
            str(labels.get(edge["source"], edge["source"])),
            str(labels.get(edge["target"], edge["target"])),
        )
        for edge in result["edges"]
        if edge.get("relation") == relation
    }


def test_gdscript_extension_is_classified_as_code() -> None:
    assert ".gd" in CODE_EXTENSIONS
    assert classify_file(Path("player.gd")) == FileType.CODE


@needs_gdscript_grammar
def test_gdscript_extracts_core_declarations_and_calls() -> None:
    result = extract_gdscript(FIXTURES / "sample.gd")

    assert "error" not in result
    assert {
        "Player",
        "health_changed",
        "weapon",
        "MAX_HEALTH",
        "State",
        "IDLE",
        "RUNNING",
        "_ready()",
        "_setup()",
        "reset()",
        "Inventory",
        "clear()",
    } <= _labels(result)

    assert ("State", "IDLE") in _edge_labels(result, "case_of")
    assert ("State", "RUNNING") in _edge_labels(result, "case_of")
    assert ("Player", "Weapon") in _edge_labels(result, "references")
    assert ("_ready()", "Weapon") in _edge_labels(result, "instantiates")
    assert ("_ready()", "_setup()") in _edge_labels(result, "calls")
    assert ("_ready()", "reset()") in _edge_labels(result, "calls")
    assert "CharacterBody2D" not in _labels(result)


@needs_gdscript_grammar
def test_gdscript_cross_file_types_and_resource_paths_resolve(tmp_path: Path) -> None:
    (tmp_path / "project.godot").write_text("[application]\n")
    actor = tmp_path / "actor.gd"
    actor.write_text(
        "class_name Actor\n"
        "extends Node\n\n"
        "func wake() -> void:\n"
        "    pass\n"
    )
    player = tmp_path / "player.gd"
    player.write_text(
        "class_name Player\n"
        "extends Actor\n\n"
        "var actor: Actor\n\n"
        "func spawn() -> void:\n"
        "    var copy := Actor.new()\n"
        '    var script = preload("res://actor.gd")\n'
    )
    child = tmp_path / "child.gd"
    child.write_text(
        'extends "res://actor.gd"\n'
        "class_name Child\n"
    )

    result = extract(
        [actor, player, child],
        cache_root=tmp_path,
        parallel=False,
    )

    assert ("Player", "Actor") in _edge_labels(result, "inherits")
    assert ("Player", "Actor") in _edge_labels(result, "references")
    assert ("spawn()", "Actor") in _edge_labels(result, "instantiates")
    assert ("player.gd", "actor.gd") in _edge_labels(result, "imports_from")
    assert ("Child", "actor.gd") in _edge_labels(result, "inherits")


def test_gdscript_missing_extra_is_reported(tmp_path: Path, capsys, monkeypatch) -> None:
    script = tmp_path / "player.gd"
    script.write_text("extends Node\n")
    monkeypatch.setitem(sys.modules, "tree_sitter_language_pack", None)

    result = extract([script], cache_root=tmp_path, parallel=False)
    error = capsys.readouterr().err

    assert result["nodes"] == []
    assert "1 .gd file(s)" in error
    assert "tree_sitter_language_pack not installed" in error
    assert "graphifyy[gdscript]" in error
    assert "#1745" in error
