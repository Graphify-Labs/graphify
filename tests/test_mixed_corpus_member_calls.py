"""Mixed-corpus isolation for the member-call resolvers (#6, #8, #10, spec #1682).

A corpus that mixes languages must not let one language's raw call data mint an
edge through a different language's member-call resolver. Two independent
mechanisms have to hold for that:

* **Raw-call ownership** -- a resolver consumes only raw calls from source files
  it owns. The cpp/csharp/java/objc/php resolvers claim theirs by the
  extractor-stamped ``lang``; Swift, Python and TypeScript raw calls carry no
  tag, so those three filter by source-file suffix instead (#10).
* **Definition-index scoping** -- the receiver-type index a resolver builds
  holds only types declared in its own sources (#8 for PHP/ObjC, #10 for
  Java/C#).

Every test goes through the public ``extract()`` seam, and the Python class
here doubles as the cross-language decoy: it owns an identically named method,
so a bare method-name match cannot tell it apart from the target.
"""
from __future__ import annotations

from pathlib import Path

from graphify.extract import extract


def _calls(tmp_path: Path, files: dict[str, str]):
    """Extract ``files`` (name -> source) and return ({(src, tgt): edge}, result)."""
    paths = []
    for name, body in files.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
        paths.append(path)
    result = extract(paths, cache_root=tmp_path / "graphify-out")
    calls = {
        (edge["source"], edge["target"]): edge
        for edge in result["edges"]
        if edge.get("relation") == "calls"
    }
    return calls, result


def _nid(result: dict, label: str, file_suffix: str) -> str:
    return next(
        node["id"]
        for node in result["nodes"]
        if node.get("label") == label
        and str(node.get("source_file", "")).endswith(file_suffix)
    )


def _call_context_pairs(result: dict) -> set[tuple[str, str]]:
    """Every ``context: "call"`` edge as (source, target) pairs.

    Wider than ``_calls``: the Swift and TypeScript resolvers fall back to a
    ``references`` edge onto the receiver's TYPE when the type has no such
    method, so a leak through either of them can surface as ``references``
    rather than ``calls``.
    """
    return {
        (edge["source"], edge["target"])
        for edge in result["edges"]
        if edge.get("context") == "call"
    }


# A Python class whose method name collides with the PHP call's callee. Nothing
# in a PHP file may ever bind to it.
_PY_DECOY = (
    "class Lead:\n"
    "    def search(self, filters):\n"
    "        return []\n"
)


def test_php_capitalized_variable_receiver_yields_no_python_edge(tmp_path: Path):
    """A capitalized PHP *variable* receiver must not reach the Python resolver.

    `$Lead->search()` spells a receiver that, read as a Python receiver, would
    hit the Python resolver's capitalized-receiver class arm and bind to the
    Python `Lead.search`. The PHP raw call is tagged `lang: "php"`, so the
    Python resolver skips it.
    """
    calls, result = _calls(tmp_path, {
        "svc.py": _PY_DECOY,
        "app/Runner.php": (
            "<?php\n"
            "namespace App;\n"
            "class Runner {\n"
            "    public function go(): void {\n"
            "        $Lead = new Lead();\n"
            "        $Lead->search([]);\n"
            "    }\n"
            "}\n"
        ),
    })
    py_search = _nid(result, ".search()", "svc.py")
    # No edge from anywhere in the PHP file may land on the Python method.
    php_sourced = [
        (src, tgt) for (src, tgt) in calls
        if str(calls[(src, tgt)].get("source_file", "")).endswith(".php")
    ]
    assert not [pair for pair in php_sourced if pair[1] == py_search], (
        "a PHP raw call minted an edge into the Python decoy method"
    )


def test_python_member_calls_still_resolve_in_a_mixed_corpus(tmp_path: Path):
    """Positive control: the tag skip must not disable the Python resolver.

    Without this, the test above would pass even if the skip discarded every
    raw call. A genuine Python capitalized-receiver call still resolves, and a
    decoy class with the same method name gets no edge.
    """
    calls, result = _calls(tmp_path, {
        "svc.py": _PY_DECOY,
        "decoy.py": (
            "class Audit:\n"
            "    def search(self, filters):\n"
            "        return []\n"
        ),
        "caller.py": (
            "from svc import Lead\n"
            "\n"
            "def run():\n"
            "    Lead.search({})\n"
        ),
        "app/Runner.php": (
            "<?php\n"
            "namespace App;\n"
            "class Runner {\n"
            "    public function go(): void { $Lead = new Lead(); $Lead->search([]); }\n"
            "}\n"
        ),
    })
    run = _nid(result, "run()", "caller.py")
    py_search = _nid(result, ".search()", "svc.py")
    decoy_search = _nid(result, ".search()", "decoy.py")
    assert (run, py_search) in calls, "genuine Python member call stopped resolving"
    assert (run, decoy_search) not in calls, "decoy class received an edge"


