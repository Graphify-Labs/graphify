"""Tests for cost.json persistence and token observability (#3658).

Verifies the ledger invariant:
- 0 is an explicitly observed measurement
- None/null is unobserved/undetermined
- unobserved tokens do not break arithmetic or formatting
- has_unrecorded_usage flag is preserved once true
"""
import json
from datetime import datetime, timezone
from pathlib import Path


def update_cost_ledger(cost_path: Path, raw_in, raw_out, total_files: int = 0) -> dict:
    """Implements Step 9 cost persistence logic."""
    input_tok = int(raw_in) if isinstance(raw_in, (int, float)) and not isinstance(raw_in, bool) else None
    output_tok = int(raw_out) if isinstance(raw_out, (int, float)) and not isinstance(raw_out, bool) else None

    if cost_path.exists():
        cost = json.loads(cost_path.read_text(encoding="utf-8"))
    else:
        cost = {"runs": [], "total_input_tokens": 0, "total_output_tokens": 0, "has_unrecorded_usage": False}

    cost["runs"].append({
        "date": datetime.now(timezone.utc).isoformat(),
        "input_tokens": input_tok,
        "output_tokens": output_tok,
        "files": total_files,
    })
    if input_tok is not None:
        cost["total_input_tokens"] += input_tok
    if output_tok is not None:
        cost["total_output_tokens"] += output_tok

    cost["has_unrecorded_usage"] = bool(cost.get("has_unrecorded_usage")) or (input_tok is None) or (output_tok is None) or any(
        r.get("input_tokens") is None or r.get("output_tokens") is None for r in cost.get("runs", [])
    )

    cost_path.write_text(json.dumps(cost, indent=2, ensure_ascii=False), encoding="utf-8")
    return cost


def test_cost_persistence_unobserved_input(tmp_path):
    cost_file = tmp_path / "cost.json"

    # Run 1: input=None, output=62833
    cost1 = update_cost_ledger(cost_file, None, 62833, total_files=44)

    # Stored JSON check
    raw_json = json.loads(cost_file.read_text(encoding="utf-8"))
    assert raw_json["runs"][0]["input_tokens"] is None
    assert raw_json["runs"][0]["output_tokens"] == 62833
    assert raw_json["total_input_tokens"] == 0
    assert raw_json["total_output_tokens"] == 62833
    assert raw_json["has_unrecorded_usage"] is True

    # Run 2: fully-observed run input=1000, output=2000
    cost2 = update_cost_ledger(cost_file, 1000, 2000, total_files=10)
    raw_json2 = json.loads(cost_file.read_text(encoding="utf-8"))

    assert len(raw_json2["runs"]) == 2
    assert raw_json2["runs"][1]["input_tokens"] == 1000
    assert raw_json2["runs"][1]["output_tokens"] == 2000
    assert raw_json2["total_input_tokens"] == 1000
    assert raw_json2["total_output_tokens"] == 64833
    # Critical: historical unrecorded run prevents resetting has_unrecorded_usage to False
    assert raw_json2["has_unrecorded_usage"] is True


def test_cost_persistence_historical_ledger_without_flag(tmp_path):
    """If cost.json predates has_unrecorded_usage but has nulls, the flag becomes True."""
    cost_file = tmp_path / "cost.json"
    legacy = {
        "runs": [
            {"date": "2026-06-09T20:34:51.846794+00:00", "input_tokens": None, "output_tokens": 62833, "files": 44}
        ],
        "total_input_tokens": 0,
        "total_output_tokens": 62833,
    }
    cost_file.write_text(json.dumps(legacy), encoding="utf-8")

    update_cost_ledger(cost_file, 500, 500, total_files=12)
    updated = json.loads(cost_file.read_text(encoding="utf-8"))
    assert updated["has_unrecorded_usage"] is True
    assert updated["total_input_tokens"] == 500
    assert updated["total_output_tokens"] == 63333


def test_cost_persistence_booleans_rejected(tmp_path):
    """Booleans must not be treated as integer token counts."""
    cost_file = tmp_path / "cost.json"
    update_cost_ledger(cost_file, True, False, total_files=5)
    data = json.loads(cost_file.read_text(encoding="utf-8"))
    assert data["runs"][0]["input_tokens"] is None
    assert data["runs"][0]["output_tokens"] is None
    assert data["total_input_tokens"] == 0
    assert data["total_output_tokens"] == 0
    assert data["has_unrecorded_usage"] is True
