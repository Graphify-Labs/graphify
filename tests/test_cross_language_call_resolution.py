"""Cross-language call resolution — a call in one language must never bind by
name to a definition in another language family.

The cross-file resolver matched raw-call callees against a repo-wide label
index with no language check, so in a repo that mixes a web app with a native
Android app a TSX callback passed by name (``register(refreshHeading)``)
resolved to a same-named Kotlin method and shipped as an INFERRED
``indirect_call`` edge — a phantom the extraction spec explicitly forbids
("calls edges MUST stay within one language"). Direct calls from non-JS/TS
languages had the same hole: a Python call bound to a Kotlin ``fun``.

The fix filters resolution candidates by language interop family. Families are
grouped by REAL interop so legitimate cross-language resolution keeps working:
Kotlin/Java share the JVM, C/C++/Objective-C share headers, JS/TS variants
compile into one module graph. Candidates with no known family (non-code
nodes) are never filtered, preserving the previous permissive behavior.
"""
from __future__ import annotations

from pathlib import Path

from graphify.extract import extract


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _call_edges(files: list[Path], base: Path) -> set[tuple[str, str, str, str]]:
    r = extract(files, cache_root=base, parallel=False)
    lbl = {n["id"]: n["label"] for n in r["nodes"]}
    return {
        (lbl.get(e["source"], ""), lbl.get(e["target"], ""), e["relation"], e.get("confidence"))
        for e in r["edges"] if e["relation"] in ("calls", "indirect_call")
    }


def test_tsx_callback_does_not_bind_to_kotlin_method(tmp_path: Path) -> None:
    # The real-world symptom: a repo with a web app and a native Android app.
    # A TSX component passes a callback by name; the only same-named definition
    # repo-wide is a Kotlin method. No edge must be emitted.
    _write(tmp_path / "web/Upcoming.tsx",
           "declare function register(cb: () => void): void;\n"
           "export function UpcomingPanel() {\n"
           "  register(refreshHeading);\n"
           "  return null;\n"
           "}\n")
    _write(tmp_path / "android/HeadingSensorBridge.kt",
           "class HeadingSensorBridge {\n"
           "    fun refreshHeading() {\n"
           "        println(\"native sensor\")\n"
           "    }\n"
           "}\n")
    edges = _call_edges(sorted(tmp_path.rglob("*.tsx")) + sorted(tmp_path.rglob("*.kt")), tmp_path)
    assert not any("refreshHeading" in t for _s, t, _r, _c in edges), edges


def test_python_call_does_not_bind_to_kotlin_function(tmp_path: Path) -> None:
    # Direct-call path (non-JS/TS callers have no import-evidence gate): a bare
    # Python call must not resolve to the lone same-named Kotlin definition.
    _write(tmp_path / "py/worker.py",
           "def process():\n"
           "    return refreshHeading()\n")
    _write(tmp_path / "android/HeadingSensorBridge.kt",
           "class HeadingSensorBridge {\n"
           "    fun refreshHeading() {\n"
           "        println(\"native sensor\")\n"
           "    }\n"
           "}\n")
    edges = _call_edges(sorted(tmp_path.rglob("*.py")) + sorted(tmp_path.rglob("*.kt")), tmp_path)
    assert not any("refreshHeading" in t for _s, t, _r, _c in edges), edges


def test_same_language_callback_still_resolves(tmp_path: Path) -> None:
    # Positive control: a TS callback passed by name with a same-language
    # definition and import evidence keeps resolving as INFERRED indirect_call.
    _write(tmp_path / "a.ts",
           'import { refreshHeading } from "./b";\n'
           "declare function register(cb: () => void): void;\n"
           "export function run() { register(refreshHeading); }\n")
    _write(tmp_path / "b.ts",
           "export function refreshHeading(): void {}\n")
    edges = _call_edges([tmp_path / "a.ts", tmp_path / "b.ts"], tmp_path)
    resolved = [e for e in edges if "refreshHeading" in e[1] and e[2] == "indirect_call"]
    assert resolved, edges
    assert resolved[0][3] == "INFERRED"


def test_jvm_interop_kotlin_call_to_java_still_resolves(tmp_path: Path) -> None:
    # Kotlin and Java share the JVM — same interop family, so a Kotlin call to a
    # Java method must keep resolving exactly as it did before the guard.
    _write(tmp_path / "Alarm.java",
           "public class Alarm {\n"
           "    public static void ring() { System.out.println(\"ring\"); }\n"
           "}\n")
    _write(tmp_path / "Scheduler.kt",
           "fun schedule() {\n"
           "    ring()\n"
           "}\n")
    edges = _call_edges([tmp_path / "Alarm.java", tmp_path / "Scheduler.kt"], tmp_path)
    assert any("ring" in t for _s, t, _r, _c in edges), edges
