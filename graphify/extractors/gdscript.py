"""GDScript extractor (tree-sitter-gdscript).

Godot 4 scripts. One file is one class: the node graph is the file node plus its
``func`` / ``signal`` / ``const`` / ``enum`` / inner ``class`` members, and edges
follow how a Godot project is actually wired together:

* ``extends`` -> ``inherits`` to the parent SCRIPT (a ``class_name`` or a
  ``res://`` path). An engine class (``Node``, ``RefCounted``) has no script and
  yields no edge.
* ``preload(...)`` / ``load(...)`` of a ``.gd`` -> ``imports`` to that script's
  file node. This is how a script with no ``class_name`` is reached at all.
* ``sig.connect(cb)`` / ``sig.emit(...)`` / ``emit_signal("sig", ...)`` ->
  ``uses`` from the enclosing function to the signal node; a connect also
  ``references`` its callback when that is a function of this file.
* calls: same-file functions and functions of an ancestor script resolve
  EXTRACTED; ``Autoload.method()`` resolves through the project's
  ``[autoload]`` table to that script's method (the receiver names the script
  in source, so it is exact); ``Alias.method()`` through a ``preload`` const
  alias; ``ClassName.method()`` / ``ClassName.new()`` through the project's
  ``class_name`` index. A bare call resolved by none of those is an engine
  builtin or a dynamic dispatch and is NOT handed to the shared name-matching
  resolver — counted in ``unresolved_calls`` instead.
* ``<page>.md §N.N`` in a comment -> ``references`` from the enclosing function
  (or the file) to a section node of that documentation page. A bare ``§N.N``
  inherits the last page a comment in the same file named (INFERRED).

The project index (autoloads, ``class_name`` -> script, ``uid://`` -> script,
per-script ``func`` names) is built once per ``project.godot`` root and cached
per process; a file outside any Godot project still extracts, with only the
same-file resolutions.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from graphify.extractors.base import _file_stem, _make_id, _read_text

_ENGINE_BUILTIN_RE = re.compile(r"^[A-Z][A-Za-z0-9]*$")
_CITATION_RE = re.compile(r"([A-Za-z0-9_./-]+\.md)`?\s*§\s*(\d+(?:\.\d+)*[a-z]?)")
_BARE_CITATION_RE = re.compile(r"§\s*(\d+(?:\.\d+)*[a-z]?)")
_CLASS_NAME_RE = re.compile(r"^class_name\s+([A-Za-z_][A-Za-z0-9_]*)", re.M)
_EXTENDS_RE = re.compile(r'^extends\s+(?:"([^"]+)"|([A-Za-z_][A-Za-z0-9_]*))', re.M)
_FUNC_RE = re.compile(r"^(?:static\s+)?func\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(", re.M)
_SIGNAL_RE = re.compile(r"^signal\s+([A-Za-z_][A-Za-z0-9_]*)", re.M)
_AUTOLOAD_RE = re.compile(r'^([A-Za-z_][A-Za-z0-9_]*)="\*?((?:res|uid)://[^"]+)"', re.M)
_UID_RE = re.compile(r"^(uid://[a-z0-9]+)\s*$", re.M)

_PROJECT_CACHE: dict[Path, "_GodotProject | None"] = {}
_FILE_INDEX_CACHE: dict[Path, tuple[frozenset[str], frozenset[str], str | None]] = {}


class _GodotProject:
    """What the extractor knows about the Godot project a script belongs to."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.autoloads: dict[str, Path] = {}
        self.class_names: dict[str, Path] = {}
        # always present: a project.godot that cannot be read returns early below,
        # and resolve() must still answer None for a uid:// rather than raise
        self._uids: dict[str, Path] = {}
        uids = self._uids
        try:
            for uid_file in root.rglob("*.gd.uid"):
                if ".godot" in uid_file.parts:
                    continue
                try:
                    m = _UID_RE.search(uid_file.read_text(encoding="utf-8", errors="replace"))
                except OSError:
                    continue
                if m:
                    uids[m.group(1)] = uid_file.with_suffix("")
            for gd in root.rglob("*.gd"):
                if ".godot" in gd.parts:
                    continue
                try:
                    head = gd.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    continue
                m = _CLASS_NAME_RE.search(head)
                if m and m.group(1) not in self.class_names:
                    self.class_names[m.group(1)] = gd
            text = (root / "project.godot").read_text(encoding="utf-8", errors="replace")
        except OSError:
            return
        section = text.split("[autoload]", 1)
        if len(section) == 2:
            body = section[1].split("\n[", 1)[0]
            for m in _AUTOLOAD_RE.finditer(body):
                target = self.resolve(m.group(2), uids)
                if target is not None:
                    self.autoloads[m.group(1)] = target

    def resolve(self, ref: str, uids: dict[str, Path] | None = None) -> Path | None:
        """A ``res://`` or ``uid://`` reference as an absolute path, or None."""
        if ref.startswith("res://"):
            return self.root / ref[len("res://"):]
        if ref.startswith("uid://"):
            return (uids if uids is not None else self._uids).get(ref)
        return None


