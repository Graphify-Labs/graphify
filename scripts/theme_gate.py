#!/usr/bin/env python3
"""Theme coverage gate: every active grep case in a Shopify theme must be in graph.json.

Measures categories a-f against ``THEME/graphify-out/graph.json`` with its own
Liquid masking (no ``graphify`` import, so the gate cannot share a bug with the
extractor it judges). Exit 0 = all categories at 100 %, 1 = a miss, 2 = bad input.

Usage: theme_gate.py THEME [THEME ...] [--categories a,b,c,d,e,f] [--max-failures N] [--json]
"""
from __future__ import annotations

import argparse
import bisect
import json
import re
import sys
from pathlib import Path

CATEGORIES = "abcdef"
LIQUID_DIRS = ("layout", "sections", "snippets", "blocks", "templates")

_TAG = re.compile(r"\{%-?(.*?)-?%\}", re.S)
_TAG_NAME = re.compile(r"\s*(#|[A-Za-z_]\w*)")
_END_RAW = re.compile(r"\{%-?\s*endraw\s*-?%\}")


def _blank(text: str, start: int, end: int, out: list[str]) -> None:
    for i in range(start, end):
        if out[i] != "\n":
            out[i] = " "


def _mask_liquid_tag_body(text: str, start: int, end: int, out: list[str]) -> None:
    """Blank ``#`` lines and comment blocks (nested) inside a ``{% liquid %}`` body."""
    depth = 0
    pos = start
    for line in text[start:end].split("\n"):
        stripped = line.strip()
        word = stripped.split(None, 1)[0] if stripped else ""
        line_end = pos + len(line)
        if depth:
            _blank(text, pos, line_end, out)
            if word == "comment":
                depth += 1
            elif word == "endcomment":
                depth -= 1
        elif word == "comment":
            depth = 1
            _blank(text, pos, line_end, out)
        elif stripped.startswith("#"):
            _blank(text, pos, line_end, out)
        pos = line_end + 1


def mask_inactive(text: str) -> str:
    """Blank what Liquid never renders, keeping every newline so line numbers hold.

    Covers nested ``{% comment %}`` (depth counter; a ``{% raw %}`` inside hides
    its ``comment``/``endcomment``), ``raw``, ``doc``, ``schema``, ``{% # … %}``
    and ``#`` / comment lines inside ``{% liquid %}``.
    """
    out = list(text)
    depth = 0
    resume = 0  # tags before this offset were consumed by a raw/doc/schema skip
    for m in _TAG.finditer(text):
        if m.start() < resume:
            continue
        nm = _TAG_NAME.match(m.group(1))
        name = nm.group(1) if nm else ""
        if depth:
            _blank(text, m.start(), m.end(), out)
            if name == "comment":
                depth += 1
            elif name == "endcomment":
                depth -= 1
            elif name == "raw":
                end = _END_RAW.search(text, m.end())
                resume = end.end() if end else len(text)
                _blank(text, m.end(), resume, out)
            continue
        if name == "comment":
            depth = 1
            _blank(text, m.start(), m.end(), out)
        elif name == "#":
            _blank(text, m.start(), m.end(), out)
        elif name in ("raw", "doc", "schema"):
            closer = re.compile(r"\{%-?\s*end" + name + r"\s*-?%\}")
            end = closer.search(text, m.end())
            resume = end.end() if end else len(text)
            _blank(text, m.start(), resume, out)
        elif name == "liquid":
            _mask_liquid_tag_body(text, m.start() + 2, m.end() - 2, out)
    return "".join(out)


def norm(label: str) -> str:
    """Normalize a node label: drop surrounding ``<>`` and a trailing ``()``."""
    s = str(label or "").strip()
    if s.startswith("<") and s.endswith(">"):
        s = s[1:-1]
    if s.endswith("()"):
        s = s[:-2]
    return s


class _Lines:
    def __init__(self, text: str) -> None:
        self.starts = [0] + [m.end() for m in re.finditer("\n", text)]

    def of(self, offset: int) -> int:
        return bisect.bisect_right(self.starts, offset)


def _liquid_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for d in LIQUID_DIRS:
        base = root / d
        if base.is_dir():
            files.extend(sorted(p for p in base.rglob("*.liquid") if p.is_file()))
    return files


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8", errors="replace")


def _rel(root: Path, p: Path) -> str:
    return p.relative_to(root).as_posix()


# ---------------------------------------------------------------- graph index

