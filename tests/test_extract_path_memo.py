"""extract()'s id remap and the call tie-break parse each distinct path once.

The remap resolved the same file paths once per input, once per stamped edge
and once per node, and `_path_proximity_winner` re-parsed every candidate's
directory on every ambiguous call site. Both now memoize; answers are unchanged.
"""
from __future__ import annotations

import sys
from pathlib import Path, PurePosixPath

import pytest

from graphify import paths as paths_mod
from graphify.extract import extract


def _corpus(root: Path) -> list[Path]:
    (root / "pkg").mkdir(parents=True)
    files = []
    for i in range(4):
        body = "".join(f"def f{i}_{j}():\n    return f{i}_{j + 1}()\n\n\n" for j in range(40))
        body += "".join(f"from pkg.m{k} import f{k}_0\n" for k in range(4) if k != i)
        p = root / "pkg" / f"m{i}.py"
        p.write_text(body, encoding="utf-8")
        files.append(p)
    (root / "pkg" / "__init__.py").write_text("", encoding="utf-8")
    return files + [root / "pkg" / "__init__.py"]


def test_extract_resolves_each_distinct_path_once(tmp_path: Path, monkeypatch):
    files = _corpus(tmp_path / "proj")
    calls: list[str] = []
    real_resolve = Path.resolve
    remap_frames = {"extract", "_decompose", "_resolved"}  # the id-remap code in extract()

    def counting_resolve(self, *args, **kwargs):
        if sys._getframe(1).f_code.co_name in remap_frames:
            calls.append(str(self))
        return real_resolve(self, *args, **kwargs)

    monkeypatch.setattr(Path, "resolve", counting_resolve)
    result = extract(files, root=tmp_path / "proj", cache_root=tmp_path / "cache", parallel=False)
    assert len(result["nodes"]) > 160  # every function became a node, so the per-node remap ran
    # Without the memo the remap resolved once per node and per stamped edge
    # (~200 calls here); with it, once per distinct path.
    assert len(calls) == len(set(calls)), f"{len(calls)} remap resolve calls for {len(set(calls))} paths"


@pytest.mark.parametrize(
    "site, candidates, expected",
    [
        ("pkg/a/x.py", {"1": "pkg/a/y.py", "2": "pkg/b/y.py"}, "1"),            # same dir
        ("pkg\\a\\x.py", {"1": "pkg/a/y.py", "2": "pkg/b/y.py"}, "1"),          # backslashes
        ("pkg/a/b/x.py", {"1": "pkg/a/y.py", "2": "other/y.py"}, "1"),          # longest prefix
        ("pkg/a/x.py", {"1": "pkg/b/y.py", "2": "pkg/c/y.py"}, None),           # tied prefix
        ("x.py", {"1": "y.py", "2": "z/y.py"}, "1"),                            # root-level file
        ("pkg/a/x.py", {"1": "pkg/a/x.py", "2": "pkg/a/y.py"}, "1"),            # same file
    ],
)
def test_proximity_winner_matches_a_fresh_parse(site, candidates, expected):
    paths_mod._parent_parts.cache_clear()
    assert paths_mod._path_proximity_winner(site, candidates) == expected
    # second call is served from the memo and must agree
    assert paths_mod._path_proximity_winner(site, candidates) == expected
    for f in candidates.values():
        assert paths_mod._parent_parts(f) == PurePosixPath(f.replace("\\", "/")).parent.parts
