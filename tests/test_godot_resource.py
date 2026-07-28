import shutil
import tempfile
import unittest
from pathlib import Path

from graphify.extract import extract_godot_resource, _make_id, _file_stem
from graphify.extractors import godot_resource as gr

_FIXTURES = Path(__file__).parent / "fixtures" / "godot" / "resource"


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


class _FixtureProject(unittest.TestCase):
    """Copy the fixture Godot project into an isolated temp dir per test."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "proj"
        shutil.copytree(_FIXTURES, self.root)

    def tearDown(self):
        self.tmp.cleanup()


class TestGodotResource(_FixtureProject):
    """The .tscn/.tres/project.godot extractor (grammar path when available)."""

    def test_scene_script_subscene_and_connection(self):
        p = self.root / "scenes" / "Main.tscn"
        r = extract_godot_resource(p)

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
        p = self.root / "project.godot"
        r = extract_godot_resource(p)

        self.assertTrue(_edges(r, "autoload"), "no autoload edge emitted")
        self.assertTrue(_edges(r, "main_scene"), "no main_scene edge emitted")

        gstate = _make_id(str((self.root / "scripts" / "game_state.gd").resolve()))
        script_targets = {e["target"] for e in _edges(r, "script")}
        self.assertIn(gstate, script_targets)

    def test_line_parser_fallback_matches(self):
        # Force the dependency-free line parser (as if the grammar were absent)
        # and confirm it still emits the same edges the default path produces.
        scene = self.root / "scenes" / "Main.tscn"
        default = extract_godot_resource(scene)
        saved = gr._RESOURCE_PARSER
        try:
            gr._RESOURCE_PARSER = None          # disable grammar -> line parser
            forced_lines = extract_godot_resource(scene)
        finally:
            gr._RESOURCE_PARSER = saved
        self.assertEqual(_norm(default), _norm(forced_lines))


@unittest.skipUnless(gr._load_resource_parser() is not None,
                     "godot_resource grammar (tree-sitter-language-pack) not installed")
class TestGodotResourceGrammar(_FixtureProject):
    """Behaviour specific to the grammar front end."""

    def test_grammar_and_line_parsers_agree(self):
        scene = self.root / "scenes" / "Main.tscn"
        text = scene.read_text()
        via_grammar = gr._build_scene(scene, gr._blocks_from_grammar(text))
        via_lines = gr._build_scene(scene, gr._blocks_from_lines(text))
        self.assertEqual(_norm(via_grammar), _norm(via_lines))

    def test_grammar_survives_bracket_in_quoted_value(self):
        # A ']' inside a quoted attribute value (node name "Odd]Name") trips the
        # line-regex section matcher but the grammar parses it correctly.
        scene = self.root / "weird.tscn"
        r = extract_godot_resource(scene)
        enemy_gd = _make_id(str((self.root / "scripts" / "enemy.gd").resolve()))
        attaches = {e["target"] for e in _edges(r, "attaches_script")}
        self.assertIn(enemy_gd, attaches)


if __name__ == "__main__":
    unittest.main()
