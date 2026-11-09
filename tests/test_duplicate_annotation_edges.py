"""Exact-duplicate edge emission from repeated annotations (#3251).

A signature that annotates the same type twice (``def f(a: Path, b: Path)``)
used to emit one identical ``references`` edge per occurrence — same source,
target, relation, source_location and context. build() drops the copy, but
diagnose_extraction first counts it under ``exact_duplicate_edges`` and the
run ends with an unexplained GRAPH HEALTH WARNING. Duplicates now collapse at
extraction; anything differing in any field still survives.
"""

import collections

from graphify.diagnostics import diagnose_extraction
from graphify.extract import extract


def _edge_counts(result):
    return collections.Counter(
        (e["source"], e["target"], e["relation"],
         e.get("source_location"), e.get("context"))
        for e in result["edges"]
    )


def test_python_repeated_parameter_annotation_emits_one_edge(tmp_path, monkeypatch):
    """The issue's exact repro: two same-typed params, one references edge."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "sample.py").write_text(
        "from pathlib import Path\n\n\n"
        "def two_params(a: Path, b: Path) -> None:\n"
        "    print(a, b)\n\n\n"
        "def one_param(a: Path) -> None:\n"
        "    print(a)\n",
        encoding="utf-8",
    )
    r = extract([tmp_path / "sample.py"], cache_root=tmp_path)
    counts = _edge_counts(r)
    dupes = {k: v for k, v in counts.items() if v > 1}
    assert dupes == {}, f"exact duplicate edges emitted: {dupes}"
    assert counts[("sample_two_params", "path", "references",
                   "L4", "parameter_type")] == 1
    assert counts[("sample_one_param", "path", "references",
                   "L8", "parameter_type")] == 1


def test_csharp_repeated_parameter_annotation_emits_one_edge(tmp_path, monkeypatch):
    """The same disease exists in every language block — C# as the witness."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "Svc.cs").write_text(
        "public class Svc {\n"
        "    public void Copy(Widget a, Widget b) { }\n"
        "}\n"
        "public class Widget { }\n",
        encoding="utf-8",
    )
    r = extract([tmp_path / "Svc.cs"], cache_root=tmp_path)
    dupes = {k: v for k, v in _edge_counts(r).items() if v > 1}
    assert dupes == {}, f"exact duplicate edges emitted: {dupes}"


def test_diagnose_reports_zero_exact_duplicates(tmp_path, monkeypatch):
    """The health warning the issue hit is gone at the source."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "sample.py").write_text(
        "from pathlib import Path\n\n\n"
        "def two_params(a: Path, b: Path) -> None:\n"
        "    print(a, b)\n",
        encoding="utf-8",
    )
    r = extract([tmp_path / "sample.py"], cache_root=tmp_path)
    summary = diagnose_extraction(r)
    assert summary["exact_duplicate_edges"] == 0


def test_differing_locations_and_contexts_survive(tmp_path, monkeypatch):
    """Only byte-identical edges collapse: the same type referenced at two
    locations, or under two contexts at one location, keeps every edge."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "sample.py").write_text(
        "from pathlib import Path\n\n\n"
        "def alpha(a: Path) -> None:\n"
        "    print(a)\n\n\n"
        "def beta(b: Path) -> Path:\n"
        "    return b\n",
        encoding="utf-8",
    )
    r = extract([tmp_path / "sample.py"], cache_root=tmp_path)
    counts = _edge_counts(r)
    # Two locations → two edges.
    assert counts[("sample_alpha", "path", "references", "L4", "parameter_type")] == 1
    assert counts[("sample_beta", "path", "references", "L8", "parameter_type")] == 1
    # Same location, different context (parameter vs return) → both edges.
    assert counts[("sample_beta", "path", "references", "L8", "return_type")] == 1
