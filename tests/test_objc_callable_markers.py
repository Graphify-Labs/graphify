"""ObjC declarations carry the `_callable` / `_callable_class` markers.

Every other extractor stamps its definitions with `_callable` — "a real callable,
not a same-named data symbol" (#2438) — and narrows a type to `_callable_class`,
callable only through a constructor (#2137). The generic engine does it for all of
them in one place (`extractors/engine.py`, `callable_def_nids` /
`callable_class_nids`).

The ObjC extractor builds its nodes by hand and set neither, so an ObjC class was
invisible to every pass that indexes declarations by those markers, and an ObjC
method could never be told apart from a data symbol of the same name. This pins the
markers onto the four node kinds ObjC produces, including the two that must stay
unmarked.
"""
from __future__ import annotations

from pathlib import Path

from graphify.extract import extract

GREETER_H = (
    "@interface Greeter : NSObject\n"
    "- (void)greet;\n"
    "+ (instancetype)shared;\n"
    "@end\n"
)
GREETER_M = (
    "#import \"Greeter.h\"\n"
    "@implementation Greeter\n"
    "- (void)greet {}\n"
    "@end\n"
)


def _extract(tmp_path: Path, files: dict[str, str]) -> dict:
    paths = []
    for name, body in files.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
        paths.append(path)
    return extract(paths, cache_root=tmp_path / "graphify-out")


def _node(result: dict, label: str) -> dict:
    matches = [n for n in result["nodes"] if n.get("label") == label]
    assert len(matches) == 1, [n.get("label") for n in result["nodes"]]
    return matches[0]


def test_a_class_is_marked_as_a_type(tmp_path: Path):
    result = _extract(tmp_path, {"Greeter.h": GREETER_H})
    greeter = _node(result, "Greeter")
    assert greeter.get("_callable") is True
    assert greeter.get("_callable_class") is True


def test_an_implementation_only_class_is_marked_too(tmp_path: Path):
    # A class whose `@interface` is not in this corpus is still a declaration.
    result = _extract(tmp_path, {"Greeter.m": "@implementation Greeter\n- (void)greet {}\n@end\n"})
    greeter = _node(result, "Greeter")
    assert greeter.get("_callable") is True
    assert greeter.get("_callable_class") is True


def test_a_header_and_impl_pair_keeps_the_markers_after_folding(tmp_path: Path):
    # `_merge_decl_def_classes` folds the `.h`/`.m` pair into one node; the markers
    # have to be on whichever node survives.
    result = _extract(tmp_path, {"Greeter.h": GREETER_H, "Greeter.m": GREETER_M})
    greeter = _node(result, "Greeter")
    assert greeter.get("_callable") is True
    assert greeter.get("_callable_class") is True


def test_a_method_is_callable_but_is_not_a_type(tmp_path: Path):
    result = _extract(tmp_path, {"Greeter.h": GREETER_H})
    for label in ("-greet", "+shared"):
        method = _node(result, label)
        assert method.get("_callable") is True, label
        assert "_callable_class" not in method, label


def test_a_protocol_is_marked_like_any_other_interface(tmp_path: Path):
    # A Java or C# interface gets `_callable_class` from the generic engine, and a
    # protocol is the same kind of declaration.
    result = _extract(tmp_path, {"Greeting.h": "@protocol Greeting\n- (void)greet;\n@end\n"})
    protocol = _node(result, "<Greeting>")
    assert protocol.get("_callable") is True
    assert protocol.get("_callable_class") is True


def test_a_dangling_reference_is_not_marked(tmp_path: Path):
    # `NSObject` is a stub minted for a name this corpus never declares, so it has
    # no source file and no declaration behind it.
    result = _extract(tmp_path, {"Greeter.h": GREETER_H})
    stub = _node(result, "NSObject")
    assert not stub.get("source_file")
    assert "_callable" not in stub
    assert "_callable_class" not in stub


def test_the_file_node_is_not_marked(tmp_path: Path):
    result = _extract(tmp_path, {"Greeter.h": GREETER_H})
    file_node = _node(result, "Greeter.h")
    assert "_callable" not in file_node
    assert "_callable_class" not in file_node
