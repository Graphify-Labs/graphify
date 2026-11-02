"""Step 3 Part A anchors node ids on the SCAN root, not the cache location (#3727).

``extract(paths, cache_root=...)`` uses ``cache_root`` as the fallback anchor for
``source_file`` and node ids when ``root`` is not given (#1941). Part A used to
call it with ``cache_root`` alone. That is harmless while the cache sits in the
scan root, but the two parameters look alike, and anyone adapting the block to a
cache that lives elsewhere re-anchored every code node: same node count, every id
renamed, and every cached edge into code left dangling. A node-count guard cannot
see it.

With #197 the split hosts no longer carry the inline block: Part A is
``graphify pipeline extract-ast``, whose body is
``graphify.pipeline.step_extract_ast``. The guard below checks the renders call
the step, and proves the step itself anchors on the scan root by running it twice
with the cache in two different places.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

# tests/ -> repo root is one parent up; put it on the path so tools.skillgen
# imports regardless of pytest's import mode.
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from graphify.pipeline import step_extract_ast  # noqa: E402
from tools.skillgen import gen  # noqa: E402

# The inline call the split hosts used to carry; must be gone from their renders.
_INLINE_CALL = "extract(code_files, cache_root="
_PIPELINE_CALL = "graphify pipeline extract-ast"


def _split_hosts() -> list[gen.Platform]:
    return [p for p in gen.load_platforms().values() if p.bucket != "monolith"]


def test_split_hosts_are_discovered():
    """The parametrized guard below must not pass vacuously on an empty list."""
    assert len(_split_hosts()) >= 10, [p.key for p in _split_hosts()]


@pytest.mark.parametrize("platform", _split_hosts(), ids=lambda p: p.key)
def test_part_a_uses_the_pipeline_step(platform: gen.Platform):
    body = gen.render(platform)[0].content
    assert _PIPELINE_CALL in body, (
        f"[{platform.key}] Part A must call `{_PIPELINE_CALL}`"
    )
    assert _INLINE_CALL not in body, (
        f"[{platform.key}] Part A must not inline extract(); "
        "the step lives in graphify.pipeline.step_extract_ast (#197)"
    )


def _write_detect(out_dir: Path, code_file: Path) -> None:
    """Lay out a minimal detect sidecar so step_extract_ast has its input."""
    graphify_out = out_dir / "graphify-out"
    graphify_out.mkdir(parents=True, exist_ok=True)
    (graphify_out / ".graphify_detect.json").write_text(
        json.dumps({"files": {"code": [str(code_file)]}, "total_files": 1}),
        encoding="utf-8",
    )


def test_relocating_only_the_cache_does_not_rename_part_a_nodes(tmp_path: Path):
    """Run step_extract_ast twice, moving nothing but the cache: ids must not change."""
    scan_root = tmp_path / "proj"
    (scan_root / "pkg").mkdir(parents=True)
    module = scan_root / "pkg" / "mod.py"
    module.write_text("def hello():\n    return 1\n", encoding="utf-8")

    in_place_dir = tmp_path / "cache-in-place"
    elsewhere_dir = tmp_path / "cache-elsewhere"
    _write_detect(in_place_dir, module)
    _write_detect(elsewhere_dir, module)

    in_place = step_extract_ast(scan_root, out=in_place_dir)
    elsewhere = step_extract_ast(scan_root, out=elsewhere_dir)

    ids_in_place = sorted(n["id"] for n in in_place["nodes"])
    ids_relocated = sorted(n["id"] for n in elsewhere["nodes"])

    assert ids_in_place, "expected AST nodes for the module"
    assert ids_relocated == ids_in_place, (
        "moving only the cache renamed the code nodes: "
        f"{ids_in_place} -> {ids_relocated}"
    )
