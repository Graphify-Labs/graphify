"""Bounded CSV/TSV parsing and contextualized Markdown rendering."""
from __future__ import annotations

import csv
import hashlib
import io
import threading
from pathlib import Path
from typing import Iterator, TextIO

DELIMITED_EXTENSIONS = {".csv", ".tsv"}

MAX_RAW_BYTES = 50 * 1024 * 1024
MAX_DATA_ROWS = 1_000
MAX_COLUMNS = 100
MAX_FIELD_CHARS = 10_000
MAX_OUTPUT_CHARS = 1_100_000
MAX_PARSE_COLUMNS = 1_000
MAX_RECORD_CHARS = 2 * 1024 * 1024
CONVERTER_VERSION = "delimited-v1"

_CSV_FIELD_LIMIT_LOCK = threading.Lock()


def _file_within_size_cap(path: Path, cap: int | None = None) -> bool:
    try:
        return path.is_file() and path.stat().st_size <= (MAX_RAW_BYTES if cap is None else cap)
    except OSError:
        return False


def source_fingerprint(path: Path) -> str | None:
    """Return a bounded source-content hash used to invalidate sidecars."""
    if not _file_within_size_cap(path):
        return None
    digest = hashlib.sha256()
    total_bytes = 0
    try:
        with path.open("rb") as source:
            for chunk in iter(lambda: source.read(64 * 1024), b""):
                total_bytes += len(chunk)
                if total_bytes > MAX_RAW_BYTES:
                    return None
                digest.update(chunk)
    except OSError:
        return None
    return digest.hexdigest()


def sidecar_marker(fingerprint: str) -> str:
    return f"<!-- graphify-delimited:{CONVERTER_VERSION} sha256={fingerprint} -->"


def _markdown_table_cell(value: str) -> str:
    """Render one value as inert, meaning-preserving Markdown table text."""
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace("\\", "\\\\")
        .replace("|", "\\|")
        .replace("[", "\\[")
        .replace("]", "\\]")
        .replace("\r\n", "<br>")
        .replace("\r", "<br>")
        .replace("\n", "<br>")
    )


def _cell_kind(value: str) -> str:
    stripped = value.strip()
    if not stripped:
        return "empty"
    if stripped.startswith(("=", "+", "-", "@")):
        return "formula"
    if stripped.lower() in {"true", "false", "yes", "no"}:
        return "boolean"
    try:
        float(stripped.replace(",", ""))
    except ValueError:
        return "text"
    return "number"


def _has_header(rows: list[list[str]], delimiter: str) -> bool:
    if len(rows) < 2 or not rows[0]:
        return bool(rows and rows[0])

    reduced = io.StringIO(newline="")
    writer = csv.writer(reduced, delimiter=delimiter, lineterminator="\n")
    writer.writerows([[cell[:256] for cell in row[:MAX_COLUMNS]] for row in rows[:20]])
    try:
        if csv.Sniffer().has_header(reduced.getvalue()):
            return True
    except csv.Error:
        pass

    first = rows[0]
    for column, value in enumerate(first):
        if _cell_kind(value) != "text":
            continue
        later_kinds = {
            _cell_kind(row[column])
            for row in rows[1:21]
            if column < len(row) and row[column].strip()
        }
        if later_kinds - {"text", "empty"}:
            return True
    return False


def _dialect_for(path: Path, sample: str) -> type[csv.Dialect] | csv.Dialect:
    if path.suffix.lower() == ".tsv":
        return csv.excel_tab
    try:
        return csv.Sniffer().sniff(sample, delimiters=",;\t|")
    except csv.Error:
        return csv.excel


