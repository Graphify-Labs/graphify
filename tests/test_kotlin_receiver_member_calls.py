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


def test_the_first_binding_of_a_name_wins(tmp_path):
    # The table is flat per file, so a parameter named like a property has to lose:
    # otherwise `other`'s signature would redirect the property's own calls.
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
    run_targets = {source_of[e["target"]] for e in result["edges"]
                   if e["relation"] == "calls"
                   and "run" in str(label_of.get(e["source"]))
                   and label_of.get(e["target"]) == ".greet()"}
    assert len(run_targets) == 1, run_targets
    assert run_targets.pop().endswith("Greeter.kt")


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
