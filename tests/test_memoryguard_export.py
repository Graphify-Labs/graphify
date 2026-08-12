from __future__ import annotations

import json
from pathlib import Path
import sys

from graphify.memoryguard_export import EXPORT_FORMAT, export_repository


def _assert_body_free(value: object) -> None:
    forbidden = {
        "body", "source_body", "raw_content", "content", "source_text",
        "secret", "token", "password", "api_key", "credential", "authority",
    }
    if isinstance(value, dict):
        assert not forbidden.intersection(value)
        for item in value.values():
            _assert_body_free(item)
    elif isinstance(value, list):
        for item in value:
            _assert_body_free(item)


def test_export_is_relative_hashed_provenance_and_body_free(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    marker = "RAW_SOURCE_BODY_MUST_NOT_LEAK_12345"
    (tmp_path / "src" / "gui.py").write_text(
        'PAGE = """<button onclick=\\"go()\\">Run</button><script>function go(){api(\\"run_it\\")}</script>"""\n'
        f"# {marker}\n",
        encoding="utf-8",
    )

    payload = export_repository(tmp_path, parallel=False)
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True)

    assert payload["format"] == EXPORT_FORMAT
    assert payload["files"]
    assert all(not Path(item["path"]).is_absolute() for item in payload["files"])
    assert all(len(item["content_hash"]) == 64 for item in payload["files"])
    assert {item["provenance"] for item in payload["files"]} == {"production"}
    assert payload["nodes"]
    assert payload["edges"]
    assert marker not in encoded
    assert str(tmp_path.resolve()).replace("\\", "/") not in encoded.replace("\\", "/")
    _assert_body_free(payload)


def test_cli_exposes_and_runs_memoryguard_metadata(tmp_path: Path, monkeypatch, capsys) -> None:
    from graphify import cli

    (tmp_path / "app.py").write_text(
        'PAGE = """<button onclick=\\"go()\\">Run</button><script>function go(){api(\\"run_it\\")}</script>"""\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(sys, "argv", ["graphify", "export", "--help"])
    cli.dispatch_command("export")
    help_text = capsys.readouterr().out
    assert "memoryguard-metadata" in help_text
    assert EXPORT_FORMAT in help_text

    monkeypatch.setattr(
        sys,
        "argv",
        ["graphify", "export", "memoryguard-metadata", str(tmp_path), "app.py", "--no-parallel"],
    )
    cli.dispatch_command("export")
    payload = json.loads(capsys.readouterr().out)
    assert payload["format"] == EXPORT_FORMAT
    assert payload["files"][0]["path"] == "app.py"


def test_full_repository_export_smoke(tmp_path: Path) -> None:
    for relative, content in {
        "src/app.py": "def run():\n    return 1\n",
        "tests/test_app.py": "def test_run():\n    assert True\n",
        "vendor/lib.py": "def vendor_call():\n    return 1\n",
        "generated/client.py": "def generated_call():\n    return 1\n",
    }.items():
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    payload = export_repository(tmp_path, parallel=False)
    assert {item["path"] for item in payload["files"]} == {
        "generated/client.py", "src/app.py", "tests/test_app.py", "vendor/lib.py",
    }
    assert {item["provenance"] for item in payload["files"]} == {
        "generated", "production", "test", "vendor",
    }
    assert payload["nodes"]
