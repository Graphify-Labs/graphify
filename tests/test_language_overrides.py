"""A project can declare what an ambiguous extension means to it (#2961).

`.inc` is hard-mapped to the Pascal extractor, but it is "include file" in
whatever language a project uses: PHP on pfSense, Pascal in Delphi, SQL or
assembly elsewhere. A PHP `.inc` parsed as Pascal does not fail — it yields a
handful of incidental nodes, so the graph looks populated while the shipped
runtime is missing from it (7 nodes instead of 471 on the reporter's file).

No global mapping can be right for everyone, so the project says what it
means in `.graphifyrc`::

    language.inc=php

The declaration has to reach every place graphify keys a decision on the
suffix — classification, extractor dispatch, the case-folding and interop
rules for cross-file resolution, the language resolvers, and the AST cache
key (same bytes parse to a different graph under a different extractor) —
and it has to survive the trip into the extraction worker processes.
"""
from __future__ import annotations

import concurrent.futures
import io
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

import pytest

from graphify import rcfile
from graphify.detect import FileType, classify_file, detect
from graphify.extract import (
    _get_extractor,
    _lang_family,
    _lang_is_case_insensitive,
    extract,
    extract_pascal,
    extract_php,
)

try:
    from graphify.extract import _worker_init
except ImportError:  # pre-fix tree: the pool had no initializer
    _worker_init = None
from graphify.rcfile import (
    activate_language_overrides,
    cache_salt,
    effective_suffix,
    load_graphifyrc,
    parse_language_value,
    set_language_overrides,
)
from graphify.resolver_registry import LanguageResolver, run_language_resolvers

PHP_SOURCE = """<?php
namespace PfBlockerNG;

class RuleSet {
    public function load(string $path): array { return $this->parse($path); }
    private function parse(string $path): array { return []; }
}

function pfb_update_lists(array $cfg): void { $r = new RuleSet(); $r->load('/tmp/x'); }
function pfb_apply_rules(): void { pfb_update_lists([]); }
function pfb_cron(): void { pfb_apply_rules(); }
"""


@pytest.fixture(autouse=True)
def _no_overrides_leak():
    """Overrides are process state; never let one test's config leak into the next."""
    set_language_overrides(None)
    rcfile._warned_roots.clear()
    yield
    set_language_overrides(None)
    rcfile._warned_roots.clear()


def _quiet_extract(paths, **kw):
    with redirect_stdout(io.StringIO()):
        return extract(paths, **kw)


# ---------------------------------------------------------------------------
# The .graphifyrc parser
# ---------------------------------------------------------------------------

def test_language_line_maps_an_extension_to_a_canonical_suffix(tmp_path):
    (tmp_path / ".graphifyrc").write_text("language.inc=php\n", encoding="utf-8")
    assert load_graphifyrc(tmp_path) == {"languages": {".inc": ".php"}}


@pytest.mark.parametrize("key", ["language.inc", "language..inc", "language.INC", "language. inc "])
def test_the_extension_key_is_normalised(tmp_path, key):
    (tmp_path / ".graphifyrc").write_text(f"{key}=php\n", encoding="utf-8")
    assert load_graphifyrc(tmp_path)["languages"] == {".inc": ".php"}


@pytest.mark.parametrize("value, expected", [
    ("php", ".php"), ("PHP", ".php"), ("pascal", ".pas"), ("delphi", ".pas"),
    ("typescript", ".ts"), ("c++", ".cpp"), (".php", ".php"), (".PHP", ".php"),
    ("markdown", ".md"),
])
def test_values_accept_a_language_name_or_an_explicit_extension(value, expected):
    assert parse_language_value(value) == expected


@pytest.mark.parametrize("value", ["", "klingon", ".", ". php", "php script"])
def test_an_unknown_language_is_an_error_naming_the_alternatives(value):
    with pytest.raises(ValueError):
        parse_language_value(value)


def test_a_bad_language_line_reports_its_line_number(tmp_path):
    (tmp_path / ".graphifyrc").write_text("viz_node_limit=5\nlanguage.inc=klingon\n", encoding="utf-8")
    with pytest.raises(ValueError, match=r"language\.inc .* line 2.*klingon"):
        load_graphifyrc(tmp_path)


def test_a_bad_language_key_is_an_error(tmp_path):
    (tmp_path / ".graphifyrc").write_text("language.=php\n", encoding="utf-8")
    with pytest.raises(ValueError, match="line 1"):
        load_graphifyrc(tmp_path)


def test_the_existing_option_and_unknown_keys_still_behave(tmp_path):
    (tmp_path / ".graphifyrc").write_text(
        "# comment\nviz_node_limit=0\nfuture_option=whatever\nlanguage.tpl=.ts\n",
        encoding="utf-8",
    )
    cfg = load_graphifyrc(tmp_path)
    assert cfg == {"viz_node_limit": 0, "languages": {".tpl": ".ts"}}


