"""Calls inside an exported function resolve through the import table (#3346).

`_js_top_level_function_bodies` scanned only direct program children, so a
top-level `export function f(){}` / `export const g = () => {}` — wrapped in an
export_statement — was skipped, and the calls inside it never became `uses`
facts. The visible symptom: an aliased-import call (`import { bar as baz };
baz()`) produced no `calls` edge, because only the use-fact path consults the
import alias table; the plain-name global resolver has no `baz` to match.
"""

from pathlib import Path

import pytest

from graphify.extract import extract

MOD = "export function foo() { return 1; }\nexport function bar() { return 2; }\n"


def _calls(tmp_path, files, suffix=".ts"):
    for name, body in files.items():
        (tmp_path / name).write_text(body, encoding="utf-8")
    r = extract(sorted(tmp_path.glob(f"*{suffix}")), cache_root=tmp_path / ".cache")
    labels = {n["id"]: n.get("label", "") for n in r["nodes"]}
    return {
        (labels.get(e["source"], ""), labels.get(e["target"], ""))
        for e in r["edges"] if e["relation"] == "calls"
    }


def _has(calls, caller_sub, callee):
    return any(caller_sub in s.lower() and t.rstrip("()") == callee for s, t in calls)


def test_aliased_import_call_in_exported_function_resolves(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    calls = _calls(tmp_path, {
        "m.ts": MOD,
        "al.ts": "import { bar as baz } from './m';\n"
                 "export function useAlias() { return baz(); }\n",
    })
    assert _has(calls, "usealias", "bar"), sorted(calls)


def test_aliased_import_call_in_exported_arrow_resolves(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    calls = _calls(tmp_path, {
        "m.ts": MOD,
        "al.ts": "import { bar as baz } from './m';\n"
                 "export const useArrow = () => baz();\n",
    })
    assert _has(calls, "usearrow", "bar"), sorted(calls)


def test_plain_named_import_control_still_resolves(tmp_path, monkeypatch):
    """The non-exported / plain-name path must be unaffected."""
    monkeypatch.chdir(tmp_path)
    calls = _calls(tmp_path, {
        "m.ts": MOD,
        "p.ts": "import { foo } from './m';\n"
                "export function usePlain() { return foo(); }\n",
    })
    assert _has(calls, "useplain", "foo"), sorted(calls)


def test_aliased_import_does_not_bind_to_the_alias_name(tmp_path, monkeypatch):
    """The edge lands on the imported definition (`bar`), never a phantom
    `baz` node (there is no such definition)."""
    monkeypatch.chdir(tmp_path)
    calls = _calls(tmp_path, {
        "m.ts": MOD,
        "al.ts": "import { bar as baz } from './m';\n"
                 "export function useAlias() { return baz(); }\n",
    })
    assert not any(t.rstrip("()") == "baz" for _s, t in calls), sorted(calls)


def test_non_exported_function_still_resolves(tmp_path, monkeypatch):
    """A plain (non-exported) function body was always scanned; keep it working
    alongside the exported-function fix."""
    monkeypatch.chdir(tmp_path)
    calls = _calls(tmp_path, {
        "m.ts": MOD,
        "al.ts": "import { bar as baz } from './m';\n"
                 "function useAlias() { return baz(); }\n",
    })
    assert _has(calls, "usealias", "bar"), sorted(calls)


# ── #4619: calls through a namespace import (`import * as ns from './mod'`) ──

def _project(tmp_path, files, monkeypatch):
    """Write `files` (relative path -> text), run the public extraction on every
    JS/TS file, and return (nodes, edges) of the result."""
    monkeypatch.chdir(tmp_path)
    paths = []
    for name, body in files.items():
        p = tmp_path / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")
        if p.suffix in (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".mts", ".cts"):
            paths.append(p)
    r = extract(sorted(paths), cache_root=tmp_path / ".cache")
    return r["nodes"], r["edges"]


def _name(label):
    return label.rstrip("()").lstrip(".")


def _call_triples(tmp_path, files, monkeypatch, relation="calls"):
    """{(source label, target label, target file name)} for one relation; the
    call parentheses and a method's leading dot are stripped from labels."""
    nodes, edges = _project(tmp_path, files, monkeypatch)
    by_id = {n["id"]: n for n in nodes}
    out = set()
    for e in edges:
        if e["relation"] != relation:
            continue
        s, t = by_id.get(e["source"], {}), by_id.get(e["target"], {})
        out.add((
            _name(s.get("label", "")),
            _name(t.get("label", "")),
            Path(t.get("source_file", "")).name,
        ))
    return out


ISSUE_FILES = {
    "ops.ts": "export function submit(n: number) { return n + 1 }\n"
              "export function reveal(n: number) { return n * 2 }\n",
    "named.ts": "export function helper() { return 1 }\n",
    "dispatch.ts": (
        "import * as ops from './ops'\n"
        "import { helper } from './named'\n"
        "export function dispatch(kind: string, n: number) {\n"
        "  switch (kind) {\n"
        "    case 'submit': return ops.submit(n)\n"
        "    case 'reveal': return ops.reveal(n)\n"
        "    default: return helper()\n"
        "  }\n"
        "}\n"
        "export function direct(n: number) { return ops.submit(n) }\n"
    ),
    "ops.test.ts": "import { submit } from './ops'\nsubmit(1)\n",
}


# T1 -- the issue's repro, one assert per expected edge
@pytest.mark.parametrize("caller,callee,callee_file", [
    ("dispatch", "submit", "ops.ts"),
    ("dispatch", "reveal", "ops.ts"),
    ("direct", "submit", "ops.ts"),
    ("dispatch", "helper", "named.ts"),
])
def test_issue_repro_namespace_member_calls_produce_calls_edges(
    tmp_path, monkeypatch, caller, callee, callee_file
):
    """The issue's four files: a call through `ops.` reaches the exported function."""
    calls = _call_triples(tmp_path, ISSUE_FILES, monkeypatch)
    assert (caller, callee, callee_file) in calls, sorted(calls)


# T2 -- the same call from other caller shapes
@pytest.mark.parametrize("ext,caller,caller_src", [
    (".js", "run",
     "import * as ops from './ops.js'\nexport const run = (n) => ops.submit(n)\n"),
    (".ts", "run",
     "import * as ops from './ops'\nexport class K { run(n: number) { return ops.submit(n) } }\n"),
    # the innermost function owns the call, as it does for a bare call
    (".ts", "inner",
     "import * as ops from './ops'\n"
     "export function outer(n: number) { function inner() { return ops.submit(n) } return inner }\n"),
    (".tsx", "View",
     "import * as ops from './ops'\nexport const View = () => { ops.submit(1); return <div /> }\n"),
    (".mjs", "run",
     "import * as ops from './ops.mjs'\nexport function run(n) { return ops.submit(n) }\n"),
], ids=["arrow-const-js", "class-method-ts", "nested-function-ts", "tsx-component", "mjs-function"])
def test_namespace_member_call_from_each_caller_shape(
    tmp_path, monkeypatch, ext, caller, caller_src
):
    """A namespace member call is an edge from its own caller to the exported function."""
    calls = _call_triples(tmp_path, {
        "ops" + ext: "export function submit(n) { return n + 1 }\n",
        "caller" + ext: caller_src,
    }, monkeypatch)
    assert (caller, "submit", "ops" + ext) in calls, sorted(calls)


# T3 -- through re-exports; the target is the real function in lib.ts
LIB = "export function viaNs() { return 1 }\n"


@pytest.mark.parametrize("barrel,caller", [
    ("export * from './lib'\n",
     "import * as b from './barrel'\nexport function run() { return b.viaNs() }\n"),
    ("export { viaNs } from './lib'\n",
     "import * as b from './barrel'\nexport function run() { return b.viaNs() }\n"),
    ("export * as ns from './lib'\n",
     "import { ns } from './barrel'\nexport function run() { return ns.viaNs() }\n"),
], ids=["export-star", "named-reexport", "export-star-as-ns"])
def test_namespace_member_call_through_a_barrel_reaches_the_real_function(
    tmp_path, monkeypatch, barrel, caller
):
    """The edge lands on `viaNs` in lib.ts, not on the barrel."""
    calls = _call_triples(tmp_path, {
        "lib.ts": LIB, "barrel.ts": barrel, "caller.ts": caller,
    }, monkeypatch)
    assert ("run", "viaNs", "lib.ts") in calls, sorted(calls)


# T3b -- a renamed re-export: `x.b()` is lib's `a`; `x.a()` names nothing the barrel exports
def test_namespace_call_through_a_renamed_reexport(tmp_path, monkeypatch):
    """`export { a as b }` exposes `b`, not `a`."""
    calls = _call_triples(tmp_path, {
        "lib.ts": "export function a() { return 1 }\n",
        "barrel.ts": "export { a as b } from './lib'\n",
        "caller.ts": "import * as x from './barrel'\n"
                     "export function useB() { return x.b() }\n"
                     "export function useA() { return x.a() }\n",
    }, monkeypatch)
    assert ("useB", "a", "lib.ts") in calls, sorted(calls)
    assert not any(s == "useA" for s, _t, _f in calls), sorted(calls)


# T4 -- must NOT create an edge
OPS = "export function submit(n: number) { return n + 1 }\n"


@pytest.mark.parametrize("files,forbidden", [
    # `missing` is not an export of ops; a same-named function in an unimported file is no evidence
    ({"ops.ts": OPS,
      "other.ts": "export function missing() { return 0 }\n",
      "caller.ts": "import * as ops from './ops'\nexport function run() { return ops.missing() }\n"},
     "missing"),
    # a local object named `ops` shadows the import inside the caller
    ({"ops.ts": OPS,
      "caller.ts": "import * as ops from './ops'\n"
                   "export function run() { const ops = { submit() { return 0 } }; return ops.submit() }\n"},
     "submit"),
    # a parameter named `ops` shadows the import
    ({"ops.ts": OPS,
      "caller.ts": "import * as ops from './ops'\n"
                   "export function run(ops: { submit(): number }) { return ops.submit() }\n"},
     "submit"),
    # an external package is not in the corpus; `createElement` elsewhere is unrelated
    ({"util.ts": "export function createElement() { return 0 }\n",
      "caller.ts": "import * as React from 'react'\n"
                   "export function C() { return React.createElement('div') }\n"},
     "createElement"),
    # a type-only namespace import used only in type positions makes no call
    ({"ops.ts": OPS,
      "caller.ts": "import type * as T from './ops'\n"
                   "export type F = typeof T.submit\n"
                   "export function run(f: F) { return 1 }\n"},
     "submit"),
], ids=["missing-name", "local-shadow", "param-shadow", "external-package", "type-only-import"])
def test_namespace_member_call_that_must_not_bind(tmp_path, monkeypatch, files, forbidden):
    """No calls edge to `forbidden` from the caller, and extraction does not crash."""
    calls = _call_triples(tmp_path, files, monkeypatch)
    caller_file_edges = {c for c in calls if c[0] in ("run", "C")}
    assert not any(t == forbidden for _s, t, _f in caller_file_edges), sorted(calls)


# T4 (continued) -- a same-named function in the CALLER's own file is not what `ops.submit` means
def test_namespace_member_call_does_not_bind_to_a_same_named_local_function(tmp_path, monkeypatch):
    """`ops.submit()` is ops.ts's submit; the caller file's own `submit` is not the target."""
    calls = _call_triples(tmp_path, {
        "ops.ts": OPS,
        "caller.ts": "import * as ops from './ops'\n"
                     "function submit(n: number) { return 0 }\n"
                     "export function run(n: number) { return ops.submit(n) }\n",
    }, monkeypatch)
    assert ("run", "submit", "caller.ts") not in calls, sorted(calls)


# T4b -- a function the module does not export is not reachable through its namespace
def test_namespace_call_to_an_unexported_function_makes_no_edge(tmp_path, monkeypatch):
    """`l.hidden()` is not an export of lib.ts, so it names nothing."""
    calls = _call_triples(tmp_path, {
        "lib.ts": "export function a() { return 1 }\nfunction hidden() { return 2 }\n",
        "caller.ts": "import * as l from './lib'\nexport function run() { return l.hidden() }\n",
    }, monkeypatch)
    assert not any(t == "hidden" for _s, t, _f in calls), sorted(calls)


# T5 -- undecided shapes: measure only
_UNDECIDED = pytest.mark.xfail(
    strict=False, reason="behaviour for this shape is not decided yet (#4619)")


@_UNDECIDED
def test_member_chain_through_a_namespace(tmp_path, monkeypatch):
    """`ops.a.b()`: what, if anything, should a two-level chain bind to."""
    calls = _call_triples(tmp_path, {
        "ops.ts": "export function a() { return 1 }\n",
        "caller.ts": "import * as ops from './ops'\nexport function run() { return (ops.a as any).b() }\n",
    }, monkeypatch)
    assert ("run", "a", "ops.ts") in calls, sorted(calls)


@_UNDECIDED
def test_new_on_a_namespace_member(tmp_path, monkeypatch):
    """`new ops.Klass()`: whether this is a calls edge, and to what."""
    calls = _call_triples(tmp_path, {
        "ops.ts": "export class Klass {}\n",
        "caller.ts": "import * as ops from './ops'\nexport function run() { return new ops.Klass() }\n",
    }, monkeypatch)
    assert ("run", "Klass", "ops.ts") in calls, sorted(calls)


@_UNDECIDED
def test_namespace_member_aliased_to_a_const_then_called(tmp_path, monkeypatch):
    """`const f = ops.submit; f()`: a call through a one-step alias."""
    calls = _call_triples(tmp_path, {
        "ops.ts": OPS,
        "caller.ts": "import * as ops from './ops'\n"
                     "export function run() { const f = ops.submit; return f(1) }\n",
    }, monkeypatch)
    assert ("run", "submit", "ops.ts") in calls, sorted(calls)


@_UNDECIDED
def test_namespace_member_destructured_then_called(tmp_path, monkeypatch):
    """`const { submit } = ops; submit()`: a call through destructuring."""
    calls = _call_triples(tmp_path, {
        "ops.ts": OPS,
        "caller.ts": "import * as ops from './ops'\n"
                     "export function run() { const { submit } = ops; return submit(1) }\n",
    }, monkeypatch)
    assert ("run", "submit", "ops.ts") in calls, sorted(calls)


# T6 -- guards that pass today
def test_named_import_call_still_resolves(tmp_path, monkeypatch):
    """Guards the named-import call path across a fix."""
    calls = _call_triples(tmp_path, {
        "m.ts": MOD,
        "c.ts": "import { foo } from './m'\nexport function run() { return foo() }\n",
    }, monkeypatch)
    assert ("run", "foo", "m.ts") in calls, sorted(calls)


def test_aliased_import_call_still_resolves_to_the_original(tmp_path, monkeypatch):
    """Guards the #3346 aliased-import call path across a fix."""
    calls = _call_triples(tmp_path, {
        "m.ts": MOD,
        "c.ts": "import { bar as baz } from './m'\nexport function run() { return baz() }\n",
    }, monkeypatch)
    assert ("run", "bar", "m.ts") in calls, sorted(calls)
    assert not any(t == "baz" for _s, t, _f in calls), sorted(calls)


def test_default_import_call_still_resolves(tmp_path, monkeypatch):
    """Guards the default-import call path across a fix."""
    calls = _call_triples(tmp_path, {
        "d.ts": "export default function dflt() { return 1 }\n",
        "c.ts": "import dflt from './d'\nexport function run() { return dflt() }\n",
    }, monkeypatch)
    assert ("run", "dflt", "d.ts") in calls, sorted(calls)


def test_issue_repro_import_edges_are_unchanged(tmp_path, monkeypatch):
    """Guards the file-level `imports_from` edges the issue says already exist."""
    imports = _call_triples(tmp_path, ISSUE_FILES, monkeypatch, relation="imports_from")
    assert {("dispatch.ts", "ops.ts", "ops.ts"), ("dispatch.ts", "named.ts", "named.ts"),
            ("ops.test.ts", "ops.ts", "ops.ts")} <= imports, sorted(imports)
