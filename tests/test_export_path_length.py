"""Regression tests for issue #2655: export filename caps must respect the
DESTINATION PATH length, not only the per-component NAME_MAX.

#1094 capped export stems at 200 bytes so they stay under the conventional
255-byte NAME_MAX. That is the correct constraint on POSIX and the wrong one on
Windows, where the limit applies to the WHOLE path (MAX_PATH = 260 chars
including the terminating NUL). A 200-byte stem under an ordinary vault
directory therefore overruns MAX_PATH, and `graphify export obsidian` /
`export wiki` die mid-write with FileNotFoundError, leaving a half-written
vault behind.

The budget math is exercised on every platform by faking `os.name`, and the
exporters' wiring is exercised by forcing a small budget, so this suite has
real teeth on the Linux CI runners as well as on Windows.
"""
import json
import os
import re

import networkx as nx
import pytest

from graphify import export as export_mod
from graphify import wiki as wiki_mod
from graphify.export import _obsidian_safe_stem, to_canvas, to_obsidian
from graphify.paths import _MIN_STEM_BUDGET, _WINDOWS_MAX_PATH, stem_filename_budget
from graphify.wiki import _safe_filename, to_wiki


def _graph(labels: list[str]) -> tuple[nx.Graph, dict[int, list[str]]]:
    G = nx.Graph()
    ids = []
    for i, lab in enumerate(labels):
        nid = f"n{i}"
        G.add_node(nid, label=lab, file_type="code", source_file="x.py", community=0)
        ids.append(nid)
    for a, b in zip(ids, ids[1:]):
        G.add_edge(a, b, relation="calls", confidence="EXTRACTED")
    return G, {0: ids}


def _fake_windows(monkeypatch):
    """Make stem_filename_budget take its Windows branch on any host.

    abspath becomes identity so a literal ``C:\\...`` string is not prefixed
    with the POSIX cwd when the test runs on Linux.
    """
    monkeypatch.setattr(os, "name", "nt")
    monkeypatch.setattr(os.path, "abspath", lambda p: str(p))


# ---------------------------------------------------------------------------
# stem_filename_budget: the budget math
# ---------------------------------------------------------------------------

def test_budget_is_untouched_on_posix(monkeypatch):
    monkeypatch.setattr(os, "name", "posix")
    # Even an absurdly deep directory must not change POSIX behaviour: the
    # constraint there is per-component, and existing vaults must stay stable.
    assert stem_filename_budget("/" + "d/" * 200, reserve=4) == 200


def test_budget_shrinks_so_the_whole_path_fits_max_path(monkeypatch):
    _fake_windows(monkeypatch)
    vault = r"C:\Users\dev\projects\payments-api\graphify-out\obsidian"
    budget = stem_filename_budget(vault, reserve=4)

    assert budget < 200, "an ordinary vault path must shrink the 200-byte default"
    # The longest name this budget can produce still has to fit in MAX_PATH.
    longest = len(vault) + len(os.sep) + budget + len("_999") + len(".md")
    assert longest < _WINDOWS_MAX_PATH


def test_budget_accounts_for_the_caller_reserve(monkeypatch):
    _fake_windows(monkeypatch)
    vault = r"C:\Users\dev\projects\payments-api\graphify-out\obsidian"
    assert stem_filename_budget(vault, reserve=4) - stem_filename_budget(vault, reserve=15) == 11


def test_budget_never_exceeds_the_requested_limit(monkeypatch):
    _fake_windows(monkeypatch)
    # A very short root leaves plenty of room; the NAME_MAX-derived limit still wins.
    assert stem_filename_budget("C:\\", reserve=0) == 200


def test_budget_floors_instead_of_going_negative(monkeypatch):
    _fake_windows(monkeypatch)
    deep = "C:\\" + "\\".join("dir%03d" % i for i in range(40))
    assert len(deep) > _WINDOWS_MAX_PATH
    # A negative budget would make _cap_filename slice with a negative index and
    # silently emit a garbage stem, so the floor matters.
    assert stem_filename_budget(deep, reserve=4) == _MIN_STEM_BUDGET


def test_budget_ignores_extended_length_paths(monkeypatch):
    _fake_windows(monkeypatch)
    # "\\?\" opts the path out of MAX_PATH entirely - nothing to shrink.
    assert stem_filename_budget(r"\\?\C:\very\deep" + "\\x" * 100, reserve=4) == 200


# ---------------------------------------------------------------------------
# The stem helpers honour an explicit limit
# ---------------------------------------------------------------------------

def test_obsidian_stem_honours_an_explicit_limit():
    stem = _obsidian_safe_stem("a" * 300, 60)
    assert len(stem.encode("utf-8")) <= 60


def test_obsidian_stem_stays_collision_safe_at_a_small_limit():
    prefix = "z" * 250
    a = _obsidian_safe_stem(prefix + "_ALPHA", 40)
    b = _obsidian_safe_stem(prefix + "_BETA", 40)
    assert a != b, "truncation dropped the only distinguishing bytes"
    assert len(a.encode("utf-8")) <= 40 and len(b.encode("utf-8")) <= 40


def test_wiki_safe_filename_honours_an_explicit_limit():
    assert len(_safe_filename("w" * 300, 60)) <= 60


