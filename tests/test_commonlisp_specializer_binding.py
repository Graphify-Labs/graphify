"""A Common Lisp method specializer must never bind to a same-named function.

Functions and types occupy separate namespaces in Common Lisp, so one symbol is
routinely both: `list`, `stream`, `condition`, `pathname`. When a specializer
names a type the corpus does not define, the cross-file stub must stay
unresolved rather than collapse onto a function that happens to share the name,
which would assert a dispatch relationship that does not exist.
"""
from __future__ import annotations

from graphify.extract import extract


def test_specializer_does_not_bind_to_same_named_function(tmp_path):
    a = tmp_path / "a.lisp"
    a.write_text("(defun square (x) (* x x))\n")          # a function named square
    b = tmp_path / "b.lisp"
    b.write_text(
        "(defgeneric area (obj))\n"
        "(defmethod area ((obj square)) 1)\n"             # dispatches on a TYPE named square
    )
    graph = extract([a, b], cache_root=tmp_path, parallel=False)
    by_id = {n["id"]: n for n in graph["nodes"]}
    for e in graph["edges"]:
        if e.get("relation") != "specializes":
            continue
        target = by_id.get(e.get("target"), {})
        label = str(target.get("label", ""))
        assert not label.endswith("()"), (
            f"specializes bound to the function {label!r}; "
            "no class of that name exists in the corpus"
        )
