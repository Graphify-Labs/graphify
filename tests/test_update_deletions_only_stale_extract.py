"""#5340: a deletions-only ``--update`` must not merge an earlier run's ``.graphify_extract.json``.

The ``--update`` runbook writes an empty extraction for a run that only has deletions, but only
when no ``.graphify_extract.json`` exists. Nothing in such a run writes one before that point, so
a file found there was left by an earlier run that never reached Step 9's cleanup. Merging it
replaces the stored nodes of every file it names, and since ``build_merge`` lets a re-extracted
source win over a deleted one, a deleted file it still names is never pruned.

This runs the rendered ``references/update.md`` blocks of every host (hosts that render the same
blocks share a case) on a built project with one deleted doc and a leftover extraction that still
holds that doc's node.
"""
from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.skillgen import gen  # noqa: E402

# Same gate as test_update_partial_manifest.py: on Windows a bare "bash" can resolve to the
# WSL launcher, which cannot run the Windows interpreter path the blocks are given.
pytestmark = pytest.mark.skipif(
    shutil.which("bash") is None or shutil.which("cat") is None or sys.platform == "win32",
    reason="runs the runbook's bash blocks: needs bash and cat on a POSIX host",
)

# A built project: the manifest a full build leaves, both docs stamped. argv[1] is the scan root.
FULL_BUILD = """
import sys
from pathlib import Path
from graphify.cli import _stamped_manifest_files
from graphify.detect import detect, save_manifest
root = Path(sys.argv[1])
extraction = {'nodes': [{'id': 'keep_widget', 'source_file': 'keep.md'},
                        {'id': 'gone_gadget', 'source_file': 'gone.md'}],
              'edges': [], 'hyperedges': []}
save_manifest(_stamped_manifest_files(detect(root)['files'], extraction, root), root=sys.argv[1])
"""

NODES = [
    {"id": "keep_widget", "label": "Widget", "file_type": "document", "source_file": "keep.md"},
    {"id": "gone_gadget", "label": "Gadget", "file_type": "document", "source_file": "gone.md"},
]


def _bash_blocks(text: str) -> list[str]:
    return re.findall(r"```bash\n(.*?)```", text, re.S)


def _one(blocks: list[str], anchor: str) -> str:
    hits = [b for b in blocks if anchor in b]
    assert len(hits) == 1, f"expected one block containing {anchor!r}, found {len(hits)}"
    return hits[0]


def _cases() -> list:
    """One case per distinct (detect, populate, deletions-only, merge) block set, named by host."""
    cases: dict[tuple[str, ...], list[str]] = {}
    for art in gen.render_all(gen.load_platforms()):
        m = re.fullmatch(r"graphify/skills/(\w+)/references/update\.md", art.path)
        if not m:
            continue
        blocks = _bash_blocks(art.content)
        key = (_one(blocks, "result = detect_incremental("),
               _one(blocks, "'all_files': r.get('files'"),
               _one(blocks, "Only deletions"),
               _one(blocks, "build_merge("))
        cases.setdefault(key, []).append(m.group(1))
    assert cases, "no host renders references/update.md"
    return [pytest.param(*blocks, id="+".join(sorted(hosts))) for blocks, hosts in cases.items()]


def _env() -> dict[str, str]:
    # bash expands backticks inside the double-quoted `python -c "..."` blocks: keep an installed
    # graphify off PATH so nothing it prints can reach the Python source. Pin the output
    # directory, and drop the startup files a non-interactive bash would source.
    path = os.pathsep.join(p for p in os.environ.get("PATH", "").split(os.pathsep)
                           if not (Path(p) / "graphify").exists())
    env = {k: v for k, v in os.environ.items() if k not in ("BASH_ENV", "ENV")}
    return {**env, "PATH": path, "PYTHONPATH": str(REPO_ROOT), "GRAPHIFY_OUT": "graphify-out"}


def _bash(block: str, proj: Path) -> str:
    # The blocks start the interpreter recorded in .graphify_python, unquoted. Name this test's
    # interpreter directly, quoted, so a path with a space in it still runs.
    block = block.replace("$(cat graphify-out/.graphify_python)",
                          shlex.quote(Path(sys.executable).as_posix()))
    block = block.replace("IS_DIRECTED", "False")
    result = subprocess.run(["bash", "-e", "-c", block], cwd=proj, env=_env(),
                            capture_output=True, text=True, timeout=300)
    assert result.returncode == 0, f"runbook block failed:\n{result.stdout}\n{result.stderr}"
    return result.stdout


@pytest.mark.parametrize("detect,populate,deletions_only,merge", _cases())
def test_deletions_only_update_ignores_a_leftover_extraction(
    tmp_path, detect, populate, deletions_only, merge
):
    proj = tmp_path / "proj"
    out = proj / "graphify-out"
    out.mkdir(parents=True)
    (proj / "keep.md").write_text("# Keep\nWidget\n", encoding="utf-8")
    (proj / "gone.md").write_text("# Gone\nGadget\n", encoding="utf-8")
    (out / ".graphify_root").write_text(proj.as_posix(), encoding="utf-8")
    subprocess.run([sys.executable, "-c", FULL_BUILD, str(proj)], cwd=proj, env=_env(),
                   check=True, capture_output=True, text=True, timeout=300)
    (out / "graph.json").write_text(json.dumps({"nodes": NODES, "edges": [], "hyperedges": []}),
                                    encoding="utf-8")

    # An earlier update stopped after Steps 4-8, so its merged extraction is still on disk.
    (out / ".graphify_extract.json").write_text(json.dumps({
        "nodes": NODES, "edges": [], "hyperedges": [], "input_tokens": 0, "output_tokens": 0,
    }), encoding="utf-8")
    (proj / "gone.md").unlink()

    printed = _bash(detect, proj)
    assert "1 deleted file(s) to prune." in printed, printed
    assert "to re-extract" not in printed, printed
    _bash(populate, proj)
    _bash(deletions_only, proj)
    _bash(merge, proj)

    merged = json.loads((out / ".graphify_extract.json").read_text(encoding="utf-8"))
    ids = {n["id"] for n in merged["nodes"]}
    assert "gone_gadget" not in ids, "the deleted doc's node came back from the leftover extraction"
    assert "keep_widget" in ids
