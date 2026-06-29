"""Tests for graphify.installer.manifest."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from graphify.installer.manifest import (
    InstallManifest,
    load_manifest,
    manifest_path,
    save_manifest,
)


def test_manifest_path_is_localappdata_graphify():
    p = manifest_path()
    assert p.name == ".graphify_install.json"
    # On Windows this is %LOCALAPPDATA%\graphify\.graphify_install.json.
    # On non-Windows the function still returns a path; we just verify shape.
    assert "graphify" in p.parts


def test_save_and_load_roundtrip(tmp_path):
    m = InstallManifest(
        version="0.9.1",
        install_path=tmp_path,
        hosts=["claude"],
        user_path_added=True,
    )
    target = tmp_path / ".graphify_install.json"
    save_manifest(m, target)
    assert target.exists()
    loaded = load_manifest(target)
    assert loaded.version == "0.9.1"
    assert loaded.install_path == tmp_path
    assert loaded.hosts == ["claude"]
    assert loaded.user_path_added is True


def test_load_manifest_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_manifest(tmp_path / "nope.json")


def test_save_manifest_creates_parent_dirs(tmp_path):
    target = tmp_path / "nested" / "dir" / "manifest.json"
    m = InstallManifest(
        version="0.9.1",
        install_path=tmp_path,
        hosts=[],
        user_path_added=False,
    )
    save_manifest(m, target)
    assert target.exists()