# ── Language-scoped receiver type index (#8) ─────────────────────────────────
#
# The `lang` tag above keeps one language's raw calls out of another
# language's resolver. It does NOT scope the DEFINITION index each resolver
# builds: `type_def_nids` was assembled from every type-like node in the
# corpus, so a receiver type name was matched against classes written in any
# language. That cut both ways — a foreign class could be bound as the
# receiver's type, and a foreign class sharing the name could trip the
# single-definition guard and suppress the correct same-language edge.


def test_php_receiver_type_does_not_match_a_python_class(tmp_path: Path):
    """Defect 1: no PHP `class Lead` exists, only a Python one — refuse."""
    calls, result = _calls(tmp_path, {
        "svc.py": _PY_DECOY,
        "app/Runner.php": (
            "<?php\n"
            "namespace App;\n"
            "class Runner {\n"
            "    private Lead $lead;\n"
            "    public function go(): void { $this->lead->search([]); }\n"
            "}\n"
        ),
    })

    go = _nid(result, ".go()", "Runner.php")
    py_search = _nid(result, ".search()", "svc.py")
    assert (go, py_search) not in calls, \
        "a PHP receiver type must not resolve against a Python class"


def test_php_receiver_resolves_despite_a_same_named_python_class(tmp_path: Path):
    """Defect 2 (the damaging one): a cross-language name collision must not
    make the god-node guard suppress the legitimate PHP-to-PHP edge."""
    calls, result = _calls(tmp_path, {
        "svc.py": _PY_DECOY,
        "app/Lead.php": (
            "<?php\nnamespace App;\n"
            "class Lead {\n"
            "    public function search(array $filters): array { return []; }\n"
            "}\n"
        ),
        "app/Runner.php": (
            "<?php\n"
            "namespace App;\n"
            "class Runner {\n"
            "    private Lead $lead;\n"
            "    public function go(): void { $this->lead->search([]); }\n"
            "}\n"
        ),
    })

    go = _nid(result, ".go()", "Runner.php")
    php_search = _nid(result, ".search()", "Lead.php")
    py_search = _nid(result, ".search()", "svc.py")
    assert (go, php_search) in calls, \
        "a same-named class in another language suppressed the real PHP edge"
    assert (go, py_search) not in calls
    assert calls[(go, php_search)]["confidence"] == "INFERRED"


def test_objc_receiver_type_does_not_match_a_python_class(tmp_path: Path):
    """Defect 1, ObjC twin: `[Lead search]` with no ObjC `Lead` in the corpus."""
    calls, result = _calls(tmp_path, {
        "svc.py": _PY_DECOY,
        "src/Runner.m": (
            "@implementation Runner\n"
            "- (void)go { [Lead search]; }\n"
            "@end\n"
        ),
    })

    go = _nid(result, "-go", "Runner.m")
    py_search = _nid(result, ".search()", "svc.py")
    assert (go, py_search) not in calls, \
        "an ObjC receiver type must not resolve against a Python class"


def test_objc_receiver_resolves_despite_a_same_named_python_class(tmp_path: Path):
    """Defect 2, ObjC twin: the collision must not suppress the ObjC edge."""
    calls, result = _calls(tmp_path, {
        "svc.py": _PY_DECOY,
        "src/Lead.h": "@interface Lead : NSObject\n- (void)search;\n@end\n",
        "src/Lead.m": (
            '#import "Lead.h"\n@implementation Lead\n- (void)search {}\n@end\n'
        ),
        "src/Runner.m": (
            '#import "Lead.h"\n@implementation Runner\n'
            "- (void)go { [Lead search]; }\n@end\n"
        ),
    })

    go = _nid(result, "-go", "Runner.m")
    py_search = _nid(result, ".search()", "svc.py")
    objc_search = next(
        node["id"] for node in result["nodes"]
        if node.get("label") == "-search"
        and str(node.get("source_file", "")).endswith((".h", ".m"))
    )
    assert (go, objc_search) in calls, \
        "a same-named Python class suppressed the real ObjC edge"
    assert (go, py_search) not in calls


