from __future__ import annotations

from pathlib import Path

from graphify.extract import extract


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _node_ids(result: dict, label: str, source_file: str) -> set[str]:
    return {
        n["id"] for n in result["nodes"]
        if n.get("label") == label and n.get("source_file") == source_file
    }


def _calls_targets(result: dict, caller_label: str, source_file: str) -> set[str]:
    caller_ids = _node_ids(result, caller_label, source_file)
    assert caller_ids
    return {
        e["target"] for e in result["edges"]
        if e["relation"] == "calls" and e["source"] in caller_ids
    }


def test_sibling_function_call_not_shadowed_by_unrelated_local_import(tmp_path: Path):
    """`caller`'s own `from .helper import target` binds `target` inside `caller`
    alone. `other_caller`'s bare `target()` has no import of its own, so it must
    keep resolving to this file's own module-level `target`, not inherit
    `caller`'s alias to `helper.target` through the shared per-file lookup
    (#5421's second, deferred scenario).
    """
    helper = _write(tmp_path / "pkg" / "helper.py", "def target():\n    return 1\n")
    mod = _write(
        tmp_path / "pkg" / "mod.py",
        "def target():\n"
        "    return 0\n\n"
        "def caller():\n"
        "    from .helper import target\n"
        "    target()\n\n"
        "def other_caller():\n"
        "    target()\n",
    )
    result = extract([helper, mod], cache_root=tmp_path)

    other_targets = _calls_targets(result, "other_caller()", "pkg/mod.py")
    mod_target_ids = _node_ids(result, "target()", "pkg/mod.py")
    helper_target_ids = _node_ids(result, "target()", "pkg/helper.py")

    assert other_targets & mod_target_ids, "other_caller must still resolve to the same-file target"
    assert not (other_targets & helper_target_ids), (
        "other_caller must not inherit caller's own function-local import alias"
    )


def test_own_function_local_import_still_resolves_correctly(tmp_path: Path):
    """A function's own local import must keep resolving its own call, scope
    tracking must not break the case it is meant to leave alone.
    """
    helper = _write(tmp_path / "pkg" / "helper.py", "def target():\n    return 1\n")
    mod = _write(
        tmp_path / "pkg" / "mod.py",
        "def target():\n"
        "    return 0\n\n"
        "def caller():\n"
        "    from .helper import target\n"
        "    target()\n",
    )
    result = extract([helper, mod], cache_root=tmp_path)

    caller_targets = _calls_targets(result, "caller()", "pkg/mod.py")
    helper_target_ids = _node_ids(result, "target()", "pkg/helper.py")

    assert caller_targets & helper_target_ids, "caller's own local import must still resolve correctly"
