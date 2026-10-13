"""Step 3 Part A passes root= to extract(), so the cache location never anchors ids (#3727).

``extract(paths, cache_root=...)`` uses ``cache_root`` as the fallback anchor for
``source_file`` and node ids when ``root`` is not given (#1941). Part A called it
with ``cache_root`` alone. That is harmless while the cache sits in the scan root,
but the two parameters look alike, and anyone adapting the block to a cache that
lives elsewhere re-anchored every code node: same node count, every id renamed,
and every cached edge into code left dangling. A node-count guard cannot see it.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

# tests/ -> repo root is one parent up; put it on the path so tools.skillgen
# imports regardless of pytest's import mode.
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from graphify.extract import extract  # noqa: E402
from tools.skillgen import gen  # noqa: E402

_CALL = "extract(code_files, cache_root="


def _split_hosts() -> list[gen.Platform]:
    return [p for p in gen.load_platforms().values() if p.bucket != "monolith"]


def _part_a_calls(platform: gen.Platform) -> list[str]:
    body = gen.render(platform)[0].content
    return [line.strip() for line in body.splitlines() if _CALL in line]


def test_split_hosts_are_discovered():
    """The parametrized guard below must not pass vacuously on an empty list."""
    assert len(_split_hosts()) >= 10, [p.key for p in _split_hosts()]


@pytest.mark.parametrize("platform", _split_hosts(), ids=lambda p: p.key)
def test_part_a_passes_an_explicit_root(platform: gen.Platform):
    calls = _part_a_calls(platform)
    assert calls, f"[{platform.key}] Part A extract() call not found"
    for call in calls:
        assert "root=Path('INPUT_PATH')" in call.replace("cache_root=Path('INPUT_PATH')", ""), (
            f"[{platform.key}] Part A calls extract() with cache_root but no root= (#3727): {call!r}"
        )


def test_relocating_only_the_cache_does_not_rename_part_a_nodes(tmp_path: Path):
    """Run the shipped call twice, moving nothing but the cache: ids must not change."""
    scan_root = tmp_path / "proj"
    (scan_root / "pkg").mkdir(parents=True)
    module = scan_root / "pkg" / "mod.py"
    module.write_text("def hello():\n    return 1\n", encoding="utf-8")
    elsewhere = tmp_path / "cache-elsewhere"
    elsewhere.mkdir()

    (call,) = _part_a_calls(gen.load_platforms()["claude"])
    expression = call.removeprefix("result = ")
    in_place = expression.replace("Path('INPUT_PATH')", f"Path({str(scan_root)!r})")
    relocated = expression.replace(
        "cache_root=Path('INPUT_PATH')", f"cache_root=Path({str(elsewhere)!r})"
    ).replace("Path('INPUT_PATH')", f"Path({str(scan_root)!r})")
    assert in_place != relocated

    scope = {"extract": extract, "Path": Path, "code_files": [module]}
    ids_in_place = sorted(n["id"] for n in eval(in_place, dict(scope))["nodes"])
    ids_relocated = sorted(n["id"] for n in eval(relocated, dict(scope))["nodes"])

    assert ids_in_place, "expected AST nodes for the module"
    assert ids_relocated == ids_in_place, (
        "moving only the cache renamed the code nodes: "
        f"{ids_in_place} -> {ids_relocated}"
    )
