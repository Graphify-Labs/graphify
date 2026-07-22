"""Fortran extractor. Moved verbatim from graphify/extract.py."""
from __future__ import annotations


import re
from pathlib import Path
from graphify.extractors.base import _file_stem, _make_id, _read_text


_FORTRAN_CPP_EXTS = {".F", ".F90", ".F95", ".F03", ".F08"}

# cpp (run WITHOUT -P) emits linemarkers `# <lineno> "<file>" [flags]` to resync
# line numbering after it blanks directive lines, drops inactive #ifdef blocks,
# and expands macros. We consume them to map a preprocessed line back to the
# original source line. cpp escapes `\` and `"` inside the quoted filename.
_LINEMARKER = re.compile(rb'^#\s+(\d+)\s+"((?:[^"\\]|\\.)*)"')


def _decode_marker_path(raw: bytes) -> str:
    """Decode a cpp linemarker filename, undoing cpp's `\\` and `"` escaping."""
    return raw.decode("utf-8", "replace").replace('\\"', '"').replace("\\\\", "\\")


def _strip_linemarkers(out: bytes, path: Path) -> tuple[bytes, list[int]]:
    """Split cpp output into (source_without_markers, line_map).

    Each `# <n> "<file>"` linemarker sets the original line of the *next* output
    line; every other line is real source and is kept verbatim (blank lines
    included) so the returned buffer's row numbering stays in lockstep with
    line_map. line_map[i] is the 1-based original source line for output row i,
    or 0 for a synthetic (`<built-in>`) or included region the caller should not
    trust. Blanked-out directive lines are preserved as empty lines so tree-sitter
    row positions never drift.
    """
    target = str(path.resolve())
    content: list[bytes] = []
    line_map: list[int] = []
    cur = 1
    in_target = True
    for raw in out.split(b"\n"):
        m = _LINEMARKER.match(raw)
        if m is not None:
            cur = int(m.group(1))
            in_target = _decode_marker_path(m.group(2)) == target
            continue
        content.append(raw)
        line_map.append(cur if in_target else 0)
        cur += 1
    return b"\n".join(content), line_map


def _cpp_preprocess(path: Path) -> tuple[bytes, list[int] | None]:
    """Run cpp on a capital-F Fortran file, returning (source, line_map).

    line_map[i] is the 1-based original source line for the i-th (0-based) line of
    the returned bytes, so a symbol's `source_location` survives the preprocessor's
    line renumbering (#2092). Returns (raw_bytes, None) — meaning "no remapping,
    line N is line N" — when cpp is unavailable or fails, matching the raw-bytes
    fallback used for lowercase .f90 files. Capital-F extensions conventionally
    require C preprocessor expansion (#ifdef MPI, #define REAL8, etc.) before parsing.

    We run WITHOUT `-P`: `-P` suppresses the linemarkers, and because cpp blanks
    directive lines, drops inactive #ifdef blocks, and collapses blank runs, its
    output line numbers then no longer match the source and there is nothing left to
    map them back — so every symbol was reported at the wrong line (#2092). Keeping
    the linemarkers lets us translate each location back to the original file.

    Security (F-007): we pass `-nostdinc` and `-I /dev/null` so a malicious
    source file containing `#include "/home/victim/.ssh/id_rsa"` (or any other
    include directive) cannot inline arbitrary host files into the output that
    we then ship to an LLM. Without these flags `cpp` happily resolves any
    relative or absolute include path it can read, which is a corpus-side
    file-exfiltration vector.
    """
    import shutil
    import subprocess
    if not shutil.which("cpp"):
        return path.read_bytes(), None
    try:
        # Pass an absolute path so a corpus file named like "-I/etc/x.F90" cannot
        # be parsed by cpp as an option (cpp does not accept a "--" end-of-options
        # terminator). An absolute path always begins with "/".
        result = subprocess.run(
            ["cpp", "-w", "-nostdinc", "-I", "/dev/null", str(path.resolve())],
            capture_output=True,
            timeout=30,
        )
        if result.returncode == 0 and result.stdout:
            return _strip_linemarkers(result.stdout, path)
    except Exception:
        pass
    return path.read_bytes(), None