def _project_for(path: Path) -> _GodotProject | None:
    """The nearest enclosing ``project.godot``, indexed once per process."""
    try:
        start = path.resolve().parent
    except OSError:
        start = path.parent
    for candidate in (start, *start.parents):
        if candidate in _PROJECT_CACHE:
            return _PROJECT_CACHE[candidate]
        if (candidate / "project.godot").is_file():
            project = _GodotProject(candidate)
            _PROJECT_CACHE[candidate] = project
            return project
    _PROJECT_CACHE[start] = None
    return None


def _file_index(script: Path) -> tuple[frozenset[str], frozenset[str], str | None]:
    """(func names, signal names, extends spec) of a script, by regex, cached."""
    key = script.resolve() if script.exists() else script
    hit = _FILE_INDEX_CACHE.get(key)
    if hit is not None:
        return hit
    try:
        text = script.read_text(encoding="utf-8", errors="replace")
    except OSError:
        text = ""
    m = _EXTENDS_RE.search(text)
    ext = (m.group(1) or m.group(2)) if m else None
    result = (frozenset(_FUNC_RE.findall(text)), frozenset(_SIGNAL_RE.findall(text)), ext)
    _FILE_INDEX_CACHE[key] = result
    return result


def _script_of(spec: str, script: Path, project: _GodotProject | None) -> Path | None:
    """The script an ``extends`` / reference spec names, or None (engine class)."""
    if spec.startswith("res://") or spec.startswith("uid://"):
        return project.resolve(spec) if project else None
    if spec.endswith(".gd"):
        return (script.parent / spec).resolve()
    if project and spec in project.class_names:
        return project.class_names[spec]
    return None


def _ancestors(script: Path, project: _GodotProject | None, limit: int = 16) -> list[Path]:
    """Ancestor scripts of ``script``, nearest first, following ``extends``."""
    out: list[Path] = []
    seen = {script}
    current = script
    while len(out) < limit:
        _funcs, _signals, spec = _file_index(current)
        if not spec:
            break
        parent = _script_of(spec, current, project)
        if parent is None or parent in seen:
            break
        seen.add(parent)
        out.append(parent)
        current = parent
    return out


