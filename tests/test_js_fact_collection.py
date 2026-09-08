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


def test_exact_facts_preserve_original_collector_contract(tmp_path: Path) -> None:
    collector = resolution._collect_js_symbol_resolution_facts
    base, first, second = sources(tmp_path)
    target = base.resolve()
    caller = _make_id(_file_stem(first), "caller")
    first_class = _make_id(_file_stem(first), "First")
    method = _make_id(_file_stem(second), "Second.method")
    # Explicit expected facts checked against 937e59a. Do not calculate this
    # oracle with the collector or its group helper: they share syntax indexing.
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


@pytest.mark.skipif(sys.implementation.name != "cpython", reason="uses CPython reference counts")
def test_duplicate_group_releases_native_trees_before_unrelated_file(
    tmp_path: Path, requires_symlinks, monkeypatch,
) -> None:
    import tree_sitter

    source, unrelated = tmp_path / "source.ts", tmp_path / "unrelated.ts"
    source.write_text("export interface Shape {}\nexport function run() {}\n")
    unrelated.write_text("export function independent() {}\n")
    alias = tmp_path / "alias.js"
    alias.symlink_to(source)
    parser_type = tree_sitter.Parser
    retained = []
    parsed_count = 0
    unrelated_references = []

    def release_group():
        # This intentionally depends on CPython and tree-sitter's ownership
        # contract. An extra reference can be a leaked Node; do not tolerate it.
        references = [sys.getrefcount(tree) for tree in retained]
        assert all(count == 3 for count in references)  # list, loop local, argument
        retained.clear()

    class TrackedParser:
        def __init__(self, *args, **kwargs):
            self.parser = parser_type(*args, **kwargs)

        def parse(self, source_bytes, *args, **kwargs):
            nonlocal parsed_count
            if source_bytes == unrelated.read_bytes():
                unrelated_references.extend(sys.getrefcount(tree) for tree in retained)
                retained.clear()
            tree = self.parser.parse(source_bytes, *args, **kwargs)
            retained.append(tree)
            parsed_count += 1
            return tree

    monkeypatch.setattr(tree_sitter, "Parser", TrackedParser)
    resolution._collect_js_symbol_resolution_facts(
        [source, unrelated, alias, source], _SymbolResolutionFacts(),
    )
    assert parsed_count == 4
    assert unrelated_references and all(count == 3 for count in unrelated_references)
    release_group()


@pytest.mark.parametrize("last_grammar", ["js", "ts", "duplicate"])
def test_interleaved_groups_preserve_every_fact_category(
    tmp_path: Path, requires_symlinks, last_grammar: str,
) -> None:
    source, other, target = [tmp_path / name for name in ("source.ts", "other.ts", "target.ts")]
    target.write_text("export function run() {}\n")
    text = ('export interface Shape {}\n'
            'import {run} from "./target.ts";\n'
            'const alias = run; export {alias};\n'
            'export * from "./target.ts"; export * as ns from "./target.ts";\n'
            'function caller() { alias(); }\n'
            'class Child extends Parent { field: Shape; }\n')
    source.write_text(text)
    other.write_text(text)
    link = tmp_path / "alias.js"
    link.symlink_to(source)
    ignored = tmp_path / "ignored.py"
    paths = {"js": [source, ignored, other, link, other],
             "ts": [link, ignored, other, source, other],
             "duplicate": [source, ignored, other, source, other]}[last_grammar]
    # Each category follows input occurrence order, even across two interleaved
    # groups. First-pass declarations use the input grammar, while exports use
    # the last successful grammar for that resolved file.
    expected = _SymbolResolutionFacts()
    class_uses = []
    for path in paths:
        if path == ignored:
            continue
        if path.suffix == ".ts":
            expected.declarations.append(_SymbolDeclarationFact(path, "Shape", 1))
        expected.imports.append(_SymbolImportFact(path, "run", target.resolve(), "run", 2))
        expected.aliases.append(_SymbolAliasFact(path, "alias", "run", 3))
        if path == other or last_grammar != "js":
            expected.exports.append(_SymbolExportFact(path, "Shape", 1, local_name="Shape"))
        expected.exports.append(_SymbolExportFact(path, "alias", 3, local_name="alias"))
        expected.star_exports.append(_StarExportFact(path, target.resolve(), 4))
        expected.namespace_exports.append(_NamespaceExportFact(path, "ns", target.resolve(), 4))
        expected.uses.append(_SymbolUseFact(
            path, _make_id(_file_stem(path), "caller"), "alias", "calls", "call", 5,
        ))
        class_id = _make_id(_file_stem(path), "Child")
        class_uses.append(_SymbolUseFact(path, class_id, "Parent", "inherits", "type", 6))
        if path == other or last_grammar != "js":
            class_uses.append(_SymbolUseFact(path, class_id, "Shape", "references", "field", 6))
    expected.uses.extend(class_uses)
    actual = _SymbolResolutionFacts()
    resolution._collect_js_symbol_resolution_facts(paths, actual)
    assert actual == expected


@pytest.mark.parametrize("failed", ["first", "last", "all"])
def test_group_reuses_last_successful_parse_after_failures(
    tmp_path: Path, requires_symlinks, monkeypatch, failed: str,
) -> None:
    source, other = tmp_path / "source.ts", tmp_path / "other.ts"
    source.write_text("export interface Shape {}\nexport function run() {}\n")
    other.write_text("export function independent() {}\n")
    alias = tmp_path / "alias.js"
    alias.symlink_to(source)
    paths = [source, other, alias]
    failed_paths = {"first": {source}, "last": {alias}, "all": {source, alias}}[failed]
    parse = resolution._parse_js_tree
    monkeypatch.setattr(resolution, "_parse_js_tree",
                        lambda path: None if path in failed_paths else parse(path))
    expected = _SymbolResolutionFacts()
    for path in paths:
        if path == other:
            expected.declarations.append(_SymbolDeclarationFact(path, "independent", 1))
            expected.exports.append(_SymbolExportFact(path, "independent", 1,
                                                       local_name="independent"))
            continue
        if path not in failed_paths:
            if path == source:
                expected.declarations.append(_SymbolDeclarationFact(path, "Shape", 1))
            expected.declarations.append(_SymbolDeclarationFact(path, "run", 2))
        if failed == "all":
            continue
        if failed == "last":
            expected.exports.append(_SymbolExportFact(path, "Shape", 1, local_name="Shape"))
        expected.exports.append(_SymbolExportFact(path, "run", 2, local_name="run"))
    actual = _SymbolResolutionFacts()
    resolution._collect_js_symbol_resolution_facts(paths, actual)
    assert actual == expected
