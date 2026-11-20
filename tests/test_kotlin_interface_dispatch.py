"""Kotlin member calls on a typed receiver, and interface dispatch.

`g.greet()` on a `g: Greeter` names `Greeter.greet`. The in-file bare-name
lookup used to pick whichever `greet` the file declared last, so the call
landed on one implementer and the others were unreachable. The receiver's
declared type now picks the method, and `kotlin_interface_dispatch` links the
interface method to every implementer.
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

from graphify.extract import extract


def _extract(tmp_path, files: dict[str, str]):
    for name, body in files.items():
        (tmp_path / name).write_text(body)
    old = os.getcwd()
    try:
        os.chdir(tmp_path)
        return extract([Path(n) for n in files], cache_root=Path(tempfile.mkdtemp()))
    finally:
        os.chdir(old)


def _pairs(r, relation):
    label = {n["id"]: (n["label"], n["source_file"], n["source_location"]) for n in r["nodes"]}
    return {(label[e["source"]], label[e["target"]]) for e in r["edges"]
            if e["relation"] == relation and e["source"] in label and e["target"] in label}


_GREETERS = (
    "interface Greeter {\n    fun greet()\n}\n"
    "class Hello : Greeter {\n    override fun greet() {}\n}\n"
    "class Hi : Greeter {\n    override fun greet() {}\n}\n"
)


@pytest.mark.parametrize("use", [
    "class Use {\n    fun use(g: Greeter) {\n        g.greet()\n    }\n}\n",
    "class Use(private val g: Greeter) {\n    fun use() {\n        g.greet()\n    }\n}\n",
    "class Use {\n    private val g: Greeter? = null\n    fun use() {\n        this.g?.greet()\n    }\n}\n",
    "class Use {\n    fun use() {\n        val g: Greeter = Hello()\n        g.greet()\n    }\n}\n",
])
def test_call_through_an_interface_typed_receiver_lands_on_the_interface(tmp_path, use):
    r = _extract(tmp_path, {"a.kt": _GREETERS + use})
    calls = {(src[0], tgt) for src, tgt in _pairs(r, "calls") if tgt[0] == ".greet()"}
    assert calls == {(".use()", (".greet()", "a.kt", "L2"))}
    dispatch = {tgt[2] for src, tgt in _pairs(r, "dispatches_to") if src[2] == "L2"}
    assert dispatch == {"L5", "L8"}


def test_a_receiver_typed_in_another_file_resolves_across_files(tmp_path):
    r = _extract(tmp_path, {
        "Greeter.kt": "interface Greeter {\n    fun greet()\n}\n",
        "Hello.kt": "class Hello : Greeter {\n    override fun greet() {}\n}\n",
        "Hi.kt": "class Hi : Greeter {\n    override fun greet() {}\n}\n",
        "Use.kt": "class Use {\n    fun use(g: Greeter) {\n        g.greet()\n    }\n}\n",
    })
    assert {tgt[1] for src, tgt in _pairs(r, "calls") if src[0] == ".use()"} == {"Greeter.kt"}
    assert {tgt[1] for _, tgt in _pairs(r, "dispatches_to")} == {"Hello.kt", "Hi.kt"}


def test_a_local_constructed_value_types_its_receiver(tmp_path):
    r = _extract(tmp_path, {"a.kt": _GREETERS + (
        "class Use {\n    fun use() {\n        val g = Hi()\n        g.greet()\n    }\n}\n"
    )})
    assert {tgt[2] for src, tgt in _pairs(r, "calls") if src[0] == ".use()" and tgt[0] == ".greet()"} == {"L8"}


def test_an_untyped_receiver_does_not_guess_between_same_named_methods(tmp_path):
    r = _extract(tmp_path, {"a.kt": _GREETERS + (
        "class Use {\n    fun use(xs: List<Greeter>) {\n        xs.forEach { it.greet() }\n    }\n}\n"
    )})
    assert not {tgt for src, tgt in _pairs(r, "calls") if tgt[0] == ".greet()"}


def test_an_untyped_receiver_still_binds_a_name_declared_once(tmp_path):
    r = _extract(tmp_path, {"a.kt": (
        "class Box {\n    fun unpack() {}\n}\n"
        "fun use(make: () -> Box) {\n    val b = make()\n    b.unpack()\n}\n"
    )})
    assert ("use()", (".unpack()", "a.kt", "L2")) in {(s[0], t) for s, t in _pairs(r, "calls")}


def test_a_shadowing_local_hides_the_property_type(tmp_path):
    r = _extract(tmp_path, {"a.kt": _GREETERS + (
        "class Use(private val g: Greeter) {\n"
        "    fun use() {\n        val g = Hi()\n        g.greet()\n    }\n}\n"
    )})
    assert {tgt[2] for src, tgt in _pairs(r, "calls") if src[0] == ".use()" and tgt[0] == ".greet()"} == {"L8"}
