"""ObjC category / class-extension interfaces must fold into the base class (#1556).

`@interface Foo (Cat)` in `Foo+Cat.h` declares members of an EXISTING class, but the
extractor keyed its class node off the file stem `Foo+Cat`, minting a SECOND node
labelled `Foo`. Every `[Foo ...]` receiver then had two type-def candidates, tripped
the member-call resolver's single-definition god-node guard, and produced NO edge —
so moving a method from `Foo.h` into a category silently destroyed call edges the
same corpus resolved fine before. Categories are pervasive in real ObjC, so this hit
ordinary code, not an edge case.

The class node now keys off the base stem, and `_merge_decl_def_classes` folds the
category header into the base header instead of bailing on "more than one header".
"""
from __future__ import annotations

from pathlib import Path

from graphify.extract import extract


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _label(result: dict, nid: str) -> str:
    for n in result["nodes"]:
        if n["id"] == nid:
            return n.get("label", "")
    return f"?{nid}"


def _calls(result: dict):
    """{(source_label, target_label, confidence)} over `calls` edges."""
    return {
        (_label(result, e["source"]), _label(result, e["target"]), e.get("confidence"))
        for e in result["edges"]
        if e.get("relation") == "calls"
    }


def _nodes_labelled(result: dict, label: str):
    return [n for n in result["nodes"] if n.get("label") == label]


_BASE_H = "@interface Base : NSObject\n@end\n"
_CALLER = (
    '#import "Base.h"\n@interface Caller : NSObject\n- (void)go;\n@end\n',
    '#import "Caller.h"\n@implementation Caller\n- (void)go { [Base useIt]; }\n@end\n',
)


def test_objc_category_method_is_reachable_from_another_class(tmp_path: Path):
    """The headline case: `-useIt` declared in a category still resolves.

    Before, `Base+Extra.h` minted a second `Base` node, so `[Base useIt]` was
    ambiguous and emitted nothing.
    """
    base = tmp_path / "src"
    _write(base / "Base.h", _BASE_H)
    _write(base / "Base+Extra.h",
           '#import "Base.h"\n@interface Base (Extra)\n- (void)useIt;\n@end\n')
    _write(base / "Base+Extra.m",
           '#import "Base+Extra.h"\n@implementation Base (Extra)\n- (void)useIt {}\n@end\n')
    _write(base / "Caller.h", _CALLER[0])
    _write(base / "Caller.m", _CALLER[1])
    result = extract(sorted(base.glob("*")), cache_root=tmp_path / "cache")

    assert len(_nodes_labelled(result, "Base")) == 1
    assert ("-go", "-useIt", "EXTRACTED") in _calls(result)


def test_objc_class_extension_folds_into_the_base_class(tmp_path: Path):
    """An anonymous class extension (`@interface Base ()`) folds the same way."""
    base = tmp_path / "src"
    _write(base / "Base.h", "@interface Base : NSObject\n- (void)pub;\n@end\n")
    _write(base / "Base.m",
           '#import "Base.h"\n'
           "@interface Base ()\n- (void)priv;\n@end\n"
           "@implementation Base\n- (void)pub { [self priv]; }\n- (void)priv {}\n@end\n")
    result = extract(sorted(base.glob("*")), cache_root=tmp_path / "cache")

    assert len(_nodes_labelled(result, "Base")) == 1
    assert ("-pub", "-priv", "EXTRACTED") in _calls(result)


def test_objc_non_category_interface_in_a_plus_named_file_is_untouched(tmp_path: Path):
    """The fold is keyed on the CATEGORY SYNTAX, not on the `+` in the filename.

    `Extra+Helpers.h` declaring a plain `@interface Extra` (no parentheses) must keep
    its own stem, so it does not silently merge into an unrelated `Extra.h`.
    """
    base = tmp_path / "src"
    _write(base / "Extra+Helpers.h", "@interface Helper : NSObject\n- (void)help;\n@end\n")
    result = extract(sorted(base.glob("*")), cache_root=tmp_path / "cache")

    helper = _nodes_labelled(result, "Helper")
    assert len(helper) == 1
    assert helper[0]["id"].endswith("extra_helpers_helper")


def test_objc_same_named_categories_in_different_directories_stay_distinct(tmp_path: Path):
    """Two unrelated `Thing` classes in different directories must not merge.

    The id embeds the full directory path, so the base-stem rewrite cannot conflate
    them; a `[Thing act]` receiver stays ambiguous and yields no edge (god-node guard).
    """
    base = tmp_path / "src"
    for d in ("a", "b"):
        _write(base / d / "Thing.h", "@interface Thing : NSObject\n@end\n")
        _write(base / d / "Thing+Ops.h",
               '#import "Thing.h"\n@interface Thing (Ops)\n- (void)act;\n@end\n')
        _write(base / d / "Thing+Ops.m",
               '#import "Thing+Ops.h"\n@implementation Thing (Ops)\n- (void)act {}\n@end\n')
    _write(base / "Use.m",
           '#import "a/Thing+Ops.h"\n@implementation Use\n- (void)go { [Thing act]; }\n@end\n')
    result = extract(sorted(base.rglob("*.[hm]")), cache_root=tmp_path / "cache")

    assert len(_nodes_labelled(result, "Thing")) == 2
    assert [e for e in result["edges"]
            if e.get("relation") == "calls" and _label(result, e["source"]) == "-go"] == []