# ---------------------------------------------------------------------------
# The exporters actually thread the budget through (runs on every platform)
# ---------------------------------------------------------------------------

def test_obsidian_respects_a_small_budget_and_links_still_resolve(tmp_path, monkeypatch):
    monkeypatch.setattr(export_mod, "stem_filename_budget", lambda out, **kw: 40 - kw.get("reserve", 0))
    G, comms = _graph(["a" * 300, "b" * 300, "neighbor"])
    to_obsidian(G, comms, str(tmp_path))

    written = list(tmp_path.glob("*.md"))
    assert len(written) == 4, [p.name for p in written]  # 3 nodes + 1 community
    for p in written:
        assert len(p.stem) <= 40, p.name

    stems = {p.stem for p in written}
    for p in written:
        for target in re.findall(r"\[\[([^\]|]+)", p.read_text(encoding="utf-8")):
            assert target in stems, f"dangling wikilink {target!r} in {p.name}"


def test_canvas_card_refs_match_the_notes_under_a_small_budget(tmp_path, monkeypatch):
    monkeypatch.setattr(export_mod, "stem_filename_budget", lambda out, **kw: 40 - kw.get("reserve", 0))
    G, comms = _graph(["a" * 300, "b" * 300])
    to_obsidian(G, comms, str(tmp_path))
    # The CLI calls to_canvas without the node_filenames map, so the canvas has
    # to re-derive the same budget or every card points at a missing note.
    to_canvas(G, comms, str(tmp_path / "graph.canvas"))

    data = json.loads((tmp_path / "graph.canvas").read_text(encoding="utf-8"))
    refs = [n["file"] for n in data["nodes"] if n.get("type") == "file"]
    assert refs
    for ref in refs:
        assert (tmp_path / ref).exists(), f"canvas card points at missing note: {ref}"


def test_wiki_respects_a_small_budget(tmp_path, monkeypatch):
    monkeypatch.setattr(wiki_mod, "stem_filename_budget", lambda out, **kw: 40 - kw.get("reserve", 0))
    G, comms = _graph(["a" * 300, "b" * 300])
    out = tmp_path / "wiki"
    to_wiki(G, comms, str(out), community_labels={0: "L" * 300})

    written = list(out.glob("*.md"))
    assert written
    for p in written:
        assert len(p.stem) <= 40, p.name


def test_wiki_multibyte_labels_stay_within_budget_and_links_resolve(tmp_path, monkeypatch):
    """A CJK label at a tight budget: the stem must stay within budget counted in
    CHARACTERS (wiki slices by character), links must resolve on disk, and the
    non-ASCII characters must survive rather than being reduced to underscores."""
    monkeypatch.setattr(wiki_mod, "stem_filename_budget", lambda out, **kw: 40 - kw.get("reserve", 0))
    G, comms = _graph(["文档索引" * 50, "配置解析器" * 50])
    out = tmp_path / "wiki"
    to_wiki(G, comms, str(out), community_labels={0: "模块" * 100})

    written = list(out.glob("*.md"))
    assert written
    import re
    target_re = re.compile(r"\]\(([^)\s]+)\)")
    for p in written:
        if p.name != "index.md":  # index is a fixed filename, not a label slug
            # 40-char window: the stem is capped at 40 - reserve, and a collision
            # suffix can add back up to the reserve, so the whole stem stays <= 40.
            assert len(p.stem) <= 40, p.name
            assert any("一" <= ch <= "鿿" for ch in p.stem), f"CJK stripped from {p.name}"
        for target in target_re.findall(p.read_text(encoding="utf-8")):
            if "://" in target:
                continue
            assert (out / target).exists(), f"{p.name}: dangling link {target!r}"


# ---------------------------------------------------------------------------
# End-to-end on the platform that actually has the ceiling
# ---------------------------------------------------------------------------

_WINDOWS_ONLY = pytest.mark.skipif(
    os.name != "nt", reason="MAX_PATH is a Windows constraint"
)


@_WINDOWS_ONLY
def test_obsidian_writes_paths_inside_max_path(tmp_path):
    G, comms = _graph(["a" * 300, "short"])
    to_obsidian(G, comms, str(tmp_path))
    written = list(tmp_path.glob("*.md"))
    assert written
    for p in written:
        assert len(str(p)) < _WINDOWS_MAX_PATH, f"{len(str(p))} chars: {p}"


@_WINDOWS_ONLY
def test_wiki_writes_paths_inside_max_path(tmp_path):
    G, comms = _graph(["a" * 300, "short"])
    out = tmp_path / "wiki"
    to_wiki(G, comms, str(out), community_labels={0: "C" * 300})
    written = list(out.glob("*.md"))
    assert written
    for p in written:
        assert len(str(p)) < _WINDOWS_MAX_PATH, f"{len(str(p))} chars: {p}"


@_WINDOWS_ONLY
def test_canvas_card_targets_exist_inside_max_path(tmp_path):
    G, comms = _graph(["a" * 300, "short"])
    to_obsidian(G, comms, str(tmp_path))
    to_canvas(G, comms, str(tmp_path / "graph.canvas"))
    data = json.loads((tmp_path / "graph.canvas").read_text(encoding="utf-8"))
    for node in data["nodes"]:
        if node.get("type") == "file":
            assert (tmp_path / node["file"]).exists(), node["file"]
