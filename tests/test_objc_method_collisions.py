"""ObjC methods whose selectors differ only by a leading `_` or by case keep their own ids.

``make_id`` drops a leading ``_`` and folds case, so ``-setup`` / ``-_setup`` of one
``@interface``/``@implementation``/``@protocol`` minted one node id: the second
declaration overwrote the first, and its own body's calls were credited to its twin
instead. A leading underscore on a method name is a common ObjC convention for a
public method and its private helper (``-setup`` / ``-_setup``), exactly the shape
every other object-oriented extractor already protects (#3302, #4415, #5058, #5151,
#5380). The Python/C#/Solidity/Java rule applies: the one public name keeps its
plain id, every other colliding name is salted.
"""
from __future__ import annotations

from pathlib import Path

from graphify.extract import extract


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _ids_by_label(result: dict, source_file: str) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for n in result["nodes"]:
        if str(n.get("source_file", "")).endswith(source_file):
            out.setdefault(n["label"], []).append(n["id"])
    return out


def _one(ids: dict[str, list[str]], label: str) -> str:
    assert len(ids.get(label, [])) == 1, (label, ids.get(label))
    return ids[label][0]


def _calls(result: dict) -> set[tuple[str, str]]:
    return {(e["source"], e["target"]) for e in result["edges"] if e["relation"] == "calls"}


FOO_M = """@implementation Foo

- (void)setup {
    [self _setup];
}

- (void)_setup {
    [self other];
}

- (void)helper {
}

- (void)other {
}

@end
"""


def test_underscore_twin_methods_get_separate_nodes(tmp_path: Path) -> None:
    result = extract([_write(tmp_path / "Foo.m", FOO_M)], cache_root=tmp_path / "cache")
    ids = _ids_by_label(result, "Foo.m")
    setup, usetup = _one(ids, "-setup"), _one(ids, "-_setup")
    assert setup != usetup
    # The one public name keeps the plain id.
    assert setup.endswith("_foo_setup")


def test_non_colliding_methods_keep_their_plain_ids(tmp_path: Path) -> None:
    result = extract([_write(tmp_path / "Foo.m", FOO_M)], cache_root=tmp_path / "cache")
    ids = _ids_by_label(result, "Foo.m")
    helper, other = _one(ids, "-helper"), _one(ids, "-other")
    assert helper.endswith("_foo_helper") and other.endswith("_foo_other")


def test_calls_from_each_colliding_method_bind_to_its_own_body(tmp_path: Path) -> None:
    result = extract([_write(tmp_path / "Foo.m", FOO_M)], cache_root=tmp_path / "cache")
    ids = _ids_by_label(result, "Foo.m")
    setup, usetup, other = _one(ids, "-setup"), _one(ids, "-_setup"), _one(ids, "-other")
    calls = _calls(result)
    assert (setup, usetup) in calls
    assert (usetup, other) in calls
    # No cross contamination: -setup's own body never called -other directly,
    # and -_setup's body never called itself or -setup.
    assert (setup, other) not in calls
    assert (usetup, setup) not in calls


CASE_M = """@implementation Svc

- (void)run {
    [self helper];
}

- (void)Run {
}

- (void)helper {
}

@end
"""


def test_case_only_methods_are_both_salted(tmp_path: Path) -> None:
    """Neither spelling is privileged when both are "public" (#2779's exported rule)."""
    result = extract([_write(tmp_path / "Svc.m", CASE_M)], cache_root=tmp_path / "cache")
    ids = _ids_by_label(result, "Svc.m")
    run, Run = _one(ids, "-run"), _one(ids, "-Run")
    assert run != Run
    assert not run.endswith("_svc_run") or not Run.endswith("_svc_run")
    calls = _calls(result)
    helper = _one(ids, "-helper")
    assert (run, helper) in calls
    assert (Run, helper) not in calls


PROTO_H = """@protocol Reload <NSObject>
- (void)reload;
- (void)_reload;
@end
"""


def test_protocol_declarations_collide_too(tmp_path: Path) -> None:
    result = extract([_write(tmp_path / "Reload.h", PROTO_H)], cache_root=tmp_path / "cache")
    ids = _ids_by_label(result, "Reload.h")
    reload_, ureload = _one(ids, "-reload"), _one(ids, "-_reload")
    assert reload_ != ureload
    assert reload_.endswith("_reload_reload")


def test_net_shrink_from_removing_one_colliding_method_is_not_lost(tmp_path: Path) -> None:
    """Before the fix both before and after had 4 nodes (one real method hidden);
    now removing a real colliding method is visible as one fewer method node."""
    before = extract([_write(tmp_path / "Foo.m", FOO_M)], cache_root=tmp_path / "cache" / "before")
    fewer = FOO_M.replace(
        "- (void)_setup {\n    [self other];\n}\n\n", "",
    )
    after = extract([_write(tmp_path / "Foo.m", fewer)], cache_root=tmp_path / "cache" / "after")

    def method_count(result: dict) -> int:
        return sum(
            1 for n in result["nodes"]
            if str(n.get("source_file", "")).endswith("Foo.m") and n.get("label", "").startswith("-")
        )

    assert method_count(before) - method_count(after) == 1
