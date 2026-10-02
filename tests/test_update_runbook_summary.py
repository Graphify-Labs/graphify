"""The --update runbook prints a summary of detect_incremental, not the result (#3944).

The first block of ``references/update.md`` both persisted the incremental
detection result and printed it in full. That result carries every file path in
the corpus, and the reader of that stdout is the agent's context window, not a
person scrolling a terminal: every later step reads the sidecar from disk, so
the dump only copied the most verbose artifact of the pipeline into its scarcest
resource. Step 2 of the core already forbids printing ``detect()`` for the same
reason; the incremental path was the one place that still dumped it.
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

from tools.skillgen import gen  # noqa: E402

UPDATE_REFERENCES = sorted((REPO_ROOT / "graphify" / "skills").glob("*/references/update.md"))
_PY_INVOKE = '$(cat graphify-out/.graphify_python) -c "'


def _detection_block(markdown: str) -> str:
    """The python body of the first ``-c "..."`` block: the incremental detection."""
    lines = markdown.splitlines()
    start = lines.index(_PY_INVOKE) + 1
    end = lines.index('"', start)
    body = "\n".join(gen._unescape_bash_dq(line) for line in lines[start:end])
    assert "detect_incremental(Path('INPUT_PATH'))" in body, "not the detection block"
    return body


def test_update_references_are_discovered():
    """The parametrized guard below must not pass vacuously on an empty glob."""
    assert len(UPDATE_REFERENCES) >= 10, [str(p) for p in UPDATE_REFERENCES]


@pytest.mark.parametrize("path", UPDATE_REFERENCES, ids=lambda p: p.parent.parent.name)
def test_no_update_reference_prints_the_full_incremental_result(path: Path):
    body = _detection_block(path.read_text(encoding="utf-8"))
    assert "print(json.dumps(result" not in body, (
        f"{path.relative_to(REPO_ROOT)} prints the whole detect_incremental result (#3944)"
    )


def test_detection_block_prints_a_summary_and_keeps_every_path_on_disk(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    """Run the shipped block on a small corpus: no corpus path may reach stdout."""
    corpus = tmp_path / "corpus"
    (corpus / "src").mkdir(parents=True)
    names = [f"module_{i:03d}.py" for i in range(40)]
    for name in names:
        (corpus / "src" / name).write_text("def f():\n    return 1\n", encoding="utf-8")
    (tmp_path / "graphify-out").mkdir()

    claude = REPO_ROOT / "graphify" / "skills" / "claude" / "references" / "update.md"
    body = _detection_block(claude.read_text(encoding="utf-8"))
    body = body.replace("Path('INPUT_PATH')", f"Path({str(corpus)!r})")

    monkeypatch.chdir(tmp_path)
    exec(compile(body, str(claude), "exec"), {"__name__": "__update_runbook__"})
    out = capsys.readouterr().out

    # The data every later step needs is on disk, in full.
    sidecar = json.loads(
        (tmp_path / "graphify-out" / ".graphify_incremental.json").read_text(encoding="utf-8")
    )
    listed = [f for files in sidecar["files"].values() for f in files]
    assert sorted(Path(f).name for f in listed) == names
    assert sidecar["new_total"] == len(names)

    # ...and stdout carries only what the next decision depends on.
    leaked = [name for name in names if name in out]
    assert leaked == [], f"{len(leaked)} corpus path(s) printed to stdout, e.g. {leaked[:3]}"
    assert f"{len(names)} new/changed file(s) to re-extract." in out
    assert f'"new_total": {len(names)}' in out
    assert ".graphify_incremental.json" in out
