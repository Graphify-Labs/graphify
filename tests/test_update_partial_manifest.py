"""#4807: a doc only partly read during ``--update`` is queued again by the next ``--update``.

Step B3.5 lists the files a subagent read only partway in ``.graphify_partial.txt``. A full
build's Step 9 passes that list to ``_stamped_manifest_files``, so those files stay unstamped and
``detect_incremental`` queues them again (#2225). The ``--update`` runbook writes the manifest
itself, so it has to pass the list too, and leave it for Step 9 when an agent runs that after the
update. A list an earlier run left must not hold back this run's files.

These tests run the blocks of each host's rendered ``references/update.md`` (and, for Step 9, its
rendered core skill) on a seeded project, then ask ``detect_incremental`` what the next run would
queue. Hosts that render the same blocks share a case. Windows renders Step 9 for PowerShell, so
it has no case in the Step 9 test; its ``update.md`` blocks are bash like every other host's.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.skillgen import gen  # noqa: E402

pytestmark = pytest.mark.skipif(
    shutil.which("bash") is None or shutil.which("cat") is None or sys.platform == "win32",
    reason="runs the runbook's bash blocks: needs bash and cat on a POSIX host",
)

LONG = "guide/long.md"  # nested, so a path cut down to its file name no longer matches
LONG_V1 = "".join(f"line {i} about Widget\n" for i in range(3000))

# A built project: the manifest a full build leaves, both docs stamped. argv[1] is the scan root.
FULL_BUILD = """
import sys
from pathlib import Path
from graphify.cli import _stamped_manifest_files
from graphify.detect import detect, save_manifest
root = Path(sys.argv[1])
extraction = {'nodes': [{'id': 'long_widget', 'source_file': 'guide/long.md'},
                        {'id': 'short_gadget', 'source_file': 'short.md'}],
              'edges': [], 'hyperedges': []}
save_manifest(_stamped_manifest_files(detect(root)['files'], extraction, root), root=sys.argv[1])
"""

# What the next --update would queue, relative to the scan root in argv[1].
QUEUED = """
import json, sys
from pathlib import Path
from graphify.detect import detect_incremental
root = Path(sys.argv[1]).resolve()
new = detect_incremental(Path(sys.argv[1]))['new_files']
print(json.dumps(sorted(Path(f).resolve().relative_to(root).as_posix()
                        for files in new.values() for f in files)))
