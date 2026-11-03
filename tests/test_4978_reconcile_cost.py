"""Hypothesis tests for #4978: reconcile asks a per-file question once per node.

Two questions are kept apart on purpose:

  cost     how often the question is asked, and how many bytes a miss reads
  meaning  whether any keep/evict decision changes

A variant that is cheap and wrong fails the differential test. A variant that is
correct and slow fails the cost test. Neither column alone picks the fix.

Variants under test
  base          today's code
  cache         H1  memoize the real answer per resolved path
  capped        H4  sniff the first 256 KiB instead of the whole file
  capped_cache  H1 + H4
  cheap         H7  ask "is this source AST-owned" instead of "which extractor"
  cheap_cache   H1 + H7
"""

from __future__ import annotations

import functools
import json
import shutil
import sys
from collections import Counter
from pathlib import Path

import pytest

import graphify.extract as ex
from graphify.build import _backfill_origin
from graphify.watch import _rebuild_code

CAP = 256 * 1024


def _for(counter: Counter, suffix: str) -> int:
    return sum(v for k, v in counter.items() if k.endswith(suffix))


# ---------------------------------------------------------------------------
# one file per ambiguity in _get_extractor's dispatch
# ---------------------------------------------------------------------------
FIXTURES = {
    "plain.h": b"int f(int a);\nstruct s { int b; };\n",
    "cpp.h": b"class Foo { public: int x(); };\nnamespace n { struct Y { }; }\n",
    "objc.h": b"@interface Widget\n@property int x;\n@end\n",
    "matlab.m": b"function y = f(x)\ny = x + 1;\nend\n",
    "objc.m": b"#import <Foundation/Foundation.h>\n@implementation App\n@end\n",
    "objcpp.mm": b"@interface A\n@end\n",
    "plain.c": b"int g(void) { return 1; }\n",
    "doc.pdf": b"%PDF-1.4\nnot really a pdf\n",
    "doc.txt": b"prose\n",
    "view.blade.php": b"<div>{{ $x }}</div>\n",
    "pyproject.toml": b'[project]\nname = "x"\n',
    ".mcp.json": b'{"mcpServers": {}}\n',
    "runtool": b"#!/usr/bin/env bash\necho hi\n",
    "noext": b"plain text, no shebang\n",
}


def _write_fixtures(root: Path) -> dict[str, Path]:
    root.mkdir(parents=True, exist_ok=True)
    out = {}
    for name, body in FIXTURES.items():
        p = root / name
        p.write_bytes(body)
        out[name] = p
    return out


# ---------------------------------------------------------------------------
# H7: the caller asks a weaker question than _get_extractor answers
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("name", ["plain.h", "cpp.h", "objc.h"])
def test_h7_every_h_dialect_is_ast_owned(tmp_path, name):
    """.h can never be None, so the sniff cannot change what reconcile reads."""
    paths = _write_fixtures(tmp_path / "f")
    extractor = ex._get_extractor(paths[name])
    assert extractor is not None
    assert getattr(extractor, "__name__", "").startswith("extract_")


def test_h7_m_is_the_only_suffix_where_the_sniff_decides_none_ness(tmp_path):
    """.m can be None (MATLAB), which is why a cheap predicate must keep it."""
    paths = _write_fixtures(tmp_path / "f")
    assert ex._get_extractor(paths["matlab.m"]) is None
    assert ex._get_extractor(paths["objc.m"]) is not None
    assert ex._get_extractor(paths["objcpp.mm"]) is not None


def _cheap_ast_owned(path: Path) -> bool:
    """Same None-ness as _get_extractor, minus the .h sniff."""
    if path.name.lower().endswith(".blade.php"):
        return True
    if ex.is_mcp_config_path(path):
        return True
    if ex.is_package_manifest_path(path):
        return True
    remapped = ex.effective_suffix(path)
    if remapped != path.suffix:
        got = ex._DISPATCH.get(remapped) or ex._DISPATCH.get(remapped.lower())
        return got is not None
    suffix = path.suffix
    if suffix not in ex._DISPATCH and suffix.lower() in ex._DISPATCH:
        suffix = suffix.lower()
    if suffix == ".m":
        return ex._is_objc_source(path)
    if not suffix:
        from graphify.detect import _shebang_interpreter

        return ex._SHEBANG_DISPATCH.get(_shebang_interpreter(path)) is not None
    return ex._DISPATCH.get(suffix) is not None


def test_h7_cheap_predicate_matches_get_extractor_everywhere(tmp_path):
    paths = _write_fixtures(tmp_path / "f")
    for name, path in paths.items():
        real = ex._get_extractor(path) is not None
        assert _cheap_ast_owned(path) == real, f"{name}: cheap != real"


