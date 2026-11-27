"""#5097: the ``--update`` runbook stamps the manifest only after Step 4 writes the graph.

The update runbook merges this run's extraction and then stamps the manifest. While
that stamp lived inside the merge block, a Step 4 that refused the write (the #479
shrink guard, or a saved semantic node missing from the new graph) left the changed
files already stamped: ``graph.json`` still held the old content, and the next
``--update`` reported nothing to do. ``--force`` could not recover either, because the
first block already saw no changes.

These tests run the rendered runbook blocks through the interpreter on a seeded
project. They assert the merge block does not advance the manifest, and that the
stamp after Step 4 does. The stamp is reached only when Step 4 has exited
successfully (it raises instead of writing a refused graph), so a refusal leaves the
changed files queued for the retry.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.skillgen import gen  # noqa: E402

DOC = "notes.md"
OLD_CONTENT = "# Notes\n\n## Gadget\n\nA widget.\n"
NEW_CONTENT = "# Notes\n\n## Flange\n\nA widget.\n"

# The manifest and graph a full build leaves after it read OLD_CONTENT.
FULL_BUILD = """
import sys
from pathlib import Path
from graphify.cli import _stamped_manifest_files
from graphify.detect import detect, save_manifest

root = Path(sys.argv[1]).resolve()
extraction = {
    "nodes": [{"id": "notes_gadget", "label": "Gadget", "source_file": "notes.md"}],
    "edges": [],
    "hyperedges": [],
}
save_manifest(_stamped_manifest_files(detect(root)["files"], extraction, root), root=str(root))
"""

# What the next --update would queue, relative to the scan root in argv[1].
QUEUED = """
import json, sys
from pathlib import Path
from graphify.detect import detect_incremental

root = Path(sys.argv[1]).resolve()
new = detect_incremental(Path(sys.argv[1]))["new_files"]
print(json.dumps(sorted(Path(f).resolve().relative_to(root).as_posix()
                        for files in new.values() for f in files)))
"""


def _python_blocks(text: str) -> list[str]:
    blocks = []
    for block in re.findall(r"```bash\n(.*?)```", text, re.S):
        match = re.search(r' -c "\n(.*)\n"\s*$', block, re.S)
        if match:
            blocks.append(match.group(1).replace('\\"', '"'))
    return blocks


def _one(blocks: list[str], anchor: str) -> str:
    hits = [b for b in blocks if anchor in b]
    assert len(hits) == 1, f"expected one block containing {anchor!r}, found {len(hits)}"
    return hits[0]


def _cases() -> list:
    """One case per distinct (detect, populate, merge, stamp) set of update blocks."""
    platforms = gen.load_platforms()
    cases: dict[tuple[str, ...], list[str]] = {}
    for artifact in gen.render_all(platforms):
        match = re.fullmatch(r"graphify/skills/(\w+)/references/update\.md", artifact.path)
        if not match:
            continue
        host = match.group(1)
        blocks = _python_blocks(artifact.content)
        key = (
            _one(blocks, "detect_incremental("),
            _one(blocks, "'all_files': r.get('files'"),
            _one(blocks, "build_merge("),
            _one(blocks, "from graphify.cli import _stamped_manifest_files"),
        )
        cases.setdefault(key, []).append(host)
    assert cases, "no host renders the update reference"
    return [pytest.param(*blocks, id="+".join(sorted(names))) for blocks, names in cases.items()]


def _env() -> dict[str, str]:
    return {
        **os.environ,
        "GRAPHIFY_OUT": "graphify-out",
        "PYTHONPATH": str(REPO_ROOT),
    }


def _run(source: str, proj: Path, *args: str) -> str:
    result = _try_run(source, proj, *args)
    assert result.returncode == 0, f"runbook block failed:\n{result.stdout}\n{result.stderr}"
    return result.stdout


def _try_run(source: str, proj: Path, *args: str) -> subprocess.CompletedProcess[str]:
    # The runbook tells the agent to substitute the real flag values.
    source = source.replace("IS_DIRECTED", "False").replace("IS_FORCE", "False")
    return subprocess.run(
        [sys.executable, "-c", source, *args],
        cwd=proj,
        env=_env(),
        capture_output=True,
        text=True,
        timeout=300,
    )


def _step4_wrote_the_graph(proj: Path) -> None:
    """Model Step 4's successful write: graph.json is replaced after the merge.

    The stamp refuses when graph.json's stat equals the one the merge block
    recorded, so a simulation must advance it. A real Step 4 does a fresh atomic
    replace, which lands in a later clock tick than the merge block's stat.
    """
    out = proj / "graphify-out"
    state = json.loads((out / ".graphify_update_extract.json").read_text(encoding="utf-8"))
    merged = json.loads((out / ".graphify_extract.json").read_text(encoding="utf-8"))
    graph = out / "graph.json"
    graph.write_text(json.dumps({
        "nodes": merged["nodes"], "edges": [], "hyperedges": [],
    }), encoding="utf-8")
    bumped = int(state.get("graph_mtime_ns") or 0) + 1_000_000_000
    os.utime(graph, ns=(bumped, bumped))


def _queued(proj: Path, root: Path) -> list[str]:
    return json.loads(_run(QUEUED, proj, str(root)).strip().splitlines()[-1])


def _seeded_project(tmp_path: Path) -> tuple[Path, Path]:
    """A project whose full build stamped notes.md, as the runbook leaves it."""
    proj = tmp_path / "proj"
    (proj / "graphify-out").mkdir(parents=True)
    doc = proj / DOC
    doc.write_text(OLD_CONTENT, encoding="utf-8")
    # Step 1 persists the scan root; the update blocks read it from here (#4762).
    (proj / "graphify-out" / ".graphify_root").write_text(".", encoding="utf-8")
    _run(FULL_BUILD, proj, str(proj))
    (proj / "graphify-out" / "graph.json").write_text(json.dumps({
        "nodes": [{"id": "notes_gadget", "label": "Gadget", "source_file": DOC,
                   "source_location": None}],
        "edges": [],
        "hyperedges": [],
    }), encoding="utf-8")
    assert _queued(proj, proj) == []
    return proj, doc


def _detect_and_merge(proj: Path, detect: str, populate: str, merge: str) -> None:
    """Everything an --update runs before Step 4, with this run's extraction in place."""
    _run(detect, proj)
    _run(populate, proj)
    # Part C's output: the renamed section, so notes_gadget is gone from the fresh
    # extraction (the saved-semantic-node guard refuses that write).
    (proj / "graphify-out" / ".graphify_extract.json").write_text(json.dumps({
        "nodes": [{"id": "notes_flange", "label": "Flange", "source_file": DOC,
                   "source_location": None}],
        "edges": [],
        "hyperedges": [],
        "input_tokens": 0,
        "output_tokens": 0,
    }), encoding="utf-8")
    _run(merge, proj)


