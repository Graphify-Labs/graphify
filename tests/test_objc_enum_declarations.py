"""C-style enum extraction for Objective-C.

Objective-C is an object-oriented extractor that already emits @interface,
@implementation and @protocol type nodes, but plain `enum` and `typedef enum`
definitions were dropped entirely — the type and all of its enumerators were
invisible. Every other language with enums emits a type node plus a `case_of`
edge per member (Java #1719, C++ #3939, Swift); ObjC now matches.

The NS_ENUM/NS_OPTIONS macro spelling is deliberately out of scope: it is a
macro call that tree-sitter-objc parses into an ERROR subtree, so there is no
clean AST to read.
"""
from __future__ import annotations

from graphify.extract import extract


def _edge_labels(result: dict, relation: str) -> set[tuple[str, str]]:
    labels = {node["id"]: node["label"] for node in result["nodes"]}
    return {
        (labels.get(edge["source"], edge["source"]), labels.get(edge["target"], edge["target"]))
        for edge in result["edges"]
        if edge["relation"] == relation
    }


def test_objc_plain_enum_emits_type_and_case_of_members(tmp_path):
    source = tmp_path / "Color.m"
    source.write_text(
        "enum Color { Red, Green, Blue };\n"
        "@interface Foo : NSObject\n@end\n"
        "@implementation Foo\n@end\n",
        encoding="utf-8",
    )

    result = extract([source], cache_root=tmp_path)

    labels = {n["label"] for n in result["nodes"]}
    assert "Color" in labels, "enum type dropped"
    case_of = _edge_labels(result, "case_of")
    assert ("Color", "Red") in case_of
    assert ("Color", "Green") in case_of
    assert ("Color", "Blue") in case_of
    # The enum does not disturb the surrounding class.
    assert "Foo" in labels


def test_objc_typedef_enum_uses_the_typedef_alias(tmp_path):
    # `.m` is shared with MATLAB, so give the file an unambiguous ObjC marker so
    # detection routes it to the ObjC extractor.
    source = tmp_path / "Dir.m"
    source.write_text(
        "#import <Foundation/Foundation.h>\n"
        "typedef enum { North, South } Direction;\n",
        encoding="utf-8",
    )

    result = extract([source], cache_root=tmp_path)

    # The anonymous enum is named after its typedef alias, the name callers use.
    assert "Direction" in {n["label"] for n in result["nodes"]}
    case_of = _edge_labels(result, "case_of")
    assert ("Direction", "North") in case_of
    assert ("Direction", "South") in case_of


def test_objc_anonymous_and_bodyless_enums_mint_no_phantom(tmp_path):
    # A nameless enum has nothing to name a node after; a bare `enum X y;` use is
    # a reference, not a definition. Neither should fabricate a node — while the
    # surrounding class is still extracted.
    source = tmp_path / "None.m"
    source.write_text(
        "#import <Foundation/Foundation.h>\n"
        "enum { Loose1, Loose2 };\n"
        "@interface Keep : NSObject\n@end\n"
        "@implementation Keep\n@end\n",
        encoding="utf-8",
    )

    result = extract([source], cache_root=tmp_path)

    labels = {n["label"] for n in result["nodes"]}
    assert "Keep" in labels, "surrounding class should still be extracted"
    assert labels.isdisjoint({"Loose1", "Loose2"})
    assert not _edge_labels(result, "case_of")
