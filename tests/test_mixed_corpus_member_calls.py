"""Mixed-corpus isolation for the member-call resolvers.

A corpus that mixes languages must not let one language's data mint an edge
through a different language's member-call resolver. Two independent mechanisms
have to hold for that:

* **Raw-call ownership** -- a resolver consumes only raw calls from source files
  it owns. The cpp/csharp/java/objc resolvers claim theirs by the
  extractor-stamped ``lang``; Swift, Python and TypeScript raw calls carry no
  tag, so those three filter by source-file suffix instead.
* **Definition-index scoping** -- the receiver-type index a resolver builds
  holds only types declared in its own sources.

Every test goes through the public ``extract()`` seam, and the Python class here
doubles as the cross-language decoy: it owns an identically named method, so a
bare method-name match cannot tell it apart from the target.
"""
from __future__ import annotations

from pathlib import Path

from graphify.extract import extract


def _calls(tmp_path: Path, files: dict[str, str], cache_root: Path | None = None):
    paths = []
    for name, body in files.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
        paths.append(path)
    result = extract(paths, cache_root=cache_root or (tmp_path / "graphify-out"))
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
        and str(node.get("source_file") or "").endswith(file_suffix)
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


def _cross_language_targets(result: dict, caller: str, file_suffix: str) -> set[str]:
    """Call-context targets of ``caller`` that live in ``file_suffix``.

    Wider than naming one node: an index leak surfaces as ``calls`` onto the
    foreign METHOD, or — when the callee name misses on the foreign type — as a
    ``references`` edge onto the foreign TYPE itself. Both are the same bug.
    """
    foreign = {
        node["id"]
        for node in result["nodes"]
        if str(node.get("source_file") or "").endswith(file_suffix)
    }
    return {
        target
        for source, target in _call_context_pairs(result)
        if source == caller and target in foreign
    }


# A Python class whose method name collides with the other languages' callee.
# Nothing written in another language may ever bind to it.
_PY_DECOY = (
    "class Lead:\n"
    "    def search(self):\n"
    "        return []\n"
)


