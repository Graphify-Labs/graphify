"""Monkey C (Garmin Connect IQ) extractor.

Monkey C has no tree-sitter grammar, so this is a scanner/regex extractor in
the spirit of the Pascal regex fallback (``_extract_pascal_regex``): comments,
string and char literals are blanked out with offsets preserved (so every line
number stays exact), then one token pass tracks brace depth to attribute every
``module`` / ``class`` / ``function`` to its enclosing scope and every call
inside a function body to that function.

Emitted per file:

- the file node; ``module`` and ``class`` nodes (``contains`` from their
  owner); functions — a ``method`` edge from a class (label ``.name()``),
  ``contains`` from a module or the file (label ``name()``);
- ``inherits`` for ``class X extends Y``: a same-file base resolves directly;
  any other base gets a SOURCELESS stub node whose label is the alias-expanded
  name (``extends Ui.View`` under ``using Toybox.WatchUi as Ui`` becomes
  ``Toybox.WatchUi.View``), so the corpus-level unique-stub rewire in
  ``extract()`` collapses it onto the real class when the base lives in
  another file, and an SDK base stays as one shared external node;
- ``imports_from`` for ``using`` / ``import`` (context ``import``). A bare
  import (``import Utils;`` — a module of the same app) also gets a sourceless
  stub for the same rewire; a dotted ``Toybox.*`` import stays dangling and is
  dropped at build time, like a Python stdlib import;
- ``calls`` for targets resolvable inside the file (own class, enclosing
  module, file scope; ``me.`` / ``self.`` stripped), ``indirect_call`` for
  ``method(:name)`` / ``new Lang.Method(self, :name)`` callbacks;
- everything else goes to ``raw_calls``: bare calls for the shared cross-file
  pass, member calls tagged ``lang="monkeyc"`` with a ``receiver_type`` — an
  explicit ``Type.fn()`` qualifier (``receiver_kind="static"``) or a receiver
  typed via ``var x as T`` / a parameter type / ``x = new T()``
  (``receiver_kind="typed"``) — for :func:`resolve_monkeyc_member_calls`.
"""
from __future__ import annotations

import bisect
import re
from pathlib import Path

from graphify.extractors.base import _LANGUAGE_BUILTIN_GLOBALS, _file_stem, _make_id

# Comments and literals, blanked before scanning. Strings never span lines in
# Monkey C; the char-literal branch keeps `'{'` from unbalancing the brace scan.
_MC_BLANK_RE = re.compile(
    r"//[^\n]*"
    r"|/\*.*?\*/"
    r"|\"(?:\\.|[^\"\\\n])*\""
    r"|'(?:\\.|[^'\\\n])'",
    re.DOTALL,
)

# One pass, left to right. Declarations consume their opening brace so the
# scope they open is pushed with the right owner; every other brace is an
# anonymous block (function body statements, dictionary literals, `enum { }`,
# `switch { }`, ...) that only has to stay balanced.
_MC_TOKEN_RE = re.compile(
    r"""
    (?P<import>\b(?:using|import)\s+(?P<import_name>[A-Za-z_][\w.]*)
        (?:\s+as\s+(?P<import_alias>[A-Za-z_]\w*))?\s*;)
  | (?P<klass>\bclass\s+(?P<class_name>[A-Za-z_]\w*)
        (?:\s+extends\s+(?P<class_base>[A-Za-z_][\w.]*))?\s*\{)
  | (?P<module>\bmodule\s+(?P<module_name>[A-Za-z_]\w*)\s*\{)
  | (?P<func>\bfunction\s+(?P<func_name>[A-Za-z_]\w*)\s*
        \((?P<func_params>(?:[^()]|\((?:[^()]|\([^()]*\))*\))*)\)\s*(?:as\b[^{;]*)?\{)
  | (?P<open>\{)
  | (?P<close>\})
    """,
    re.VERBOSE,
)

