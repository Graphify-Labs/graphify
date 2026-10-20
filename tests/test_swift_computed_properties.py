"""Regression tests for #2181.

Swift computed properties (`var body: some View { … }`) and observed
properties (`willSet` / `didSet`) carry a body. Before the fix the Swift
extractor only recognised function/init/deinit/subscript as callables, so
those properties produced no node and their bodies were never walked -- which
for SwiftUI erased the entire view layer (`body` is a computed property).
"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from graphify.extract import extract_swift


def _labels(result):
    return [n["label"] for n in result["nodes"]]


def _rel(result, relation):
    return [e for e in result["edges"] if e["relation"] == relation]


class TestSwiftComputedProperties(unittest.TestCase):
    def _extract(self, src: str) -> dict:
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "View.swift"
            p.write_text(src, encoding="utf-8")
            return extract_swift(p)

    def test_computed_property_emits_node_and_walks_body(self):
        r = self._extract(
            "struct PlayerScrubber: View {\n"
            "    var body: some View {\n"
            "        VStack { doTap() }\n"
            "    }\n"
            "    var toggled: Int { 1 }\n"
            "    func doTap() {}\n"
            "}\n"
        )
        labels = _labels(r)
        # Both computed properties become nodes...
        self.assertIn(".body", labels)
        self.assertIn(".toggled", labels)
        # ...and the call inside `body` is attributed to the body node, not lost.
        call_pairs = {(e["source"], e["target"]) for e in _rel(r, "calls")}
        body_nid = next(n["id"] for n in r["nodes"] if n["label"] == ".body")
        dotap_nid = next(n["id"] for n in r["nodes"] if n["label"] == ".doTap()")
        self.assertIn((body_nid, dotap_nid), call_pairs,
                      "call inside computed `body` was not captured")

    def test_stored_property_not_emitted_as_member_but_keeps_type_ref(self):
        # A plain stored property has no body block: it must NOT become a
        # function-like node, but its type must still produce a references edge.
        r = self._extract(
            "struct S {\n"
            "    var vm: ViewModel\n"
            "}\n"
        )
        self.assertNotIn(".vm", _labels(r))
        ref_targets = {n["label"]
                       for e in _rel(r, "references")
                       for n in r["nodes"] if n["id"] == e["target"]}
        self.assertIn("ViewModel", ref_targets)

    def test_observed_property_body_is_walked(self):
        # willSet/didSet observers also carry a body whose calls used to vanish.
        r = self._extract(
            "class M {\n"
            "    var score: Int = 0 {\n"
            "        didSet { react() }\n"
            "    }\n"
            "    func react() {}\n"
            "}\n"
        )
        self.assertIn(".score", _labels(r))
        call_pairs = {(e["source"], e["target"]) for e in _rel(r, "calls")}
        score_nid = next(n["id"] for n in r["nodes"] if n["label"] == ".score")
        react_nid = next(n["id"] for n in r["nodes"] if n["label"] == ".react()")
        self.assertIn((score_nid, react_nid), call_pairs)


if __name__ == "__main__":
    unittest.main()