def test_hooks_still_reads_the_same_file_through_its_old_name(tmp_path):
    from graphify.hooks import _load_graphifyrc
    (tmp_path / ".graphifyrc").write_text("viz_node_limit=3\nlanguage.inc=php\n", encoding="utf-8")
    assert _load_graphifyrc(tmp_path)["viz_node_limit"] == 3
    (tmp_path / ".graphifyrc").write_text("viz_node_limit=-1\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Invalid viz_node_limit"):
        _load_graphifyrc(tmp_path)


def test_no_file_means_no_overrides(tmp_path):
    assert load_graphifyrc(tmp_path) == {}
    assert activate_language_overrides(tmp_path) == {}


# ---------------------------------------------------------------------------
# Every suffix-keyed decision sees the declared language
# ---------------------------------------------------------------------------

def test_effective_suffix_is_the_real_one_until_a_project_says_otherwise():
    assert effective_suffix(Path("x/a.inc")) == ".inc"
    assert effective_suffix(Path("x/a.F90")) == ".F90"  # case preserved
    set_language_overrides({".inc": ".php"})
    assert effective_suffix(Path("x/a.inc")) == ".php"
    assert effective_suffix(Path("x/a.INC")) == ".php"
    assert effective_suffix(Path("x/a.F90")) == ".F90"


def test_dispatch_goes_to_the_declared_extractor():
    assert _get_extractor(Path("a.inc")) is extract_pascal
    set_language_overrides({".inc": ".php"})
    assert _get_extractor(Path("a.inc")) is extract_php
    assert _get_extractor(Path("b.pas")) is extract_pascal  # untouched


def test_a_remapped_header_skips_the_content_sniff(tmp_path):
    """`.h` is normally sniffed for C++/ObjC; a declaration makes it definite."""
    from graphify.extract import extract_cpp
    h = tmp_path / "plain.h"
    h.write_text("int add(int a, int b);\n", encoding="utf-8")
    set_language_overrides({".h": ".cpp"})
    assert _get_extractor(h) is extract_cpp


def test_a_remap_to_an_extension_without_an_extractor_yields_none():
    set_language_overrides({".inc": ".nosuchlang"})
    assert _get_extractor(Path("a.inc")) is None


def test_classification_follows_the_declaration():
    assert classify_file(Path("page.tpl")) is None  # unknown extension
    set_language_overrides({".tpl": ".php", ".txt": ".md"})
    assert classify_file(Path("page.tpl")) is FileType.CODE
    assert classify_file(Path("notes.txt")) is FileType.DOCUMENT


def test_case_folding_and_interop_family_follow_the_declaration():
    assert not _lang_is_case_insensitive("lib/a.inc")
    assert _lang_family("lib/a.inc") is None
    set_language_overrides({".inc": ".php"})
    assert _lang_is_case_insensitive("lib/a.inc")  # PHP identifiers fold case
    assert _lang_family("lib/a.inc") == "php"


def test_language_resolvers_wake_for_the_declared_language():
    ran: list[str] = []
    resolvers = [
        LanguageResolver("php", frozenset({".php"}), lambda *a: ran.append("php")),
        LanguageResolver("pascal", frozenset({".pas", ".inc"}), lambda *a: ran.append("pascal")),
    ]
    paths = [Path("a.inc")]
    run_language_resolvers(paths, [{}], [], [], resolvers=resolvers)
    assert ran == ["pascal"]
    ran.clear()
    set_language_overrides({".inc": ".php"})
    run_language_resolvers(paths, [{}], [], [], resolvers=resolvers)
    assert ran == ["php"]


# ---------------------------------------------------------------------------
# The reporter's repro: same bytes, two extensions
# ---------------------------------------------------------------------------

@pytest.fixture
def php_pair(tmp_path):
    (tmp_path / "a.inc").write_text(PHP_SOURCE, encoding="utf-8")
    (tmp_path / "b.php").write_text(PHP_SOURCE, encoding="utf-8")
    return tmp_path


def _counts(root, name):
    r = _quiet_extract([root / name], cache_root=root, root=root)
    return len(r["nodes"]), len(r["edges"])


def test_without_a_declaration_the_inc_file_is_nearly_empty(php_pair):
    """The failure mode: no error, just a graph missing the runtime."""
    inc, php = _counts(php_pair, "a.inc"), _counts(php_pair, "b.php")
    assert php[0] > 5 and php[1] > 5
    assert inc[0] < php[0] and inc[1] < php[1]


def test_with_the_declaration_the_two_files_yield_the_same_graph(php_pair):
    (php_pair / ".graphifyrc").write_text("language.inc=php\n", encoding="utf-8")
    assert _counts(php_pair, "a.inc") == _counts(php_pair, "b.php")


def test_a_library_caller_needs_no_setup_beyond_the_file(php_pair):
    """extract() finds `<root>/.graphifyrc` itself — the skill runbook and the
    MCP server call it directly, never through the CLI."""
    (php_pair / ".graphifyrc").write_text("language.inc=php\n", encoding="utf-8")
    set_language_overrides(None)  # nothing pre-activated
    assert _counts(php_pair, "a.inc") == _counts(php_pair, "b.php")


