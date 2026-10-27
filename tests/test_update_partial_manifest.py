"""#4807: a doc only partly read during ``--update`` is queued again by the next ``--update``.

Step B3.5 lists the files a subagent read only partway in ``.graphify_partial.txt``. A full
build's Step 9 passes that list to ``_stamped_manifest_files``, so those files stay unstamped and
``detect_incremental`` queues them again (#2225). ``--update`` does not run Step 9: its runbook
writes the manifest itself, so it has to pass the list too.

These tests run the merge block of the rendered ``references/update.md`` on a seeded project,
then ask ``detect_incremental`` what the next run would queue. The generated hosts share one
merge block; each distinct block is a case.
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

SHARED_HOSTS = ["agents", "amp", "claude", "claw", "codex", "copilot", "droid", "kilo",
                "kiro", "opencode", "pi", "trae", "vscode", "windows"]

LONG_V1 = "".join(f"line {i} about Widget\n" for i in range(3000))

# A built project: the manifest a full build leaves, both docs stamped.
FULL_BUILD = """
from pathlib import Path
from graphify.cli import _stamped_manifest_files
from graphify.detect import detect, save_manifest
root = Path('.').resolve()
extraction = {'nodes': [{'id': 'long_widget', 'source_file': 'long.md'},
                        {'id': 'short_gadget', 'source_file': 'short.md'}],
              'edges': [], 'hyperedges': []}
