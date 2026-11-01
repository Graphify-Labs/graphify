"""A plain PHP function call can only resolve to a function, never to a class method.

`dispatch(new X)` is a global helper supplied by a framework. With no `dispatch` function in
the corpus, the cross-file call pass bound it by bare name to any in-corpus static method
called `dispatch` (a bus-like class, a job base class) as an INFERRED `calls` edge. A method
needs a receiver (`$this->`, `Foo::`), which the extractor marks as a member call and
resolves elsewhere.
"""
from __future__ import annotations

import tempfile
from pathlib import Path

from graphify.extract import extract

BUS = (
    "<?php\nnamespace App;\nclass Bus {\n"
    "    public static function dispatch($job) { return $job; }\n}\n"
)


def _calls(tmp_path: Path, files: dict[str, str]) -> set[tuple[str, str]]:
    for name, body in files.items():
        p = tmp_path / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")
    r = extract([tmp_path / n for n in files], cache_root=Path(tempfile.mkdtemp()),
                root=tmp_path, parallel=False)
    labels = {n["id"]: n["label"] for n in r["nodes"]}
    return {
        (labels[e["source"]], labels[e["target"]])
        for e in r["edges"] if e["relation"] == "calls"
    }


def test_global_helper_call_does_not_bind_to_a_same_named_static_method(tmp_path):
    calls = _calls(tmp_path, {
        "Bus.php": BUS,
        "Ctl.php": "<?php\nnamespace App;\nclass Ctl {\n"
                   "    public function store() { return dispatch(new Job()); }\n}\n",
    })
    assert (".store()", ".dispatch()") not in calls


def test_a_real_global_function_is_still_resolved(tmp_path):
    calls = _calls(tmp_path, {
        "Bus.php": BUS,
        "helpers.php": "<?php\nfunction dispatch($job) { return $job; }\n",
        "Ctl.php": "<?php\nnamespace App;\nclass Ctl {\n"
                   "    public function store() { return dispatch(new Job()); }\n}\n",
    })
    assert (".store()", "dispatch()") in calls
    assert (".store()", ".dispatch()") not in calls


def test_receiver_calls_to_the_method_still_resolve(tmp_path):
    calls = _calls(tmp_path, {
        "Bus.php": BUS,
        "Ctl.php": "<?php\nnamespace App;\nclass Ctl {\n"
                   "    public function store() { return Bus::dispatch(new Job()); }\n"
                   "    public function again() { return $this->dispatch(new Job()); }\n"
                   "    public function dispatch($j) { return $j; }\n}\n",
    })
    assert (".store()", ".dispatch()") in calls
    assert (".again()", ".dispatch()") in calls


def test_method_and_enum_case_both_named_like_the_helper_leave_the_call_unbound(tmp_path):
    # PHP function names fold case. With methods out of the index, an enum case is
    # the only remaining same-named definition; it must not become the target.
    calls = _calls(tmp_path, {
        "Bus.php": BUS,
        "Kind.php": "<?php\nnamespace App;\nenum Kind {\n    case DISPATCH;\n}\n",
        "Ctl.php": "<?php\nnamespace App;\nclass Ctl {\n"
                   "    public function store() { return dispatch(new Job()); }\n}\n",
    })
    assert not [c for c in calls if c[0] == ".store()" and c[1] in (".dispatch()", "DISPATCH")]
