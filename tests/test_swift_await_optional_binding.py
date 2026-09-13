"""Regression tests for #3540.

tree-sitter-swift (0.7.3, the only published release) accepts `await` in an
`if let` binding ONLY when the operand is a direct call. Valid Swift 6 such as
`if let r = await pending`, `if let r = await box.rings` and
`if let r = try await mint()` all parse as ERROR, so the file is reported as
"partially extracted" and every rule downstream walks a damaged subtree.
`guard let` with the same operand parses, which places the gap in the
if/while binding rule rather than in `await` itself.

The repair blanks the `await` with SPACES instead of deleting it, so the
repaired source is byte-for-byte the same length and every offset, line and
column downstream still points where it did.
"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from graphify.extract import extract_swift

from graphify.extractors.engine import _swift_blank_await_bindings

PREAMBLE = """import Foundation

struct Rings { let move: Double = 0 }

func fetchRings() async -> Rings? { nil }
"""

# A declaration after the binding, so "the file still parsed past it" is
# something the assertions can see rather than something they assume.
SENTINEL = "\nstruct SentinelType { let marker = 1 }\n"


class TestSwiftAwaitOptionalBinding(unittest.TestCase):
    def _extract(self, body: str) -> dict:
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "Await.swift"
            p.write_text(PREAMBLE + body + SENTINEL, encoding="utf-8")
            return extract_swift(p)

    def test_every_await_binding_shape_parses(self):
        """The four shapes the report measured, plus `while` and `var`."""
        bodies = {
            "await a bare identifier": (
                "func load() async {\n"
                "    async let pending = fetchRings()\n"
                "    if let r = await pending { print(r.move) }\n"
                "}\n"
            ),
            "await a member": (
                "func load(box: Box) async {\n"
                "    if let r = await box.rings { print(r.move) }\n"
                "}\n"
            ),
            "try await a call": (
                "func load() async throws {\n"
                "    if let r = try await fetchRings() { print(r.move) }\n"
                "}\n"
            ),
            "if var": (
                "func load() async {\n"
                "    async let pending = fetchRings()\n"
                "    if var r = await pending { print(r.move) }\n"
                "}\n"
            ),
            "while let": (
                "func load() async {\n"
                "    async let pending = fetchRings()\n"
                "    while let r = await pending { print(r.move) }\n"
                "}\n"
            ),
        }
        for name, body in bodies.items():
            with self.subTest(name):
                result = self._extract(body)
                # `parse_errors`, plural — the key the extractor actually
                # sets. The singular spelling is never present, so asserting
                # on it passes for a file that failed to parse.
                self.assertEqual(result.get("parse_errors"), None, name)
                # Arrival: the file really was walked, so the absence above is
                # a clean parse and not an empty result.
                self.assertIn("SentinelType", [n["label"] for n in result["nodes"]])

    def test_a_direct_call_operand_was_never_broken(self):
        """Accept control. `await` + a direct call always parsed, so a rule
        that "fixed" it would be repairing nothing and could only add risk."""
        result = self._extract(
            "func load() async {\n"
            "    if let r = await fetchRings() { print(r.move) }\n"
            "}\n"
        )
        self.assertEqual(result.get("parse_errors"), None)
        self.assertIn("SentinelType", [n["label"] for n in result["nodes"]])

    def test_the_repair_preserves_every_byte_offset(self):
        """The property the whole approach rests on: same length, so every
        node's start/end byte still addresses the text it did."""
        for source in (
            b"if let r = await pending {",
            b"if let r = try await mint() {",
            b"while var r = await box.rings {",
            b"if let r = await fetchRings() {",
            b"guard let r = await pending else {",
        ):
            with self.subTest(source.decode()):
                self.assertEqual(len(_swift_blank_await_bindings(source)), len(source))

    def test_the_repair_leaves_everything_else_alone(self):
        """It rewrites the binding operand and nothing else — not a `guard`,
        which the grammar already accepts, and not an `await` in a statement
        position."""
        for untouched in (
            b"guard let r = await pending else { return }",
            b"let r = await pending",
            b"await doThing()",
            b"// if let r = await pending\n",
        ):
            with self.subTest(untouched.decode()):
                self.assertEqual(_swift_blank_await_bindings(untouched), untouched)
