"""Extraction coverage for cobol."""


from __future__ import annotations





import sys


from pathlib import Path





import pytest

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


def _go_to_edges(result: dict) -> set[tuple[str, str]]:
    labels = {node["id"]: node["label"] for node in result["nodes"]}
    return {
        (labels.get(edge["source"], edge["source"]), labels.get(edge["target"], edge["target"]))
        for edge in result["edges"]
        if edge["relation"] == "calls" and edge.get("context") == "go_to"
    }


def test_cobol_go_to_links_the_paragraph_it_jumps_to(tmp_path):
    """`GO TO X` transfers control to X. No edge was emitted for it, so a
    paragraph reached only by a jump had no inbound edge at all."""
    source = tmp_path / "jump.cbl"
    source.write_text(
        "       IDENTIFICATION DIVISION.\n"
        "       PROGRAM-ID. JUMP.\n"
        "       PROCEDURE DIVISION.\n"
        "       MAIN-PARA.\n"
        "           IF WS-EOF = 'Y'\n"
        "               GO TO EXIT-PARA.\n"
        "           PERFORM WORK-PARA.\n"
        "       WORK-PARA.\n"
        "           DISPLAY 'GO TO NOWHERE-PARA'.\n"
        "       NOWHERE-PARA.\n"
        "           DISPLAY 'not a jump target'.\n"
        "       EXIT-PARA.\n"
        "           STOP RUN.\n",
        encoding="utf-8",
    )

    result = extract([source], cache_root=tmp_path)

    assert _go_to_edges(result) == {("MAIN-PARA", "EXIT-PARA")}
    # The jump is told apart from a PERFORM by its context, not by a new relation.
    calls = _edge_labels(result, "calls")
    assert ("MAIN-PARA", "EXIT-PARA") in calls
    assert ("MAIN-PARA", "WORK-PARA") in calls
    assert ("MAIN-PARA", "WORK-PARA") not in _go_to_edges(result)


def test_cobol_go_to_depending_on_links_every_listed_target_only(tmp_path):
    """`GO TO A B C DEPENDING ON X` can reach A, B and C. X is a data name, and
    in `A OF SEC` the section only qualifies A: neither is a target."""
    source = tmp_path / "switch.cbl"
    source.write_text(
        "       IDENTIFICATION DIVISION.\n"
        "       PROGRAM-ID. SWITCH.\n"
        "       PROCEDURE DIVISION.\n"
        "       MAIN-PARA.\n"
        "           GO TO A-PARA, B-PARA C-PARA DEPENDING ON CHOICE.\n"
        "       OTHER-PARA.\n"
        "           GO TO A-PARA OF LAST-SEC.\n"
        "       QUALIFIED-PARA.\n"
        "           GO TO B-PARA OF LAST-SEC, C-PARA DEPENDING ON CHOICE.\n"
        "       A-PARA.\n"
        "           DISPLAY 'A'.\n"
        "       B-PARA.\n"
        "           DISPLAY 'B'.\n"
        "       C-PARA.\n"
        "           DISPLAY 'C'.\n"
        "       CHOICE.\n"
        "           DISPLAY 'shares its name with the data item'.\n"
        "       LAST-SEC SECTION.\n"
        "       LAST-PARA.\n"
        "           STOP RUN.\n",
        encoding="utf-8",
    )

    result = extract([source], cache_root=tmp_path)

    assert _go_to_edges(result) == {
        ("MAIN-PARA", "A-PARA"),
        ("MAIN-PARA", "B-PARA"),
        ("MAIN-PARA", "C-PARA"),
        ("OTHER-PARA", "A-PARA"),
        ("QUALIFIED-PARA", "B-PARA"),
        ("QUALIFIED-PARA", "C-PARA"),
    }


