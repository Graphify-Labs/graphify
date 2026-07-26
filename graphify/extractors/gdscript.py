"""GDScript (Godot Engine) extractor.

Parses ``.gd`` files with a tree-sitter GDScript grammar and emits Graphify's
node/edge dicts. Captures:

* ``class_name X`` / inner ``class X`` -> class node
* ``extends Base`` / ``extends "res://x.gd"`` -> ``extends`` edge
* ``func f(): ...`` -> function node + ``defines`` edge
* generic ``foo()`` / ``obj.method()`` calls inside a body -> ``calls`` edges
* ``Autoload.method()`` -> ``calls`` edge resolved to the function in the
  autoload's script (autoload map read from ``project.godot``)
* ``signal s(args)`` -> signal node + ``declares`` edge
* ``emit_signal("s")`` / ``s.emit()`` -> ``emits`` edge
* ``s.connect(handler)`` -> ``connects`` edge
* ``preload("res://y.gd")`` / ``load("res://y.gd")`` -> ``imports`` edge

Depends on the GDScript grammar from ``tree-sitter-language-pack`` (the Godot
extra, ``graphify[godot]``). If the grammar is not installed the extractor
degrades to a bare file node so the pipeline never crashes.
"""
from __future__ import annotations

import re

from pathlib import Path

from graphify.extractors.base import _file_stem, _make_id

# Cache of resolved [autoload] maps keyed by project root, so project.godot is
# parsed once per worker process rather than per .gd file.
_AUTOLOAD_CACHE: dict[str, dict[str, Path]] = {}
_AUTOLOAD_SECTION_RE = re.compile(r'^\s*\[(?P<name>\w+)\]')


def _load_gdscript_parser():
    """Return a tree-sitter Parser for GDScript, or None if no grammar is available.

    Tries grammar sources in order of preference:
      1. ``tree_sitter_language_pack`` — the Godot extra (``graphify[godot]``)
         installs this; it bundles PrestonKnopp's GDScript grammar and is the
         supported path since the standalone wheel is not on PyPI.
      2. ``tree_sitter_gdscript`` — the standalone grammar package, used
         opportunistically if a user has it installed directly.
    """
    try:
        from tree_sitter import Language, Parser
    except Exception:
        return None
    # 1) language-pack (the Godot extra installs this)
    try:
        from tree_sitter_language_pack import get_parser
        return get_parser("gdscript")
    except Exception:
        pass
    # 2) standalone grammar package (opportunistic fallback)
    try:
        import tree_sitter_gdscript as tsg
        return Parser(Language(tsg.language()))
    except Exception:
        pass
    return None


def _txt(node, source: bytes) -> str:
    return source[node.start_byte:node.end_byte].decode("utf-8", "replace")


def _loc(node) -> str:
    return f"L{node.start_point[0] + 1}"


def _field_ident(node, source: bytes) -> str | None:
    """Return the text of a node's ``name`` field (an identifier)."""
    n = node.child_by_field_name("name")
    if n is not None:
        return _txt(n, source)
    return None


def _first_named(node, types: set[str]):
    for c in node.children:
        if c.is_named and c.type in types:
            return c
    return None


def _strip_quotes(s: str) -> str:
    s = s.strip()
    if len(s) >= 2 and s[0] in "\"'" and s[-1] == s[0]:
        return s[1:-1]
    return s


def _resolve_res(res_path: str, path: Path) -> Path | None:
    """Resolve a ``res://`` path to a real file relative to the project root.

    The project root is the nearest ancestor containing ``project.godot``;
    fall back to the file's own directory when none is found.
    """
    if not res_path.startswith("res://"):
        return None
    rel = res_path[len("res://"):]
    root = path.parent
    for parent in [path.parent, *path.parents]:
        if (parent / "project.godot").exists():
            root = parent
            break
    candidate = (root / rel)
    try:
        return candidate.resolve()
    except Exception:
        return candidate