save_manifest(_stamped_manifest_files(detect(root)['files'], extraction, root), root=str(root))
"""

QUEUED = """
import json
from pathlib import Path
from graphify.detect import detect_incremental
new = detect_incremental(Path('.').resolve())['new_files']
print(json.dumps(sorted(Path(f).name for files in new.values() for f in files)))
"""


def _one(blocks: list[str], anchor: str) -> str:
    hits = [b for b in blocks if anchor in b]
    assert len(hits) == 1, f"expected one block containing {anchor!r}, found {len(hits)}"
    return hits[0]


def _runbooks() -> list:
    """One case per distinct merge block: (detect block, merge block), ids naming the hosts."""
    rendered = {a.path: a.content for a in gen.render_all(gen.load_platforms())}
    cases: dict[str, tuple[list[str], str]] = {}
    for host in SHARED_HOSTS:
        update = rendered[f"graphify/skills/{host}/references/update.md"]
        blocks = re.findall(r"```bash\n(.*?)```", update, re.S)
        merge = _one(blocks, "build_merge(")
        cases.setdefault(merge, ([], _one(blocks, "result = detect_incremental(")))[0].append(host)
    return [pytest.param(detect, merge, id="+".join(hosts))
            for merge, (hosts, detect) in cases.items()]


def _env() -> dict[str, str]:
    # The blocks are `python -c "..."` strings run by bash, which expands any backticks in them.
    # Keep an installed graphify off PATH so nothing it prints can reach the Python source, and
    # pin the output directory so a GRAPHIFY_OUT in the caller's shell cannot move it.
    path = os.pathsep.join(p for p in os.environ.get("PATH", "").split(os.pathsep)
                           if not (Path(p) / "graphify").exists())
    return {**os.environ, "PATH": path, "PYTHONPATH": str(REPO_ROOT),
            "GRAPHIFY_OUT": "graphify-out"}


def _bash(block: str, proj: Path) -> str:
    block = block.replace("INPUT_PATH", proj.as_posix()).replace("IS_DIRECTED", "False")
    result = subprocess.run(["bash", "-c", block], cwd=proj, env=_env(),
                            capture_output=True, text=True, timeout=300)
    assert result.returncode == 0, f"runbook block failed:\n{result.stdout}\n{result.stderr}"
    return result.stdout


def _python(source: str, proj: Path) -> str:
    result = subprocess.run([sys.executable, "-c", source], cwd=proj, env=_env(),
                            capture_output=True, text=True, timeout=300)
    assert result.returncode == 0, f"helper failed:\n{result.stdout}\n{result.stderr}"
    return result.stdout


def _queued(proj: Path) -> list[str]:
    return json.loads(_python(QUEUED, proj).strip().splitlines()[-1])


def _built_project(tmp_path: Path) -> Path:
    proj = tmp_path / "proj"
    out = proj / "graphify-out"
    out.mkdir(parents=True)
    (proj / "long.md").write_text(LONG_V1, encoding="utf-8")
    (proj / "short.md").write_text("# Short\nGadget uses Widget\n", encoding="utf-8")
    (out / ".graphify_python").write_text(sys.executable, encoding="utf-8")
    _python(FULL_BUILD, proj)
    (out / "graph.json").write_text(json.dumps({
        "nodes": [{"id": "long_widget", "label": "Widget", "source_file": "long.md"},
                  {"id": "short_gadget", "label": "Gadget", "source_file": "short.md"}],
        "edges": [], "hyperedges": [],
    }), encoding="utf-8")
    assert _queued(proj) == []
    return proj


def _update(proj: Path, detect: str, merge: str, nodes: list[dict],
            partial: list[str] | None) -> None:
    """One --update: detection, this run's extraction (Part C's output), the list B3.5 writes
    when it runs (None: it did not), then the merge."""
    out = proj / "graphify-out"
    _bash(detect, proj)
    (out / ".graphify_extract.json").write_text(json.dumps({
        "nodes": nodes, "edges": [], "hyperedges": [], "input_tokens": 0, "output_tokens": 0,
    }), encoding="utf-8")
    if partial is not None:
        (out / ".graphify_partial.txt").write_text("\n".join(partial), encoding="utf-8")
    _bash(merge, proj)


@pytest.mark.parametrize("detect,merge", _runbooks())
def test_partly_read_doc_is_queued_again_by_the_next_update(detect, merge, tmp_path):
    proj = _built_project(tmp_path)
    (proj / "long.md").write_text(LONG_V1 + "line 3000 about Sprocket\n", encoding="utf-8")
    (proj / "short.md").write_text("# Short\nGadget uses Sprocket\n", encoding="utf-8")

    # Both docs changed. The subagent read short.md to its end and long.md only partway;
    # B3.5 lists long.md by the path the subagent was given, which is absolute.
    _update(proj, detect, merge,
            nodes=[{"id": "long_widget", "label": "Widget", "source_file": "long.md"},
                   {"id": "short_sprocket", "label": "Sprocket", "source_file": "short.md"}],
            partial=[str(proj / "long.md")])

    assert _queued(proj) == ["long.md"]
    # The nodes read so far are kept until the retry replaces them.
    extract = proj / "graphify-out" / ".graphify_extract.json"
    merged = json.loads(extract.read_text(encoding="utf-8"))
    assert "long_widget" in {node["id"] for node in merged["nodes"]}


@pytest.mark.parametrize("detect,merge", _runbooks())
def test_a_used_partial_list_does_not_hold_back_a_later_cache_hit(detect, merge, tmp_path):
    proj = _built_project(tmp_path)
    (proj / "long.md").write_text(LONG_V1 + "line 3000 about Sprocket\n", encoding="utf-8")
    _update(proj, detect, merge,
            nodes=[{"id": "long_widget", "label": "Widget", "source_file": "long.md"}],
            partial=[str(proj / "long.md")])
    assert _queued(proj) == ["long.md"]

    # long.md goes back to the content the full build read to its end, so the next run serves
    # it from the semantic cache and no subagent reports on it. A run that skips B3.5 writes
    # no list; the previous run's list must not hold the doc back, or it is never stamped.
    (proj / "long.md").write_text(LONG_V1, encoding="utf-8")
    _update(proj, detect, merge,
            nodes=[{"id": "long_widget", "label": "Widget", "source_file": "long.md"}],
            partial=None)

    assert _queued(proj) == []
