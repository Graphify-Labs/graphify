"""C-style enum extraction for Objective-C.

Objective-C is an object-oriented extractor that already emits @interface,
@implementation and @protocol type nodes, but plain `enum` and `typedef enum`
definitions were dropped entirely — the type and all of its enumerators were
invisible. Every other language with enums emits a type node plus a `case_of`
edge per member (Java #1719, C++ #3939, Swift); ObjC now matches.

NS_ENUM and NS_OPTIONS typedefs use the same graph representation.
"""
from __future__ import annotations

import pytest

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


@pytest.mark.parametrize("suffix", [".h", ".m", ".mm"])
@pytest.mark.parametrize("macro", ["NS_ENUM", "NS_OPTIONS"])
def test_objc_macro_enum_types_and_members_survive_cache(tmp_path, suffix, macro):
    source = tmp_path / ("Window" + suffix)
    source.write_text(
        "#import <Foundation/Foundation.h>\n"
        f"typedef {macro}(NSUInteger, WindowOptions) {{\n"
        "    WindowResizable = 1UL << 0,\n"
        "    WindowClosable = 1UL << 1,\n"
        "    WindowAll = WindowResizable | WindowClosable,\n"
        "};\n",
        encoding="utf-8",
    )
    cold = extract([source], cache_root=tmp_path)
    warm = extract([source], cache_root=tmp_path)
    expected = {
        ("WindowOptions", "WindowResizable"),
        ("WindowOptions", "WindowClosable"),
        ("WindowOptions", "WindowAll"),
    }
    assert _edge_labels(cold, "case_of") == expected
    assert _edge_labels(warm, "case_of") == expected
    assert cold["nodes"] == warm["nodes"]
    assert cold["edges"] == warm["edges"]
    assert any(target == "WindowOptions" for _, target in _edge_labels(cold, "contains"))


@pytest.mark.parametrize(
    ("declaration", "members"),
    [
        ("typedef NS_ENUM(NSInteger, Kind) { First, Second = 4 };", {"First", "Second"}),
        ("typedef NS_OPTIONS(unsigned long, Kind) { First = 1 << 0 };", {"First"}),
        ("typedef NS_ENUM(NSInteger, Kind) {};", set()),
        ("typedef NS_ENUM(NSInteger, Kind) { First = -1, Second = First + 1 };", {"First", "Second"}),
        ("typedef NS_ENUM(NSInteger, Kind) { First = 1, Second = First };", {"First", "Second"}),
        ("typedef /* type */ NS_ENUM(NSInteger /* a,b */, /* c,d */ Kind) { First /* e,f */, };", {"First"}),
        ("void use(void) { typedef NS_ENUM(NSInteger, Kind) { First }; }", {"First"}),
        ("#if ENABLE_KIND\ntypedef NS_ENUM(NSInteger, Kind) { First };\n#endif", {"First"}),
    ],
)
def test_objc_macro_enum_declaration_forms(tmp_path, declaration, members):
    source = tmp_path / "Kinds.h"
    source.write_text("#import <Foundation/Foundation.h>\n" + declaration, encoding="utf-8")
    result = extract([source], cache_root=tmp_path)
    assert "Kind" in {n["label"] for n in result["nodes"]}
    assert _edge_labels(result, "case_of") == {("Kind", name) for name in members}


@pytest.mark.parametrize("newline", ["\n", "\r\n"])
def test_objc_macro_enum_preserves_original_utf8_member_lines(tmp_path, newline):
    source = tmp_path / "Unicode.h"
    lines = [
        "#import <Foundation/Foundation.h>",
        "// café π",
        "NS_ASSUME_NONNULL_BEGIN",
        "typedef NS_ENUM(",
        "    NSInteger /* µ, storage */ ,",
        "    Kind",
        ") {",
        "    Café,",
        "    Second = 2,",
        "};",
        "NS_ASSUME_NONNULL_END",
    ]
    source.write_bytes((newline.join(lines) + newline).encode("utf-8"))
    result = extract([source], cache_root=tmp_path)
    nodes = {n["label"]: n for n in result["nodes"]}
    assert _edge_labels(result, "case_of") == {("Kind", "Café"), ("Kind", "Second")}
    assert nodes["Kind"]["source_location"] == "L4"
    assert nodes["Café"]["source_location"] == "L8"
    assert nodes["Second"]["source_location"] == "L9"