@pytest.mark.parametrize("detect,populate,merge,stamp", _cases())
def test_merge_does_not_stamp_the_manifest(detect, populate, merge, stamp, tmp_path):
    """A refused Step 4 must leave the changed doc queued for the next --update."""
    proj, doc = _seeded_project(tmp_path)
    doc.write_text(NEW_CONTENT, encoding="utf-8")
    manifest = proj / "graphify-out" / "manifest.json"
    before = manifest.read_bytes()

    _detect_and_merge(proj, detect, populate, merge)

    # The merge only rewrites .graphify_extract.json; the manifest is Step 4's job.
    assert manifest.read_bytes() == before, "the merge block stamped the manifest too early"
    assert _queued(proj, proj) == [DOC], "a refused Step 4 must leave the doc queued"


@pytest.mark.parametrize("detect,populate,merge,stamp", _cases())
def test_the_stamp_after_step_4_advances_the_manifest(detect, populate, merge, stamp, tmp_path):
    """Once Step 4 succeeded, the stamp records the change and the retry is a no-op."""
    proj, doc = _seeded_project(tmp_path)
    before = json.loads((proj / "graphify-out" / "manifest.json").read_text(encoding="utf-8"))
    doc.write_text(NEW_CONTENT, encoding="utf-8")

    _detect_and_merge(proj, detect, populate, merge)
    _step4_wrote_the_graph(proj)
    _run(stamp, proj)

    after = json.loads((proj / "graphify-out" / "manifest.json").read_text(encoding="utf-8"))
    assert after[DOC]["semantic_hash"] != before[DOC]["semantic_hash"]
    assert _queued(proj, proj) == []


@pytest.mark.parametrize("detect,populate,merge,stamp", _cases())
def test_the_stamp_refuses_when_step_4_did_not_write_the_graph(
        detect, populate, merge, stamp, tmp_path):
    """A stamp that runs before/without Step 4 must not advance the manifest.

    The runbook orders the stamp after Step 4, but the block no longer trusts that
    order: it compares graph.json's stat with the one the merge block recorded and
    exits non-zero without stamping when Step 4 never wrote it (#5097).
    """
    proj, doc = _seeded_project(tmp_path)
    doc.write_text(NEW_CONTENT, encoding="utf-8")
    manifest = proj / "graphify-out" / "manifest.json"

    _detect_and_merge(proj, detect, populate, merge)
    before = manifest.read_bytes()

    result = _try_run(stamp, proj)

    assert result.returncode != 0, "the stamp must refuse without a Step 4 write"
    assert "Step 4 did not rewrite" in (result.stdout + result.stderr)
    assert manifest.read_bytes() == before
    assert _queued(proj, proj) == [DOC]
