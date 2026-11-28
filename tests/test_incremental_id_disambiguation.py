"""A changed-files rebuild must salt colliding ids the way a full build does.

`foo.h` and `foo.c` collapse to one `foo` file id, so disambiguation salts them apart (#1475).
When only `foo.c` changes, the rebuild re-extracts it alone and the collision with the unchanged
`foo.h` is invisible: `foo.c` keeps the bare id, and the graph no longer matches a full build.
"""
from __future__ import annotations

import json
from pathlib import Path

from graphify.watch import _rebuild_code


def _write(root: Path, rel: str, body: str) -> Path:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body, encoding="utf-8")
    return p


def _rebuild(root: Path, changed: list[Path] | None = None) -> None:
    assert _rebuild_code(root, changed_paths=changed, no_cluster=True, acquire_lock=False, force=True) is True


def _file_ids(root: Path) -> set[str]:
    graph = json.loads((root / "graphify-out" / "graph.json").read_text(encoding="utf-8"))
    return {n["id"] for n in graph["nodes"]
            if n.get("source_file") and Path(n["source_file"]).name == n.get("label")}


def test_changed_source_is_salted_against_its_unchanged_header(tmp_path):
    root = tmp_path / "proj"
    _write(root, "foo.h", "int foo(void);\n")
    _write(root, "foo.c", '#include "foo.h"\nint foo(void) { return 1; }\n')
    _write(root, "main.c", '#include "foo.h"\nint main(void) { return foo(); }\n')
    _rebuild(root)
    full = _file_ids(root)

    src = root / "foo.c"
    src.write_text(src.read_text(encoding="utf-8") + "/* edited */\n", encoding="utf-8")
    _rebuild(root, [src])

    assert _file_ids(root) == full