def test_cobol_go_to_without_depending_has_one_target(tmp_path):
    """A plain `GO TO A` jumps to A alone. The words after it belong to the
    next statement, and one of them can be the name of a paragraph: every word
    up to the end of the line was read as a target."""
    source = tmp_path / "single.cbl"
    source.write_text(
        "       IDENTIFICATION DIVISION.\n"
        "       PROGRAM-ID. SINGLE.\n"
        "       PROCEDURE DIVISION.\n"
        "       MAIN-PARA.\n"
        "           IF WS-A = 1 GO TO ERR-PARA ELSE SET CHOICE TO TRUE.\n"
        "           IF WS-A = 2 GO TO ERR-PARA ELSE GO TO LAST-PARA.\n"
        "       ERR-PARA.\n"
        "           STOP RUN.\n"
        "       CHOICE.\n"
        "           DISPLAY 'shares its name with the data item'.\n"
        "       LAST-PARA.\n"
        "           STOP RUN.\n",
        encoding="utf-8",
    )

    result = extract([source], cache_root=tmp_path)

    assert _go_to_edges(result) == {
        ("MAIN-PARA", "ERR-PARA"),
        ("MAIN-PARA", "LAST-PARA"),
    }


def test_cobol_procedure_copybook_without_division_header_has_paragraphs(tmp_path):
    """A copybook of procedure code is pasted into the PROCEDURE DIVISION of the
    program that copies it, so it has no such header of its own. It was read as
    data from top to bottom: no paragraph, no PERFORM edge."""
    copybook = tmp_path / "ERRORS.cpy"
    copybook.write_text(
        "      * error handling, copied into the procedure division\n"
        "       ERR-CHECK.\n"
        "           IF WS-STATUS NOT = '00'\n"
        "               PERFORM ERR-REPORT\n"
        "           END-IF.\n"
        "       ERR-REPORT.\n"
        "           EXEC CICS\n"
        "               PERFORM NOT-A-PARA\n"
        "           END-EXEC.\n"
        "           DISPLAY 'status ' WS-STATUS.\n",
        encoding="utf-8",
    )

    result = extract([copybook], cache_root=tmp_path)

    kinds = {node["label"]: node["metadata"]["kind"] for node in result["nodes"]}
    assert kinds == {
        "ERRORS.cpy": "file", "ERR-CHECK": "paragraph", "ERR-REPORT": "paragraph",
    }
    assert _edge_labels(result, "calls") == {("ERR-CHECK", "ERR-REPORT")}
    assert _edge_labels(result, "contains") == {
        ("ERRORS.cpy", "ERR-CHECK"), ("ERRORS.cpy", "ERR-REPORT"),
    }


def test_cobol_data_copybook_is_still_read_as_data(tmp_path):
    """A data copybook has no statements, so a lone `NAME.` line in it (a VALUE
    clause that runs on to the next line) is not a paragraph, and the items
    after it are still data items."""
    copybook = tmp_path / "RECORD.cpy"
    copybook.write_text(
        "       01  WS-RECORD.\n"
        "           05  WS-FILL             PIC X(10) VALUE\n"
        "               SPACES.\n"
        "           05  WS-STATUS           PIC XX.\n",
        encoding="utf-8",
    )

    result = extract([copybook], cache_root=tmp_path)

    kinds = {node["label"]: node["metadata"]["kind"] for node in result["nodes"]}
    assert kinds == {
        "RECORD.cpy": "file", "WS-RECORD": "data_item", "WS-FILL": "data_item",
        "WS-STATUS": "data_item",
    }


def _program(name: str, *body: str) -> str:
    return "".join(
        f"       {line}\n"
        for line in ("IDENTIFICATION DIVISION.", f"PROGRAM-ID. {name}.", "PROCEDURE DIVISION.", *body)
    )


def _copybook(*body: str) -> str:
    return "".join(f"       {line}\n" for line in body)


def _copybook_performs(result: dict) -> set[tuple[str, str]]:
    """(caller, target) of every cross-file PERFORM edge, each end as `file:LABEL`."""
    names = {
        node["id"]: f"{Path(node['source_file']).name}:{node['label']}"
        for node in result["nodes"]
        if node.get("source_file")
    }
    return {
        (names[edge["source"]], names[edge["target"]])
        for edge in result["edges"]
        if edge["relation"] == "calls" and edge.get("context") == "copybook_perform"
    }


