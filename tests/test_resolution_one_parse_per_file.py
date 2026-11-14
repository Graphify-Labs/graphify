"""Symbol resolution must not hold every file's source and syntax tree at once."""
from __future__ import annotations

import gc
from pathlib import Path

from graphify.extractors import resolution


def _watch_parses(monkeypatch, parse_name: str) -> list[bytes]:
    real = getattr(resolution, parse_name)
    sources: list[bytes] = []

    def parse(path):
        # The loop's own variables keep the previous file alive until they are rebound,
        # so nothing but this list may still hold anything older than that.
        for index in range(len(sources) - 1):
            holders = [holder for holder in gc.get_referrers(sources[index]) if holder is not sources]
            assert not holders, "an earlier file's source is still held"
        parsed = real(path)
        if parsed is not None:
            sources.append(parsed[0])
        return parsed

    monkeypatch.setattr(resolution, parse_name, parse)
    return sources


def test_js_facts_hold_one_file_at_a_time(tmp_path: Path, monkeypatch) -> None:
    paths = []
    for name in ("a", "b", "c", "d"):
        path = tmp_path / f"{name}.ts"
        path.write_text(f"export function {name}() {{ return 1 }}\nclass K{name} {{ m() {{ {name}() }} }}\n")
        paths.append(path)
    sources = _watch_parses(monkeypatch, "_parse_js_tree")

    facts = resolution._SymbolResolutionFacts()
    resolution._collect_js_symbol_resolution_facts(paths, facts)

    assert len(sources) == 4


def test_java_import_rows_keep_every_form() -> None:
    from tree_sitter import Language, Parser
    import tree_sitter_java as tsjava

    source = (
        b"package p;\n"
        b"import q.Thing;\n"
        b"import static q.Other.helper;\n"
        b"import q.*;\n"
        b"class C {}\n"
    )
    tree = Parser(Language(tsjava.language())).parse(source)

    assert resolution._java_import_rows(tree.root_node, source) == [
        ("Thing", "q", 2),
        ("Other", "q", 3),
    ]
