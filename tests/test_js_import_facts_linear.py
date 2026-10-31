"""Rebinding JS/TS import stubs must not walk every edge per import (#4905)."""
from pathlib import Path

from graphify.extract import extract
from graphify.extractors import resolution


def _project(root: Path, n: int) -> list[Path]:
    src = root / "src"
    src.mkdir()
    for i in range(n):
        lines = [f'import {{ f{(i + k) % n}_{k} }} from "./m{(i + k) % n}";' for k in range(1, 6)]
        lines += [f"export function f{i}_{k}() {{ return 1; }}" for k in range(1, 6)]
        lines.append("export const all = () => [" + ", ".join(f"f{(i + k) % n}_{k}()" for k in range(1, 6)) + "];")
        (src / f"m{i}.ts").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return sorted(src.glob("*.ts"))


def _source_path_calls(tmp_path: Path, monkeypatch, n: int) -> int:
    root = (tmp_path / str(n)).resolve()
    root.mkdir()
    paths = _project(root, n)
    real = resolution._js_source_path
    calls = 0

    def counting(source_file, base):
        nonlocal calls
        calls += 1
        return real(source_file, base)

    monkeypatch.setattr(resolution, "_js_source_path", counting)
    extract(paths, cache_root=root, root=root)
    monkeypatch.setattr(resolution, "_js_source_path", real)
    return calls


def test_source_path_lookups_grow_linearly_with_the_project(tmp_path, monkeypatch):
    small = _source_path_calls(tmp_path, monkeypatch, 20)
    large = _source_path_calls(tmp_path, monkeypatch, 40)

    assert large < small * 3


def test_import_stub_is_still_rebound_to_the_declaration(tmp_path):
    root = tmp_path.resolve()
    (root / "a.ts").write_text("export interface Shape { x: number }\n", encoding="utf-8")
    (root / "b.ts").write_text(
        'import { Shape } from "./a";\nexport function area(s: Shape) { return s.x; }\n', encoding="utf-8"
    )

    result = extract([root / "a.ts", root / "b.ts"], cache_root=root, root=root)

    declared = next(n["id"] for n in result["nodes"] if n["label"] == "Shape" and n.get("source_file"))
    targets = {e["target"] for e in result["edges"] if e["source_file"].endswith("b.ts")}
    assert declared in targets
