"""A CommonJS `const X = require('./m')` binding must not create a local node.

The binding is an import, not a module-scope data binding. A node for it in
the importing file shadowed the class the required file exports, so `new X()`
bound to the local node and the required class got no incoming edge (#4621).
"""
from __future__ import annotations

from pathlib import Path

from graphify.extract import _make_id, extract


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_require_binding_does_not_shadow_the_required_class(tmp_path: Path):
    logger = _write(
        tmp_path / "src/logger.js",
        "function Logger(p) { this.p = p }\n"
        "Logger.prototype.warn = function warn() {}\n"
        "module.exports = Logger\n",
    )
    use = _write(
        tmp_path / "src/use.js",
        "const Logger = require('./logger')\n"
        "function Watcher() { return new Logger('w') }\n"
        "module.exports = Watcher\n",
    )

    result = extract([logger, use], cache_root=tmp_path)

    node_ids = {node["id"] for node in result["nodes"]}
    assert _make_id("src/use", "Logger") not in node_ids, (
        "the require binding must not create a node in the importing file"
    )

    calls = {
        (edge["source"], edge["target"])
        for edge in result["edges"]
        if edge["relation"] == "calls"
    }
    assert (_make_id("src/use", "Watcher"), _make_id("src/logger", "Logger")) in calls, (
        "the call must land on the class the required file exports"
    )
