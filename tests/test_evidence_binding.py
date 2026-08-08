"""Tests for semantic evidence-binding in graphify.llm.

A code node the model returns whose symbol name has no evidence in the dispatched
source is flagged ``verification = "unverified"`` (never dropped). This closes
the intra-file hallucination gap that ``_out_of_scope`` (#1895) — which only
rejects nodes attributed to a file that was NOT dispatched — cannot see.
"""

from pathlib import Path
from unittest.mock import patch

from graphify import llm


_SOURCE = (
    "def real_function():\n"
    "    return PaymentProcessor().charge_card()\n"
    "\n"
    "class PaymentProcessor:\n"
    "    def charge_card(self):\n"
    "        pass\n"
)


def _run(files, nodes, tmp_path):
    """Drive extract_files_direct with a faked backend returning ``nodes``."""
    result = {
        "nodes": nodes,
        "edges": [],
        "hyperedges": [],
        "input_tokens": 1,
        "output_tokens": 1,
        "finish_reason": "stop",
    }
    with patch("graphify.llm._call_openai_compat", return_value=result):
        return llm.extract_files_direct(files, backend="kimi", api_key="k", root=tmp_path)


def _by_label(out):
    return {n["label"]: n for n in out["nodes"]}


def test_fabricated_code_symbol_is_downgraded(tmp_path):
    src = tmp_path / "mod.py"
    src.write_text(_SOURCE, encoding="utf-8")
    nodes = [
        {"id": "a", "label": "real_function()", "file_type": "code", "source_file": "mod.py"},
        {"id": "b", "label": "totally_fabricated_symbol()", "file_type": "code", "source_file": "mod.py"},
        {"id": "c", "label": "Payments Overview", "file_type": "concept", "source_file": "mod.py"},
    ]
    out = _by_label(_run([src], nodes, tmp_path))
    # The fabricated symbol has no evidence in the source -> flagged.
    assert out["totally_fabricated_symbol()"]["verification"] == "unverified"
    # A symbol that IS in the source is verified -> untouched (no confidence key).
    assert "verification" not in out["real_function()"]
    # A concept node is prose, never checked.
    assert "verification" not in out["Payments Overview"]


def test_qualified_and_prettified_labels_do_not_false_positive(tmp_path):
    src = tmp_path / "mod.py"
    src.write_text(_SOURCE, encoding="utf-8")
    nodes = [
        {"id": "a", "label": "PaymentProcessor.charge_card()", "file_type": "code", "source_file": "mod.py"},
        {"id": "b", "label": "charge_card(amount, token)", "file_type": "code", "source_file": "mod.py"},
    ]
    out = _by_label(_run([src], nodes, tmp_path))
    # Any label identifier present in the source verifies the whole label.
    assert "verification" not in out["PaymentProcessor.charge_card()"]
    assert "verification" not in out["charge_card(amount, token)"]


def test_document_and_sourceless_nodes_are_never_flagged(tmp_path):
    src = tmp_path / "mod.py"
    src.write_text(_SOURCE, encoding="utf-8")
    nodes = [
        {"id": "a", "label": "Nonexistent Heading", "file_type": "document", "source_file": "mod.py"},
        {"id": "b", "label": "orphan_symbol()", "file_type": "code"},  # no source_file
    ]
    out = _by_label(_run([src], nodes, tmp_path))
    assert "verification" not in out["Nonexistent Heading"]
    assert "verification" not in out["orphan_symbol()"]


def test_node_attributed_to_undispatched_file_is_left_to_out_of_scope(tmp_path):
    src = tmp_path / "mod.py"
    src.write_text(_SOURCE, encoding="utf-8")
    # other.py exists on disk but is NOT dispatched in this call.
    (tmp_path / "other.py").write_text("def elsewhere():\n    pass\n", encoding="utf-8")
    nodes = [
        {"id": "a", "label": "ghost_func()", "file_type": "code", "source_file": "other.py"},
    ]
    out = _by_label(_run([src], nodes, tmp_path))
    # Not in the dispatched set -> #1895's domain, not evidence-binding's.
    assert "verification" not in out["ghost_func()"]


def test_uncheckable_short_label_is_not_flagged(tmp_path):
    src = tmp_path / "mod.py"
    src.write_text(_SOURCE, encoding="utf-8")
    nodes = [
        {"id": "a", "label": "id()", "file_type": "code", "source_file": "mod.py"},
    ]
    out = _by_label(_run([src], nodes, tmp_path))
    # "id" is < 3 chars, so there is no checkable identifier -> leave as-is.
    assert "verification" not in out["id()"]


