"""Tests for the semantic ``source_file`` provenance invariant (#2217).

A semantic result's ``source_file`` is provenance: it is what tells a reader
which dispatched file a node came from. ``_out_of_scope`` (#1895) held only
attributions that resolved to an *existing* file outside the dispatched set, so
a path the model invented — one that exists nowhere — was admitted to the graph
while ``save_semantic_cache`` refused the identical attribution. These tests pin
the corrected rule: existence never decides admission, a *claimed* file does.
"""

import warnings
from pathlib import Path
from unittest.mock import patch

import pytest

from graphify.cache import save_semantic_cache
from graphify.llm import _claims_a_file, extract_corpus_parallel


def _run(files, result, tmp_path):
    """Drive extract_corpus_parallel with a faked per-chunk extraction result."""
    payload = {"input_tokens": 1, "output_tokens": 1, **result}
    payload.setdefault("edges", [])
    payload.setdefault("hyperedges", [])
    with patch("graphify.llm.extract_files_direct", side_effect=lambda c, **k: dict(payload)):
        return extract_corpus_parallel(
            files, backend="kimi", root=tmp_path,
            token_budget=None, chunk_size=len(files), max_concurrency=1,
        )


# ── _claims_a_file ────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "value",
    [
        "src/auth/session.py",      # the #2217 shape: assembled repo path
        "src\\auth\\session.py",    # Windows separators
        "docs/README.md",           # known doc extension
        "papers/paper.pdf",         # known paper extension
        "assets/diagram.png",       # known image extension
        "a/b/notes.DOCX",           # case-insensitive suffix match
    ],
)
def test_values_that_claim_a_file(value):
    assert _claims_a_file(value) is True


@pytest.mark.parametrize(
    "value",
    [
        # Concept markers #1895 deliberately preserves.
        "auth flow",
        "authentication",
        "React.Component",      # dotted, but ".component" is not a corpus extension
        "graphify v0.9.26",     # version suffix must not read as an extension
        "Section 3.2",
        "",
        "   ",
        # Slash-bearing prose. A separator alone must never imply a path: models
        # routinely put these in source_file, and treating them as file claims
        # deleted the nodes outright.
        "N/A",
        "TCP/IP",
        "CI/CD",
        "and/or",
        "I/O",
        "24/7",
        "input/output",
        "A/B testing",
        "client/server architecture",
        "read/write lock",
        # A corpus suffix alone must not imply a path either — these are
        # technology names, not files.
        "Node.js",
        "React.js",
        "Vue.js",
        "D3.js",
        "Objective.C",
        # Directory-shaped values. cache.py documents that subagent fragments
        # really do carry a directory here; it is malformed provenance, not a
        # fabricated file, and the base filter kept these.
        "src/auth",
        "src/auth/",
        "docs/",
    ],
)
def test_values_that_do_not_claim_a_file(value):
    assert _claims_a_file(value) is False


def test_slash_bearing_prose_and_directories_survive_the_filter(tmp_path):
    """End-to-end guard for the class above: these must reach the graph.

    A false positive here does not merely mislabel a node — it deletes it and
    cascade-drops every edge that touches it.
    """
    doc = tmp_path / "notes.md"
    doc.write_text("notes\n", encoding="utf-8")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "auth").mkdir()

    survivors = {
        "na": "N/A",
        "cicd": "CI/CD",
        "tcpip": "TCP/IP",
        "cs": "client/server architecture",
        "nodejs": "Node.js",
        "adir": "src/auth",
    }
    out = _run([doc], {"nodes": [
        {"id": "ok", "source_file": "notes.md", "file_type": "document"},
        *({"id": k, "source_file": v, "file_type": "concept"} for k, v in survivors.items()),
    ]}, tmp_path)

    assert {n["id"] for n in out["nodes"]} == {"ok", *survivors}
    assert out["out_of_scope_dropped"] == 0


