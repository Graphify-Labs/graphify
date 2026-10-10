"""Calls inside an exported function resolve through the import table (#3346).

`_js_top_level_function_bodies` scanned only direct program children, so a
top-level `export function f(){}` / `export const g = () => {}` — wrapped in an
export_statement — was skipped, and the calls inside it never became `uses`
facts. The visible symptom: an aliased-import call (`import { bar as baz };
baz()`) produced no `calls` edge, because only the use-fact path consults the
import alias table; the plain-name global resolver has no `baz` to match.
"""

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
