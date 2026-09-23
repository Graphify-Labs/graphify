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
