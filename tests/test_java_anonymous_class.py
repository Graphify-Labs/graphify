"""Java/Groovy anonymous-class members (the Java twin of Kotlin #2347).

`new Runnable() { ... }` keeps its body as a `class_body` hanging off an
`object_creation_expression`. That node is not a class_type and the function
branch never recurses into bodies, so the anonymous class's methods AND every
call inside them were silently dropped — a large loss given how routine
anonymous listeners/callbacks are in Java. The extractor now emits an owner
node per anonymous class (labeled after the base type), a `contains` edge from
the enclosing method, and walks the body like a class so members and their
calls flow normally. The subtype relation is deliberately NOT asserted: an
anonymous class usually realises a library interface/class whose kind is
unknowable from this file (fail-closed).
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


_APP = {
    "App.java": (
        "class App {\n"
        "    void setup() {\n"
        "        Runnable r = new Runnable() {\n"
        "            public void run() { helper(); }\n"
        "        };\n"
        "    }\n"
        "    void helper() {}\n"
        "}\n"
    ),
}


def test_anonymous_class_members_get_nodes_and_method_edges(tmp_path):
    r = _extract(tmp_path, _APP)
    obj_nid = _find(r, "Runnable", "object")
    run = _find(r, ".run()", "object")
    methods = _edges(r, "method")
    assert (obj_nid, run) in methods, "anonymous-class member must hang off the owner"
    # The owner itself is contained by the enclosing method.
    setup = _find(r, ".setup()", "app_setup")
    assert (setup, obj_nid) in _edges(r, "contains"), \
        "the enclosing method contains the anonymous class"


def test_anonymous_class_member_call_resolves_to_enclosing_method(tmp_path):
    r = _extract(tmp_path, _APP)
    run = _find(r, ".run()", "object")
    helper = _find(r, ".helper()", "app_helper")
    assert (run, helper) in _edges(r, "calls"), \
        "a call made inside an anonymous-class method was dropped"


def test_two_anonymous_classes_in_one_method_do_not_collide(tmp_path):
    r = _extract(tmp_path, {
        "App.java": (
            "import java.util.Comparator;\n"
            "class App {\n"
            "    void setup() {\n"
            "        Runnable a = new Runnable() {\n"
            "            public void run() { doWork(); }\n"
            "        };\n"
            "        Comparator<Integer> c = new Comparator<Integer>() {\n"
            "            public int compare(Integer x, Integer y) { return rank(x); }\n"
            "        };\n"
            "    }\n"
            "    void doWork() {}\n"
            "    int rank(Integer x) { return 0; }\n"
            "}\n"
        ),
    })
    run = _find(r, ".run()", "object")
    compare = _find(r, ".compare()", "object")
    assert run != compare, "two anonymous classes collapsed onto one node"
    calls = _edges(r, "calls")
    assert (run, _find(r, ".doWork()", "app_dowork")) in calls
    assert (compare, _find(r, ".rank()", "app_rank")) in calls
