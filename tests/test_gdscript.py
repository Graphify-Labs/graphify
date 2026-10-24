"""GDScript (.gd) and Godot text resources (.tscn/.tres/project.godot)."""
from __future__ import annotations

import importlib.util as _ilu
import shutil
import sys
from pathlib import Path

import pytest

from graphify.detect import CODE_EXTENSIONS
from graphify.extract import _DISPATCH, extract, extract_gdscript, extract_godot_resource

# The GDScript grammar comes from tree-sitter-language-pack, an optional extra.
# Scenes and project.godot need no grammar and are always tested.
_needs_gdscript = pytest.mark.skipif(
    _ilu.find_spec("tree_sitter_language_pack") is None,
    reason="tree-sitter-language-pack not installed (optional [gdscript] extra)",
)

FIXTURE = Path(__file__).parent / "fixtures" / "godot"


def _project(tmp_path: Path) -> Path:
    root = tmp_path / "game"
    shutil.copytree(FIXTURE, root)
    return root


def _godot_files(root: Path) -> list[Path]:
    return sorted(p for p in root.rglob("*") if p.suffix in (".gd", ".tscn", ".tres", ".godot"))


def _extract(root: Path, paths: list[Path] | None = None, **kwargs) -> dict:
    return extract(paths or _godot_files(root), cache_root=root, root=root, parallel=False, **kwargs)


def _name(node: dict) -> str:
    return f"{Path(str(node['source_file'])).name}:{node['label']}"


def _pairs(result: dict, relation: str) -> set[tuple[str, str]]:
    names = {n["id"]: _name(n) for n in result["nodes"]}
    return {
        (names.get(e["source"], e["source"]), names.get(e["target"], e["target"]))
        for e in result["edges"]
        if e["relation"] == relation
    }


def test_godot_extensions_are_dispatched():
    for ext in (".gd", ".tscn", ".tres", ".godot"):
        assert ext in CODE_EXTENSIONS
    assert _DISPATCH[".gd"] is extract_gdscript
    for ext in (".tscn", ".tres", ".godot"):
        assert _DISPATCH[ext] is extract_godot_resource


@_needs_gdscript
def test_gdscript_declarations_hang_off_the_class_name(tmp_path):
    root = _project(tmp_path)
    r = extract_gdscript(root / "actors" / "player.gd")
    assert "error" not in r
    labels = {n["label"]: n for n in r["nodes"]}
    for want in ("player.gd", "Player", ".clamp_speed()", "._ready()", "signal jumped",
                 "signal landed", "State", "MAX_JUMPS", "Movement", "Stats", ".speed_for()"):
        assert want in labels, want
    assert labels["Player"]["metadata"] == {"language": "gdscript", "kind": "class", "name": "Player"}
    contains = _pairs(r, "contains")
    methods = _pairs(r, "method")
    assert ("player.gd:player.gd", "player.gd:Player") in contains
    assert ("player.gd:Player", "player.gd:._ready()") in methods
    assert ("player.gd:Player", "player.gd:signal jumped") in contains
    assert ("player.gd:Stats", "player.gd:.speed_for()") in methods
    # a script without class_name: the file node owns its members
    enemy = extract_gdscript(root / "actors" / "enemy.gd")
    assert ("enemy.gd:enemy.gd", "enemy.gd:.patrol()") in _pairs(enemy, "method")


@_needs_gdscript
def test_gdscript_same_file_calls_signals_and_loads(tmp_path):
    root = _project(tmp_path)
    r = extract_gdscript(root / "actors" / "player.gd")
    calls = _pairs(r, "calls")
    assert ("player.gd:._ready()", "player.gd:.clamp_speed()") in calls   # bare and self.
    assert ("player.gd:.speed_for()", "player.gd:.base_speed()") in calls  # inner class
    uses = _pairs(r, "uses")
    assert ("player.gd:._ready()", "player.gd:signal jumped") in uses      # connect + emit
    assert ("player.gd:._ready()", "player.gd:signal landed") in uses      # emit_signal("landed")
    refs = _pairs(r, "references")
    assert ("player.gd:._ready()", "player.gd:._on_jumped()") in refs     # connect callback
    assert ("player.gd:._ready()", "player.gd:._on_landed()") in refs     # self._on_landed
    assert ("player.gd:._ready()", "player.gd:Stats") in refs             # Stats.new()
    loads = [e for e in r["edges"] if e["relation"] == "imports_from"]
    assert {Path(e["target_file"]).name for e in loads} == {"movement.gd", "bullet.tscn"}
    # what needs another file is left to the resolver, never to the shared
    # name-matching pass
    assert r["raw_calls"] and all(rc["is_member_call"] for rc in r["raw_calls"])


