import tempfile
import textwrap
import unittest
from pathlib import Path

from graphify.extract import extract_godot_scene, _make_id, _file_stem


def _edges(result, relation):
    return [e for e in result["edges"] if e["relation"] == relation]


class TestGodotScene(unittest.TestCase):
    """The .tscn/.tres/project.godot extractor needs no grammar."""

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

        gs = _make_id(str((self.root / "scripts" / "game_state.gd").resolve()))
        script_targets = {e["target"] for e in _edges(r, "script")}
        self.assertIn(gs, script_targets)


if __name__ == "__main__":
    unittest.main()
