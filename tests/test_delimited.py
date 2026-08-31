from __future__ import annotations

import os
from pathlib import Path

from graphify import delimited, detect


def test_csv_to_markdown_preserves_quoted_values_and_context(tmp_path):
    source = tmp_path / "research.csv"
    source.write_text(
        '\ufeffname,description,formula\r\n'
        'Alice,"quoted, value with | pipe",=SUM(A1:A2)\r\n'
        'Bob,"line one\nline two",@reference\r\n',
        encoding="utf-8",
    )

    markdown = delimited.delimited_to_markdown(source)

    assert "# Table: research.csv" in markdown
    assert "- Delimiter: comma" in markdown
    assert "- Header: detected" in markdown
    assert "- Data rows: 2" in markdown
    assert "- Columns: 3" in markdown
    assert "- Truncated: no" in markdown
    assert "| name | description | formula |" in markdown
    assert "| Alice | quoted, value with \\| pipe | =SUM(A1:A2) |" in markdown
    assert "| Bob | line one<br>line two | @reference |" in markdown


def test_tsv_reports_ragged_rows_without_dropping_extra_cells(tmp_path):
    source = tmp_path / "observations.tsv"
    source.write_text(
        "id\tname\n"
        "1\tAlice\n"
        "2\tBob\textra\n",
        encoding="utf-8",
    )

    markdown = delimited.delimited_to_markdown(source)

    assert "- Delimiter: tab" in markdown
    assert "- Ragged rows: 1" in markdown
    assert "| id | name | column_3 |" in markdown
    assert "| 2 | Bob | extra |" in markdown


def test_headerless_numeric_csv_uses_synthetic_columns(tmp_path):
    source = tmp_path / "measurements.csv"
    source.write_text("1,2\n3,4\n", encoding="utf-8")

    markdown = delimited.delimited_to_markdown(source)

    assert "- Header: synthesized" in markdown
    assert "- Data rows: 2" in markdown
    assert "| column_1 | column_2 |" in markdown
    assert "| 1 | 2 |" in markdown


def test_delimited_limits_are_bounded_and_reported(tmp_path, monkeypatch):
    monkeypatch.setattr(delimited, "MAX_DATA_ROWS", 2)
    monkeypatch.setattr(delimited, "MAX_COLUMNS", 2)
    monkeypatch.setattr(delimited, "MAX_FIELD_CHARS", 5)
    source = tmp_path / "bounded.csv"
    source.write_text(
        "name,notes,ignored\n"
        "Alice,123456789,x\n"
        "Bob,short,y\n"
        "Carol,short,z\n",
        encoding="utf-8",
    )

    markdown = delimited.delimited_to_markdown(source)

    assert "- Data rows: 2" in markdown
    assert "- Columns: 2" in markdown
    assert "- Truncated: yes" in markdown
    assert "- Truncation: columns, fields, rows" in markdown
    assert "| Alice | 12345… |" in markdown
    assert "Carol" not in markdown
    assert "ignored" not in markdown


def test_delimited_raw_size_cap_rejects_oversized_input(tmp_path, monkeypatch):
    monkeypatch.setattr(delimited, "MAX_RAW_BYTES", 16)
    source = tmp_path / "oversized.csv"
    source.write_text("name,value\nalpha,1234567890\n", encoding="utf-8")

    assert delimited.delimited_to_markdown(source) == ""


def test_source_fingerprint_enforces_cap_while_reading(tmp_path, monkeypatch):
    source = tmp_path / "growing.csv"
    source.write_bytes(b"x" * 32)
    monkeypatch.setattr(delimited, "MAX_RAW_BYTES", 16)
    monkeypatch.setattr(delimited, "_file_within_size_cap", lambda _path: True)

    assert delimited.source_fingerprint(source) is None


def test_delimited_output_cap_keeps_complete_markdown_rows(tmp_path, monkeypatch):
    monkeypatch.setattr(delimited, "MAX_OUTPUT_CHARS", 240)
    source = tmp_path / "many.csv"
    source.write_text(
        "id,description\n"
        + "".join(f"{index},observation-{index:02d}-with-context\n" for index in range(20)),
        encoding="utf-8",
    )

    markdown = delimited.delimited_to_markdown(source)

    assert len(markdown) <= 240
    assert "- Truncated: yes" in markdown
    assert "output" in markdown
    assert markdown.splitlines()[-1].startswith("| ")
    assert markdown.splitlines()[-1].endswith(" |")


def test_detect_converts_csv_and_tsv_to_markdown_sidecars(tmp_path):
    (tmp_path / "people.csv").write_text("name,role\nAda,researcher\n", encoding="utf-8")
    (tmp_path / "scores.tsv").write_text("name\tscore\nAda\t10\n", encoding="utf-8")

    result = detect.detect(tmp_path)

    documents = [Path(path) for path in result["files"]["document"]]
    assert result["total_files"] == 2
    assert len(documents) == 2
    assert all(path.suffix == ".md" for path in documents)
    assert all(path.parent.name == "converted" for path in documents)
    bodies = "\n".join(path.read_text(encoding="utf-8") for path in documents)
    assert "# Table: people.csv" in bodies
    assert "# Table: scores.tsv" in bodies
    assert result["unclassified"] == []