def extract_gdscript(path: Path) -> dict:
    """Extract classes, functions, signals, constants, enums, imports, signal
    wiring, calls and documentation citations from a .gd file."""
    try:
        import tree_sitter_gdscript as tsgd
        from tree_sitter import Language, Parser
    except ImportError:
        return {"nodes": [], "edges": [], "error": "tree_sitter_gdscript not installed"}

    try:
        language = Language(tsgd.language())
        parser = Parser(language)
        source = path.read_bytes()
        tree = parser.parse(source)
        root = tree.root_node
    except Exception as e:
        return {"nodes": [], "edges": [], "error": str(e)}

    project = _project_for(path)
    stem = _file_stem(path)
    str_path = str(path)
    nodes: list[dict] = []
    edges: list[dict] = []
    seen_ids: set[str] = set()
    seen_edges: set[tuple[str, str, str]] = set()
    unresolved_calls: list[dict] = []

    def add_node(nid: str, label: str, line: int, kind: str, **extra: Any) -> None:
        if nid in seen_ids:
            return
        seen_ids.add(nid)
        node = {"id": nid, "label": label, "file_type": "code", "type": kind,
                "source_file": str_path, "source_location": f"L{line}"}
        node.update(extra)
        nodes.append(node)

    def add_edge(src: str, tgt: str, relation: str, line: int,
                 confidence: str = "EXTRACTED", context: str | None = None) -> None:
        key = (src, tgt, relation)
        if key in seen_edges or src == tgt:
            return
        seen_edges.add(key)
        edge = {"source": src, "target": tgt, "relation": relation,
                "confidence": confidence, "source_file": str_path,
                "source_location": f"L{line}", "weight": 1.0}
        if context:
            edge["context"] = context
        edges.append(edge)

    def other_file_nid(script: Path) -> str:
        return _make_id(str(script))

    def other_symbol_nid(script: Path, name: str) -> str:
        return _make_id(_file_stem(script), name)

    def line_of(node) -> int:
        return node.start_point[0] + 1

    def string_value(node) -> str | None:
        if node.type != "string":
            return None
        return _read_text(node, source).strip("\"'")

    file_nid = _make_id(str(path))
    class_label = path.name
    if project is not None:
        # An autoload with no class_name is known to every other script by its
        # autoload name, so that is the label the graph carries for it.
        try:
            resolved = path.resolve()
        except OSError:
            resolved = path
        for auto_name, auto_path in project.autoloads.items():
            if auto_path == resolved or auto_path == path:
                class_label = auto_name
                break
    add_node(file_nid, class_label, 1, "class")

    # --- pass 1: declarations --------------------------------------------------
    func_nids: dict[str, str] = {}          # top-level func name -> nid
    signal_nids: dict[str, str] = {}        # signal name -> nid
    preload_alias: dict[str, Path] = {}     # const NAME := preload("...gd") -> script
    function_bodies: list[tuple[str, Any, Any]] = []   # (nid, body node, def node)
    top_funcs: frozenset[str] = frozenset()

    def declare_member(node, owner_nid: str, owner_stem: str, inner: bool) -> None:
        t = node.type
        if t == "function_definition":
            name_node = node.child_by_field_name("name")
            if not name_node:
                return
            name = _read_text(name_node, source)
            nid = _make_id(owner_stem, name)
            add_node(nid, f".{name}()" if inner else f"{name}()", line_of(node), "function")
            add_edge(owner_nid, nid, "method" if inner else "contains", line_of(node))
            if not inner:
                func_nids[name] = nid
            body = node.child_by_field_name("body")
            if body:
                function_bodies.append((nid, body, node))
            return
        if t == "signal_statement":
            name_node = node.child_by_field_name("name")
            if not name_node:
                return
            name = _read_text(name_node, source)
            nid = _make_id(owner_stem, name)
            add_node(nid, f"signal {name}", line_of(node), "signal")
            add_edge(owner_nid, nid, "contains", line_of(node))
            if not inner:
                signal_nids[name] = nid
            return
        if t == "const_statement":
            name_node = node.child_by_field_name("name")
            if not name_node:
                return
            name = _read_text(name_node, source)
            # kind-qualified: make_id case-folds, so a `const Helper` and a
            # `func helper()` would otherwise claim one id
            nid = _make_id(owner_stem, "const", name)
            add_node(nid, name, line_of(node), "constant")
            add_edge(owner_nid, nid, "contains", line_of(node))
            for child in node.children:
                if child.type == "call":
                    target = _load_target(child)
                    if target is not None:
                        preload_alias[name] = target
            return
        if t == "enum_definition":
            name_node = node.child_by_field_name("name")
            if not name_node:
                return
            name = _read_text(name_node, source)
            nid = _make_id(owner_stem, "enum", name)
            add_node(nid, f"enum {name}", line_of(node), "enum")
            add_edge(owner_nid, nid, "contains", line_of(node))
            return
        if t == "class_definition":
            name_node = node.child_by_field_name("name")
            if not name_node:
                return
            name = _read_text(name_node, source)
            nid = _make_id(owner_stem, name)
            add_node(nid, name, line_of(node), "class")
            add_edge(owner_nid, nid, "contains", line_of(node))
            for child in node.children:
                if child.type == "extends_statement":
                    emit_extends(child, nid)
                elif child.type == "class_body":
                    for member in child.children:
                        declare_member(member, nid, f"{owner_stem}/{name}", True)
            return

    def _load_target(call_node) -> Path | None:
        """The script a ``preload("…")`` / ``load("…")`` call names, or None."""
        fn = None
        args = None
        for c in call_node.children:
            if c.type == "identifier" and fn is None:
                fn = _read_text(c, source)
            elif c.type == "arguments":
                args = c
        if fn not in ("preload", "load") or args is None:
            return None
        for a in args.children:
            value = string_value(a)
            if value is not None:
                return _script_of(value, path, project) if value.endswith(".gd") else None
        return None

    def emit_extends(node, owner_nid: str) -> None:
        spec = None
        for c in node.children:
            if c.type == "type":
                spec = _read_text(c, source)
            elif c.type == "string":
                spec = string_value(c)
        if not spec:
            return
        target = _script_of(spec, path, project)
        if target is not None:
            add_edge(owner_nid, other_file_nid(target), "inherits", line_of(node))

    for child in root.children:
        if child.type == "extends_statement":
            emit_extends(child, file_nid)
        elif child.type == "class_name_statement":
            name_node = child.child_by_field_name("name")
            if name_node:
                class_label = _read_text(name_node, source)
                for n in nodes:
                    if n["id"] == file_nid:
                        n["label"] = class_label
        else:
            declare_member(child, file_nid, stem, False)
    top_funcs = frozenset(func_nids)

    # imports: every preload/load of a .gd anywhere in the file (const aliases,
    # locals, inline arguments) -> the target script's file node.
    def walk_loads(node) -> None:
        if node.type == "call":
            target = _load_target(node)
            if target is not None:
                add_edge(file_nid, other_file_nid(target), "imports", line_of(node))
        for c in node.children:
            walk_loads(c)
    walk_loads(root)

    # --- pass 2: calls and signal wiring inside function bodies -------------------
    ancestors = _ancestors(path, project)

    def resolve_bare(name: str) -> str | None:
        if name in func_nids:
            return func_nids[name]
        for anc in ancestors:
            funcs, _signals, _ext = _file_index(anc)
            if name in funcs:
                return other_symbol_nid(anc, name)
        return None

    def resolve_receiver(receiver: str) -> Path | None:
        if receiver in preload_alias:
            return preload_alias[receiver]
        if project is not None:
            if receiver in project.autoloads:
                return project.autoloads[receiver]
            if receiver in project.class_names:
                return project.class_names[receiver]
        return None

    def signal_nid_for(script: Path | None, name: str) -> str | None:
        if script is None:
            if name in signal_nids:
                return signal_nids[name]
            for anc in ancestors:
                _funcs, signals, _ext = _file_index(anc)
                if name in signals:
                    return other_symbol_nid(anc, name)
            return None
        _funcs, signals, _ext = _file_index(script)
        return other_symbol_nid(script, name) if name in signals else None

    def callback_of(args_node) -> str | None:
        for a in args_node.children:
            if a.type == "identifier":
                return _read_text(a, source)
            if a.type == "attribute":
                parts = [c for c in a.children if c.type == "identifier"]
                if len(parts) == 2 and _read_text(parts[0], source) == "self":
                    return _read_text(parts[1], source)
        return None

    def handle_attribute(node, caller_nid: str) -> None:
        # attribute := <head> ('.' identifier)* '.' attribute_call
        parts = list(node.children)
        call = next((c for c in parts if c.type == "attribute_call"), None)
        if call is None:
            return
        idx = parts.index(call)
        chain = [c for c in parts[:idx] if c.type in ("identifier", "attribute_call", "get_node", "call", "self")]
        method_node = next((c for c in call.children if c.type == "identifier"), None)
        args = next((c for c in call.children if c.type == "arguments"), None)
        if method_node is None:
            return
        method = _read_text(method_node, source)
        line = line_of(node)
        head = _read_text(chain[0], source) if chain and chain[0].type == "identifier" else None
        names = [_read_text(c, source) for c in chain if c.type == "identifier"]

        # signal wiring: <signal>.connect(cb) / <signal>.emit(...)
        if method in ("connect", "emit") and names:
            sig_name = names[-1]
            script = None
            if len(names) >= 2 and names[0] != "self":
                script = resolve_receiver(names[0])
                if script is None:
                    # a signal of some other object (a child node, a local) —
                    # nothing in this project index names it
                    unresolved_calls.append({"caller_nid": caller_nid, "callee": f"{'.'.join(names)}.{method}", "line": line})
                    return
            sig = signal_nid_for(script, sig_name)
            if sig is not None:
                add_edge(caller_nid, sig, "uses", line, context=method)
            if method == "connect" and args is not None:
                cb = callback_of(args)
                cb_nid = resolve_bare(cb) if cb else None
                if cb_nid is not None:
                    add_edge(caller_nid, cb_nid, "references", line, context="connect")
            return

        if head in ("self", "super") and len(names) == 1:
            target = resolve_bare(method)
            if target is not None:
                add_edge(caller_nid, target, "calls", line, context="call")
            else:
                unresolved_calls.append({"caller_nid": caller_nid, "callee": method, "line": line})
            return

        if head is not None and len(names) == 1:
            script = resolve_receiver(head)
            if script is not None:
                if method == "new":
                    add_edge(caller_nid, other_file_nid(script), "references", line, context="instantiates")
                    return
                funcs, _signals, _ext = _file_index(script)
                if method in funcs:
                    add_edge(caller_nid, other_symbol_nid(script, method), "calls", line, context="call")
                    return
                for anc in _ancestors(script, project):
                    afuncs, _s, _e = _file_index(anc)
                    if method in afuncs:
                        add_edge(caller_nid, other_symbol_nid(anc, method), "calls", line, context="call")
                        return
                unresolved_calls.append({"caller_nid": caller_nid, "callee": f"{head}.{method}", "line": line})
                return
        unresolved_calls.append({"caller_nid": caller_nid, "callee": f"{'.'.join(names)}.{method}" if names else method, "line": line})

    def handle_call(node, caller_nid: str) -> None:
        fn = None
        args = None
        for c in node.children:
            if c.type == "identifier" and fn is None:
                fn = _read_text(c, source)
            elif c.type == "arguments":
                args = c
        if fn is None:
            return
        line = line_of(node)
        if fn in ("preload", "load"):
            return
        if fn == "emit_signal" and args is not None:
            for a in args.children:
                name = string_value(a)
                if name is not None:
                    sig = signal_nid_for(None, name)
                    if sig is not None:
                        add_edge(caller_nid, sig, "uses", line, context="emit")
                    return
            return
        if fn in ("connect", "is_connected", "disconnect") and args is not None:
            # Godot 3 style connect("sig", target, "method") is not Godot 4; skip.
            return
        target = resolve_bare(fn)
        if target is not None:
            add_edge(caller_nid, target, "calls", line, context="call")
        elif not _ENGINE_BUILTIN_RE.match(fn):
            unresolved_calls.append({"caller_nid": caller_nid, "callee": fn, "line": line})

    def walk_calls(node, caller_nid: str) -> None:
        t = node.type
        if t == "function_definition":
            return
        if t == "attribute":
            handle_attribute(node, caller_nid)
            for c in node.children:
                if c.type == "attribute_call":
                    for a in c.children:
                        if a.type == "arguments":
                            walk_calls(a, caller_nid)
                elif c.type in ("call", "attribute"):
                    walk_calls(c, caller_nid)
            return
        if t == "call":
            handle_call(node, caller_nid)
            for c in node.children:
                if c.type == "arguments":
                    walk_calls(c, caller_nid)
            return
        for c in node.children:
            walk_calls(c, caller_nid)

    for nid, body, _def in function_bodies:
        walk_calls(body, nid)

    # --- pass 3: documentation citations in comments -----------------------------
    spans = [(d.start_byte, d.end_byte, nid) for nid, _b, d in function_bodies]

    def enclosing(byte: int) -> str:
        for start, end, nid in spans:
            if start <= byte < end:
                return nid
        return file_nid

    def section_node(page: str, section: str, line: int) -> str:
        # The caller hands a basename, but the resolver enforces containment itself:
        # a page is looked up under the project root (or its docs/), and only a real
        # file that RESOLVES inside the root is allowed to rewrite the recorded path.
        page_rel = page.lstrip("./")
        if project is not None and ".." not in Path(page_rel).parts:
            try:
                root = project.root.resolve()
            except OSError:
                root = project.root
            for candidate in (root / page_rel, root / "docs" / page_rel):
                try:
                    resolved = candidate.resolve()
                    if resolved.is_file() and resolved.is_relative_to(root):
                        page_rel = resolved.relative_to(root).as_posix()
                        break
                except OSError:
                    continue
        nid = _make_id("doc", page_rel, "s" + section)
        if nid not in seen_ids:
            seen_ids.add(nid)
            nodes.append({"id": nid, "label": f"{Path(page_rel).name} §{section}",
                          "file_type": "doc", "type": "section",
                          "source_file": page_rel, "source_location": f"§{section}"})
        return nid

    last_page: str | None = None

    def walk_comments(node) -> None:
        nonlocal last_page
        if node.type == "comment":
            text = _read_text(node, source)
            line = line_of(node)
            src = enclosing(node.start_byte)
            explicit = list(_CITATION_RE.finditer(text))
            spans = [(m.start(), m.end()) for m in explicit]
            bare = [m for m in _BARE_CITATION_RE.finditer(text)
                    if not any(a <= m.start() < b for a, b in spans)]
            # walk every citation in the order it appears, so a bare section takes the
            # page named before it — never one named later on the same line
            for m in sorted(explicit + bare, key=lambda m: m.start()):
                if m.re is _CITATION_RE:
                    last_page = m.group(1).split("/")[-1]
                    add_edge(src, section_node(last_page, m.group(2), line), "references", line,
                             context="citation")
                elif last_page is not None:
                    add_edge(src, section_node(last_page, m.group(1), line), "references", line,
                             confidence="INFERRED", context="citation")
            return
        for c in node.children:
            walk_comments(c)
    walk_comments(root)

    return {"nodes": nodes, "edges": edges, "raw_calls": [],
            "unresolved_calls": unresolved_calls}