def _bounded_csv_lines(
    source: TextIO, dialect: type[csv.Dialect] | csv.Dialect
) -> Iterator[str]:
    """Yield physical lines only after validating their logical CSV record."""
    delimiter = dialect.delimiter
    quotechar = dialect.quotechar
    escapechar = dialect.escapechar
    doublequote = dialect.doublequote
    skipinitialspace = dialect.skipinitialspace

    in_quotes = False
    quote_pending = False
    escape_pending = False
    after_quote = False
    at_field_start = True
    saw_cr = False
    columns = 1
    record_chars = 0
    total_chars = 0
    raw_buffer = getattr(source, "buffer", None)

    while line := source.readline(MAX_RECORD_CHARS + 1):
        total_chars += len(line)
        if total_chars > MAX_RAW_BYTES:
            raise csv.Error("delimited input exceeds raw parser limit")
        if raw_buffer is not None and raw_buffer.tell() > MAX_RAW_BYTES:
            raise csv.Error("delimited input exceeds raw parser limit")

        for char in line:
            if saw_cr:
                saw_cr = False
                if char == "\n":
                    continue

            record_chars += 1
            if record_chars > MAX_RECORD_CHARS:
                raise csv.Error("delimited logical record exceeds parser limit")
            if char == "\x00":
                raise csv.Error("NUL byte in delimited input")

            if quote_pending:
                quote_pending = False
                if doublequote and quotechar and char == quotechar:
                    continue
                in_quotes = False
                after_quote = True

            if after_quote:
                if char == delimiter:
                    columns += 1
                    if columns > MAX_PARSE_COLUMNS:
                        raise csv.Error("delimited logical record exceeds parser column limit")
                    after_quote = False
                    at_field_start = True
                elif char in {"\r", "\n"}:
                    columns = 1
                    record_chars = 0
                    after_quote = False
                    at_field_start = True
                    saw_cr = char == "\r"
                elif char not in {" ", "\t"}:
                    raise csv.Error("unexpected character after closing quote")
                continue

            if escape_pending:
                escape_pending = False
                at_field_start = False
                continue
            if escapechar and char == escapechar:
                escape_pending = True
                at_field_start = False
                continue

            if in_quotes:
                if quotechar and char == quotechar:
                    if doublequote:
                        quote_pending = True
                    else:
                        in_quotes = False
                        after_quote = True
                continue

            if quotechar and at_field_start and char == quotechar:
                in_quotes = True
                at_field_start = False
            elif quotechar and char == quotechar:
                raise csv.Error("quote in unquoted field")
            elif char == delimiter:
                columns += 1
                if columns > MAX_PARSE_COLUMNS:
                    raise csv.Error("delimited logical record exceeds parser column limit")
                at_field_start = True
            elif char in {"\r", "\n"}:
                columns = 1
                record_chars = 0
                at_field_start = True
                saw_cr = char == "\r"
            elif skipinitialspace and at_field_start and char == " ":
                continue
            else:
                at_field_start = False

        yield line

    if quote_pending:
        in_quotes = False
    if in_quotes or escape_pending:
        raise csv.Error("unterminated quoted or escaped field")


def _validate_record_bounds(source: TextIO, dialect: type[csv.Dialect] | csv.Dialect) -> None:
    """Validate all logical records before constructing a ``csv.reader``."""
    for _line in _bounded_csv_lines(source, dialect):
        pass


def _truncate_for_render(value: str, render_limit: int) -> str:
    rendered = _markdown_table_cell(value)
    if len(rendered) <= render_limit:
        return value
    suffix = "…"
    low, high = 0, len(value)
    while low < high:
        midpoint = (low + high + 1) // 2
        if len(_markdown_table_cell(value[:midpoint] + suffix)) <= render_limit:
            low = midpoint
        else:
            high = midpoint - 1
    return value[:low] + suffix if low else suffix


