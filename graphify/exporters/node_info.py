"""node_info — per-node descriptions for the 3D graph.html viewer.

For every node this pulls, from the project's source files:

  k  kind         what the node is (Function, Method, Struct, Enum variant,
                  Document section, Shell script, External item, ...)
  s  signature    the declaration line (code) or the heading text (docs)
  d  description  the doc comment / comment block / docstring next to it, the
                  first paragraph under a Markdown heading, or graphify's own
                  ``rationale`` text
  l  location     ``file:line``

The viewer shows these in its floating node card. Nodes the source does not
comment get no ``d``; the page then builds a plain-language summary from the
graph's edges instead.

Everything here is best effort and read-only: a missing or unreadable file, a
file outside the project root, or a drifted line number just yields fewer
fields. Nothing is executed, and all text is later JSON-encoded and
HTML-escaped by the page before display.
"""
from __future__ import annotations

import os
import re
from pathlib import Path

import networkx as nx

from graphify.security import _CONTROL_CHAR_RE

MAX_DOC = 700
MAX_SIG = 240
_MAX_FILE_BYTES = 2_000_000
_SEARCH_RADIUS = 80  # line numbers drift after edits; look this far either way

_RUST = {".rs"}
_PYTHON = {".py", ".pyi", ".pyw"}
_C_LIKE = {
    ".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx", ".mts", ".cts", ".go", ".java",
    ".kt", ".kts", ".swift", ".c", ".h", ".cc", ".cpp", ".cxx", ".hpp", ".hh",
    ".cs", ".scala", ".dart", ".php", ".zig", ".groovy", ".m", ".mm", ".proto",
    ".sol", ".v", ".vue", ".svelte",
}
_HASH = {".rb", ".r", ".pl", ".pm", ".ex", ".exs", ".jl", ".nim"}
# Line-oriented files: the node's own line is its "signature", `#` comments
# above it its description.
_SCRIPT_KIND = {
    ".sh": "Shell script", ".bash": "Shell script", ".zsh": "Shell script",
    ".fish": "Shell script", ".ps1": "PowerShell script",
    ".yml": "YAML config", ".yaml": "YAML config", ".toml": "TOML config",
    ".cfg": "Config file", ".ini": "Config file", ".conf": "Config file",
    ".tf": "Terraform config", ".hcl": "HCL config", ".cmake": "CMake file",
    ".mk": "Makefile", ".dockerfile": "Dockerfile", ".env": "Environment file",
}
_DASH = {".lua", ".sql", ".hs", ".elm", ".ada", ".adb"}
_MARKDOWN = {".md", ".mdx", ".markdown"}
_TEXT = {".txt", ".rst", ".adoc"}

_FILE_KIND = {
    ".rs": "Rust source file", ".py": "Python module", ".pyi": "Python stub",
    ".js": "JavaScript file", ".mjs": "JavaScript module", ".cjs": "JavaScript file",
    ".jsx": "React (JSX) file", ".ts": "TypeScript file", ".tsx": "React (TSX) file",
    ".go": "Go source file", ".java": "Java source file", ".kt": "Kotlin file",
    ".swift": "Swift file", ".c": "C source file", ".h": "C/C++ header",
    ".cpp": "C++ source file", ".cc": "C++ source file", ".hpp": "C++ header",
    ".cs": "C# source file", ".rb": "Ruby file", ".php": "PHP file",
    ".sh": "Shell script", ".bash": "Shell script", ".zsh": "Shell script",
    ".yml": "YAML config", ".yaml": "YAML config", ".toml": "TOML config",
    ".md": "Document", ".mdx": "Document", ".txt": "Text file", ".sql": "SQL file",
    ".lua": "Lua file",
}