def test_cobol_perform_resolves_between_a_program_and_its_copybook(tmp_path):
    """A copybook is pasted into the program that copies it, so a PERFORM can
    name a paragraph in the other file, in either direction. Each file was
    resolved on its own, so both PERFORMs were dropped."""
    program = tmp_path / "billing.cbl"
    program.write_text(_program(
        "BILLING",
        "MAIN-PARA.",
        "    PERFORM ERR-CHECK.",
        "    STOP RUN.",
        "CLEANUP.",
        "    DISPLAY 'cleanup'.",
        "COPY ERRORS.",
    ), encoding="utf-8")
    copybook = tmp_path / "ERRORS.cpy"
    copybook.write_text(_copybook(
        "ERR-CHECK.",
        "    PERFORM CLEANUP.",
    ), encoding="utf-8")

    result = extract([program, copybook], cache_root=tmp_path)

    assert _copybook_performs(result) == {
        ("billing.cbl:MAIN-PARA", "ERRORS.cpy:ERR-CHECK"),
        ("ERRORS.cpy:ERR-CHECK", "billing.cbl:CLEANUP"),
    }
    # The second run reads both files from the AST cache; the unresolved
    # PERFORMs must come back with them.
    cached = extract([program, copybook], cache_root=tmp_path)
    assert _copybook_performs(cached) == _copybook_performs(result)


def test_cobol_perform_is_not_matched_by_name_across_programs(tmp_path):
    """A paragraph name is visible only inside its own program. A program that
    does not copy the copybook gets no edge to its paragraph, nor to a
    same-named paragraph of another program."""
    copier = tmp_path / "copier.cbl"
    copier.write_text(_program(
        "COPIER", "MAIN-PARA.", "    PERFORM ERR-CHECK.", "COPY ERRORS.",
    ), encoding="utf-8")
    stranger = tmp_path / "stranger.cbl"
    stranger.write_text(_program(
        "STRANGER", "MAIN-PARA.", "    PERFORM ERR-CHECK.", "    PERFORM ONLY-HERE.",
    ), encoding="utf-8")
    other = tmp_path / "other.cbl"
    other.write_text(_program(
        "OTHER", "ONLY-HERE.", "    DISPLAY 'in another program'.",
    ), encoding="utf-8")
    copybook = tmp_path / "ERRORS.cpy"
    copybook.write_text(_copybook("ERR-CHECK.", "    DISPLAY 'error'."), encoding="utf-8")

    result = extract([copier, stranger, other, copybook], cache_root=tmp_path)

    assert _copybook_performs(result) == {
        ("copier.cbl:MAIN-PARA", "ERRORS.cpy:ERR-CHECK"),
    }
    names = {node["id"]: node["label"] for node in result["nodes"]}
    stranger_calls = {
        names.get(edge["target"])
        for edge in result["edges"]
        if edge["relation"] == "calls" and edge["source_file"].endswith("stranger.cbl")
    }
    assert stranger_calls == set()


def test_cobol_shared_copybook_performs_into_each_program_that_copies_it(tmp_path):
    """A copybook two programs copy is part of both, so its PERFORM of a
    paragraph each program defines gets an edge into each."""
    for name in ("ALPHA", "BETA"):
        (tmp_path / f"{name.lower()}.cbl").write_text(_program(
            name, "MAIN-PARA.", "    PERFORM SHARED-STEP.", "CLEANUP.", "    EXIT.", "COPY SHARED.",
        ), encoding="utf-8")
    copybook = tmp_path / "SHARED.cpy"
    copybook.write_text(_copybook("SHARED-STEP.", "    PERFORM CLEANUP."), encoding="utf-8")

    result = extract(
        [tmp_path / "alpha.cbl", tmp_path / "beta.cbl", copybook], cache_root=tmp_path
    )

    assert _copybook_performs(result) == {
        ("alpha.cbl:MAIN-PARA", "SHARED.cpy:SHARED-STEP"),
        ("beta.cbl:MAIN-PARA", "SHARED.cpy:SHARED-STEP"),
        ("SHARED.cpy:SHARED-STEP", "alpha.cbl:CLEANUP"),
        ("SHARED.cpy:SHARED-STEP", "beta.cbl:CLEANUP"),
    }


