"""A parked member call records its call-site file, relativized (#3152 issue 3).

`_park_unresolved_member_call` keeps an unresolved cross-repo call on the caller
node so a later merge can finish the edge. The call-site file (the `.m`) differs
from the caller node's own source_file (the `.h` where the method is declared),
and the raw_call carries it as an ABSOLUTE path. Left absolute it leaks the
checkout directory into graph.json — the same non-reproducibility class as the
category-id leak — and into the cross-repo edge built from it. The extract-time
source_file relativization pass now relativizes the parked `file` too.
"""
from __future__ import annotations

import importlib.util

import pytest

from graphify.extract import extract

pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("tree_sitter_objc") is None,
    reason="tree_sitter_objc not installed",
)


def _parked(result: dict) -> list[dict]:
    out: list[dict] = []
    for n in result["nodes"]:
        out.extend((n.get("metadata") or {}).get("unresolved_calls") or [])
    return out


def test_parked_call_site_file_is_repo_relative(tmp_path):
    src = tmp_path / "appB"
    src.mkdir()
    (src / "Host.h").write_text(
        "@interface Host : NSObject\n- (void)start;\n@end\n", encoding="utf-8")
    (src / "Host.m").write_text(
        '#import "Host.h"\n'
        "@implementation Host\n"
        "- (void)start {\n"
        "    Player *p = [[Player alloc] init];\n"
        "    [p play];\n"
        "}\n@end\n",
        encoding="utf-8")
    result = extract(sorted(src.glob("*")), root=src, cache_root=tmp_path / "c")

    play = [e for e in _parked(result) if e.get("callee") == "play"]
    assert play, "the call into the undeclared Player type should be parked"
    entry = play[0]
    assert entry["file"] == "Host.m"  # the call-site .m, not the caller's Host.h
    assert "private" not in entry["file"] and tmp_path.name not in entry["file"]
