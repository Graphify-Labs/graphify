"""Scala 3 `given ... with` members are scoped to the given, not file scope (#4130).

A `given intShow: Show[Int] with` instance owns its `def`s. They used to leak to
file scope, where `show` (cased to `_show`) collided with the trait TYPE node
`Show` — so the given's call/reference edges landed on the trait. The given is now
a class-like container; an anonymous `given Show[String] with` gets a synthesized
name so its members are kept (scoped) instead of dropped.
"""
from __future__ import annotations

from pathlib import Path

from graphify.extract import extract_scala

SRC = (
    "trait Show[A]:\n"
    "  def show(a: A): String\n"
    "\n"
    "given intShow: Show[Int] with\n"
    "  def show(a: Int): String = helper(a)\n"
    "  def helper(a: Int): String = a.toString\n"
    "\n"
    "given Show[String] with\n"
    "  def show(a: String): String = a\n"
)


def _graph(tmp_path):
    f = tmp_path / "given.scala"
    f.write_text(SRC, encoding="utf-8")
    r = extract_scala(f)
    label = {n["id"]: str(n.get("label", "")) for n in r["nodes"]}
    return r, label


def _method(r, label, owner, method):
    return any(
        e.get("relation") == "method"
        and label.get(e.get("source")) == owner
        and label.get(e.get("target")) == method
        for e in r["edges"]
    )


def test_named_given_owns_its_methods(tmp_path):
    r, label = _graph(tmp_path)
    assert _method(r, label, "intShow", ".show()"), "given's show not scoped to the given"
    assert _method(r, label, "intShow", ".helper()"), "given's helper not scoped to the given"


def test_intra_given_call_resolves(tmp_path):
    r, label = _graph(tmp_path)
    calls = {
        (label.get(e["source"]), label.get(e["target"]))
        for e in r["edges"] if e.get("relation") == "calls"
    }
    assert (".show()", ".helper()") in calls


def test_trait_method_is_untouched_by_the_given(tmp_path):
    r, label = _graph(tmp_path)
    assert _method(r, label, "Show", ".show()"), "trait lost its own method"
    # The trait TYPE node must carry no call/method edge stolen from the given.
    show_trait_id = next(
        n["id"] for n in r["nodes"]
        if n.get("label") == "Show" and n.get("source_file")
    )
    for e in r["edges"]:
        if e.get("source") == show_trait_id and e.get("relation") == "calls":
            raise AssertionError(f"given's call leaked onto the trait node: {e}")


def test_given_members_do_not_leak_to_file_scope(tmp_path):
    r, _ = _graph(tmp_path)
    labels = [n.get("label") for n in r["nodes"]]
    # a leaked member would be a bare, file-scoped `helper()` (no leading dot)
    assert "helper()" not in labels, "given member leaked to file scope"


def test_anonymous_given_members_are_kept(tmp_path):
    r, label = _graph(tmp_path)
    # the anonymous `given Show[String] with` is scoped under a synthesized owner,
    # distinct from the trait node, and still owns its show().
    assert _method(r, label, "given Show", ".show()"), "anonymous given's members dropped"
    trait_id = next(n["id"] for n in r["nodes"] if n.get("label") == "Show" and n.get("source_file"))
    anon_ids = [n["id"] for n in r["nodes"] if n.get("label") == "given Show"]
    assert anon_ids and trait_id not in anon_ids, "anonymous given collided with the trait node"
