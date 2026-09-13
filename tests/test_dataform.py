"""Tests for deterministic Dataform SQLX extraction (#3496)."""

from __future__ import annotations

from pathlib import Path

from graphify.detect import CODE_EXTENSIONS, FileType, classify_file
from graphify.extract import _DISPATCH, extract, extract_dataform
from graphify.extractors import LANGUAGE_EXTRACTORS

FIXTURE = Path(__file__).parent / "fixtures" / "dataform_basic.sqlx"


def test_sqlx_is_detected_and_dispatched():
    assert ".sqlx" in CODE_EXTENSIONS
    assert classify_file(FIXTURE) == FileType.CODE
    assert _DISPATCH[".sqlx"] is extract_dataform
    assert LANGUAGE_EXTRACTORS["dataform"] is extract_dataform


def test_extracts_model_config_and_literal_refs(tmp_path):
    events = tmp_path / "stg_events.sqlx"
    events.write_text('config { type: "table" }\nSELECT 1;\n', encoding="utf-8")
    users = tmp_path / "users.sqlx"
    users.write_text('config { type: "table" }\nSELECT 1;\n', encoding="utf-8")

    model = tmp_path / "daily_events.sqlx"
    model.write_text(FIXTURE.read_text(encoding="utf-8"), encoding="utf-8")
    result = extract([events, users, model], root=tmp_path, cache_root=tmp_path, parallel=False)

    models = {node["id"]: node for node in result["nodes"] if node.get("type") == "dataform_model"}
    current = models["dataform_daily_events"]
    assert current["dataform_config"] == {
        "type": "table",
        "schema": "analytics",
        "tags": ["daily", "reporting"],
        "dependencies": ["stg_events"],
    }

    dependencies = {
        (edge["target"], edge["context"])
        for edge in result["edges"]
        if edge["source"] == "dataform_daily_events" and edge["relation"] == "depends_on"
    }
    assert dependencies == {
        ("dataform_stg_events", "dataform_config"),
        ("dataform_analytics_users", "dataform_ref"),
    }
    assert not any(
        edge["target"] == "dataform_daily_events"
        for edge in result["edges"]
        if edge["relation"] == "depends_on"
    )


def test_refs_in_comments_and_nonliteral_calls_are_ignored(tmp_path):
    model = tmp_path / "commented.sqlx"
    model.write_text(
        'config { type: "table" }\n'
        '-- ${ref("commented_out")}\n'
        'SELECT table.ref("member_call") AS ignored,\n'
        "SELECT ${ref(model_name)} AS value;\n",
        encoding="utf-8",
    )

    result = extract_dataform(model)

    assert result["edges"] == []


def test_refs_in_sql_string_literals_and_commented_config_are_ignored(tmp_path):
    model = tmp_path / "literal.sqlx"
    model.write_text(
        '// config { type: "table" }\n'
        "SELECT 'ref(\"inside_sql\")' AS example, ${ref(\"real_model\")};\n",
        encoding="utf-8",
    )

    result = extract_dataform(model)

    assert "dataform_config" not in result["nodes"][0]
    assert [edge["target"] for edge in result["edges"]] == ["dataform_real_model"]


def test_config_array_delimiter_ignores_comments_and_stays_within_field(tmp_path):
    model = tmp_path / "array_config.sqlx"
    model.write_text(
        'config { tags: ["daily /* ] */", /* ] */ "reporting"], '
        'dependencies: ["upstream"] }\n',
        encoding="utf-8",
    )

    result = extract_dataform(model)

    assert result["nodes"][0]["dataform_config"] == {
        "tags": ["daily /* ] */", "reporting"],
        "dependencies": ["upstream"],
    }


def test_config_parser_handles_inline_fields_without_reading_description_text(tmp_path):
    model = tmp_path / "inline_config.sqlx"
    model.write_text(
        'config { description: "type: fake, schema: fake", type: "table", '
        'schema: "analytics" }\n'
        "SELECT 1;\n",
        encoding="utf-8",
    )

    result = extract_dataform(model)

    assert result["nodes"][0]["dataform_config"] == {
        "description": "type: fake, schema: fake",
        "type": "table",
        "schema": "analytics",
    }
