"""Regression tests for missing tomli on Python < 3.11 (#3283)."""
from __future__ import annotations

import builtins
import sys
from pathlib import Path

import pytest

from graphify.manifest_ingest import (
    _TOMLI_REQUIRED,
    _load_toml_module,
    _parse_cargo,
    _parse_pyproject,
    extract_package_manifest,
)


def test_load_toml_module_raises_when_tomli_missing(monkeypatch):
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name in ("tomllib", "tomli"):
            raise ImportError(f"blocked {name}")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    with pytest.raises(ImportError, match="tomli"):
        _load_toml_module()


def test_parse_pyproject_surfaces_missing_parser(monkeypatch):
    monkeypatch.setattr(
        "graphify.manifest_ingest._load_toml_module",
        lambda: (_ for _ in ()).throw(ImportError(_TOMLI_REQUIRED)),
    )
    with pytest.raises(ImportError, match="tomli"):
        _parse_pyproject('[project]\nname = "x"\n')


def test_parse_cargo_surfaces_missing_parser(monkeypatch):
    monkeypatch.setattr(
        "graphify.manifest_ingest._load_toml_module",
        lambda: (_ for _ in ()).throw(ImportError(_TOMLI_REQUIRED)),
    )
    with pytest.raises(ImportError, match="tomli"):
        _parse_cargo('[package]\nname = "x"\nversion = "0.1.0"\n')


def test_extract_package_manifest_reports_missing_tomli(tmp_path, monkeypatch):
    p = tmp_path / "pyproject.toml"
    p.write_text('[project]\nname = "cool"\nversion = "0.1"\n', encoding="utf-8")
    monkeypatch.setattr(
        "graphify.manifest_ingest._load_toml_module",
        lambda: (_ for _ in ()).throw(ImportError(_TOMLI_REQUIRED)),
    )
    result = extract_package_manifest(p)
    assert result["nodes"] == []
    assert "tomli" in result.get("error", "").lower()


@pytest.mark.skipif(sys.version_info >= (3, 11), reason="stdlib tomllib present")
def test_tomli_is_importable_on_py310():
    import tomli  # noqa: F401
