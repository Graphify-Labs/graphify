"""Cross-file name resolution respects case in case-sensitive languages (#1581).

Case is semantic in most languages: `Path` (a class), `PATH` (an env var), and
`path` (a variable) are distinct. Cross-file resolution used to fold case for every
language, so `from pathlib import Path` (ubiquitous) resolved to a shell script's
`export PATH=...` node — turning one shell variable into the corpus's #1 god-node.

These tests pin: case-sensitive languages match by exact case (removing that false
edge), while genuinely case-insensitive languages (PHP) still fold.
"""
from __future__ import annotations

import os
from pathlib import Path

from graphify.extract import extract


def _extract(tmp_path, files: dict[str, str]):
    for name, body in files.items():
        (tmp_path / name).write_text(body)
    old = os.getcwd()
    try:
        os.chdir(tmp_path)
        r = extract([Path(n) for n in files], cache_root=tmp_path)
    finally:
        os.chdir(old)
    return r


def _labels(r):
    return {n["id"]: n["label"] for n in r["nodes"]}


def test_python_Path_does_not_resolve_to_shell_PATH(tmp_path):
    r = _extract(tmp_path, {
        "run.sh": "export PATH=/usr/local/bin:$PATH\n",
        "mod.py": (
            "from pathlib import Path\n"
            "def load(p: Path) -> Path:\n    return Path(p)\n"
            "def other():\n    return load(Path('x'))\n"
        ),
    })
    lbl = _labels(r)
    path_nid = next((n["id"] for n in r["nodes"] if n["label"] == "PATH"), None)
    assert path_nid is not None
    # No edge from the Python functions should land on the shell PATH node
    false_edges = [
        e for e in r["edges"]
        if e["target"] == path_nid and lbl.get(e["source"], "").startswith(("load", "other"))
    ]
    assert not false_edges, f"Python Path leaked onto shell PATH: {false_edges}"
    # PATH keeps only its own `defines` edge (from run.sh), not a false super-hub
    assert sum(1 for e in r["edges"] if e["target"] == path_nid) <= 1


def test_case_sensitive_cross_file_ref_respects_case(tmp_path):
    r = _extract(tmp_path, {
        "consts.rs": 'pub const PATH: &str = "/x";\n',
        "use.rs": "struct Wrap(Path);\n",   # `Path` — no such node in the corpus
    })
    lbl = _labels(r)
    path_nid = next((n["id"] for n in r["nodes"] if n["label"] == "PATH"), None)
    xref = [e for e in r["edges"] if e["target"] == path_nid and lbl.get(e["source"]) == "Wrap"]
    assert not xref, "a `Path` reference must not resolve to a case-differing `PATH`"


def test_exact_case_cross_file_still_resolves(tmp_path):
    r = _extract(tmp_path, {
        "h.py": "def helper():\n    return 1\n",
        "m.py": "from h import helper\ndef go():\n    return helper()\n",
    })
    lbl = _labels(r)
    calls = {(lbl.get(e["source"]), lbl.get(e["target"]))
             for e in r["edges"] if e["relation"] == "calls"}
    assert ("go()", "helper()") in calls


def test_php_case_insensitive_resolution_preserved(tmp_path):
    r = _extract(tmp_path, {
        "lib.php": "<?php\nfunction Greet() { return 1; }\n",
        "main.php": "<?php\nfunction run() { return greet(); }\n",
    })
    lbl = _labels(r)
    calls = {(lbl.get(e["source"]), lbl.get(e["target"]))
             for e in r["edges"] if e["relation"] == "calls"}
    assert ("run()", "Greet()") in calls, "PHP identifiers are case-insensitive; fold must still apply"
