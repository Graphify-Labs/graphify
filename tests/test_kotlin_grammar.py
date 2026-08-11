"""Kotlin grammar-node-type mismatches (#2526, #2550, #2551).

PyPI tree-sitter-kotlin 1.x renamed/reshaped several nodes relative to the
older forks the extractor was written against:

* #2526 — imports are `import` nodes (an `import` keyword + a
  `qualified_identifier`; no `path` field), so every Kotlin import edge was
  silently dropped. Fixed by accepting the new node shape (adapted from PR
  #2531 by @Mustaqeem66) and resolving the written FQN to the real node via
  the per-file `package_header` declarations, which also unlocks the
  INFERRED -> EXTRACTED import-evidence promotion.
* #2550 — `com.example.Foo.bar()` parses to a NESTED navigation_expression
  chain; only the last identifier was kept, the receiver was never captured,
  and the raw_call died in the member-call skip. Fixed by flattening
  all-identifier chains into a `qualified_prefix` resolved against the
  declared packages (exactly-one-candidate guarded).
* #2551 — the grammar rejects one-line `class C { val x }` bodies; consecutive
  one-liners can dissolve the whole file's parse. Graphify warns on a file
  extracted through ERROR recovery (language-agnostic, also #2520) and keeps
  class linkage for declarations recovered inside an ERROR span. Since
  #2610/#2599 the warning fires only on PLAUSIBLE symbol loss (file-node-only
  result or a multiline ERROR region) — tiny fully-recovered errors that
  extract completely stay silent.
"""
from __future__ import annotations

import os
import re
from pathlib import Path

from graphify.extract import extract


def _extract(tmp_path, files: dict[str, str]):
    for name, body in files.items():
        p = tmp_path / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body)
    old = os.getcwd()
    try:
        os.chdir(tmp_path)
        r = extract([Path(n) for n in files],
                    cache_root=tmp_path / ".cache", parallel=False)
    finally:
        os.chdir(old)
    return r


def _edges(r, relation):
    return {(e["source"], e["target"]) for e in r["edges"] if e["relation"] == relation}


def _find(r, label, id_contains=""):
    return next(n["id"] for n in r["nodes"]
                if n["label"] == label and id_contains in n["id"])


# ── #2526: import edges ───────────────────────────────────────────────────────

_IMPORT_CORPUS = {
    "model/Money.kt": (
        "package com.demo.model\n"
        "\n"
        "class Money(val amount: Int)\n"
    ),
    "model/Ledger.kt": (
        "package com.demo.model\n"
        "\n"
        "class Ledger {\n"
        "    fun record(m: Money) { }\n"
        "}\n"
    ),
    "app/Main.kt": (
        "package com.demo.app\n"
        "\n"
        "import com.demo.model.Money\n"
        "import com.demo.model.Ledger\n"
        "\n"
        "fun main() {\n"
        "    val m = Money(5)\n"
        "    val l = Ledger()\n"
        "}\n"
    ),
}


def test_kotlin_imports_resolve_to_real_nodes(tmp_path):
    r = _extract(tmp_path, _IMPORT_CORPUS)
    node_ids = {n["id"] for n in r["nodes"]}
    main_file = _find(r, "Main.kt")
    money = _find(r, "Money")
    ledger = _find(r, "Ledger")
    imports = _edges(r, "imports")
    assert (main_file, money) in imports
    assert (main_file, ledger) in imports
    # Every Kotlin import edge points at an EXISTING node — the dangling
    # bare-last-segment target ("money") would be pruned by build.
    kotlin_imports = [e for e in r["edges"] if e["relation"] == "imports"
                      and str(e.get("source_file", "")).endswith(".kt")]
    assert len(kotlin_imports) >= 2
    for e in kotlin_imports:
        assert e["target"] in node_ids, f"import target {e['target']} dangles"


def test_kotlin_import_evidence_promotes_calls_to_extracted(tmp_path):
    r = _extract(tmp_path, _IMPORT_CORPUS)
    main_fn = _find(r, "main()")
    money = _find(r, "Money")
    call = next(e for e in r["edges"] if e["relation"] == "calls"
                and e["source"] == main_fn and e["target"] == money)
    assert call["confidence"] == "EXTRACTED", \
        "an explicitly-imported cross-file call must be promoted to EXTRACTED"


