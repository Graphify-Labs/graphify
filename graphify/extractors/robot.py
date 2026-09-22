"""Robot Framework extractor for .robot/.resource files (issue #3192)."""
from __future__ import annotations

import os
import re

from pathlib import Path
from graphify.extractors.base import _file_stem, _make_id


# Robot Framework standard libraries - imports of these are noise (like the
# Python built-ins in _LANGUAGE_BUILTIN_GLOBALS), so only third-party
# libraries get stub nodes.
_ROBOT_STDLIBS = frozenset({
    "BuiltIn", "Collections", "DateTime", "Dialogs", "Easter", "OperatingSystem",
    "Process", "Remote", "Reserved", "Screenshot", "String", "Telnet", "XML",
})


_ROBOT_VAR_RE = re.compile(r"\$\{([^}]*)\}")


def _resolve_robot_import(raw: str, source_path: Path) -> Path | None:
    """Resolve a Settings-section import path relative to the importing file.

    Preserves the relative/absolute form of source_path so the target ID
    matches the ID the imported file's own extraction produces (same approach
    as the JS relative-import resolver). Robot matches variable names case-,
    space-, and underscore-insensitively, so ``${curdir}`` and ``${Cur_Dir}``
    resolve like ``${CURDIR}``. Returns None when the path holds any other
    (unresolvable) ${VARIABLE} or %{ENV_VAR}.
    """
    s = raw.strip()
    # ${CURDIR}/${EXECDIR} already anchor the path - substituting and then
    # re-joining below would prefix source_path.parent twice when the scan
    # uses relative paths, so track anchoring explicitly.
    anchored = False
    parts = []
    last = 0
    for m in _ROBOT_VAR_RE.finditer(s):
        name = m.group(1).replace(" ", "").replace("_", "").lower()
        if name == "/":
            repl = "/"
        elif name == "curdir":
            repl = str(source_path.parent)
            anchored = True
        elif name == "execdir":
            # ${EXECDIR} is the directory Robot was launched from - statically
            # knowable only for a relative scan, where "." is the scan root
            # and matches how relative file-node IDs are built. For an
            # absolute source path the resolved ID could never match a node,
            # so emit nothing rather than a guaranteed-dangling edge.
            if source_path.is_absolute():
                return None
            repl = "."
            anchored = True
        else:
            return None
        parts.append(s[last:m.start()])
        parts.append(repl)
        last = m.end()
    parts.append(s[last:])
    s = "".join(parts)
    if "%{" in s:
        return None
    p = Path(s)
    if not anchored and not p.is_absolute():
        p = source_path.parent / p
    # normpath unconditionally so ../ segments collapse and the ID matches
    # the imported file's own node ID (absolute paths included)
    return Path(os.path.normpath(p))


# Robot resolves BDD-style calls (Given/When/Then/And/But <keyword>) by trying
# the full name first, then the name with one prefix stripped. English prefixes
# only - Robot's localized BDD prefixes are out of scope here.
_BDD_PREFIXES = ("given ", "when ", "then ", "and ", "but ")


def _kw_id(name: str) -> str:
    """Node ID for a keyword, normalized the way Robot Framework matches
    keyword names: case-, space-, and underscore-insensitive. Stripping
    spaces/underscores before _make_id means ``Open Session``,
    ``open_session``, and ``OpenSession`` all share one node ID, exactly as
    Robot resolves them to one keyword."""
    return _make_id(name.replace(" ", "").replace("_", ""))