class Graph:
    """Read-only view over graph.json, reimplemented here on purpose."""

    def __init__(self, path: Path, root: Path) -> None:
        data = json.loads(path.read_text(encoding="utf-8"))
        self.root = root.resolve().as_posix().rstrip("/") + "/"
        self.nodes: dict[str, dict] = {n["id"]: n for n in data.get("nodes", []) if "id" in n}
        edges = data.get("links", data.get("edges", []))
        self.edges_at: dict[tuple[str, int], list[dict]] = {}
        self.out: dict[str, list[dict]] = {}
        for e in edges:
            src_file = self.rel(e.get("source_file"))
            for ln in self._lines(e, src_file):
                self.edges_at.setdefault((src_file, ln), []).append(e)
            self.out.setdefault(e.get("source"), []).append(e)
        self.nodes_at: dict[tuple[str, int], list[dict]] = {}
        for n in self.nodes.values():
            m = re.fullmatch(r"L(\d+)", str(n.get("source_location") or ""))
            if m:
                self.nodes_at.setdefault((self.rel(n.get("source_file")), int(m.group(1))), []).append(n)

    def rel(self, f: object) -> str:
        s = str(f or "").replace("\\", "/")
        return s[len(self.root):] if s.startswith(self.root) else s

    def _lines(self, e: dict, src_file: str) -> set[int]:
        lines: set[int] = set()
        for ev in (e, *[a for a in (e.get("also_seen") or []) if isinstance(a, dict)]):
            if ev is not e and ev.get("source_file") not in (None, "") and self.rel(ev["source_file"]) != src_file:
                continue
            m = re.fullmatch(r"L(\d+)", str(ev.get("source_location") or ""))
            if m:
                lines.add(int(m.group(1)))
        return lines

    def targets(self, file: str, line: int) -> list[dict]:
        """Destination nodes of every edge seen at ``file:line``."""
        return [self.nodes[e["target"]] for e in self.edges_at.get((file, line), []) if e.get("target") in self.nodes]

    def target_edges(self, file: str, line: int) -> list[tuple[dict, dict]]:
        return [(e, self.nodes[e["target"]]) for e in self.edges_at.get((file, line), []) if e.get("target") in self.nodes]


def _is_unresolved(n: dict) -> bool:
    return bool(n.get("unresolved"))


# -------------------------------------------------------------------- cases

Case = tuple[str, int, str]  # file, line, key

_CALL = re.compile(r"""\b(render|include|section)\s+(['"])([^'"\n]+)\2""")


def cases_a(root: Path) -> list[tuple[str, int, str, str]]:
    """render/include/section calls with a literal name: (file, line, name, expected path)."""
    out: list[tuple[str, int, str, str]] = []
    for p in _liquid_files(root):
        text = _read(p)
        masked = mask_inactive(text)
        ln = _Lines(masked)
        rel = _rel(root, p)
        for m in _TAG.finditer(masked):
            body = m.group(1)
            nm = _TAG_NAME.match(body)
            name = nm.group(1) if nm else ""
            if name == "liquid":
                base = m.start(1)
                for lm in re.finditer(r"^[ \t]*(render|include|section)[ \t]+(['\"])([^'\"\n]+)\2", body, re.M):
                    out.append((rel, ln.of(base + lm.start()), lm.group(3), _expected(lm.group(1), lm.group(3))))
            elif name in ("render", "include", "section"):
                cm = _CALL.match(body.lstrip())
                if cm:
                    off = m.start(1) + (len(body) - len(body.lstrip()))
                    out.append((rel, ln.of(off), cm.group(3), _expected(cm.group(1), cm.group(3))))
    return out


def _expected(kind: str, name: str) -> str:
    return f"sections/{name}.liquid" if kind == "section" else f"snippets/{name}.liquid"


_SELECTOR_TOKEN = re.compile(r"[.#][A-Za-z_-][\w-]*")


def _strip_css(text: str) -> str:
    """Blank CSS comments, strings and Liquid spans, keeping newlines."""
    out = list(text)
    for m in re.finditer(r"/\*.*?\*/|\"(?:[^\"\\\n]|\\.)*\"|'(?:[^'\\\n]|\\.)*'|\{\{.*?\}\}|\{%.*?%\}", text, re.S):
        _blank(text, m.start(), m.end(), out)
    return "".join(out)


def css_selectors(text: str) -> list[tuple[int, str]]:
    """Class/id selector tokens in selector position: (line, ``.x`` | ``#x``)."""
    clean = _strip_css(mask_inactive(text))
    ln = _Lines(clean)
    found: list[tuple[int, str]] = []
    start = 0
    for i, ch in enumerate(clean):
        if ch in ";}":
            start = i + 1
        elif ch == "{":
            prelude = clean[start:i]
            if not prelude.lstrip().startswith("@"):
                _scan_prelude(prelude, start, ln, found)
            start = i + 1
    return found