def test_kotlin_wildcard_import_emits_no_symbol_edge(tmp_path):
    r = _extract(tmp_path, {
        **{k: v for k, v in _IMPORT_CORPUS.items() if k != "app/Main.kt"},
        "app/Main.kt": (
            "package com.demo.app\n"
            "\n"
            "import com.demo.model.*\n"
            "\n"
            "fun main() { }\n"
        ),
    })
    main_file = _find(r, "Main.kt")
    bad_targets = {"model", "*", ""}
    for e in r["edges"]:
        if e["relation"] == "imports" and e["source"] == main_file:
            assert e["target"] not in bad_targets, \
                "a wildcard import names a PACKAGE; a symbol-level edge to the " \
                "last segment is a phantom"


def test_kotlin_aliased_import_resolves_to_original_symbol(tmp_path):
    r = _extract(tmp_path, {
        **{k: v for k, v in _IMPORT_CORPUS.items() if k != "app/Main.kt"},
        "app/Main.kt": (
            "package com.demo.app\n"
            "\n"
            "import com.demo.model.Money as Cash\n"
            "\n"
            "fun main() {\n"
            "    val m = Cash(5)\n"
            "}\n"
        ),
    })
    main_file = _find(r, "Main.kt")
    money = _find(r, "Money")
    assert (main_file, money) in _edges(r, "imports"), \
        "`import a.b.C as D` still imports C — the alias is caller-local"
    alias_edge = next(e for e in r["edges"] if e["relation"] == "imports"
                      and e["source"] == main_file and e["target"] == money)
    meta = alias_edge.get("metadata") or {}
    assert meta.get("target_fqn") == "com.demo.model.Money"
    assert meta.get("alias") == "Cash"


# ── #2550: fully-qualified call expressions ──────────────────────────────────

_FQ_CORPUS = {
    "lib/Lib.kt": (
        "package com.demo.lib\n"
        "\n"
        "fun BetaScreen() { }\n"
        "\n"
        "object Help {\n"
        "    fun help() { }\n"
        "}\n"
    ),
    "feature/Feature.kt": (
        "package com.demo.feature\n"
        "\n"
        "fun DeltaScreen() { }\n"
        "\n"
        "fun SamePackageCaller() {\n"
        "    com.demo.feature.DeltaScreen()\n"
        "}\n"
    ),
    "nav/Nav.kt": (
        "package com.demo.nav\n"
        "\n"
        "fun NavGraph() {\n"
        "    com.demo.lib.BetaScreen()\n"
        "    com.demo.feature.DeltaScreen()\n"
        "    com.demo.lib.Help.help()\n"
        "    com.nonexistent.pkg.Thing()\n"
        "}\n"
    ),
}


def test_kotlin_fully_qualified_calls_resolve(tmp_path):
    r = _extract(tmp_path, _FQ_CORPUS)
    calls = _edges(r, "calls")
    navgraph = _find(r, "NavGraph()")
    beta = _find(r, "BetaScreen()")
    delta = _find(r, "DeltaScreen()")
    same_pkg = _find(r, "SamePackageCaller()")
    help_fn = _find(r, ".help()")
    assert (navgraph, beta) in calls
    assert (navgraph, delta) in calls
    assert (same_pkg, delta) in calls
    assert (navgraph, help_fn) in calls, \
        "`com.demo.lib.Help.help()` must resolve through the object declaration"
    fq_calls = [e for e in r["edges"] if e["relation"] == "calls"
                and e["source"] == navgraph]
    assert all(e["confidence"] == "EXTRACTED" for e in fq_calls), \
        "the FQN is written verbatim in source: exact match, EXTRACTED"


def test_kotlin_fq_call_to_unknown_package_yields_no_edge(tmp_path):
    r = _extract(tmp_path, _FQ_CORPUS)
    navgraph = _find(r, "NavGraph()")
    targets = {t for s, t in _edges(r, "calls") if s == navgraph}
    assert not any("thing" in t.lower() for t in targets), \
        "`com.nonexistent.pkg.Thing()` is external — no edge, no fabricated node"


def test_kotlin_fq_call_to_ambiguous_name_yields_no_edge(tmp_path):
    r = _extract(tmp_path, {
        "dup1/D1.kt": (
            "package com.demo.dup\n"
            "\n"
            "fun Same() { }\n"
        ),
        "dup2/D2.kt": (
            "package com.demo.dup\n"
            "\n"
            "fun Same() { }\n"
        ),
        "callr/Caller.kt": (
            "package com.demo.callr\n"
            "\n"
            "fun Caller() {\n"
            "    com.demo.dup.Same()\n"
            "}\n"
        ),
    })
    caller = _find(r, "Caller()")
    assert not {t for s, t in _edges(r, "calls") if s == caller}, \
        "`Same` is defined twice in com.demo.dup — the exactly-one-candidate " \
        "guard must refuse to pick"


