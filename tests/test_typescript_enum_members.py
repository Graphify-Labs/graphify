"""TypeScript enum members get a node and a `case_of` edge, like Java's (#1719).

`enum_declaration` is in `_TS_CONFIG.class_types` with the comment "parity with
Java/C#", but only the container half was done: the enum type was a node while
its members were not, leaving the type a leaf. Java has emitted a node per
`enum_constant` with a `case_of` edge since #1719 and Kotlin since #1738 (both
from #1700), and Swift does the same for `enum_entry`.

TS spells a member two ways. A bare `Red` is a `property_identifier`; `Green = 5`
is an `enum_assignment` whose `name` is a `property_identifier`, or a `string`
when the member is quoted. Both live directly under `enum_body`, which is what
keeps this off the `property_identifier` nodes elsewhere in a file.
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

from graphify.extract import extract


def _extract(tmp_path, files: dict[str, str]):
    for name, body in files.items():
        p = tmp_path / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body)
    old = os.getcwd()
    try:
        os.chdir(tmp_path)
        r = extract([Path(n) for n in files], cache_root=Path(tempfile.mkdtemp()))
    finally:
        os.chdir(old)
    case_of = {(e["source"], e["target"]) for e in r["edges"] if e["relation"] == "case_of"}
    return case_of, r


def _find(r, label):
    return next(n["id"] for n in r["nodes"] if n["label"] == label)


def _labels(r):
    return [n["label"] for n in r["nodes"]]


def test_a_bare_member_becomes_a_node(tmp_path):
    case_of, r = _extract(tmp_path, {"s.ts": (
        "export enum Color {\n"
        "    Red\n"
        "}\n"
    )})
    assert "Red" in _labels(r)
    assert (_find(r, "Color"), _find(r, "Red")) in case_of


def test_an_assigned_member_becomes_a_node(tmp_path):
    # `Green = 5` parses as enum_assignment, a different node type from the bare
    # spelling, and both must land on the same edge.
    case_of, r = _extract(tmp_path, {"s.ts": (
        "export enum Color {\n"
        "    Red,\n"
        "    Green = 5\n"
        "}\n"
    )})
    color = _find(r, "Color")
    assert (color, _find(r, "Red")) in case_of
    assert (color, _find(r, "Green")) in case_of


def test_a_quoted_member_uses_its_name_not_the_literal(tmp_path):
    # The name node is a `string`; the label must be the member name without
    # the surrounding quotes.
    case_of, r = _extract(tmp_path, {"s.ts": (
        "export enum Weird {\n"
        "    \"Odd Name\" = 7\n"
        "}\n"
    )})
    labels = _labels(r)
    assert "Odd Name" in labels
    assert '"Odd Name"' not in labels
    assert (_find(r, "Weird"), _find(r, "Odd Name")) in case_of


def test_an_escape_in_a_quoted_member_does_not_truncate_the_name(tmp_path):
    # An escape splits the string into several fragments, so reading the first
    # fragment alone would label this member `A`. The whole text is unquoted
    # instead, which keeps the escape as it was written.
    case_of, r = _extract(tmp_path, {"s.ts": (
        "export enum E {\n"
        "    \"A\\tB\" = 1\n"
        "}\n"
    )})
    assert "A\\tB" in _labels(r)
    assert "A" not in _labels(r)
    assert (_find(r, "E"), _find(r, "A\\tB")) in case_of


def test_a_string_valued_enum_still_emits_members(tmp_path):
    # String enums are the common TS spelling and assign a string to a plain
    # identifier name; the value must not be mistaken for the name.
    case_of, r = _extract(tmp_path, {"s.ts": (
        "export enum Direction {\n"
        "    Up = \"UP\",\n"
        "    Down = \"DOWN\"\n"
        "}\n"
    )})
    direction = _find(r, "Direction")
    assert (direction, _find(r, "Up")) in case_of
    assert (direction, _find(r, "Down")) in case_of
    assert "UP" not in _labels(r)


def test_case_only_sibling_members_do_not_duplicate_an_edge(tmp_path):
    # Legal TS, one id after normalization. The first declaration keeps it.
    case_of, r = _extract(tmp_path, {"s.ts": (
        "export enum Odd {\n"
        "    Value,\n"
        "    value\n"
        "}\n"
    )})
    assert len(case_of) == 1


def test_a_class_property_identifier_is_not_read_as_an_enum_member(tmp_path):
    # `property_identifier` appears throughout a TS file. Only the ones directly
    # under an enum_body are members, so a class with properties and methods
    # must produce no case_of edges at all.
    case_of, r = _extract(tmp_path, {"s.ts": (
        "export class Widget {\n"
        "    label: string = \"x\";\n"
        "    render(): void {}\n"
        "}\n"
    )})
    assert case_of == set()


def test_a_const_enum_emits_members(tmp_path):
    case_of, r = _extract(tmp_path, {"s.ts": (
        "export const enum Mode {\n"
        "    Fast\n"
        "}\n"
    )})
    assert (_find(r, "Mode"), _find(r, "Fast")) in case_of


def test_an_enum_inside_a_namespace_emits_members(tmp_path):
    # The namespace container is handled in the same walk; the enum must not
    # lose its members to the namespace hop.
    case_of, r = _extract(tmp_path, {"s.ts": (
        "namespace App {\n"
        "    export enum Color {\n"
        "        Red\n"
        "    }\n"
        "}\n"
    )})
    assert (_find(r, "Color"), _find(r, "Red")) in case_of


def test_the_enum_type_node_is_kept(tmp_path):
    # Regression guard: the member nodes are additive, the enum type stays.
    _, r = _extract(tmp_path, {"s.ts": (
        "export enum Color {\n"
        "    Red\n"
        "}\n"
    )})
    color = _find(r, "Color")
    contains = {(e["source"], e["target"]) for e in r["edges"] if e["relation"] == "contains"}
    assert any(target == color for _, target in contains)


def test_an_empty_enum_emits_no_members(tmp_path):
    case_of, r = _extract(tmp_path, {"s.ts": "export enum Empty {\n}\n"})
    assert "Empty" in _labels(r)
    assert case_of == set()


def test_claiming_a_member_does_not_swallow_its_initializer(tmp_path):
    # An enum value can hold a whole expression. Handling the member must not
    # stop the walk before it, or everything the initializer declares is lost:
    # here the class expression's method disappeared until the `value` was
    # walked explicitly.
    case_of, r = _extract(tmp_path, {"s.ts": (
        "export enum E {\n"
        "    A = class Inner { m() { return 1; } }.name.length\n"
        "}\n"
    )})
    assert (_find(r, "E"), _find(r, "A")) in case_of
    assert "m()" in _labels(r), "the initializer's class expression was not walked"
