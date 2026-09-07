"""Streaming facts retain category order and bound retained parse roots."""
from __future__ import annotations

import copy
import sys
from pathlib import Path

import pytest

from graphify.extractors import resolution
from graphify.extractors.base import _file_stem, _make_id
from graphify.extractors.models import (
    _NamespaceExportFact,
    _StarExportFact,
    _SymbolAliasFact,
    _SymbolDeclarationFact,
    _SymbolExportFact,
    _SymbolImportFact,
    _SymbolResolutionFacts,
    _SymbolUseFact,
)


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


@pytest.mark.parametrize("collector", [
    resolution._collect_js_symbol_resolution_facts,
    resolution._collect_js_symbol_resolution_facts_batch,
])
def test_exact_facts_preserve_original_collector_contract(tmp_path: Path, collector) -> None:
    base, first, second = sources(tmp_path)
    target = base.resolve()
    caller = _make_id(_file_stem(first), "caller")
    first_class = _make_id(_file_stem(first), "First")
    method = _make_id(_file_stem(second), "Second.method")
    # Explicit expected facts checked against 937e59a. Do not calculate this
    # oracle with either collector: both share the syntax-index implementation.
    expected = _SymbolResolutionFacts(
        declarations=[
            _SymbolDeclarationFact(base, "Base", 1),
            _SymbolDeclarationFact(base, "Shape", 2),
            _SymbolDeclarationFact(base, "run", 3),
            _SymbolDeclarationFact(first, "First", 3),
        ],
        imports=[
            _SymbolImportFact(first, "Base", target, "Base", 1),
            _SymbolImportFact(first, "Shape", target, "Shape", 1),
            _SymbolImportFact(first, "run", target, "run", 1),
            _SymbolImportFact(second, "run", target, "run", 1),
            _SymbolImportFact(second, "Shape", target, "Shape", 1),
        ],
        aliases=[_SymbolAliasFact(first, "alias", "run", 2)],
        exports=[
            _SymbolExportFact(base, "Base", 1, local_name="Base"),
            _SymbolExportFact(base, "Shape", 2, local_name="Shape"),
            _SymbolExportFact(base, "run", 3, local_name="run"),
            _SymbolExportFact(first, "alias", 2, local_name="alias"),
            _SymbolExportFact(first, "First", 3, local_name="First"),
            _SymbolExportFact(first, "default", 3, local_name="First"),
            _SymbolExportFact(second, "Shape", 3, target_path=target,
                              target_name="Shape", type_only=True),
        ],
        star_exports=[_StarExportFact(second, target, 2)],
        namespace_exports=[_NamespaceExportFact(second, "ns", target, 2)],
        uses=[
            _SymbolUseFact(first, caller, "alias", "calls", "call", 4),
            _SymbolUseFact(first, caller, "run", "calls", "call", 4),
            _SymbolUseFact(second, _make_id(_file_stem(second), "arrow"),
                           "run", "calls", "call", 4),
            _SymbolUseFact(first, first_class, "Base", "inherits", "type", 3),
            _SymbolUseFact(first, first_class, "Shape", "implements", "type", 3),
            _SymbolUseFact(first, first_class, "Shape", "references", "field", 3),
            _SymbolUseFact(second, method, "Array", "references", "parameter_type", 5),
            _SymbolUseFact(second, method, "Shape", "references", "generic_arg", 5),
            _SymbolUseFact(second, method, "Shape", "references", "return_type", 5),
        ],
    )
    actual = _SymbolResolutionFacts()
    collector([base, first, second], actual)
    assert actual == expected

    # Every existing category must remain a prefix, including Python's
    # module_imports, which JS collection does not produce.
    actual.module_imports.append((base, first, 1, "existing"))
    prefix = copy.deepcopy(actual)
    collector([base, first, second], actual)
    for name, previous in vars(prefix).items():
        assert getattr(actual, name) == previous + getattr(expected, name)


@pytest.mark.parametrize("last_grammar", ["js", "ts", "duplicate"])
def test_duplicate_symlink_preserves_last_grammar(
    tmp_path: Path, requires_symlinks, last_grammar: str,
) -> None:
    source = tmp_path / "source.ts"
    source.write_text("export interface Shape {}\nexport function run() {}\n")
    link = tmp_path / "alias.js"
    link.symlink_to(source)
    paths = {"js": [source, link], "ts": [link, source],
             "duplicate": [source, source]}[last_grammar]
    # Declarations use each input's grammar, but exports use the last
    # successful parse for that resolved path. These expectations are frozen
    # from the original collector, not from the compatibility helper.
    expected = _SymbolResolutionFacts()
    for path in paths:
        if path.suffix == ".ts":
            expected.declarations.append(_SymbolDeclarationFact(path, "Shape", 1))
        expected.declarations.append(_SymbolDeclarationFact(path, "run", 2))
        if last_grammar != "js":
            expected.exports.append(_SymbolExportFact(path, "Shape", 1, local_name="Shape"))
        expected.exports.append(_SymbolExportFact(path, "run", 2, local_name="run"))
    actual = _SymbolResolutionFacts()
    resolution._collect_js_symbol_resolution_facts(paths, actual)
    assert actual == expected


def test_class_relations_stay_interleaved_in_file_order(tmp_path: Path) -> None:
    first, second = tmp_path / "a.ts", tmp_path / "b.ts"
    for path in (first, second):
        path.write_text("function caller() { run(); }\n"
                        "class Child extends Parent { field: Shape; }\n")
    expected_calls = [
        _SymbolUseFact(path, _make_id(_file_stem(path), "caller"),
                       "run", "calls", "call", 1)
        for path in (first, second)
    ]
    expected_types = [
        _SymbolUseFact(first, _make_id(_file_stem(first), "Child"),
                       "Parent", "inherits", "type", 2),
        _SymbolUseFact(first, _make_id(_file_stem(first), "Child"),
                       "Shape", "references", "field", 2),
        _SymbolUseFact(second, _make_id(_file_stem(second), "Child"),
                       "Parent", "inherits", "type", 2),
        _SymbolUseFact(second, _make_id(_file_stem(second), "Child"),
                       "Shape", "references", "field", 2),
    ]
    actual = _SymbolResolutionFacts()
    resolution._collect_js_symbol_resolution_facts([first, second], actual)
    assert actual.uses == expected_calls + expected_types


@pytest.mark.skipif(sys.implementation.name != "cpython", reason="uses CPython reference counts")
def test_previous_native_tree_released_before_next_parse(tmp_path: Path, monkeypatch) -> None:
    import tree_sitter

    paths = sources(tmp_path)
    parser_type = tree_sitter.Parser
    retained = []
    parsed_count = 0

    def release_previous_tree():
        if retained:
            # Native Nodes each retain their Tree, including descendants whose
            # root has gone away. Only this list and getrefcount's argument may
            # still own the tree. Clear our final reference before parsing.
            references = sys.getrefcount(retained[0])
            assert references == 2
            retained.clear()

    class TrackedParser:
        def __init__(self, *args, **kwargs):
            self.parser = parser_type(*args, **kwargs)

        def parse(self, *args, **kwargs):
            nonlocal parsed_count
            release_previous_tree()
            tree = self.parser.parse(*args, **kwargs)
            retained.append(tree)
            parsed_count += 1
            return tree

    monkeypatch.setattr(tree_sitter, "Parser", TrackedParser)
    resolution._collect_js_symbol_resolution_facts(paths, _SymbolResolutionFacts())
    assert parsed_count == len(paths)
    release_previous_tree()