def test_filter_is_a_superset_of_the_1895_existence_check(tmp_path):
    """The claim rule is an ADDITION to the existence check, never a replacement.

    A real corpus file that was not dispatched must still be dropped even when its
    name carries no corpus extension (`Makefile`, `LICENSE`, `pyproject.toml`).
    Replacing the existence arm silently re-admitted these while
    `save_semantic_cache` went on refusing them — reopening, for that class, the
    very graph-vs-cache divergence this change exists to close.
    """
    doc = tmp_path / "notes.md"
    doc.write_text("notes\n", encoding="utf-8")
    for name in ("Makefile", "LICENSE", "pyproject.toml", "data.csv"):
        (tmp_path / name).write_text("x\n", encoding="utf-8")

    out = _run([doc], {"nodes": [
        {"id": "ok", "source_file": "notes.md", "file_type": "document"},
        *({"id": n.lower(), "source_file": n, "file_type": "document"}
          for n in ("Makefile", "LICENSE", "pyproject.toml", "data.csv")),
    ]}, tmp_path)

    assert {n["id"] for n in out["nodes"]} == {"ok"}
    # Real files, so they are misattributions (#1895), not fabrications.
    assert out["provenance_dropped_misattributed"] == 4
    assert out["provenance_dropped_fabricated"] == 0


def test_duplicate_id_keeps_the_surviving_copys_edges(tmp_path):
    """Chunks are concatenated, so one id can appear twice in the merged result.

    If one copy is dropped and another survives, the id is still live. Pruning its
    edges would leave a correctly-attributed node stripped of every relationship —
    the hazard cache.py fixed for its own prune in #1916.
    """
    doc = tmp_path / "notes.md"
    doc.write_text("notes\n", encoding="utf-8")

    out = _run([doc], {
        "nodes": [
            {"id": "dup", "source_file": "notes.md", "file_type": "document"},
            {"id": "dup", "source_file": "src/auth/session.py", "file_type": "code"},
            {"id": "peer", "source_file": "notes.md", "file_type": "document"},
        ],
        "edges": [{"source": "dup", "target": "peer", "source_file": "notes.md"}],
        "hyperedges": [{"id": "h", "nodes": ["dup", "peer"], "source_file": "notes.md"}],
    }, tmp_path)

    assert out["provenance_dropped_fabricated"] == 1
    assert "dup" in {n["id"] for n in out["nodes"]}
    assert len(out["edges"]) == 1, "surviving duplicate lost its edge"
    assert len(out["hyperedges"]) == 1, "surviving duplicate lost its hyperedge"


def test_dirty_edge_is_filtered_even_when_no_node_is_dropped(tmp_path):
    """The prompt holds edges to the same source_file rule as nodes, and the cache
    groups them by their own source_file. Filtering them only when some node
    happened to be dropped left a clean-nodes/dirty-edge response unexamined."""
    doc = tmp_path / "notes.md"
    doc.write_text("notes\n", encoding="utf-8")

    out = _run([doc], {
        "nodes": [
            {"id": "a", "source_file": "notes.md", "file_type": "document"},
            {"id": "b", "source_file": "notes.md", "file_type": "document"},
        ],
        "edges": [
            {"source": "a", "target": "b", "source_file": "notes.md"},
            {"source": "a", "target": "b", "source_file": "src/auth/session.py"},
        ],
        "hyperedges": [
            {"id": "h_bad", "nodes": ["a", "b"], "source_file": "src/auth/session.py"},
        ],
    }, tmp_path)

    assert out["out_of_scope_dropped"] == 0, "no node should have been dropped"
    assert len(out["edges"]) == 1
    assert out["edges"][0]["source_file"] == "notes.md"
    assert out["hyperedges"] == []
    assert out["provenance_dropped_edges"] == 1
    assert out["provenance_dropped_hyperedges"] == 1


def test_unhashable_ids_do_not_abort_the_run(tmp_path):
    """Untrusted results really do put lists where scalars belong (#1631). The
    filter must degrade, not raise, after every chunk has already been paid for."""
    doc = tmp_path / "notes.md"
    doc.write_text("notes\n", encoding="utf-8")

    out = _run([doc], {
        "nodes": [
            {"id": ["a", "b"], "source_file": "src/auth/session.py", "file_type": "code"},
            {"id": "ok", "source_file": "notes.md", "file_type": "document"},
        ],
        "edges": [{"source": ["a"], "target": "ok", "source_file": "notes.md"}],
    }, tmp_path)

    assert "ok" in {str(n.get("id")) for n in out["nodes"]}


