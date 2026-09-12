"""manifest.json rebuild idempotency (#2988).

save_manifest restamped volatile ``mtime``/``seen`` values on every run
whenever the stored row no longer matched a fresh stat (checkout / copy /
touch move mtimes without touching content), and one restamped field broke
the other's preservation condition too — so with the README-recommended flow
of committing graphify-out/ behind a post-commit rebuild hook, the working
tree went dirty again after every single commit. The volatile fields are now
inherited verbatim from the previous row whenever the freshly computed hashes
match the stored ones, so an unchanged corpus yields a byte-identical
manifest.json and #2838's skip-write fires.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from graphify.detect import save_manifest


def _corpus(tmp_path: Path, n: int = 3) -> list[str]:
    docs = tmp_path / "docs"
    docs.mkdir(exist_ok=True)
    paths = []
    for i in range(n):
        p = docs / f"note{i}.md"
        p.write_text(f"# Note {i}\n\nStable content {i}.\n", encoding="utf-8")
        paths.append(str(p))
    return paths


def _save(paths: list[str], mp: Path, **kw) -> None:
    save_manifest({"document": paths}, str(mp), **kw)


def _bump_mtime(path: str, delta: float) -> None:
    st = os.stat(path)
    os.utime(path, (st.st_atime + delta, st.st_mtime + delta))


def test_repeated_save_over_untouched_corpus_is_byte_identical(tmp_path):
    """The #2988 headline: rebuilds over a settled corpus must not rewrite
    manifest.json at all."""
    files = _corpus(tmp_path)
    mp = tmp_path / "graphify-out" / "manifest.json"
    _save(files, mp)
    first = mp.read_text(encoding="utf-8")

    _save(files, mp)
    assert mp.read_text(encoding="utf-8") == first


def test_mtime_motion_without_content_change_does_not_restamp(tmp_path):
    """A checkout/copy/touch moves mtimes without changing content; hashes stay
    authoritative, so every row keeps its previous mtime/seen verbatim."""
    files = _corpus(tmp_path)
    mp = tmp_path / "graphify-out" / "manifest.json"
    _save(files, mp)
    before = json.loads(mp.read_text(encoding="utf-8"))

    for f in files:
        _bump_mtime(f, 3600.0)

    _save(files, mp)
    after = json.loads(mp.read_text(encoding="utf-8"))
    assert set(after) == set(before)
    for f in files:
        assert after[f]["mtime"] == before[f]["mtime"], f
        assert after[f]["seen"] == before[f]["seen"], f
        assert after[f]["ast_hash"] == before[f]["ast_hash"], f


def test_real_content_change_still_freshens_stamps(tmp_path):
    """Only genuine hash changes earn fresh stamps: the edited row restamps,
    untouched rows stay frozen."""
    files = _corpus(tmp_path)
    mp = tmp_path / "graphify-out" / "manifest.json"
    _save(files, mp)
    before = json.loads(mp.read_text(encoding="utf-8"))

    target = files[0]
    Path(target).write_text("# Note 0\n\nChanged.\n", encoding="utf-8")
    _bump_mtime(target, 7200.0)

    _save(files, mp)
    after = json.loads(mp.read_text(encoding="utf-8"))
    assert after[target]["ast_hash"] != before[target]["ast_hash"]
    assert after[target]["mtime"] != before[target]["mtime"]
    assert after[target]["seen"] >= before[target]["seen"]
    for f in files[1:]:
        assert after[f] == before[f], f


def test_kind_alternation_between_update_and_extract_settles(tmp_path):
    """Hook flows alternate kind='ast' (`update`) and kind='semantic'
    (`extract`) saves. Each hash-state transition may stamp once, but once
    both hashes are recorded the alternation is byte-stable."""
    files = _corpus(tmp_path)
    mp = tmp_path / "graphify-out" / "manifest.json"
    _save(files, mp, kind="ast")
    _save(files, mp, kind="semantic")  # semantic_hash "" -> h: one legit stamp
    settled = mp.read_text(encoding="utf-8")

    _save(files, mp, kind="ast")
    assert mp.read_text(encoding="utf-8") == settled
    _save(files, mp, kind="semantic")
    assert mp.read_text(encoding="utf-8") == settled


def test_subset_save_preserves_untouched_rows_verbatim(tmp_path):
    """A caller saving a SUBSET of files (#917) must not churn the seeded rows
    — and the stamped subset row inherits its volatile fields too."""
    files = _corpus(tmp_path)
    mp = tmp_path / "graphify-out" / "manifest.json"
    _save(files, mp)
    first = mp.read_text(encoding="utf-8")

    _save(files[:1], mp)
    assert mp.read_text(encoding="utf-8") == first


def test_legacy_float_row_promotes_once_then_stable(tmp_path):
    """Legacy bare-float rows promote to the dict schema exactly once; the
    promoted row is then frozen like any other unchanged row."""
    files = _corpus(tmp_path, n=1)
    f = files[0]
    mp = tmp_path / "graphify-out" / "manifest.json"
    mp.parent.mkdir(parents=True, exist_ok=True)
    mp.write_text(json.dumps({f: os.stat(f).st_mtime}), encoding="utf-8")

    _save(files, mp)
    promoted = json.loads(mp.read_text(encoding="utf-8"))
    assert isinstance(promoted[f], dict) and promoted[f]["ast_hash"]

    _save(files, mp)
    assert json.loads(mp.read_text(encoding="utf-8")) == promoted
