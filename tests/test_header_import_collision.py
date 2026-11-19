import pytest

from graphify.build import build
from graphify.extract import extract


@pytest.mark.parametrize(("suffix", "module", "consumer"), [
    (".py", "def run(): return 1\n", "import foo\n"),
    (".ts", "export function run() { return 1; }\n", "import { run } from './foo';\nrun();\n"),
])
def test_header_does_not_capture_other_languages(tmp_path, suffix, module, consumer):
    sources = {"foo.h": "int run(void);\n", "foo.c": '#include "foo.h"\n',
               f"foo{suffix}": module, f"consumer{suffix}": consumer}
    for name, content in sources.items():
        (tmp_path / name).write_text(content, encoding="utf-8")
    raw = extract([tmp_path / name for name in sources], root=tmp_path,
                  cache_root=tmp_path, parallel=False)
    graph = build([raw], root=tmp_path, directed=True)
    imports = {
        (attrs["source_file"], graph.nodes[target].get("source_file"))
        for _, target, attrs in graph.edges(data=True)
        if attrs.get("relation") in {"imports", "imports_from"}
    }
    assert ("foo.c", "foo.h") in imports
    assert (f"consumer{suffix}", f"foo{suffix}") in imports


def test_explicit_import_target_wins_over_header_fallback(tmp_path):
    from graphify.extractors.resolution import _disambiguate_colliding_node_ids

    nodes = [{"id": "foo", "source_file": name, "label": name}
             for name in ("foo.h", "foo.ts", "foo.mjs")]
    edge = {"source": "consumer", "target": "foo", "relation": "imports",
            "source_file": "consumer.ts", "target_file": str(tmp_path / "foo.mjs")}
    _disambiguate_colliding_node_ids(nodes, [edge], [], tmp_path)
    assert edge["target"] == nodes[2]["id"]
    assert "target_file" not in edge