def test_cobol_perform_reaches_a_copybook_copied_by_a_copybook(tmp_path):
    program = tmp_path / "nested.cbl"
    program.write_text(_program(
        "NESTED", "MAIN-PARA.", "    PERFORM INNER-STEP.", "COPY OUTER.",
    ), encoding="utf-8")
    (tmp_path / "OUTER.cpy").write_text(_copybook(
        "OUTER-STEP.", "    PERFORM INNER-STEP.", "COPY INNER.",
    ), encoding="utf-8")
    (tmp_path / "INNER.cpy").write_text(_copybook(
        "INNER-STEP.", "    DISPLAY 'inner'.",
    ), encoding="utf-8")

    result = extract(
        [program, tmp_path / "OUTER.cpy", tmp_path / "INNER.cpy"], cache_root=tmp_path
    )

    assert _copybook_performs(result) == {
        ("nested.cbl:MAIN-PARA", "INNER.cpy:INNER-STEP"),
        ("OUTER.cpy:OUTER-STEP", "INNER.cpy:INNER-STEP"),
    }


def test_cobol_perform_of_a_name_two_copybooks_define_is_left_unlinked(tmp_path):
    """Two copybooks of one program with a paragraph of the same name: which one
    the PERFORM means cannot be told, so no edge is guessed."""
    program = tmp_path / "twice.cbl"
    program.write_text(_program(
        "TWICE", "MAIN-PARA.", "    PERFORM SAME-NAME.", "COPY FIRST.", "COPY SECOND.",
    ), encoding="utf-8")
    for name in ("FIRST", "SECOND"):
        (tmp_path / f"{name}.cpy").write_text(_copybook(
            "SAME-NAME.", f"    DISPLAY '{name}'.",
        ), encoding="utf-8")

    result = extract(
        [program, tmp_path / "FIRST.cpy", tmp_path / "SECOND.cpy"], cache_root=tmp_path
    )

    assert _copybook_performs(result) == set()


def test_cobol_nested_program_restores_enclosing_scope_after_end_program(tmp_path):
    """A contained (nested) program's own PROGRAM-ID switches the active
    program with no record of what it switched from, so code physically back
    in the enclosing program after the nested one's END PROGRAM kept
    attributing to the nested program forever."""
    source = tmp_path / "nested.cbl"
    source.write_text(
        "       IDENTIFICATION DIVISION.\n"
        "       PROGRAM-ID. PARENT.\n"
        "       PROCEDURE DIVISION.\n"
        "       PARENT-PARA.\n"
        "           CALL 'CHILD'.\n"
        "           STOP RUN.\n"
        "       IDENTIFICATION DIVISION.\n"
        "       PROGRAM-ID. CHILD.\n"
        "       PROCEDURE DIVISION.\n"
        "       CHILD-PARA.\n"
        "           DISPLAY 'CHILD'.\n"
        "       END PROGRAM CHILD.\n"
        "       PARENT-PARA-2.\n"
        "           DISPLAY 'BACK IN PARENT'.\n"
        "       END PROGRAM PARENT.\n",
        encoding="utf-8",
    )

    result = extract([source], cache_root=tmp_path)

    contains = _edge_labels(result, "contains")
    assert ("PARENT", "PARENT-PARA-2") in contains
    assert ("CHILD", "PARENT-PARA-2") not in contains