def test_h7_cheap_predicate_follows_a_graphifyrc_remap(tmp_path, monkeypatch):
    paths = _write_fixtures(tmp_path / "f")
    monkeypatch.setattr(ex, "effective_suffix", lambda p: ".unmapped")
    for name in ("plain.h", "cpp.h"):
        assert _cheap_ast_owned(paths[name]) is False
        assert (ex._get_extractor(paths[name]) is None) is True


def test_h7_cheap_predicate_reads_nothing_for_h(tmp_path, monkeypatch):
    paths = _write_fixtures(tmp_path / "f")
    reads = Counter()
    real_read_bytes = Path.read_bytes

    def counting(self):
        reads[str(self)] += 1
        return real_read_bytes(self)

    monkeypatch.setattr(Path, "read_bytes", counting)

    _cheap_ast_owned(paths["plain.h"])
    assert reads[str(paths["plain.h"])] == 0

    ex._get_extractor(paths["plain.h"])
    assert reads[str(paths["plain.h"])] == 2, "two sniffs per call, one read each"


# ---------------------------------------------------------------------------
# H4: reading only the used bytes cannot change the answer
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("size", [0, 1, CAP - 1, CAP, CAP + 1, 1024 * 1024])
def test_h4_capped_read_is_byte_identical(tmp_path, size):
    p = tmp_path / "blob.h"
    p.write_bytes(bytes((i * 7) % 251 for i in range(size)))
    with open(p, "rb") as fh:
        assert p.read_bytes()[:CAP] == fh.read(CAP)


def test_h4_capped_read_preserves_sniff_answers(tmp_path):
    paths = _write_fixtures(tmp_path / "f")
    late_cpp = tmp_path / "late_cpp.h"
    late_cpp.write_bytes(b"/* pad */\n" * 40000 + b"class Late { };\n")
    late_objc = tmp_path / "late_objc.h"
    late_objc.write_bytes(b"/* pad */\n" * 40000 + b"@interface Late\n@end\n")

    def capped(path, markers):
        try:
            with open(path, "rb") as fh:
                head = fh.read(CAP)
        except OSError:
            return False
        return any(m in head for m in markers)

    for p in [*paths.values(), late_cpp, late_objc]:
        assert ex._is_objc_header(p) == capped(p, ex._OBJC_HEADER_MARKERS), p.name
        assert ex._is_cpp_header(p) == capped(p, ex._CPP_HEADER_MARKERS), p.name


# ---------------------------------------------------------------------------
# H2: a path-keyed global cache is wrong in a long-lived watcher
# ---------------------------------------------------------------------------
def test_h2_path_keyed_global_cache_serves_a_stale_answer(tmp_path):
    p = tmp_path / "x.h"
    p.write_bytes(b"int f(int a);\n")
    cached = functools.lru_cache(maxsize=None)(ex._get_extractor)

    before = cached(p)
    assert before is ex._get_extractor(p)

    p.write_bytes(b"@interface W\n@end\n")

    assert cached(p) is before, "the cache keeps answering extract_c"
    assert ex._get_extractor(p) is not before, "while the file is now Objective-C"


# ---------------------------------------------------------------------------
# a latent bug the suite found: sniffing depends on the process CWD
# ---------------------------------------------------------------------------
def test_sniff_silently_fails_when_the_cwd_is_outside_the_project(tmp_path, monkeypatch):
    paths = _write_fixtures(tmp_path / "f")
    monkeypatch.chdir(tmp_path / "f")
    assert ex._is_cpp_header(Path("cpp.h")) is True

    monkeypatch.chdir(tmp_path)
    assert ex._is_cpp_header(Path("cpp.h")) is False, "OSError swallowed, markers missed"
    assert ex._get_extractor(Path("cpp.h")) is ex._DISPATCH[".h"]


# ---------------------------------------------------------------------------
# pipeline: real _rebuild_code, instrumented per variant
# ---------------------------------------------------------------------------
HEADER_FUNCS = 60


def _make_corpus(root: Path) -> Path:
    corpus = root / "corpus"
    corpus.mkdir(parents=True)
    (corpus / "app.py").write_text("def one():\n    pass\n\ndef two():\n    pass\n")
    lines = ["#ifndef BIG_H\n#define BIG_H\n"]
    lines += [f"static inline int hf{i}(int a) {{ return a + {i}; }}\n" for i in range(HEADER_FUNCS)]
    lines.append("#endif\n")
    (corpus / "big.h").write_text("".join(lines))
    (corpus / "gone.c").write_text("int gone(void) { return 0; }\n")
    (corpus / "sub").mkdir()
    (corpus / "sub" / "b.c").write_text("int b(void) { return 1; }\n")
    return corpus


