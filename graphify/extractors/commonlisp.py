"""Common Lisp extractor for .lisp/.cl/.lsp/.asd, backed by tree-sitter-commonlisp."""
from __future__ import annotations

import warnings
from pathlib import Path

from graphify.extractors.base import _make_id


# Standard CL definer forms that introduce data/type/variable bindings
# (not callable, no body to walk for calls)
_CL_DATA_DEFINERS = frozenset({
    "defstruct", "deftype", "define-condition",
    "defvar", "defparameter", "defconstant",
    "define-symbol-macro",
})

# Subset of data definers that take a VALUE as their second argument, which
# may itself be a string literal. For these, we must not mistake the value
# for a docstring.
_CL_VALUE_DEFINERS = frozenset({"defvar", "defparameter", "defconstant"})

# Standard CL macro-style definers
_CL_MACRO_DEFINERS = frozenset({
    "define-modify-macro", "define-compiler-macro",
    "define-setf-expander", "defsetf",
})

# Symbols that start with "def" but are NOT definitions (denylist for the
# def-prefix heuristic that catches custom definers like definline-maybe)
_CL_NOT_DEFINERS = frozenset({
    "default", "default-value", "defaults", "define",
    "defer", "deferred", "deflate", "deftest",
})

# CL special forms / macros that should not count as "calls" in the graph
_CL_SPECIAL_FORMS = frozenset({
    "let", "let*", "flet", "labels", "macrolet",
    "if", "when", "unless", "cond", "case", "ecase", "typecase", "etypecase",
    "progn", "prog1", "prog2", "block", "return-from", "tagbody", "go",
    "lambda", "function", "funcall", "apply",
    "setf", "setq", "psetf", "psetq", "incf", "decf", "push", "pop",
    "loop", "do", "do*", "dolist", "dotimes", "map", "mapcar", "mapc",
    "format", "print", "princ", "prin1", "write", "terpri",
    "and", "or", "not", "null",
    "values", "multiple-value-bind", "multiple-value-setq",
    "declare", "the", "locally", "eval-when",
    "quote", "backquote",
    "error", "signal", "warn", "assert", "check-type",
    "handler-case", "handler-bind", "restart-case", "ignore-errors",
    "unwind-protect", "catch", "throw",
    "with-open-file", "with-output-to-string", "with-input-from-string",
    "with-slots", "with-accessors",
    "defvar", "defparameter", "defconstant",
    "in-package", "require", "provide", "use-package",
    "t", "nil",
})