@pytest.mark.parametrize(
    "spelling",
    [
        " pkg/B.md ",     # surrounding whitespace
        "pkg/ B.md",      # whitespace after the separator
        "pkg\\B.md",      # Windows separators on a POSIX host
        " pkg\\B.md ",    # both
    ],
)
def test_alternate_spellings_of_a_dispatched_path_are_tolerated(tmp_path, spelling):
    """Both halves of the decision must canonicalise identically.

    `_claims_a_file` flips backslashes and strips segments. If the dispatched-set
    lookup does not, a node attributed to a genuinely dispatched file misses the
    set, misses is_file()/is_dir(), and is deleted as "fabricated" by the one half
    that did normalise — taking its edges with it.

    The path must be NESTED: a top-level ` notes.md ` can never reach the
    fabricated arm (no separator means `_claims_a_file` is False), so it would
    pass with the whole normalisation deleted. That earlier version of this test
    was green against code that had been removed entirely.
    """
    sub = tmp_path / "pkg"
    sub.mkdir()
    doc = sub / "B.md"
    doc.write_text("b\n", encoding="utf-8")

    out = _run([doc], {
        "nodes": [
            {"id": "ws", "source_file": spelling, "file_type": "document"},
            {"id": "peer", "source_file": "pkg/B.md", "file_type": "document"},
        ],
        "edges": [{"source": "ws", "target": "peer", "source_file": "pkg/B.md"}],
    }, tmp_path)

    assert {n["id"] for n in out["nodes"]} == {"ws", "peer"}, (
        f"{spelling!r} was not recognised as the dispatched pkg/B.md"
    )
    assert out["provenance_dropped_fabricated"] == 0
    assert len(out["edges"]) == 1, "the node's edge was cascade-dropped with it"


def test_directory_attribution_that_looks_like_a_file_is_kept(tmp_path):
    """Pins the `is_dir()` arm, which is otherwise unreachable in the suite.

    A value only reaches that arm when it BOTH claims a file and resolves to a
    directory, so it needs a directory named like one. Deleting the arm must fail
    a test rather than silently start dropping directory attributions.
    """
    doc = tmp_path / "notes.md"
    doc.write_text("notes\n", encoding="utf-8")
    weird = tmp_path / "docs" / "guide.md"
    weird.mkdir(parents=True)  # a DIRECTORY named guide.md

    out = _run([doc], {"nodes": [
        {"id": "ok", "source_file": "notes.md", "file_type": "document"},
        {"id": "dir", "source_file": "docs/guide.md", "file_type": "concept"},
    ]}, tmp_path)

    assert {n["id"] for n in out["nodes"]} == {"ok", "dir"}
    assert out["out_of_scope_dropped"] == 0


def test_url_shaped_source_file_is_not_a_fabrication(tmp_path):
    """A URL is a `source_url`, not a corpus path. Base kept these; a scheme is
    never evidence that a local file was claimed."""
    doc = tmp_path / "notes.md"
    doc.write_text("notes\n", encoding="utf-8")

    out = _run([doc], {"nodes": [
        {"id": "ok", "source_file": "notes.md", "file_type": "document"},
        {"id": "url", "source_file": "https://example.com/pkg/mod.py", "file_type": "document"},
    ]}, tmp_path)

    assert {n["id"] for n in out["nodes"]} == {"ok", "url"}
    assert out["out_of_scope_dropped"] == 0


def test_non_string_source_file_does_not_abort_the_run(tmp_path):
    """The #1631 class again, on the source_file field rather than the id."""
    doc = tmp_path / "notes.md"
    doc.write_text("notes\n", encoding="utf-8")

    out = _run([doc], {"nodes": [
        {"id": "ok", "source_file": "notes.md", "file_type": "document"},
        {"id": "weird", "source_file": ["a/b.py"], "file_type": "document"},
        {"id": "num", "source_file": 42, "file_type": "document"},
    ]}, tmp_path)

    assert "ok" in {n["id"] for n in out["nodes"]}


# ── The #2217 defect ──────────────────────────────────────────────────────────


