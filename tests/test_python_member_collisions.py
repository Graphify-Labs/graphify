"""Python member calls must bind to the method the call spells.

`run` and `_run` are two methods of one class (#3302 gave them separate ids), but
`_resolve_python_member_calls` keys its method index through `_key`, which strips
`_` and folds case — so both methods landed on one entry and the later one won.
The module arm already resolves by the exact name (#4577); the method arms must
too, the same rule C# (#4415) and TypeScript (review on #4479) already apply.
"""
from __future__ import annotations

import warnings
from pathlib import Path

import pytest

from graphify.extract import extract


def _extract(tmp_path: Path, files: dict[str, str]) -> dict:
    for name, src in files.items():
        (tmp_path / name).write_text(src, encoding="utf-8")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return extract(
            [tmp_path / n for n in files],
            root=tmp_path,
            cache_root=tmp_path,
            parallel=False,
        )


def _calls(r: dict) -> set[tuple[str, str]]:
    label = {n["id"]: n["label"] for n in r["nodes"]}
    return {
        (label.get(e["source"]), label.get(e["target"]))
        for e in r["edges"]
        if e["relation"] == "calls"
    }


_WORKER = (
    "class Worker:\n"
    "    def run(self):\n"
    "        return 1\n"
    "\n"
    "    def _run(self):\n"
    "        return 2\n"
)


@pytest.mark.parametrize("call,caller,target", [
    ("Worker.run(None)", "viaclass()", ".run()"),
    ("Worker._run(None)", "viaclass()", "._run()"),
])
def test_class_qualified_call_hits_the_spelled_method(tmp_path, call, caller, target):
    r = _extract(tmp_path, {
        "worker.py": _WORKER,
        "main.py": f"from worker import Worker\n\n\ndef viaclass():\n    return {call}\n",
    })
    hits = {t for s, t in _calls(r) if s == caller and t and t.startswith(".")}
    assert hits == {target}, _calls(r)


@pytest.mark.parametrize("call,target", [("w.run()", ".run()"), ("w._run()", "._run()")])
def test_typed_receiver_call_hits_the_spelled_method(tmp_path, call, target):
    r = _extract(tmp_path, {
        "worker.py": _WORKER,
        "main.py": (
            "from worker import Worker\n\n\n"
            f"def typed(w: Worker):\n    return {call}\n"
        ),
    })
    hits = {t for s, t in _calls(r) if s == "typed()" and t and t.startswith(".")}
    assert hits == {target}, _calls(r)


@pytest.mark.parametrize("call,target", [("self.run()", ".run()"), ("self._run()", "._run()")])
def test_inherited_self_call_hits_the_spelled_method(tmp_path, call, target):
    r = _extract(tmp_path, {
        "base.py": _WORKER.replace("Worker", "Base"),
        "child.py": (
            "from base import Base\n\n\n"
            f"class Child(Base):\n    def start(self):\n        return {call}\n"
        ),
    })
    hits = {t for s, t in _calls(r) if s == ".start()" and t and t.startswith(".")}
    assert hits == {target}, _calls(r)


def test_call_matching_no_method_exactly_is_not_guessed(tmp_path):
    # `Run` is neither `run` nor `_run`, and the folded key fits both, so picking
    # one would be a guess (it was whichever `method` edge registered last).
    r = _extract(tmp_path, {
        "worker.py": _WORKER,
        "main.py": "from worker import Worker\n\n\ndef viaclass():\n    return Worker.Run(None)\n",
    })
    assert not [t for s, t in _calls(r) if s == "viaclass()" and t and t.startswith(".")], _calls(r)


def test_uncolliding_method_still_resolves(tmp_path):
    # Control: with no collision the loose key is the only lookup that can fire
    # for a class-qualified call, and it must keep firing.
    r = _extract(tmp_path, {
        "worker.py": "class Worker:\n    def run(self):\n        return 1\n",
        "main.py": "from worker import Worker\n\n\ndef viaclass():\n    return Worker.run(None)\n",
    })
    assert ("viaclass()", ".run()") in _calls(r)