"""


def _bash_blocks(text: str) -> list[str]:
    return re.findall(r"```bash\n(.*?)```", text, re.S)


def _one(blocks: list[str], anchor: str) -> str:
    hits = [b for b in blocks if anchor in b]
    assert len(hits) == 1, f"expected one block containing {anchor!r}, found {len(hits)}"
    return hits[0]


def _cases(*, step9: bool) -> list:
    """One case per distinct set of blocks (detect, populate, merge, Step 9), named by host."""
    platforms = gen.load_platforms()
    hosts = sorted(m.group(1) for a in gen.render_all(platforms)
                   if (m := re.fullmatch(r"graphify/skills/(\w+)/references/update\.md", a.path)))
    cases: dict[tuple[str, ...], list[str]] = {}
    for host in hosts:
        rendered = {a.path: a.content for a in gen.render_all(platforms, only=host)}
        update = _bash_blocks(rendered[f"graphify/skills/{host}/references/update.md"])
        blocks = (_one(update, "result = detect_incremental("),
                  _one(update, "'all_files': r.get('files'"),
                  _one(update, "build_merge("))
        if step9:
            core = next(text for path, text in rendered.items()
                        if re.fullmatch(r"graphify/skill(-\w+)?\.md", path))
            found = [b for b in _bash_blocks(core) if "Update cumulative cost tracker" in b]
            if not found:  # Step 9 rendered for PowerShell (windows)
                continue
            blocks += (_one(found, "Update cumulative cost tracker"),)
        cases.setdefault(blocks, []).append(host)
    assert cases, "no host renders these blocks"
    return [pytest.param(*blocks, id="+".join(names)) for blocks, names in cases.items()]


def _env() -> dict[str, str]:
    # The blocks are `python -c "..."` strings run by bash, which expands any backticks in them:
    # keep an installed graphify off PATH so nothing it prints can reach the Python source. Pin
    # the output directory, and drop the startup files a non-interactive bash would source.
    path = os.pathsep.join(p for p in os.environ.get("PATH", "").split(os.pathsep)
                           if not (Path(p) / "graphify").exists())
    env = {k: v for k, v in os.environ.items() if k not in ("BASH_ENV", "ENV")}
    return {**env, "PATH": path, "PYTHONPATH": str(REPO_ROOT), "GRAPHIFY_OUT": "graphify-out"}


def _bash(block: str, proj: Path, root: str) -> str:
    block = block.replace("INPUT_PATH", root).replace("IS_DIRECTED", "False")
    result = subprocess.run(["bash", "-c", block], cwd=proj, env=_env(),
                            capture_output=True, text=True, timeout=300)
    assert result.returncode == 0, f"runbook block failed:\n{result.stdout}\n{result.stderr}"
    return result.stdout


def _python(source: str, proj: Path, *args: str) -> str:
    result = subprocess.run([sys.executable, "-c", source, *args], cwd=proj, env=_env(),
                            capture_output=True, text=True, timeout=300)
    assert result.returncode == 0, f"helper failed:\n{result.stdout}\n{result.stderr}"
    return result.stdout


def _queued(proj: Path, root: str) -> list[str]:
    return json.loads(_python(QUEUED, proj, root).strip().splitlines()[-1])


def _built_project(tmp_path: Path, root: str) -> Path:
    """A project at tmp_path/proj with scan root proj/<root>, as `/graphify <root>` builds it."""
    proj = tmp_path / "proj"
    (proj / root / "guide").mkdir(parents=True)
    out = proj / "graphify-out"
    out.mkdir()
    (proj / root / LONG).write_text(LONG_V1, encoding="utf-8")
    (proj / root / "short.md").write_text("# Short\nGadget uses Widget\n", encoding="utf-8")
    (out / ".graphify_python").write_text(sys.executable, encoding="utf-8")
    _python(FULL_BUILD, proj, root)
    (out / "graph.json").write_text(json.dumps({
        "nodes": [{"id": "long_widget", "label": "Widget", "source_file": LONG},
                  {"id": "short_gadget", "label": "Gadget", "source_file": "short.md"}],
        "edges": [], "hyperedges": [],
    }), encoding="utf-8")
    assert _queued(proj, root) == []
    return proj


def _update(proj: Path, root: str, detect: str, populate: str, merge: str, *,
            nodes: list[dict], partial: list[str] | None) -> None:
    """One --update up to its manifest write: detection, this run's extraction (Part C's
    output), the list B3.5 writes when it runs (None: it did not), then the merge."""
    out = proj / "graphify-out"
    _bash(detect, proj, root)
    _bash(populate, proj, root)
    (out / ".graphify_extract.json").write_text(json.dumps({
        "nodes": nodes, "edges": [], "hyperedges": [], "input_tokens": 0, "output_tokens": 0,
    }), encoding="utf-8")
    if partial is not None:
        (out / ".graphify_partial.txt").write_text("\n".join(partial), encoding="utf-8")
    _bash(merge, proj, root)


def _edit_long(proj: Path, root: str) -> None:
    (proj / root / LONG).write_text(LONG_V1 + "line 3000 about Sprocket\n", encoding="utf-8")


LONG_NODE = {"id": "long_widget", "label": "Widget", "source_file": LONG}
SHORT_NODE = {"id": "short_sprocket", "label": "Sprocket", "source_file": "short.md"}


@pytest.mark.parametrize("root", [".", "docs"])
@pytest.mark.parametrize("entry", ["absolute", "root-relative"])
@pytest.mark.parametrize("detect,populate,merge", _cases(step9=False))
def test_partly_read_doc_is_queued_again_by_the_next_update(
        detect, populate, merge, entry, root, tmp_path):
    proj = _built_project(tmp_path, root)
    _edit_long(proj, root)
    (proj / root / "short.md").write_text("# Short\nGadget uses Sprocket\n", encoding="utf-8")

    # Both docs changed. The subagent read short.md to its end and long.md only partway. B3.5
    # lists long.md as the subagent reported it: the absolute path it was given, or relative
    # to the scan root.
    listed = str(proj / root / LONG) if entry == "absolute" else LONG
    _update(proj, root, detect, populate, merge,
            nodes=[LONG_NODE, SHORT_NODE],
            partial=[listed])

    assert _queued(proj, root) == [LONG]
    # The nodes read so far are kept until the retry replaces them.
    extract = proj / "graphify-out" / ".graphify_extract.json"
    merged = json.loads(extract.read_text(encoding="utf-8"))
    assert LONG in {node.get("source_file") for node in merged["nodes"]}


@pytest.mark.parametrize("detect,populate,merge,step9", _cases(step9=True))
def test_step_9_after_the_update_leaves_the_partly_read_doc_queued(
        detect, populate, merge, step9, tmp_path):
    root = "docs"
    proj = _built_project(tmp_path, root)
    _edit_long(proj, root)
    _update(proj, root, detect, populate, merge,
            nodes=[LONG_NODE], partial=[str(proj / root / LONG)])

    # An agent may run Step 9 after an --update too (its manifest code handles that mode). It
    # reads the same list, so the update must not have removed it.
    _bash(step9, proj, root)

    assert _queued(proj, root) == [LONG]


@pytest.mark.parametrize("detect,populate,merge", _cases(step9=False))
def test_a_list_from_an_earlier_run_does_not_hold_back_a_cache_hit(
        detect, populate, merge, tmp_path):
    root = "docs"
    proj = _built_project(tmp_path, root)
    _edit_long(proj, root)
    _update(proj, root, detect, populate, merge,
            nodes=[LONG_NODE], partial=[str(proj / root / LONG)])
    assert _queued(proj, root) == [LONG]

    # long.md goes back to the content the full build read to its end, so the next run serves
    # it from the semantic cache and no subagent reports on it. A run that skips B3.5 writes
    # no list; the previous run's list must not hold the doc back, or it is never stamped.
    (proj / root / LONG).write_text(LONG_V1, encoding="utf-8")
    _update(proj, root, detect, populate, merge, nodes=[LONG_NODE], partial=None)

    assert _queued(proj, root) == []