def test_cobol_sibling_programs_with_end_program_are_unaffected(tmp_path):
    """A control for the fix above: two standalone (non-nested) programs each
    closed with their own END PROGRAM must still resolve their own paragraphs
    to themselves, not leak into one another."""
    source = tmp_path / "siblings.cbl"
    source.write_text(
        "       IDENTIFICATION DIVISION.\n"
        "       PROGRAM-ID. ONE.\n"
        "       PROCEDURE DIVISION.\n"
        "       ONE-PARA.\n"
        "           DISPLAY 'ONE'.\n"
        "       END PROGRAM ONE.\n"
        "       IDENTIFICATION DIVISION.\n"
        "       PROGRAM-ID. TWO.\n"
        "       PROCEDURE DIVISION.\n"
        "       TWO-PARA.\n"
        "           DISPLAY 'TWO'.\n"
        "       END PROGRAM TWO.\n",
        encoding="utf-8",
    )

    result = extract([source], cache_root=tmp_path)

    contains = _edge_labels(result, "contains")
    assert ("ONE", "ONE-PARA") in contains
    assert ("TWO", "TWO-PARA") in contains
    assert ("ONE", "TWO-PARA") not in contains
    assert ("TWO", "ONE-PARA") not in contains


@pytest.mark.parametrize("statement", [
    "SORT WORK-FILE ON ASCENDING KEY WS-KEY USING IN-FILE GIVING OUT-FILE.",
    "SEARCH WS-ROW AT END MOVE 1 TO WS-FLAG.",
    "NEXT SENTENCE.",
    "INSPECT WS-TEXT TALLYING WS-COUNT FOR ALL 'X'.",
    "STOP RUN.",
    "EXEC SQL COMMIT END-EXEC.",
    "EXEC SQL\n               COMMIT\n           END-EXEC.",
])
def test_cobol_procedure_copybook_is_known_by_any_statement(tmp_path, statement):
    """The statement that shows a headerless copybook to be procedure code can
    be any verb. With a short list of verbs, a copybook whose only statement
    was a SORT or a SEARCH stayed data and lost its paragraph."""
    copybook = tmp_path / "ROUTINE.cpy"
    copybook.write_text(
        "       ONLY-PARA.\n"
        f"           {statement}\n",
        encoding="utf-8",
    )

    result = extract([copybook], cache_root=tmp_path)

    kinds = {node["label"]: node["metadata"]["kind"] for node in result["nodes"]}
    assert kinds == {"ROUTINE.cpy": "file", "ONLY-PARA": "paragraph"}


@pytest.mark.parametrize("line", [
    # A name that begins with a verb is not a statement.
    "               OPEN-FILES.",
    # A declaration, which the DATA DIVISION has as well.
    "           EXEC SQL INCLUDE SQLCA END-EXEC.",
    "           EXEC SQL\n               INCLUDE SQLCA\n           END-EXEC.",
    # A quoted value is text, whatever it says.
    "               'EXEC SQL COMMIT END-EXEC'.",
    "               'MOVE A TO B'.",
])
def test_cobol_data_copybook_with_a_statement_lookalike_stays_data(tmp_path, line):
    """After a lone `SPACES.` line, a data copybook was read as procedure code
    when a later line looked like a statement, and lost its data items."""
    copybook = tmp_path / "RECORD.cpy"
    copybook.write_text(
        "       01  WS-RECORD.\n"
        "           05  WS-FILL             PIC X(10) VALUE\n"
        "               SPACES.\n"
        "           05  WS-NAME             PIC X(10) VALUE\n"
        f"{line}\n"
        "       01  WS-STATUS               PIC XX.\n",
        encoding="utf-8",
    )

    result = extract([copybook], cache_root=tmp_path)

    kinds = {node["label"]: node["metadata"]["kind"] for node in result["nodes"]}
    assert kinds == {
        "RECORD.cpy": "file", "WS-RECORD": "data_item", "WS-FILL": "data_item",
        "WS-NAME": "data_item", "WS-STATUS": "data_item",
    }
