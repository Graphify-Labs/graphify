"""An ObjC category's node ids must not carry the checkout path.

A category (`@interface Foo (Cat)` in `Foo+Cat.h`) keys its class node and methods
off the BASE stem `Foo`, so they fold into `Foo.h`'s class (#1556). extract() turns
an id minted from an absolute input path into the repo-relative form only when it
starts with its own file's stem prefix (`.../Foo+Cat`), so these ids kept the
absolute form: `/home/me/proj/Lib/NSString+Extra.h` produced a `NSString` node
`home_me_proj_lib_nsstring_nsstring`. A method of a category on an in-corpus class
(`Foo (Cat) -bar`) kept it too. The same repo checked out in two places gave two
different graphs, and graph.json carried the checkout path (#502).
"""
from __future__ import annotations

from pathlib import Path

from graphify.extract import extract
from graphify.extractors.base import _make_id

_FILES = {
    "Lib/Foo.h": "#import <Foundation/Foundation.h>\n@interface Foo : NSObject\n- (void)base;\n@end\n",
    "Lib/Foo+Cat.h": '#import "Foo.h"\n@interface Foo (Cat)\n- (void)bar;\n@end\n',
    "Lib/Foo+Cat.m": '#import "Foo+Cat.h"\n@implementation Foo (Cat)\n- (void)bar { [self base]; }\n@end\n',
    "Lib/NSString+Extra.h": "#import <Foundation/Foundation.h>\n@interface NSString (Extra)\n- (void)baz;\n@end\n",
    "Lib/NSString+Extra.m": '#import "NSString+Extra.h"\n@implementation NSString (Extra)\n- (void)baz {}\n@end\n',
}


def _project(root: Path) -> list[Path]:
    for rel, text in _FILES.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text, encoding="utf-8")
    return sorted(root / rel for rel in _FILES)


def _extract(root: Path, paths: list[Path], cache: Path) -> dict:
    return extract(paths, root=root, cache_root=cache, parallel=False)


def _edges(result: dict) -> set[tuple[str, str, str]]:
    return {(e["source"], e["relation"], e["target"]) for e in result["edges"]}


def test_no_id_carries_the_checkout_path(tmp_path: Path):
    root = tmp_path / "checkout" / "proj"
    result = _extract(root, _project(root), tmp_path / "cache")
    slug = _make_id(str(root))
    leaked = sorted({n["id"] for n in result["nodes"] if slug in n["id"]}
                    | {x for e in result["edges"] for x in (e["source"], e["target"]) if slug in x})
    assert leaked == []


def test_category_class_and_methods_get_repo_relative_ids(tmp_path: Path):
    root = tmp_path / "proj"
    result = _extract(root, _project(root), tmp_path / "cache")
    ids = {n["id"]: n["label"] for n in result["nodes"]}
    # A category on a class outside the corpus.
    assert ids.get("lib_nsstring_nsstring") == "NSString"
    assert ids.get("lib_nsstring_nsstring_baz") == "-baz"
    # A category method folds under the in-corpus class, named like its own methods.
    assert ids.get("lib_foo_foo") == "Foo"
    assert ids.get("lib_foo_foo_base") == "-base"
    assert ids.get("lib_foo_foo_bar") == "-bar"
    assert ("lib_foo_foo", "method", "lib_foo_foo_bar") in _edges(result)
    assert ("lib_nsstring_nsstring", "method", "lib_nsstring_nsstring_baz") in _edges(result)


def test_two_checkouts_give_the_same_graph(tmp_path: Path):
    one, two = tmp_path / "one" / "proj", tmp_path / "two" / "proj"
    a = _extract(one, _project(one), tmp_path / "cache-one")
    b = _extract(two, _project(two), tmp_path / "cache-two")
    assert {n["id"] for n in a["nodes"]} == {n["id"] for n in b["nodes"]}
    assert _edges(a) == _edges(b)


def test_relative_input_paths_give_the_same_ids(tmp_path: Path, monkeypatch):
    root = tmp_path / "proj"
    absolute = _extract(root, _project(root), tmp_path / "cache-abs")
    monkeypatch.chdir(root)
    relative = _extract(Path("."), sorted(Path(rel) for rel in _FILES), tmp_path / "cache-rel")
    assert {n["id"] for n in absolute["nodes"]} == {n["id"] for n in relative["nodes"]}
    assert _edges(absolute) == _edges(relative)