# ── Untagged resolvers consume each other's raw calls ────────────────────────
#
# The extractor stamps `lang` only on cpp/csharp/java/objc raw calls. Swift,
# Python and TypeScript raw calls carry none, so those three resolvers had
# nothing at all separating their own raw calls from each other's: a TypeScript
# receiver reached the Python resolver's capitalized-receiver class arm and
# minted a cross-language edge at EXTRACTED. Only a positive source-file suffix
# filter closes that by construction.
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
    """No TypeScript `Lead` exists anywhere in the corpus.

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


# ── Language-scoped Java and C# receiver type indexes ────────────────────────
#
# Both resolvers built `type_def_nids` from every type-like node in the corpus,
# so a Java `Lead lead; lead.search()` bound to a Python `class Lead` at
# INFERRED -- and, in the other direction, a foreign class merely SHARING the
# short name pushed the single-definition guard to 2 and silently suppressed
# the correct same-language edge.


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


# ── Language-scoped C++, ObjC, Swift and TypeScript receiver type indexes ────
#
# The remaining copies of the same shape. Each of these four resolvers built
# `type_def_nids` from every type-like node in the corpus, so the receiver's
# declared type name was matched against class definitions written in ANY
# language. Both directions of the defect are covered per language: the foreign
# class TYPING the receiver, and the foreign class merely SHARING the short name
# pushing the single-definition guard to 2 and deleting the correct edge.
#
# Raw-call ownership (above) cannot close this: the raw call being resolved is
# genuinely the resolver's own, and the leak is in what its INDEX offers up.

_CPP_CALLER = (
    "class Runner {\n"
    "public:\n"
    "    void go() { Lead lead; lead.search(); }\n"
    "};\n"
)
"""`Lead lead;` is a local declaration, so the C++ `cpp_type_table` types the
receiver and the call resolves at INFERRED."""

_OBJC_CALLER = (
    "@interface Runner : NSObject\n"
    "- (void)go;\n"
    "@end\n"
    "\n"
    "@implementation Runner\n"
    "- (void)go {\n"
    "    [Lead search];\n"
    "}\n"
    "@end\n"
)
"""A capitalized ObjC receiver names the type explicitly, so this arm resolves
at EXTRACTED -- the strongest confidence a leak can carry."""

_SWIFT_CALLER = (
    "class Runner {\n"
    "    let lead: Lead\n"
    "    func go() { lead.search() }\n"
    "}\n"
)
"""Declared without an initializer on purpose: `= Lead()` would additionally be
picked up by the shared cross-file CALL pass, which is a different mechanism
and would muddy what this test pins down."""

_TS_CALLER = (
    "export class Runner {\n"
    "  constructor(private lead: Lead) {}\n"
    "  go() { return this.lead.search(); }\n"
    "}\n"
)

# The same caller, importing the type it names. Upstream's origin gate (#2553)
# resolves a TS member call only when the matched type is visible to the calling
# file -- same file, a named import, or a module the file imports -- so the
# positive-direction test needs the import that real TypeScript would require
# anyway. `_TS_CALLER` deliberately keeps no import, so the negative test below
# still pins this PR's definition-index scoping on its own evidence.
_TS_CALLER_IMPORTING = "import { Lead } from './lead';\n" + _TS_CALLER


def test_cpp_receiver_type_does_not_match_a_python_class(tmp_path: Path):
    """No C++ `Lead` exists in the corpus, only a Python one."""
    _, result = _calls(tmp_path, {"svc.py": _PY_DECOY, "Runner.cpp": _CPP_CALLER})

    go = _nid(result, ".go()", "Runner.cpp")
    assert not _cross_language_targets(result, go, "svc.py"), \
        "a C++ receiver type must not resolve against a Python class"


def test_cpp_receiver_resolves_despite_a_same_named_python_class(tmp_path: Path):
    """The same-named Python class must not suppress the real C++ edge."""
    calls, result = _calls(tmp_path, {
        "svc.py": _PY_DECOY,
        "lead.cpp": "class Lead {\npublic:\n    void search() {}\n};\n",
        "Runner.cpp": _CPP_CALLER,
    })

    go = _nid(result, ".go()", "Runner.cpp")
    cpp_search = _nid(result, ".search()", "lead.cpp")
    py_search = _nid(result, ".search()", "svc.py")
    assert (go, cpp_search) in calls, \
        "a same-named Python class suppressed the real C++ edge"
    assert (go, py_search) not in calls, "the Python decoy received an edge"
    assert calls[(go, cpp_search)]["confidence"] == "INFERRED"


def test_objc_receiver_type_does_not_match_a_python_class(tmp_path: Path):
    """No ObjC `Lead` exists in the corpus, only a Python one."""
    _, result = _calls(tmp_path, {"svc.py": _PY_DECOY, "Runner.m": _OBJC_CALLER})

    go = _nid(result, "-go", "Runner.m")
    assert not _cross_language_targets(result, go, "svc.py"), \
        "an ObjC receiver type must not resolve against a Python class"


def test_objc_receiver_resolves_despite_a_same_named_python_class(tmp_path: Path):
    """The same-named Python class must not suppress the real ObjC edge."""
    calls, result = _calls(tmp_path, {
        "svc.py": _PY_DECOY,
        "Lead.m": (
            "@interface Lead : NSObject\n"
            "+ (void)search;\n"
            "@end\n"
            "\n"
            "@implementation Lead\n"
            "+ (void)search {}\n"
            "@end\n"
        ),
        "Runner.m": _OBJC_CALLER,
    })

    go = _nid(result, "-go", "Runner.m")
    objc_search = _nid(result, "+search", "Lead.m")
    py_search = _nid(result, ".search()", "svc.py")
    assert (go, objc_search) in calls, \
        "a same-named Python class suppressed the real ObjC edge"
    assert (go, py_search) not in calls, "the Python decoy received an edge"
    assert calls[(go, objc_search)]["confidence"] == "EXTRACTED"


def test_swift_receiver_type_does_not_match_a_python_class(tmp_path: Path):
    """No Swift `Lead` exists in the corpus, only a Python one."""
    _, result = _calls(tmp_path, {"svc.py": _PY_DECOY, "Runner.swift": _SWIFT_CALLER})

    go = _nid(result, ".go()", "Runner.swift")
    assert not _cross_language_targets(result, go, "svc.py"), \
        "a Swift receiver type must not resolve against a Python class"


def test_swift_receiver_resolves_despite_a_same_named_python_class(tmp_path: Path):
    """The same-named Python class must not suppress the real Swift edge."""
    calls, result = _calls(tmp_path, {
        "svc.py": _PY_DECOY,
        "Lead.swift": "class Lead { func search() {} }\n",
        "Runner.swift": _SWIFT_CALLER,
    })

    go = _nid(result, ".go()", "Runner.swift")
    swift_search = _nid(result, ".search()", "Lead.swift")
    py_search = _nid(result, ".search()", "svc.py")
    assert (go, swift_search) in calls, \
        "a same-named Python class suppressed the real Swift edge"
    assert (go, py_search) not in calls, "the Python decoy received an edge"
    assert calls[(go, swift_search)]["confidence"] == "INFERRED"


def test_typescript_receiver_type_does_not_match_a_python_class(tmp_path: Path):
    """No TypeScript `Lead` exists in the corpus, only a Python one."""
    _, result = _calls(tmp_path, {"svc.py": _PY_DECOY, "runner.ts": _TS_CALLER})

    go = _nid(result, ".go()", "runner.ts")
    assert not _cross_language_targets(result, go, "svc.py"), \
        "a TypeScript receiver type must not resolve against a Python class"


def test_typescript_receiver_resolves_despite_a_same_named_python_class(tmp_path: Path):
    """The same-named Python class must not suppress the real TypeScript edge."""
    calls, result = _calls(tmp_path, {
        "svc.py": _PY_DECOY,
        "lead.ts": "export class Lead { search() { return []; } }\n",
        "runner.ts": _TS_CALLER_IMPORTING,
    })

    go = _nid(result, ".go()", "runner.ts")
    ts_search = _nid(result, ".search()", "lead.ts")
    py_search = _nid(result, ".search()", "svc.py")
    assert (go, ts_search) in calls, \
        "a same-named Python class suppressed the real TypeScript edge"
    assert (go, py_search) not in calls, "the Python decoy received an edge"
    # INFERRED, not EXTRACTED: the receiver is typed through the
    # constructor-injection table rather than named at the call site, which
    # upstream's #2553 tiers like the Swift/C#/Java resolvers (sibling Swift
    # test above asserts the same).
    assert calls[(go, ts_search)]["confidence"] == "INFERRED"


# ── Language-scoped Python class and module indexes ──────────────────────────
#
# The Python resolver's two arms are indexed differently from every resolver
# above -- its class index is built by walking `method` edges rather than by
# filtering source-backed nodes, and its module arm resolves through the
# caller's own `imports` edges -- but both were corpus-wide all the same.
#
# Both arms are covered in both directions. The module arm's suppression case
# turned out not to be an index defect at all: two same-stem files disambiguate
# the FILE node ids (`lead_py_lead`, `lead_ts_lead`) while the `imports` edge
# target stays the bare alias `lead`, so the arm saw ZERO candidates rather
# than an ambiguous two. That is fixed one layer down, in the import-alias
# hinting, and asserted at both layers below.

_JAVA_DECOY = "class Lead { void search() {} }\n"


def test_python_class_receiver_does_not_match_a_java_class(tmp_path: Path):
    """Class arm, defect 1: no Python `Lead` exists, only a Java one.

    `Lead.search()` is a Python raw call the Python resolver rightly owns. Its
    class index held every class in the corpus, so the Java `Lead` answered for
    the receiver and the call was minted at EXTRACTED -- the label reserved for
    an explicitly named, unambiguous class reference.
    """
    _, result = _calls(tmp_path, {
        "caller.py": "def run():\n    Lead.search()\n",
        "Lead.java": _JAVA_DECOY,
    })

    run = _nid(result, "run()", "caller.py")
    assert not _cross_language_targets(result, run, "Lead.java"), \
        "a Python class receiver must not resolve against a Java class"


def test_python_class_receiver_resolves_despite_a_same_named_java_class(tmp_path: Path):
    """Class arm, defect 2: the Java decoy must not delete the Python edge."""
    calls, result = _calls(tmp_path, {
        "caller.py": "from svc import Lead\n\n\ndef run():\n    Lead.search()\n",
        "svc.py": _PY_DECOY,
        "Lead.java": _JAVA_DECOY,
    })

    run = _nid(result, "run()", "caller.py")
    py_search = _nid(result, ".search()", "svc.py")
    java_search = _nid(result, ".search()", "Lead.java")
    assert (run, py_search) in calls, \
        "a same-named Java class suppressed the real Python edge"
    assert (run, java_search) not in calls, "the Java decoy received an edge"
    assert calls[(run, py_search)]["confidence"] == "EXTRACTED"


# The module arm resolves an `import` to the imported file's node, which only
# lines up when ids are relativized against the corpus root itself -- hence the
# explicit `cache_root`, matching the prior art in
# `tests/test_extract.py::test_python_module_qualified_call_resolves_extracted`.
_MOD_CALLER = "import lead\n\n\ndef run():\n    lead.search()\n"
_TS_MODULE_DECOY = "export function search() { return []; }\n"


def test_python_module_receiver_does_not_match_a_typescript_file(tmp_path: Path):
    """Module arm, defect 1: `import lead` must not reach `lead.ts`.

    No `lead.py` exists. The arm matched any corpus file whose stem equalled the
    receiver, so a TypeScript file of the same stem satisfied it and
    `lead.search()` bound to a TypeScript function at EXTRACTED -- an import
    edge Python could not possibly have.
    """
    _, result = _calls(tmp_path, {
        "caller.py": _MOD_CALLER,
        "lead.ts": _TS_MODULE_DECOY,
    }, cache_root=tmp_path)

    run = _nid(result, "run()", "caller.py")
    assert not _cross_language_targets(result, run, "lead.ts"), \
        "a Python module receiver must not resolve against a TypeScript file"


def test_python_module_receiver_still_resolves_its_own_module(tmp_path: Path):
    """The module arm's positive control: scoping must not cost the real edge."""
    calls, result = _calls(tmp_path, {
        "caller.py": _MOD_CALLER,
        "lead.py": "def search():\n    return []\n",
    }, cache_root=tmp_path)

    run = _nid(result, "run()", "caller.py")
    py_search = _nid(result, "search()", "lead.py")
    assert (run, py_search) in calls, "the module arm stopped resolving"
    assert calls[(run, py_search)]["confidence"] == "EXTRACTED"


