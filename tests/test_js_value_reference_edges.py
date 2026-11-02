"""Value reads in JS/TS emit symbol-level `references` edges (#4265).

A function body that reads an imported or module-level value — `SeatInput`,
`SeatInput.parse(...)`, a constant handed to a call — had no edge to it: the
graph carried only `file --imports--> symbol`, so the function was reachable
from the value only through `contains` and `affected`/`path` stopped at the
file. These tests pin the new `references[value]` edges for top-level
functions, arrow-const functions, and class methods, plus the shadowing guards
that keep the pass from inventing edges.
"""

from __future__ import annotations

from graphify.extract import extract


def _graph(tmp_path, files):
    for name, body in files.items():
        p = tmp_path / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")
    r = extract([tmp_path / n for n in files],
                cache_root=tmp_path / "graphify-out", parallel=False)
    labels = {n["id"]: n.get("label", "") for n in r["nodes"]}
    refs = {
        (labels.get(e["source"], ""), labels.get(e["target"], ""))
        for e in r["edges"] if e["relation"] == "references"
        and e.get("context") == "value"
    }
    calls = {
        (labels.get(e["source"], ""), labels.get(e["target"], ""))
        for e in r["edges"] if e["relation"] == "calls"
    }
    return refs, calls, r


def _has(edges, caller_sub, target):
    return any(caller_sub in s.lower() and t.rstrip("()") == target for s, t in edges)


SCHEMA = "export const SeatInput = { parse: (x: string) => x };\nexport const MAX = 10;\n"


def test_imported_value_read_in_function(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    refs, _calls, _ = _graph(tmp_path, {
        "schema.ts": SCHEMA,
        "route.ts": "import { SeatInput } from './schema';\n"
                    "export function buildManifest() { return SeatInput; }\n",
    })
    assert _has(refs, "buildmanifest", "SeatInput"), sorted(refs)


def test_imported_value_member_read_in_function(tmp_path, monkeypatch):
    """`SeatInput.parse(id)` reads the imported object, not its member."""
    monkeypatch.chdir(tmp_path)
    refs, _calls, _ = _graph(tmp_path, {
        "schema.ts": SCHEMA,
        "route.ts": "import { SeatInput } from './schema';\n"
                    "export function readRoute(id: string) { return SeatInput.parse(id); }\n",
    })
    assert _has(refs, "readroute", "SeatInput"), sorted(refs)


def test_imported_value_read_in_arrow_const(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    refs, _calls, _ = _graph(tmp_path, {
        "schema.ts": SCHEMA,
        "use.ts": "import { MAX } from './schema';\n"
                  "export const limit = () => MAX;\n",
    })
    assert _has(refs, "limit", "MAX"), sorted(refs)


def test_imported_value_read_in_class_method(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    refs, _calls, _ = _graph(tmp_path, {
        "schema.ts": SCHEMA,
        "widget.ts": "import { SeatInput } from './schema';\n"
                     "export class Widget {\n"
                     "  render() { return SeatInput.parse('x'); }\n"
                     "  never() { return 1; }\n"
                     "}\n",
    })
    assert _has(refs, "render", "SeatInput"), sorted(refs)
    assert not _has(refs, "never", "SeatInput"), sorted(refs)


def test_same_file_module_value_read(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    refs, _calls, _ = _graph(tmp_path, {
        "local.ts": "const LOCAL = { a: 1 };\n"
                    "export function sameFile() { return LOCAL; }\n"
                    "export function notAReference() { return 42; }\n",
    })
    assert _has(refs, "samefile", "LOCAL"), sorted(refs)
    assert not _has(refs, "notareference", "LOCAL"), sorted(refs)


def test_parameter_shadowing_suppresses_reference(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    refs, _calls, _ = _graph(tmp_path, {
        "schema.ts": SCHEMA,
        "shadow.ts": "import { SeatInput } from './schema';\n"
                     "export function shadowParam(SeatInput: any) { return SeatInput; }\n",
    })
    assert not _has(refs, "shadowparam", "SeatInput"), sorted(refs)


def test_local_binding_shadowing_suppresses_reference(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    refs, _calls, _ = _graph(tmp_path, {
        "schema.ts": SCHEMA,
        "shadow.ts": "import { MAX } from './schema';\n"
                     "export function shadowLet() { const MAX = 3; return MAX; }\n",
    })
    assert not _has(refs, "shadowlet", "MAX"), sorted(refs)


def test_invoked_name_does_not_also_emit_reference(tmp_path, monkeypatch):
    """A called name is owned by the call-graph pass; a second `references`
    edge for the same pair would suppress the real cross-file `calls` edge."""
    monkeypatch.chdir(tmp_path)
    refs, calls, _ = _graph(tmp_path, {
        "schema.ts": SCHEMA,
        "call.ts": "import { MAX } from './schema';\n"
                   "export function useValue() { return MAX; }\n"
                   "export function useCall() { return MAX(); }\n",
    })
    assert _has(refs, "usevalue", "MAX"), sorted(refs)
    assert not _has(refs, "usecall", "MAX"), sorted(refs)
    assert _has(calls, "usecall", "MAX"), sorted(calls)


def test_jsx_component_usage_still_calls_cross_file(tmp_path, monkeypatch):
    """Regression: the value-read pass must not shadow the JSX `calls` edge."""
    monkeypatch.chdir(tmp_path)
    refs, calls, _ = _graph(tmp_path, {
        "components/bubble.tsx": "export function Bubble() { return <span />; }\n",
        "app/screen.tsx": 'import { Bubble } from "../components/bubble";\n'
                          "export function Screen() {\n"
                          "  return <Bubble />;\n"
                          "}\n",
    })
    assert _has(calls, "screen", "Bubble"), sorted(calls)
    assert not _has(refs, "screen", "Bubble"), sorted(refs)
