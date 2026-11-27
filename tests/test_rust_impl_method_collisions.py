"""Rust impl-block members whose names fold to one node id.

``make_id`` casefolds and strips underscores, and unlike file-level items
(#3302, ``test_rust_case_collisions.py``) an impl block's methods, associated
consts and statics went straight through ``_make_id(parent_impl_nid, name)``
with no collision check at all: two members of one type differing only by a
leading ``_`` or by case minted one node, and the second declaration's own
body was credited to the first.
"""

from pathlib import Path

from graphify.extract import extract

_SVC_RS = (
    "struct Svc;\n"
    "\n"
    "impl Svc {\n"
    "    fn foo(&self) {\n"
    "        self.helper();\n"
    "    }\n"
    "    fn _foo(&self) {\n"
    "        self.other();\n"
    "    }\n"
    "    fn helper(&self) {}\n"
    "    fn other(&self) {}\n"
    "}\n"
)


def _extract(tmp_path: Path, source: str, name: str = "lib.rs") -> dict:
    path = tmp_path / name
    path.write_text(source, encoding="utf-8")
    return extract([path], cache_root=tmp_path, root=tmp_path, parallel=False)


def _sourced(result: dict, label: str) -> list[dict]:
    return [n for n in result["nodes"] if n.get("label") == label and n.get("source_file")]


def _edges(result: dict, relation: str) -> set[tuple[str, str]]:
    by_id = {n["id"]: n["label"] for n in result["nodes"]}
    return {
        (by_id.get(e["source"], ""), by_id.get(e["target"], ""))
        for e in result["edges"]
        if e.get("relation") == relation
    }


def test_methods_differing_by_underscore_get_separate_nodes(tmp_path: Path) -> None:
    result = _extract(tmp_path, _SVC_RS)
    foo = _sourced(result, ".foo()")
    foo_underscore = _sourced(result, "._foo()")
    assert len(foo) == 1 and len(foo_underscore) == 1
    assert foo[0]["id"] != foo_underscore[0]["id"]


def test_non_colliding_methods_keep_their_plain_ids(tmp_path: Path) -> None:
    """``helper``/``other`` have no sibling folding onto them, so they are
    unaffected: same ids as a build with no collision in the impl block."""
    solo = _extract(
        tmp_path,
        "struct Svc;\n\nimpl Svc {\n    fn helper(&self) {}\n    fn other(&self) {}\n}\n",
    )
    solo_ids = {n["id"] for n in solo["nodes"] if n.get("label") in (".helper()", ".other()")}

    result = _extract(tmp_path, _SVC_RS)
    ids = {n["id"] for n in result["nodes"] if n.get("label") in (".helper()", ".other()")}
    assert ids == solo_ids


def test_calls_from_each_colliding_method_bind_to_its_own_body(tmp_path: Path) -> None:
    """``foo``'s call to ``helper`` and ``_foo``'s call to ``other`` must not
    cross — before the fix both bodies were credited to whichever method
    kept the one shared node."""
    result = _extract(tmp_path, _SVC_RS)
    calls = _edges(result, "calls")
    assert (".foo()", ".helper()") in calls, calls
    assert ("._foo()", ".other()") in calls, calls
    assert (".foo()", ".other()") not in calls
    assert ("._foo()", ".helper()") not in calls


def test_collision_split_across_two_impl_blocks_of_one_type(tmp_path: Path) -> None:
    """The two impl blocks of ``Svc`` are one logical member set; a name
    declared in one block still collides with a sibling in the other."""
    src = (
        "struct Svc;\n"
        "\n"
        "impl Svc {\n"
        "    fn foo(&self) {\n"
        "        self.helper();\n"
        "    }\n"
        "    fn helper(&self) {}\n"
        "}\n"
        "\n"
        "impl Svc {\n"
        "    fn _foo(&self) {\n"
        "        self.other();\n"
        "    }\n"
        "    fn other(&self) {}\n"
        "}\n"
    )
    result = _extract(tmp_path, src)
    foo = _sourced(result, ".foo()")
    foo_underscore = _sourced(result, "._foo()")
    assert len(foo) == 1 and len(foo_underscore) == 1
    assert foo[0]["id"] != foo_underscore[0]["id"]
    calls = _edges(result, "calls")
    assert (".foo()", ".helper()") in calls
    assert ("._foo()", ".other()") in calls


def test_associated_const_colliding_with_a_method_name_also_splits(tmp_path: Path) -> None:
    """The same ``_make_id(parent_impl_nid, name)`` collision point is shared
    by methods and associated consts/statics, so a const can collide with a
    method too (``FOO`` the const, ``foo`` the method)."""
    src = (
        "struct Svc;\n"
        "\n"
        "impl Svc {\n"
        "    const FOO: u32 = 1;\n"
        "    fn foo(&self) {}\n"
        "}\n"
    )
    result = _extract(tmp_path, src)
    const_nodes = _sourced(result, ".FOO")
    method_nodes = _sourced(result, ".foo()")
    assert len(const_nodes) == 1 and len(method_nodes) == 1
    assert const_nodes[0]["id"] != method_nodes[0]["id"]


def test_case_only_methods_are_both_salted(tmp_path: Path) -> None:
    """With no declared-type precedent to defer to inside an impl block
    (mirrors ``test_case_only_functions_are_both_salted`` for file-level
    items), neither colliding method keeps the plain id."""
    plain = _sourced(
        _extract(tmp_path, "struct S;\n\nimpl S {\n    fn run(&self) {}\n}\n"), ".run()",
    )[0]["id"]

    result = _extract(
        tmp_path,
        "struct S;\n\nimpl S {\n    fn run(&self) {}\n    fn Run(&self) {}\n}\n",
    )
    lower, upper = _sourced(result, ".run()"), _sourced(result, ".Run()")
    assert len(lower) == 1 and len(upper) == 1
    assert lower[0]["id"] != upper[0]["id"]
    assert plain not in {lower[0]["id"], upper[0]["id"]}


def test_net_shrink_from_removing_one_colliding_method_is_not_lost(tmp_path: Path) -> None:
    before = _extract(tmp_path, _SVC_RS)
    after = _extract(
        tmp_path,
        _SVC_RS.replace("    fn _foo(&self) {\n        self.other();\n    }\n", ""),
    )
    before_count = len([n for n in before["nodes"] if n.get("source_file")])
    after_count = len([n for n in after["nodes"] if n.get("source_file")])
    assert before_count - after_count == 1
