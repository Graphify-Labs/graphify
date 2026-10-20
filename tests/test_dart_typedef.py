"""Dart `typedef` declarations are type aliases, not variables of type `typedef`.

The typedef pattern accepted no parentheses, so a function-type alias
(`typedef Callback = void Function(int);`) never matched it, and an alias of a
builtin (`typedef JsonMap = Map<String, dynamic>;`) matched but was skipped.
Both then fell through to the variable pattern, which read the line as a
variable named `Callback` whose type is `typedef`: the file grew a
`references` edge to a SOURCELESS node labelled `typedef`, one per file using
the keyword. The legacy form (`typedef int Compare(Object a, Object b);`)
matched nothing at all, so references to it had no declaration to land on.
A legacy typedef whose return type is itself a function type
(`typedef int Function(int) Make();`) was named `Function`, after the return
type's head, and `Make` got no node.
"""
from __future__ import annotations

import textwrap
from pathlib import Path

from graphify.extract import extract_dart

_SOURCE = textwrap.dedent("""\
    typedef Callback = void Function(int);
    typedef JsonMap = Map<String, dynamic>;
    typedef Mapper<T> = T Function(T value);
    typedef UserList = List<User>;
    typedef Lookup = Repo;
    typedef int Compare(Object a, Object b);
    typedef void onTap();

    class User {}
    class Repo {}
    """)


def _extract(tmp_path: Path, source: str = _SOURCE) -> dict:
    path = tmp_path / "types.dart"
    path.write_text(source, encoding="utf-8")
    return extract_dart(path)


def test_no_node_or_edge_for_the_typedef_keyword(tmp_path: Path):
    result = _extract(tmp_path)
    assert [n for n in result["nodes"] if n["label"] == "typedef"] == []
    assert [e for e in result["edges"] if e["target"] == "typedef"] == []


def test_every_typedef_form_is_a_sourced_node_on_its_line(tmp_path: Path):
    result = _extract(tmp_path)
    expected = {"Callback": "L1", "JsonMap": "L2", "Mapper": "L3", "UserList": "L4",
                "Lookup": "L5", "Compare": "L6", "onTap": "L7"}
    for label, line in expected.items():
        matches = [n for n in result["nodes"] if n["label"] == label]
        assert len(matches) == 1, label
        assert matches[0]["source_file"], label
        assert matches[0]["source_location"] == line, label


def test_each_typedef_is_defined_once_by_the_file(tmp_path: Path):
    result = _extract(tmp_path)
    by_label = {n["label"]: n["id"] for n in result["nodes"]}
    for label in ("Callback", "JsonMap", "Compare", "onTap"):
        defines = [e for e in result["edges"]
                   if e["relation"] == "defines" and e["target"] == by_label[label]]
        assert len(defines) == 1, label


def test_an_alias_of_a_named_type_still_references_it(tmp_path: Path):
    """The pre-existing typedef edge is kept for a plain named target."""
    result = _extract(tmp_path)
    by_id = {n["id"]: n["label"] for n in result["nodes"]}
    refs = {(by_id.get(e["source"]), by_id.get(e["target"]))
            for e in result["edges"] if e.get("context") == "typedef"}
    assert ("Lookup", "Repo") in refs
    # A function type's head is its return type, not an aliased type, and
    # builtins (`Map`) are never referenced.
    assert not any(src == "Callback" or src == "JsonMap" for src, _ in refs)


def test_a_typedef_line_is_not_a_variable(tmp_path: Path):
    result = _extract(tmp_path)
    assert not any(e.get("context") == "variable_type" for e in result["edges"])


def test_a_legacy_typedef_returning_a_function_type_is_named_by_its_own_name(tmp_path: Path):
    result = _extract(tmp_path, textwrap.dedent("""\
        typedef int Function(int) Make();
        typedef void Function() Callback(String s);
        typedef int Function(int)? MaybeMake();
        typedef Map<String, int> Function(int a, String b) Build();
        """))
    labels = {n["label"]: n["source_location"] for n in result["nodes"] if n.get("source_file")}
    assert {"Make": "L1", "Callback": "L2", "MaybeMake": "L3", "Build": "L4"}.items() <= labels.items()
    assert "Function" not in labels