@_needs_gdscript
def test_gdscript_cross_file_references_resolve(tmp_path):
    root = _project(tmp_path)
    r = _extract(root)
    calls = _pairs(r, "calls")
    assert ("player.gd:._ready()", "game_state.gd:.add_score()") in calls        # autoload
    assert ("player.gd:._ready()", "movement.gd:.walk_vector()") in calls        # preload alias
    assert ("player.gd:._ready()", "actor.gd:.take_damage()") in calls           # inherited
    assert ("grunt.gd:._ready()", "actor.gd:.take_damage()") in calls            # grandparent
    assert ("grunt.gd:._ready()", "enemy.gd:.patrol()") in calls                 # super.patrol()
    assert ("grunt.gd:.patrol()", "enemy.gd:.patrol()") in calls                 # super()
    assert not any(src.startswith("grunt.gd") and dst == "grunt.gd:.patrol()"
                   for src, dst in calls)
    inherits = _pairs(r, "inherits")
    assert ("player.gd:Player", "actor.gd:Actor") in inherits                   # class_name
    assert ("enemy.gd:enemy.gd", "actor.gd:Actor") in inherits
    assert ("grunt.gd:grunt.gd", "enemy.gd:enemy.gd") in inherits               # res:// path
    uses = _pairs(r, "uses")
    assert ("player.gd:._ready()", "game_state.gd:signal paused") in uses      # autoload signal
    assert ("grunt.gd:._ready()", "actor.gd:signal died") in uses              # inherited signal
    refs = _pairs(r, "references")
    assert ("player.gd:Player", "weapon.gd:Weapon") in refs                     # var weapon: Weapon
    assert ("player.gd:._ready()", "weapon.gd:Weapon") in refs                  # Weapon.new()
    # engine calls, unknown receivers and unknown members bind to nothing
    targets = {dst for _src, dst in calls}
    assert not any(t.endswith((":.fire()", ":.unknown_method()", ":.add_child()", ":.print()"))
                   for t in targets)


@_needs_gdscript
def test_gdscript_bare_call_never_binds_an_unrelated_script(tmp_path):
    (tmp_path / "project.godot").write_text("config_version=5\n", encoding="utf-8")
    (tmp_path / "a.gd").write_text("extends Node\n\n\nfunc refresh() -> void:\n\tpass\n",
                                   encoding="utf-8")
    caller = tmp_path / "b.gd"
    caller.write_text("extends Node\n\n\nfunc _ready() -> void:\n\trefresh()\n", encoding="utf-8")
    r = _extract(tmp_path, [tmp_path / "a.gd", caller])
    # b.gd does not inherit a.gd, so GDScript cannot reach a.gd's refresh()
    assert not _pairs(r, "calls")


@_needs_gdscript
def test_gdscript_ambiguous_class_name_stays_unresolved(tmp_path):
    (tmp_path / "project.godot").write_text("config_version=5\n", encoding="utf-8")
    for folder in ("one", "two"):
        (tmp_path / folder).mkdir()
        (tmp_path / folder / "unit.gd").write_text(
            "class_name Unit\nextends Node\n\n\nfunc move() -> void:\n\tpass\n", encoding="utf-8")
    caller = tmp_path / "army.gd"
    caller.write_text("extends Unit\n\n\nfunc _ready() -> void:\n\tmove()\n\tUnit.new()\n",
                      encoding="utf-8")
    r = _extract(tmp_path)
    assert not _pairs(r, "inherits")
    assert not _pairs(r, "calls")
    assert not _pairs(r, "references")


