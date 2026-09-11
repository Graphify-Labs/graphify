"""Kotlin member calls resolve through the receiver's declared type.

The shared cross-file pass skips member calls, so `greeter.greet()` on a receiver
whose class lives in another file produced no edge at all — the Kotlin twin of the
Swift gap in #1356. Each case below pins one source of the receiver's type, and the
negative cases pin what must stay unresolved: an untyped receiver, an ambiguous class
name, and a builtin type that happens to share a name with a local class.
"""
from __future__ import annotations

import importlib

import pytest

from graphify.extract import extract

pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("tree_sitter_kotlin") is None,
    reason="tree_sitter_kotlin not installed",
)

GREETER = "class Greeter {\n    fun greet() {}\n}\n"


def _calls(tmp_path, files: dict[str, str]):
    for name, body in files.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
    result = extract([tmp_path / n for n in files],
                     cache_root=tmp_path / "graphify-out", parallel=False)
    label = {n["id"]: n["label"] for n in result["nodes"]}
    calls = {(label.get(e["source"]), label.get(e["target"])): e
             for e in result["edges"] if e["relation"] == "calls"}
    return calls, result


def _greet_edge(calls: dict) -> dict | None:
    return next((e for (src, tgt), e in calls.items()
                 if src and "run" in src and tgt == ".greet()"), None)


def test_a_primary_constructor_parameter_types_the_receiver(tmp_path):
    # Kotlin's idiomatic injection point declares no property, so nothing else in
    # the walk ever names `greeter`'s type.
    calls, _ = _calls(tmp_path, {
        "Greeter.kt": GREETER,
        "App.kt": "class App(private val greeter: Greeter) {\n"
                  "    fun run() { greeter.greet() }\n"
                  "}\n",
    })
    edge = _greet_edge(calls)
    assert edge is not None, calls
    assert edge["confidence"] == "INFERRED"


def test_an_annotated_property_types_the_receiver(tmp_path):
    calls, _ = _calls(tmp_path, {
        "Greeter.kt": GREETER,
        "App.kt": "class App {\n"
                  "    private val greeter: Greeter = Greeter()\n"
                  "    fun run() { greeter.greet() }\n"
                  "}\n",
    })
    assert _greet_edge(calls) is not None, calls


def test_a_constructor_call_types_an_unannotated_local(tmp_path):
    calls, _ = _calls(tmp_path, {
        "Greeter.kt": GREETER,
        "App.kt": "class App {\n"
                  "    fun run() {\n"
                  "        val greeter = Greeter()\n"
                  "        greeter.greet()\n"
                  "    }\n"
                  "}\n",
    })
    assert _greet_edge(calls) is not None, calls


def test_a_function_parameter_types_the_receiver(tmp_path):
    calls, _ = _calls(tmp_path, {
        "Greeter.kt": GREETER,
        "App.kt": "class App {\n"
                  "    fun run(greeter: Greeter) { greeter.greet() }\n"
                  "}\n",
    })
    assert _greet_edge(calls) is not None, calls


def test_an_object_receiver_is_the_type_itself(tmp_path):
    # `Registry.register()` names the type in source, so the edge is exact.
    calls, _ = _calls(tmp_path, {
        "Registry.kt": "object Registry {\n    fun register() {}\n}\n",
        "App.kt": "class App {\n    fun run() { Registry.register() }\n}\n",
    })
    edge = next((e for (src, tgt), e in calls.items()
                 if src and "run" in src and tgt == ".register()"), None)
    assert edge is not None, calls
    assert edge["confidence"] == "EXTRACTED"


def test_an_untyped_receiver_resolves_to_nothing(tmp_path):
    calls, _ = _calls(tmp_path, {
        "Greeter.kt": GREETER,
        "App.kt": "class App {\n"
                  "    fun run(greeter: Any) { greeter.greet() }\n"
                  "}\n",
    })
    assert _greet_edge(calls) is None, calls


