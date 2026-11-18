"""#4598: a JS/TS member call must not fall back to a same-file bare-name match.

`receiver.name(...)` used to resolve to a function called `name` declared
anywhere in the same file, ignoring the receiver entirely. Inside a
delegating wrapper this fabricated an EXTRACTED `calls` self-loop; more
generally it could bind to any unrelated same-named function in the file.
"""
from __future__ import annotations

import warnings
from pathlib import Path

from graphify.extract import extract


def _extract(tmp_path: Path, files: dict[str, str]) -> dict:
    for name, src in files.items():
        (tmp_path / name).write_text(src, encoding="utf-8")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return extract([tmp_path / n for n in files], cache_root=tmp_path, parallel=False)


def _calls(r: dict) -> set[tuple[str, str]]:
    label = {n["id"]: n["label"] for n in r["nodes"]}
    return {
        (label.get(e["source"]), label.get(e["target"]))
        for e in r["edges"] if e["relation"] == "calls"
    }


def test_delegating_wrapper_does_not_self_loop(tmp_path):
    r = _extract(tmp_path, {
        "app.js": (
            'import { createHistory } from "./history.js";\n'
            "const history = createHistory();\n\n"
            "export function appendFrame(entry) {\n"
            "  return history.appendFrame(entry);\n"
            "}\n\n"
            "export function confirm(message) {\n"
            "  return window.confirm(message);\n"
            "}\n"
        ),
        "history.js": (
            "export function createHistory() {\n"
            "  return { appendFrame: (e) => e };\n"
            "}\n"
        ),
    })
    calls = _calls(r)
    assert ("appendFrame()", "appendFrame()") not in calls
    assert ("confirm()", "confirm()") not in calls
    assert not [t for s, t in calls if s == t], calls


def test_receiver_call_does_not_bind_to_an_unrelated_sibling(tmp_path):
    # `addFrame` delegates to `history.appendFrame()`; a totally unrelated
    # `appendFrame` function also lives in the file. The bare-name map used
    # to bind the call to that sibling instead of leaving it unresolved.
    r = _extract(tmp_path, {"app.js": (
        "function appendFrame(entry) { return entry; }\n\n"
        "function addFrame(history, entry) {\n"
        "  return history.appendFrame(entry);\n"
        "}\n"
    )})
    calls = _calls(r)
    assert ("addFrame()", "appendFrame()") not in calls


def test_bare_unqualified_call_is_unaffected(tmp_path):
    # No receiver at all: resolving by name is correct and must keep working.
    r = _extract(tmp_path, {"app.js": (
        "function helper(x) { return x; }\n"
        "function run(x) { return helper(x); }\n"
    )})
    assert ("run()", "helper()") in _calls(r)


def test_this_method_call_is_unaffected(tmp_path):
    # `this.m()` is self_receiver, resolved through the caller's own class,
    # not the deferred member-call path this issue is about.
    r = _extract(tmp_path, {"app.js": (
        "class Wrapper {\n"
        "  run(entry) { return this.appendFrame(entry); }\n"
        "  appendFrame(entry) { return entry; }\n"
        "}\n"
    )})
    assert (".run()", ".appendFrame()") in _calls(r)


def test_ts_typed_receiver_still_resolves_through_its_own_type(tmp_path):
    r = _extract(tmp_path, {
        "greeter.ts": "export class Greeter {\n  greet(): void {}\n}\n",
        "app.ts": (
            'import { Greeter } from "./greeter";\n'
            "export function run(g: Greeter) {\n  g.greet();\n}\n"
        ),
    })
    assert ("run()", ".greet()") in _calls(r)


def test_factory_object_sibling_call_is_unaffected(tmp_path):
    # #1322/#3408's own pattern: methods assigned onto a local factory object
    # calling each other through that same object must keep resolving --
    # this is a genuine, already-scoped sibling call, not a guess.
    r = _extract(tmp_path, {"store.js": (
        "function makeStore() {\n"
        "  const store = {};\n"
        "  store.get = (k) => k;\n"
        "  store.set = (k, v) => store.get(k);\n"
        "  return store;\n"
        "}\n"
    )})
    assert (".set()", ".get()") in _calls(r)