def _snapshot(corpus: Path) -> Path:
    snap = corpus.parent / "snap"
    shutil.copytree(corpus, snap)
    return snap


def _restore(corpus: Path, snap: Path) -> None:
    shutil.rmtree(corpus)
    shutil.copytree(snap, corpus)


def _apply_standard_change(corpus: Path) -> None:
    (corpus / "app.py").write_text(
        "def one():\n    pass\n\ndef two():\n    pass\n\ndef three():\n    pass\n"
    )
    (corpus / "gone.c").unlink()


def _node_ids(corpus: Path) -> list[str]:
    data = json.loads((corpus / "graphify-out" / "graph.json").read_text())
    return sorted(n["id"] for n in data["nodes"])


def _header_nodes(corpus: Path) -> int:
    data = json.loads((corpus / "graphify-out" / "graph.json").read_text())
    return sum(1 for n in data["nodes"] if str(n.get("source_file", "")).endswith("big.h"))


def _caller_is_reconcile() -> bool:
    frame = sys._getframe(1)
    for _ in range(8):
        if frame is None:
            return False
        if frame.f_code.co_name == "_reconcile_existing_graph":
            return True
        frame = frame.f_back
    return False


class Probe:
    def __init__(self) -> None:
        self.calls: Counter[str] = Counter()
        self.reconcile_calls: Counter[str] = Counter()
        self.reconcile_real: Counter[str] = Counter()
        self.reconcile_reads: Counter[str] = Counter()
        self.reconcile_bytes: Counter[str] = Counter()
        self._active: str | None = None

    def install(self, monkeypatch, variant: str) -> None:
        real_get = ex._get_extractor
        real_read_bytes = Path.read_bytes
        probe = self
        cache: dict[str, object] = {}

        def get(path):
            p = Path(path)
            key = str(p)
            reconcile = _caller_is_reconcile()
            probe.calls[key] += 1
            if not reconcile:
                return real_get(p)

            probe.reconcile_calls[key] += 1

            if variant.startswith("cheap"):
                return True if _cheap_ast_owned(p) else None

            cache_key = str(p.resolve())
            if "cache" in variant and cache_key in cache:
                return cache[cache_key]

            probe.reconcile_real[key] += 1
            probe._active = key
            try:
                value = real_get(p)
            finally:
                probe._active = None

            if "cache" in variant:
                cache[cache_key] = value
            return value

        def counting_read_bytes(self):
            data = real_read_bytes(self)
            if probe._active is not None:
                probe.reconcile_reads[probe._active] += 1
                probe.reconcile_bytes[probe._active] += len(data)
            return data

        if variant.startswith("capped"):

            def capped(path, markers):
                try:
                    with open(path, "rb") as fh:
                        head = fh.read(CAP)
                except OSError:
                    return False
                if probe._active is not None:
                    probe.reconcile_reads[probe._active] += 1
                    probe.reconcile_bytes[probe._active] += len(head)
                return any(m in head for m in markers)

            monkeypatch.setattr(ex, "_is_objc_header", lambda p: capped(p, ex._OBJC_HEADER_MARKERS))
            monkeypatch.setattr(ex, "_is_objc_source", lambda p: capped(p, ex._OBJC_HEADER_MARKERS))
            monkeypatch.setattr(ex, "_is_cpp_header", lambda p: capped(p, ex._CPP_HEADER_MARKERS))

        monkeypatch.setattr(ex, "_get_extractor", get)
        monkeypatch.setattr(Path, "read_bytes", counting_read_bytes)


def _run(corpus: Path, monkeypatch, variant: str) -> tuple[Probe, list[str]]:
    # reconcile resolves graph source_file strings against the CWD, so rebuild
    # from the project root the way the CLI does
    monkeypatch.chdir(corpus)
    _apply_standard_change(corpus)
    probe = Probe()
    probe.install(monkeypatch, variant)
    assert _rebuild_code(corpus, no_cluster=True, acquire_lock=False) is True
    return probe, _node_ids(corpus)


@pytest.fixture
def built_corpus(tmp_path, capsys):
    corpus = _make_corpus(tmp_path)
    assert _rebuild_code(corpus, no_cluster=True, acquire_lock=False) is True
    capsys.readouterr()
    return corpus, _snapshot(corpus)


EXPECT = {
    # variant: (real asks for the header, reads per ask, bytes per read is capped)
    "base": ("nodes", 2, False),
    "cache": (1, 2, False),
    "capped": ("nodes", 2, True),
    "capped_cache": (1, 2, True),
    "cheap": (0, 0, False),
    "cheap_cache": (0, 0, False),
}