def test_two_classes_of_the_same_name_resolve_to_neither(tmp_path):
    # The single-definition guard: guessing one of two `Greeter`s is worse than
    # leaving the call unresolved.
    calls, _ = _calls(tmp_path, {
        "a/Greeter.kt": GREETER,
        "b/Greeter.kt": GREETER,
        "App.kt": "class App(private val greeter: Greeter) {\n"
                  "    fun run() { greeter.greet() }\n"
                  "}\n",
    })
    assert _greet_edge(calls) is None, calls


def test_a_builtin_receiver_type_does_not_reach_a_same_named_class(tmp_path):
    # A local `class Regex` must not answer for `kotlin.text.Regex`.
    calls, _ = _calls(tmp_path, {
        "Regex.kt": "class Regex {\n    fun greet() {}\n}\n",
        "App.kt": "class App {\n"
                  "    fun run(r: Regex) { r.greet() }\n"
                  "}\n",
    })
    assert _greet_edge(calls) is None, calls


def test_a_parameter_types_its_own_function_without_retyping_the_property(tmp_path):
    # The receiver table is function-scoped for parameters and locals, so the two `greeter`
    # receivers are two names: the parameter answers inside `other`, the property in `run`.
    calls, result = _calls(tmp_path, {
        "Greeter.kt": GREETER,
        "Other.kt": "class Other {\n    fun greet() {}\n}\n",
        "App.kt": "class App {\n"
                  "    private val greeter: Greeter = Greeter()\n"
                  "    fun run() { greeter.greet() }\n"
                  "    fun other(greeter: Other) { greeter.greet() }\n"
                  "}\n",
    })
    source_of = {n["id"]: str(n.get("source_file") or "") for n in result["nodes"]}
    label_of = {n["id"]: n["label"] for n in result["nodes"]}
    targets_by_caller = {}
    for e in result["edges"]:
        if e["relation"] == "calls" and label_of.get(e["target"]) == ".greet()":
            targets_by_caller.setdefault(label_of.get(e["source"]), set()).add(
                source_of[e["target"]].rsplit("/", 1)[-1])
    assert targets_by_caller == {".run()": {"Greeter.kt"}, ".other()": {"Other.kt"}}, calls


def test_a_local_in_one_function_does_not_type_a_receiver_in_another(tmp_path):
    # `svc` in two bodies is two names. A file-wide table hands the second function the
    # first one's type, and `svc`/`client`/`repo` twice in a class is the common case.
    calls, _ = _calls(tmp_path, {
        "Alpha.kt": "class Alpha {\n    fun doThing() {}\n}\n",
        "Beta.kt": "class Beta {\n    fun doThing() {}\n}\n",
        "App.kt": "class App {\n"
                  "    fun a() {\n"
                  "        val svc = Alpha()\n"
                  "        svc.doThing()\n"
                  "    }\n"
                  "    fun b() {\n"
                  "        val svc = Beta()\n"
                  "        svc.doThing()\n"
                  "    }\n"
                  "}\n",
    })
    edges = {src: e["target"] for (src, tgt), e in calls.items() if tgt == ".doThing()"}
    assert set(edges) == {".a()", ".b()"}, calls
    assert "alpha" in edges[".a()"].lower(), edges
    assert "beta" in edges[".b()"].lower(), edges


def test_a_qualified_call_still_reaches_the_package_resolver(tmp_path):
    # A >= 3-segment chain is an FQN, not a receiver, and stays with #2550's pass.
    calls, _ = _calls(tmp_path, {
        "Greeter.kt": "package com.example\n\nobject Greeter {\n    fun greet() {}\n}\n",
        "App.kt": "class App {\n    fun run() { com.example.Greeter.greet() }\n}\n",
    })
    edge = _greet_edge(calls)
    assert edge is not None, calls
    assert edge["confidence"] == "EXTRACTED"