def test_godot_scene_links_scripts_scenes_and_signal_handlers(tmp_path):
    root = _project(tmp_path)
    r = extract_godot_resource(root / "scenes" / "main.tscn")
    assert "error" not in r
    loads = {(e["context"], Path(e["target_file"]).name) for e in r["edges"]
             if e["relation"] == "imports_from"}
    assert loads == {("Script", "player.gd"), ("PackedScene", "bullet.tscn")}   # no texture
    handlers = [e for e in r["edges"] if e["relation"] == "references"]
    # the "." connection has no script on the root node, so it is dropped
    assert len(handlers) == 1
    assert handlers[0]["context"] == "signal pressed"
    assert Path(handlers[0]["target_file"]).name == "player.gd"


def test_godot_project_declares_autoloads_and_main_scene(tmp_path):
    root = _project(tmp_path)
    r = extract_godot_resource(root / "project.godot")
    autoloads = {n["label"]: n for n in r["nodes"] if n["metadata"]["kind"] == "autoload"}
    assert set(autoloads) == {"GameState", "Hud", "Probe"}
    linked = {e["source"]: Path(e["target_file"]).name for e in r["edges"]
              if e["relation"] == "imports_from"}
    # uid:// names no file this pass can see: the autoload stays, unlinked
    assert linked == {autoloads["GameState"]["id"]: "game_state.gd",
                      autoloads["Hud"]["id"]: "hud.tscn"}
    main = [e for e in r["edges"] if e.get("context") == "main_scene"]
    assert [Path(e["target_file"]).name for e in main] == ["main.tscn"]


@_needs_gdscript
def test_godot_scene_handler_lands_on_the_script_method(tmp_path):
    root = _project(tmp_path)
    r = _extract(root)
    assert ("main.tscn:main.tscn", "player.gd:._on_jumped()") in _pairs(r, "references")
    assert ("project.godot:GameState", "game_state.gd:game_state.gd") in _pairs(r, "imports_from")


def _as_watch_context(result: dict, changed: Path) -> tuple[list[dict], list[dict]]:
    """What `graphify watch` hands an incremental rebuild for the unchanged files:
    the same node fields, metadata keys and edge relations watch.py forwards."""
    changed_name = changed.name
    nodes = [
        {
            **{k: n.get(k) for k in ("id", "label", "source_file", "file_type", "type")},
            **({"_callable": True} if n.get("_callable") else {}),
            "metadata": {k: v for k, v in (n.get("metadata") or {}).items()
                         if k in ("language", "kind", "module", "name", "arity")},
        }
        for n in result["nodes"]
        if n.get("source_file") and Path(str(n["source_file"])).name != changed_name
    ]
    edges = [
        {k: e.get(k) for k in ("source", "target", "relation", "source_file")}
        for e in result["edges"]
        if e["relation"] in ("contains", "method", "inherits", "imports", "imports_from")
        and Path(str(e["source_file"])).name != changed_name
    ]
    return nodes, edges


@_needs_gdscript
def test_gdscript_incremental_rebuild_matches_full_build(tmp_path):
    root = _project(tmp_path)
    full = _extract(root)
    player = root / "actors" / "player.gd"
    player.write_text(player.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    context_nodes, context_edges = _as_watch_context(full, player)
    changed = _extract(root, [player], resolution_context_nodes=context_nodes,
                       resolution_context_edges=context_edges)

    def from_player(result: dict) -> set[tuple[str, str, str]]:
        return {(e["source"], e["target"], e["relation"]) for e in result["edges"]
                if Path(str(e["source_file"])).name == "player.gd"}

    assert from_player(changed) == from_player(full)
    assert ("player.gd:._ready()", "game_state.gd:.add_score()") in {
        (s, t) for s, t in _pairs(full, "calls")}


def test_gdscript_missing_grammar_reports_install_hint(tmp_path, monkeypatch, capsys):
    script = tmp_path / "lone.gd"
    script.write_text("extends Node\n", encoding="utf-8")
    monkeypatch.setitem(sys.modules, "tree_sitter_language_pack", None)
    r = extract([script], cache_root=tmp_path)
    assert r["nodes"] == []
    assert 'pip install "graphifyy[gdscript]"' in capsys.readouterr().err