# ── Untagged resolvers consume each other's raw calls (#10) ──────────────────
#
# The `lang` tag the tests above rely on is stamped only on cpp/csharp/java/
# objc/php raw calls. Swift, Python and TypeScript raw calls carry none, so a
# `if rc.get("lang"): continue` guard in those three resolvers excluded the
# tagged languages and let the untagged ones flow into each other: a TypeScript
# receiver reached the Python resolver's capitalized-receiver class arm and
# minted a cross-language edge at EXTRACTED. The guard cannot close that by
# construction; only a positive source-file suffix filter can.
#
# Each test below is built so that exactly one resolver can be the miner: the
# resolver that legitimately owns the raw call refuses it on its own terms, so
# any surviving edge is another language's resolver reaching across.

_TS_TYPED_RECEIVER = (
    "class Dep { go() { return 1; } }\n"
    "export class Widget {\n"
    "  constructor(private dep: Dep) {}\n"
    "  run() { return this.dep.go(); }\n"
    "}\n"
)
"""A TS constructor parameter property. Produces the `ts_type_table` the
TypeScript resolver requires -- without one it returns early and cannot leak."""

_SWIFT_TYPED_RECEIVER = (
    "class Dep { func go() {} }\n"
    "class Widget {\n"
    "    let dep: Dep = Dep()\n"
    "    func run() { dep.go() }\n"
    "}\n"
)
"""The Swift twin: produces the `swift_type_table` the Swift resolver requires."""

# Calls a method the Python class does not own, so the Python resolver itself
# refuses (its method index misses) -- any edge onto `Lead` is foreign.
_PY_CALLER_MISSING_METHOD = (
    "from svc import Lead\n"
    "\n"
    "\n"
    "def run():\n"
    "    Lead.missing()\n"
)


def test_typescript_receiver_mints_no_edge_into_a_python_method(tmp_path: Path):
    """The reported repro (#10): no TS `Lead` exists anywhere in the corpus.

    `Lead.search({})` is a TypeScript raw call. Read as a Python raw call it
    hits the Python resolver's capitalized-receiver class arm and binds to the
    Python `Lead.search` at EXTRACTED -- the strongest confidence label -- for
    a call written in a file the Python resolver does not own.
    """
    calls, result = _calls(tmp_path, {
        "svc.py": _PY_DECOY,
        "runner.ts": "class Runner {\n  go() { return Lead.search({}); }\n}\n",
    })

    go = _nid(result, ".go()", "runner.ts")
    py_search = _nid(result, ".search()", "svc.py")
    assert (go, py_search) not in calls, \
        "a TypeScript raw call minted an edge into a Python method"


def test_python_raw_call_is_not_mined_by_the_typescript_resolver(tmp_path: Path):
    """The reverse direction: a Python raw call reaching the TS resolver.

    `Lead.missing()` is refused by the Python resolver -- the Python `Lead` has
    no `missing`. The TypeScript resolver, handed the same raw call, resolves
    the receiver type and falls back to a `references` edge onto the class,
    inventing a call-context edge out of Python source.
    """
    _, result = _calls(tmp_path, {
        "svc.py": _PY_DECOY,
        "caller.py": _PY_CALLER_MISSING_METHOD,
        "widget.ts": _TS_TYPED_RECEIVER,
    })
    pairs = _call_context_pairs(result)

    run = _nid(result, "run()", "caller.py")
    py_lead = _nid(result, "Lead", "svc.py")
    assert (run, py_lead) not in pairs, \
        "the TypeScript resolver mined a Python raw call"
    # Positive control: the TS resolver still resolves its own typed receiver.
    ts_run = _nid(result, ".run()", "widget.ts")
    ts_go = _nid(result, ".go()", "widget.ts")
    assert (ts_run, ts_go) in pairs, "the TypeScript resolver stopped resolving"


def test_python_raw_call_is_not_mined_by_the_swift_resolver(tmp_path: Path):
    """Same shape, Swift twin: `Lead.missing()` is Python's raw call to refuse."""
    _, result = _calls(tmp_path, {
        "svc.py": _PY_DECOY,
        "caller.py": _PY_CALLER_MISSING_METHOD,
        "Widget.swift": _SWIFT_TYPED_RECEIVER,
    })
    pairs = _call_context_pairs(result)

    run = _nid(result, "run()", "caller.py")
    py_lead = _nid(result, "Lead", "svc.py")
    assert (run, py_lead) not in pairs, \
        "the Swift resolver mined a Python raw call"
    # Positive control: the Swift resolver still resolves its own typed receiver.
    swift_run = _nid(result, ".run()", "Widget.swift")
    swift_go = _nid(result, ".go()", "Widget.swift")
    assert (swift_run, swift_go) in pairs, "the Swift resolver stopped resolving"