def test_existing_lower_confidence_is_not_overwritten(tmp_path):
    src = tmp_path / "mod.py"
    src.write_text(_SOURCE, encoding="utf-8")
    nodes = [
        {"id": "a", "label": "made_up()", "file_type": "code", "source_file": "mod.py", "confidence": "INFERRED"},
    ]
    out = _by_label(_run([src], nodes, tmp_path))
    # The model already hedged it (INFERRED); evidence-binding leaves it entirely
    # alone — no verification flag added, and its confidence is never clobbered.
    assert out["made_up()"]["confidence"] == "INFERRED"
    assert "verification" not in out["made_up()"]


def test_label_identifiers_helper():
    assert llm._label_identifiers("foo()") == ["foo"]
    assert llm._label_identifiers("Cls.method(x)") == ["Cls", "method"]
    assert llm._label_identifiers("id()") == []  # all tokens < 3 chars
    assert llm._label_identifiers("") == []


def test_bind_node_evidence_returns_downgrade_count(tmp_path):
    src = tmp_path / "mod.py"
    src.write_text(_SOURCE, encoding="utf-8")
    result = {
        "nodes": [
            {"id": "a", "label": "real_function()", "file_type": "code", "source_file": "mod.py"},
            {"id": "b", "label": "fake_one()", "file_type": "code", "source_file": "mod.py"},
            {"id": "c", "label": "fake_two()", "file_type": "code", "source_file": "mod.py"},
        ],
    }
    downgraded = llm._bind_node_evidence(result, [src], tmp_path)
    assert downgraded == 2


def test_evidence_binding_handles_file_slice(tmp_path):
    # A slice reports its PARENT file as source_file; verification runs against
    # the slice bytes the model actually saw.
    from graphify.file_slice import FileSlice

    src = tmp_path / "big.md"
    src.write_text("intro\n" + _SOURCE + "\ntail\n", encoding="utf-8")
    text = src.read_text()
    fs = FileSlice(path=src, start=0, end=len(text), index=0, total=1)
    result = {
        "nodes": [
            {"id": "a", "label": "real_function()", "file_type": "code", "source_file": "big.md"},
            {"id": "b", "label": "ghost_symbol()", "file_type": "code", "source_file": "big.md"},
        ],
    }
    n = llm._bind_node_evidence(result, [fs], tmp_path)
    by = {x["label"]: x for x in result["nodes"]}
    assert n == 1
    assert "verification" not in by["real_function()"]
    assert by["ghost_symbol()"]["verification"] == "unverified"


def test_evidence_binding_handles_absolute_source_file(tmp_path):
    src = tmp_path / "mod.py"
    src.write_text(_SOURCE, encoding="utf-8")
    # Model returns an absolute source_file rather than a root-relative one.
    result = {"nodes": [
        {"id": "a", "label": "ghost_symbol()", "file_type": "code", "source_file": str(src)},
    ]}
    n = llm._bind_node_evidence(result, [src], tmp_path)
    assert n == 1
    assert result["nodes"][0]["verification"] == "unverified"


def test_downgrade_emits_stderr_summary(tmp_path, capsys):
    src = tmp_path / "mod.py"
    src.write_text(_SOURCE, encoding="utf-8")
    nodes = [{"id": "b", "label": "totally_made_up_symbol()", "file_type": "code", "source_file": "mod.py"}]
    _run([src], nodes, tmp_path)
    err = capsys.readouterr().err
    assert "unverified" in err


def test_unverified_flag_does_not_fail_validation():
    # The flag lives on its own ``verification`` field, deliberately NOT on the
    # validated ``confidence`` key (whose vocabulary is edge-only), so it must
    # never make an otherwise-valid node fail validation.
    from graphify.validate import validate_extraction

    extraction = {
        "nodes": [{"id": "n1", "label": "foo", "file_type": "code",
                   "source_file": "a.md", "verification": "unverified"}],
        "edges": [],
    }
    errors = validate_extraction(extraction)
    assert not any("verification" in str(e).lower() for e in errors)


def test_diagnostics_reports_unverified_node_count():
    # The consumer: diagnose_extraction surfaces the persisted verification flag
    # so it is not a dead field.
    from graphify.diagnostics import diagnose_extraction, format_diagnostic_report

    extraction = {
        "nodes": [
            {"id": "n1", "label": "ghost", "file_type": "code",
             "source_file": "a.md", "verification": "unverified"},
            {"id": "n2", "label": "real", "file_type": "code", "source_file": "a.md"},
        ],
        "edges": [],
    }
    summary = diagnose_extraction(extraction)
    assert summary["unverified_node_count"] == 1
    assert "unverified_code_nodes: 1" in format_diagnostic_report(summary)
