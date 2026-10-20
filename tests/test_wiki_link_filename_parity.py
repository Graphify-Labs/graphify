"""Regression tests for issue #2597: a wiki link's target must BE the on-disk
filename, byte for byte.

`_md_link` percent-encoded the slug (`_make_id%28%29.md`) while `to_wiki` wrote
the file raw (`_make_id().md`), so every article whose label contained `(`, `)`,
`&` or a non-ASCII character was linked at a path that does not exist. Renderers
hid it by decoding before resolving, but the wiki's stated purpose is to be
agent-crawlable, and an agent that reads the target off disk verbatim gets a
FileNotFoundError. Function-named nodes (`foo()`) make this common in any code
repo — 27 of 1141 links on a 2247-node graph.

The invariant these tests pin down: for every inline link the wiki emits,
`(wiki_dir / target).exists()` is true WITHOUT any unquoting step.
"""
import re

import networkx as nx
import pytest

from graphify.wiki import _safe_filename, to_wiki

# Deliberately does not decode: the target is compared exactly as written.
# Key on the `](target)` boundary rather than the whole `[display](target)` so a
# display text that itself contains brackets (e.g. `Array[T] Models`) is still
# captured — a display-anchored regex silently skips those links, making the
# bracket case a vacuous pass. Wiki targets never contain `)` (parens are dropped
# from the slug) or whitespace (spaces become `_`), so `[^)\s]+` is exact.
_MD_TARGET = re.compile(r"\]\(([^)\s]+)\)")


def _targets(text: str) -> list[str]:
    return [t for t in _MD_TARGET.findall(text) if "://" not in t]


def _wiki(tmp_path, labels: dict[int, str], god: list[dict] | None = None):
    G = nx.Graph()
    communities: dict[int, list[str]] = {}
    for cid in labels:
        nid = f"n{cid}"
        G.add_node(nid, label=f"sym{cid}", file_type="code",
                   source_file=f"m{cid}.py", community=cid)
        communities[cid] = [nid]
    ids = list(G.nodes)
    for a, b in zip(ids, ids[1:]):
        G.add_edge(a, b, relation="references", confidence="INFERRED", weight=1.0)
    out = tmp_path / "wiki"
    to_wiki(G, communities, out, community_labels=labels, god_nodes_data=god or [])
    return out


def _assert_every_link_resolves(out) -> int:
    seen = 0
    for md in out.glob("*.md"):
        for target in _targets(md.read_text(encoding="utf-8")):
            seen += 1
            assert (out / target).exists(), (
                f"{md.name}: link target {target!r} does not exist on disk"
            )
    assert seen, "expected the wiki to emit inline links"
    return seen


# ---------------------------------------------------------------------------
# The character classes from the report
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "label",
    [
        "load_traumas()",                                   # the common case: any callable
        "__init__()",                                       # dunder must survive paren removal
        "Forgejo upgrade & rollback (runbook)",             # & plus parens
        "Tailscale HTTPS endpoints — how services get URLs",  # em dash (non-ASCII)
        "C# & Auth (v2)",                                   # # would be read as a fragment
        "100% coverage",                                    # % would read as a percent-escape
        "文档 索引",                                          # CJK must not be reduced to noise
        "Array[T] Models",                                  # brackets are legal in a destination
    ],
)
def test_link_target_is_the_filename_verbatim(tmp_path, label):
    out = _wiki(tmp_path, {0: label, 1: "Other"})
    _assert_every_link_resolves(out)


def test_no_link_target_is_percent_encoded(tmp_path):
    out = _wiki(tmp_path, {0: "Forgejo upgrade & rollback (runbook)", 1: "Other"})
    for md in out.glob("*.md"):
        for target in _targets(md.read_text(encoding="utf-8")):
            assert "%" not in target, f"{md.name}: target still encoded: {target}"


# ---------------------------------------------------------------------------
# _safe_filename's own guarantees
# ---------------------------------------------------------------------------

def test_slug_drops_parens_without_mangling_dunders():
    # Substituting "(" / ")" with "_" would leave "__init______"; collapsing the
    # runs afterwards would corrupt the dunder to "_init_". Dropping does neither.
    assert _safe_filename("__init__()") == "__init__"
    assert _safe_filename("load_traumas()") == "load_traumas"


def test_slug_has_nothing_that_needs_url_encoding():
    from urllib.parse import quote
    for label in [
        "load_traumas()", "C# & Auth (v2)", "100% coverage",
        "Forgejo upgrade & rollback (runbook)", "a/b:c*d?e", 'q"uote', "ctrl\x07char",
    ]:
        slug = _safe_filename(label)
        # `&` and friends are legal raw in a link destination; the ones that are
        # NOT must be gone, so quoting with them marked safe is a no-op.
        assert quote(slug, safe="&+,;=@$!'~[]") == slug, (label, slug)


def test_slug_keeps_non_ascii():
    # Stripping non-ASCII would reduce a CJK or Cyrillic wiki to underscores.
    assert _safe_filename("文档 索引") == "文档_索引"
    assert _safe_filename("Ünicode Straße") == "Ünicode_Straße"


def test_slug_still_strips_windows_reserved_characters():
    slug = _safe_filename('a<b>c:d"e/f\\g|h?i*j')
    for ch in '<>:"/\\|?*':
        assert ch not in slug, (ch, slug)


def test_distinct_labels_collapsing_to_one_slug_stay_distinct(tmp_path):
    # "parse()" and "parse" both slug to "parse"; _unique_slug must separate them.
    out = _wiki(tmp_path, {0: "parse()", 1: "parse", 2: "Other"})
    _assert_every_link_resolves(out)
    names = sorted(p.name for p in out.glob("*.md"))
    assert len(names) == len(set(names))
    assert "parse.md" in names and "parse_2.md" in names, names


# ---------------------------------------------------------------------------
# The whole-wiki guard, on a graph shaped like a real code repo
# ---------------------------------------------------------------------------

def test_whole_wiki_has_no_dangling_link_with_callable_god_nodes(tmp_path):
    G = nx.Graph()
    for i, lab in enumerate(["_make_id()", "_read_text()", "__init__()", "Path"]):
        G.add_node(f"g{i}", label=lab, file_type="code",
                   source_file=f"src/m{i}.py", community=i % 2)
    ids = list(G.nodes)
    for a in ids:
        for b in ids:
            if a != b:
                G.add_edge(a, b, relation="calls", confidence="EXTRACTED", weight=1.0)
    god = [{"id": n, "label": G.nodes[n]["label"], "degree": G.degree(n)} for n in ids]
    out = tmp_path / "wiki"
    to_wiki(G, {0: ["g0", "g2"], 1: ["g1", "g3"]}, out,
            community_labels={0: "Ident & IDs (core)", 1: "I/O — helpers"},
            god_nodes_data=god)
    assert _assert_every_link_resolves(out) > 5
