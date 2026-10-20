"""C++ `using X = ...;` and `typedef ... X;` at namespace scope are declarations.

The C++ extractor emitted no node for an alias declaration or a typedef, so a
field, parameter or return typed with one, even in the declaring header,
resolved to a SOURCELESS stub that the corpus rewire can grow into a hub. A
namespace- or file-scope alias is now a type node contained by its file; every
declarator of a typedef counts (`typedef int Handle, *HandlePtr;`,
`typedef int (*Fn)(int);`, `typedef int Arr[4];`), and an alias template
(`template <class T> using Ptr = T*;`) too. An include guard or an
`#if`/`#ifdef` block is a conditional wrapper, not a scope: an alias inside
one at file scope is still file-scope.

Not declarations here: a member alias (`using value_type = T;` in a class: one
in every container, and C++ class-member ids are not class-qualified, so they
would fold into one hub); the struct a C-style `typedef struct Foo {...} Foo;`
names (the struct's own node is it); and a same-name re-export
(`using Bar = ns::Bar;`), which denotes the original type and declares no new
name.
"""
from __future__ import annotations

import importlib.util
import textwrap
from pathlib import Path

import pytest

from graphify.extract import extract

pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("tree_sitter_cpp") is None,
    reason="tree_sitter_cpp not installed",
)

_HEADER = textwrap.dedent("""\
    #include <vector>
    #include <functional>
    namespace app {
    using IntVec = std::vector<int>;
    typedef int Handle, *HandlePtr;
    typedef struct { int x; } Point;
    typedef int (*Fn)(int);
    template <typename T> using Ptr = T*;
    using Callback = std::function<void(int)>;
    struct Widget {
      using value_type = int;
      typedef int size_type;
      IntVec items;
      Handle h;
      Point p;
      Fn f;
      Ptr<int> raw;
      Callback cb;
      IntVec get(Handle h, Callback cb);
    };
    }
    """)


def _extract(tmp_path: Path, files: dict[str, str]) -> dict:
    for name, body in files.items():
        (tmp_path / name).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / name).write_text(body, encoding="utf-8")
    return extract([tmp_path / n for n in files], root=tmp_path,
                   cache_root=tmp_path / "graphify-out", parallel=False)


def _labels(result: dict) -> dict[str, str]:
    return {n["id"]: n["label"] for n in result["nodes"]}


def _pairs(result: dict, relation: str) -> set[tuple[str, str]]:
    label = _labels(result)
    return {(label.get(e["source"], str(e["source"])), label.get(e["target"], str(e["target"])))
            for e in result["edges"] if e["relation"] == relation}


def test_each_namespace_scope_alias_is_a_sourced_node_on_its_line(tmp_path: Path):
    result = _extract(tmp_path, {"widget.hpp": _HEADER})
    expected = {"IntVec": "L4", "Handle": "L5", "HandlePtr": "L5", "Point": "L6",
                "Fn": "L7", "Ptr": "L8", "Callback": "L9"}
    for label, line in expected.items():
        matches = [n for n in result["nodes"] if n["label"] == label]
        assert len(matches) == 1, label
        assert matches[0]["source_file"], label
        assert matches[0]["source_location"] == line, label
    assert [n["label"] for n in result["nodes"] if not n.get("source_file")] == []


def test_each_alias_is_contained_by_its_file(tmp_path: Path):
    contained = {tgt for _src, tgt in _pairs(_extract(tmp_path, {"widget.hpp": _HEADER}), "contains")}
    assert {"IntVec", "Handle", "HandlePtr", "Point", "Fn", "Ptr", "Callback"} <= contained


def test_fields_reference_the_local_aliases(tmp_path: Path):
    refs = _pairs(_extract(tmp_path, {"widget.hpp": _HEADER}), "references")
    assert {("Widget", "IntVec"), ("Widget", "Handle"), ("Widget", "Point"), ("Widget", "Fn"),
            ("Widget", "Ptr"), ("Widget", "Callback")} <= refs


def test_member_aliases_are_not_file_level_nodes(tmp_path: Path):
    result = _extract(tmp_path, {"widget.hpp": _HEADER})
    assert [n for n in result["nodes"] if n["label"] in ("value_type", "size_type")] == []


def test_a_c_style_typedef_of_a_named_struct_is_the_struct(tmp_path: Path):
    result = _extract(tmp_path, {"foo.hpp": "typedef struct Foo { int y; } Foo;\nstruct User { Foo f; };\n"})
    foos = [n for n in result["nodes"] if n["label"] == "Foo"]
    assert len(foos) == 1 and foos[0]["source_file"]
    assert ("User", "Foo") in _pairs(result, "references")


def test_a_same_name_re_export_emits_no_node(tmp_path: Path):
    result = _extract(tmp_path, {"api.hpp": "namespace ns { struct Bar {}; }\nusing Bar = ns::Bar;\n"})
    bars = [n for n in result["nodes"] if n["label"] == "Bar"]
    assert len(bars) == 1
    assert bars[0]["source_location"] == "L1"


def test_a_reference_from_another_file_lands_on_the_alias(tmp_path: Path):
    result = _extract(tmp_path, {
        "types.hpp": "#include <vector>\nusing IntVec = std::vector<int>;\n",
        "user.hpp": '#include "types.hpp"\nstruct Bag { IntVec v; };\n',
    })
    [alias] = [n for n in result["nodes"] if n["label"] == "IntVec"]
    assert alias["source_file"].endswith("types.hpp")
    label = _labels(result)
    targets = {e["target"] for e in result["edges"]
               if e["relation"] == "references" and label.get(e["source"]) == "Bag"}
    assert targets == {alias["id"]}


_GUARDED = textwrap.dedent("""\
    #ifndef CONFIG_HPP
    #define CONFIG_HPP
    using Guarded = int;
    typedef long GuardedT;
    #if defined(USE_WIDE)
    using Char = wchar_t;
    #elif defined(USE_U16)
    using Char16 = char16_t;
    #else
    using Narrow = char;
    #endif
    #ifdef HAVE_POOL
    template <typename T> using Pool = T*;
    #endif
    struct Config {
    #ifdef DEBUG
      using debug_type = int;
    #endif
      Guarded g;
      GuardedT t;
      Narrow n;
    };
    #endif
    """)


def test_aliases_inside_include_guards_and_conditionals_are_nodes(tmp_path: Path):
    result = _extract(tmp_path, {"config.hpp": _GUARDED})
    expected = {"Guarded": "L3", "GuardedT": "L4", "Char": "L6", "Char16": "L8",
                "Narrow": "L10", "Pool": "L13"}
    for label, line in expected.items():
        matches = [n for n in result["nodes"] if n["label"] == label]
        assert len(matches) == 1, label
        assert matches[0]["source_file"], label
        assert matches[0]["source_location"] == line, label
    assert {("Config", "Guarded"), ("Config", "GuardedT"), ("Config", "Narrow")} <= _pairs(result, "references")


def test_a_member_alias_inside_a_conditional_is_still_a_member(tmp_path: Path):
    result = _extract(tmp_path, {"config.hpp": _GUARDED})
    assert [n for n in result["nodes"] if n["label"] == "debug_type"] == []