# ── #2551: one-line type bodies + ERROR recovery ─────────────────────────────

def test_kotlin_partial_parse_warns_with_file_and_line(tmp_path, capsys):
    # Consecutive one-line class bodies dissolve the whole file's parse in
    # tree-sitter-kotlin 1.x; graphify must say so instead of silently
    # returning a near-empty result.
    files = {
        "Broken.kt": (
            "class A { val v: Money = Money(5) }\n"
            "class B { val w: Ledger = Ledger() }\n"
            "fun Top() { }\n"
        ),
    }
    _extract(tmp_path, files)
    err = capsys.readouterr().err
    assert "syntax errors" in err
    assert "Broken.kt" in err
    assert re.search(r"first error at line \d+", err)
    # The marker must survive the per-file AST cache: a warm re-run (same
    # cache_root) warns again.
    old = os.getcwd()
    try:
        os.chdir(tmp_path)
        extract([Path("Broken.kt")], cache_root=tmp_path / ".cache", parallel=False)
    finally:
        os.chdir(old)
    err = capsys.readouterr().err
    assert "syntax errors" in err and "Broken.kt" in err


def test_kotlin_one_line_class_with_fun_still_extracts(tmp_path, capsys):
    # `class VM { fun f() = 1 }` trips has_error but recovers structurally:
    # everything must extract. #2610: since the recovery is zero-width and
    # every symbol is present, the corrected gate (warn only on plausible
    # symbol loss — file-node-only or a multiline ERROR region) stays SILENT;
    # the old has_error-gated warning here was a false positive.
    r = _extract(tmp_path, {
        "VM.kt": (
            "class VM { fun f() = 1 }\n"
            "fun After() { }\n"
        ),
    })
    vm = _find(r, "VM")
    f = _find(r, ".f()")
    _find(r, "After()")  # present
    assert (vm, f) in _edges(r, "method")
    assert "VM.kt" not in capsys.readouterr().err


def test_kotlin_one_line_class_keeps_field_reference(tmp_path):
    # ERROR parent-link guard: the one-line body's property must keep its
    # enclosing class, so the field-type reference lands on C.
    r = _extract(tmp_path, {
        "C.kt": "class C { val v: Money = Money(5) }\n",
    })
    c = _find(r, "C")
    money = _find(r, "Money")
    field_refs = {(e["source"], e["target"]) for e in r["edges"]
                  if e["relation"] == "references" and e.get("context") == "field"}
    assert (c, money) in field_refs


# ── #2565: property-initializer calls ────────────────────────────────────────

_INIT_CORPUS = {
    "lib/Lib.kt": (
        "package com.demo.lib\n"
        "\n"
        "class Repo\n"
        "\n"
        "class HttpClient(val url: String)\n"
        "\n"
        "fun createRepo(): Repo {\n"
        "    return Repo()\n"
        "}\n"
        "\n"
        "fun base(): String {\n"
        "    return \"\"\n"
        "}\n"
        "\n"
        "fun compute(): Int {\n"
        "    return 1\n"
        "}\n"
        "\n"
        "fun companionInit(): Int {\n"
        "    return 2\n"
        "}\n"
    ),
    "app/Service.kt": (
        "package com.demo.app\n"
        "\n"
        "import com.demo.lib.HttpClient\n"
        "import com.demo.lib.base\n"
        "import com.demo.lib.companionInit\n"
        "import com.demo.lib.compute\n"
        "import com.demo.lib.createRepo\n"
        "\n"
        "class Service {\n"
        "    val repo = createRepo()\n"
        "    private val client = HttpClient(base())\n"
        "    val x by lazy {\n"
        "        compute()\n"
        "    }\n"
        "    val plain = 5\n"
        "    companion object {\n"
        "        val shared = companionInit()\n"
        "    }\n"
        "    fun go() {\n"
        "        val r = createRepo()\n"
        "    }\n"
        "}\n"
    ),
    # No import here on purpose: the shared cross-file pass dedups on
    # (source, target) across relations, so a file-level `imports` edge to
    # createRepo would mask the file-level `calls` edge this corpus pins down
    # (single-candidate resolution needs no import evidence outside JS/TS).
    "app/TopLevel.kt": (
        "package com.demo.app\n"
        "\n"
        "val topRepo = createRepo()\n"
    ),
}


def test_kotlin_class_property_initializer_calls(tmp_path):
    r = _extract(tmp_path, _INIT_CORPUS)
    calls = _edges(r, "calls")
    service = _find(r, "Service")
    create = _find(r, "createRepo()")
    client = _find(r, "HttpClient")
    base = _find(r, "base()")
    assert (service, create) in calls, \
        "`val repo = createRepo()` runs at construction time — a calls edge"
    assert (service, client) in calls, \
        "`val client = HttpClient(...)` is a constructor call"
    assert (service, base) in calls, \
        "walk_calls recurses into nested initializer argument calls"


