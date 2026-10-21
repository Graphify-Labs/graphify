"""`}` and `from '...'` on separate lines: valid JS the grammar splits in two."""
from graphify.extract import extract


def _graph(tmp_path, files):
    paths = []
    for name, text in files.items():
        p = tmp_path / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
        paths.append(p)
    return extract(paths, root=tmp_path, cache_root=tmp_path, parallel=False)


def _imports_from(graph, source):
    return {e["target"] for e in graph["edges"] if e["relation"] == "imports_from" and e["source"] == source}


def test_multiline_export_clause_with_from_on_its_own_line(tmp_path):
    g = _graph(tmp_path, {
        "ui/index.js": (
            "export {\n    default as Tabs\n}\nfrom './Tabs.vue'\n"
            "export {\n    default as TabsList\n}\nfrom \"./TabsList.vue\"\n"
            "export { Foo } from './foo'\n"
        ),
        "ui/Tabs.vue": "<template><div/></template>\n<script setup>\nconst a = 1\n</script>\n",
        "ui/TabsList.vue": "<template><div/></template>\n<script setup>\nconst b = 1\n</script>\n",
        "ui/foo.js": "export const Foo = 1\n",
    })
    targets = _imports_from(g, "ui_index")
    assert "ui_tabs" in targets
    assert "ui_tabslist" in targets
    assert "ui_foo" in targets


def test_split_from_keeps_symbol_reexport(tmp_path):
    g = _graph(tmp_path, {
        "a/index.ts": "export {\n  Foo\n}\nfrom './foo'\n",
        "a/foo.ts": "export const Foo = 1\n",
    })
    edges = [e for e in g["edges"] if e["source"] == "a_index" and e["relation"] == "re_exports"]
    assert edges and edges[0]["target"] == "a_foo_foo"


def test_import_clause_with_from_on_its_own_line(tmp_path):
    g = _graph(tmp_path, {
        "m.js": "import {\n  Foo\n}\nfrom './foo'\nexport const x = Foo\n",
        "foo.js": "export const Foo = 1\n",
    })
    assert "foo" in _imports_from(g, "m")
