"""Extraction coverage for cobol."""


from __future__ import annotations





import sys


from pathlib import Path





from graphify.extract import extract





FIXTURE = Path(__file__).parent / "fixtures" / "new_languages" / "sample.cob"





def _edge_labels(result: dict, relation: str) -> set[tuple[str, str]]:
    labels = {node["id"]: node["label"] for node in result["nodes"]}
    return {
        (labels.get(edge["source"], edge["source"]), labels.get(edge["target"], edge["target"]))
        for edge in result["edges"]
        if edge["relation"] == relation
    }


def test_cobol_program_paragraphs_and_perform_calls(tmp_path):
    source = tmp_path / "demo.cbl"
    source.write_text(
        "       IDENTIFICATION DIVISION.\n"
        "       PROGRAM-ID. DEMO.\n"
        "       PROCEDURE DIVISION.\n"
        "       MAIN-PARA.\n"
        "           PERFORM WORK-PARA.\n"
        "           STOP RUN.\n"
        "       WORK-PARA.\n"
        "           DISPLAY 'ok'.\n",
        encoding="utf-8",
    )

    result = extract([source], cache_root=tmp_path)

    labels = {node["label"] for node in result["nodes"]}
    assert {"DEMO", "MAIN-PARA", "WORK-PARA"} <= labels
    assert ("MAIN-PARA", "WORK-PARA") in _edge_labels(result, "calls")


def test_cobol_fixed_free_copy_call_and_exec_blocks(tmp_path):
    copybook = tmp_path / "CUSTOMER.cpy"
    copybook.write_text(
        "       01  CUSTOMER-RECORD.\n"
        "       05  CUSTOMER-\n"
        "      -    NAME PIC X(20).\n",
        encoding="utf-8",
    )
    subprogram = tmp_path / "subprog.cbl"
    subprogram.write_text(
        "       IDENTIFICATION DIVISION.\n"
        "       PROGRAM-ID. SUBPROG.\n"
        "       PROCEDURE DIVISION.\n"
        "       ENTRY-PARA.\n"
        "           GOBACK.\n",
        encoding="utf-8",
    )
    source = tmp_path / "main.cob"
    source.write_text(
        ">>SOURCE FORMAT FREE\n"
        "IDENTIFICATION DIVISION.\n"
        "PROGRAM-ID. MAINPROG.\n"
        "DATA DIVISION.\n"
        "WORKING-STORAGE SECTION.\n"
        "01 TARGET-NAME PIC X(8).\n"
        "COPY CUSTOMER REPLACING ==CUSTOMER-RECORD== BY ==CLIENT-RECORD==.\n"
        "PROCEDURE DIVISION.\n"
        "MAIN-PARA.\n"
        "    PERFORM WORK-PARA.\n"
        "    CALL 'SUBPROG'.\n"
        "    CALL TARGET-NAME.\n"
        "    EXEC CICS\n"
        "      CALL 'FAKE'\n"
        "    END-EXEC.\n"
        "WORK-PARA SECTION.\n"
        "    DISPLAY \"PERFORM FAKE-PARA\".\n"
        "    DISPLAY \"CALL 'SUBPROG'\".\n"
        "    STOP RUN.\n",
        encoding="utf-8",
    )

    result = extract([source, subprogram, copybook], cache_root=tmp_path)

    labels = {node["label"] for node in result["nodes"]}
    assert {
        "MAINPROG", "SUBPROG", "MAIN-PARA", "WORK-PARA", "TARGET-NAME",
        "CUSTOMER-RECORD", "CUSTOMER-NAME",
    } <= labels
    calls = _edge_labels(result, "calls")
    assert ("MAIN-PARA", "WORK-PARA") in calls
    assert ("MAIN-PARA", "SUBPROG") in calls
    assert ("WORK-PARA", "SUBPROG") not in calls
    assert all(target != "FAKE" for _, target in calls)
    assert any(edge["relation"] == "imports_from" for edge in result["edges"])


def test_cobol_fixture_uses_normal_extract_path(tmp_path):
    result = extract([FIXTURE], cache_root=tmp_path)

    labels = {node["label"] for node in result["nodes"]}
    assert {'SAMPLE', 'HELPER-PARA', 'MAIN-PARA'} <= labels
    assert ('MAIN-PARA', 'HELPER-PARA') in _edge_labels(result, "calls")


def test_cobol_malformed_tail_comments_and_strings_do_not_create_phantoms(tmp_path):
    source = tmp_path / 'broken.cbl'
    source.write_text("       IDENTIFICATION DIVISION.\n       PROGRAM-ID. KEPT.\n       PROCEDURE DIVISION.\n       MAIN.\n           DISPLAY 'PERFORM GHOST'.\n", encoding="utf-8")

    result = extract([source], cache_root=tmp_path)

    labels = {node["label"].casefold() for node in result["nodes"]}
    assert 'kept' in labels
    assert labels.isdisjoint({'ghost'})


def test_cobol_fixed_format_with_sequence_numbers(tmp_path):
    """Legacy fixed-format source carries a sequence NUMBER in columns 1-6, not
    blanks. The format detector required six blank columns, so a sequence-numbered
    file was misread as free-format — the sequence number stayed in the code and
    every paragraph (its `^NAME.$` anchor no longer matched) and PERFORM edge was
    lost, leaving only the file and program nodes."""
    source = tmp_path / "legacy.cob"
    source.write_text(
        "000100 IDENTIFICATION DIVISION.\n"
        "000200 PROGRAM-ID. PAYROLL.\n"
        "000300 PROCEDURE DIVISION.\n"
        "000400 MAIN-PARA.\n"
        "000500     PERFORM INIT-PARA.\n"
        "000600 INIT-PARA.\n"
        "000700     DISPLAY 'HELLO'.\n",
        encoding="utf-8",
    )

    result = extract([source], cache_root=tmp_path)

    labels = {node["label"] for node in result["nodes"]}
    assert {"PAYROLL", "MAIN-PARA", "INIT-PARA"} <= labels
    assert ("MAIN-PARA", "INIT-PARA") in _edge_labels(result, "calls")


def test_cobol_perform_thru_links_both_range_endpoints(tmp_path):
    """`PERFORM A THRU Z` runs the range A..Z, so both endpoints are performed.
    Only the entry paragraph was linked before, leaving the range-end with no
    inbound `calls` edge."""
    source = tmp_path / "range.cbl"
    source.write_text(
        "       IDENTIFICATION DIVISION.\n"
        "       PROGRAM-ID. RANGE.\n"
        "       PROCEDURE DIVISION.\n"
        "       MAIN-PARA.\n"
        "           PERFORM A-PARA THRU Z-PARA.\n"
        "       A-PARA.\n"
        "           DISPLAY 'A'.\n"
        "       Z-PARA.\n"
        "           DISPLAY 'Z'.\n",
        encoding="utf-8",
    )

    result = extract([source], cache_root=tmp_path)

    calls = _edge_labels(result, "calls")
    assert ("MAIN-PARA", "A-PARA") in calls
    assert ("MAIN-PARA", "Z-PARA") in calls
