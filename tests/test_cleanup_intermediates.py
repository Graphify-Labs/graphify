"""Step 9 cleanup must use pathlib, not rm/find (#2790)."""

from pathlib import Path

from graphify.paths import cleanup_build_intermediates


def test_removes_named_intermediates_and_chunks(tmp_path: Path) -> None:
    out = tmp_path / "graphify-out"
    out.mkdir()
    (out / ".graphify_extract.json").write_text("x", encoding="utf-8")
    (out / ".graphify_chunk_01.json").write_text("x", encoding="utf-8")
    (out / ".needs_update").write_text("1", encoding="utf-8")
    keep = out / "graph.json"
    keep.write_text("{}", encoding="utf-8")

    removed = cleanup_build_intermediates(out)
    names = {p.name for p in removed}

    assert names == {".graphify_extract.json", ".graphify_chunk_01.json", ".needs_update"}
    assert keep.exists()
    assert not (out / ".graphify_extract.json").exists()
    assert not (out / ".graphify_chunk_01.json").exists()


def test_missing_dir_is_a_no_op(tmp_path: Path) -> None:
    assert cleanup_build_intermediates(tmp_path / "nope") == []


def test_does_not_descend_into_subdirs(tmp_path: Path) -> None:
    out = tmp_path / "graphify-out"
    nested = out / "keep"
    nested.mkdir(parents=True)
    (nested / ".graphify_chunk_99.json").write_text("x", encoding="utf-8")

    assert cleanup_build_intermediates(out) == []
    assert (nested / ".graphify_chunk_99.json").exists()