def test_invented_nonexistent_source_file_is_dropped(tmp_path, capsys):
    """#2217: the model reconstructs a plausible repo path from a node id inside
    a document. The path exists nowhere and was never dispatched, so the old
    ``p.is_file()`` condition admitted it as a 'model-invented anchor'."""
    doc = tmp_path / "notes.md"
    doc.write_text("see src_auth_session_validate for details\n", encoding="utf-8")

    out = _run([doc], {
        "nodes": [
            {"id": "notes_ok", "source_file": "notes.md", "file_type": "document"},
            {"id": "ghost", "source_file": "src/auth/session.py", "file_type": "code"},
        ],
    }, tmp_path)

    ids = {n["id"] for n in out["nodes"]}
    assert "ghost" not in ids, "invented source_file reached the merged graph (#2217)"
    assert ids == {"notes_ok"}
    assert out["out_of_scope_dropped"] == 1
    assert out["provenance_dropped_fabricated"] == 1
    assert out["provenance_dropped_misattributed"] == 0
    assert "does not exist" in capsys.readouterr().err


def test_invented_attribution_cascades_to_edges_and_hyperedges(tmp_path):
    """A dropped node must not leave a dangling edge or hyperedge behind, and an
    edge/hyperedge carrying the invented attribution itself is dropped too."""
    doc = tmp_path / "notes.md"
    doc.write_text("notes\n", encoding="utf-8")

    out = _run([doc], {
        "nodes": [
            {"id": "notes_ok", "source_file": "notes.md", "file_type": "document"},
            {"id": "also_ok", "source_file": "notes.md", "file_type": "document"},
            {"id": "ghost", "source_file": "src/auth/session.py", "file_type": "code"},
        ],
        "edges": [
            {"source": "notes_ok", "target": "also_ok", "source_file": "notes.md"},
            # endpoint was dropped
            {"source": "notes_ok", "target": "ghost", "source_file": "notes.md"},
            # the edge itself carries the invented attribution
            {"source": "notes_ok", "target": "also_ok",
             "source_file": "src/auth/session.py"},
        ],
        "hyperedges": [
            {"id": "h_ok", "nodes": ["notes_ok", "also_ok"], "source_file": "notes.md"},
            {"id": "h_ghost", "nodes": ["notes_ok", "ghost"], "source_file": "notes.md"},
        ],
    }, tmp_path)

    node_ids = {n["id"] for n in out["nodes"]}
    assert "ghost" not in node_ids
    assert len(out["edges"]) == 1, f"dangling/invented edges survived: {out['edges']}"
    assert out["edges"][0]["target"] == "also_ok"
    assert [h["id"] for h in out["hyperedges"]] == ["h_ok"]


def test_misattributed_and_fabricated_are_counted_separately(tmp_path):
    """The two failure modes need different fixes, so they get different counters:
    a real file you can go read vs. a path with nothing behind it."""
    a = tmp_path / "A.md"; a.write_text("a\n", encoding="utf-8")
    real_undispatched = tmp_path / "B.py"
    real_undispatched.write_text("def b(): pass\n", encoding="utf-8")

    out = _run([a], {
        "nodes": [
            {"id": "a_ok", "source_file": "A.md", "file_type": "document"},
            {"id": "mis", "source_file": "B.py", "file_type": "code"},
            {"id": "fab", "source_file": "src/nope.py", "file_type": "code"},
        ],
    }, tmp_path)

    assert {n["id"] for n in out["nodes"]} == {"a_ok"}
    assert out["provenance_dropped_misattributed"] == 1
    assert out["provenance_dropped_fabricated"] == 1
    assert out["out_of_scope_dropped"] == 2


# ── What the invariant must NOT do ────────────────────────────────────────────


def test_concept_marker_source_file_still_survives(tmp_path):
    """Regression guard on the design choice. The literal invariant suggested in
    #2217 — every non-empty source_file must resolve into the dispatched set —
    deletes a concept node whose source_file is a bare phrase, which #1895
    deliberately kept (and which the #1895 test asserts). Only values that CLAIM
    a file are held to the dispatched set."""
    doc = tmp_path / "notes.md"
    doc.write_text("notes\n", encoding="utf-8")

    out = _run([doc], {
        "nodes": [
            {"id": "notes_ok", "source_file": "notes.md", "file_type": "document"},
            {"id": "auth_flow", "source_file": "auth flow", "file_type": "concept"},
            {"id": "no_anchor", "file_type": "concept"},
        ],
    }, tmp_path)

    assert {n["id"] for n in out["nodes"]} == {"notes_ok", "auth_flow", "no_anchor"}
    assert out["out_of_scope_dropped"] == 0


