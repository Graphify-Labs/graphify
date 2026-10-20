"""C# method overloads get their own nodes, calls, and callers (#4584).

A method name declared twice on one type, with different parameters, used
to mint ONE node at the first declaration's location. Every caller of any
overload got a `calls` edge to that single node, the second overload's own
outgoing calls were credited to the first overload's node, and the second
overload's location was lost outright.
"""
from __future__ import annotations

import os
import tempfile
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
        r = extract([Path(n) for n in files], cache_root=Path(tempfile.mkdtemp()))
    finally:
        os.chdir(old)
    return r


def _edges(r, relation):
    return {(e["source"], e["target"]) for e in r["edges"] if e["relation"] == relation}


def _nodes(r, label):
    return [n for n in r["nodes"] if n["label"] == label]


def _by_line(n: dict) -> int:
    return int(n["source_location"].lstrip("L"))


_MESSAGES = {
    "Messages.cs": (
        "namespace Demo\n"
        "{\n"
        "    public static class Messages\n"
        "    {\n"
        "        public static string Banner(int code)\n"
        "        {\n"
        "            return Format(code);\n"
        "        }\n"
        "\n"
        "        public static string Banner(int code, string format)\n"
        "        {\n"
        "            return Pad(format);\n"
        "        }\n"
        "\n"
        "        private static string Format(int code) { return code.ToString(); }\n"
        "        private static string Pad(string text) { return text; }\n"
        "    }\n"
        "}\n"
    ),
    "Caller.cs": (
        "namespace Demo\n"
        "{\n"
        "    public class Caller\n"
        "    {\n"
        "        public string OneArg() { return Messages.Banner(1); }\n"
        "        public string TwoArgs() { return Messages.Banner(1, \"x\"); }\n"
        "    }\n"
        "}\n"
    ),
}


def test_each_overload_gets_its_own_node_with_its_own_location(tmp_path):
    r = _extract(tmp_path, _MESSAGES)
    banners = _nodes(r, ".Banner()")
    assert len(banners) == 2
    locations = {n["source_location"] for n in banners}
    assert locations == {"L5", "L10"}


def test_each_overload_keeps_its_own_outgoing_calls(tmp_path):
    r = _extract(tmp_path, _MESSAGES)
    one_arg, two_args = sorted(_nodes(r, ".Banner()"), key=_by_line)
    pad = next(n for n in r["nodes"] if n["label"] == ".Pad()")
    fmt = next(n for n in r["nodes"] if n["label"] == ".Format()")
    calls = _edges(r, "calls")
    assert (one_arg["id"], fmt["id"]) in calls
    assert (two_args["id"], pad["id"]) in calls
    # Neither overload's calls leak onto the other.
    assert (one_arg["id"], pad["id"]) not in calls
    assert (two_args["id"], fmt["id"]) not in calls


def test_callers_bind_to_the_overload_their_own_arity_matches(tmp_path):
    r = _extract(tmp_path, _MESSAGES)
    one_arg_banner, two_args_banner = sorted(
        _nodes(r, ".Banner()"), key=_by_line
    )
    one_arg_caller = next(n for n in r["nodes"] if n["label"] == ".OneArg()")
    two_args_caller = next(n for n in r["nodes"] if n["label"] == ".TwoArgs()")
    calls = _edges(r, "calls")
    assert (one_arg_caller["id"], one_arg_banner["id"]) in calls
    assert (two_args_caller["id"], two_args_banner["id"]) in calls
    # Neither caller binds to the wrong-arity overload.
    assert (one_arg_caller["id"], two_args_banner["id"]) not in calls
    assert (two_args_caller["id"], one_arg_banner["id"]) not in calls


def test_a_name_declared_once_is_unaffected(tmp_path):
    """Keep-the-bar: a type with no overloads at all mints exactly the same
    id it always has -- the fix is purely additive for overload sets."""
    r = _extract(tmp_path, {
        "Plain.cs": (
            "namespace Demo { public class Plain {\n"
            "    public void Run() { Helper(); }\n"
            "    private void Helper() { }\n"
            "} }\n"
        ),
    })
    run_nodes = _nodes(r, ".Run()")
    assert len(run_nodes) == 1
    assert run_nodes[0]["id"] == "plain_demo_plain_run"


def test_same_arity_different_types_resolves_to_neither(tmp_path):
    """Two overloads with the SAME argument count but different parameter
    types cannot be told apart by arity alone -- this extractor does not
    infer argument expression types, so a call naming them stays unresolved
    rather than guessing which one it meant."""
    r = _extract(tmp_path, {
        "Ambiguous.cs": (
            "namespace Demo\n"
            "{\n"
            "    public static class Over\n"
            "    {\n"
            "        public static void Pick(int x) { }\n"
            "        public static void Pick(string x) { }\n"
            "    }\n"
            "    public class User\n"
            "    {\n"
            "        public void Use() { Over.Pick(1); }\n"
            "    }\n"
            "}\n"
        ),
    })
    pick_nodes = _nodes(r, ".Pick()")
    assert len(pick_nodes) == 2
    use_node = next(n for n in r["nodes"] if n["label"] == ".Use()")
    calls = _edges(r, "calls")
    assert not any(src == use_node["id"] and tgt in {n["id"] for n in pick_nodes}
                   for src, tgt in calls)