_DECL_KINDS = {
    "fn": "Function", "func": "Function", "function": "Function", "def": "Function",
    "async def": "Function", "sub": "Function",
    "class": "Class", "struct": "Struct", "enum": "Enum", "union": "Union",
    "interface": "Interface", "trait": "Trait", "protocol": "Protocol",
    "type": "Type alias", "typealias": "Type alias", "record": "Record",
    "object": "Object", "module": "Module", "mod": "Module", "namespace": "Namespace",
    "const": "Constant", "static": "Static", "let": "Variable", "var": "Variable",
    "val": "Value", "macro_rules!": "Macro", "impl": "impl block",
}
_DECL_KW = (
    r"async\s+def|def|async\s+function|function|fn|func|sub|class|struct|enum|union|"
    r"interface|trait|protocol|typealias|type|record|object|module|mod|namespace|"
    r"const|static|let|var|val|macro_rules!"
)
_DECORATOR_RE = re.compile(r"^\s*(#\[|#!\[|@[\w.]|\[[A-Z]\w*)")
_CALLABLE_HINT_RE = re.compile(r"=>|\bfunction\b|\blambda\b|=\s*\(")


def _clean(s: str, n: int) -> str:
    s = re.sub(r"\s+", " ", s)
    s = _CONTROL_CHAR_RE.sub("", s).strip()
    return s if len(s) <= n else s[: n - 1].rstrip() + "…"


def _bare_name(label: str) -> str:
    """`.method()` / `func()` / `macro!` -> the identifier graphify labelled."""
    name = label.strip()
    if name.startswith("."):
        name = name[1:]
    if name.endswith("()"):
        name = name[:-2]
    name = name.rstrip("!")
    # Qualified labels (`Type.method`, `mod::item`) declare only the last part.
    return re.split(r"::|\.", name)[-1] if name else name


class _SourceReader:
    """Reads project files once each, refusing anything outside *root*."""

    def __init__(self, root: Path | None):
        self.root = root.resolve() if root else None
        self._cache: dict[str, list[str] | None] = {}

    def lines(self, rel: str) -> list[str] | None:
        if rel in self._cache:
            return self._cache[rel]
        self._cache[rel] = None
        if self.root is None or not rel:
            return None
        try:
            p = Path(rel)
            p = (p if p.is_absolute() else self.root / p).resolve()
            p.relative_to(self.root)  # ValueError when outside the project
            if not p.is_file() or p.stat().st_size > _MAX_FILE_BYTES:
                return None
            text = p.read_text(encoding="utf-8", errors="replace")
        except (OSError, ValueError, RuntimeError):
            return None
        self._cache[rel] = text.split("\n")
        return self._cache[rel]


def _find_decl(L: list[str], start: int, name: str, variant: bool) -> tuple[int, str | None]:
    """Index and keyword of the declaration of *name* nearest to line *start*."""
    if not name or not re.match(r"^[A-Za-z_$][\w$]*$", name):
        return start, None
    n = re.escape(name)
    decl = re.compile(
        rf"(?:^|[^\w.])({_DECL_KW})\s+(?:\([^)]*\)\s*)?[*&]?\s*{n}\b"
    )
    impl = re.compile(rf"^\s*(?:unsafe\s+)?impl\b.*\b{n}\b")
    var = re.compile(rf"^\s*{n}\b\s*[,({{=]?\s*$|^\s*{n}\s*[,({{=]")
    for d in range(_SEARCH_RADIUS):
        for i in ((start - d, start + d) if d else (start,)):
            if not 0 <= i < len(L):
                continue
            line = L[i]
            stripped = line.lstrip()
            if stripped.startswith(("//", "#", "*", "/*", "--")) and not stripped.startswith("#["):
                continue
            m = decl.search(line)
            if m:
                return i, re.sub(r"\s+", " ", m.group(1))
            if d == 0 and impl.search(line):
                return i, "impl"
            if variant and var.match(line):
                return i, "variant"
    # No keyword declaration nearby (e.g. a TS/Java method `public foo(...)`):
    # trust graphify's own location when that line mentions the name.
    for i in (start, start + 1, start - 1):
        if 0 <= i < len(L) and re.search(rf"\b{n}\b", L[i]):
            return i, None
    return start, None