def extract_fortran(path: Path) -> dict:
    """Extract programs, modules, subroutines, functions, use statements, and calls from Fortran files.

    Capital-F extensions (.F, .F90, etc.) are run through the C preprocessor before
    parsing so #ifdef/#define macros are resolved.
    """
    try:
        import tree_sitter_fortran as tsfortran
        from tree_sitter import Language, Parser
    except ImportError:
        return {"nodes": [], "edges": [], "error": "tree-sitter-fortran not installed"}

    try:
        language = Language(tsfortran.language())
        parser = Parser(language)
        if path.suffix in _FORTRAN_CPP_EXTS:
            source, line_map = _cpp_preprocess(path)
        else:
            source, line_map = path.read_bytes(), None
        tree = parser.parse(source)
        root = tree.root_node
    except Exception as e:
        return {"nodes": [], "edges": [], "error": str(e)}

    stem = _file_stem(path)
    str_path = str(path)
    nodes: list[dict] = []
    edges: list[dict] = []
    seen_ids: set[str] = set()
    scope_bodies: list[tuple[str, object]] = []

    def _orig_line(line: int) -> int:
        """Translate a 1-based preprocessed line to its original source line (#2092).

        No-op when the source was not preprocessed (line_map is None); falls back to
        the preprocessed line for rows outside the map or in an untrusted region.
        """
        if line_map is None:
            return line
        idx = line - 1
        if 0 <= idx < len(line_map) and line_map[idx] >= 1:
            return line_map[idx]
        return line

    def add_node(nid: str, label: str, line: int) -> None:
        if nid not in seen_ids:
            seen_ids.add(nid)
            nodes.append({
                "id": nid,
                "label": label,
                "file_type": "code",
                "source_file": str_path,
                "source_location": f"L{_orig_line(line)}",
            })

    def add_edge(src: str, tgt: str, relation: str, line: int,
                 confidence: str = "EXTRACTED", weight: float = 1.0,
                 context: str | None = None) -> None:
        edge = {
            "source": src,
            "target": tgt,
            "relation": relation,
            "confidence": confidence,
            "source_file": str_path,
            "source_location": f"L{_orig_line(line)}",
            "weight": weight,
        }
        if context:
            edge["context"] = context
        edges.append(edge)

    file_nid = _make_id(str(path))
    add_node(file_nid, path.name, 1)

    def _fortran_name(stmt_node) -> str | None:
        """Extract name from a *_statement node. Fortran is case-insensitive; lowercase."""
        for child in stmt_node.children:
            if child.type in ("name", "identifier"):
                return _read_text(child, source).lower()
        return None

    def ensure_named_node(name: str, line: int) -> str:
        nid = _make_id(stem, name)
        if nid in seen_ids:
            return nid
        nid = _make_id(name)
        if nid not in seen_ids:
            # The name isn't defined in this file, so this is a cross-file reference
            # (e.g. a `Thing` type annotation imported from another module). Emit a
            # SOURCELESS stub — like the inheritance-base path below — so the
            # corpus-level rewire can collapse it onto the real definition. A sourced
            # stub here makes _disambiguate_colliding_node_ids bake the referencing
            # file's path (with extension) into the id and blocks the rewire, which is
            # the phantom-duplicate-node bug (#1402).
            seen_ids.add(nid)
            nodes.append({
                "id": nid,
                "label": name,
                "file_type": "code",
                "source_file": "",
                "source_location": "",
                "origin_file": str_path,
            })
        return nid

    def emit_signature_refs(scope_node, fn_nid: str, is_function: bool) -> None:
        """Emit references[parameter_type] / references[return_type] edges for
        a subroutine/function based on its variable_declaration siblings."""
        stmt_type = "function_statement" if is_function else "subroutine_statement"
        stmt = next((c for c in scope_node.children if c.type == stmt_type), None)
        if stmt is None:
            return
        param_names: set[str] = set()
        params_node = next((c for c in stmt.children if c.type == "parameters"), None)
        if params_node is not None:
            for c in params_node.children:
                if c.type == "identifier":
                    param_names.add(_read_text(c, source).lower())
        result_name: str | None = None
        if is_function:
            result_node = next((c for c in stmt.children if c.type == "function_result"), None)
            if result_node is not None:
                res_id = next((c for c in result_node.children if c.type == "identifier"), None)
                if res_id is not None:
                    result_name = _read_text(res_id, source).lower()
            else:
                # implicit result variable: same name as the function
                result_name = _fortran_name(stmt)
        for child in scope_node.children:
            if child.type != "variable_declaration":
                continue
            derived = next((c for c in child.children if c.type == "derived_type"), None)
            if derived is None:
                continue
            type_name_node = next((c for c in derived.children if c.type == "type_name"), None)
            if type_name_node is None:
                continue
            type_name = _read_text(type_name_node, source).lower()
            for var in child.children:
                if var.type != "identifier":
                    continue
                var_name = _read_text(var, source).lower()
                var_line = var.start_point[0] + 1
                if var_name in param_names:
                    tgt = ensure_named_node(type_name, var_line)
                    if tgt != fn_nid:
                        add_edge(fn_nid, tgt, "references", var_line, context="parameter_type")
                elif is_function and var_name == result_name:
                    tgt = ensure_named_node(type_name, var_line)
                    if tgt != fn_nid:
                        add_edge(fn_nid, tgt, "references", var_line, context="return_type")

    def walk_calls(node, scope_nid: str) -> None:
        if node is None:
            return
        t = node.type
        if t in ("subroutine", "function", "module", "program", "internal_procedures"):
            return
        # call FOO(args) — tree-sitter-fortran uses subroutine_call
        if t == "subroutine_call":
            name_node = next((c for c in node.children if c.type == "identifier"), None)
            if name_node:
                callee = _read_text(name_node, source).lower()
                target_nid = _make_id(stem, callee)
                add_edge(scope_nid, target_nid, "calls", node.start_point[0] + 1,
                         confidence="EXTRACTED", context="call")
        # x = compute(args) — function invocations are `call_expression`, which
        # shares Fortran's `name(...)` syntax with array indexing. Only emit a
        # call edge when the callee resolves to a procedure defined in this file
        # (an array variable produces no matching node), so array accesses can't
        # fabricate spurious `calls` edges.
        elif t == "call_expression":
            name_node = next((c for c in node.children if c.type == "identifier"), None)
            if name_node:
                callee = _read_text(name_node, source).lower()
                target_nid = _make_id(stem, callee)
                if target_nid in seen_ids and target_nid != scope_nid:
                    add_edge(scope_nid, target_nid, "calls", node.start_point[0] + 1,
                             confidence="EXTRACTED", context="call")
        for child in node.children:
            walk_calls(child, scope_nid)

    def walk(node, scope_nid: str) -> None:
        t = node.type

        if t == "program":
            stmt = next((c for c in node.children if c.type == "program_statement"), None)
            name = _fortran_name(stmt) if stmt else None
            if name:
                nid = _make_id(stem, name)
                line = node.start_point[0] + 1
                add_node(nid, name, line)
                add_edge(file_nid, nid, "defines", line)
                scope_bodies.append((nid, node))
                for child in node.children:
                    walk(child, nid)
            return

        if t == "module":
            stmt = next((c for c in node.children if c.type == "module_statement"), None)
            name = _fortran_name(stmt) if stmt else None
            if name:
                nid = _make_id(stem, name)
                line = node.start_point[0] + 1
                add_node(nid, name, line)
                add_edge(file_nid, nid, "defines", line)
                for child in node.children:
                    walk(child, nid)
            return

        # subroutines/functions inside a module live under internal_procedures
        if t == "internal_procedures":
            for child in node.children:
                walk(child, scope_nid)
            return

        if t == "derived_type_definition":
            stmt = next((c for c in node.children if c.type == "derived_type_statement"), None)
            if stmt is not None:
                name_node = next((c for c in stmt.children if c.type == "type_name"), None)
                if name_node is not None:
                    type_name = _read_text(name_node, source).lower()
                    type_nid = _make_id(stem, type_name)
                    line = node.start_point[0] + 1
                    add_node(type_nid, type_name, line)
                    add_edge(scope_nid, type_nid, "defines", line)
            return

        if t == "subroutine":
            stmt = next((c for c in node.children if c.type == "subroutine_statement"), None)
            name = _fortran_name(stmt) if stmt else None
            if name:
                nid = _make_id(stem, name)
                line = node.start_point[0] + 1
                add_node(nid, f"{name}()", line)
                add_edge(scope_nid, nid, "defines", line)
                scope_bodies.append((nid, node))
                emit_signature_refs(node, nid, is_function=False)
                for child in node.children:
                    walk(child, nid)
            return

        if t == "function":
            stmt = next((c for c in node.children if c.type == "function_statement"), None)
            name = _fortran_name(stmt) if stmt else None
            if name:
                nid = _make_id(stem, name)
                line = node.start_point[0] + 1
                add_node(nid, f"{name}()", line)
                add_edge(scope_nid, nid, "defines", line)
                scope_bodies.append((nid, node))
                emit_signature_refs(node, nid, is_function=True)
                for child in node.children:
                    walk(child, nid)
            return

        if t == "use_statement":
            line = node.start_point[0] + 1
            # tree-sitter-fortran uses module_name node for the used module
            name_node = next((c for c in node.children if c.type in ("module_name", "name", "identifier")), None)
            if name_node:
                mod_name = _read_text(name_node, source).lower()
                imp_nid = _make_id(mod_name)
                add_node(imp_nid, mod_name, line)
                add_edge(scope_nid, imp_nid, "imports", line, context="use")
            return

        for child in node.children:
            walk(child, scope_nid)

    walk(root, file_nid)

    _stmt_headers = {
        "subroutine_statement", "function_statement",
        "program_statement", "module_statement",
    }
    for scope_nid, body_node in scope_bodies:
        for child in body_node.children:
            if child.type not in _stmt_headers:
                walk_calls(child, scope_nid)

    return {"nodes": nodes, "edges": edges}