def _scan_prelude(prelude: str, base: int, ln: _Lines, found: list[tuple[int, str]]) -> None:
    view = list(prelude)
    for pm in re.finditer(r"::?[\w-]+(?:\([^()]*\))?|\[[^\]]*\]", prelude):
        _blank(prelude, pm.start(), pm.end(), view)
    for tm in _SELECTOR_TOKEN.finditer("".join(view)):
        found.append((ln.of(base + tm.start()), tm.group(0)))


def cases_b(root: Path) -> list[Case]:
    out: list[Case] = []
    assets = root / "assets"
    if not assets.is_dir():
        return out
    for p in sorted(assets.glob("*.css.liquid")):
        rel = _rel(root, p)
        out.extend((rel, line, key) for line, key in css_selectors(_read(p)))
    for p in sorted(assets.glob("*.js.liquid")):
        rel = _rel(root, p)
        text = mask_inactive(_read(p))
        ln = _Lines(text)
        for m in re.finditer(r"\b(?:function|class)\s+([A-Za-z_$][\w$]*)", text):
            out.append((rel, ln.of(m.start()), m.group(1)))
    return out


_DEFINE = re.compile(r"""customElements\s*\.\s*define\s*\(\s*(['"])([\w-]+)\1""")
_JS_BLOCK = re.compile(r"\{%-?\s*javascript\s*-?%\}(.*?)\{%-?\s*endjavascript\s*-?%\}", re.S)


def _defined_elements(root: Path) -> set[str]:
    names: set[str] = set()
    assets = root / "assets"
    if assets.is_dir():
        for p in [*assets.glob("*.js"), *assets.glob("*.js.liquid")]:
            names.update(m.group(2) for m in _DEFINE.finditer(_read(p)))
    for p in _liquid_files(root):
        for jm in _JS_BLOCK.finditer(_read(p)):
            names.update(m.group(2) for m in _DEFINE.finditer(jm.group(1)))
    return names


def cases_c(root: Path) -> list[Case]:
    defined = _defined_elements(root)
    out: list[Case] = []
    if not defined:
        return out
    for p in _liquid_files(root):
        masked = mask_inactive(_read(p))
        ln = _Lines(masked)
        rel = _rel(root, p)
        for m in re.finditer(r"""<([a-z][\w]*(?:-[\w]+)+)|\bis\s*=\s*(['"])([a-z][\w]*(?:-[\w]+)+)\2""", masked):
            name = m.group(1) or m.group(3)
            if name in defined:
                out.append((rel, ln.of(m.start()), name))
    return out


_SETTING = re.compile(
    r"(?<![\w.])(?<!t:)(section\.settings|block\.settings|settings)(?:\.([A-Za-z_]\w*)|\[\s*(['\"])([\w-]+)\3\s*\])"
)
_LIQUID_SPAN = re.compile(r"\{\{.*?\}\}|\{%.*?%\}", re.S)


def cases_d(root: Path) -> list[Case]:
    out: list[Case] = []
    for p in _liquid_files(root):
        masked = mask_inactive(_read(p))
        ln = _Lines(masked)
        rel = _rel(root, p)
        for sp in _LIQUID_SPAN.finditer(masked):
            for m in _SETTING.finditer(sp.group(0)):
                out.append((rel, ln.of(sp.start() + m.start()), f"{m.group(1)}.{m.group(2) or m.group(4)}"))
    return out


_META_BRACKET = re.compile(r"""metafields\[['"]([\w-]+)['"]\]\[['"]([\w-]+)['"]\]""")


def cases_f(root: Path) -> list[Case]:
    out: list[Case] = []
    for p in _liquid_files(root):
        masked = mask_inactive(_read(p))
        ln = _Lines(masked)
        rel = _rel(root, p)
        for m in re.finditer(r"\w+\.metafields\.(\w+)\.(\w+)", masked):
            out.append((rel, ln.of(m.start()), f"metafields.{m.group(1)}.{m.group(2)}"))
        for m in _META_BRACKET.finditer(masked):
            out.append((rel, ln.of(m.start()), f"metafields.{m.group(1)}.{m.group(2)}"))
    return out


_CLASS_ATTR = re.compile(r"""(?<![\w-])class\s*=\s*(["'])(.*?)\1""", re.S)
_CLASS_TOKEN = re.compile(r"\S+")
_VALID_TOKEN = re.compile(r"^[A-Za-z_-][\w-]*$")


