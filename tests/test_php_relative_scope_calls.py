"""PHP relative-scope calls must not name a callee (#39).

``parent::setUp()`` / ``self::foo()`` / ``static::bar()`` are *relative* scopes:
which class they denote depends on inheritance context the raw-call facts do not
carry.  The ``scoped_call_expression`` handler used to take the scope text as the
callee name, so ``parent::setUp()`` produced a raw call to a callee literally
named ``parent`` — which the cross-file pass then matched, by normalized label,
against any unrelated ``->parent()`` method in the corpus.

Refusal over guessing: the relative scopes name no callee at all.  Absolute
scopes (``Helper::format()``) are unaffected.
"""
from __future__ import annotations

from pathlib import Path

from graphify.extract import extract


def _calls(tmp_path: Path, files: dict[str, str]):
    """Extract ``files`` (name -> source) and return ({(src, tgt): edge}, result)."""
    paths = []
    for name, body in files.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
        paths.append(path)
    result = extract(paths, cache_root=tmp_path / "graphify-out")
    calls = {
        (edge["source"], edge["target"]): edge
        for edge in result["edges"]
        if edge.get("relation") == "calls"
    }
    return calls, result


def _find(result: dict, label: str, id_contains: str) -> str:
    nid = next(
        (
            node["id"]
            for node in result["nodes"]
            if node.get("label") == label and id_contains in node["id"]
        ),
        None,
    )
    assert nid is not None, f"no node {label}/{id_contains}"
    return nid


def _relative_scope_corpus(scope: str, callee: str) -> dict[str, str]:
    """A caller using ``<scope>::<callee>()`` plus an unrelated decoy method.

    The decoy is named after the SCOPE (``parent`` / ``self`` / ``static``) —
    that is the label the buggy callee name matched against corpus-wide.
    """
    return {
        "app/A.php": (
            "<?php\nnamespace App;\n"
            "class A extends Base {\n"
            f"    public function setUp(): void {{ {scope}::{callee}(); }}\n"
            "}\n"
        ),
        "app/Unrelated.php": (
            "<?php\nnamespace App;\n"
            "class B {\n"
            f"    public function {scope}(): int {{ return 1; }}\n"
            "}\n"
        ),
    }


def test_parent_scope_mints_no_call_to_unrelated_parent_method(tmp_path: Path):
    """`parent::setUp()` must not resolve to an unrelated `B::parent()`."""
    calls, r = _calls(tmp_path, _relative_scope_corpus("parent", "setUp"))

    set_up = _find(r, ".setUp()", "app_a_a_setup")
    decoy = _find(r, ".parent()", "app_unrelated_b_parent")
    assert (set_up, decoy) not in calls


def test_self_scope_mints_no_call_to_unrelated_self_method(tmp_path: Path):
    calls, r = _calls(tmp_path, _relative_scope_corpus("self", "boot"))

    set_up = _find(r, ".setUp()", "app_a_a_setup")
    decoy = _find(r, ".self()", "app_unrelated_b_self")
    assert (set_up, decoy) not in calls


def test_static_scope_mints_no_call_to_unrelated_static_method(tmp_path: Path):
    calls, r = _calls(tmp_path, _relative_scope_corpus("static", "make"))

    set_up = _find(r, ".setUp()", "app_a_a_setup")
    decoy = _find(r, ".static()", "app_unrelated_b_static")
    assert (set_up, decoy) not in calls


def test_absolute_scoped_call_still_resolves(tmp_path: Path):
    """Positive control: `Helper::format()` still targets the `Helper` class.

    Same corpus shape as the refusal tests, so the refusal is demonstrably
    scoped to the relative names and not to scoped calls in general.
    """
    calls, r = _calls(tmp_path, {
        "app/Support/Helper.php": (
            "<?php\nnamespace App\\Support;\n"
            "class Helper {\n"
            "    public static function format(string $s): string { return $s; }\n"
            "}\n"
        ),
        "app/A.php": (
            "<?php\nnamespace App;\n"
            "use App\\Support\\Helper;\n"
            "class A {\n"
            "    public function setUp(): void { Helper::format('x'); }\n"
            "}\n"
        ),
    })

    set_up = _find(r, ".setUp()", "app_a_a_setup")
    helper = _find(r, "Helper", "app_support_helper_helper")
    assert (set_up, helper) in calls
