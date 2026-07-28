import shutil
import tempfile
import unittest
from pathlib import Path

from graphify.extract import extract_gdscript, _make_id, _file_stem
from graphify.extractors.gdscript import _load_gdscript_parser

_HAS_GRAMMAR = _load_gdscript_parser() is not None
_FIXTURES = Path(__file__).parent / "fixtures" / "godot" / "gdscript"


def _rels(result):
    return {e["relation"] for e in result["edges"]}


def _edge(result, relation):
    return [e for e in result["edges"] if e["relation"] == relation]


@unittest.skipUnless(_HAS_GRAMMAR, "tree-sitter-gdscript grammar not installed")
class TestGDScript(unittest.TestCase):
    def setUp(self):
        # Copy the fixture project into a temp dir so res:// resolution and the
        # per-project autoload cache anchor on a real, isolated project root.
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "proj"
        shutil.copytree(_FIXTURES, self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def test_class_extends_functions_signals_calls(self):
        p = self.root / "enemy.gd"
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
        caller = self.root / "player.gd"
        r = extract_gdscript(caller)
        # the call must target analytics.gd's track function node, NOT a bare anchor
        want = _make_id(_file_stem(self.root / "analytics.gd"), "track")
        resolved = [e for e in _edge(r, "calls") if e.get("context") == "Analytics"]
        self.assertTrue(resolved, "no autoload-resolved call edge emitted")
        self.assertEqual(resolved[0]["target"], want)
        # a bare `track()` anchor must NOT have been created
        self.assertFalse(any(n["label"] == "track()" for n in r["nodes"]))

    def test_missing_grammar_is_graceful(self):
        # Even with a grammar present, an empty file yields just the file node.
        p = self.root / "empty.gd"
        r = extract_gdscript(p)
        self.assertTrue(any(n["label"] == "empty.gd" for n in r["nodes"]))
        self.assertNotIn("error", r)


if __name__ == "__main__":
    unittest.main()
