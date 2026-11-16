"""A bare Go receiver type name is a same-package reference, so two packages
that each declare a type of that name must not collide into one corpus-wide
ambiguity (#5242). ``_resolve_go_member_calls`` looked a bare receiver type up
in a flat, corpus-wide ``type_def_nids`` table keyed only by the type's bare
label; with two packages each declaring e.g. ``Service``, the lookup found two
candidates and bailed as ambiguous (the god-node guard), dropping the
same-file ``s.helper()`` call for BOTH packages even though each call site's
own file has only one ``Service`` in scope.
"""
from __future__ import annotations

from pathlib import Path

from graphify.extract import extract

_GO_TEMPLATE = """package {pkg}

type {typ} struct{{}}

func (s *{typ}) helper() int {{ return 1 }}

func (s *{typ}) Run() int {{ return s.helper() }}
"""


def _build(tmp_path: Path, pkgs: list[tuple[str, str, str]]) -> dict:
    (tmp_path / "go.mod").write_text("module example.com/app\n\ngo 1.22\n")
    for pkg, fname, typ in pkgs:
        d = tmp_path / pkg
        d.mkdir(exist_ok=True)
        (d / fname).write_text(_GO_TEMPLATE.format(pkg=pkg, typ=typ))
    return extract(
        sorted(tmp_path.rglob("*.go")), root=tmp_path, cache_root=tmp_path / "cache", parallel=False,
    )


def _nid(result: dict, *, source_suffix: str, label: str) -> str:
    """The id of the one node in a given file whose label strips to ``label``."""
    matches = [
        n["id"] for n in result["nodes"]
        if str(n.get("source_file", "")).endswith(source_suffix)
        and str(n.get("label", "")).strip(".()") == label
    ]
    assert len(matches) == 1, (source_suffix, label, matches)
    return matches[0]


def _calls_pairs(result: dict) -> set[tuple[str, str]]:
    return {(e["source"], e["target"]) for e in result["edges"] if e["relation"] == "calls"}


def test_two_packages_declaring_the_same_type_name_each_keep_their_own_call(tmp_path: Path) -> None:
    result = _build(tmp_path, [("alpha", "impl.go", "Service"), ("beta", "impl.go", "Service")])
    pairs = _calls_pairs(result)

    alpha_run = _nid(result, source_suffix="alpha/impl.go", label="Run")
    alpha_helper = _nid(result, source_suffix="alpha/impl.go", label="helper")
    beta_run = _nid(result, source_suffix="beta/impl.go", label="Run")
    beta_helper = _nid(result, source_suffix="beta/impl.go", label="helper")

    assert (alpha_run, alpha_helper) in pairs, pairs
    assert (beta_run, beta_helper) in pairs, pairs
    # Each package's call must resolve to its OWN helper, never the other
    # package's same-named one.
    assert (alpha_run, beta_helper) not in pairs, pairs
    assert (beta_run, alpha_helper) not in pairs, pairs


def test_two_packages_same_type_name_different_file_names(tmp_path: Path) -> None:
    """Control: the collision is about the package, not the file name."""
    result = _build(tmp_path, [("alpha", "a.go", "Service"), ("beta", "b.go", "Service")])
    pairs = _calls_pairs(result)

    alpha_run = _nid(result, source_suffix="alpha/a.go", label="Run")
    alpha_helper = _nid(result, source_suffix="alpha/a.go", label="helper")
    beta_run = _nid(result, source_suffix="beta/b.go", label="Run")
    beta_helper = _nid(result, source_suffix="beta/b.go", label="helper")

    assert (alpha_run, alpha_helper) in pairs, pairs
    assert (beta_run, beta_helper) in pairs, pairs


def test_a_uniquely_named_type_still_resolves(tmp_path: Path) -> None:
    """Control: a single package declaring the type keeps working as before."""
    result = _build(tmp_path, [("alpha", "impl.go", "Service")])
    pairs = _calls_pairs(result)

    run = _nid(result, source_suffix="alpha/impl.go", label="Run")
    helper = _nid(result, source_suffix="alpha/impl.go", label="helper")
    assert (run, helper) in pairs, pairs


def test_three_packages_only_two_colliding_the_unique_one_still_resolves(tmp_path: Path) -> None:
    """Control: an unrelated, uniquely named type in a third package is
    unaffected by a collision between the other two."""
    result = _build(tmp_path, [
        ("alpha", "a.go", "Service"), ("beta", "b.go", "Service"), ("gamma", "c.go", "Other"),
    ])
    pairs = _calls_pairs(result)

    gamma_run = _nid(result, source_suffix="gamma/c.go", label="Run")
    gamma_helper = _nid(result, source_suffix="gamma/c.go", label="helper")
    assert (gamma_run, gamma_helper) in pairs, pairs