def _css_defined_classes(root: Path) -> set[str]:
    defined: set[str] = set()
    assets = root / "assets"
    if not assets.is_dir():
        return defined
    for p in [*assets.glob("*.css"), *assets.glob("*.css.liquid")]:
        defined.update(key for _l, key in css_selectors(_read(p)) if key.startswith("."))
    return defined


def cases_e(root: Path) -> list[Case]:
    defined = _css_defined_classes(root)
    out: list[Case] = []
    for p in _liquid_files(root):
        masked = mask_inactive(_read(p))
        view_chars = list(masked)
        for sp in _LIQUID_SPAN.finditer(masked):
            _blank(masked, sp.start(), sp.end(), view_chars)
        view = "".join(view_chars)
        ln = _Lines(view)
        rel = _rel(root, p)
        for am in _CLASS_ATTR.finditer(view):
            base = am.start(2)
            for tm in _CLASS_TOKEN.finditer(am.group(2)):
                tok = tm.group(0)
                if _VALID_TOKEN.match(tok) and f".{tok}" in defined:
                    out.append((rel, ln.of(base + tm.start()), f".{tok}"))
    return out


# --------------------------------------------------------------- definitions

def _schema_ids(text: str) -> set[str]:
    """Setting ids declared in the ``{% schema %}`` of a Liquid file (own and block settings)."""
    ids: set[str] = set()
    m = re.search(r"\{%-?\s*schema\s*-?%\}(.*?)\{%-?\s*endschema\s*-?%\}", text, re.S)
    if not m:
        return ids
    try:
        data = json.loads(m.group(1))
    except ValueError:
        return ids

    def walk(o: object) -> None:
        if isinstance(o, dict):
            sid = o.get("id")
            if isinstance(sid, str) and ("type" in o):
                ids.add(sid)
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)

    walk(data)
    return ids


def _global_setting_ids(root: Path) -> set[str]:
    p = root / "config" / "settings_schema.json"
    if not p.is_file():
        return set()
    try:
        data = json.loads(_read(p))
    except ValueError:
        return set()
    ids: set[str] = set()

    def walk(o: object) -> None:
        if isinstance(o, dict):
            sid = o.get("id")
            if isinstance(sid, str) and "type" in o:
                ids.add(sid)
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)

    walk(data)
    return ids


def _metafield_defs(root: Path) -> set[str] | None:
    p = root / ".shopify" / "metafields.json"
    if not p.is_file():
        return None
    try:
        data = json.loads(_read(p))
    except ValueError:
        return None
    keys: set[str] = set()

    def walk(o: object) -> None:
        if isinstance(o, dict):
            if isinstance(o.get("namespace"), str) and isinstance(o.get("key"), str):
                keys.add(f"metafields.{o['namespace']}.{o['key']}")
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)

    walk(data)
    return keys


def _callers(root: Path) -> dict[str, set[str]]:
    """file -> every file that (transitively) renders it, from the grep-level (a) cases."""
    direct: dict[str, set[str]] = {}
    for f, _l, _n, target in cases_a(root):
        direct.setdefault(target, set()).add(f)
    closure: dict[str, set[str]] = {}
    for f in direct:
        seen: set[str] = set()
        todo = list(direct[f])
        while todo:
            c = todo.pop()
            if c in seen:
                continue
            seen.add(c)
            todo.extend(direct.get(c, ()))
        closure[f] = seen
    return closure


# ------------------------------------------------------------------ measuring

