"""Robot Framework extractor for .robot/.resource files (issue #3192)."""
from __future__ import annotations

import os

from pathlib import Path
from graphify.extractors.base import _file_stem, _make_id


# Robot Framework standard libraries - imports of these are noise (like the
# Python built-ins in _LANGUAGE_BUILTIN_GLOBALS), so only third-party
# libraries get stub nodes.
_ROBOT_STDLIBS = frozenset({
    "BuiltIn", "Collections", "DateTime", "Dialogs", "Easter", "OperatingSystem",
    "Process", "Remote", "Reserved", "Screenshot", "String", "Telnet", "XML",
})


def _resolve_robot_import(raw: str, source_path: Path) -> Path | None:
    """Resolve a Settings-section import path relative to the importing file.

    Preserves the relative/absolute form of source_path so the target ID
    matches the ID the imported file's own extraction produces (same approach
    as the JS relative-import resolver). Returns None when unresolvable
    ${VARIABLES} remain in the path.
    """
    s = raw.strip().replace("${/}", "/")
    s = s.replace("${CURDIR}", str(source_path.parent))
    s = s.replace("${EXECDIR}", ".")
    if "${" in s or "%{" in s:
        return None
    p = Path(s)
    if not p.is_absolute():
        p = Path(os.path.normpath(source_path.parent / p))
    return p


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

    Keyword nodes are keyed by bare keyword name (not stem-qualified): Robot
    resolves keywords globally by name across imported resources, so bare IDs
    make cross-file call edges land on the defining node without a separate
    resolution pass. Test case nodes stay stem-qualified because test names
    repeat across suites. Calls to keywords never defined in the corpus (e.g.
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

    def kw_target(name: str) -> str:
        # "SSHLibrary.Open Connection" -> keyword part only; explicit
        # library/resource prefixes are common, dots inside keyword names are not.
        return _make_id(name.rsplit(".", 1)[-1])

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
                nid = _make_id(raw)
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
                add_edge(file_nid, kw_target(node.name), "calls", node.lineno,
                         context="call")

        def visit_SuiteTeardown(self, node):
            if node.name:
                add_edge(file_nid, kw_target(node.name), "calls", node.lineno,
                         context="call")

        def visit_TestSetup(self, node):
            if node.name:
                add_edge(file_nid, kw_target(node.name), "calls", node.lineno,
                         context="call")

        def visit_TestTeardown(self, node):
            if node.name:
                add_edge(file_nid, kw_target(node.name), "calls", node.lineno,
                         context="call")

        def visit_TestTemplate(self, node):
            # Template statements carry the keyword in .value, not .name
            if node.value:
                add_edge(file_nid, kw_target(node.value), "calls", node.lineno,
                         context="call")

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
            kw_nid = _make_id(node.name)
            add_node(kw_nid, node.name, node.lineno)
            add_edge(file_nid, kw_nid, "contains", node.lineno)
            prev, self.scope_nid = self.scope_nid, kw_nid
            self.generic_visit(node)
            self.scope_nid = prev

        # Calls (current test/keyword scope, file scope for suite fixtures)
        def visit_KeywordCall(self, node):
            if node.keyword:
                add_edge(self.scope_nid, kw_target(node.keyword), "calls",
                         node.lineno, context="call")
            self.generic_visit(node)

        def visit_Setup(self, node):
            if node.name:
                add_edge(self.scope_nid, kw_target(node.name), "calls",
                         node.lineno, context="call")

        def visit_Teardown(self, node):
            if node.name:
                add_edge(self.scope_nid, kw_target(node.name), "calls",
                         node.lineno, context="call")

        def visit_Template(self, node):
            # Template statements carry the keyword in .value, not .name
            if node.value:
                add_edge(self.scope_nid, kw_target(node.value), "calls",
                         node.lineno, context="call")

    try:
        _RobotVisitor().visit(model)
    except Exception as e:
        return {"nodes": nodes, "edges": edges, "error": str(e)}

    return {"nodes": nodes, "edges": edges}
