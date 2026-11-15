"""GDScript extractor (tree-sitter) for Godot ``.gd`` scripts.

A GDScript file is itself a class. When it declares ``class_name X`` the script
gets a class node labelled ``X`` and its functions hang off it as methods;
without one, the functions are ``contains``-ed by the file node, like module
functions elsewhere. Inner ``class Foo:`` blocks become class nodes of their own.

Calls bind in two places. A bare call or a ``self.m()`` call whose target is in
the same file is bound here. Everything else (inherited methods, ``super``,
``ClassName.m()``, receivers typed by an annotation or a ``Foo.new()`` binding,
``extends``/``preload``/``load`` of ``res://`` paths) is recorded as name-keyed
facts under ``gdscript_facts`` and bound by :func:`resolve_gdscript` once every
file is extracted. The facts carry names and lines, never node ids, so they
survive the id remaps and the cache relativization untouched.

GDScript calls are deliberately kept out of ``raw_calls``: Godot's engine API
(``add_child``, ``queue_free``, ``emit``...) would otherwise bind by bare name
to whatever project method happens to share it.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from graphify.extractors.base import _file_stem, _make_id, _read_source_bytes, _read_text

_SELF_NAMES = ("self",)

# A class scope in the cross-file pass: (script file, inner-class key). Key ""
# is the script itself; "Outer.Inner" names a nested inner class.
Owner = tuple[Path, str]


def _first_child(node, *types: str):
    for c in node.children:
        if c.type in types:
            return c
    return None


def _type_name(type_node, source: bytes) -> str | None:
    """`Foo`, `Foo.Inner`, or the element of `Array[Foo]`; None for `:=`."""
    if type_node is None or type_node.type == "inferred_type":
        return None
    text = _read_text(type_node, source).strip()
    if text.startswith("Array[") and text.endswith("]"):
        text = text[6:-1].strip()
    if not text or not (text[0].isalpha() or text[0] == "_"):
        return None
    return text


def _string_value(node, source: bytes) -> str | None:
    if node is None or node.type != "string":
        return None
    text = _read_text(node, source)
    if len(text) >= 2 and text[0] in "\"'" and text[-1] == text[0]:
        return text[1:-1]
    return None


def _call_name_and_arg(node, source: bytes) -> tuple[str | None, Any]:
    """For a `call` node `name(args)`, the callee name and its first argument."""
    ident = _first_child(node, "identifier")
    args = node.child_by_field_name("arguments")
    first = None
    if args is not None:
        first = next((c for c in args.children if c.is_named), None)
    return (_read_text(ident, source) if ident is not None else None), first


def _new_type(value, source: bytes) -> str | None:
    """`Foo.new(...)` -> "Foo"."""
    if value is None or value.type != "attribute":
        return None
    named = [c for c in value.children if c.is_named]
    if (len(named) == 2 and named[0].type == "identifier"
            and named[1].type == "attribute_call"):
        meth = _first_child(named[1], "identifier")
        if meth is not None and _read_text(meth, source) == "new":
            name = _read_text(named[0], source)
            if name[:1].isupper():
                return name
    return None


def extract_gdscript(path: Path) -> dict:
    """Extract classes, inner classes, functions, signals, enums and calls."""
    try:
        import tree_sitter_gdscript as tsgd
        from tree_sitter import Language, Parser
    except ImportError:
        return {"nodes": [], "edges": [], "error": "tree_sitter_gdscript not installed"}

    try:
        parser = Parser(Language(tsgd.language()))
        source = _read_source_bytes(path)
        root = parser.parse(source).root_node
    except Exception as e:
        return {"nodes": [], "edges": [], "error": str(e)}

    stem = _file_stem(path)
    str_path = str(path)
    nodes: list[dict] = []
    edges: list[dict] = []
    seen_ids: set[str] = set()

    def add_node(nid: str, label: str, line: int) -> None:
        if nid not in seen_ids:
            seen_ids.add(nid)
            nodes.append({"id": nid, "label": label, "file_type": "code",
                          "source_file": str_path, "source_location": f"L{line}"})

    def add_edge(src: str, tgt: str, relation: str, line: int,
                 confidence: str = "EXTRACTED", context: str | None = None) -> None:
        edge = {"source": src, "target": tgt, "relation": relation,
                "confidence": confidence, "source_file": str_path,
                "source_location": f"L{line}", "weight": 1.0}
        if context:
            edge["context"] = context
        edges.append(edge)

    file_nid = _make_id(str(path))
    add_node(file_nid, path.name, 1)

    facts: dict[str, Any] = {
        "class_name": None,
        # owner key ("" = the script itself, else the inner class name) ->
        # {"extends": {...} | None, "line", "methods": {name: line}, "signals": {name: line},
        #  "member_types": {var: type}}
        "owners": {},
        "loads": [],         # {"path", "line", "kind", "const"}
        "type_refs": [],     # {"owner", "type", "line"}
        "calls": [],         # {"owner", "caller", "caller_line", "callee", "receiver",
                             #  "receiver_type", "line"}
        "connects": [],      # {"owner", "signal", "receiver", "receiver_type", "handler",
                             #  "handler_owner", "line"}
        "emits": [],         # {"owner", "caller", "caller_line", "signal", "line"}
    }

    def new_owner(key: str, line: int) -> dict:
        o = {"extends": None, "line": line, "methods": {}, "signals": {},
             "member_types": {}, "label": None}
        facts["owners"][key] = o
        return o

    script = new_owner("", 1)

    def parse_extends(ext_node) -> dict | None:
        if ext_node is None:
            return None
        s = _string_value(_first_child(ext_node, "string"), source)
        if s is not None:
            return {"path": s, "line": ext_node.start_point[0] + 1}
        t = _type_name(_first_child(ext_node, "type"), source)
        if t:
            return {"class": t, "line": ext_node.start_point[0] + 1}
        return None

    # ── pass 1: the script's own header and its members ─────────────────────
    script_owner_nid = file_nid
    for child in root.children:
        if child.type == "class_name_statement":
            name_node = child.child_by_field_name("name")
            if name_node is not None:
                facts["class_name"] = _read_text(name_node, source)
            nested = child.child_by_field_name("extends") or _first_child(child, "extends_statement")
            if nested is not None:
                script["extends"] = parse_extends(nested)
        elif child.type == "extends_statement":
            script["extends"] = parse_extends(child)

    if facts["class_name"]:
        line = 1
        for child in root.children:
            if child.type == "class_name_statement":
                line = child.start_point[0] + 1
        script_owner_nid = _make_id(stem, facts["class_name"])
        add_node(script_owner_nid, facts["class_name"], line)
        add_edge(file_nid, script_owner_nid, "contains", line)
        script["label"] = facts["class_name"]

    owner_nids: dict[str, str] = {"": script_owner_nid}
    function_bodies: list[tuple[str, str, str, int, Any, dict[str, str]]] = []

    def param_types(params) -> dict[str, str]:
        out: dict[str, str] = {}
        if params is None:
            return out
        for p in params.children:
            if p.type in ("typed_parameter", "typed_default_parameter"):
                ident = _first_child(p, "identifier")
                t = _type_name(p.child_by_field_name("type") or _first_child(p, "type"), source)
                if ident is not None and t:
                    out[_read_text(ident, source)] = t
        return out

    def note_type_ref(owner_key: str, t: str | None, line: int) -> None:
        if t and t[:1].isupper():
            facts["type_refs"].append({"owner": owner_key, "type": t.split(".")[0], "line": line})

    def note_load(value, line: int, const_name: str | None) -> None:
        if value is None or value.type != "call":
            return
        name, first = _call_name_and_arg(value, source)
        if name in ("preload", "load"):
            p = _string_value(first, source)
            if p:
                facts["loads"].append({"path": p, "line": line, "kind": name, "const": const_name})

    def add_function(child, owner_key: str, line: int) -> None:
        owner = facts["owners"][owner_key]
        owner_nid = owner_nids[owner_key]
        is_method_owner = owner_nid != file_nid
        name_node = child.child_by_field_name("name")
        if name_node is None:
            return
        fname = _read_text(name_node, source)
        label = f".{fname}()" if is_method_owner else f"{fname}()"
        fnid = _make_id(owner_nid if is_method_owner else stem, fname)
        add_node(fnid, label, line)
        add_edge(owner_nid, fnid, "method" if is_method_owner else "contains", line)
        owner["methods"][fname] = line
        ptypes = param_types(child.child_by_field_name("parameters"))
        for pt in ptypes.values():
            note_type_ref(owner_key, pt, line)
        note_type_ref(owner_key, _type_name(child.child_by_field_name("return_type"), source), line)
        body = child.child_by_field_name("body")
        if body is not None:
            function_bodies.append((owner_key, fnid, label, line, body, ptypes))

    def walk_members(container, owner_key: str) -> None:
        owner = facts["owners"][owner_key]
        owner_nid = owner_nids[owner_key]
        for child in container.children:
            t = child.type
            line = child.start_point[0] + 1
            if t == "extends_statement" and owner_key:
                owner["extends"] = parse_extends(child)
            elif t == "function_definition":
                add_function(child, owner_key, line)
            elif t == "signal_statement":
                name_node = child.child_by_field_name("name")
                if name_node is None:
                    continue
                sname = _read_text(name_node, source)
                snid = _make_id(owner_nid, "signal", sname)
                add_node(snid, sname, line)
                add_edge(owner_nid, snid, "contains", line, context="signal")
                owner["signals"][sname] = line
            elif t == "enum_definition":
                name_node = child.child_by_field_name("name")
                if name_node is None:
                    continue
                ename = _read_text(name_node, source)
                enid = _make_id(owner_nid, ename)
                add_node(enid, ename, line)
                add_edge(owner_nid, enid, "contains", line, context="enum")
            elif t in ("variable_statement", "const_statement"):
                name_node = child.child_by_field_name("name")
                value = child.child_by_field_name("value")
                vname = _read_text(name_node, source) if name_node is not None else None
                vtype = _type_name(child.child_by_field_name("type"), source) or _new_type(value, source)
                if vname and vtype:
                    owner["member_types"][vname] = vtype
                note_type_ref(owner_key, vtype, line)
                note_load(value, line, vname if t == "const_statement" else None)
                setget = child.child_by_field_name("setget")
                if setget is not None:
                    # Property accessors run as the owner's code; attribute their
                    # calls to the owner itself rather than inventing nodes.
                    for acc in setget.children:
                        body = acc.child_by_field_name("body")
                        if body is not None:
                            function_bodies.append((owner_key, owner_nid, owner.get("label") or path.name, line, body, {}))
            elif t == "class_definition":
                name_node = child.child_by_field_name("name")
                if name_node is None:
                    continue
                cname = _read_text(name_node, source)
                key = cname if not owner_key else f"{owner_key}.{cname}"
                cnid = _make_id(owner_nid, cname)
                add_node(cnid, cname, line)
                add_edge(owner_nid, cnid, "contains", line)
                owner_nids[key] = cnid
                inner = new_owner(key, line)
                inner["label"] = cname
                body = child.child_by_field_name("body")
                ext = child.child_by_field_name("extends")
                if ext is not None:
                    inner["extends"] = parse_extends(ext)
                if body is not None:
                    walk_members(body, key)

    walk_members(root, "")

    # ── pass 2: calls inside every function body ────────────────────────────
    seen_pairs: set[tuple[str, str]] = set()

    def resolve_local_type(name: str, owner_key: str, locals_: dict[str, str]) -> str | None:
        if name in locals_:
            return locals_[name]
        key = owner_key
        while True:
            mt = facts["owners"].get(key, {}).get("member_types", {})
            if name in mt:
                return mt[name]
            if not key:
                return None
            key = key.rpartition(".")[0]

    def same_file_method(owner_key: str, name: str) -> str | None:
        owner = facts["owners"].get(owner_key)
        if owner and name in owner["methods"]:
            onid = owner_nids[owner_key]
            return _make_id(onid if onid != file_nid else stem, name)
        return None

    def emit_local(caller_nid: str, tgt: str, line: int) -> None:
        if tgt == caller_nid or (caller_nid, tgt) in seen_pairs:
            return
        seen_pairs.add((caller_nid, tgt))
        add_edge(caller_nid, tgt, "calls", line)

    def walk_attribute(node, owner_key: str, caller_nid: str, caller_label: str,
                       caller_line: int, locals_: dict[str, str], line: int) -> None:
        """`recv.m()`, `self.m()`, `super.m()`, `sig.emit()`, `obj.sig.connect(h)`."""
        parts = [c for c in node.children if c.is_named]
        # Only `recv.m(...)` and `recv.signal.connect/emit(...)` carry a
        # receiver we can type; longer chains are left alone.
        if len(parts) >= 2 and parts[1].type == "attribute_call":
            recv_node, call = parts[0], parts[1]
            meth_node = _first_child(call, "identifier")
            meth = _read_text(meth_node, source) if meth_node is not None else None
            recv = _read_text(recv_node, source) if recv_node.type == "identifier" else None
            if meth and recv is not None:
                owner_signals = facts["owners"][owner_key]["signals"]
                if meth in ("emit", "connect") and recv in owner_signals or (
                        meth in ("emit", "connect") and recv not in locals_
                        and resolve_local_type(recv, owner_key, locals_) is None
                        and not recv[:1].isupper() and recv not in _SELF_NAMES
                        and recv != "super"):
                    # `sig.emit()` / `sig.connect(h)` on a signal of this
                    # script or of a base class (bound in the cross-file pass).
                    if meth == "emit":
                        facts["emits"].append({"owner": owner_key, "caller": caller_label,
                                               "caller_line": caller_line, "signal": recv,
                                               "line": line})
                    else:
                        record_connect(call, owner_key, recv, None, None, line)
                elif recv in _SELF_NAMES:
                    tgt = same_file_method(owner_key, meth)
                    if tgt:
                        emit_local(caller_nid, tgt, line)
                    else:
                        facts["calls"].append({"owner": owner_key, "caller": caller_label,
                                               "caller_line": caller_line, "callee": meth,
                                               "receiver": "self", "receiver_type": None,
                                               "line": line})
                elif recv == "super":
                    facts["calls"].append({"owner": owner_key, "caller": caller_label,
                                           "caller_line": caller_line, "callee": meth,
                                           "receiver": "super", "receiver_type": None,
                                           "line": line})
                elif meth != "new":
                    rtype = resolve_local_type(recv, owner_key, locals_)
                    if rtype is None and recv[:1].isupper():
                        rtype = recv  # ClassName.static_m() / Const.m()
                    if rtype:
                        facts["calls"].append({"owner": owner_key, "caller": caller_label,
                                               "caller_line": caller_line, "callee": meth,
                                               "receiver": recv, "receiver_type": rtype,
                                               "line": line})
        elif (len(parts) >= 3 and parts[0].type == "identifier"
              and parts[1].type == "identifier" and parts[2].type == "attribute_call"):
            # `obj.sig.connect(h)` / `obj.sig.emit()` with `obj` typed.
            call = parts[2]
            meth_node = _first_child(call, "identifier")
            meth = _read_text(meth_node, source) if meth_node is not None else None
            recv = _read_text(parts[0], source)
            sig = _read_text(parts[1], source)
            rtype = resolve_local_type(recv, owner_key, locals_)
            if rtype is None and recv[:1].isupper():
                rtype = recv
            if meth == "connect" and rtype:
                record_connect(call, owner_key, sig, recv, rtype, line)
            elif meth == "emit" and rtype:
                facts["emits"].append({"owner": owner_key, "caller": caller_label,
                                       "caller_line": caller_line, "signal": sig,
                                       "receiver": recv, "receiver_type": rtype,
                                       "line": line})

    def walk_calls(node, owner_key: str, caller_nid: str, caller_label: str,
                   caller_line: int, locals_: dict[str, str]) -> None:
        t = node.type
        if t in ("function_definition", "class_definition"):
            return
        line = node.start_point[0] + 1
        if t == "for_statement":
            var = node.child_by_field_name("left")
            vt = _type_name(node.child_by_field_name("type"), source)
            if var is not None and vt:
                locals_[_read_text(var, source)] = vt
        elif t == "variable_statement":
            name_node = node.child_by_field_name("name")
            value = node.child_by_field_name("value")
            vt = _type_name(node.child_by_field_name("type"), source) or _new_type(value, source)
            if name_node is not None and vt:
                locals_[_read_text(name_node, source)] = vt
            note_load(value, line, None)
        elif t == "call":
            name, first = _call_name_and_arg(node, source)
            if name in ("preload", "load"):
                note_load(node, line, None)
            elif name == "emit_signal":
                sig = _string_value(first, source)
                if sig:
                    facts["emits"].append({"owner": owner_key, "caller": caller_label,
                                           "caller_line": caller_line, "signal": sig, "line": line})
            elif name == "super":
                cur = caller_label.strip(".()")
                facts["calls"].append({"owner": owner_key, "caller": caller_label,
                                       "caller_line": caller_line, "callee": cur,
                                       "receiver": "super", "receiver_type": None, "line": line})
            elif name:
                tgt = same_file_method(owner_key, name)
                if tgt:
                    emit_local(caller_nid, tgt, line)
                else:
                    facts["calls"].append({"owner": owner_key, "caller": caller_label,
                                           "caller_line": caller_line, "callee": name,
                                           "receiver": None, "receiver_type": None, "line": line})
        elif t == "attribute":
            walk_attribute(node, owner_key, caller_nid, caller_label, caller_line,
                           locals_, line)
        for c in node.children:
            walk_calls(c, owner_key, caller_nid, caller_label, caller_line, locals_)

    def record_connect(call, owner_key: str, sig: str, recv: str | None,
                       rtype: str | None, line: int) -> None:
        args = call.child_by_field_name("arguments")
        first = next((c for c in args.children if c.is_named), None) if args is not None else None
        handler = None
        if first is not None and first.type == "identifier":
            handler = _read_text(first, source)
        elif first is not None and first.type == "attribute":
            # `self._on_x` / `obj._on_x` -> the trailing name, same owner only for self
            named = [c for c in first.children if c.is_named]
            if len(named) == 2 and named[0].type == "identifier" and named[1].type == "identifier" \
                    and _read_text(named[0], source) in _SELF_NAMES:
                handler = _read_text(named[1], source)
        if handler:
            facts["connects"].append({"owner": owner_key, "signal": sig, "receiver": recv,
                                      "receiver_type": rtype, "handler": handler, "line": line})

    for owner_key, fnid, label, line, body, ptypes in function_bodies:
        walk_calls(body, owner_key, fnid, label, line, dict(ptypes))

    clean_edges = [e for e in edges if e["source"] in seen_ids and e["target"] in seen_ids]
    return {"nodes": nodes, "edges": clean_edges, "gdscript_facts": facts}


# ── cross-file pass ──────────────────────────────────────────────────────────

def _project_root(p: Path, cache: dict[Path, Path | None]) -> Path | None:
    """Nearest ancestor holding project.godot: the directory `res://` names."""
    d = p.parent
    chain: list[Path] = []
    found: Path | None = None
    while True:
        if d in cache:
            found = cache[d]
            break
        chain.append(d)
        if (d / "project.godot").is_file():
            found = d
            break
        if d.parent == d:
            break
        d = d.parent
    for c in chain:
        cache[c] = found
    return found


def _autoloads(proj: Path, cache: dict[Path, dict[str, str]]) -> dict[str, str]:
    """`[autoload]` of project.godot: singleton name -> `res://` script path."""
    if proj in cache:
        return cache[proj]
    out: dict[str, str] = {}
    try:
        text = (proj / "project.godot").read_text(encoding="utf-8", errors="replace")
    except OSError:
        text = ""
    in_section = False
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("["):
            in_section = line == "[autoload]"
            continue
        if not in_section or "=" not in line or line.startswith(";"):
            continue
        name, _, value = line.partition("=")
        value = value.strip().strip('"').lstrip("*")
        if value.endswith(".gd"):
            out[name.strip()] = value
    cache[proj] = out
    return out


def resolve_gdscript(per_file: list, paths: list, all_nodes: list, all_edges: list,
                     root: Path) -> int:
    """Bind GDScript facts across files. Returns the number of edges added."""
    sel = [(r, Path(p)) for r, p in zip(per_file, paths)
           if isinstance(r, dict) and r.get("gdscript_facts") is not None]
    if not sel:
        return 0

    root = Path(root)

    def norm(sf: object) -> Path | None:
        if not sf:
            return None
        p = Path(str(sf))
        if not p.is_absolute():
            p = root / p
        try:
            return p.resolve()
        except OSError:
            return p.absolute()

    # (file, "L<line>", label) -> node id, for every node of a .gd file.
    gd_files = {norm(p) for _, p in sel}
    by_loc: dict[tuple[Path, str, str], str] = {}
    file_nid: dict[Path, str] = {}
    class_nid: dict[tuple[Path, str], str] = {}   # (file, label) -> first node so labelled
    str_of: dict[Path, str] = {}                   # the source_file string the graph uses
    for n in all_nodes:
        nfp = norm(n.get("source_file"))
        if nfp is None or nfp not in gd_files:
            continue
        label = n.get("label") or ""
        by_loc[(nfp, n.get("source_location") or "", label)] = n["id"]
        class_nid.setdefault((nfp, label), n["id"])
        str_of.setdefault(nfp, n.get("source_file"))
        if label == nfp.name and nfp not in file_nid:
            file_nid[nfp] = n["id"]

    proj_cache: dict[Path, Path | None] = {}
    autoload_cache: dict[Path, dict[str, str]] = {}
    facts_of: dict[Path, dict] = {}
    class_file: dict[str, list[Path]] = {}
    for r, p in sel:
        sfp = norm(p)
        if sfp is None:
            continue
        facts_of[sfp] = r["gdscript_facts"]
        cn = r["gdscript_facts"].get("class_name")
        if cn:
            class_file.setdefault(cn, []).append(sfp)

    def res_to_file(res: str, from_file: Path) -> Path | None:
        if res.startswith("res://"):
            proj = _project_root(from_file, proj_cache)
            if proj is None:
                return None
            target = proj / res[len("res://"):]
        elif res.startswith(("/", "user://", "uid://")):
            return None
        else:
            target = from_file.parent / res
        try:
            return target.resolve()
        except OSError:
            return target

    def owner_nid(o: Owner) -> str | None:
        fp, key = o
        facts = facts_of.get(fp)
        if facts is None:
            return None
        if key == "":
            cn = facts.get("class_name")
            return (class_nid.get((fp, cn)) if cn else None) or file_nid.get(fp)
        info = facts["owners"].get(key)
        if info is None:
            return None
        return by_loc.get((fp, f"L{info['line']}", key.rpartition(".")[2]))

    def method_nid(o: Owner, name: str) -> str | None:
        fp, key = o
        info = facts_of[fp]["owners"].get(key)
        if info is None or name not in info["methods"]:
            return None
        line = info["methods"][name]
        is_method = owner_nid(o) != file_nid.get(fp)
        label = f".{name}()" if is_method else f"{name}()"
        return by_loc.get((fp, f"L{line}", label))

    def signal_nid(o: Owner, name: str) -> str | None:
        fp, key = o
        info = facts_of[fp]["owners"].get(key)
        if info is None or name not in info["signals"]:
            return None
        return by_loc.get((fp, f"L{info['signals'][name]}", name))

    def resolve_type(name: str, from_owner: Owner) -> Owner | None:
        """A type name as seen from `from_owner`: inner class, const alias, class_name."""
        fp, key = from_owner
        facts = facts_of[fp]
        head, _, rest = name.partition(".")
        # inner classes visible from here (own nesting chain, innermost first)
        k = key
        base: Owner | None = None
        while True:
            cand = f"{k}.{head}" if k else head
            if cand in facts["owners"] and cand != "":
                base = (fp, cand)
                break
            if not k:
                break
            k = k.rpartition(".")[0]
        if base is None:
            # const Foo = preload("res://foo.gd")
            for ld in facts["loads"]:
                if ld.get("const") == head and ld["path"].endswith(".gd"):
                    tf = res_to_file(ld["path"], fp)
                    if tf in facts_of:
                        base = (tf, "")
                        break
        if base is None:
            files = class_file.get(head, [])
            if len(files) == 1:
                base = (files[0], "")
        if base is None:
            # An autoload singleton: `RunState.m()` names the script registered
            # under [autoload] in project.godot.
            proj = _project_root(fp, proj_cache)
            res = _autoloads(proj, autoload_cache).get(head) if proj else None
            tf = res_to_file(res, fp) if res else None
            if tf in facts_of:
                base = (tf, "")
        if base is None:
            return None
        if rest:
            bfp, bkey = base
            cand = f"{bkey}.{rest}" if bkey else rest
            return (bfp, cand) if cand in facts_of[bfp]["owners"] else None
        return base

    def base_of(o: Owner) -> Owner | None:
        fp, key = o
        info = facts_of[fp]["owners"].get(key)
        ext = info.get("extends") if info else None
        if not ext:
            return None
        if "path" in ext:
            tf = res_to_file(ext["path"], fp)
            return (tf, "") if tf in facts_of else None
        return resolve_type(ext["class"], o)

    def find_method(o: Owner | None, name: str) -> str | None:
        seen: set = set()
        while o is not None and o not in seen:
            seen.add(o)
            hit = method_nid(o, name)
            if hit:
                return hit
            o = base_of(o)
        return None

    def find_signal(o: Owner | None, name: str) -> str | None:
        seen: set = set()
        while o is not None and o not in seen:
            seen.add(o)
            hit = signal_nid(o, name)
            if hit:
                return hit
            o = base_of(o)
        return None

    existing = {(e.get("source"), e.get("target"), e.get("relation")) for e in all_edges}
    added = 0

    def emit(src: str | None, tgt: str | None, rel: str, fp: Path, line: int,
             confidence: str = "EXTRACTED", context: str | None = None) -> None:
        nonlocal added
        if not src or not tgt or src == tgt or (src, tgt, rel) in existing:
            return
        existing.add((src, tgt, rel))
        e = {"source": src, "target": tgt, "relation": rel, "confidence": confidence,
             "source_file": str_of.get(fp) or str(fp),
             "source_location": f"L{line}", "weight": 1.0}
        if context:
            e["context"] = context
        all_edges.append(e)
        added += 1

    def bind_links(fp: Path, facts: dict) -> None:
        """extends -> inherits, preload/load -> imports_from, types -> references."""
        fnid = file_nid.get(fp)

        # extends -> inherits
        for key, info in facts["owners"].items():
            ext = info.get("extends")
            if not ext:
                continue
            base = base_of((fp, key))
            if base is not None:
                emit(owner_nid((fp, key)), owner_nid(base), "inherits", fp, ext["line"])
                if base[0] != fp:
                    emit(fnid, file_nid.get(base[0]), "imports_from", fp, ext["line"],
                         context="extends")

        # preload/load of another script -> imports_from
        for ld in facts["loads"]:
            if not ld["path"].endswith(".gd"):
                continue
            tf = res_to_file(ld["path"], fp)
            if tf in facts_of and tf != fp:
                emit(fnid, file_nid.get(tf), "imports_from", fp, ld["line"], context=ld["kind"])

        # class_name used as a type -> references (owner -> class)
        for ref in facts["type_refs"]:
            src_owner = (fp, ref["owner"])
            tgt = resolve_type(ref["type"], src_owner)
            if tgt is not None and tgt != src_owner and tgt[0] != fp:
                emit(owner_nid(src_owner), owner_nid(tgt), "references", fp, ref["line"])

    def bind_calls(fp: Path, facts: dict) -> None:
        def caller_of(c: dict) -> str | None:
            return by_loc.get((fp, f"L{c['caller_line']}", c["caller"]))

        for c in facts["calls"]:
            own: Owner = (fp, c["owner"])
            recv = c["receiver"]
            if recv in (None, "self"):
                tgt, conf = find_method(own, c["callee"]), "EXTRACTED"
            elif recv == "super":
                tgt, conf = find_method(base_of(own), c["callee"]), "EXTRACTED"
            else:
                # A receiver with no inferred type (a stale cache entry, or a
                # fact from a hand-built result) cannot be bound: skip it
                # rather than abort the whole pass.
                rtype = c.get("receiver_type")
                t_owner = resolve_type(rtype, own) if rtype else None
                tgt = find_method(t_owner, c["callee"]) if t_owner else None
                # A static ClassName.m() names its class outright; a typed
                # variable only says what the annotation claims.
                conf = "EXTRACTED" if recv == rtype else "INFERRED"
            if tgt:
                emit(caller_of(c), tgt, "calls", fp, c["line"], confidence=conf)

    def bind_signals(fp: Path, facts: dict) -> None:
        """`sig.emit()` -> emits, `sig.connect(h)` -> listened_by."""
        for em in facts["emits"]:
            own = (fp, em["owner"])
            rtype = em.get("receiver_type")
            target_owner = resolve_type(rtype, own) if rtype else own
            sig = find_signal(target_owner, em["signal"]) if target_owner else None
            if sig:
                emit(by_loc.get((fp, f"L{em['caller_line']}", em["caller"])), sig,
                     "emits", fp, em["line"],
                     confidence="EXTRACTED" if not rtype or em.get("receiver") == rtype else "INFERRED")

        for cn in facts["connects"]:
            own = (fp, cn["owner"])
            rtype = cn.get("receiver_type")
            if rtype:
                t_owner = resolve_type(rtype, own)
                sig = find_signal(t_owner, cn["signal"]) if t_owner else None
            else:
                sig = find_signal(own, cn["signal"])
            handler = find_method(own, cn["handler"])
            if sig and handler:
                static = not rtype or cn.get("receiver") == rtype
                emit(sig, handler, "listened_by", fp, cn["line"],
                     confidence="EXTRACTED" if static else "INFERRED")

    for fp, facts in facts_of.items():
        bind_links(fp, facts)
        bind_calls(fp, facts)
        bind_signals(fp, facts)

    return added
