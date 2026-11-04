"""A call inside ``_main`` is credited to ``_main``, not to its public sibling (#4994).

``make_id`` strips the underscore edges off each part, so ``_main``/``main`` (and
any ``foo``/``_foo`` pair, e.g. ``invoke_scheduler``/``_invoke_scheduler``) mint
one plain id. The engine salts the pair apart like #3302 does, keeping the plain
id on the unique public name. The import-aware pass that turns a call on an
imported symbol into a ``calls`` edge rebuilt the caller id from the bare ``def``
name instead, so it always landed on ``main()`` — and every call inside
``_main`` produced a second, wrongly-sourced edge next to the correct one.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from graphify.extract import extract

TARGETS = """\
def alpha():
    return 1

def beta():
    return 2
"""

CLI = """\
from targets import alpha, beta

def _main():
    return beta()

def main():
    return alpha()
"""


def _extract(tmp_path, files: dict[str, str]):
    for name, body in files.items():
        p = tmp_path / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body)
    old = os.getcwd()
    try:
        os.chdir(tmp_path)
        paths = [Path(n).resolve() for n in files]
        return extract(paths, root=tmp_path.resolve(), cache_root=Path(tempfile.mkdtemp()))
    finally:
        os.chdir(old)


def _call_edges(result, labels):
    out = set()
    for e in result["edges"]:
        if e.get("relation") != "calls":
            continue
        source, target = labels.get(e["source"]), labels.get(e["target"])
        if source and target:
            out.add((source, target, e.get("source_location")))
    return out


def test_private_main_call_not_attributed_to_public_main(tmp_path):
    result = _extract(tmp_path, {"targets.py": TARGETS, "cli.py": CLI})
    labels = {n["id"]: n["label"] for n in result["nodes"]}
    calls = _call_edges(result, labels)

    assert ("_main()", "beta()", "L4") in calls
    assert ("main()", "alpha()", "L7") in calls
    assert ("main()", "beta()", "L4") not in calls


def test_both_declarations_survive_as_distinct_nodes(tmp_path):
    result = _extract(tmp_path, {"targets.py": TARGETS, "cli.py": CLI})
    ids = {n["label"]: n["id"] for n in result["nodes"] if n.get("source_file")}
    assert ids["_main()"] != ids["main()"]


def test_underscore_sibling_without_collision_is_unchanged(tmp_path):
    """No public sibling, so the private name keeps the plain id and its call."""
    result = _extract(
        tmp_path,
        {
            "targets.py": TARGETS,
            "cli.py": "from targets import beta\n\ndef _helper():\n    return beta()\n",
        },
    )
    labels = {n["id"]: n["label"] for n in result["nodes"]}
    calls = _call_edges(result, labels)
    assert ("_helper()", "beta()", "L4") in calls
    assert not any(source == "main()" for source, _, _ in calls)


def test_class_field_reference_stays_on_the_class_not_a_method(tmp_path):
    """The #4994 collision fix must not steal a class member's edge. A class whose
    method is followed by a type-annotated field shares the member-id prefix
    (`classid_methodname`) with the class, but that is a child node, not an
    underscore-collision salt - so the field's type reference must stay on the
    class, not move to the preceding method."""
    result = _extract(tmp_path, {
        "widget.ts": "export class Baz {}\n",
        "foo.ts": (
            "import { Baz } from './widget';\n"
            "export class Foo {\n"
            "  render(): number { return 1; }\n"
            "  item: Baz = new Baz();\n"
            "}\n"
        ),
    })
    labels = {n["id"]: n["label"] for n in result["nodes"]}
    refs = {(labels.get(e["source"]), labels.get(e["target"]))
            for e in result["edges"] if e.get("relation") == "references"}
    assert ("Foo", "Baz") in refs
    assert not any(src and src.endswith("render()") and tgt == "Baz" for src, tgt in refs)