def test_dispatched_files_are_never_dropped(tmp_path, capsys):
    """A clean run must be untouched: no drops, no warning, counters at zero."""
    a = tmp_path / "A.md"; a.write_text("a\n", encoding="utf-8")
    sub = tmp_path / "pkg"; sub.mkdir()
    b = sub / "B.md"; b.write_text("b\n", encoding="utf-8")

    out = _run([a, b], {
        "nodes": [
            {"id": "a_ok", "source_file": "A.md", "file_type": "document"},
            # nested attribution, given relative to root exactly as spec'd
            {"id": "b_ok", "source_file": "pkg/B.md", "file_type": "document"},
        ],
    }, tmp_path)

    assert {n["id"] for n in out["nodes"]} == {"a_ok", "b_ok"}
    assert out["out_of_scope_dropped"] == 0
    assert out["provenance_dropped_fabricated"] == 0
    assert "out-of-scope" not in capsys.readouterr().err


# ── The property the bug violated ─────────────────────────────────────────────


def _cache_accepts(node: dict, doc: Path, tmp_path: Path, probe: Path) -> bool:
    """Whether ``save_semantic_cache`` (#1757) will persist *node*.

    Uses the documented return value — the number of entries written — rather
    than probing the on-disk layout, so the signal cannot silently go vacuous.
    """
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return save_semantic_cache(
            [dict(node)], [], [], root=tmp_path, cache_root=probe,
            allowed_source_files=[doc],
        ) > 0


def test_file_claiming_attributions_agree_with_the_cache(tmp_path):
    """The property whose violation caused #2217's non-convergence.

    ``save_semantic_cache`` (#1757) skips a group when ``not p.is_file() or p not
    in allowed``; the merged-graph filter used to apply only the second half. A
    node the graph admitted but the cache refused became a ghost: absent from the
    cache, it was re-extracted on every ``--update``, minting a *different* ghost
    each run.

    For every source_file that CLAIMS a file, graph admission and cache admission
    must now be the same decision. (Bare concept markers are deliberately outside
    this property: #1895 keeps them in the graph, while the cache — which is keyed
    by real file — has always skipped them. That divergence is pre-existing, is
    not a ghost, and is asserted separately below.)"""
    doc = tmp_path / "notes.md"
    doc.write_text("notes\n", encoding="utf-8")
    real_undispatched = tmp_path / "other.py"
    real_undispatched.write_text("x = 1\n", encoding="utf-8")

    file_claims = [
        {"id": "notes_ok", "source_file": "notes.md", "file_type": "document"},
        {"id": "ghost", "source_file": "src/auth/session.py", "file_type": "code"},
        {"id": "mis", "source_file": "other.py", "file_type": "code"},
    ]
    concept = {"id": "concept", "source_file": "auth flow", "file_type": "concept"}

    out = _run([doc], {"nodes": [dict(n) for n in file_claims + [concept]]}, tmp_path)
    survivors = {n["id"] for n in out["nodes"]}

    for i, node in enumerate(file_claims):
        in_graph = node["id"] in survivors
        in_cache = _cache_accepts(node, doc, tmp_path, tmp_path / f"probe{i}")
        assert in_graph == in_cache, (
            f"{node['id']!r} ({node['source_file']!r}): graph={in_graph} "
            f"cache={in_cache} — the #2217 divergence"
        )

    # Sanity: the probe distinguishes accept from refuse (guards against a
    # vacuously-passing loop where the cache refuses everything).
    assert _cache_accepts(file_claims[0], doc, tmp_path, tmp_path / "probe_ok") is True
    assert _cache_accepts(file_claims[1], doc, tmp_path, tmp_path / "probe_bad") is False

    # The documented exception, pinned so it stays deliberate.
    assert concept["id"] in survivors
    assert _cache_accepts(concept, doc, tmp_path, tmp_path / "probe_concept") is False
