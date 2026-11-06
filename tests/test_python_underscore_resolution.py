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


# --- Module-level classes join the collision map (#2810) -------------------
#
# The pre-scan above records module-level functions and class methods but not
# module-level class names, so a class colliding with a function or another
# class on one id (`Session` / `session()`, `Foo` / `FOO`, `Pair` / `_Pair`)
# still lost one declaration to first-wins `add_node`, and which one survived
# depended on declaration order.


def _labels_to_ids(result: dict) -> dict[str, str]:
    return {n["label"]: n["id"] for n in _rationale_free_nodes(result)}


def test_class_and_function_case_collision_both_extracted(tmp_path: Path) -> None:
    """requests/sessions.py's shape: a class and its lowercase factory."""
    path = _write_py(tmp_path, '''
        class Session:
            pass

        def session():
            return Session()
    ''')
    ids = _labels_to_ids(extract_python(path))
    assert "Session" in ids, f"class missing (#2810): {sorted(ids)}"
    assert "session()" in ids, f"function missing (#2810): {sorted(ids)}"
    assert ids["Session"] != ids["session()"]


def test_class_and_function_case_collision_is_order_independent(tmp_path: Path) -> None:
    """Function declared first must not change which declarations survive or
    what ids they get."""
    class_first = _labels_to_ids(extract_python(_write_py(tmp_path, '''
        class Session:
            pass

        def session():
            return Session()
    ''')))
    func_first = _labels_to_ids(extract_python(_write_py(tmp_path, '''
        def session():
            return Session()

        class Session:
            pass
    ''')))
    assert class_first["Session"] == func_first["Session"]
    assert class_first["session()"] == func_first["session()"]


def test_class_and_class_case_collision_both_extracted(tmp_path: Path) -> None:
    path = _write_py(tmp_path, '''
        class Foo:
            pass

        class FOO:
            pass
    ''')
    ids = _labels_to_ids(extract_python(path))
    assert "Foo" in ids and "FOO" in ids, f"a class was dropped: {sorted(ids)}"
    assert ids["Foo"] != ids["FOO"]


def test_class_underscore_collision_public_class_keeps_plain_id(tmp_path: Path) -> None:
    """`Pair` / `_Pair`: same unique-public-member rule as functions -- the
    public class keeps the id it has with no private sibling."""
    solo_id = _labels_to_ids(extract_python(_write_py(tmp_path, '''
        class Pair:
            pass
    ''')))["Pair"]
    ids = _labels_to_ids(extract_python(_write_py(tmp_path, '''
        class _Pair:
            pass

        class Pair:
            pass
    ''')))
    assert "_Pair" in ids and "Pair" in ids
    assert ids["Pair"] == solo_id
    assert ids["_Pair"] != solo_id


def test_methods_of_a_salted_class_keep_underscore_protection(tmp_path: Path) -> None:
    """Once the class id is salted its methods are minted under the salted id,
    so the pre-scan must key their collision groups under it too -- otherwise
    `_get`/`get` inside the salted class collapse again."""
    path = _write_py(tmp_path, '''
        class Session:
            def _get(self):
                return 1

            def get(self):
                return self._get()

        def session():
            return Session()
    ''')
    ids = _labels_to_ids(extract_python(path))
    assert "._get()" in ids and ".get()" in ids, f"a method was dropped: {sorted(ids)}"
    assert ids["._get()"] != ids[".get()"]
    assert ids[".get()"].startswith(ids["Session"]), "method not scoped under its class"


def test_constructor_call_binds_to_the_salted_class(tmp_path: Path) -> None:
    """`session()`'s `Session()` call must reach the class node, not dangle or
    bind back to `session()` itself."""
    path = _write_py(tmp_path, '''
        class Session:
            pass

        def session():
            return Session()
    ''')
    result = extract_python(path)
    ids = _labels_to_ids(result)
    pairs = {(e["source"], e["target"]) for e in result["edges"]}
    assert (ids["session()"], ids["Session"]) in pairs, (
        f"no edge from session() to the Session class: {result['edges']}"
    )
    assert (ids["session()"], ids["session()"]) not in pairs


def test_cross_file_import_resolves_to_the_salted_class(tmp_path: Path) -> None:
    from graphify.build import build
    from graphify.extract import extract

    (tmp_path / "sessions.py").write_text(textwrap.dedent('''
        class Session:
            pass

        def session():
            return Session()
    '''))
    (tmp_path / "api.py").write_text(textwrap.dedent('''
        from sessions import Session, session

        def make():
            return Session(), session()
    '''))
    G = build([extract(sorted(tmp_path.glob("*.py")), root=tmp_path, cache_root=tmp_path)])
    label = {n: d.get("label") for n, d in G.nodes(data=True)}
    targets = {
        label.get(d.get("_tgt", v))
        for u, v, d in G.edges(data=True)
        if label.get(d.get("_src", u)) in ("api.py", "make()")
    }
    assert "Session" in targets, f"nothing from api.py reaches the class: {targets}"
    assert "session()" in targets, f"nothing from api.py reaches the function: {targets}"


def test_same_file_subclass_inherits_from_the_salted_class(tmp_path: Path) -> None:
    """`class Sub(Session)` must point at the real (salted) class, not mint a
    second sourceless `Session` stub under the plain id."""
    path = _write_py(tmp_path, '''
        class Session:
            pass

        def session():
            return Session()

        class Sub(Session):
            pass
    ''')
    result = extract_python(path)
    nodes = _rationale_free_nodes(result)
    assert [n["label"] for n in nodes].count("Session") == 1, (
        f"a phantom Session stub was minted: {[(n['id'], n['label']) for n in nodes]}"
    )
    ids = _labels_to_ids(result)
    inherits = {(e["source"], e["target"]) for e in result["edges"] if e.get("relation") == "inherits"}
    assert (ids["Sub"], ids["Session"]) in inherits


def test_decorated_class_and_function_case_collision_both_extracted(tmp_path: Path) -> None:
    """`@dataclass class Session` is wrapped in a decorated_definition; the
    pre-scan must see through it."""
    path = _write_py(tmp_path, '''
        from dataclasses import dataclass

        @dataclass
        class Session:
            x: int = 0

        def session():
            return Session()
    ''')
    ids = _labels_to_ids(extract_python(path))
    assert "Session" in ids and "session()" in ids, f"a declaration was dropped: {sorted(ids)}"
    assert ids["Session"] != ids["session()"]


def test_decorated_method_underscore_collision_both_extracted(tmp_path: Path) -> None:
    """The `_x` / `@property x` idiom: a decorated method collides like a bare one."""
    path = _write_py(tmp_path, '''
        class C:
            def _x(self):
                return 1

            @property
            def x(self):
                return self._x()
    ''')
    ids = _labels_to_ids(extract_python(path))
    assert "._x()" in ids and ".x()" in ids, f"a method was dropped: {sorted(ids)}"
    assert ids["._x()"] != ids[".x()"]
