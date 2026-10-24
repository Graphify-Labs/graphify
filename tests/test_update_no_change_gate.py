"""#4740: `graphify update` must not extract when nothing relevant changed.

_rebuild_code() used to run detect -> extract -> build -> cluster and only then
compare topology, so a zero-change run still cost minutes and gigabytes. These
tests pin the early exit, and — more importantly — the inputs that must NOT take
it. A false "unchanged" ships a stale graph, so every uncertain input has to fall
back to the full path.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

import graphify.extract as extract_mod
from graphify.watch import _rebuild_code

SKIP_MESSAGE = "No relevant changes"


def _corpus(root: Path) -> Path:
    """A corpus whose graph depends on more than its own code files."""
    (root / "src").mkdir(parents=True, exist_ok=True)
    (root / "src" / "a.ts").write_text(
        "export const A = 1;\nexport function fa() { return A; }\n"
    )
    (root / "src" / "b.ts").write_text(
        'import { fa } from "./a";\nexport const B = fa();\n'
    )
    (root / "src" / "m.py").write_text("def f():\n    return 1\n")
    (root / "tsconfig.json").write_text('{"compilerOptions": {"baseUrl": "."}}\n')
    (root / "package.json").write_text('{"name": "x", "version": "1.0.0"}\n')
    (root / "package-lock.json").write_text('{"lockfileVersion": 3}\n')
    return root


@pytest.fixture()
def built(tmp_path: Path) -> Path:
    """A corpus with one completed rebuild behind it (manifest stamped)."""
    root = _corpus(tmp_path / "corpus")
    assert _rebuild_code(root, acquire_lock=False) is True
    assert (root / "graphify-out" / "manifest.json").is_file()
    return root


def _spy_extract(monkeypatch: pytest.MonkeyPatch) -> list:
    """Count extract() calls. _rebuild_code imports it at call time."""
    calls: list = []
    real = extract_mod.extract

    def _counting(*args, **kwargs):
        calls.append(args[0] if args else None)
        return real(*args, **kwargs)

    monkeypatch.setattr(extract_mod, "extract", _counting)
    return calls


def _snapshot(root: Path) -> dict[str, bytes]:
    return {
        p.name: p.read_bytes()
        for p in sorted((root / "graphify-out").iterdir())
        if p.is_file()
    }


def test_unchanged_tree_skips_extraction_and_leaves_outputs_untouched(
    built: Path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    before = _snapshot(built)
    calls = _spy_extract(monkeypatch)

    assert _rebuild_code(built, acquire_lock=False) is True

    assert SKIP_MESSAGE in capsys.readouterr().out
    assert calls == [], "extract() must not run when nothing changed"
    assert _snapshot(built) == before, "outputs must be byte-identical"


def test_new_file_takes_the_full_path(
    built: Path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    calls = _spy_extract(monkeypatch)
    (built / "src" / "c.ts").write_text("export const C = 3;\n")

    assert _rebuild_code(built, acquire_lock=False) is True
    assert SKIP_MESSAGE not in capsys.readouterr().out
    assert calls, "a new file must re-extract"


def test_deleted_file_takes_the_full_path(
    built: Path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    calls = _spy_extract(monkeypatch)
    (built / "src" / "m.py").unlink()

    assert _rebuild_code(built, acquire_lock=False) is True
    assert SKIP_MESSAGE not in capsys.readouterr().out
    assert calls, "a deletion must re-extract"


def test_edited_tsconfig_takes_the_full_path(
    built: Path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    calls = _spy_extract(monkeypatch)
    (built / "tsconfig.json").write_text(
        '{"compilerOptions": {"baseUrl": ".", "paths": {"@app/*": ["src/*"]}}}\n'
    )

    assert _rebuild_code(built, acquire_lock=False) is True
    assert SKIP_MESSAGE not in capsys.readouterr().out
    assert calls, "a tsconfig edit changes JS/TS resolution, not just the graph"


def test_edited_package_json_takes_the_full_path(
    built: Path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    calls = _spy_extract(monkeypatch)
    (built / "package.json").write_text('{"name": "x", "version": "2.0.0"}\n')

    assert _rebuild_code(built, acquire_lock=False) is True
    assert SKIP_MESSAGE not in capsys.readouterr().out
    assert calls, "a package.json edit changes workspace resolution"


def test_edited_lock_file_takes_the_full_path(
    built: Path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    # The lock files are resolution inputs detect() skips by name, so they are
    # the ones the manifest has to carry under the resolution bucket.
    calls = _spy_extract(monkeypatch)
    (built / "package-lock.json").write_text(
        '{"lockfileVersion": 3, "packages": {"node_modules/x": {}}}\n'
    )

    assert _rebuild_code(built, acquire_lock=False) is True
    assert SKIP_MESSAGE not in capsys.readouterr().out
    assert calls, "a lock-file edit is a resolution-input change"


def test_touch_with_identical_content_still_skips(
    built: Path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    # Never skip on mtime alone: a bumped mtime with the same bytes is unchanged.
    # Bumping the clock is what `git checkout`/`rsync --times` do, so the gate has
    # to compare content rather than trust the timestamp.
    target = built / "src" / "a.ts"
    stat = target.stat()
    os.utime(target, (stat.st_mtime + 5, stat.st_mtime + 5))
    assert target.stat().st_mtime != stat.st_mtime

    calls = _spy_extract(monkeypatch)
    assert _rebuild_code(built, acquire_lock=False) is True

    assert SKIP_MESSAGE in capsys.readouterr().out
    assert calls == [], "identical content must not re-extract"


def test_changed_paths_supplied_does_not_use_the_gate(
    built: Path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    calls = _spy_extract(monkeypatch)

    assert _rebuild_code(
        built,
        changed_paths=[built / "src" / "a.ts"],
        acquire_lock=False,
    ) is True

    assert SKIP_MESSAGE not in capsys.readouterr().out
    assert calls, "an explicit change set must still reach extract()"


def test_force_does_not_use_the_gate(
    built: Path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    calls = _spy_extract(monkeypatch)

    assert _rebuild_code(built, force=True, acquire_lock=False) is True

    assert SKIP_MESSAGE not in capsys.readouterr().out
    assert calls, "--force must run the full path"


def test_gate_fails_closed_without_a_manifest(
    built: Path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    (built / "graphify-out" / "manifest.json").unlink()
    calls = _spy_extract(monkeypatch)

    assert _rebuild_code(built, acquire_lock=False) is True

    assert SKIP_MESSAGE not in capsys.readouterr().out
    assert calls, "no manifest means the tree cannot be proven unchanged"


def test_inputs_unchanged_rejects_an_empty_manifest(tmp_path: Path) -> None:
    from graphify.detect import detect
    from graphify.watch import _inputs_unchanged

    root = _corpus(tmp_path / "corpus")
    detected = detect(root)

    assert _inputs_unchanged(detected, root / "graphify-out" / "manifest.json", root) is False


def test_inputs_unchanged_tolerates_a_scanned_file_with_no_manifest_row(
    built: Path,
) -> None:
    # A source whose AST extraction permanently fails is deliberately never
    # stamped (#2543), so a row-based comparison alone would report it changed on
    # every run and the gate could never fire. The observable state of such a
    # file is exactly "in the scan, absent from the manifest".
    from graphify.detect import detect, load_manifest
    from graphify.watch import _inputs_unchanged

    manifest_path = built / "graphify-out" / "manifest.json"
    manifest = load_manifest(str(manifest_path), root=built)
    assert str((built / "src" / "m.py").resolve()) in manifest

    manifest = {k: v for k, v in manifest.items() if not k.endswith("m.py")}
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    detected = detect(built)
    assert _inputs_unchanged(detected, manifest_path, built) is True


def test_scan_digest_tracks_the_file_set_not_the_contents(built: Path) -> None:
    # The digest is the only thing that can tell "same file, still failing" from
    # "a file appeared", so it has to move for the latter and not for the former.
    from graphify.detect import detect
    from graphify.watch import _scan_digest

    before = _scan_digest(detect(built))
    (built / "src" / "new.py").write_text("def added(): return 1\n")
    assert _scan_digest(detect(built)) != before

    (built / "src" / "new.py").unlink()
    assert _scan_digest(detect(built)) == before
