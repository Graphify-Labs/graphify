"""Regression coverage for Swift 5.9 macro declarations and calls (#4551).

`macro stringify(...) = #externalMacro(...)` parses as `macro_declaration`,
which was in neither the Swift `function_types` nor `class_types`, so the
whole declaration was dropped -- the symbol was invisible. A freestanding
call site `#stringify(...)` parses as `macro_invocation`, not
`call_expression`, so its call edge was lost too.
"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from graphify.extract import extract_swift


class TestSwiftMacroDeclarations(unittest.TestCase):
    def _extract(self, src: str) -> dict:
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "Macro.swift"
            p.write_text(src, encoding="utf-8")
            return extract_swift(p)

    def test_macro_declaration_becomes_a_node(self):
        r = self._extract(
            'macro stringify<T>(_ v: T) -> (T, String) = '
            '#externalMacro(module: "M", type: "S")\n'
        )
        labels = {n["label"] for n in r["nodes"]}
        self.assertTrue(
            any("stringify" in label for label in labels),
            f"expected a stringify node, got {sorted(labels)}",
        )

    def test_freestanding_macro_call_resolves_to_the_declaration(self):
        r = self._extract(
            'macro stringify<T>(_ v: T) -> (T, String) = '
            '#externalMacro(module: "M", type: "S")\n'
            'func use() { let x = #stringify(1 + 1) }\n'
        )
        macro_nid = next(n["id"] for n in r["nodes"] if "stringify" in n["label"])
        use_nid = next(n["id"] for n in r["nodes"] if n["label"] == "use()")
        calls = {(e["source"], e["target"]) for e in r["edges"] if e["relation"] == "calls"}
        self.assertIn((use_nid, macro_nid), calls)

    def test_calls_inside_a_macro_argument_still_resolve(self):
        r = self._extract(
            "func helper() -> Int { return 1 }\n"
            "func use() { let x = #stringify(helper() + 1) }\n"
        )
        helper_nid = next(n["id"] for n in r["nodes"] if n["label"] == "helper()")
        use_nid = next(n["id"] for n in r["nodes"] if n["label"] == "use()")
        calls = {(e["source"], e["target"]) for e in r["edges"] if e["relation"] == "calls"}
        self.assertIn((use_nid, helper_nid), calls)

    def test_attached_macro_attribute_usage_mints_no_node(self):
        """Attached-macro *usage* (`@AddCompletion` on a type) is an
        attribute, not a macro_invocation, and stays unresolved (fail
        closed) -- it must not mint a spurious node either."""
        r = self._extract("@AddCompletion\nstruct Foo {}\n")
        labels = {n["label"] for n in r["nodes"]}
        self.assertNotIn("AddCompletion", labels)
        self.assertIn("Foo", labels)