def test_a_java_class_answers_a_kotlin_receiver(tmp_path):
    # Kotlin and Java compile to one classpath, so a receiver typed to a Java class is
    # ordinary interop — the dominant shape in an Android codebase mid-migration.
    calls, _ = _calls(tmp_path, {
        "Greeter.java": "public class Greeter {\n    public void greet() {}\n}\n",
        "App.kt": "class App(private val greeter: Greeter) {\n"
                  "    fun run() { greeter.greet() }\n"
                  "}\n",
    })
    edge = _greet_edge(calls)
    assert edge is not None, calls
    assert edge["confidence"] == "INFERRED"


def test_a_class_from_an_unrelated_language_never_answers_a_kotlin_receiver(tmp_path):
    # The declaration index is corpus-wide, so a same-named PHP class would both answer
    # the receiver and hide that nothing on the classpath declares it.
    calls, result = _calls(tmp_path, {
        "Greeter.php": "<?php\nclass Greeter {\n    public function greet(): void {}\n}\n",
        "App.kt": "class App(private val greeter: Greeter) {\n"
                  "    fun run() { greeter.greet() }\n"
                  "}\n",
    })
    assert _greet_edge(calls) is None, calls
    parked = [(n.get("metadata") or {}).get("unresolved_calls") for n in result["nodes"]
              if "run" in str(n["label"]) and n.get("metadata")]
    assert parked == [[{"callee": "greet", "receiver_type": "Greeter",
                        "lang": "kotlin", "line": "L2"}]], parked


def test_the_first_binding_of_a_name_wins_over_a_later_sibling_branch(tmp_path):
    # The per-file table keys on the name alone, so two branches binding `svc` collide.
    # A tree walk that visits siblings in reverse hands the call to the branch it is not
    # written in — the type the reader sees one line above has to be the one that answers.
    calls, _ = _calls(tmp_path, {
        "Alpha.kt": "class Alpha {\n    fun doThing() {}\n}\n",
        "Beta.kt": "class Beta {\n    fun doThing() {}\n}\n",
        "App.kt": "class App {\n"
                  "    fun run(flag: Boolean) {\n"
                  "        if (flag) {\n"
                  "            val svc: Alpha = Alpha()\n"
                  "            svc.doThing()\n"
                  "        } else {\n"
                  "            val svc: Beta = Beta()\n"
                  "        }\n"
                  "    }\n"
                  "}\n",
    })
    hits = [e for (src, tgt), e in calls.items()
            if src and "run" in src and tgt == ".doThing()"]
    assert len(hits) == 1, calls
    assert "alpha" in hits[0]["target"].lower(), hits[0]["target"]


def test_a_property_outranks_a_plain_constructor_parameter_of_the_same_name(tmp_path):
    # A `class_parameter` without `val`/`var` is not a member: it is out of scope in every
    # method body, so wrapping it in a property of the same name is legal and common.
    calls, _ = _calls(tmp_path, {
        "Raw.kt": "class Raw {\n    fun doThing() {}\n}\n",
        "Wrapper.kt": "class Wrapper(raw: Raw) {\n    fun doThing() {}\n}\n",
        "App.kt": "class App(raw: Raw) {\n"
                  "    private val raw = Wrapper(raw)\n"
                  "    fun run() { raw.doThing() }\n"
                  "}\n",
    })
    hits = [e for (src, tgt), e in calls.items()
            if src and "run" in src and tgt == ".doThing()"]
    assert len(hits) == 1, calls
    assert "wrapper" in hits[0]["target"].lower(), hits[0]["target"]


def test_a_plain_constructor_parameter_still_types_an_initializer_receiver(tmp_path):
    # It stays in scope for property initializers and `init` blocks, so dropping plain
    # parameters outright would lose the calls written there.
    calls, _ = _calls(tmp_path, {
        "Greeter.kt": GREETER,
        "App.kt": "class App(greeter: Greeter) {\n"
                  "    private val name = greeter.greet()\n"
                  "}\n",
    })
    assert next((e for (src, tgt), e in calls.items() if tgt == ".greet()"), None) is not None, calls


