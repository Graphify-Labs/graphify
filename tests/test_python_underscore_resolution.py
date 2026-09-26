"""Regression coverage for Python leading-underscore node-id collisions (#3302).

``ids.py:make_id`` strips leading/trailing underscores from every part before
normalizing, so ``_get_connection``/``get_connection`` (and more broadly any
name differing only by ``_``/``__``/dunder wrapping, e.g. ``x``/``_x``/``__x``/
``__x__``) mint the SAME node id. ``add_node`` then silently drops whichever
declaration is walked second, so a public method/function can be entirely
absent from the graph while its private-by-convention sibling occupies the
public name.
"""
from __future__ import annotations
import textwrap
from pathlib import Path

from graphify.extract import extract_python


def _write_py(tmp_path: Path, code: str) -> Path:
    p = tmp_path / "mod.py"
    p.write_text(textwrap.dedent(code))
    return p


def _rationale_free_nodes(result: dict) -> list[dict]:
    return [n for n in result["nodes"] if n.get("file_type") != "rationale"]


def test_leading_underscore_method_collision_both_extracted(tmp_path: Path) -> None:
    """#3302's exact repro: both methods survive as distinct nodes."""
    path = _write_py(tmp_path, '''
        class Adapter:
            def _get_connection(self, url):
                return url

            def get_connection(self, url):
                return self._get_connection(url)

            def unrelated(self, x):
                return x
    ''')
    result = extract_python(path)
    labels = {n["label"] for n in _rationale_free_nodes(result)}
    assert "._get_connection()" in labels, f"private method missing: {labels}"
    assert ".get_connection()" in labels, f"public method missing (#3302): {labels}"
    assert ".unrelated()" in labels


def test_leading_underscore_method_collision_ids_distinct(tmp_path: Path) -> None:
    path = _write_py(tmp_path, '''
        class Adapter:
            def _get_connection(self, url):
                return url

            def get_connection(self, url):
                return self._get_connection(url)
    ''')
    result = extract_python(path)
    by_label = {n["label"]: n["id"] for n in _rationale_free_nodes(result)}
    assert by_label["._get_connection()"] != by_label[".get_connection()"]


def test_public_method_keeps_plain_id_private_sibling_is_salted(tmp_path: Path) -> None:
    """The public member's id must equal what it would be with no private sibling
    at all -- an incremental rebuild that adds/removes the private sibling must
    not re-point edges already targeting the public method."""
    solo = _write_py(tmp_path, '''
        class Adapter:
            def get_connection(self, url):
                return url
    ''')
    solo_result = extract_python(solo)
    solo_id = next(
        n["id"] for n in _rationale_free_nodes(solo_result)
        if n["label"] == ".get_connection()"
    )

    with_sibling = _write_py(tmp_path, '''
        class Adapter:
            def _get_connection(self, url):
                return url

            def get_connection(self, url):
                return self._get_connection(url)
    ''')
    result = extract_python(with_sibling)
    nodes = _rationale_free_nodes(result)
    public_id = next(n["id"] for n in nodes if n["label"] == ".get_connection()")
    private_id = next(n["id"] for n in nodes if n["label"] == "._get_connection()")

    assert public_id == solo_id, (
        f"adding a private sibling moved the public method's id: {solo_id} -> {public_id}"
    )
    assert private_id != public_id


def test_call_edge_resolves_to_the_salted_private_method(tmp_path: Path) -> None:
    """`get_connection`'s call to `self._get_connection(...)` must bind to the
    salted private-method node, not dangle or bind to the public one."""
    path = _write_py(tmp_path, '''
        class Adapter:
            def _get_connection(self, url):
                return url

            def get_connection(self, url):
                return self._get_connection(url)
    ''')
    result = extract_python(path)
    nodes = _rationale_free_nodes(result)
    public_id = next(n["id"] for n in nodes if n["label"] == ".get_connection()")
    private_id = next(n["id"] for n in nodes if n["label"] == "._get_connection()")

    calls = [e for e in result["edges"] if e.get("relation") == "calls"]
    assert (public_id, private_id) in {(e["source"], e["target"]) for e in calls}, (
        f"no calls edge from get_connection to the salted _get_connection: {calls}"
    )