def delimited_to_markdown(path: Path, *, output_limit: int | None = None) -> str:
    """Convert bounded UTF-8 CSV/TSV data into contextualized Markdown."""
    if not _file_within_size_cap(path):
        return ""
    limit = MAX_OUTPUT_CHARS if output_limit is None else output_limit
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as source:
            sample = source.read(MAX_RECORD_CHARS)
            dialect = _dialect_for(path, sample)
            source.seek(0)
            _validate_record_bounds(source, dialect)

        rows: list[list[str]] = []
        truncation: set[str] = set()
        expected_columns: int | None = None
        ragged_rows = 0
        stored_render_chars = 0

        with _CSV_FIELD_LIMIT_LOCK:
            previous_field_limit = csv.field_size_limit()
            csv.field_size_limit(max(previous_field_limit, MAX_RECORD_CHARS))
            try:
                with path.open("r", encoding="utf-8-sig", newline="") as source:
                    reader = csv.reader(_bounded_csv_lines(source, dialect), dialect, strict=True)
                    for raw_row in reader:
                        if expected_columns is None:
                            expected_columns = len(raw_row)
                        elif len(raw_row) != expected_columns:
                            ragged_rows += 1
                        if len(raw_row) > MAX_COLUMNS:
                            truncation.add("columns")
                            raw_row = raw_row[:MAX_COLUMNS]

                        bounded: list[str] = []
                        for cell in raw_row:
                            if len(cell) > MAX_FIELD_CHARS:
                                truncation.add("fields")
                                cell = cell[:MAX_FIELD_CHARS] + "…"
                            bounded.append(cell)
                        rendered_chars = 4 + sum(
                            len(_markdown_table_cell(cell)) + 3 for cell in bounded
                        )
                        if rows and stored_render_chars + rendered_chars > limit:
                            truncation.add("output")
                            break
                        rows.append(bounded)
                        stored_render_chars += rendered_chars
                        if len(rows) > MAX_DATA_ROWS + 1:
                            truncation.add("rows")
                            break
            finally:
                csv.field_size_limit(previous_field_limit)
    except (OSError, UnicodeError, csv.Error):
        return ""

    if not rows:
        return ""

    delimiter = dialect.delimiter
    has_header = _has_header(rows, delimiter)
    max_rows = MAX_DATA_ROWS + (1 if has_header else 0)
    if len(rows) > max_rows:
        rows = rows[:max_rows]
        truncation.add("rows")

    max_columns = max(len(row) for row in rows)
    padded = [row + [""] * (max_columns - len(row)) for row in rows]
    if has_header:
        header = [cell or f"column_{index + 1}" for index, cell in enumerate(padded[0])]
        data_rows = padded[1:]
        header_status = "detected"
    else:
        header = [f"column_{index + 1}" for index in range(max_columns)]
        data_rows = padded
        header_status = "synthesized"

    header_render_budget = max(32, limit // 3)
    per_header_budget = max(8, header_render_budget // max(1, len(header)))
    fitted_header = [_truncate_for_render(cell, per_header_budget) for cell in header]
    if fitted_header != header:
        header = fitted_header
        truncation.update({"fields", "output"})

    delimiter_names = {",": "comma", "\t": "tab", ";": "semicolon", "|": "pipe"}
    data_lines = [
        "| " + " | ".join(_markdown_table_cell(cell) for cell in row) + " |"
        for row in data_rows
    ]

    def render(kept_lines: list[str]) -> str:
        reason_order = ("columns", "fields", "rows", "output")
        lines = [
            f"# Table: {_markdown_table_cell(path.name)}",
            "",
            f"- Delimiter: {delimiter_names.get(delimiter, repr(delimiter))}",
            f"- Header: {header_status}",
            f"- Data rows: {len(kept_lines)}",
            f"- Columns: {max_columns}",
            f"- Ragged rows: {ragged_rows}",
            f"- Truncated: {'yes' if truncation else 'no'}",
        ]
        if truncation:
            lines.append(
                "- Truncation: " + ", ".join(reason for reason in reason_order if reason in truncation)
            )
        lines.extend([
            "",
            "| " + " | ".join(_markdown_table_cell(cell) for cell in header) + " |",
            "| " + " | ".join("---" for _ in header) + " |",
        ])
        lines.extend(kept_lines)
        return "\n".join(lines)

    markdown = render(data_lines)
    if len(markdown) > limit:
        truncation.add("output")
        base = render([])
        kept_lines: list[str] = []
        size = len(base)
        for line in data_lines:
            added = len(line) + 1
            if size + added > limit:
                break
            kept_lines.append(line)
            size += added
        markdown = render(kept_lines)
        while kept_lines and len(markdown) > limit:
            kept_lines.pop()
            markdown = render(kept_lines)
        if len(markdown) > limit:
            return ""
    return markdown
