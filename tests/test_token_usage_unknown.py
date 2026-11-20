"""#2786: a host that reports no subagent usage must yield "unknown", not 0.

Codex returns a subagent's completion text but no machine-readable usage. The
skill now has the parent write ``null`` token counts for such a chunk, and every
step after that keeps the total unknown: the B3 chunk merge, the cumulative
cost.json tracker, ``graphify merge-chunks``, and the GRAPH_REPORT.md line. Zero
stays reserved for a run that did no semantic work.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

from graphify.build import build
from graphify.report import generate
from tests.test_report import make_inputs

GRAPHIFY = Path(__file__).resolve().parent.parent / "graphify"
# One skill per core fragment: core.md (codex, the reporting host), aider.md, devin.md.
SKILLS = ["skill-codex.md", "skill-aider.md", "skill-devin.md"]


def _python_block(skill: str, marker: str) -> str:
    """The `python -c "..."` source of the skill's bash block that contains marker."""
    body = (GRAPHIFY / skill).read_text(encoding="utf-8")
    for block in re.findall(r"```bash\n(.*?)```", body, re.S):
        match = re.search(r' -c "\n(.*?)\n"(?:\n|$)', block, re.S)
        if match and marker in match.group(1):
            return match.group(1).replace('\\"', '"')
    raise AssertionError(f"no python block containing {marker!r} in {skill}")


def _merge_chunks(skill: str, tmp_path: Path, chunks: list[dict]) -> tuple[dict, str]:
    out = tmp_path / "graphify-out"
    out.mkdir()
    for i, chunk in enumerate(chunks, 1):
        (out / f".graphify_chunk_{i:02d}.json").write_text(json.dumps(chunk), encoding="utf-8")
    source = _python_block(skill, "total_in, total_out = 0, 0")
    run = subprocess.run([sys.executable, "-c", source], cwd=tmp_path, check=True,
                         capture_output=True, text=True)
    merged = json.loads((out / ".graphify_semantic_new.json").read_text(encoding="utf-8"))
    return merged, run.stdout


def _chunk(input_tokens, output_tokens) -> dict:
    return {"nodes": [{"id": "n", "label": "N", "file_type": "document", "source_file": "a.md"}],
            "edges": [], "hyperedges": [],
            "input_tokens": input_tokens, "output_tokens": output_tokens}


@pytest.mark.parametrize("skill", SKILLS)
def test_chunk_merge_keeps_unreported_usage_unknown(skill, tmp_path):
    merged, stdout = _merge_chunks(skill, tmp_path, [_chunk(1200, 300), _chunk(None, None)])

    assert merged["input_tokens"] is None
    assert merged["output_tokens"] is None
    assert "token usage unavailable" in stdout


@pytest.mark.parametrize("skill", SKILLS)
def test_chunk_merge_still_sums_reported_usage(skill, tmp_path):
    merged, stdout = _merge_chunks(skill, tmp_path, [_chunk(1200, 300), _chunk(800, 200)])

    assert (merged["input_tokens"], merged["output_tokens"]) == (2000, 500)
    assert "2,000 in / 500 out tokens" in stdout


def _run_cost_tracker(skill: str, cwd: Path, input_tokens, output_tokens) -> str:
    """Run the skill's cost.json update on its own, with the inputs it reads."""
    block = _python_block(skill, "# Update cumulative cost tracker")
    tracker = block[block.index("# Update cumulative cost tracker"):]
    source = (
        "import json\nfrom datetime import datetime, timezone\nfrom pathlib import Path\n"
        f"extract = {{'input_tokens': {input_tokens!r}, 'output_tokens': {output_tokens!r}}}\n"
        "detect = {'total_files': 3}\n" + tracker
    )
    return subprocess.run([sys.executable, "-c", source], cwd=cwd, check=True,
                          capture_output=True, text=True).stdout


@pytest.mark.parametrize("skill", SKILLS)
def test_cost_tracker_records_an_unmeasured_run_without_zeroing_it(skill, tmp_path):
    (tmp_path / "graphify-out").mkdir()

    _run_cost_tracker(skill, tmp_path, 1000, 250)
    stdout = _run_cost_tracker(skill, tmp_path, None, None)

    cost = json.loads((tmp_path / "graphify-out" / "cost.json").read_text(encoding="utf-8"))
    assert cost["runs"][-1]["input_tokens"] is None
    assert cost["runs"][-1]["output_tokens"] is None
    assert (cost["total_input_tokens"], cost["total_output_tokens"]) == (1000, 250)
    assert cost["unmeasured_runs"] == 1
    assert "This run: token usage unavailable" in stdout
    assert "(2 runs, 1 not measured)" in stdout


def test_report_says_unavailable_instead_of_zero():
    G, communities, cohesion, labels, gods, surprises, detection, _ = make_inputs()
    report = generate(G, communities, cohesion, labels, gods, surprises, detection,
                      {"input": None, "output": None}, "./project")

    assert "- Token cost: unavailable (the host did not report token usage)" in report
    assert "0 input" not in report


def test_report_keeps_a_real_zero_for_a_code_only_run():
    G, communities, cohesion, labels, gods, surprises, detection, _ = make_inputs()
    report = generate(G, communities, cohesion, labels, gods, surprises, detection,
                      {"input": 0, "output": 0}, "./project")

    assert "- Token cost: 0 input · 0 output" in report


def test_build_accepts_an_extraction_with_unknown_usage():
    ast = {"nodes": [{"id": "a", "label": "A", "file_type": "code", "source_file": "a.py"}],
           "edges": [], "input_tokens": 0, "output_tokens": 0}
    semantic = {"nodes": [{"id": "b", "label": "B", "file_type": "document", "source_file": "b.md"}],
                "edges": [], "input_tokens": None, "output_tokens": None}

    assert build([ast, semantic]).number_of_nodes() == 2


def test_merge_chunks_cli_keeps_unreported_usage_unknown(tmp_path):
    for i, chunk in enumerate([_chunk(1200, 300), _chunk(None, None)], 1):
        (tmp_path / f"c{i}.json").write_text(json.dumps(chunk), encoding="utf-8")
    out = tmp_path / "merged.json"

    run = subprocess.run(
        [sys.executable, "-m", "graphify", "merge-chunks", str(tmp_path / "c*.json"), "--out", str(out)],
        check=True, capture_output=True, text=True,
    )

    merged = json.loads(out.read_text(encoding="utf-8"))
    assert merged["input_tokens"] is None and merged["output_tokens"] is None
    assert "token usage unavailable" in run.stdout