def test_parser_rejects_pathological_column_count_before_materializing(tmp_path):
    source = tmp_path / "too-wide.csv"
    source.write_text(",".join(["value"] * 1_001) + "\n", encoding="utf-8")

    assert delimited.delimited_to_markdown(source) == ""


def test_valid_field_above_python_csv_default_is_truncated(tmp_path):
    source = tmp_path / "long-field.csv"
    source.write_text("name,notes\nalpha," + ("x" * 140_000) + "\n", encoding="utf-8")

    markdown = delimited.delimited_to_markdown(source)

    assert "- Truncated: yes" in markdown
    assert "fields" in markdown
    assert ("x" * 10_000) + "…" in markdown


def test_malformed_unclosed_quote_is_rejected(tmp_path):
    source = tmp_path / "malformed.csv"
    source.write_text('a,b\n1,"hello\n2,world\n', encoding="utf-8")

    assert delimited.delimited_to_markdown(source) == ""


def test_malformed_quote_placement_and_nul_are_rejected(tmp_path):
    cases = {
        "junk-after-quote.csv": 'a,b\n1,"hello"junk\n',
        "quote-in-unquoted.csv": 'a,b\n1,hel"lo\n',
        "nul.csv": "a,b\n1,x\x00y\n",
    }

    for name, text in cases.items():
        source = tmp_path / name
        source.write_text(text, encoding="utf-8")
        assert delimited.delimited_to_markdown(source) == ""


def test_parse_stream_is_revalidated_if_source_changes_after_preflight(tmp_path, monkeypatch):
    source = tmp_path / "changing.csv"
    source.write_text("a,b\n1,2\n", encoding="utf-8")
    real_validate = delimited._validate_record_bounds

    def validate_then_replace(handle, dialect):
        real_validate(handle, dialect)
        source.write_text(",".join(["x" * 800_000] * 3) + "\n", encoding="utf-8")

    monkeypatch.setattr(delimited, "_validate_record_bounds", validate_then_replace)

    assert delimited.delimited_to_markdown(source) == ""


def test_invalid_utf8_is_rejected_without_lossy_decoding(tmp_path):
    source = tmp_path / "invalid.csv"
    source.write_bytes(b"name,value\nalpha,\xff\n")

    assert delimited.delimited_to_markdown(source) == ""


def test_markdown_and_html_payloads_are_rendered_as_inert_text(tmp_path):
    source = tmp_path / "payload.csv"
    source.write_text(
        'name,payload\nalpha,"<img src=x onerror=alert(1)> [click](https://example.com)"\n',
        encoding="utf-8",
    )

    markdown = delimited.delimited_to_markdown(source)

    assert "&lt;img src=x onerror=alert(1)&gt;" in markdown
    assert r"\[click\](https://example.com)" in markdown
    assert "<img src=x" not in markdown


def test_csv_sniffs_delimiter_beyond_the_old_64k_window(tmp_path):
    source = tmp_path / "late-delimiter.csv"
    source.write_text(("A" * 70_000) + ";value\nshort;2\n", encoding="utf-8")

    markdown = delimited.delimited_to_markdown(source)

    assert "- Delimiter: semicolon" in markdown
    assert "| short | 2 |" in markdown


def test_escape_expanded_header_is_truncated_not_dropped(tmp_path):
    source = tmp_path / "wide-header.tsv"
    source.write_text("\t".join(["|" * 6_000] * 100) + "\n", encoding="utf-8")

    markdown = delimited.delimited_to_markdown(source)

    assert markdown
    assert "- Truncated: yes" in markdown
    assert "output" in markdown
    assert len(markdown) <= delimited.MAX_OUTPUT_CHARS


def test_delimited_sidecar_refresh_uses_content_not_source_mtime(tmp_path):
    source = tmp_path / "evidence.csv"
    source.write_text("name,value\nold,1\n", encoding="utf-8")
    first = detect.detect(tmp_path)
    sidecar = Path(first["files"]["document"][0])
    first_sidecar_mtime = sidecar.stat().st_mtime_ns
    unchanged = detect.detect(tmp_path)
    assert Path(unchanged["files"]["document"][0]) == sidecar
    assert sidecar.stat().st_mtime_ns == first_sidecar_mtime

    sidecar_mtime = sidecar.stat().st_mtime

    source.write_text("name,value\nnew,2\n", encoding="utf-8")
    os.utime(source, (sidecar_mtime - 10, sidecar_mtime - 10))
    second = detect.detect(tmp_path)

    assert Path(second["files"]["document"][0]) == sidecar
    body = sidecar.read_text(encoding="utf-8")
    assert "| new | 2 |" in body
    assert "| old | 1 |" not in body
