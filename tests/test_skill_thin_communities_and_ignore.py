"""Two facts an operator had to dig out of the source (#2842, items 1 and 3).

1. ``report.generate`` leaves communities with fewer than ``min_community_size``
   real nodes out of the report's community sections. The skill's labeling step
   did not say so, so the missing communities looked like a bug.
2. When the large-corpus warning fires, the skill only offered to narrow the run
   to one subfolder. A large folder that is not project content (agent logs,
   scratch) is better excluded with ``.graphifyignore``, which ``detect()``
   already reads.
"""
from __future__ import annotations

import inspect
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from graphify.report import generate  # noqa: E402
from tools.skillgen import gen  # noqa: E402

_NARROW_PROMPT = "then ask which subfolder to run on"
_LABEL_STEP = "### Step 5 - Label communities"


def _bodies_with(marker: str):
    # Monolith bodies (aider, devin) are frozen against a pinned v8 baseline and
    # are not covered by this change.
    bodies = [
        a
        for p in gen.load_platforms().values()
        if p.bucket != "monolith"
        for a in gen.render(p)
        if marker in a.content
    ]
    assert bodies, f"no rendered non-monolith skill body contains {marker!r}"
    return bodies


def test_large_corpus_warning_offers_graphifyignore():
    for a in _bodies_with(_NARROW_PROMPT):
        lines = a.content.splitlines()
        i = next(n for n, ln in enumerate(lines) if _NARROW_PROMPT in ln)
        assert "`.graphifyignore`" in lines[i + 1], a.path


def test_label_step_states_the_thin_community_threshold():
    default = inspect.signature(generate).parameters["min_community_size"].default
    for a in _bodies_with(_LABEL_STEP):
        step = a.content.split(_LABEL_STEP, 1)[1].split("\n### ", 1)[0]
        assert f"min_community_size={default}" in step, a.path
        assert "thin omitted" in step, a.path


def test_graphifyignore_excludes_a_scratch_folder(tmp_path):
    # The skill's advice only holds if detect() honours a scan-root
    # .graphifyignore entry for a whole folder.
    from graphify.detect import detect

    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("def f():\n    return 1\n", encoding="utf-8")
    (tmp_path / "agent-logs").mkdir()
    (tmp_path / "agent-logs" / "session.md").write_text("# log\n", encoding="utf-8")
    (tmp_path / ".graphifyignore").write_text("agent-logs/\n", encoding="utf-8")

    result = detect(tmp_path)
    files = [f for group in result["files"].values() for f in group]
    assert any(f.endswith("app.py") for f in files)
    assert not any("agent-logs" in f for f in files)
