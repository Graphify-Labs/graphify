"""A use through a CommonJS require of an external package must stay visible
instead of silently losing its edge (#4688).

#4621/#4634 stopped minting a local node for a `const X = require('./m')`
binding so it no longer shadowed the class the required file exports, which
fixed `new X()` for a resolvable local require. But the same guard also
suppressed the node for a require of an EXTERNAL package (`require('some-
plugin')`), where there is no required class to redirect to -- the binding
node was the only thing a caller could ever point at, and suppressing it
there just dropped the use entirely, a real regression from 0.9.93 (where it
pointed at the, admittedly wrong, binding node) to 0.9.94 (no edge at all).
The issue's own "Expected" section asks for the use to stay visible in this
case specifically: "an edge to the binding, or to an external-package node,
instead of no edge."
"""
from __future__ import annotations

from pathlib import Path

from graphify.extract import _make_id, extract


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_new_through_an_external_package_require_stays_visible(tmp_path: Path):
    ext = _write(
        tmp_path / "ext.js",
        "const Plugin = require('some-plugin');\nfunction cfg() { return new Plugin(); }\n",
    )

    result = extract([ext], cache_root=tmp_path)

    node_ids = {node["id"] for node in result["nodes"]}
    assert _make_id("ext", "Plugin") in node_ids, (
        "an external package's require has no file to redirect to, "
        "so the binding node must stay instead of vanishing entirely"
    )
    calls = {
        (edge["source"], edge["target"])
        for edge in result["edges"]
        if edge["relation"] == "calls"
    }
    assert (_make_id("ext", "cfg"), _make_id("ext", "Plugin")) in calls, (
        "the use must stay visible on the binding node, not disappear"
    )


def test_a_resolvable_require_still_suppresses_its_binding_node(tmp_path: Path):
    """The #4621/#4634 fix for a LOCAL, resolvable require must be unaffected:
    only an unresolvable (external) specifier keeps its binding node."""
    logger = _write(
        tmp_path / "logger.js",
        "function Logger(p) { this.p = p }\nmodule.exports = Logger\n",
    )
    use = _write(
        tmp_path / "use.js",
        "const Logger = require('./logger')\nfunction Watcher() { return new Logger('w') }\n",
    )

    result = extract([logger, use], cache_root=tmp_path)

    node_ids = {node["id"] for node in result["nodes"]}
    assert _make_id("use", "Logger") not in node_ids, (
        "a resolvable require binding must still not create a local node"
    )
