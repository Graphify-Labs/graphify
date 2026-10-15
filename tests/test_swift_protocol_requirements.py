"""Regression coverage for method requirements declared in a Swift protocol.

tree-sitter-swift gives a protocol's body-less method requirement its own node
type, ``protocol_function_declaration``, rather than reusing the
``function_declaration`` used inside a class/struct. The Swift config only
listed ``function_declaration``, so a protocol's method contract was dropped and
the protocol became an empty node -- the API surface every conformer must
implement never entered the graph.
"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from graphify.extract import extract_swift


def _labels(result):
    return [n["label"] for n in result["nodes"]]


class TestSwiftProtocolRequirements(unittest.TestCase):
    def _extract(self, src: str) -> dict:
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "Proto.swift"
            p.write_text(src, encoding="utf-8")
            return extract_swift(p)

    def test_protocol_method_requirements_become_methods(self):
        r = self._extract(
            "protocol Drawable {\n"
            "    func draw()\n"
            "    func area() -> Double\n"
            "}\n"
        )
        proto_nid = next(n["id"] for n in r["nodes"] if n["label"] == "Drawable")
        method_targets = {
            n["label"]
            for e in r["edges"]
            if e["relation"] == "method" and e["source"] == proto_nid
            for n in r["nodes"]
            if n["id"] == e["target"]
        }
        self.assertEqual(method_targets, {".draw()", ".area()"})

    def test_protocol_method_return_type_reference_is_captured(self):
        # The requirement's body-less signature still carries a return type.
        r = self._extract(
            "protocol Sized {\n"
            "    func area() -> Double\n"
            "}\n"
        )
        area_nid = next(n["id"] for n in r["nodes"] if n["label"] == ".area()")
        ref_targets = {
            n["label"]
            for e in r["edges"]
            if e["relation"] == "references" and e["source"] == area_nid
            for n in r["nodes"]
            if n["id"] == e["target"]
        }
        self.assertIn("Double", ref_targets)

    def test_protocol_and_conformer_methods_are_distinct_nodes(self):
        r = self._extract(
            "protocol Drawable {\n"
            "    func draw()\n"
            "}\n\n"
            "struct Circle: Drawable {\n"
            "    func draw() {}\n"
            "}\n"
        )
        proto_nid = next(n["id"] for n in r["nodes"] if n["label"] == "Drawable")
        circle_nid = next(n["id"] for n in r["nodes"] if n["label"] == "Circle")
        proto_draw = {
            e["target"] for e in r["edges"]
            if e["relation"] == "method" and e["source"] == proto_nid
        }
        circle_draw = {
            e["target"] for e in r["edges"]
            if e["relation"] == "method" and e["source"] == circle_nid
        }
        self.assertTrue(proto_draw and circle_draw)
        self.assertTrue(
            proto_draw.isdisjoint(circle_draw),
            "protocol requirement and conformer method collapsed onto one node",
        )
        # The conformance heritage edge is untouched.
        self.assertTrue(
            any(
                e["relation"] == "implements"
                and e["source"] == circle_nid
                and e["target"] == proto_nid
                for e in r["edges"]
            )
        )


if __name__ == "__main__":
    unittest.main()