def _signature(L: list[str], i: int, python: bool) -> str:
    parts: list[str] = []
    depth = 0
    for j in range(i, min(i + 14, len(L))):
        t = L[j]
        if not python:
            t = re.sub(r"\s//.*$", "", t)
        t = t.rstrip()
        parts.append(t.strip())
        depth += t.count("(") + t.count("[") - t.count(")") - t.count("]")
        if depth > 0:
            continue
        if "{" in t or t.endswith((";", ",", ":", "=>", "=")) or (python and t.endswith(":")):
            break
    sig = " ".join(parts)
    sig = re.sub(r"\(\s+", "(", sig)
    sig = re.sub(r",\s*\)", ")", sig)
    sig = re.sub(r"\s*\{.*$", "", sig)
    sig = sig.rstrip(",;").rstrip()
    if python and sig.endswith(":"):
        sig = sig[:-1].rstrip()
    return _clean(sig, MAX_SIG)


def _comment_above(L: list[str], i: int, prefixes: tuple[str, ...]) -> str:
    """The contiguous comment block directly above line *i* (skipping attributes,
    decorators and annotations). Understands `/** ... */` blocks too."""
    j = i - 1
    while j >= 0 and _DECORATOR_RE.match(L[j]):
        j -= 1
    if j >= 0 and L[j].rstrip().endswith("*/"):
        block = []
        while j >= 0:
            s = L[j].strip()
            block.append(s)
            if s.startswith("/*"):
                break
            j -= 1
        block.reverse()
        text = []
        for s in block:
            s = re.sub(r"^/\*+!?|\*+/$", "", s).strip()
            s = re.sub(r"^\*+\s?", "", s)
            if s.startswith("@"):  # JSDoc / Javadoc tags: stop at @param etc.
                break
            text.append(s)
        return " ".join(t for t in text if t)
    out = []
    while j >= 0:
        s = L[j].strip()
        hit = next((p for p in prefixes if s.startswith(p)), None)
        if hit is None or s.startswith(("#!", "#[", "#![")):
            break
        out.append(s[len(hit):].strip())
        j -= 1
    out.reverse()
    return " ".join(x for x in out if x)


def _python_docstring(L: list[str], i: int) -> str:
    """Docstring of the def/class at line *i* (or of the module when i < 0)."""
    j = i
    if i >= 0:
        while j < len(L) and not L[j].split("#")[0].rstrip().endswith(":"):
            j += 1
            if j - i > 12:
                return ""
    j += 1
    while j < len(L) and (not L[j].strip() or (i < 0 and L[j].lstrip().startswith("#"))):
        j += 1
    if j >= len(L):
        return ""
    first = L[j].strip()
    m = re.match(r'^[rRuUbB]?("""|\'\'\')(.*)$', first)
    if not m:
        return ""
    q, rest = m.group(1), m.group(2)
    if q in rest:
        return rest.split(q)[0]
    out = [rest]
    for k in range(j + 1, min(j + 60, len(L))):
        if q in L[k]:
            out.append(L[k].split(q)[0])
            break
        out.append(L[k])
    # The summary paragraph is what fits in a card.
    para = []
    for s in out:
        if not s.strip() and para:
            break
        para.append(s.strip())
    return " ".join(p for p in para if p)


def _header_comment(L: list[str], prefixes: tuple[str, ...]) -> str:
    """Leading comment block of a file (shebang and blank lines skipped)."""
    doc: list[str] = []
    in_block = False
    for s in L[:60]:
        st = s.strip()
        if in_block:
            end = "*/" in st
            st = re.sub(r"\*+/.*$", "", st)
            st = re.sub(r"^\*+\s?", "", st).strip()
            if st.startswith("@"):
                break
            doc.append(st)
            if end:
                break
            continue
        if st.startswith("#!") and not doc:
            continue
        if st.startswith("/*"):
            in_block = True
            rest = re.sub(r"^/\*+!?", "", st)
            if "*/" in rest:
                doc.append(rest.split("*/")[0].strip())
                break
            doc.append(rest.strip())
            continue
        hit = next((p for p in prefixes if st.startswith(p)), None)
        if hit:
            doc.append(st[len(hit):].strip())
        elif st == "" and not doc:
            continue
        else:
            break
    return " ".join(d for d in doc if d)


