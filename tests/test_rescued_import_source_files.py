"""Unresolved import specifiers are references, never filesystem provenance."""
from pathlib import Path
import tempfile
import unittest

from graphify.build import build_from_json
from graphify.extract import _make_id, extract


class RescuedImportSourcesTests(unittest.TestCase):
    def test_unresolved_imports_retain_edges_without_inventing_source_files(self):
        specifiers = ("unknown-package", "./not-created.js", "/node_modules/.vite/deps/react.js")
        for suffix in ("js", "ts", "svelte", "astro", "vue"):
            with self.subTest(suffix=suffix), tempfile.TemporaryDirectory() as directory:
                root = Path(directory).resolve()
                body = "\n".join(f"const value{i} = import({raw!r});" for i, raw in enumerate(specifiers))
                if suffix in ("svelte", "vue"):
                    body = f"<script>\n{body}\n</script>\n<div />\n"
                elif suffix == "astro":
                    body = f"---\n{body}\n---\n<div />\n"
                source = root / f"entry.{suffix}"
                source.write_text(body, encoding="utf-8")
                result = extract([source], root=root, cache_root=root, parallel=False)
                for raw in specifiers:
                    nodes = [n for n in result["nodes"] if n.get("label") == raw]
                    self.assertEqual(len(nodes), 1, (raw, result["nodes"]))
                    self.assertEqual(nodes[0].get("source_file"), "", raw)
                    self.assertNotIn(_make_id(str(root)), nodes[0]["id"])
                    self.assertNotIn("_unresolved_import", nodes[0])
                    edges = [e for e in result["edges"] if e["target"] == nodes[0]["id"]]
                    self.assertTrue(edges, raw)
                    self.assertTrue(all(e.get("source_file") == source.name for e in edges))
                graph = build_from_json(result, root=str(root))
                for _, attrs in graph.nodes(data=True):
                    path = attrs.get("source_file")
                    if path:
                        self.assertTrue((root / path).is_file(), path)
                # Astro may reuse its raw AST cache. The transient marker
                # must survive in that cache and be consumed on every return.
                warm = extract([source], root=root, cache_root=root, parallel=False)
                self.assertEqual(result["nodes"], warm["nodes"])
                self.assertEqual(result["edges"], warm["edges"])

    def test_resolved_import_keeps_real_target_and_importing_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            target = root / "local.js"
            target.write_text("export const useful = 1;\n", encoding="utf-8")
            source = root / "entry.js"
            source.write_text("export const loaded = import('./local.js');\n", encoding="utf-8")
            result = extract([source, target], root=root, cache_root=root, parallel=False)
            nodes = {n["id"]: n for n in result["nodes"]}
            edges = [e for e in result["edges"] if e.get("relation") == "dynamic_import"]
            self.assertTrue(edges)
            self.assertTrue(all(e.get("source_file") == "entry.js" for e in edges))
            self.assertTrue(all(nodes[e["target"]].get("source_file") == "local.js" for e in edges))


if __name__ == "__main__":
    unittest.main()
