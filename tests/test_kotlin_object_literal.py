"""Kotlin anonymous-object members (#2347).

`object : Foo { ... }` (node type `object_literal`) got no nodes at all:
object_literal is not a class_type (it has no name), and the function branch
never recurses into function bodies — so the literal's members AND every call
inside them were silently dropped. The extractor now emits an owner node per
literal (labeled after its first supertype), a `contains` edge from the
enclosing function, the implements/inherits edge to the supertype, and walks
the literal's class_body like a class so members flow normally.
"""
from __future__ import annotations

import os
from pathlib import Path

from graphify.extract import extract


def _extract(tmp_path, files: dict[str, str]):
    for name, body in files.items():
        p = tmp_path / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body)
    old = os.getcwd()
    try:
        os.chdir(tmp_path)
        r = extract([Path(n) for n in files], cache_root=tmp_path / ".cache")
    finally:
        os.chdir(old)
    return r


def _edges(r, relation):
    return {(e["source"], e["target"]) for e in r["edges"] if e["relation"] == relation}


def _find(r, label, id_contains=""):
    return next(n["id"] for n in r["nodes"]
                if n["label"] == label and id_contains in n["id"])


_REGISTRY = {
    "Registry.kt": (
        "interface EventListener {\n"
        "    fun process(e: Event)\n"
        "}\n"
        "class Event\n"
        "class Registry {\n"
        "    fun register() {\n"
        "        val listener = object : EventListener {\n"
        "            fun process(e: Event) { handleSomething(e) }\n"
        "            fun handleSomething(e: Event) { }\n"
        "        }\n"
        "    }\n"
        "}\n"
    ),
}


def test_object_literal_members_get_nodes_and_method_edges(tmp_path):
    r = _extract(tmp_path, _REGISTRY)
    obj_nid = _find(r, "EventListener", "object")
    process = _find(r, ".process()", "object")
    handle = _find(r, ".handleSomething()", "object")
    methods = _edges(r, "method")
    assert (obj_nid, process) in methods, "anonymous-object member must hang off the owner"
    assert (obj_nid, handle) in methods, "anonymous-object member must hang off the owner"
    # The owner itself is contained by the enclosing function.
    register = _find(r, ".register()", "registry")
    assert (register, obj_nid) in _edges(r, "contains"), \
        "the enclosing function contains the anonymous object"


def test_object_literal_implements_supertype(tmp_path):
    r = _extract(tmp_path, _REGISTRY)
    obj_nid = _find(r, "EventListener", "object")
    iface = next(n["id"] for n in r["nodes"]
                 if n["label"] == "EventListener" and "object" not in n["id"])
    assert (obj_nid, iface) in _edges(r, "implements"), \
        "object : EventListener must implement the in-corpus interface"


def test_object_literal_member_calls_sibling_member(tmp_path):
    r = _extract(tmp_path, _REGISTRY)
    process = _find(r, ".process()", "object")
    handle = _find(r, ".handleSomething()", "object")
    assert (process, handle) in _edges(r, "calls"), \
        "a call between two anonymous-object members must resolve"


def test_two_object_literals_in_one_function_do_not_collide(tmp_path):
    r = _extract(tmp_path, {
        "Make.kt": (
            "interface Alpha {\n"
            "    fun one()\n"
            "}\n"
            "interface Beta {\n"
            "    fun two()\n"
            "}\n"
            "class Maker {\n"
            "    fun make() {\n"
            "        val a = object : Alpha {\n"
            "            fun one() { }\n"
            "        }\n"
            "        val b = object : Beta {\n"
            "            fun two() { }\n"
            "        }\n"
            "    }\n"
            "}\n"
        ),
    })
    obj_a = _find(r, "Alpha", "object")
    obj_b = _find(r, "Beta", "object")
    assert obj_a != obj_b
    methods = _edges(r, "method")
    one = _find(r, ".one()", "object")
    two = _find(r, ".two()", "object")
    assert (obj_a, one) in methods
    assert (obj_b, two) in methods
    assert (obj_a, two) not in methods, "members must not leak across sibling literals"
    assert (obj_b, one) not in methods, "members must not leak across sibling literals"


def test_named_object_and_plain_class_unchanged(tmp_path):
    """Keep-the-bar: named `object` declarations and plain classes extract
    exactly as before — the literal handling is purely additive."""
    r = _extract(tmp_path, {
        "Mix.kt": (
            "object Singleton {\n"
            "    fun go() { }\n"
            "}\n"
            "class Plain {\n"
            "    fun run() { go2() }\n"
            "    fun go2() { }\n"
            "}\n"
        ),
    })
    singleton = _find(r, "Singleton")
    plain = _find(r, "Plain")
    methods = _edges(r, "method")
    go = _find(r, ".go()")
    run = _find(r, ".run()")
    go2 = _find(r, ".go2()")
    assert (singleton, go) in methods
    assert (plain, run) in methods and (plain, go2) in methods
    assert (run, go2) in _edges(r, "calls")
    assert not any("object" in n["id"] and n["label"].startswith("object@")
                   for n in r["nodes"]), "no phantom object-literal owner nodes"