def _is_file_node(node: dict, sf: str, line_no: int | None) -> bool:
    label = str(node.get("label") or "")
    base = os.path.basename(sf)
    if node.get("node_kind") == "page" or label in (base, sf):
        return True
    if base and label.endswith("/" + base) and sf.endswith(label):
        return True
    # Entry/module nodes graphify anchors at line 1 (`foo.sh entry`, ...).
    return line_no == 1 and bool(base) and base in label


def _script_info(node: dict, L: list[str], i: int, ext: str, is_file: bool) -> tuple[str, str | None, str]:
    kind = _SCRIPT_KIND.get(ext, "File")
    if is_file:
        return kind, None, _header_comment(L, ("#",))
    sig = _clean(L[i], MAX_SIG) if 0 <= i < len(L) else None
    if kind == "Shell script":
        kind = "Shell function" if sig and re.search(r"\(\)\s*\{?\s*$", sig) else "Shell statement"
    elif kind.endswith("config") or kind == "Config file":
        kind = "Config entry"
    return kind, sig, _comment_above(L, i, ("#",))


def _code_info(node: dict, L: list[str], i: int, ext: str) -> tuple[str, str | None, str]:
    label = str(node.get("label") or "")
    base = os.path.basename(str(node.get("source_file") or ""))
    python = ext in _PYTHON
    if ext in _RUST:
        prefixes: tuple[str, ...] = ("///", "//")
    elif python or ext in _HASH:
        prefixes = ("#",)
    elif ext in _DASH:
        prefixes = ("---", "--")
    else:
        prefixes = ("///", "//")

    if _is_file_node(node, str(node.get("source_file") or ""), _line_number(node.get("source_location"))):
        kind = _FILE_KIND.get(ext, "Source file")
        if python:
            doc = _python_docstring(L, -1) or _header_comment(L, ("#",))
        elif ext in _RUST:
            doc = _header_comment(L, ("//!",)) or _header_comment(L, ("//",))
        else:
            doc = _header_comment(L, prefixes)
        return kind, None, doc

    name = _bare_name(label)
    variant = bool(node.get("_is_variant"))
    i, kw = _find_decl(L, i, name, variant)
    sig = _signature(L, i, python) if 0 <= i < len(L) else None
    is_method = label.startswith(".")

    if kw is None:
        if sig and re.match(r"^(pub(\([^)]*\))?\s+)?(unsafe\s+)?impl\b", sig):
            kind = "impl block"
        elif variant:
            kind = "Enum variant"
        elif sig and "(" in sig and label.endswith("()"):
            kind = "Method" if is_method else "Function"
        else:
            kind = "Code item"
    elif kw == "variant":
        kind = "Enum variant"
    else:
        kind = _DECL_KINDS.get(kw, "Item")
        if kind == "Function" and is_method:
            kind = "Method"
        elif kind in ("Constant", "Variable", "Value") and sig and _CALLABLE_HINT_RE.search(sig):
            kind = "Method" if is_method else "Function"

    doc = ""
    if python and kw in ("def", "async def", "class"):
        doc = _python_docstring(L, i)
    if not doc:
        doc = _comment_above(L, i, prefixes[:1]) or _comment_above(L, i, prefixes)
    if not doc and 0 <= i < len(L) and not python:
        # Trailing `// note` on the declaration line itself.
        m = re.search(r"\s//+\s*(.+)$", L[i])
        if m:
            doc = m.group(1).strip()
    if kind == "impl block" and not doc:
        doc = f"Adds methods to {name} in {base}."
    return kind, sig, doc