def extract_robot(path: Path) -> dict:
    """Extract suites, test cases, user keywords, imports, and keyword calls
    from Robot Framework .robot/.resource files via the official robot.api
    parser (no maintained tree-sitter grammar exists for Robot Framework).

    Nodes: the suite/resource file, its test cases, and its user keywords.
    Edges: `contains` (file -> test case / keyword), `imports` (file -> the
    Resource/Library/Variables files it pulls in, resolved onto the imported
    file's own node; non-stdlib named libraries like SeleniumLibrary get stub
    nodes so suites sharing a library cluster together), and `calls`
    (test case / keyword / suite fixture -> the keyword it invokes).

    Keyword nodes are keyed by bare keyword name (not stem-qualified),
    normalized the way Robot matches keywords (case-, space-, and
    underscore-insensitive, see _kw_id): Robot resolves keywords globally by
    name across imported resources, so bare IDs make cross-file call edges
    land on the defining node without a separate resolution pass. Two files
    defining the same keyword name deliberately merge into one node - that
    mirrors Robot's own single global namespace (where such duplicates are
    ambiguous). Test case nodes stay stem-qualified because test names repeat
    across suites. Calls to keywords never defined in the corpus (e.g.
    BuiltIn's Log) are dropped by build_from_json like any external reference.
    """
    try:
        from robot.api import get_model, get_resource_model
        from robot.api.parsing import ModelVisitor
    except ImportError:
        return {"nodes": [], "edges": [],
                "error": "robotframework not installed. Run: pip install robotframework"}

    stem = _file_stem(path)
    str_path = str(path)
    nodes: list[dict] = []
    edges: list[dict] = []
    seen_ids: set[str] = set()
    seen_edges: set[tuple] = set()

    def add_node(nid: str, label: str, line: int) -> None:
        if nid not in seen_ids:
            seen_ids.add(nid)
            nodes.append({
                "id": nid,
                "label": label,
                "file_type": "code",
                "source_file": str_path,
                "source_location": f"L{line}",
            })

    def add_edge(src: str, tgt: str, relation: str, line: int,
                 confidence: str = "EXTRACTED", context: str | None = None) -> None:
        if not src or not tgt or src == tgt:
            return
        key = (src, tgt, relation)
        if key in seen_edges:
            return
        seen_edges.add(key)
        edge = {
            "source": src,
            "target": tgt,
            "relation": relation,
            "confidence": confidence,
            "source_file": str_path,
            "source_location": f"L{line}",
            "weight": 1.0,
        }
        if context:
            edge["context"] = context
        edges.append(edge)

    file_nid = _make_id(str_path)
    add_node(file_nid, path.name, 1)

    try:
        if path.suffix.lower() == ".resource":
            model = get_resource_model(str_path)
        else:
            model = get_model(str_path)
    except Exception as e:
        return {"nodes": nodes, "edges": edges, "error": str(e)}

    def kw_targets(name: str) -> list:
        # "SSHLibrary.Open Connection" -> keyword part only; explicit
        # library/resource prefixes are common, dots inside keyword names are not.
        name = name.rsplit(".", 1)[-1].strip()
        targets = [_kw_id(name)]
        # BDD calls: emit an edge for BOTH the full and the prefix-stripped
        # candidate, mirroring Robot's try-full-then-stripped resolution.
        # Whichever keyword exists receives the edge; the other candidate
        # dangles and is dropped by the graph builder.
        low = name.lower()
        for prefix in _BDD_PREFIXES:
            if low.startswith(prefix) and len(name) > len(prefix):
                targets.append(_kw_id(name[len(prefix):]))
                break
        return targets

    def add_call_edges(src: str, name: str, line: int) -> None:
        for tgt in kw_targets(name):
            add_edge(src, tgt, "calls", line, context="call")

    class _RobotVisitor(ModelVisitor):
        def __init__(self):
            self.scope_nid = file_nid

        # Settings-section imports
        def visit_ResourceImport(self, node):
            raw = (node.name or "").strip()
            if not raw:
                return
            target = _resolve_robot_import(raw, path)
            if target is not None:
                add_edge(file_nid, _make_id(str(target)), "imports", node.lineno)

        def visit_LibraryImport(self, node):
            raw = (node.name or "").strip()
            if not raw:
                return
            if raw.endswith(".py") or "/" in raw or "\\" in raw:
                # Path-form library import -> edge onto the Python file's node
                target = _resolve_robot_import(raw, path)
                if target is not None:
                    add_edge(file_nid, _make_id(str(target)), "imports", node.lineno)
            elif raw not in _ROBOT_STDLIBS:
                # External library (SeleniumLibrary, RequestsLibrary, ...) -
                # stub node so suites sharing a library cluster together.
                # Namespace the id so a user keyword that happens to share the
                # library's name cannot collide with this stub (the label keeps
                # the raw library name for display).
                nid = _make_id("robot_library", raw)
                add_node(nid, raw, node.lineno)
                add_edge(file_nid, nid, "imports", node.lineno)

        def visit_VariablesImport(self, node):
            raw = (node.name or "").strip()
            if not raw:
                return
            target = _resolve_robot_import(raw, path)
            if target is not None:
                add_edge(file_nid, _make_id(str(target)), "imports", node.lineno)

        # Suite-level fixtures (file scope)
        def visit_SuiteSetup(self, node):
            if node.name:
                add_call_edges(file_nid, node.name, node.lineno)

        def visit_SuiteTeardown(self, node):
            if node.name:
                add_call_edges(file_nid, node.name, node.lineno)

        def visit_TestSetup(self, node):
            if node.name:
                add_call_edges(file_nid, node.name, node.lineno)

        def visit_TestTeardown(self, node):
            if node.name:
                add_call_edges(file_nid, node.name, node.lineno)

        def visit_TestTemplate(self, node):
            # Template statements carry the keyword in .value, not .name
            if node.value:
                add_call_edges(file_nid, node.value, node.lineno)

        # Definitions
        def visit_TestCase(self, node):
            if not node.name:
                return
            tc_nid = _make_id(stem, node.name)
            add_node(tc_nid, node.name, node.lineno)
            add_edge(file_nid, tc_nid, "contains", node.lineno)
            prev, self.scope_nid = self.scope_nid, tc_nid
            self.generic_visit(node)
            self.scope_nid = prev

        def visit_Keyword(self, node):
            if not node.name:
                return
            kw_nid = _kw_id(node.name)
            add_node(kw_nid, node.name, node.lineno)
            add_edge(file_nid, kw_nid, "contains", node.lineno)
            prev, self.scope_nid = self.scope_nid, kw_nid
            self.generic_visit(node)
            self.scope_nid = prev

        # Calls (current test/keyword scope, file scope for suite fixtures)
        def visit_KeywordCall(self, node):
            if node.keyword:
                add_call_edges(self.scope_nid, node.keyword, node.lineno)
            self.generic_visit(node)

        def visit_Setup(self, node):
            if node.name:
                add_call_edges(self.scope_nid, node.name, node.lineno)

        def visit_Teardown(self, node):
            if node.name:
                add_call_edges(self.scope_nid, node.name, node.lineno)

        def visit_Template(self, node):
            # Template statements carry the keyword in .value, not .name
            if node.value:
                add_call_edges(self.scope_nid, node.value, node.lineno)

    try:
        _RobotVisitor().visit(model)
    except Exception as e:
        return {"nodes": nodes, "edges": edges, "error": str(e)}

    return {"nodes": nodes, "edges": edges}
