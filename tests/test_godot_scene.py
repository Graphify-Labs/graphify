import tempfile
import textwrap
import unittest
from pathlib import Path

from graphify.extract import extract_godot_scene, _make_id, _file_stem
from graphify.extractors import godot_scene as gs


def _edges(result, relation):
    return [e for e in result["edges"] if e["relation"] == relation]


def _norm(result):
    """Order-independent snapshot of a result's nodes and edges."""
    n = sorted((x["id"], x["label"], x.get("source_location") or "")
               for x in result["nodes"])
    e = sorted((x["source"], x["target"], x["relation"],
                x.get("context") or "", x.get("source_location") or "")
               for x in result["edges"])
    return n, e


class TestGodotScene(unittest.TestCase):
    """The .tscn/.tres/project.godot extractor (grammar path when available)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "scripts").mkdir()
        (self.root / "scenes").mkdir()
        (self.root / "project.godot").write_text("config_version=5\n")
        (self.root / "scripts" / "enemy.gd").write_text(
            "class_name Enemy\nextends CharacterBody2D\nfunc take_damage(a):\n\tpass\n"
        )
        (self.root / "scripts" / "game_state.gd").write_text("extends Node\n")
        (self.root / "scenes" / "Bullet.tscn").write_text(
            '[gd_scene format=3 uid="uid://bul"]\n\n[node name="Bullet" type="Area2D"]\n'
        )

    def tearDown(self):
        self.tmp.cleanup()

    def _write(self, name, body):
        p = self.root / name
        p.write_text(textwrap.dedent(body))
        return p

    def test_scene_script_subscene_and_connection(self):
        p = self._write("scenes/Main.tscn", """
            [gd_scene load_steps=3 format=3 uid="uid://abc"]

            [ext_resource type="Script" path="res://scripts/enemy.gd" id="1_e"]
            [ext_resource type="PackedScene" path="res://scenes/Bullet.tscn" id="2_b"]

            [node name="Enemy" type="CharacterBody2D"]
            script = ExtResource("1_e")

            [node name="Hitbox" type="Area2D" parent="."]

            [connection signal="body_entered" from="Hitbox" to="." method="take_damage"]
        """)
        r = extract_godot_scene(p)

        enemy_gd = _make_id(str((self.root / "scripts" / "enemy.gd").resolve()))
        bullet = _make_id(str((self.root / "scenes" / "Bullet.tscn").resolve()))

        attaches = {e["target"] for e in _edges(r, "attaches_script")}
        self.assertIn(enemy_gd, attaches)

        instances = {e["target"] for e in _edges(r, "instances")}
        self.assertIn(bullet, instances)

        # the connection method resolves to the ROOT script's function node id,
        # i.e. the same id the gdscript extractor emits for take_damage()
        stem = _file_stem((self.root / "scripts" / "enemy.gd").resolve())
        take_damage_nid = _make_id(stem, "take_damage")
        conn_targets = {e["target"] for e in _edges(r, "connects")}
        self.assertIn(take_damage_nid, conn_targets)

    def test_project_godot_autoloads_and_main_scene(self):
        p = self._write("project.godot", """
            config_version=5

            [application]
            run/main_scene="res://scenes/Main.tscn"

            [autoload]
            GameState="*res://scripts/game_state.gd"
        """)
        r = extract_godot_scene(p)

        self.assertTrue(_edges(r, "autoload"), "no autoload edge emitted")
        self.assertTrue(_edges(r, "main_scene"), "no main_scene edge emitted")

        gstate = _make_id(str((self.root / "scripts" / "game_state.gd").resolve()))
        script_targets = {e["target"] for e in _edges(r, "script")}
        self.assertIn(gstate, script_targets)

    def test_line_parser_fallback_matches(self):
        # Force the dependency-free line parser (as if the grammar were absent)
        # and confirm it still emits the same edges the default path produces.
        scene = self._write("scenes/Main.tscn", """
            [gd_scene load_steps=3 format=3 uid="uid://abc"]

            [ext_resource type="Script" path="res://scripts/enemy.gd" id="1_e"]
            [ext_resource type="PackedScene" path="res://scenes/Bullet.tscn" id="2_b"]

            [node name="Enemy" type="CharacterBody2D"]
            script = ExtResource("1_e")

            [connection signal="body_entered" from="Enemy" to="." method="take_damage"]
        """)
        default = extract_godot_scene(scene)
        saved = gs._RESOURCE_PARSER
        try:
            gs._RESOURCE_PARSER = None          # disable grammar -> line parser
            forced_lines = extract_godot_scene(scene)
        finally:
            gs._RESOURCE_PARSER = saved
        # The line fallback must be at least as capable as the default path here.
        self.assertEqual(_norm(default), _norm(forced_lines))


@unittest.skipUnless(gs._load_resource_parser() is not None,
                     "godot_resource grammar (tree-sitter-language-pack) not installed")
class TestGodotSceneGrammar(unittest.TestCase):
    """Behaviour specific to the grammar front end."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "scripts").mkdir()
        (self.root / "project.godot").write_text("config_version=5\n")
        (self.root / "scripts" / "enemy.gd").write_text("extends Node\n")

    def tearDown(self):
        self.tmp.cleanup()

    def _write(self, name, body):
        p = self.root / name
        p.write_text(textwrap.dedent(body))
        return p

    def test_grammar_and_line_parsers_agree(self):
        scene = self._write("Main.tscn", """
            [gd_scene load_steps=2 format=3 uid="uid://abc"]

            [ext_resource type="Script" path="res://scripts/enemy.gd" id="1_e"]
            [ext_resource type="Texture2D" path="res://art/hero.png" id="2_t"]

            [node name="Enemy" type="CharacterBody2D"]
            script = ExtResource("1_e")
        """)
        text = scene.read_text()
        via_grammar = gs._build_scene(scene, gs._blocks_from_grammar(text))
        via_lines = gs._build_scene(scene, gs._blocks_from_lines(text))
        self.assertEqual(_norm(via_grammar), _norm(via_lines))

    def test_grammar_survives_bracket_in_quoted_value(self):
        # A ']' inside a quoted attribute value trips the line-regex section
        # matcher but the grammar parses it correctly.
        scene = self._write("Weird.tscn", """
            [gd_scene format=3]

            [ext_resource type="Script" path="res://scripts/enemy.gd" id="1_e"]

            [node name="Odd]Name" type="Node2D"]
            script = ExtResource("1_e")
        """)
        r = extract_godot_scene(scene)
        enemy_gd = _make_id(str((self.root / "scripts" / "enemy.gd").resolve()))
        attaches = {e["target"] for e in _edges(r, "attaches_script")}
        self.assertIn(enemy_gd, attaches)


if __name__ == "__main__":
    unittest.main()