def test_python_module_receiver_resolves_despite_a_same_stem_typescript_file(
    tmp_path: Path,
):
    """Module arm, defect 2: a same-stem foreign file must not delete the edge.

    `lead.py` and `lead.ts` both derive the file node id `lead`, so
    disambiguation salts them into `lead_py_lead` and `lead_ts_lead` — while the
    `imports` edge target stays the bare alias `lead`, which now names nothing.
    The arm then sees ZERO candidate modules rather than an ambiguous two, and
    the one edge Python's own import genuinely supports disappears.
    """
    calls, result = _calls(tmp_path, {
        "caller.py": _MOD_CALLER,
        "lead.py": "def search():\n    return []\n",
        "lead.ts": _TS_MODULE_DECOY,
    }, cache_root=tmp_path)

    run = _nid(result, "run()", "caller.py")
    py_search = _nid(result, "search()", "lead.py")
    ts_search = _nid(result, "search()", "lead.ts")
    assert (run, py_search) in calls, \
        "a same-stem TypeScript file suppressed the real Python edge"
    assert (run, ts_search) not in calls, "the TypeScript decoy received an edge"
    assert calls[(run, py_search)]["confidence"] == "EXTRACTED"


def test_python_import_edge_survives_a_same_stem_foreign_sibling(tmp_path: Path):
    """The `imports` edge itself, one layer below the call edge above.

    Asserted separately because the module arm is only one consumer: any query
    over Python imports lost this edge to the same dangling alias.
    """
    _, result = _calls(tmp_path, {
        "caller.py": _MOD_CALLER,
        "lead.py": "def search():\n    return []\n",
        "lead.ts": _TS_MODULE_DECOY,
    }, cache_root=tmp_path)

    node_ids = {node["id"] for node in result["nodes"]}
    py_file = _nid(result, "lead.py", "lead.py")
    ts_file = _nid(result, "lead.ts", "lead.ts")
    imports = {
        (edge["source"], edge["target"])
        for edge in result["edges"]
        if edge["relation"] in ("imports", "imports_from")
    }
    caller_file = _nid(result, "caller.py", "caller.py")
    assert (caller_file, py_file) in imports, \
        "the Python import edge dangled on the pre-disambiguation alias"
    assert (caller_file, ts_file) not in imports, \
        "a Python import must never resolve to a TypeScript file"
    for source, target in imports:
        assert target in node_ids, f"import edge dangles: {source} -> {target}"
