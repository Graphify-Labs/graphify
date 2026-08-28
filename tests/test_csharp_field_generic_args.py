"""C# generic type arguments in FIELD position.

The field_declaration handler read only the outer type name, so the inner argument of
`Box<Widget>` produced no edge. Properties, return types and parameters already walked
the full type expression via _csharp_collect_type_refs, which made fields the odd one
out for two very common shapes: `IDbContextFactory<SomeContext>` lost SomeContext, and
`Mock<IThing>` lost IThing across whole test suites.

Missing edges here are silent -- `affected` returns a smaller, confident answer rather
than an error -- so each case asserts the edge exists rather than asserting a count.
"""
from __future__ import annotations

import os
from pathlib import Path

from graphify.extract import extract


def _refs(tmp_path, files: dict[str, str]) -> set[tuple[str, str]]:
    """Extract, returning {(source_label, target_label)} for `references` edges."""
    for name, body in files.items():
        p = tmp_path / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body)
    old = os.getcwd()
    try:
        os.chdir(tmp_path)
        r = extract([Path(n) for n in files], cache_root=tmp_path / ".cache")
    finally:
        os.chdir(old)
    labels = {n["id"]: n.get("label", "") for n in r["nodes"]}
    return {
        (labels.get(e["source"], ""), labels.get(e["target"], ""))
        for e in r["edges"]
        if e["relation"] == "references"
    }


_TYPES = (
    "public interface IThing { }\n"
    "public class Box<T> { }\n"
    "public class Outer { public class Inner { } }\n"
)


def test_field_generic_argument_produces_edge(tmp_path):
    refs = _refs(tmp_path, {
        "T.cs": _TYPES,
        "P.cs": "public class Probe { private Box<IThing> _f = null!; }\n",
    })
    assert ("Probe", "Box") in refs, "outer field type must still be linked"
    assert ("Probe", "IThing") in refs, "generic argument in field position must be linked"


def test_field_matches_property_behaviour(tmp_path):
    """A field and a property of the same type must produce the same references."""
    refs = _refs(tmp_path, {
        "T.cs": _TYPES,
        "P.cs": (
            "public class WithField { private Box<IThing> _f = null!; }\n"
            "public class WithProp  { public Box<IThing> P { get; set; } = null!; }\n"
        ),
    })
    field_targets = {t for s, t in refs if s == "WithField"}
    prop_targets = {t for s, t in refs if s == "WithProp"}
    assert field_targets == prop_targets, (
        f"field and property disagree: field={field_targets} property={prop_targets}"
    )


def test_nested_generic_arguments(tmp_path):
    refs = _refs(tmp_path, {
        "T.cs": _TYPES,
        "P.cs": "public class Probe { private Box<Box<IThing>> _f = null!; }\n",
    })
    assert ("Probe", "IThing") in refs, "innermost generic argument must be linked"


def test_multiple_declarators_share_the_type(tmp_path):
    refs = _refs(tmp_path, {
        "T.cs": _TYPES,
        "P.cs": "public class Probe { private Box<IThing> _a = null!, _b = null!; }\n",
    })
    assert ("Probe", "IThing") in refs


def test_bare_type_parameter_is_not_fabricated(tmp_path):
    """`T item` must not create a node for the type parameter itself."""
    refs = _refs(tmp_path, {
        "P.cs": "public class Probe<T> { private T _item = default!; }\n",
    })
    assert not any(t == "T" for _, t in refs), "type parameter must not become a node"


def test_type_parameter_as_generic_argument_is_not_fabricated(tmp_path):
    refs = _refs(tmp_path, {
        "T.cs": _TYPES,
        "P.cs": "public class Probe<T> { private Box<T> _f = null!; }\n",
    })
    assert ("Probe", "Box") in refs, "outer type is still a real reference"
    assert not any(t == "T" for _, t in refs), "type parameter must not become a node"


def test_predefined_types_are_not_fabricated(tmp_path):
    refs = _refs(tmp_path, {
        "T.cs": _TYPES,
        "P.cs": "public class Probe { private Box<int> _f = null!; private string _s = \"\"; }\n",
    })
    assert not any(t in {"int", "string"} for _, t in refs), (
        "builtin types must not become nodes"
    )


def test_plain_field_still_links(tmp_path):
    """The non-generic path must be unchanged."""
    refs = _refs(tmp_path, {
        "T.cs": _TYPES,
        "P.cs": "public class Probe { private IThing _f = null!; }\n",
    })
    assert ("Probe", "IThing") in refs