def _parked(result: dict) -> list[dict]:
    return [entry for n in result["nodes"] if isinstance(n.get("metadata"), dict)
            for entry in n["metadata"].get("unresolved_calls", [])]


QUALIFIED_GREETER = "package com.example\n\nclass Greeter {\n    fun greet() {}\n}\n"


def test_a_qualified_property_annotation_names_the_type_in_its_last_segment(tmp_path):
    # A dotted spelling names the type in its last segment. Keyed on `com`, the receiver
    # matches no declaration and a package segment travels into the merged graph as a type.
    calls, result = _calls(tmp_path, {
        "Greeter.kt": QUALIFIED_GREETER,
        "App.kt": "class App {\n"
                  "    private val greeter: com.example.Greeter = com.example.Greeter()\n"
                  "    fun run() { greeter.greet() }\n"
                  "}\n",
    })
    assert _greet_edge(calls) is not None, calls
    assert _parked(result) == [], _parked(result)


def test_a_qualified_parameter_type_names_the_type_in_its_last_segment(tmp_path):
    calls, result = _calls(tmp_path, {
        "Greeter.kt": QUALIFIED_GREETER,
        "App.kt": "class App {\n"
                  "    fun run(greeter: com.example.Greeter) { greeter.greet() }\n"
                  "}\n",
    })
    assert _greet_edge(calls) is not None, calls
    assert _parked(result) == [], _parked(result)


def test_a_qualified_builtin_type_parks_no_package_segment(tmp_path):
    # The tail carries the builtin filter too: `kotlin.text.Regex` is unresolvable, and
    # parking `kotlin` as its type is worse than parking nothing.
    calls, result = _calls(tmp_path, {
        "Regex.kt": "class Regex {\n    fun greet() {}\n}\n",
        "App.kt": "class App {\n"
                  "    fun run(r: kotlin.text.Regex) { r.greet() }\n"
                  "}\n",
    })
    assert _greet_edge(calls) is None, calls
    assert _parked(result) == [], _parked(result)


def test_a_qualified_constructor_call_types_an_unannotated_local(tmp_path):
    # `val g = com.example.Greeter()` is the same qualified spelling with the type named
    # only in the initializer, so the constructor head has to be read to its last segment.
    calls, result = _calls(tmp_path, {
        "Greeter.kt": QUALIFIED_GREETER,
        "App.kt": "class App {\n"
                  "    fun run() {\n"
                  "        val greeter = com.example.Greeter()\n"
                  "        greeter.greet()\n"
                  "    }\n"
                  "}\n",
    })
    assert _greet_edge(calls) is not None, calls
    assert _parked(result) == [], _parked(result)


def test_a_qualified_method_call_does_not_type_a_local(tmp_path):
    # Only a capitalized last segment is constructor evidence: `repo.load()` binds nothing,
    # so a receiver typed off it would be a guess.
    calls, _ = _calls(tmp_path, {
        "Greeter.kt": GREETER,
        "App.kt": "class App {\n"
                  "    fun run(repo: Any) {\n"
                  "        val greeter = repo.load()\n"
                  "        greeter.greet()\n"
                  "    }\n"
                  "}\n",
    })
    assert _greet_edge(calls) is None, calls


def test_a_binding_in_scope_outranks_the_class_of_the_same_name(tmp_path):
    # A capitalized receiver is the type itself only when nothing of that name is bound:
    # a local shadowing a class name means the call goes through the local's type.
    calls, _ = _calls(tmp_path, {
        "Greeter.kt": GREETER,
        "Other.kt": "class Other {\n    fun greet() {}\n}\n",
        "App.kt": "class App {\n"
                  "    fun run() {\n"
                  "        val Greeter = Other()\n"
                  "        Greeter.greet()\n"
                  "    }\n"
                  "}\n",
    })
    edge = _greet_edge(calls)
    assert edge is not None, calls
    assert "other" in edge["target"].lower(), edge["target"]