# Inside a function body: `new T(`, `method(:sym)`, and `recv.callee(` /
# `callee(`. `new` is listed first so `new Foo(` is never read as a call to
# `Foo`; the negative lookbehind keeps `a.b().c(` from yielding a spurious
# receiver-less `c(` and skips symbols such as `:name(`; `$.` (the global
# scope qualifier) is accepted and dropped.
_MC_CALL_RE = re.compile(
    r"""
    (?P<new>\bnew\s+(?P<new_type>[A-Za-z_][\w.]*)\s*\()
  | (?P<mref>\bmethod\s*\(\s*:(?P<mref_name>[A-Za-z_]\w*)\s*\))
  | (?P<call>(?<![\w.:$])(?:\$\.)?
        (?:(?P<recv>[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*)\.)?
        (?P<callee>[A-Za-z_]\w*)\s*\()
    """,
    re.VERBOSE,
)

# `new Lang.Method(self, :onTick)` / `new Method(me, :onTick)` — the callback
# form that predates the `method(:sym)` shorthand.
_MC_METHOD_OBJ_RE = re.compile(r"\s*(?P<obj>[A-Za-z_]\w*)\s*,\s*:(?P<sym>[A-Za-z_]\w*)")
# `me.method(:sym)` / `obj.method(:sym)`: the receiver form of the callback
# shorthand, reached through the `call` branch (callee `method`).
_MC_METHOD_SYM_RE = re.compile(r"\s*:(?P<sym>[A-Za-z_]\w*)\s*\)")

# Type table sources: `var x as T`, `x = new T(`, and `name as T` parameters.
_MC_VAR_TYPED_RE = re.compile(r"\bvar\s+(?P<name>[A-Za-z_]\w*)\s+as\s+(?P<type>[A-Za-z_][\w.]*)")
_MC_VAR_NAME_RE = re.compile(r"\bvar\s+(?P<name>[A-Za-z_]\w*)")
_MC_NEW_ASSIGN_RE = re.compile(
    r"(?<![\w.])(?:(?:me|self)\.)?(?P<name>[A-Za-z_]\w*)\s*=\s*new\s+(?P<type>[A-Za-z_][\w.]*)\s*\("
)
_MC_PARAM_TYPED_RE = re.compile(r"(?P<name>[A-Za-z_]\w*)\s+as\s+(?P<type>[A-Za-z_][\w.]*)")

# Statement keywords that are followed by `(` and would otherwise look like a
# call. `method` is Object.method(:sym), handled by its own branch; a
# `method(x)` with a non-symbol argument is not a call graph edge either.
_MC_CALL_KEYWORDS = frozenset({
    "if", "else", "for", "while", "do", "switch", "case", "default", "catch",
    "try", "finally", "return", "throw", "new", "function", "and", "or", "not",
    "instanceof", "has", "as", "break", "continue", "var", "const", "enum",
    "class", "module", "using", "import", "static", "hidden", "private",
    "public", "protected", "self", "me", "null", "true", "false", "method",
})

_MC_SELF = frozenset({"me", "self"})
_MC_SDK_ROOT = "Toybox"


def _expand_alias(name: str, aliases: dict[str, str]) -> str:
    """``Ui.View`` -> ``Toybox.WatchUi.View`` under ``using Toybox.WatchUi as Ui``."""
    head, sep, rest = name.partition(".")
    full = aliases.get(head)
    if full is None:
        return name
    return f"{full}.{rest}" if sep else full


