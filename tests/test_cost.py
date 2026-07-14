from __future__ import annotations

import json
import os
import stat
from concurrent.futures import ThreadPoolExecutor

import pytest

from graphify.cost import record_cost_run


def test_record_cost_run_appends_to_existing_ledger(tmp_path):
    out = tmp_path / "graphify-out"
    out.mkdir()
    original_run = {
        "date": "2026-07-01T00:00:00+00:00",
        "input_tokens": 100,
        "output_tokens": 25,
        "files": 4,
    }
    (out / "cost.json").write_text(
        json.dumps({
            "runs": [original_run],
            "total_input_tokens": 100,
            "total_output_tokens": 25,
        }),
        encoding="utf-8",
    )

    cost = record_cost_run(
        out,
        input_tokens=40,
        output_tokens=10,
        files=2,
    )

    assert cost["runs"][0] == original_run
    assert cost["runs"][1]["input_tokens"] == 40
    assert cost["runs"][1]["output_tokens"] == 10
    assert cost["runs"][1]["files"] == 2
    assert cost["runs"][1]["date"].endswith("+00:00")
    assert cost["total_input_tokens"] == 140
    assert cost["total_output_tokens"] == 35
    assert json.loads((out / "cost.json").read_text(encoding="utf-8")) == cost


def test_record_cost_run_rebuilds_missing_totals_from_history(tmp_path):
    out = tmp_path / "graphify-out"
    out.mkdir()
    (out / "cost.json").write_text(
        json.dumps({
            "runs": [{
                "date": "2026-07-01T00:00:00+00:00",
                "input_tokens": 100,
                "output_tokens": 25,
                "files": 4,
            }],
        }),
        encoding="utf-8",
    )

    cost = record_cost_run(
        out,
        input_tokens=40,
        output_tokens=10,
        files=2,
    )

    assert cost["total_input_tokens"] == 140
    assert cost["total_output_tokens"] == 35


def test_record_cost_run_preserves_ledger_when_atomic_replace_fails(
    tmp_path, monkeypatch
):
    out = tmp_path / "graphify-out"
    out.mkdir()
    cost_path = out / "cost.json"
    original = json.dumps({
        "runs": [],
        "total_input_tokens": 0,
        "total_output_tokens": 0,
    })
    cost_path.write_text(original, encoding="utf-8")

    def _replace_fails(source, destination):
        raise OSError("replace failed")

    monkeypatch.setattr("graphify.cost.os.replace", _replace_fails)

    with pytest.raises(OSError, match="replace failed"):
        record_cost_run(out, input_tokens=1, output_tokens=2, files=3)

    assert cost_path.read_text(encoding="utf-8") == original
    assert not list(out.glob(".cost.*.tmp"))


def test_record_cost_run_serializes_concurrent_writers(tmp_path):
    out = tmp_path / "graphify-out"

    def _record(_index):
        record_cost_run(out, input_tokens=3, output_tokens=2, files=1)

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(_record, range(20)))

    cost = json.loads((out / "cost.json").read_text(encoding="utf-8"))
    assert len(cost["runs"]) == 20
    assert cost["total_input_tokens"] == 60
    assert cost["total_output_tokens"] == 40


@pytest.mark.skipif(os.name == "nt", reason="POSIX permission bits")
def test_record_cost_run_preserves_existing_permissions(tmp_path):
    out = tmp_path / "graphify-out"
    out.mkdir()
    cost_path = out / "cost.json"
    cost_path.write_text(
        json.dumps({
            "runs": [],
            "total_input_tokens": 0,
            "total_output_tokens": 0,
        }),
        encoding="utf-8",
    )
    cost_path.chmod(0o640)

    record_cost_run(out, input_tokens=1, output_tokens=2, files=3)

    assert stat.S_IMODE(cost_path.stat().st_mode) == 0o640


@pytest.mark.skipif(os.name == "nt", reason="POSIX umask semantics")
def test_record_cost_run_respects_umask_for_new_ledger(tmp_path):
    out = tmp_path / "graphify-out"
    old_umask = os.umask(0o027)
    try:
        record_cost_run(out, input_tokens=1, output_tokens=2, files=3)
    finally:
        os.umask(old_umask)

    assert stat.S_IMODE((out / "cost.json").stat().st_mode) == 0o640
