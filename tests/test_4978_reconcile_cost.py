"""Hypothesis tests for #4978: reconcile asks a per-file question once per node.

Two questions are kept apart on purpose:

  cost     how often the question is asked, and how many bytes a miss reads
  meaning  whether any keep/evict decision changes

A fix that is cheap and wrong fails the counting test. A fix that is correct and slow
fails the cost test. The frozen node set catches a fix that changes a keep or evict
decision, which is the failure mode that matters here.

The hypotheses the fix implements, named as they were argued on the issue:
  H7  ask "is this source AST-owned" instead of "which extractor"
  H1  resolve that answer once per file, keyed by identity
  H4  sniff the first 256 KiB instead of the whole file
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


def test_sniff_headers_flag_never_changes_none_ness(tmp_path):
    paths = _write_fixtures(tmp_path / "f")
    for name, path in paths.items():
        real = ex._get_extractor(path) is not None
        cheap = ex._get_extractor(path, sniff_headers=False) is not None
        assert cheap == real, f"{name}: sniff_headers=False != default"


def test_sniff_headers_flag_follows_a_graphifyrc_remap(tmp_path, monkeypatch):
    paths = _write_fixtures(tmp_path / "f")
    monkeypatch.setattr(ex, "effective_suffix", lambda p: ".unmapped")
    for name in ("plain.h", "cpp.h"):
        assert ex._get_extractor(paths[name], sniff_headers=False) is None
        assert (ex._get_extractor(paths[name]) is None) is True


def test_sniff_headers_false_reads_nothing_for_h(tmp_path, monkeypatch):
    paths = _write_fixtures(tmp_path / "f")
    reads = 0
    opens = 0
    real_read_bytes = Path.read_bytes
    real_open = open

    def counting_read_bytes(self):
        nonlocal reads
        reads += 1
        return real_read_bytes(self)

    def counting_open(*args, **kwargs):
        nonlocal opens
        opens += 1
        return real_open(*args, **kwargs)

    monkeypatch.setattr(Path, "read_bytes", counting_read_bytes)
    monkeypatch.setattr("builtins.open", counting_open)

    assert ex._get_extractor(paths["plain.h"], sniff_headers=False) is not None
    assert reads == 0
    assert opens == 0


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


@pytest.mark.parametrize("name", ["huge_cpp.h", "huge_objc.m"])
def test_production_sniffer_reads_only_the_cap(tmp_path, monkeypatch, name):
    """The shipped sniffer must read _SNIFF_BYTES, not the whole file.

    Without this, reverting to read_bytes()[:CAP] would keep every other test
    green while reintroducing a full-file read and allocation per call (#4978).
    """
    p = tmp_path / name
    body = b"class Late { };\n" if name.endswith(".h") else b"@implementation App\n"
    p.write_bytes(body + b"/* pad */\n" * 130000)
    assert p.stat().st_size > ex._SNIFF_BYTES

    sizes = []
    real_open = open

    class CountingFile:
        def __init__(self, fh):
            self._fh = fh

        def __getattr__(self, attr):
            return getattr(self._fh, attr)

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return self._fh.__exit__(*exc)

        def read(self, *args, **kwargs):
            data = self._fh.read(*args, **kwargs)
            sizes.append(len(data))
            return data

    def counting_open(file, mode="r", *args, **kwargs):
        fh = real_open(file, mode, *args, **kwargs)
        if "b" in str(mode):
            return CountingFile(fh)
        return fh

    monkeypatch.setattr("builtins.open", counting_open)
    ex._get_extractor(p)

    assert sizes == [ex._SNIFF_BYTES], f"{p.stat().st_size} byte file, reads {sizes}"


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
# pipeline: real _rebuild_code, instrumented at the reconcile call site
# ---------------------------------------------------------------------------
HEADER_FUNCS = 60


def _make_corpus(root: Path) -> Path:
    corpus = root / "corpus"
    corpus.mkdir(parents=True)
    (corpus / "app.py").write_text("def one():\n    pass\n\ndef two():\n    pass\n")
    lines = ["#ifndef BIG_H\n#define BIG_H\n"]
    lines += [
        f"static inline int hf{i}(int a) {{ return a + {i}; }}\n"
        for i in range(HEADER_FUNCS)
    ]
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

    def install(self, monkeypatch) -> None:
        real_get = ex._get_extractor
        real_read_bytes = Path.read_bytes
        real_open = open
        probe = self

        def get(path, **kwargs):
            p = Path(path)
            key = str(p)
            reconcile = _caller_is_reconcile()
            probe.calls[key] += 1
            if not reconcile:
                return real_get(p, **kwargs)

            probe.reconcile_calls[key] += 1
            probe.reconcile_real[key] += 1
            probe._active = key
            try:
                return real_get(p, **kwargs)
            finally:
                probe._active = None

        def counting_read_bytes(self):
            data = real_read_bytes(self)
            if probe._active is not None:
                probe.reconcile_reads[probe._active] += 1
                probe.reconcile_bytes[probe._active] += len(data)
            return data

        class CountingFile:
            def __init__(self, fh):
                self._fh = fh

            def __getattr__(self, name):
                return getattr(self._fh, name)

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return self._fh.__exit__(*exc)

            def read(self, *args, **kwargs):
                data = self._fh.read(*args, **kwargs)
                if probe._active is not None:
                    probe.reconcile_reads[probe._active] += 1
                    probe.reconcile_bytes[probe._active] += len(data)
                return data

        def counting_open(file, mode="r", *args, **kwargs):
            fh = real_open(file, mode, *args, **kwargs)
            if "b" in mode and probe._active is not None:
                return CountingFile(fh)
            return fh

        monkeypatch.setattr(ex, "_get_extractor", get)
        monkeypatch.setattr(Path, "read_bytes", counting_read_bytes)
        monkeypatch.setattr("builtins.open", counting_open)


def _run(corpus: Path, monkeypatch) -> tuple[Probe, list[str]]:
    # reconcile resolves graph source_file strings against the CWD, so rebuild
    # from the project root the way the CLI does
    monkeypatch.chdir(corpus)
    _apply_standard_change(corpus)
    probe = Probe()
    probe.install(monkeypatch)
    assert _rebuild_code(corpus, no_cluster=True, acquire_lock=False) is True
    return probe, _node_ids(corpus)


@pytest.fixture
def built_corpus(tmp_path, capsys):
    corpus = _make_corpus(tmp_path)
    assert _rebuild_code(corpus, no_cluster=True, acquire_lock=False) is True
    capsys.readouterr()
    return corpus, _snapshot(corpus)


def test_cost_reconcile_resolves_each_source_once(built_corpus, monkeypatch, capsys):
    """The #4978 invariant: a per-file answer is computed once per file."""
    corpus, snap = built_corpus
    _restore(corpus, snap)
    header_nodes = _header_nodes(corpus)
    assert header_nodes >= HEADER_FUNCS

    probe, _ = _run(corpus, monkeypatch)
    capsys.readouterr()

    assert _for(probe.reconcile_calls, "big.h") == 1, "one resolution per file, not per node"
    assert _for(probe.reconcile_real, "big.h") == 1
    assert _for(probe.reconcile_reads, "big.h") == 0, "the flag reads nothing"
    assert _for(probe.reconcile_bytes, "big.h") == 0


def test_objc_m_resolves_once_and_reads_at_most_one_head(built_corpus, monkeypatch, capsys):
    corpus, snap = built_corpus
    _restore(corpus, snap)
    # marker first, then padding past the cap: verifies the owned branch and the
    # read size in one file, which a 15 byte fixture cannot do
    (corpus / "objc.m").write_text(
        "@implementation App\n+ (void)load { }\n@end\n" + "/* pad */\n" * 40000
    )
    assert _rebuild_code(corpus, no_cluster=True, acquire_lock=False) is True
    capsys.readouterr()

    probe, _ = _run(corpus, monkeypatch)
    capsys.readouterr()

    assert _for(probe.reconcile_calls, "objc.m") == 1
    assert _for(probe.reconcile_real, "objc.m") == 1
    assert _for(probe.reconcile_reads, "objc.m") == 1
    assert _for(probe.reconcile_bytes, "objc.m") == ex._SNIFF_BYTES, "one head, capped"


def test_memo_does_not_survive_a_rebuild(built_corpus, monkeypatch, capsys):
    """The memo is local to one reconcile call, so watch re-reads after an edit.

    A module-level cache would return a stale answer for a header edited between
    two rebuilds in the same process, which is exactly what watch does.
    """
    corpus, snap = built_corpus
    _restore(corpus, snap)
    monkeypatch.chdir(corpus)
    (corpus / "gone.c").unlink()

    probe = Probe()
    probe.install(monkeypatch)

    counts = []
    for i in range(3):
        (corpus / "app.py").write_text(f"def one():\n    pass\n\ndef r{i}():\n    pass\n")
        before = _for(probe.reconcile_calls, "big.h")
        assert _rebuild_code(corpus, no_cluster=True, acquire_lock=False) is True
        capsys.readouterr()
        counts.append(_for(probe.reconcile_calls, "big.h") - before)

    assert counts == [1, 1, 1], "every rebuild resolves the header again"


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
    _, ids = _run(corpus, monkeypatch)
    capsys.readouterr()

    if os.environ.get("GRAPHIFY_4978_WRITE_GOLDEN"):
        GOLDEN.parent.mkdir(parents=True, exist_ok=True)
        GOLDEN.write_text(json.dumps(ids, indent=2) + "\n")

    assert ids == json.loads(GOLDEN.read_text())
