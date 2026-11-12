from pathlib import Path
from graphify.detect import detect


def test_detect_directory_walk_is_sorted(tmp_path):
    # Create dirs in reverse-alpha order to ensure os.walk would visit them
    # non-deterministically without our sorting fix.
    (tmp_path / "b").mkdir()
    (tmp_path / "a").mkdir()

    # Files named in reverse order within each dir, for the same reason.
    (tmp_path / "b" / "z.py").write_text("print('z')")
    (tmp_path / "b" / "y.py").write_text("print('y')")
    (tmp_path / "a" / "x.py").write_text("print('x')")
    (tmp_path / "a" / "w.py").write_text("print('w')")

    result = detect(tmp_path)
    code_files = result["files"]["code"]

    # Full repo-relative paths should arrive in sorted order:
    # a/w.py, a/x.py, b/y.py, b/z.py — not filesystem-dependent.
    relative = [str(Path(f).relative_to(tmp_path)) for f in code_files]
    assert relative == ["a/w.py", "a/x.py", "b/y.py", "b/z.py"], (
        f"Files were not detected in sorted order: {relative}"
    )