def test_extract_announces_the_active_overrides(php_pair):
    (php_pair / ".graphifyrc").write_text("language.inc=php\n", encoding="utf-8")
    out = io.StringIO()
    with redirect_stdout(out):
        extract([php_pair / "a.inc"], cache_root=php_pair, root=php_pair)
    assert ".inc -> .php" in out.getvalue()


def test_detect_counts_a_declared_extension_as_code(tmp_path):
    (tmp_path / "page.tpl").write_text(PHP_SOURCE, encoding="utf-8")
    with redirect_stdout(io.StringIO()):
        before = detect(tmp_path)["files"]
    (tmp_path / ".graphifyrc").write_text("language.tpl=php\n", encoding="utf-8")
    with redirect_stdout(io.StringIO()):
        after = detect(tmp_path)["files"]
    assert not any(p.endswith("page.tpl") for p in before.get("code", []))
    assert any(p.endswith("page.tpl") for p in after.get("code", []))


# ---------------------------------------------------------------------------
# The cache must not replay the other language's parse
# ---------------------------------------------------------------------------

def test_cache_salt_exists_only_for_remapped_files():
    assert cache_salt(Path("a.inc")) is None
    set_language_overrides({".inc": ".php"})
    assert cache_salt(Path("a.inc")) == "language=.php"
    assert cache_salt(Path("b.php")) is None


def test_changing_the_declaration_does_not_serve_the_stale_entry(php_pair):
    """Extract as Pascal (cached), declare PHP, extract again: the PHP graph,
    not the Pascal entry keyed by the same bytes."""
    pascal = _counts(php_pair, "a.inc")
    (php_pair / ".graphifyrc").write_text("language.inc=php\n", encoding="utf-8")
    php = _counts(php_pair, "a.inc")
    assert php == _counts(php_pair, "b.php") != pascal
    # and back again: the PHP entry must not be served for the Pascal parse
    (php_pair / ".graphifyrc").write_text("language.inc=pascal\n", encoding="utf-8")
    assert _counts(php_pair, "a.inc") == pascal


# ---------------------------------------------------------------------------
# Worker processes
# ---------------------------------------------------------------------------

@pytest.mark.skipif(_worker_init is None, reason="pre-fix tree")
def test_worker_init_installs_the_parents_overrides():
    _worker_init({".inc": ".php"})
    assert _get_extractor(Path("a.inc")) is extract_php


@pytest.mark.skipif(_worker_init is None, reason="pre-fix tree")
def test_the_pool_hands_its_workers_the_overrides(php_pair, monkeypatch):
    """Under `spawn` a worker starts with empty module state; the pool must
    forward the mapping through its initializer."""
    seen: dict = {}

    class RecordingPool(concurrent.futures.ThreadPoolExecutor):
        def __init__(self, max_workers=None, initializer=None, initargs=(), **kw):
            seen["initializer"] = initializer
            seen["initargs"] = initargs
            super().__init__(max_workers=max_workers, initializer=initializer, initargs=initargs)

    monkeypatch.setattr(concurrent.futures, "ProcessPoolExecutor", RecordingPool)
    for i in range(25):  # past _PARALLEL_THRESHOLD
        (php_pair / f"f{i}.inc").write_text(PHP_SOURCE, encoding="utf-8")
    (php_pair / ".graphifyrc").write_text("language.inc=php\n", encoding="utf-8")
    files = sorted(php_pair.glob("f*.inc"))
    result = _quiet_extract(files, cache_root=php_pair, root=php_pair, parallel=True)
    assert seen["initializer"] is _worker_init
    assert seen["initargs"] == ({".inc": ".php"},)
    # and every file came back as PHP, not Pascal
    per_file = {}
    for n in result["nodes"]:
        per_file.setdefault(n.get("source_file"), 0)
        per_file[n.get("source_file")] += 1
    assert len(per_file) == 25 and min(per_file.values()) > 5


# ---------------------------------------------------------------------------
# A config typo must be loud, not fatal
# ---------------------------------------------------------------------------

def test_a_malformed_rc_warns_once_and_scans_without_overrides(php_pair):
    (php_pair / ".graphifyrc").write_text("language.inc=klingon\n", encoding="utf-8")
    err = io.StringIO()
    with redirect_stderr(err):
        first = _counts(php_pair, "a.inc")
        _counts(php_pair, "a.inc")
    assert first == _counts(php_pair, "a.inc")  # Pascal, as before
    assert err.getvalue().count("ignoring .graphifyrc") == 1
    assert "klingon" in err.getvalue()


def test_activating_a_root_without_rc_clears_a_previous_roots_overrides(tmp_path):
    set_language_overrides({".inc": ".php"})
    activate_language_overrides(tmp_path)
    assert effective_suffix(Path("a.inc")) == ".inc"