def test_cost_baseline_asks_once_per_node(built_corpus, monkeypatch, capsys):
    corpus, snap = built_corpus
    _restore(corpus, snap)
    header_nodes = _header_nodes(corpus)
    size = (corpus / "big.h").stat().st_size
    assert header_nodes >= HEADER_FUNCS

    probe, _ = _run(corpus, monkeypatch, "base")
    capsys.readouterr()

    assert _for(probe.reconcile_calls, "big.h") == header_nodes, "one ask per node"
    assert _for(probe.reconcile_real, "big.h") == header_nodes
    assert _for(probe.reconcile_reads, "big.h") == 2 * header_nodes, "two sniffs"
    assert _for(probe.reconcile_bytes, "big.h") == 2 * header_nodes * size, "whole file each"


@pytest.mark.parametrize("variant", list(EXPECT))
def test_cost_variants(built_corpus, monkeypatch, capsys, variant):
    corpus, snap = built_corpus
    _restore(corpus, snap)
    header_nodes = _header_nodes(corpus)
    size = (corpus / "big.h").stat().st_size

    probe, _ = _run(corpus, monkeypatch, variant)
    capsys.readouterr()

    real_expected, reads_per_ask, capped = EXPECT[variant]
    real_expected = header_nodes if real_expected == "nodes" else real_expected

    assert _for(probe.reconcile_calls, "big.h") == header_nodes, "the loop still visits every node"
    assert _for(probe.reconcile_real, "big.h") == real_expected
    assert _for(probe.reconcile_reads, "big.h") == reads_per_ask * real_expected
    per_read = min(size, CAP) if capped else size
    assert _for(probe.reconcile_bytes, "big.h") == per_read * reads_per_ask * real_expected


@pytest.mark.parametrize("variant", ["cache", "capped", "capped_cache", "cheap", "cheap_cache"])
def test_meaning_is_unchanged(built_corpus, monkeypatch, capsys, variant):
    """The differential net: every variant must keep and evict the same nodes."""
    corpus, snap = built_corpus

    _restore(corpus, snap)
    _, baseline = _run(corpus, monkeypatch, "base")
    capsys.readouterr()
    monkeypatch.undo()

    _restore(corpus, snap)
    _, changed = _run(corpus, monkeypatch, variant)
    capsys.readouterr()

    assert changed == baseline


def test_h8_stored_origin_can_answer_without_the_filesystem(built_corpus, monkeypatch, capsys):
    """Probe: the graph already stores the bit reconcile recomputes from disk."""
    corpus, snap = built_corpus
    _restore(corpus, snap)
    monkeypatch.chdir(corpus)

    (corpus / "docs").mkdir()
    (corpus / "docs" / "paper.pdf").write_bytes(b"%PDF-1.4\n")

    graph_path = corpus / "graphify-out" / "graph.json"
    data = json.loads(graph_path.read_text())
    data["nodes"].append(
        {
            "id": "doc_paper",
            "label": "a semantic node",
            "type": "document",
            "source_file": str(corpus / "docs" / "paper.pdf"),
            "source_location": None,
        }
    )
    for item in data["nodes"]:
        item.pop("_origin", None)
        _backfill_origin(item)
    graph_path.write_text(json.dumps(data, indent=2))

    by_id = {n["id"]: n for n in data["nodes"]}
    assert by_id["doc_paper"]["_origin"] == "semantic"
    code_node = next(n for n in data["nodes"] if str(n.get("source_file", "")).endswith("big.h"))
    assert code_node["_origin"] == "ast"

    _apply_standard_change(corpus)
    assert _rebuild_code(corpus, no_cluster=True, acquire_lock=False) is True
    capsys.readouterr()
    assert "doc_paper" in _node_ids(corpus), "semantic node preserved, like the sniff branch does"


GOLDEN = Path(__file__).parent / "fixtures" / "4978" / "expected_nodes.json"


def test_golden_node_set(built_corpus, monkeypatch, capsys):
    """The exact survivor set for the standard corpus and change.

    Written once from the pre-fix code with GRAPHIFY_4978_WRITE_GOLDEN=1, then
    asserted unchanged after every fix commit.
    """
    import os

    corpus, snap = built_corpus
    _restore(corpus, snap)
    _, ids = _run(corpus, monkeypatch, "base")
    capsys.readouterr()

    if os.environ.get("GRAPHIFY_4978_WRITE_GOLDEN"):
        GOLDEN.parent.mkdir(parents=True, exist_ok=True)
        GOLDEN.write_text(json.dumps(ids, indent=2) + "\n")

    assert ids == json.loads(GOLDEN.read_text())
