"""#4200 — ``graphify rebuild`` manifest-reset wrapper.

Confirms rebuild backs up the existing manifest and delegates to the
code-rebuild path. The semantic cache (docs/papers/images) survives
because rebuild never touches ``cache/`` under ``graphify-out/``.
"""
from __future__ import annotations
import json
import subprocess
import sys
from pathlib import Path


def _write_min_manifest(root: Path) -> Path:
    out = root / "graphify-out"
    out.mkdir(exist_ok=True)
    manifest = out / "manifest.json"
    manifest.write_text(json.dumps({"example.py": {"mtime": 0.0, "seen": 0.0}}), encoding="utf-8")
    (out / "cache").mkdir(exist_ok=True)
    (out / "cache" / "semantic.json").write_text("{}", encoding="utf-8")
    return manifest


def test_rebuild_backs_up_manifest(tmp_path, monkeypatch, capsys):
    """``graphify rebuild <path>`` must rename manifest.json to a backup
    before invoking the rebuild. Semantic cache files are untouched."""
    (tmp_path / "example.py").write_text("def foo(): pass\n", encoding="utf-8")
    manifest = _write_min_manifest(tmp_path)
    cache = tmp_path / "graphify-out" / "cache" / "semantic.json"
    assert manifest.exists()
    assert cache.exists()

    # Stub _rebuild_code so the test doesn't invoke the full build pipeline —
    # we only verify the manifest-reset behavior rebuild() owns.
    rebuild_calls: list[tuple] = []

    def fake_rebuild(path, force=False, no_cluster=False, block_on_lock=True):
        rebuild_calls.append((Path(path), force, no_cluster, block_on_lock))
        return True

    import graphify.watch as _watch
    monkeypatch.setattr(_watch, "_rebuild_code", fake_rebuild)

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "argv", ["graphify", "rebuild", str(tmp_path)])
    from graphify.cli import dispatch_command
    dispatch_command("rebuild")

    # Manifest was moved to a timestamped backup.
    assert not manifest.exists(), "manifest.json should be renamed by rebuild"
    backups = list((tmp_path / "graphify-out").glob(".manifest-backup-*.json"))
    assert backups, "no manifest backup written"

    # Semantic cache survived.
    assert cache.exists()

    # _rebuild_code was invoked with the given path and legacy defaults.
    assert rebuild_calls == [(Path(str(tmp_path)), False, False, True)]


def test_rebuild_no_manifest_still_runs(tmp_path, monkeypatch, capsys):
    """When no manifest.json exists, rebuild falls through to a from-scratch
    build rather than failing."""
    (tmp_path / "example.py").write_text("def foo(): pass\n", encoding="utf-8")
    (tmp_path / "graphify-out").mkdir()

    def fake_rebuild(path, force=False, no_cluster=False, block_on_lock=True):
        return True

    import graphify.watch as _watch
    monkeypatch.setattr(_watch, "_rebuild_code", fake_rebuild)

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "argv", ["graphify", "rebuild", str(tmp_path)])
    from graphify.cli import dispatch_command
    dispatch_command("rebuild")

    out = capsys.readouterr().out
    assert "No manifest.json found" in out
