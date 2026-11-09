"""#5034: a constructor reached through a destructured require of a CommonJS
barrel must resolve to the class in the module the barrel re-exports.

`const { SourceCode } = require('./index')` where `index.js` does
`const SourceCode = require('./source'); module.exports = { SourceCode }`
used to leave the call's reference on the barrel, which defines nothing, so
the `calls` edge disappeared even though the direct-require case resolved.
"""
from __future__ import annotations

from pathlib import Path

from graphify.extract import extract


def test_constructor_call_resolves_through_destructured_barrel_require(tmp_path):
    files = {
        "source.js": "class SourceCode {}\nmodule.exports = SourceCode;\n",
        "index.js": (
            "const SourceCode = require('./source');\n"
            "module.exports = { SourceCode };\n"
        ),
        "consumer.js": (
            "const { SourceCode } = require('./index');\n"
            "function create() { return new SourceCode(); }\n"
        ),
    }
    for name, body in files.items():
        (tmp_path / name).write_text(body, encoding="utf-8")

    graph = extract(
        [tmp_path / name for name in files],
        cache_root=tmp_path / "cache",
        root=tmp_path,
        parallel=False,
    )
    nodes = {node["id"]: node for node in graph["nodes"]}
    calls = [
        (
            nodes[edge["source"]]["label"],
            nodes[edge["target"]]["label"],
            Path(nodes[edge["target"]]["source_file"]).name,
        )
        for edge in graph["edges"]
        if edge["relation"] == "calls"
        and edge["source"] in nodes
        and edge["target"] in nodes
    ]

    assert ("create()", "SourceCode", "source.js") in calls, calls
