"""ObjC category node ids must not carry the absolute checkout path.

A category/extension keys its class and method nodes off the base stem (`Foo+Ext`
-> `Foo`, #1556). The extract() id-remap post-pass relativizes a file's ids by its
OWN file-stem prefix, which for `Foo+Ext.h` is `foo_ext`; a base-stem-prefixed id
(`<abs>_foo_foo_baz`) never matched, so the absolute path leaked in and the same
source produced a different graph.json per checkout directory (not reproducible).
"""
from __future__ import annotations

from pathlib import Path

from graphify.extract import extract


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _mk(src: Path) -> None:
    _write(src / "Foo.h", "@interface Foo : NSObject\n- (void)bar;\n@end\n")
    _write(src / "Foo+Ext.h",
           '#import "Foo.h"\n@interface Foo (Ext)\n- (void)baz;\n@end\n')
    _write(src / "Foo+Ext.m",
           '#import "Foo+Ext.h"\n@implementation Foo (Ext)\n- (void)baz {}\n@end\n')


def _ids(result: dict) -> set[str]:
    return {n["id"] for n in result["nodes"]}


def test_category_ids_are_identical_across_checkout_dirs(tmp_path: Path):
    a = tmp_path / "checkoutA" / "src"
    b = tmp_path / "checkoutB" / "src"
    _mk(a)
    _mk(b)
    ra = extract(sorted(a.glob("*")), root=a, cache_root=tmp_path / "ca")
    rb = extract(sorted(b.glob("*")), root=b, cache_root=tmp_path / "cb")

    assert _ids(ra) == _ids(rb)
    assert not [i for i in _ids(ra) if "private" in i or "var_folders" in i or tmp_path.name in i]


def test_category_method_hangs_on_base_class_with_canonical_id(tmp_path: Path):
    src = tmp_path / "src"
    _mk(src)
    result = extract(sorted(src.glob("*")), root=src, cache_root=tmp_path / "c")

    foo = [n for n in result["nodes"] if n.get("_callable_class") and n.get("label") == "Foo"]
    assert len(foo) == 1
    assert foo[0]["id"] == "foo_foo"
    method = [(e["source"], e["target"]) for e in result["edges"]
              if e.get("relation") == "method" and e["target"] == "foo_foo_baz"]
    assert method == [("foo_foo", "foo_foo_baz")]


def test_category_without_a_sibling_base_header_keeps_a_clean_class_id(tmp_path: Path):
    """When the category's directory has no `Foo.h`, the class node is the only one
    carrying the base-stem prefix; it still must relativize instead of leaking."""
    plug = tmp_path / "plug"
    _write(plug / "Engine+Ads.h",
           "@interface Engine (Ads)\n- (void)showAd;\n@end\n")
    _write(plug / "Engine+Ads.m",
           '#import "Engine+Ads.h"\n@implementation Engine (Ads)\n- (void)showAd {}\n@end\n')
    result = extract(sorted(plug.glob("*")), root=plug, cache_root=tmp_path / "c")

    assert not [n["id"] for n in result["nodes"]
                if "private" in n["id"] or "var_folders" in n["id"]]
