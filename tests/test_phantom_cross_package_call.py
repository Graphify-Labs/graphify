"""#1659 — a JS/TS call with no local definition and no import must not bind to
a same-named export in an unrelated package that was never imported.

JS/TS modules have no implicit cross-module scope: a call into another file is
real only if the caller imported it. The cross-file resolver used to fall back
to any lone same-named export repo-wide and emit a `calls` edge at INFERRED/0.8,
so on a monorepo a package that exports generically-named symbols (`*Schema`,
`validate`, ...) appeared depended-on by packages that import nothing from it.

The fix gates JS/TS cross-file call attribution on import evidence; other
languages keep the #1553 single-candidate resolution (headers, autoload,
same-package implicit scope legitimately call across files with no import).
"""
from __future__ import annotations

from pathlib import Path

from graphify.extract import extract


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _calls(files: list[Path], base: Path) -> set[tuple[str, str, str]]:
    r = extract(files, cache_root=base, parallel=False)
    lbl = {n["id"]: n["label"] for n in r["nodes"]}
    return {
        (lbl.get(e["source"], ""), lbl.get(e["target"], ""), e.get("confidence"))
        for e in r["edges"] if e["relation"] == "calls"
    }


def test_unimported_cross_package_call_emits_no_edge(tmp_path: Path) -> None:
    _write(tmp_path / "pkg-a/src/index.ts",
           "declare function validate(x: number): boolean;\n"
           "export function run(x: number): boolean { return validate(x); }\n")
    _write(tmp_path / "pkg-b/src/index.ts",
           "export function validate(name: string): boolean { return name.length > 0; }\n")
    calls = _calls(sorted(tmp_path.rglob("*.ts")), tmp_path)
    assert not any("run" in s and "validate" in t for s, t, _ in calls), calls


def test_many_files_do_not_collapse_onto_one_export(tmp_path: Path) -> None:
    # The real-world symptom: N packages importing nothing all showed edges to a
    # single package that exported a generically-named symbol.
    _write(tmp_path / "proto/index.ts",
           "export function encode(x: string): string { return x; }\n")
    for i in range(4):
        _write(tmp_path / f"svc{i}/index.ts",
               "declare function encode(x: string): string;\n"
               f"export function use{i}(x: string) {{ return encode(x); }}\n")
    calls = _calls(sorted(tmp_path.rglob("*.ts")), tmp_path)
    assert not any("encode" in t for _s, t, _ in calls), calls


def test_imported_cross_file_call_still_resolves(tmp_path: Path) -> None:
    # A real import must still resolve (and be promoted to EXTRACTED).
    _write(tmp_path / "a.ts",
           'import { validate } from "./b";\n'
           "export function run(x: number) { return validate(x); }\n")
    _write(tmp_path / "b.ts",
           "export function validate(name: string): boolean { return name.length > 0; }\n")
    calls = _calls([tmp_path / "a.ts", tmp_path / "b.ts"], tmp_path)
    resolved = [c for c in calls if "run" in c[0] and "validate" in c[1]]
    assert resolved, calls
    assert resolved[0][2] == "EXTRACTED"


def test_same_file_call_unaffected(tmp_path: Path) -> None:
    _write(tmp_path / "s.ts",
           "function helper() { return 1; }\n"
           "export function main() { return helper(); }\n")
    calls = _calls([tmp_path / "s.ts"], tmp_path)
    assert any("main" in s and "helper" in t for s, t, _ in calls), calls


def test_non_js_single_candidate_cross_file_still_resolves(tmp_path: Path) -> None:
    # The gate is JS/TS-only. Ruby (autoload, no require) legitimately calls a
    # lone same-named function across files without an import — keep the #1553
    # single-candidate resolution for it.
    _write(tmp_path / "helper.rb", "def transform(data)\n  data.upcase\nend\n")
    _write(tmp_path / "main.rb", "def handle(v)\n  transform(v)\nend\n")
    calls = _calls([tmp_path / "main.rb", tmp_path / "helper.rb"], tmp_path)
    assert any("handle" in s and "transform" in t for s, t, _ in calls), calls
