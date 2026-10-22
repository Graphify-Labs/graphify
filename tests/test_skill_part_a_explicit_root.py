"""Part A supplies a trusted explicit root independent of its cache location (#3727).

Inspect the actual emitted multiline call structurally. Execute its complete
program twice, changing only cache_root, to retain the original identity proof
without depending on keyword order or a superseded literal INPUT_PATH template.
"""
from __future__ import annotations

import ast
import copy
import json
from pathlib import Path
import re
import sys

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.skillgen import gen  # noqa: E402


def _split_hosts() -> list[gen.Platform]:
    return [p for p in gen.load_platforms().values() if p.bucket != "monolith"]


def _part_a_program(platform: gen.Platform) -> ast.Module:
    """Decode only the actual rendered Part A shell program for either shell."""
    body = gen.render(platform)[0].content
    section = body.split("#### Part A - Structural extraction for code files", 1)[1].split(
        "#### Part B - Semantic extraction", 1)[0]
    if platform.shell == "powershell":
        programs = re.findall(r"@'\n(.*?)\n'@", section, re.S)
    else:
        programs = [source.replace('\\"', '"') for source in re.findall(
            r' -c "\n(.*?)\n"\s*```', section, re.S)]
    assert len(programs) == 1, f"[{platform.key}] Part A program not found"
    return ast.parse(programs[0])


def _extract_calls(tree):
    """Find the real extraction call without assuming a single physical line."""
    return [node for node in ast.walk(tree) if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name) and node.func.id == "extract"
            and node.args and isinstance(node.args[0], ast.Name) and node.args[0].id == "code_files"]


def test_split_hosts_are_discovered():
    """The parametrized guard must not pass vacuously on an empty list."""
    assert len(_split_hosts()) >= 10, [p.key for p in _split_hosts()]


@pytest.mark.parametrize("platform", _split_hosts(), ids=lambda p: p.key)
def test_part_a_passes_an_explicit_root(platform: gen.Platform):
    """Every host anchors extraction to the recorded scan root, not cache fallback."""
    tree = _part_a_program(platform)
    calls = _extract_calls(tree)
    assert calls, f"[{platform.key}] Part A extract() call not found"
    assert any(isinstance(node, ast.Constant) and node.value == "graphify-out/.graphify_root"
               for node in ast.walk(tree))
    for call in calls:
        roots = [keyword.value for keyword in call.keywords if keyword.arg == "root"]
        assert len(roots) == 1 and ast.unparse(roots[0]) == "scan_root", platform.key


def test_relocating_only_the_cache_does_not_rename_part_a_nodes(tmp_path: Path, monkeypatch):
    """Run actual Part A twice; only its cache keyword changes, preserving IDs and provenance."""
    scan_root = tmp_path / "proj"
    (scan_root / "pkg").mkdir(parents=True)
    module = scan_root / "pkg" / "mod.py"
    module.write_text("def hello():\n    return 1\n", encoding="utf-8")
    elsewhere = tmp_path / "cache-elsewhere"
    elsewhere.mkdir()
    output = tmp_path / "graphify-out"
    output.mkdir()
    (output / ".graphify_root").write_text(str(scan_root), encoding="utf-8")
    (output / ".graphify_detect.json").write_text(json.dumps({
        "files": {"code": [str(module)]}}), encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    original = _part_a_program(gen.load_platforms()["claude"])
    relocated = copy.deepcopy(original)
    (call,) = _extract_calls(relocated)
    (cache_keyword,) = [keyword for keyword in call.keywords if keyword.arg == "cache_root"]
    cache_keyword.value = ast.Call(func=ast.Name(id="Path", ctx=ast.Load()),
                                   args=[ast.Constant(value=str(elsewhere))], keywords=[])
    ast.fix_missing_locations(relocated)
    assert ast.dump(original) != ast.dump(relocated)
    results = []
    for program in (original, relocated):
        scope = {}
        exec(compile(program, "<actual-shipped-part-a>", "exec"), scope)
        results.append(scope["result"])
    ids = [sorted(node["id"] for node in result["nodes"]) for result in results]
    sources = [{node["source_file"] for node in result["nodes"]} for result in results]
    assert ids[0] and ids[1] == ids[0], "moving only the cache renamed the code nodes"
    assert sources == [{"pkg/mod.py"}, {"pkg/mod.py"}]