def test_module_level_function_collision_both_extracted(tmp_path: Path) -> None:
    """Same bug, module-scoped (not inside a class)."""
    path = _write_py(tmp_path, '''
        def _helper():
            return 1

        def helper():
            return _helper()
    ''')
    result = extract_python(path)
    labels = {n["label"] for n in _rationale_free_nodes(result)}
    assert "_helper()" in labels
    assert "helper()" in labels
    by_label = {n["label"]: n["id"] for n in _rationale_free_nodes(result)}
    assert by_label["_helper()"] != by_label["helper()"]
    calls = {(e["source"], e["target"]) for e in result["edges"] if e.get("relation") == "calls"}
    assert (by_label["helper()"], by_label["_helper()"]) in calls


def test_no_unique_public_member_salts_every_member(tmp_path: Path) -> None:
    """`_x`/`__x` collide with no fully-public name in the group -- both must be
    salted (order-independent), not one arbitrarily kept plain."""
    path = _write_py(tmp_path, '''
        class C:
            def _x(self):
                return 1

            def __x(self):
                return 2
    ''')
    result = extract_python(path)
    nodes = _rationale_free_nodes(result)
    labels = {n["label"] for n in nodes}
    assert "._x()" in labels and ".__x()" in labels
    ids = {n["label"]: n["id"] for n in nodes}
    plain_class_scope_id = next(n["id"] for n in nodes if n["label"] == "C")
    # Neither survivor kept the bare, unsalted `<class>_x` id.
    for label in ("._x()", ".__x()"):
        assert ids[label] != f"{plain_class_scope_id}_x", (
            f"{label} kept the unsalted id despite no unique public member"
        )


def test_dunder_and_plain_name_collision_both_extracted(tmp_path: Path) -> None:
    """`__x__`, `__x`, and `x` all strip to the same id -- the fully public `x`
    must win and the dunder must still be extracted, salted."""
    path = _write_py(tmp_path, '''
        class C:
            def __x__(self):
                return 1

            def x(self):
                return 2
    ''')
    result = extract_python(path)
    nodes = _rationale_free_nodes(result)
    labels = {n["label"] for n in nodes}
    assert ".__x__()" in labels and ".x()" in labels
    ids = {n["label"]: n["id"] for n in nodes}
    assert ids[".__x__()"] != ids[".x()"]


def test_no_collision_ids_unaffected(tmp_path: Path) -> None:
    """A file with no underscore-only collisions must extract exactly as before
    -- no unnecessary salting applied to unrelated names."""
    path = _write_py(tmp_path, '''
        class D:
            def public_one(self):
                return 1

            def _private_two(self):
                return 2
    ''')
    result = extract_python(path)
    nodes = _rationale_free_nodes(result)
    ids = {n["label"]: n["id"] for n in nodes}
    class_id = next(n["id"] for n in nodes if n["label"] == "D")
    assert ids[".public_one()"] == f"{class_id}_public_one"
    assert ids["._private_two()"] == f"{class_id}_private_two"


def test_collision_in_one_class_does_not_salt_unrelated_class(tmp_path: Path) -> None:
    """A `_foo`/`foo` collision inside class A must not touch an unrelated,
    non-colliding `_foo` in class B (scope-keyed, not name-keyed)."""
    path = _write_py(tmp_path, '''
        class A:
            def _foo(self):
                return 1

            def foo(self):
                return self._foo()

        class B:
            def _foo(self):
                return 3
    ''')
    result = extract_python(path)
    nodes = _rationale_free_nodes(result)
    class_b_id = next(n["id"] for n in nodes if n["label"] == "B")
    b_foo = next(n for n in nodes if n["id"].startswith(class_b_id) and n["label"] == "._foo()")
    assert b_foo["id"] == f"{class_b_id}_foo", (
        "an unrelated class's non-colliding _foo was needlessly salted"
    )
