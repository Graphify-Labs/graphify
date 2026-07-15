import tempfile
import textwrap
import unittest
from pathlib import Path

from graphify.extract import extract_gdscript, _make_id, _file_stem
from graphify.extractors.gdscript import _load_gdscript_parser

_HAS_GRAMMAR = _load_gdscript_parser() is not None


def _rels(result):
    return {e["relation"] for e in result["edges"]}


def _edge(result, relation):
    return [e for e in result["edges"] if e["relation"] == relation]


@unittest.skipUnless(_HAS_GRAMMAR, "tree-sitter-gdscript grammar not installed")
class TestGDScript(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "project.godot").write_text("config_version=5\n")

    def tearDown(self):
        self.tmp.cleanup()

    def _write(self, name, body):
        p = self.root / name
        p.write_text(textwrap.dedent(body))
        return p

    def test_class_extends_functions_signals_calls(self):
        (self.root / "audio.gd").write_text("extends Node\nclass_name AudioManager\n")
        p = self._write("enemy.gd", """
            class_name Enemy
            extends CharacterBody2D

            signal died(reason)

            func _ready():
                died.connect(_on_died)
                sprite.play("idle")

            func take_damage(amount):
                if amount > 0:
                    emit_signal("died", "killed")
                    die()

            func die():
                var fx = preload("res://audio.gd")
                queue_free()

            func _on_died(reason):
                print(reason)
        """)
        r = extract_gdscript(p)
        rels = _rels(r)
        for expected in ("defines", "extends", "declares", "emits", "connects", "calls", "imports"):
            self.assertIn(expected, rels, f"missing relation {expected}")

        # class node id
        stem = _file_stem(p)
        enemy_nid = _make_id(stem, "Enemy")
        labels = {n["id"]: n["label"] for n in r["nodes"]}
        self.assertEqual(labels.get(enemy_nid), "Enemy")

        # extends target is the base type
        ext = _edge(r, "extends")[0]
        self.assertEqual(labels.get(ext["target"]), "CharacterBody2D")

        # local call resolves to the DEFINED die() (same id, no orphan anchor)
        die_nid = _make_id(stem, "die")
        calls_targets = {e["target"] for e in _edge(r, "calls")}
        self.assertIn(die_nid, calls_targets)

        # signal connect resolves handler to the local function
        on_died_nid = _make_id(stem, "_on_died")
        conn = _edge(r, "connects")[0]
        self.assertEqual(conn["target"], on_died_nid)

        # preload resolves res:// to the real file node id
        audio_nid = _make_id(str((self.root / "audio.gd").resolve()))
        imports_targets = {e["target"] for e in _edge(r, "imports")}
        self.assertIn(audio_nid, imports_targets)

    def test_autoload_method_call_resolves_to_script_function(self):
        # project.godot registers Analytics as an autoload -> analytics.gd
        (self.root / "project.godot").write_text(
            'config_version=5\n\n[autoload]\nAnalytics="*res://analytics.gd"\n'
        )
        analytics = self.root / "analytics.gd"
        analytics.write_text("extends Node\nfunc track(name):\n\tpass\n")
        caller = self._write("player.gd", """
            extends Node
            func attack():
                Analytics.track("hit")
        """)
        r = extract_gdscript(caller)
        # the call must target analytics.gd's track function node, NOT a bare anchor
        want = _make_id(_file_stem(analytics), "track")
        resolved = [e for e in _edge(r, "calls") if e.get("context") == "Analytics"]
        self.assertTrue(resolved, "no autoload-resolved call edge emitted")
        self.assertEqual(resolved[0]["target"], want)
        # a bare `track()` anchor must NOT have been created
        self.assertFalse(any(n["label"] == "track()" for n in r["nodes"]))

    def test_missing_grammar_is_graceful(self):
        # Even with a grammar present, an empty file yields just the file node.
        p = self._write("empty.gd", "")
        r = extract_gdscript(p)
        self.assertTrue(any(n["label"] == "empty.gd" for n in r["nodes"]))
        self.assertNotIn("error", r)


if __name__ == "__main__":
    unittest.main()