def test_kotlin_delegate_initializer_calls(tmp_path):
    r = _extract(tmp_path, _INIT_CORPUS)
    service = _find(r, "Service")
    compute = _find(r, "compute()")
    assert (service, compute) in _edges(r, "calls"), \
        "`by lazy { compute() }` invokes compute() to produce the property"


def test_kotlin_companion_property_initializer_attributes_to_class(tmp_path):
    r = _extract(tmp_path, _INIT_CORPUS)
    service = _find(r, "Service")
    ci = _find(r, "companionInit()")
    assert (service, ci) in _edges(r, "calls"), \
        "a companion object is not an attribution scope: its property " \
        "initializers belong to the enclosing class"


def test_kotlin_literal_initializer_emits_nothing(tmp_path):
    r = _extract(tmp_path, _INIT_CORPUS)
    service = _find(r, "Service")
    plain_line = _INIT_CORPUS["app/Service.kt"].splitlines().index(
        "    val plain = 5") + 1
    assert not [e for e in r["edges"] if e["source"] == service
                and e.get("source_location") == f"L{plain_line}"], \
        "`val plain = 5` contains no call — nothing to emit"


def test_kotlin_function_body_calls_unchanged(tmp_path):
    r = _extract(tmp_path, _INIT_CORPUS)
    calls = _edges(r, "calls")
    go = _find(r, ".go()")
    create = _find(r, "createRepo()")
    repo = _find(r, "Repo")
    assert (go, create) in calls
    assert (create, repo) in calls


def test_kotlin_top_level_property_initializer_attributes_to_file(tmp_path):
    r = _extract(tmp_path, _INIT_CORPUS)
    top_file = _find(r, "TopLevel.kt")
    create = _find(r, "createRepo()")
    assert (top_file, create) in _edges(r, "calls"), \
        "a top-level `val` has no class: its initializer belongs to the file"


def test_kotlin_fq_initializer_call_resolves_extracted(tmp_path):
    # Composition with #2550: a fully-qualified constructor call in a property
    # initializer flows through walk_calls' qualified_prefix stamping and
    # resolves to the REAL Router node via _resolve_kotlin_qualified_calls.
    r = _extract(tmp_path, {
        "nav/Router.kt": (
            "package com.demo.nav\n"
            "\n"
            "class Router\n"
        ),
        "app/App.kt": (
            "package com.demo.app\n"
            "\n"
            "class App {\n"
            "    val r = com.demo.nav.Router()\n"
            "}\n"
        ),
    })
    app = _find(r, "App")
    router = _find(r, "Router")
    edge = next(e for e in r["edges"] if e["relation"] == "calls"
                and e["source"] == app and e["target"] == router)
    assert edge["confidence"] == "EXTRACTED", \
        "the FQN is written verbatim in source: exact match, EXTRACTED"


# ── keep-the-bar: multi-line Kotlin is byte-identical ────────────────────────

def test_multiline_kotlin_unchanged(tmp_path, capsys):
    """Golden guard: ordinary multi-line Kotlin produces the same nodes/edges
    as before — the #2526/#2550/#2551 handling is purely additive — and no
    partial-parse warning fires."""
    r = _extract(tmp_path, {
        "Shop.kt": (
            "package com.shop\n"
            "\n"
            "class Cart {\n"
            "    val items: Inventory = Inventory()\n"
            "    fun checkout() {\n"
            "        total()\n"
            "    }\n"
            "    fun total() { }\n"
            "}\n"
            "\n"
            "class Inventory\n"
            "\n"
            "fun main() {\n"
            "    Cart().checkout()\n"
            "}\n"
        ),
    })
    labels = {n["label"] for n in r["nodes"]}
    assert {"Shop.kt", "Cart", "Inventory", ".checkout()", ".total()",
            "main()"} <= labels
    cart = _find(r, "Cart")
    checkout = _find(r, ".checkout()")
    total = _find(r, ".total()")
    methods = _edges(r, "method")
    assert (cart, checkout) in methods and (cart, total) in methods
    assert (checkout, total) in _edges(r, "calls")
    inv = _find(r, "Inventory")
    field_refs = {(e["source"], e["target"]) for e in r["edges"]
                  if e["relation"] == "references" and e.get("context") == "field"}
    assert (cart, inv) in field_refs
    assert "syntax errors" not in capsys.readouterr().err