def _autoload_map(path: Path) -> dict[str, Path]:
    """Return ``{AutoloadName: resolved script Path}`` from the project's
    ``project.godot`` ``[autoload]`` section, so that ``Autoload.method()`` calls
    can resolve to the real function node in the autoload's script.

    Only ``.gd`` autoloads are mapped. Result is cached per project root.
    """
    root = None
    for parent in [path.parent, *path.parents]:
        if (parent / "project.godot").exists():
            root = parent
            break
    if root is None:
        return {}
    key = str(root)
    cached = _AUTOLOAD_CACHE.get(key)
    if cached is not None:
        return cached

    amap: dict[str, Path] = {}
    try:
        text = (root / "project.godot").read_text(encoding="utf-8", errors="replace")
    except OSError:
        _AUTOLOAD_CACHE[key] = amap
        return amap

    section: str | None = None
    for line in text.splitlines():
        m = _AUTOLOAD_SECTION_RE.match(line)
        if m:
            section = m.group("name")
            continue
        if section != "autoload":
            continue
        s = line.strip()
        if not s or "=" not in s:
            continue
        name, _, val = s.partition("=")
        name = name.strip()
        raw = val.strip().strip('"')
        res = raw[1:] if raw.startswith("*") else raw   # '*' = enabled singleton
        resolved = _resolve_res(res, path) if res.endswith(".gd") else None
        if name and resolved is not None:
            amap[name] = resolved
    _AUTOLOAD_CACHE[key] = amap
    return amap