def measure(root: Path, graph: Graph, cats: str) -> dict[str, dict]:
    result: dict[str, dict] = {}
    for cat in cats:
        covered = 0
        failures: list[list] = []
        warnings: list[list] = []
        cases: list = []

        def hit(file: str, line: int, key: str) -> bool:
            if any(norm(n.get("label")) == key for n in graph.targets(file, line)):
                return True
            return any(norm(n.get("label")) == key for n in graph.nodes_at.get((file, line), []))

        if cat == "a":
            for file, line, name, expected in cases_a(root):
                cases.append(1)
                if any(graph.rel(n.get("source_file")) == expected for n in graph.targets(file, line)):
                    covered += 1
                else:
                    failures.append([file, line, f"{name} -> {expected}"])
        elif cat == "b":
            for file, line, key in cases_b(root):
                cases.append(1)
                if hit(file, line, key):
                    covered += 1
                else:
                    failures.append([file, line, key])
        elif cat == "c":
            for file, line, key in cases_c(root):
                cases.append(1)
                if any(norm(n.get("label")) == key and not _is_unresolved(n) for n in graph.targets(file, line)):
                    covered += 1
                else:
                    failures.append([file, line, key])
        elif cat == "d":
            glob_ids = _global_setting_ids(root)
            callers = _callers(root)
            schema_cache: dict[str, set[str]] = {}

            def schema_of(f: str) -> set[str]:
                if f not in schema_cache:
                    p = root / f
                    schema_cache[f] = _schema_ids(_read(p)) if p.is_file() else set()
                return schema_cache[f]

            for file, line, key in cases_d(root):
                cases.append(1)
                scope, _, sid = key.rpartition(".")
                if scope == "settings":
                    definers = ["config/settings_schema.json"] if sid in glob_ids else []
                else:
                    definers = [f for f in (file, *sorted(callers.get(file, ()))) if sid in schema_of(f)]
                targets = [n for n in graph.targets(file, line) if norm(n.get("label")) == key]
                if definers:
                    ok = any(not _is_unresolved(n) and graph.rel(n.get("source_file")) in definers for n in targets)
                    if ok:
                        covered += 1
                    else:
                        failures.append([file, line, key])
                elif targets:
                    covered += 1
                    if all(_is_unresolved(n) for n in targets):
                        warnings.append([file, line, key])
                else:
                    failures.append([file, line, key])
        elif cat == "e":
            for file, line, key in cases_e(root):
                cases.append(1)
                if any(norm(n.get("label")) == key and not _is_unresolved(n) for n in graph.targets(file, line)):
                    covered += 1
                else:
                    failures.append([file, line, key])
        elif cat == "f":
            defs = _metafield_defs(root)
            for file, line, key in cases_f(root):
                cases.append(1)
                use = [n for n in graph.targets(file, line) if norm(n.get("label")) == key]
                if defs is None:
                    failures.append([file, line, key])
                elif key in defs:
                    ok = any(
                        graph.rel(graph.nodes[e["target"]].get("source_file")) == ".shopify/metafields.json"
                        for u in use
                        for e in graph.out.get(u["id"], [])
                        if e.get("target") in graph.nodes
                    )
                    if ok:
                        covered += 1
                    else:
                        failures.append([file, line, key])
                elif use:
                    covered += 1
                    if all(_is_unresolved(n) for n in use):
                        warnings.append([file, line, key])
                else:
                    failures.append([file, line, key])
        result[cat] = {"covered": covered, "total": len(cases), "failures": failures, "warnings": warnings}
    return result


def _pct(r: dict) -> str:
    if r["total"] == 0:
        return "n/a (0 cases)"
    return f"{r['covered']}/{r['total']} = {100 * r['covered'] // r['total']}%" if r["covered"] < r["total"] \
        else f"{r['covered']}/{r['total']} = 100%"


def main(argv: list[str] | None = None) -> int:
    """CLI entry point; returns the process exit code (0 ok, 1 miss, 2 bad input)."""
    ap = argparse.ArgumentParser(description="Check graph.json covers every active grep case of a theme.")
    ap.add_argument("themes", nargs="+", help="theme root(s) containing graphify-out/graph.json")
    ap.add_argument("--categories", default=CATEGORIES, help="comma list drawn from a,b,c,d,e,f")
    ap.add_argument("--max-failures", type=int, default=5, help="failures listed per category")
    ap.add_argument("--json", action="store_true", help="emit JSON {theme: {category: {covered,total,failures,warnings}}}")
    try:
        args = ap.parse_args(argv)
    except SystemExit:
        return 2
    cats = [c.strip() for c in args.categories.split(",") if c.strip()]
    if not cats or any(c not in tuple(CATEGORIES) for c in cats) or args.max_failures < 0:
        print("invalid --categories / --max-failures", file=sys.stderr)
        return 2
    report: dict[str, dict] = {}
    worst = 0
    for t in args.themes:
        root = Path(t)
        gpath = root / "graphify-out" / "graph.json"
        try:
            graph = Graph(gpath, root)
        except (OSError, ValueError, KeyError) as exc:
            print(f"cannot read {gpath}: {exc}", file=sys.stderr)
            return 2
        res = measure(root, graph, "".join(cats))
        report[root.name] = res
        if any(r["covered"] < r["total"] for r in res.values()):
            worst = 1
    if args.json:
        json.dump(report, sys.stdout, indent=1)
        print()
    else:
        for theme, res in report.items():
            print(f"== {theme}")
            for cat, r in res.items():
                w = f" (+{len(r['warnings'])} warnings)" if r["warnings"] else ""
                print(f"  ({cat}) {_pct(r)}{w}")
                for f, ln, key in r["failures"][: args.max_failures]:
                    print(f"      {f}:{ln} {key}")
    return worst


if __name__ == "__main__":
    sys.exit(main())
