"""#5167: Oracle's [NON]EDITIONABLE keyword must not hide a routine or trigger."""
from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("tree_sitter_sql")

from graphify.extractors.sql import extract_sql  # noqa: E402

PROCEDURE = (
    "CREATE OR REPLACE {kw}PROCEDURE hr.load_emp IS\n"
    "BEGIN\n"
    "  INSERT INTO hr.emp_copy SELECT * FROM hr.emp;\n"
    "END;\n/\n"
)
FUNCTION = (
    "CREATE OR REPLACE {kw}FUNCTION hr.f RETURN NUMBER IS\n"
    "  n NUMBER;\n"
    "BEGIN\n"
    "  SELECT COUNT(*) INTO n FROM hr.emp;\n"
    "  RETURN n;\n"
    "END;\n/\n"
)
TRIGGER = (
    "CREATE OR REPLACE {kw}TRIGGER hr.trg_emp BEFORE INSERT ON hr.emp FOR EACH ROW\n"
    "BEGIN\n"
    "  INSERT INTO hr.audit_log (id) VALUES (:new.id);\n"
    "END;\n/\n"
)


def _graph(tmp_path: Path, name: str, src: str):
    path = tmp_path / name
    path.write_text(src, encoding="utf-8")
    result = extract_sql(path)
    labels = sorted(n["label"] for n in result["nodes"] if n["label"] != name)
    edges = sorted(
        (e["relation"], e["target"])
        for e in result["edges"]
        if e["relation"] != "contains"
    )
    return labels, edges


@pytest.mark.parametrize(
    "kw", ["EDITIONABLE ", "NONEDITIONABLE ", "editionable "], ids=["ed", "noned", "lower"]
)
@pytest.mark.parametrize(
    "template, expected_label",
    [
        (PROCEDURE, "hr.load_emp()"),
        (FUNCTION, "hr.f()"),
        (TRIGGER, "hr.trg_emp"),
    ],
    ids=["procedure", "function", "trigger"],
)
def test_edition_keyword_matches_plain_ddl(tmp_path, kw, template, expected_label):
    plain = _graph(tmp_path, "plain.sql", template.format(kw=""))
    edition = _graph(tmp_path, "edition.sql", template.format(kw=kw))

    assert expected_label in edition[0]
    assert edition == plain


def test_edition_trigger_keeps_its_subject_table(tmp_path):
    _, edges = _graph(tmp_path, "trg.sql", TRIGGER.format(kw="EDITIONABLE "))
    assert ("triggers", "hr_emp") in edges


def test_edition_word_alone_is_not_a_routine(tmp_path):
    # The keyword is only accepted between CREATE [OR REPLACE] and the object
    # kind, so a table or column literally named editionable stays harmless.
    labels, _ = _graph(
        tmp_path,
        "t.sql",
        "CREATE TABLE editionable (id INT);\nSELECT editionable FROM editionable;\n",
    )
    assert not any(label.endswith("()") for label in labels)
