from __future__ import annotations

import json

from graphify.trust import evaluate_navigation_trust, main, render_markdown


PASSING_CAPABILITIES = {
    "internal_import_resolution": {"status": "PASS", "evidence": "12/12 resolved"},
    "lexical_inferred_ownership": {"status": "PASS", "evidence": "6/6 owners matched"},
    "artifact_freshness": {"status": "PASS", "evidence": "built at HEAD"},
}


def test_navigation_trust_requires_every_capability_to_pass() -> None:
    report = evaluate_navigation_trust(PASSING_CAPABILITIES)

    assert report["status"] == "TRUSTED"
    assert [row["status"] for row in report["capabilities"]] == ["PASS", "PASS", "PASS"]


def test_navigation_trust_fails_closed_for_failed_or_missing_capabilities() -> None:
    failing = dict(PASSING_CAPABILITIES)
    failing["lexical_inferred_ownership"] = {"status": "FAIL", "evidence": "owner mismatch"}

    failed_report = evaluate_navigation_trust(failing)
    missing_report = evaluate_navigation_trust({"internal_import_resolution": {"status": "PASS"}})

    assert failed_report["status"] == "UNTRUSTED"
    assert missing_report["status"] == "UNTRUSTED"
    assert [row["status"] for row in missing_report["capabilities"]] == [
        "PASS",
        "MISSING",
        "MISSING",
    ]


def test_navigation_trust_markdown_keeps_rows_diagnostic() -> None:
    capabilities = dict(PASSING_CAPABILITIES)
    capabilities["artifact_freshness"] = {"status": "FAIL", "evidence": "source advanced"}

    rendered = render_markdown(evaluate_navigation_trust(capabilities))

    assert "**Overall: UNTRUSTED**" in rendered
    assert "| Artifact freshness | FAIL | source advanced |" in rendered
    assert "| Internal import resolution | PASS | 12/12 resolved |" in rendered


def test_navigation_trust_cli_writes_report_and_returns_nonzero_when_untrusted(
    tmp_path,
) -> None:
    evidence_path = tmp_path / "evidence.json"
    json_path = tmp_path / "trust.json"
    markdown_path = tmp_path / "TRUST.md"
    evidence_path.write_text(
        json.dumps({"capabilities": {"internal_import_resolution": {"status": "PASS"}}}),
        encoding="utf-8",
    )

    exit_code = main(
        [
            str(evidence_path),
            "--json-out",
            str(json_path),
            "--markdown-out",
            str(markdown_path),
        ]
    )

    assert exit_code == 1
    assert json.loads(json_path.read_text(encoding="utf-8"))["status"] == "UNTRUSTED"
    assert "**Overall: UNTRUSTED**" in markdown_path.read_text(encoding="utf-8")