def extract_monkeyc(path: Path) -> dict:
    """Extract modules, classes, functions, imports and calls from a ``.mc`` file."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except Exception as e:  # noqa: BLE001 - mirrors the other extractors
        return {"nodes": [], "edges": [], "error": str(e)}

    # Blank comments/literals in place: same length, newlines kept.
    def _blank(m: re.Match) -> str:
        return "".join("\n" if ch == "\n" else " " for ch in m.group(0))

    src = _MC_BLANK_RE.sub(_blank, text)
    line_starts = [0] + [m.end() for m in re.finditer(r"\n", src)]

    def _line(offset: int) -> int:
        return bisect.bisect_right(line_starts, offset)

    stem = _file_stem(path)
    str_path = str(path)
    nodes: list[dict] = []
    edges: list[dict] = []
    raw_calls: list[dict] = []
    seen_ids: set[str] = set()
    seen_edges: set[tuple[str, str, str]] = set()

    def add_node(nid: str, label: str, line: int, **extra) -> None:
        if nid in seen_ids:
            return
        seen_ids.add(nid)
        node = {"id": nid, "label": label, "file_type": "code",
                "source_file": str_path, "source_location": f"L{line}"}
        node.update(extra)
        nodes.append(node)

    def add_stub(nid: str, label: str) -> None:
        # Sourceless stub for a symbol defined outside this file (a base class or
        # an imported module). No source_file, so _disambiguate_colliding_node_ids
        # never bakes this file's path into the id and the unique-stub rewire can
        # collapse it onto the real definition (see powershell/objc for the same
        # pattern, #1402).
        if nid in seen_ids:
            return
        seen_ids.add(nid)
        nodes.append({"id": nid, "label": label, "file_type": "code",
                      "source_file": "", "source_location": ""})

    def add_edge(src: str, tgt: str, relation: str, line: int, *,
                 confidence: str = "EXTRACTED", context: str | None = None) -> None:
        key = (src, tgt, relation)
        if key in seen_edges:
            return
        seen_edges.add(key)
        edge = {"source": src, "target": tgt, "relation": relation,
                "confidence": confidence, "source_file": str_path,
                "source_location": f"L{line}", "weight": 1.0}
        if context:
            edge["context"] = context
        edges.append(edge)

    file_nid = _make_id(str(path))
    add_node(file_nid, path.name, 1)

    aliases: dict[str, str] = {}
    # owner nid -> {function name -> function nid}; the file's own functions
    # are keyed by file_nid.
    funcs_by_owner: dict[str, dict[str, str]] = {}
    # type name -> nid for classes/modules declared in this file
    local_types: dict[str, str] = {}
    class_bases: list[tuple[str, str, int]] = []       # (class nid, base as written, line)
    bare_imports: list[tuple[str, int]] = []           # (module name, line)
    func_scopes: list[dict] = []                        # closed function scopes
    class_spans: list[dict] = []                        # closed class/module scopes

    # Scope stack. kind: file | module | class | function | block.
    stack: list[dict] = [{"kind": "file", "nid": file_nid, "name": path.name, "start": 0}]

    def _owner() -> dict:
        for scope in reversed(stack):
            if scope["kind"] in ("file", "module", "class"):
                return scope
        return stack[0]

    def _enclosing(kind: str) -> dict | None:
        for scope in reversed(stack):
            if scope["kind"] == kind:
                return scope
        return None

    for m in _MC_TOKEN_RE.finditer(src):
        kind = m.lastgroup
        line = _line(m.start())
        if kind == "import":
            name = m.group("import_name")
            alias = m.group("import_alias") or name.rsplit(".", 1)[-1]
            aliases[alias] = name
            if "." in name:
                add_edge(file_nid, _make_id(name), "imports_from", line, context="import")
            else:
                # A bare import names a module of this app — possibly one
                # declared further down this very file, so it is resolved in
                # the post-pass below.
                bare_imports.append((name, line))
        elif kind == "klass":
            owner = _owner()
            prefix = stem if owner["kind"] == "file" else owner["nid"]
            name = m.group("class_name")
            nid = _make_id(prefix, name)
            add_node(nid, name, line, _callable=True, _callable_class=True)
            add_edge(owner["nid"], nid, "contains", line)
            local_types.setdefault(name, nid)
            base = m.group("class_base")
            if base:
                class_bases.append((nid, base, line))
            stack.append({"kind": "class", "nid": nid, "name": name, "start": m.end()})
        elif kind == "module":
            owner = _owner()
            prefix = stem if owner["kind"] == "file" else owner["nid"]
            name = m.group("module_name")
            nid = _make_id(prefix, name)
            add_node(nid, name, line)
            add_edge(owner["nid"], nid, "contains", line)
            local_types.setdefault(name, nid)
            stack.append({"kind": "module", "nid": nid, "name": name, "start": m.end()})
        elif kind == "func":
            owner = _owner()
            name = m.group("func_name")
            if owner["kind"] == "class":
                nid = _make_id(owner["nid"], name)
                add_node(nid, f".{name}()", line, _callable=True)
                add_edge(owner["nid"], nid, "method", line)
            else:
                prefix = stem if owner["kind"] == "file" else owner["nid"]
                nid = _make_id(prefix, name)
                add_node(nid, f"{name}()", line, _callable=True)
                add_edge(owner["nid"], nid, "contains", line)
            funcs_by_owner.setdefault(owner["nid"], {}).setdefault(name, nid)
            stack.append({"kind": "function", "nid": nid, "name": name,
                          "start": m.end(), "owner": owner,
                          "params": m.group("func_params") or "", "line": line})
        elif kind == "open":
            stack.append({"kind": "block", "start": m.end()})
        elif kind == "close":
            if len(stack) <= 1:
                continue  # unbalanced `}` — never pop the file scope
            scope = stack.pop()
            scope["end"] = m.start()
            if scope["kind"] == "function":
                func_scopes.append(scope)
            elif scope["kind"] in ("class", "module"):
                class_spans.append(scope)

    # A scope still open at EOF (unbalanced source) closes at the end.
    while len(stack) > 1:
        scope = stack.pop()
        scope["end"] = len(src)
        if scope["kind"] == "function":
            func_scopes.append(scope)
        elif scope["kind"] in ("class", "module"):
            class_spans.append(scope)

    # ── bare imports (post-pass: the module may be declared later in the file) ──
    for name, line in bare_imports:
        if name in local_types:
            target = local_types[name]
        else:
            # A module of this app defined in another file: a sourceless stub
            # lets the corpus-level unique-stub rewire collapse the edge onto
            # the real module node.
            target = _make_id(name)
            add_stub(target, name)
        add_edge(file_nid, target, "imports_from", line, context="import")

    # ── inherits (post-pass: the base may be declared later in the file) ──
    for cls_nid, base, line in class_bases:
        if "." not in base and base in local_types:
            base_nid = local_types[base]
        else:
            label = _expand_alias(base, aliases)
            base_nid = _make_id(label)
            add_stub(base_nid, label)
        if base_nid != cls_nid:
            add_edge(cls_nid, base_nid, "inherits", line)

    # ── type tables for receiver typing ──
    # Every typed `var`, `x = new T(` and typed parameter is attributed to the
    # innermost function (a local) or, outside any function, to the enclosing
    # class/module (a field). A name bound to two different types is dropped.
    func_scopes.sort(key=lambda s: s["start"])
    func_starts = [s["start"] for s in func_scopes]

    def _func_at(offset: int) -> dict | None:
        i = bisect.bisect_right(func_starts, offset) - 1
        if i >= 0 and offset < func_scopes[i]["end"]:
            return func_scopes[i]
        return None

    class_spans.sort(key=lambda s: s["start"])

    def _type_scope_at(offset: int) -> dict | None:
        best = None
        for scope in class_spans:
            if scope["start"] <= offset < scope["end"]:
                best = scope  # spans are nested; the last (innermost) start wins
        return best

    locals_by_func: dict[str, dict[str, str | None]] = {}
    fields_by_type: dict[str, dict[str, str | None]] = {}
    declared_locals: dict[str, set[str]] = {}

    def _bind(table: dict[str, str | None], name: str, type_name: str) -> None:
        prev = table.get(name, ...)
        if prev is ... or prev == type_name:
            table[name] = type_name
        else:
            table[name] = None  # ambiguous

    for fs in func_scopes:
        for pm in _MC_PARAM_TYPED_RE.finditer(fs["params"]):
            _bind(locals_by_func.setdefault(fs["nid"], {}), pm.group("name"), pm.group("type"))
    for vm in _MC_VAR_NAME_RE.finditer(src):
        fs = _func_at(vm.start())
        if fs is not None:
            declared_locals.setdefault(fs["nid"], set()).add(vm.group("name"))
    for vm in _MC_VAR_TYPED_RE.finditer(src):
        fs = _func_at(vm.start())
        if fs is not None:
            _bind(locals_by_func.setdefault(fs["nid"], {}), vm.group("name"), vm.group("type"))
        else:
            ts = _type_scope_at(vm.start())
            owner_nid = ts["nid"] if ts is not None else file_nid
            _bind(fields_by_type.setdefault(owner_nid, {}), vm.group("name"), vm.group("type"))
    for am in _MC_NEW_ASSIGN_RE.finditer(src):
        name, type_name = am.group("name"), am.group("type")
        fs = _func_at(am.start())
        if fs is not None and name in declared_locals.get(fs["nid"], ()):
            _bind(locals_by_func.setdefault(fs["nid"], {}), name, type_name)
            continue
        ts = _type_scope_at(am.start())
        owner_nid = ts["nid"] if ts is not None else file_nid
        _bind(fields_by_type.setdefault(owner_nid, {}), name, type_name)

    # ── calls ──
    seen_call_pairs: set[tuple[str, str]] = set()

    def _module_of(scope: dict) -> str | None:
        # The innermost module that contains a scope, for a bare call from a
        # class method to a function of the enclosing module. Spans are sorted
        # by start, so a nested module comes after its parent: keep the last hit.
        best = None
        for outer in class_spans:
            if outer["kind"] == "module" and outer["start"] <= scope["start"] < outer["end"]:
                best = outer["nid"]
        return best

    def _receiver_type(fs: dict, recv: str) -> tuple[str | None, str | None]:
        """(type name, kind) for a member-call receiver, or (None, None)."""
        head = recv.split(".", 1)[0]
        if "." not in recv:
            typed = locals_by_func.get(fs["nid"], {}).get(recv)
            if typed is None:
                owner = fs["owner"]
                typed = fields_by_type.get(owner["nid"], {}).get(recv)
                if typed is None and owner["kind"] == "class":
                    mod = _module_of(fs)
                    if mod:
                        typed = fields_by_type.get(mod, {}).get(recv)
                if typed is None:
                    typed = fields_by_type.get(file_nid, {}).get(recv)
            if typed:
                return _expand_alias(typed, aliases), "typed"
        if head[:1].isupper():
            return _expand_alias(recv, aliases), "static"
        return None, None

    def _emit_call(caller: str, target: str, relation: str, line: int, *,
                   confidence: str = "EXTRACTED", context: str = "call") -> None:
        if target == caller:
            return
        pair = (caller, target)
        if pair in seen_call_pairs:
            return
        seen_call_pairs.add(pair)
        add_edge(caller, target, relation, line, confidence=confidence, context=context)

    def _resolve_bare(fs: dict, name: str) -> str | None:
        owner = fs["owner"]
        hit = funcs_by_owner.get(owner["nid"], {}).get(name)
        if hit:
            return hit
        if owner["kind"] == "class":
            mod = _module_of(fs)
            if mod:
                hit = funcs_by_owner.get(mod, {}).get(name)
                if hit:
                    return hit
        if owner["kind"] != "file":
            hit = funcs_by_owner.get(file_nid, {}).get(name)
            if hit:
                return hit
        return None

    def _raw(fs: dict, callee: str, line: int, **extra) -> None:
        rc = {"caller_nid": fs["nid"], "callee": callee, "is_member_call": False,
              "lang": "monkeyc", "source_file": str_path, "source_location": f"L{line}"}
        rc.update(extra)
        raw_calls.append(rc)

    def _callback(fs: dict, sym: str, line: int) -> None:
        target = _resolve_bare(fs, sym)
        if target:
            _emit_call(fs["nid"], target, "indirect_call", line,
                       confidence="INFERRED", context="callback")
        else:
            _raw(fs, sym, line, indirect=True, context="callback",
                 self_scope=fs["owner"]["kind"] == "class")

    for fs in func_scopes:
        body = src[fs["start"]:fs["end"]]
        base = fs["start"]
        for cm in _MC_CALL_RE.finditer(body):
            line = _line(base + cm.start())
            branch = cm.lastgroup
            if branch == "new":
                type_name = cm.group("new_type")
                if type_name.rsplit(".", 1)[-1] == "Method":
                    om = _MC_METHOD_OBJ_RE.match(body, cm.end())
                    if om is not None:
                        if om.group("obj") in _MC_SELF:
                            _callback(fs, om.group("sym"), line)
                        else:
                            _raw(fs, om.group("sym"), line, indirect=True, context="callback")
                        continue
                if "." not in type_name and type_name in local_types:
                    _emit_call(fs["nid"], local_types[type_name], "calls", line)
                elif _expand_alias(type_name, aliases).startswith(_MC_SDK_ROOT + "."):
                    continue  # SDK constructor: never binds to a same-named app class
                else:
                    # `new Foo(...)` is a call to Foo's constructor: the shared
                    # cross-file pass resolves the bare type name (as the Java
                    # extractor does for object_creation_expression, #1373).
                    _raw(fs, type_name.rsplit(".", 1)[-1], line)
            elif branch == "mref":
                _callback(fs, cm.group("mref_name"), line)
            else:
                callee = cm.group("callee")
                recv = cm.group("recv")
                if recv:
                    head, _, rest = recv.partition(".")
                    if head in _MC_SELF:
                        recv = rest or None
                if callee == "method":
                    # `me.method(:sym)` / `obj.method(:sym)`: same callback as
                    # the bare `method(:sym)` branch, on a receiver.
                    sm = _MC_METHOD_SYM_RE.match(body, cm.end())
                    if sm is not None:
                        if recv is None:
                            _callback(fs, sm.group("sym"), line)
                        else:
                            _raw(fs, sm.group("sym"), line, indirect=True, context="callback")
                    continue
                if callee in _MC_CALL_KEYWORDS:
                    continue
                if not recv:
                    target = _resolve_bare(fs, callee)
                    if target:
                        _emit_call(fs["nid"], target, "calls", line)
                    else:
                        _raw(fs, callee, line, self_scope=fs["owner"]["kind"] == "class")
                    continue
                if "." not in recv and recv in local_types:
                    target = funcs_by_owner.get(local_types[recv], {}).get(callee)
                    if target:
                        _emit_call(fs["nid"], target, "calls", line)
                        continue
                type_name, kind = _receiver_type(fs, recv)
                _raw(fs, callee, line, is_member_call=True, receiver=recv,
                     receiver_type=type_name, receiver_kind=kind)

    clean_edges = [e for e in edges if e["source"] in seen_ids and
                   (e["target"] in seen_ids or e["relation"] == "imports_from")]
    return {"nodes": nodes, "edges": clean_edges, "raw_calls": raw_calls}


def resolve_monkeyc_member_calls(
    per_file: list[dict],
    all_nodes: list[dict],
    all_edges: list[dict],
) -> None:
    """Resolve cross-file Monkey C member calls and inherited bare calls.

    The shared cross-file call pass skips every ``is_member_call`` (a bare method
    name collides across the corpus and inflates god nodes, #543/#1219). Monkey C
    code is dominated by such calls: an app is one namespace of modules and
    classes, so ``Store.get()``, ``BleSession.enroll()`` and
    ``_transport.write()`` are the architecture. The extractor records the
    receiver and, when it can, its type; this pass binds the call ONLY when that
    type name resolves to exactly one Monkey C definition (the god-node guard) and
    the callee is a function of that type or of a base along its ``inherits``
    chain (a module's functions hang off ``contains`` edges, a class's off
    ``method`` edges). An explicit ``Type.fn()`` qualifier is EXTRACTED; a
    receiver typed by local inference is INFERRED. A qualified call whose type is
    known but whose function is not (a field, an SDK method on a local
    subclass) becomes a type-level ``references`` edge.

    A bare call the extractor could not resolve inside its own file but which
    was made from a class body (``self_scope``) is looked up along the caller's
    class ``inherits`` chain — the ``initialize()`` / ``onShow()`` -style call to
    a method a base class in another file provides; when the shared pass already
    bound that pair by corpus-unique name, nothing is added. ``Toybox.*``
    receivers are the SDK and never resolve to app code.

    Purely additive; runs after id disambiguation so node ids are final.
    """
    raw = [
        rc
        for result in per_file
        for rc in (result.get("raw_calls") or [])
        if rc.get("lang") == "monkeyc" and rc.get("callee") and rc.get("caller_nid")
        and (rc.get("receiver_type") or rc.get("self_scope"))
    ]
    if not raw:
        return

    node_by_id: dict[str, dict] = {n["id"]: n for n in all_nodes if n.get("id")}
    # Real (sourced) Monkey C class/module definitions, by exact label. Labels of
    # functions carry `()`, so `endswith(")")` keeps them out; a stub has no
    # source_file and is skipped so the guard counts definitions only.
    types_by_label: dict[str, list[str]] = {}
    for n in all_nodes:
        sf = str(n.get("source_file") or "")
        if not sf.endswith(".mc") or n.get("file_type") != "code":
            continue
        label = str(n.get("label", ""))
        if not label or label.endswith(")") or label.startswith(".") or "." in label:
            continue
        if label == Path(sf).name:
            continue  # the file node
        types_by_label.setdefault(label, []).append(n["id"])

    children: dict[str, dict[str, str]] = {}   # type nid -> {function name -> nid}
    parent_of: dict[str, str] = {}             # function nid -> owning type nid
    bases: dict[str, list[str]] = {}
    for e in all_edges:
        rel = e.get("relation")
        src, tgt = e.get("source"), e.get("target")
        if rel in ("method", "contains"):
            tnode = node_by_id.get(tgt)
            if tnode is None:
                continue
            label = str(tnode.get("label", ""))
            if label.endswith("()"):
                name = label[:-2].lstrip(".")
                children.setdefault(src, {}).setdefault(name, tgt)
                parent_of.setdefault(tgt, src)
        elif rel == "inherits":
            bases.setdefault(src, []).append(tgt)

    def _lookup(type_nid: str, name: str) -> str | None:
        seen: set[str] = set()
        frontier = [type_nid]
        depth = 0
        while frontier and depth < 16:
            nxt: list[str] = []
            for t in frontier:
                if t in seen:
                    continue
                seen.add(t)
                hit = children.get(t, {}).get(name)
                if hit:
                    return hit
                nxt.extend(bases.get(t, []))
            frontier = nxt
            depth += 1
        return None

    existing = {(e.get("source"), e.get("target")) for e in all_edges}
    for rc in raw:
        caller = rc["caller_nid"]
        callee = rc["callee"]
        indirect = bool(rc.get("indirect"))
        relation = "indirect_call" if indirect else "calls"
        target: str | None = None
        rtype = rc.get("receiver_type")
        if rtype:
            if rtype == _MC_SDK_ROOT or rtype.startswith(_MC_SDK_ROOT + "."):
                continue
            head = rtype.rsplit(".", 1)[-1]
            if head in _LANGUAGE_BUILTIN_GLOBALS:
                continue
            candidates = types_by_label.get(rtype) or types_by_label.get(head, [])
            if len(candidates) != 1:
                continue
            type_nid = candidates[0]
            target = _lookup(type_nid, callee)
            if target is None:
                if rc.get("receiver_kind") != "static":
                    continue
                target = type_nid
                relation = "references"
            confidence = "EXTRACTED" if rc.get("receiver_kind") == "static" else "INFERRED"
        else:
            owner = parent_of.get(caller)
            if not owner:
                continue
            target = _lookup(owner, callee)
            confidence = "EXTRACTED"
        if indirect:
            confidence = "INFERRED"  # a callback names the method; it is not invoked here
        # The shared pass runs first and may already have bound the same pair
        # (an inherited bare call resolved by corpus-unique name); additive only.
        if not target or target == caller or (caller, target) in existing:
            continue
        existing.add((caller, target))
        edge = {
            "source": caller,
            "target": target,
            "relation": relation,
            "confidence": confidence,
            "source_file": rc.get("source_file", ""),
            "source_location": rc.get("source_location"),
            "weight": 1.0,
            "context": rc.get("context") or ("callback" if indirect else "call"),
        }
        all_edges.append(edge)