def extract_gdscript(path: Path) -> dict:
    parser = _load_gdscript_parser()
    try:
        raw = path.read_bytes()
    except OSError:
        return {"error": f"cannot read {path}"}

    stem = _file_stem(path)
    file_nid = _make_id(str(path))
    nodes: list[dict] = [{
        "id": file_nid, "label": path.name, "file_type": "code",
        "source_file": str(path), "source_location": None,
    }]
    edges: list[dict] = []
    defined: set[str] = {file_nid}

    def add_node(nid: str, label: str, source_location: str | None = None) -> None:
        if nid not in defined:
            nodes.append({"id": nid, "label": label, "file_type": "code",
                          "source_file": str(path), "source_location": source_location})
            defined.add(nid)

    def add_edge(src: str, tgt: str, relation: str, location: str | None = None,
                 context: str | None = None) -> None:
        edge = {"source": src, "target": tgt, "relation": relation,
                "confidence": "EXTRACTED", "confidence_score": 1.0,
                "source_file": str(path), "source_location": location, "weight": 1.0}
        if context:
            edge["context"] = context
        edges.append(edge)

    if parser is None:
        # grammar unavailable: bare file node keeps the pipeline alive
        return {"nodes": nodes, "edges": edges}

    tree = parser.parse(raw)
    root = tree.root_node
    autoloads = _autoload_map(path)   # AutoloadName -> resolved script Path

    # ---- pre-scan: local function names so calls resolve to real defs -------
    local_funcs: dict[str, str] = {}

    def _prescan(node) -> None:
        for c in node.children:
            if c.type in ("function_definition", "constructor_definition"):
                fname = _field_ident(c, raw) or ("_init" if c.type == "constructor_definition" else None)
                if fname:
                    local_funcs.setdefault(fname, _make_id(stem, fname))
            _prescan(c)

    _prescan(root)

    # ---- top-level class identity -------------------------------------------
    owner_nid = file_nid
    owner_label = path.name
    signals: dict[str, str] = {}   # signal name -> node id (script-level)

    cn = _first_named(root, {"class_name_statement"})
    if cn is not None:
        name = _field_ident(cn, raw)
        if name:
            owner_label = name
            owner_nid = _make_id(stem, name)
            add_node(owner_nid, name, _loc(cn))
            add_edge(file_nid, owner_nid, "defines", _loc(cn))

    # ---- extends -------------------------------------------------------------
    ext = _first_named(root, {"extends_statement"})
    if ext is not None:
        type_node = _first_named(ext, {"type"})
        base_txt = _txt(type_node, raw).strip() if type_node is not None else _txt(ext, raw).replace("extends", "", 1).strip()
        if base_txt:
            res = None
            if base_txt.startswith(("\"", "'")):
                res = _resolve_res(_strip_quotes(base_txt), path)
            if res is not None:
                tgt = _make_id(str(res))
                add_node(tgt, res.name)
            else:
                tgt = _make_id(base_txt)
                add_node(tgt, base_txt)
            add_edge(owner_nid, tgt, "extends", _loc(ext))

    # ---- signals (script level) ---------------------------------------------
    for sig in [c for c in root.children if c.is_named and c.type == "signal_statement"]:
        sname = _field_ident(sig, raw)
        if sname:
            snid = _make_id(stem, "signal:" + sname)
            add_node(snid, sname + " (signal)", _loc(sig))
            add_edge(owner_nid, snid, "declares", _loc(sig))
            signals[sname] = snid

    # ---- functions and their call bodies ------------------------------------
    def handle_call(call_node, func_nid: str) -> None:
        """A bare ``call`` node: callee is the first identifier child."""
        callee = None
        for c in call_node.children:
            if c.type == "identifier":
                callee = _txt(c, raw)
                break
            if c.type in ("attribute",):
                break
        if callee is None:
            return
        args = call_node.child_by_field_name("arguments")
        if callee in ("preload", "load") and args is not None:
            for a in args.children:
                if a.type == "string":
                    res = _resolve_res(_strip_quotes(_txt(a, raw)), path)
                    if res is not None:
                        tgt = _make_id(str(res))
                        add_node(tgt, res.name)
                        add_edge(file_nid, tgt, "imports", _loc(call_node), context="preload")
                    break
            return
        if callee == "emit_signal" and args is not None:
            for a in args.children:
                if a.type == "string":
                    sname = _strip_quotes(_txt(a, raw))
                    snid = signals.get(sname) or _make_id(stem, "signal:" + sname)
                    add_node(snid, sname + " (signal)")
                    add_edge(func_nid, snid, "emits", _loc(call_node))
                    break
            return
        if callee in local_funcs:
            tgt = local_funcs[callee]
        else:
            tgt = _make_id(callee)
            add_node(tgt, callee + "()")
        add_edge(func_nid, tgt, "calls", _loc(call_node))

    def handle_attribute_call(attr_node, func_nid: str) -> None:
        """``receiver.method(args)`` -> attribute( identifier, attribute_call )."""
        recv = None
        acall = None
        for c in attr_node.children:
            if c.type == "identifier" and recv is None:
                recv = _txt(c, raw)
            elif c.type == "attribute_call":
                acall = c
        if acall is None:
            return
        method = None
        for c in acall.children:
            if c.type == "identifier":
                method = _txt(c, raw)
                break
        if method is None:
            return
        if method == "connect" and recv in signals:
            acargs = acall.child_by_field_name("arguments")
            handler = None
            if acargs is not None:
                for a in acargs.children:
                    if a.type == "identifier":
                        handler = _txt(a, raw)
                        break
            if handler:
                if handler in local_funcs:
                    htgt = local_funcs[handler]
                else:
                    htgt = _make_id(handler)
                    add_node(htgt, handler + "()")
                add_edge(signals[recv], htgt, "connects", _loc(attr_node))
            return
        if method == "emit" and recv in signals:
            add_edge(func_nid, signals[recv], "emits", _loc(attr_node))
            return
        # ``Autoload.method()`` -> resolve to the real function node in the
        # autoload's script (its id matches _make_id(_file_stem(script), method)).
        if recv in autoloads:
            tgt = _make_id(_file_stem(autoloads[recv]), method)
            add_edge(func_nid, tgt, "calls", _loc(attr_node), context=recv)
            return
        tgt = _make_id(method)
        add_node(tgt, method + "()")
        add_edge(func_nid, tgt, "calls", _loc(attr_node), context=(recv or ""))

    def walk_body(node, func_nid: str) -> None:
        for c in node.children:
            if c.type == "function_definition":
                continue  # nested funcs handled separately
            if c.type == "call":
                handle_call(c, func_nid)
            elif c.type == "attribute":
                # attribute may itself contain an attribute_call (method call)
                if any(k.type == "attribute_call" for k in c.children):
                    handle_attribute_call(c, func_nid)
            walk_body(c, func_nid)

    def collect_functions(container, owner: str) -> None:
        for c in container.children:
            if c.type in ("function_definition", "constructor_definition"):
                fname = _field_ident(c, raw) or ("_init" if c.type == "constructor_definition" else None)
                if not fname:
                    continue
                fnid = _make_id(stem, fname)
                add_node(fnid, fname + "()", _loc(c))
                add_edge(owner, fnid, "defines", _loc(c))
                body = c.child_by_field_name("body")
                if body is not None:
                    walk_body(body, fnid)
            elif c.type == "class_definition":
                iname = _field_ident(c, raw)
                inid = _make_id(stem, iname) if iname else owner
                if iname:
                    add_node(inid, iname, _loc(c))
                    add_edge(owner, inid, "defines", _loc(c))
                cbody = _first_named(c, {"class_body"})
                if cbody is not None:
                    collect_functions(cbody, inid)

    collect_functions(root, owner_nid)

    return {"nodes": nodes, "edges": edges}
