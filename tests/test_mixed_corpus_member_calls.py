"""Mixed-corpus isolation for the member-call resolvers (#6, spec #1682).

A corpus that mixes PHP with another language must not let one language's raw
call data mint an edge through a different language's member-call resolver.
The extractor stamps ``lang`` on every cpp/csharp/java/php raw call (and objc
stamps its own), while Swift, Python and TypeScript raw calls carry no tag --
so those three resolvers skip any tagged raw call outright.

Every test goes through the public ``extract()`` seam, and the Python class
here doubles as the cross-language decoy: it owns an identically named method,
so a bare method-name match cannot tell it apart from the PHP target.
"""
from __future__ import annotations

from pathlib import Path

from graphify.extract import extract


def _calls(tmp_path: Path, files: dict[str, str]):
    """Extract ``files`` (name -> source) and return ({(src, tgt): edge}, result)."""
    paths = []
    for name, body in files.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
        paths.append(path)
    result = extract(paths, cache_root=tmp_path / "graphify-out")
    calls = {
        (edge["source"], edge["target"]): edge
        for edge in result["edges"]
        if edge.get("relation") == "calls"
    }
    return calls, result


def _nid(result: dict, label: str, file_suffix: str) -> str:
    return next(
        node["id"]
        for node in result["nodes"]
        if node.get("label") == label
        and str(node.get("source_file", "")).endswith(file_suffix)
    )


# A Python class whose method name collides with the PHP call's callee. Nothing
# in a PHP file may ever bind to it.
_PY_DECOY = (
    "class Lead:\n"
    "    def search(self, filters):\n"
    "        return []\n"
)


def test_php_capitalized_variable_receiver_yields_no_python_edge(tmp_path: Path):
    """A capitalized PHP *variable* receiver must not reach the Python resolver.

    `$Lead->search()` spells a receiver that, read as a Python receiver, would
    hit the Python resolver's capitalized-receiver class arm and bind to the
    Python `Lead.search`. The PHP raw call is tagged `lang: "php"`, so the
    Python resolver skips it.
    """
    calls, result = _calls(tmp_path, {
        "svc.py": _PY_DECOY,
        "app/Runner.php": (
            "<?php\n"
            "namespace App;\n"
            "class Runner {\n"
            "    public function go(): void {\n"
            "        $Lead = new Lead();\n"
            "        $Lead->search([]);\n"
            "    }\n"
            "}\n"
        ),
    })
    py_search = _nid(result, ".search()", "svc.py")
    # No edge from anywhere in the PHP file may land on the Python method.
    php_sourced = [
        (src, tgt) for (src, tgt) in calls
        if str(calls[(src, tgt)].get("source_file", "")).endswith(".php")
    ]
    assert not [pair for pair in php_sourced if pair[1] == py_search], (
        "a PHP raw call minted an edge into the Python decoy method"
    )


def test_python_member_calls_still_resolve_in_a_mixed_corpus(tmp_path: Path):
    """Positive control: the tag skip must not disable the Python resolver.

    Without this, the test above would pass even if the skip discarded every
    raw call. A genuine Python capitalized-receiver call still resolves, and a
    decoy class with the same method name gets no edge.
    """
    calls, result = _calls(tmp_path, {
        "svc.py": _PY_DECOY,
        "decoy.py": (
            "class Audit:\n"
            "    def search(self, filters):\n"
            "        return []\n"
        ),
        "caller.py": (
            "from svc import Lead\n"
            "\n"
            "def run():\n"
            "    Lead.search({})\n"
        ),
        "app/Runner.php": (
            "<?php\n"
            "namespace App;\n"
            "class Runner {\n"
            "    public function go(): void { $Lead = new Lead(); $Lead->search([]); }\n"
            "}\n"
        ),
    })
    run = _nid(result, "run()", "caller.py")
    py_search = _nid(result, ".search()", "svc.py")
    decoy_search = _nid(result, ".search()", "decoy.py")
    assert (run, py_search) in calls, "genuine Python member call stopped resolving"
    assert (run, decoy_search) not in calls, "decoy class received an edge"
