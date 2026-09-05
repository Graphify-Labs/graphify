"""Streaming facts retain category order and bound retained parse roots."""
from __future__ import annotations

import weakref
from pathlib import Path

import pytest

from graphify.extractors import resolution
from graphify.extractors.models import _SymbolResolutionFacts, _SymbolUseFact


def sources(root: Path) -> list[Path]:
    texts = {
        "base.ts": "export class Base {}\nexport interface Shape {}\nexport function run() {}\n",
        "first.ts": 'import {Base, Shape, run} from "./base.js";\n'
        'const alias = run; export {alias};\n'
        'export default class First extends Base implements Shape { field: Shape; }\n'
        'function caller() { alias(); function nested() { run(); } }\n',
        "second.ts": 'import {run, Shape} from "./base.js";\n'
        'export * from "./base.js"; export * as ns from "./base.js";\n'
        'export type {Shape} from "./base.js";\n'
        'const arrow = () => run();\n'
        'class Second { method(value: Array<Shape>): Shape { return value[0]; } }\n',
    }
    for name, text in texts.items():
        (root / name).write_text(text)
    return [root / name for name in texts]


@pytest.mark.parametrize("duplicates", [False, True])
def test_ordered_facts_match_batch(tmp_path: Path, duplicates: bool) -> None:
    paths = sources(tmp_path)
    if duplicates:
        paths += [paths[1]]
    before = _SymbolUseFact(paths[0], "existing", "existing", "references", "type", 1)
    expected = _SymbolResolutionFacts(uses=[before])
    actual = _SymbolResolutionFacts(uses=[before])
    resolution._collect_js_symbol_resolution_facts_batch(paths, expected)
    resolution._collect_js_symbol_resolution_facts(paths, actual)
    assert actual == expected
    assert actual.uses[0] == before
    assert actual.aliases and actual.star_exports and actual.namespace_exports
    assert any(item.type_only for item in actual.exports)
    relations = [item.relation for item in actual.uses[1:]]
    last_call = max(i for i, relation in enumerate(relations) if relation == "calls")
    assert all(relation == "calls" for relation in relations[:last_call + 1])
    assert "inherits" in relations and "references" in relations


def test_duplicate_symlink_preserves_last_grammar(tmp_path: Path) -> None:
    paths = sources(tmp_path)
    link = tmp_path / "alias.js"
    try:
        link.symlink_to(paths[1])
    except OSError:
        pytest.skip("symlinks unavailable")
    paths.append(link)
    expected, actual = _SymbolResolutionFacts(), _SymbolResolutionFacts()
    resolution._collect_js_symbol_resolution_facts_batch(paths, expected)
    resolution._collect_js_symbol_resolution_facts(paths, actual)
    assert actual == expected


def test_previous_parse_root_released_before_next_file(tmp_path: Path, monkeypatch) -> None:
    paths = sources(tmp_path)
    parse = resolution._parse_js_tree
    roots = []

    class Root:
        def __init__(self, node):
            self.node = node

        def __getattr__(self, name):
            return getattr(self.node, name)

    def tracked(path):
        assert all(reference() is None for reference in roots)
        result = parse(path)
        assert result is not None
        source, node = result
        wrapped = Root(node)
        roots.append(weakref.ref(wrapped))
        return source, wrapped

    monkeypatch.setattr(resolution, "_parse_js_tree", tracked)
    resolution._collect_js_symbol_resolution_facts(paths, _SymbolResolutionFacts())
    assert len(roots) == len(paths)
    assert all(reference() is None for reference in roots)