def test_swift_raw_call_is_not_mined_by_the_python_resolver(tmp_path: Path):
    """A Swift raw call the Swift resolver refuses must not reach Python.

    `Bundle` is in `_LANGUAGE_BUILTIN_GLOBALS`, so the Swift resolver skips the
    receiver outright (#2147) rather than binding a same-named user symbol. The
    Python resolver has no such guard, so the Swift raw call flowed into its
    class arm and bound to a Python `class Bundle` at EXTRACTED.
    """
    calls, result = _calls(tmp_path, {
        "svc.py": "class Bundle:\n    def load(self):\n        return []\n",
        "Runner.swift": "class Runner {\n    func go() { Bundle.load() }\n}\n",
        "Widget.swift": _SWIFT_TYPED_RECEIVER,
    })

    go = _nid(result, ".go()", "Runner.swift")
    py_load = _nid(result, ".load()", "svc.py")
    assert (go, py_load) not in calls, \
        "a Swift raw call minted an edge into a Python method"
    # Positive control, with a decoy: the Swift resolver still resolves its own
    # typed receiver and does not fall back to a bare method-name match.
    swift_run = _nid(result, ".run()", "Widget.swift")
    swift_go = _nid(result, ".go()", "Widget.swift")
    assert (swift_run, swift_go) in calls, "the Swift resolver stopped resolving"
    assert (swift_run, go) not in calls, "the decoy Swift class received an edge"


# ── Language-scoped Java and C# receiver type indexes (#10) ──────────────────
#
# The definition-index half of the family #8 fixed for PHP/ObjC and recorded as
# knowingly deferred elsewhere. Java and C# still built `type_def_nids` from
# every type-like node in the corpus, so a Java `Lead lead; lead.search()`
# bound to a Python `class Lead` at INFERRED.


def test_java_receiver_type_does_not_match_a_python_class(tmp_path: Path):
    """Defect 1, Java: no Java `class Lead` exists, only a Python one."""
    calls, result = _calls(tmp_path, {
        "svc.py": _PY_DECOY,
        "Runner.java": (
            "class Runner {\n"
            "    private Lead lead;\n"
            "    void go() { lead.search(); }\n"
            "}\n"
        ),
    })

    go = _nid(result, ".go()", "Runner.java")
    py_search = _nid(result, ".search()", "svc.py")
    assert (go, py_search) not in calls, \
        "a Java receiver type must not resolve against a Python class"


def test_java_receiver_resolves_despite_a_same_named_python_class(tmp_path: Path):
    """Defect 2, Java: the cross-language name collision pushed the
    single-definition guard to 2 and suppressed the legitimate Java edge."""
    calls, result = _calls(tmp_path, {
        "svc.py": _PY_DECOY,
        "Lead.java": "class Lead { void search() {} }\n",
        "Runner.java": (
            "class Runner {\n"
            "    private Lead lead;\n"
            "    void go() { lead.search(); }\n"
            "}\n"
        ),
    })

    go = _nid(result, ".go()", "Runner.java")
    java_search = _nid(result, ".search()", "Lead.java")
    py_search = _nid(result, ".search()", "svc.py")
    assert (go, java_search) in calls, \
        "a same-named class in another language suppressed the real Java edge"
    assert (go, py_search) not in calls, "the Python decoy received an edge"
    assert calls[(go, java_search)]["confidence"] == "INFERRED"


def test_csharp_receiver_type_does_not_match_a_python_class(tmp_path: Path):
    """Defect 1, C#: no C# `class Lead` exists, only a Python one."""
    calls, result = _calls(tmp_path, {
        "svc.py": _PY_DECOY,
        "Runner.cs": (
            "public class Runner {\n"
            "    private Lead lead;\n"
            "    public void Go() { lead.search(); }\n"
            "}\n"
        ),
    })

    go = _nid(result, ".Go()", "Runner.cs")
    py_search = _nid(result, ".search()", "svc.py")
    assert (go, py_search) not in calls, \
        "a C# receiver type must not resolve against a Python class"


def test_csharp_receiver_resolves_despite_a_same_named_python_class(tmp_path: Path):
    """Defect 2, C#: the legitimate C#-to-C# edge survives the collision."""
    calls, result = _calls(tmp_path, {
        "svc.py": "class Lead:\n    def Search(self):\n        return []\n",
        "Lead.cs": "public class Lead { public void Search() {} }\n",
        "Runner.cs": (
            "public class Runner {\n"
            "    private Lead lead;\n"
            "    public void Go() { lead.Search(); }\n"
            "}\n"
        ),
    })

    go = _nid(result, ".Go()", "Runner.cs")
    cs_search = _nid(result, ".Search()", "Lead.cs")
    py_search = _nid(result, ".Search()", "svc.py")
    assert (go, cs_search) in calls, \
        "a same-named class in another language suppressed the real C# edge"
    assert (go, py_search) not in calls, "the Python decoy received an edge"
