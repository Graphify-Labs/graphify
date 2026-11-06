"""C# `foreach` loop variables type their member calls.

`foreach (var a in agents.Values) a.look.Animate();` produced no calls edge when
`Agent` and `Look` lived in another file: the loop variable had no binding, so
the receiver chain could not start. A loop variable is now bound inside its
loop, to its explicit type, or for `var` to the element type of the class field
or property it iterates (`f`, `this.f`, `f.Values`, `f.Keys`). Iterating a
dictionary itself yields pairs and stays untyped, and so does a loop over a name
a local or parameter shadows — no edge beats a guessed one.
"""
from __future__ import annotations

import os
from pathlib import Path

from graphify.extract import extract


def _calls(tmp_path, files: dict[str, str]):
    for name, body in files.items():
        (tmp_path / name).write_text(body)
    old = os.getcwd()
    try:
        os.chdir(tmp_path)
        r = extract([Path(n) for n in files], cache_root=tmp_path / ".cache")
    finally:
        os.chdir(old)
    calls = {(e["source"], e["target"]) for e in r["edges"] if e["relation"] == "calls"}
    return calls, r


def _find(r, label, id_contains):
    return next(n["id"] for n in r["nodes"]
                if n["label"] == label and id_contains in n["id"])


_MODEL = (
    "namespace Demo\n{\n"
    "    public class Look { public void Animate() { } }\n"
    "    public class Agent { public Look look; public void Step() { } }\n"
    "    public class Decoy { public void Step() { } public void Animate() { } }\n"
    "}\n"
)


def _crowd(methods: str) -> str:
    return (
        "using System.Collections.Generic;\nnamespace Demo\n{\n"
        "    public class Crowd\n    {\n"
        "        readonly Dictionary<string, Agent> agents = new Dictionary<string, Agent>();\n"
        "        readonly Dictionary<Agent, int> scores = new Dictionary<Agent, int>();\n"
        "        readonly List<Agent> list = new List<Agent>();\n"
        "        Agent[] array;\n"
        "        public IEnumerable<Agent> All { get; set; }\n"
        f"        {methods}\n"
        "    }\n}\n"
    )


def _edge(r, calls, caller, label, owner):
    return (_find(r, caller, "crowd"), _find(r, label, owner)) in calls


def test_var_over_dictionary_values_types_the_chain(tmp_path):
    calls, r = _calls(tmp_path, {"Model.cs": _MODEL, "Crowd.cs": _crowd(
        "public void Tick() { foreach (var a in agents.Values) a.look.Animate(); }"
    )})
    assert _edge(r, calls, ".Tick()", ".Animate()", "look")
    assert not _edge(r, calls, ".Tick()", ".Animate()", "decoy")


def test_var_over_dictionary_keys_takes_the_key_type(tmp_path):
    calls, r = _calls(tmp_path, {"Model.cs": _MODEL, "Crowd.cs": _crowd(
        "public void Tick() { foreach (var a in scores.Keys) a.Step(); }"
    )})
    assert _edge(r, calls, ".Tick()", ".Step()", "agent")


def test_var_over_sequences_takes_the_element_type(tmp_path):
    calls, r = _calls(tmp_path, {"Model.cs": _MODEL, "Crowd.cs": _crowd(
        "public void Listed() { foreach (var a in list) a.Step(); }\n"
        "        public void Arrayed() { foreach (var a in array) a.Step(); }\n"
        "        public void Property() { foreach (var a in All) a.Step(); }\n"
        "        public void ThisField() { foreach (var a in this.list) a.Step(); }"
    )})
    for caller in (".Listed()", ".Arrayed()", ".Property()", ".ThisField()"):
        assert _edge(r, calls, caller, ".Step()", "agent"), caller
        assert not _edge(r, calls, caller, ".Step()", "decoy"), caller


def test_explicitly_typed_loop_variable_binds_its_type(tmp_path):
    calls, r = _calls(tmp_path, {"Model.cs": _MODEL, "Crowd.cs": _crowd(
        "public void Tick(IEnumerable<object> xs) { foreach (Agent a in xs) a.Step(); }"
    )})
    assert _edge(r, calls, ".Tick()", ".Step()", "agent")


def test_iterating_a_dictionary_itself_stays_untyped(tmp_path):
    calls, r = _calls(tmp_path, {"Model.cs": _MODEL, "Crowd.cs": _crowd(
        "public void Tick() { foreach (var kv in agents) kv.Step(); }"
    )})
    tick = _find(r, ".Tick()", "crowd")
    assert not {t for s, t in calls if s == tick}


def test_a_local_shadowing_the_field_leaves_the_loop_untyped(tmp_path):
    calls, r = _calls(tmp_path, {"Model.cs": _MODEL, "Crowd.cs": _crowd(
        "public void Tick() { var list = new List<Decoy>(); foreach (var a in list) a.Step(); }"
    )})
    assert not _edge(r, calls, ".Tick()", ".Step()", "agent")


def test_the_loop_variable_does_not_leak_past_its_loop(tmp_path):
    calls, r = _calls(tmp_path, {"Model.cs": _MODEL, "Crowd.cs": _crowd(
        "public void Tick(Decoy a) { foreach (var b in list) { } a.Step(); }"
    )})
    assert _edge(r, calls, ".Tick()", ".Step()", "decoy")
    assert not _edge(r, calls, ".Tick()", ".Step()", "agent")
