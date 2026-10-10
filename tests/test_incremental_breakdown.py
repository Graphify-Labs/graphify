"""Boundary summaries reuse the incremental file set, without rescanning."""
from graphify import detect
from tools.skillgen import gen


def test_breakdown_large_change_groups_count_and_bytes(tmp_path):
    paths = []
    for name, content in [("vendor/a.md", "abc"), ("vendor/b.md", "defgh"), ("src/a.py", "x"), ("README.md", "hi")]:
        p = tmp_path / name
        p.parent.mkdir(exist_ok=True)
        p.write_text(content, encoding="utf-8")
        paths.append(str(p))
    result = {"scan_root": str(tmp_path), "total_files": 6, "new_total": 4, "new_files": {"document": paths}}
    assert detect.summarize_incremental_changes(result) == [
        {"directory": "vendor", "files": 2, "bytes": 8},
        {"directory": "(root)", "files": 1, "bytes": 2},
        {"directory": "src", "files": 1, "bytes": 1},
    ]


def test_breakdown_only_when_more_than_half_changed():
    for total, changed in [(0, 0), (10, 0), (10, 5), (10, 4)]:
        assert detect.summarize_incremental_changes({"total_files": total, "new_total": changed}) == []


def test_breakdown_limits_deduplicates_and_tolerates_disappearing_files(tmp_path):
    files = []
    for i in range(8):
        p = tmp_path / f"dir{i}" / "gone.md"
        files.append(str(p))
    result = {"scan_root": str(tmp_path), "total_files": 8, "new_total": 8, "new_files": {"document": files + files, "code": [str(tmp_path.parent / "outside.py")]}}
    assert detect.summarize_incremental_changes(result) == [
        {"directory": f"dir{i}", "files": 1, "bytes": 0} for i in range(5)
    ]


def test_breakdown_supports_relative_scan_paths(tmp_path):
    p = tmp_path / "data" / "a.md"
    p.parent.mkdir()
    p.write_text("abc")
    r = {"scan_root": str(tmp_path), "total_files": 1, "new_total": 1, "new_files": {"document": ["data/a.md"]}}
    assert detect.summarize_incremental_changes(r) == [{"directory": "data", "files": 1, "bytes": 3}]


def test_update_skill_surfaces_boundaries_before_dispatch_in_all_hosts():
    for key, platform in gen.load_platforms().items():
        artifacts = gen.render(platform)
        body = "\n".join(a.content for a in artifacts if str(a.path).endswith("update.md") or "skill" in str(a.path))
        assert "summarize_incremental_changes(result)" in body, key
        assert body.index("summarize_incremental_changes(result)") < body.index("code_only ="), key
        assert "before any semantic dispatch" in body, key
        assert "rerun detection" in body, key


def test_breakdown_does_not_rescan_or_stat_outside_boundary(tmp_path, monkeypatch):
    import os
    p = tmp_path / "src/a.py"
    p.parent.mkdir()
    p.write_text("x")
    outside = tmp_path.parent / "outside.py"
    original_os_path = detect._os_path
    def bounded_os_path(path):
        assert path.is_relative_to(tmp_path)
        return original_os_path(path)
    def forbidden_walk(*args, **kwargs):
        raise AssertionError("summary must not rescan")
    monkeypatch.setattr(os, "walk", forbidden_walk)
    r = {"scan_root": str(tmp_path), "total_files": 1, "new_total": 1, "new_files": {"code": [str(p), str(outside)]}}
    monkeypatch.setattr(detect, "_os_path", bounded_os_path)
    assert detect.summarize_incremental_changes(r) == [{"directory": "src", "files": 1, "bytes": 1}]
    assert detect.summarize_incremental_changes(r, limit=0) == []