def _markdown_info(L: list[str], i: int) -> tuple[str, str | None, str]:
    if not 0 <= i < len(L):
        return "Document", None, ""
    head = L[i].strip()
    is_heading = head.startswith("#")
    kind = "Document section" if is_heading else "Document"
    para: list[str] = []
    j = i + 1 if is_heading else i
    while j < len(L) and not L[j].strip():
        j += 1
    while j < len(L) and L[j].strip() and not L[j].lstrip().startswith("#"):
        t = L[j].strip()
        if t.startswith("```"):
            break
        para.append(t)
        j += 1
    sig = _clean(head.lstrip("#").strip(), MAX_SIG) if is_heading else None
    return kind, sig, " ".join(para)


def _plain_info(node: dict, L: list[str], i: int, ext: str) -> tuple[str, str | None, str]:
    sf = str(node.get("source_file") or "")
    label = str(node.get("label") or "")
    whole_file = node.get("node_kind") == "page" or label in (os.path.basename(sf), sf)
    if ext in _MARKDOWN:
        if whole_file:
            first = next((k for k, t in enumerate(L) if t.strip()), 0)
            _, title, para = _markdown_info(L, first)
            return "Document", title, para
        return _markdown_info(L, i)
    if whole_file:
        return "Text file", None, ""
    sig = _clean(L[i], MAX_SIG) if 0 <= i < len(L) else None
    return "Text section", sig, ""


def _line_number(loc: object) -> int | None:
    m = re.match(r"L?(\d+)", str(loc or ""))
    return int(m.group(1)) if m else None


def build_node_info(G: nx.Graph, root: "str | Path | None") -> dict[str, dict[str, str]]:
    """Return ``{node_id: {k, s?, d?, l?}}`` for every node in *G*."""
    reader = _SourceReader(Path(root) if root else None)
    variants = set()
    for u, v, data in G.edges(data=True):
        if data.get("relation") == "case_of":
            variants.add(data.get("_tgt", v))

    info: dict[str, dict[str, str]] = {}
    for node_id, data in G.nodes(data=True):
        node = dict(data)
        node["_is_variant"] = node_id in variants
        sf = str(node.get("source_file") or "")
        line_no = _line_number(node.get("source_location"))
        ext = os.path.splitext(sf)[1].lower()
        low = os.path.basename(sf).lower()
        if low in ("dockerfile", "containerfile"):
            ext = ".dockerfile"
        elif low in ("makefile", "gnumakefile"):
            ext = ".mk"
        elif low.startswith(".env"):
            ext = ".env"
        kind, sig, doc = None, None, ""
        lines = reader.lines(sf) if sf else None
        if not ext and lines and lines[0].startswith("#!"):
            shebang = lines[0]
            ext = ".py" if "python" in shebang else ".rb" if "ruby" in shebang else ".sh"

        if node.get("external") or node.get("type") == "external":
            kind = "External item (library)"
        elif node.get("type") == "package":
            kind = "Package"
        elif lines is not None and (line_no is not None or os.path.basename(sf) == node.get("label")):
            i = (line_no or 1) - 1
            if ext in _MARKDOWN or ext in _TEXT:
                kind, sig, doc = _plain_info(node, lines, i, ext)
            elif ext in _SCRIPT_KIND:
                kind, sig, doc = _script_info(node, lines, i, ext, _is_file_node(node, sf, line_no))
            else:
                kind, sig, doc = _code_info(node, lines, i, ext)
        else:
            ft = str(node.get("file_type") or "")
            kind = {"concept": "Concept", "rationale": "Design rationale",
                    "document": "Document", "paper": "Paper", "image": "Image",
                    "video": "Video"}.get(ft, "Node")
            if not sf and ft == "code":
                kind = "External item (library)"
            elif node.get("node_kind") == "heading":
                kind = "Document section"

        rationale = node.get("rationale")
        if rationale:
            doc = (str(rationale) + (" " + doc if doc else "")).strip()

        entry: dict[str, str] = {"k": kind or "Node"}
        if sig:
            entry["s"] = sig
        doc = _clean(doc, MAX_DOC) if doc else ""
        if doc:
            entry["d"] = doc
        if sf:
            entry["l"] = _clean(sf, 400) + (f":{line_no}" if line_no is not None else "")
        info[str(node_id)] = entry
    return info
