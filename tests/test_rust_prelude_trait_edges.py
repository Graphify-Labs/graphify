"""A Rust `implements` / `inherits` edge must name the trait, not its argument.

The trait written in `impl Tr<A> for B` or `trait T: Tr<A>` is the first type
reference collected from that position, and it took the edge by being first. A
prelude trait (`From`, `Into`, `PartialEq`, ...) makes no node, so in
`impl From<A> for B` the first reference left is `A`, and the graph said
`B implements A`. `Fn(A) -> R` sugar put its parameter type there the same way.

These tests pin the argument to a `references[generic_arg]` edge, and a trait
that does make a node (user-defined, or a local one shadowing the prelude name)
to its `implements` / `inherits` edge.
"""
from __future__ import annotations

from graphify.extract import extract

_TEMPERATURES = "pub struct Celsius(pub f64);\npub struct Fahrenheit(pub f64);\n"
_JOBS = "pub struct Job;\npub struct Report;\n"


def _check_trait_edges(tmp_path, source, expected):
    (tmp_path / "lib.rs").write_text(source, encoding="utf-8")
    r = extract([tmp_path / "lib.rs"], cache_root=tmp_path / "graphify-out")
    label = {n["id"]: n["label"] for n in r["nodes"]}
    got = {
        (label[e["source"]], e["relation"], label[e["target"]])
        for e in r["edges"]
        if e["relation"] in ("implements", "inherits") or e.get("context") == "generic_arg"
    }
    assert got == expected


def test_prelude_trait_impl_does_not_implement_its_type_argument(tmp_path):
    _check_trait_edges(
        tmp_path,
        _TEMPERATURES
        + "impl From<Celsius> for Fahrenheit {\n"
        "    fn from(c: Celsius) -> Self { Fahrenheit(c.0 * 1.8 + 32.0) }\n"
        "}\n",
        {("Fahrenheit", "references", "Celsius")},
    )


def test_prelude_supertrait_does_not_inherit_its_type_argument(tmp_path):
    _check_trait_edges(
        tmp_path,
        _TEMPERATURES + "pub trait Reading: Into<Celsius> {}\n",
        {("Reading", "references", "Celsius")},
    )


def test_fn_sugar_supertrait_does_not_inherit_its_parameter_type(tmp_path):
    _check_trait_edges(
        tmp_path,
        _JOBS + "pub trait Handler: Fn(Job) -> Report {}\n",
        {("Handler", "references", "Job"), ("Handler", "references", "Report")},
    )


def test_higher_ranked_fn_supertrait_does_not_inherit_its_parameter_type(tmp_path):
    _check_trait_edges(
        tmp_path,
        _JOBS + "pub trait Visitor: for<'a> Fn(&'a Job) -> Report {}\n",
        {("Visitor", "references", "Job"), ("Visitor", "references", "Report")},
    )


def test_user_trait_with_type_argument_keeps_its_trait_edge(tmp_path):
    _check_trait_edges(
        tmp_path,
        _TEMPERATURES
        + "pub trait Convert<T> {}\n"
        "impl Convert<Celsius> for Fahrenheit {}\n"
        "pub trait Reading: Convert<Celsius> {}\n"
        "pub trait Borrowed: for<'a> Convert<&'a Celsius> {}\n",
        {
            ("Fahrenheit", "implements", "Convert"),
            ("Fahrenheit", "references", "Celsius"),
            ("Reading", "inherits", "Convert"),
            ("Reading", "references", "Celsius"),
            ("Borrowed", "inherits", "Convert"),
            ("Borrowed", "references", "Celsius"),
        },
    )


def test_locally_defined_prelude_trait_keeps_its_trait_edge(tmp_path):
    # A file that defines its own `From` shadows the prelude: that trait is a
    # node, so it is what the impl implements.
    _check_trait_edges(
        tmp_path,
        _TEMPERATURES + "pub trait From<T> {}\nimpl From<Celsius> for Fahrenheit {}\n",
        {("Fahrenheit", "implements", "From"), ("Fahrenheit", "references", "Celsius")},
    )