def extract_commonlisp(path: Path) -> dict:
    """Extract packages, classes, functions, methods, macros, and calls from a Common Lisp file."""
    try:
        import tree_sitter_commonlisp as tscl
        from tree_sitter import Language, Parser
    except ImportError:
        return {"nodes": [], "edges": [], "error": "tree-sitter-commonlisp not installed"}

    try:
        # tree-sitter-commonlisp 0.4.1 (latest) ships the old binding that returns
        # an int pointer from language(); tree_sitter.Language only accepts that
        # int via a deprecated path. Silence that one warning at the call site
        # until the grammar ships a PyCapsule binding.
        with warnings.catch_warnings():
            warnings.filterwarnings(
                "ignore",
                message="int argument support is deprecated",
                category=DeprecationWarning,
            )
            language = Language(tscl.language())
        parser = Parser(language)
        source = path.read_bytes()
        tree = parser.parse(source)
        root = tree.root_node
    except Exception as e:
        return {"nodes": [], "edges": [], "error": str(e)}

    stem = path.stem
    str_path = str(path)
    nodes: list[dict] = []
    edges: list[dict] = []
    seen_ids: set[str] = set()
    function_bodies: list[tuple[str, object]] = []  # (nid, body_nodes)
    current_package: str | None = None

    def _text(node) -> str:
        return source[node.start_byte:node.end_byte].decode("utf-8", errors="replace")

    # CL symbols can contain operator chars like = < > ? ! + * / that the
    # generic _make_id strips. Map them to readable suffixes so upi=, upi<,
    # upi> become distinct ids.
    _CL_CHAR_MAP = {
        '=': '_eq', '<': '_lt', '>': '_gt', '?': '_p', '!': '_bang',
        '+': '_plus', '*': '_star', '/': '_slash', '%': '_pct', '&': '_amp',
    }

    def _cl_id(*parts: str) -> str:
        normalized = []
        for p in parts:
            normalized.append(''.join(_CL_CHAR_MAP.get(c, c) for c in p))
        return _make_id(*normalized)

    def add_node(nid: str, label: str, line: int, file_type: str = "code") -> None:
        if nid not in seen_ids:
            seen_ids.add(nid)
            nodes.append({
                "id": nid,
                "label": label,
                "file_type": file_type,
                "source_file": str_path,
                "source_location": f"L{line}",
            })

    def add_edge(src: str, tgt: str, relation: str, line: int,
                 confidence: str = "EXTRACTED", weight: float = 1.0) -> None:
        edges.append({
            "source": src,
            "target": tgt,
            "relation": relation,
            "confidence": confidence,
            "source_file": str_path,
            "source_location": f"L{line}",
            "weight": weight,
        })

    file_nid = _cl_id(stem)
    add_node(file_nid, path.name, 1)

    def add_import_stub(mod_name: str) -> str:
        """Mint a SOURCELESS stub for an imported package so its `imports` edge
        has a real target instead of dangling. The corpus rewire collapses it
        onto a unique in-corpus `defpackage` of the same name; an external one
        (cl, alexandria) stays a sourceless leaf. `origin_file` is stripped
        before persist (no #1899 leak); a sourced bare stub would salt the id."""
        nid = _cl_id(mod_name)
        if nid not in seen_ids:
            seen_ids.add(nid)
            nodes.append({
                "id": nid,
                "label": mod_name,
                "file_type": "code",
                "source_file": "",
                "source_location": "",
                "origin_file": str_path,
            })
        return nid

    def ensure_class_ref(name: str, line: int) -> str:
        """Resolve a superclass name to a node id.

        If the class is defined in THIS file, bind to its local node. Otherwise
        mint a SOURCELESS stub (like `add_import_stub`) so the corpus-level
        rewire can collapse it onto the real `defclass` in another file. Without
        this, a cross-file superclass had no matching node and its `inherits`
        edge was pruned by the dangling-edge filter — silently erasing every
        inheritance edge whose parent lives in a different file."""
        local = _cl_id(stem, name)
        if local in seen_ids:
            return local
        stub = _cl_id(name)
        if stub not in seen_ids:
            seen_ids.add(stub)
            nodes.append({
                "id": stub,
                "label": name,
                "file_type": "code",
                "source_file": "",
                "source_location": "",
                "origin_file": str_path,
            })
        return stub

    def _first_sym(node) -> str | None:
        """Get the first sym_lit text from a list_lit's children."""
        for child in node.children:
            if child.type == "sym_lit":
                return _text(child)
        return None

    def _kwd_text(node) -> str:
        """Extract the symbol name from a kwd_lit, stripping the leading colon."""
        t = _text(node)
        return t.lstrip(":").lstrip("#:")

    def _handle_defpackage(node) -> None:
        nonlocal current_package
        children = node.children
        pkg_name = None
        for child in children:
            if child.type == "kwd_lit" and pkg_name is None:
                pkg_name = _kwd_text(child)
                break
            if child.type == "sym_lit" and _text(child) != "defpackage":
                pkg_name = _text(child)
                break
        if not pkg_name:
            return
        current_package = pkg_name
        pkg_nid = _cl_id(stem, pkg_name)
        line = node.start_point[0] + 1
        add_node(pkg_nid, pkg_name, line)
        add_edge(file_nid, pkg_nid, "contains", line)

        # Extract :use clauses as imports
        for child in children:
            if child.type == "list_lit":
                first = _first_sym(child)
                if first is None:
                    # Could be (:use ...) with kwd_lit
                    for gc in child.children:
                        if gc.type == "kwd_lit" and _kwd_text(gc) == "use":
                            for uc in child.children:
                                if uc.type == "kwd_lit" and uc != gc:
                                    mod_name = _kwd_text(uc)
                                    if mod_name != "use":
                                        tgt_nid = add_import_stub(mod_name)
                                        add_edge(pkg_nid, tgt_nid, "imports",
                                                 child.start_point[0] + 1)
                            break

    def _handle_defclass(node) -> None:
        children = node.children
        # Find class name: second sym_lit after "defclass"
        sym_lits = [c for c in children if c.type == "sym_lit"]
        if len(sym_lits) < 2:
            return
        class_name = _text(sym_lits[1])
        line = node.start_point[0] + 1
        class_nid = _cl_id(stem, class_name)
        add_node(class_nid, class_name, line)

        parent_nid = file_nid
        if current_package:
            pkg_nid = _cl_id(stem, current_package)
            if pkg_nid in seen_ids:
                parent_nid = pkg_nid
        add_edge(parent_nid, class_nid, "contains", line)

        # Superclasses (third element, a list)
        list_lits = [c for c in children if c.type == "list_lit"]
        if list_lits:
            superclass_list = list_lits[0]
            for sc in superclass_list.children:
                if sc.type == "sym_lit":
                    sc_name = _text(sc)
                    sc_nid = ensure_class_ref(sc_name, superclass_list.start_point[0] + 1)
                    add_edge(class_nid, sc_nid, "inherits",
                             superclass_list.start_point[0] + 1)

    def _handle_defun_node(node) -> None:
        """Handle a defun AST node (covers defun, defmethod, defgeneric, defmacro)."""
        header = None
        for child in node.children:
            if child.type == "defun_header":
                header = child
                break
        if not header:
            return

        # Determine keyword type
        keyword_type = "defun"
        func_name = None
        for child in header.children:
            if child.type == "defun_keyword":
                for kc in child.children:
                    if kc.type in ("defun", "defmethod", "defgeneric", "defmacro"):
                        keyword_type = kc.type
                        break
            if child.type == "sym_lit" and func_name is None:
                func_name = _text(child)

        if not func_name:
            return

        line = node.start_point[0] + 1
        func_nid = _cl_id(stem, func_name)

        if keyword_type == "defmethod":
            label = f".{func_name}()"
        elif keyword_type == "defmacro":
            label = f"{func_name} (macro)"
        elif keyword_type == "defgeneric":
            label = f"{func_name} (generic)"
        else:
            label = f"{func_name}()"

        add_node(func_nid, label, line)

        parent_nid = file_nid
        if current_package:
            pkg_nid = _cl_id(stem, current_package)
            if pkg_nid in seen_ids:
                parent_nid = pkg_nid
        if keyword_type == "defmethod":
            add_edge(parent_nid, func_nid, "method", line)
        else:
            add_edge(parent_nid, func_nid, "contains", line)

        # Method specializers: (defmethod name ((param class) ...))
        if keyword_type == "defmethod":
            for child in header.children:
                if child.type == "list_lit":
                    # This is the parameter list
                    for param in child.children:
                        if param.type == "list_lit":
                            syms = [c for c in param.children if c.type == "sym_lit"]
                            if len(syms) >= 2:
                                specializer_name = _text(syms[1])
                                spec_nid = _cl_id(stem, specializer_name)
                                add_edge(func_nid, spec_nid, "specializes",
                                         param.start_point[0] + 1)
                    break

        # Docstring
        for child in node.children:
            if child.type == "str_lit":
                doc_text = _text(child).strip('"')
                if doc_text:
                    doc_nid = _cl_id(func_nid, "rationale")
                    add_node(doc_nid, doc_text[:120], child.start_point[0] + 1, file_type="rationale")
                    add_edge(doc_nid, func_nid, "rationale_for",
                             child.start_point[0] + 1)
                break

        # Collect body for call extraction
        body_nodes = [c for c in node.children
                      if c.type not in ("(", ")", "defun_header", "str_lit")]
        if body_nodes:
            function_bodies.append((func_nid, body_nodes))

    def _extract_def_name(node, def_keyword: str) -> str | None:
        """Get the name being defined. May be a sym_lit or a list_lit whose
        first sym_lit is the name (e.g. (defstruct (foo :conc-name "BAR-") ...))."""
        seen_keyword = False
        for child in node.children:
            if not seen_keyword:
                if child.type == "sym_lit" and _text(child).lower() == def_keyword:
                    seen_keyword = True
                continue
            if child.type == "sym_lit":
                return _text(child)
            if child.type == "list_lit":
                for gc in child.children:
                    if gc.type == "sym_lit":
                        return _text(gc)
                return None
        return None

    def _collect_def_body(node, def_keyword: str) -> list:
        """Collect body forms from (DEFKEYWORD name (params) [doc] body...).
        Skips the def keyword, the name, the params list (if present), and
        a leading docstring str_lit."""
        children = [c for c in node.children if c.type not in ("(", ")")]
        idx = 0
        # Skip def keyword
        if idx < len(children) and children[idx].type == "sym_lit" \
           and _text(children[idx]).lower() == def_keyword:
            idx += 1
        # Skip name (sym_lit or list_lit)
        if idx < len(children) and children[idx].type in ("sym_lit", "list_lit"):
            idx += 1
        # Skip params list (the next list_lit, if any)
        if idx < len(children) and children[idx].type == "list_lit":
            idx += 1
        # Skip leading docstring
        if idx < len(children) and children[idx].type == "str_lit":
            idx += 1
        return children[idx:]

    def _handle_def_form(node, def_keyword: str) -> None:
        """Handle a generic (DEFKEYWORD name ...) form. Covers standard CL
        definers (defstruct, deftype, defvar, define-condition, etc.) and
        custom def-prefixed macros (definline, definline-maybe, etc.)."""
        name = _extract_def_name(node, def_keyword)
        if not name:
            return
        line = node.start_point[0] + 1
        nid = _cl_id(stem, name)

        kw = def_keyword.lower()
        if kw in _CL_DATA_DEFINERS:
            label = name
            is_callable = False
        elif kw in _CL_MACRO_DEFINERS or "macro" in kw:
            label = f"{name} (macro)"
            is_callable = True
        else:
            # Custom def-prefixed: assume function-like
            label = f"{name}()"
            is_callable = True

        add_node(nid, label, line)

        parent_nid = file_nid
        if current_package:
            pkg_nid = _cl_id(stem, current_package)
            if pkg_nid in seen_ids:
                parent_nid = pkg_nid
        add_edge(parent_nid, nid, "contains", line)

        # Docstring. Skip for defvar/defparameter/defconstant — their second
        # argument is a value (possibly a string literal) which would be
        # wrongly captured as a docstring.
        if kw not in _CL_VALUE_DEFINERS:
            for child in node.children:
                if child.type == "str_lit":
                    doc_text = _text(child).strip('"')
                    if doc_text:
                        doc_nid = _cl_id(nid, "rationale")
                        add_node(doc_nid, doc_text[:120], child.start_point[0] + 1, file_type="rationale")
                        add_edge(doc_nid, nid, "rationale_for",
                                 child.start_point[0] + 1)
                    break

        if is_callable:
            body_nodes = _collect_def_body(node, def_keyword)
            if body_nodes:
                function_bodies.append((nid, body_nodes))

    def _is_def_prefixed(sym: str) -> bool:
        """Heuristic: does this symbol look like a definition macro?"""
        if sym in _CL_NOT_DEFINERS:
            return False
        return sym.startswith("def") or sym.startswith("define-")

    def _process_form(top) -> bool:
        """Dispatch on a single list_lit form. Returns True if it was
        recognized as a definition or package directive (caller must NOT
        recurse into it). Returns False if unrecognized, so the caller can
        recurse to find defs nested inside wrapper macros like
        (optimizing ...), (eval-when ...), (progn ...), etc."""
        nonlocal current_package

        # Check for defun node type inside list_lit
        for child in top.children:
            if child.type == "defun":
                _handle_defun_node(child)
                return True

        first = _first_sym(top)
        if not first:
            return False
        first_lower = first.lower()

        if first_lower == "defpackage":
            _handle_defpackage(top)
            return True
        if first_lower == "in-package":
            for child in top.children:
                if child.type == "kwd_lit":
                    current_package = _kwd_text(child)
                    break
                if child.type == "sym_lit" and _text(child) != "in-package":
                    current_package = _text(child)
                    break
            return True
        if first_lower == "defclass":
            _handle_defclass(top)
            return True
        if first_lower in ("require", "ql:quickload"):
            for child in top.children:
                if child.type in ("kwd_lit", "str_lit"):
                    mod_name = _kwd_text(child) if child.type == "kwd_lit" else _text(child).strip('"')
                    if mod_name:
                        tgt_nid = add_import_stub(mod_name)
                        add_edge(file_nid, tgt_nid, "imports",
                                 top.start_point[0] + 1)
                    break
            return True
        if first_lower in _CL_DATA_DEFINERS or first_lower in _CL_MACRO_DEFINERS:
            _handle_def_form(top, first_lower)
            return True
        if _is_def_prefixed(first_lower):
            # Custom definer (definline, definline-maybe, defcomponent, etc.)
            _handle_def_form(top, first_lower)
            return True

        return False

    def _walk_forms(parent) -> None:
        """Walk list_lit children of `parent`, processing each. If a form
        isn't recognized, recurse into it — many CL codebases wrap
        definitions in macros like (optimizing ...), (eval-when ...), or
        (progn ...) that aren't themselves definers but contain defs.
        Also descends into reader conditionals (#+feature / #-feature),
        which wrap their guarded form in an include_reader_macro node."""
        for top in parent.children:
            if top.type == "list_lit":
                if not _process_form(top):
                    _walk_forms(top)
            elif top.type == "include_reader_macro":
                _walk_forms(top)

    _walk_forms(root)

    # Call extraction pass
    label_to_nid: dict[str, str] = {}
    for n in nodes:
        raw = n["label"]
        normalised = raw.replace(" (macro)", "").replace(" (generic)", "").strip("()").lstrip(".")
        label_to_nid[normalised.lower()] = n["id"]

    seen_call_pairs: set[tuple[str, str]] = set()

    def walk_calls(node, caller_nid: str) -> None:
        if node.type == "defun":
            return
        if node.type == "list_lit":
            callee = _first_sym(node)
            if callee and callee.lower() not in _CL_SPECIAL_FORMS:
                tgt_nid = label_to_nid.get(callee.lower())
                if tgt_nid and tgt_nid != caller_nid:
                    pair = (caller_nid, tgt_nid)
                    if pair not in seen_call_pairs:
                        seen_call_pairs.add(pair)
                        add_edge(caller_nid, tgt_nid, "calls",
                                 node.start_point[0] + 1, confidence="EXTRACTED", weight=1.0)
        for child in node.children:
            walk_calls(child, caller_nid)

    for caller_nid, body_nodes in function_bodies:
        for body_node in body_nodes:
            walk_calls(body_node, caller_nid)

    clean_edges = [e for e in edges if e["source"] in seen_ids and
                   (e["target"] in seen_ids or e["relation"] in ("imports", "imports_from"))]
    return {"nodes": nodes, "edges": clean_edges}