@pytest.mark.parametrize(
    "declaration",
    [
        "typedef OTHER_ENUM(NSInteger, Broken) { Bad };",
        "typedef MY_NS_ENUM(NSInteger, Broken) { Bad };",
        "typedef CF_ENUM(NSInteger, Broken) { Bad };",
        "typedef NS_CLOSED_ENUM(NSInteger, Broken) { Bad };",
        "NS_ENUM(NSInteger, Broken) { Bad };",
        "typedef NS_ENUM(NSInteger, ) { Bad };",
        "typedef NS_ENUM(NSInteger, Broken, Extra) { Bad };",
        "typedef NS_ENUM(NSInteger, Broken);",
        "typedef NS_ENUM(NSInteger, Broken) { Bad = , Other };",
        "typedef NS_ENUM(NSInteger, Broken) { Bad Other };",
        "typedef NS_ENUM(NSInteger, Broken) { Bad; };",
        "typedef NS_ENUM(NSInteger, Broken) { Bad",
        "typedef NS_ENUM(NSInteger, Broken) { Bad }",
        "typedef NS_ENUM(NSInteger, Broken) unrelated { Bad };",
        "// typedef NS_ENUM(NSInteger, Broken) { Bad };",
        'const char *text = "typedef NS_ENUM(NSInteger, Broken) { Bad };";',
        "#define EXAMPLE typedef NS_ENUM(NSInteger, Broken) { Bad };",
    ],
)
def test_objc_macro_enum_rejects_unrelated_and_malformed_declarations(tmp_path, declaration):
    source = tmp_path / "Negative.h"
    source.write_text("#import <Foundation/Foundation.h>\n" + declaration, encoding="utf-8")
    result = extract([source], cache_root=tmp_path)
    assert {n["label"] for n in result["nodes"]}.isdisjoint({"Broken", "Bad", "Other"})
    assert not _edge_labels(result, "case_of")


def test_objc_macro_enums_preserve_siblings_and_unrelated_parser_errors(tmp_path):
    source = tmp_path / "Mixed.h"
    source.write_text(
        "#import <Foundation/Foundation.h>\n"
        "enum Plain { PlainOne, PlainTwo };\n"
        "typedef enum { North, South } Direction;\n"
        "typedef NS_ENUM(NSInteger, Kind) { First, Second };\n"
        "typedef NS_OPTIONS(NSUInteger, Broken) { Bad = , Other };\n"
        "typedef NS_OPTIONS(NSUInteger, Mask) { Enabled = 1 << 0 };\n"
        "@interface Keep : NSObject\n@end\n"
        "@interface Invalid : NSObject\n- (void)broken:(;\n@end\n",
        encoding="utf-8",
    )
    result = extract([source], cache_root=tmp_path)
    labels = {n["label"] for n in result["nodes"]}
    assert "Keep" in labels
    assert labels.isdisjoint({"Broken", "Bad", "Other"})
    assert _edge_labels(result, "case_of") == {
        ("Plain", "PlainOne"), ("Plain", "PlainTwo"),
        ("Direction", "North"), ("Direction", "South"),
        ("Kind", "First"), ("Kind", "Second"), ("Mask", "Enabled"),
    }


@pytest.mark.parametrize(
    "declaration",
    [
        "typedef NS_ENUM(NSInteger = 1, Broken) { Bad };",
        "typedef NS_ENUM(NSInteger, *Broken) { Bad };",
        "typedef NS_ENUM(NSInteger, Broken[2]) { Bad };",
        "typedef NS_OPTIONS(NSUInteger, Broken) {\n"
        "#ifdef FEATURE\n    Bad = 1 << 0,\n#endif\n    Other = 1 << 1,\n};",
    ],
)
def test_objc_macro_enum_unsupported_parts_do_not_emit_partial_enums(tmp_path, declaration):
    source = tmp_path / "Partial.h"
    source.write_text(
        "#import <Foundation/Foundation.h>\n" + declaration + "\n"
        "typedef NS_ENUM(NSInteger, Good) { Kept };\n",
        encoding="utf-8",
    )
    result = extract([source], cache_root=tmp_path)
    assert {n["label"] for n in result["nodes"]}.isdisjoint({"Broken", "Bad", "Other"})
    assert _edge_labels(result, "case_of") == {("Good", "Kept")}


@pytest.mark.parametrize("macro", ["NS_ENUM", "NS_OPTIONS"])
def test_objc_macro_enum_preserves_members_with_attributes(tmp_path, macro):
    source = tmp_path / "Attributes.h"
    source.write_text(
        "#import <Foundation/Foundation.h>\n"
        f"typedef {macro}(NSInteger, Kind) {{\n"
        "    First __attribute__((deprecated)),\n"
        "    Second,\n"
        "};\n",
        encoding="utf-8",
    )
    result = extract([source], cache_root=tmp_path)
    assert _edge_labels(result, "case_of") == {("Kind", "First"), ("Kind", "Second")}
    nodes = {n["label"]: n for n in result["nodes"]}
    assert nodes["First"]["source_location"] == "L3"
    assert nodes["Second"]["source_location"] == "L4"
