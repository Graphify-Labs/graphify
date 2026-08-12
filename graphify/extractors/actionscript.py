"""ActionScript 3 extractor (Adobe Flex / AIR / Apache Royale).

Regex-based, in the style of ``dart.py`` and ``pascal.py``. ActionScript has no
usable tree-sitter grammar — the two that exist on GitHub are unmaintained, and
one of them targets decompiler output rather than source — so the AST path other
languages take is not available here.

Two design points carry most of the value:

**Node IDs converge on the defining file.** ActionScript requires the package
path to mirror the directory layout, so ``classes.utils.Tools`` can be resolved
to ``<root>/classes/utils/Tools.as`` and the import edge pointed at that file's
own node. Definition site and reference site therefore meet on one node instead
of producing two orphans. Types that resolve to no file in the corpus (``flash.*``,
``mx.*``, and the rest of the SDK) stay as bare fully-qualified concept nodes.

**Bare type names are resolved through the file's own import table.** AS3 demands
an explicit import for anything outside the current package, which makes
``extends EventDispatcher`` -> ``flash.events.EventDispatcher`` a reliable lookup
rather than a guess. Names that resolve to nothing fall back to the current
package, which is exactly AS3's own resolution order.

**Events are keyed by value, not by name.** Flex couples components through
string constants, and that traffic is invisible to the import graph. Dispatch
sites tend to write the literal while listen sites write the constant, so both
are reduced to the literal value — see :func:`_string_constants`.

The approximation this makes is worth stating: two unrelated subsystems that
happen to reuse a literal (``'OK'``) collapse onto one event node, because the
extractor keys on the string alone and not on which object the listener was
attached to. Deciding that needs dataflow. In practice the string *is* the
contract in Flex, so the collapse is usually the intended reading — but an event
node is a navigational hint, not proof that two sites are connected.

Node identity follows the two rules graphify's own passes require: a symbol that
resolves to a file in the corpus is attributed to the file that *defines* it, and
a shared entity with no defining file (an SDK type, an event, a singleton) is
marked ``type: "module"`` so ``_disambiguate_colliding_node_ids`` leaves it
alone. Without both, one event dispatched from N files becomes N nodes.
"""
from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

from graphify.extractors.base import _make_id

# ── Lexical pre-pass ─────────────────────────────────────────────────────────

# Comments are *blanked*, not deleted, so byte offsets — and therefore every
# line number reported on a node or edge — stay identical to the raw source.
# String literals are preserved verbatim: `@Embed(source='…')` asset paths and
# the string constants carrying Flex's event wiring both live inside them.
_COMMENT_OR_STRING_RE = re.compile(
    r'"(?:\\.|[^"\\])*"'
    r"|'(?:\\.|[^'\\])*'"
    r"|/\*[\s\S]*?\*/"
    r"|//[^\n]*"
)


def _blank_comments(src: str) -> str:
    def repl(m: re.Match) -> str:
        token = m.group(0)
        if token[0] in "\"'":
            return token
        return "".join("\n" if ch == "\n" else " " for ch in token)

    return _COMMENT_OR_STRING_RE.sub(repl, src)


# ── Declaration patterns ─────────────────────────────────────────────────────

# `package classes.payment.country` — may also be the bare `package` of the
# default package used by an application's root file, hence the `*` quantifier.
_PACKAGE_RE = re.compile(r"\bpackage\s+([\w.]*)")

# Import lines vary only by whitespace across this corpus (the same symbol shows
# up under several spacings), so the captured group is normalised by the regex
# itself rather than deduplicated later.
_IMPORT_RE = re.compile(r"^[ \t]*import\s+([\w.$]+(?:\.\*)?)\s*;", re.MULTILINE)

# Brace placement is inconsistent in this codebase (`class X {` and a brace on
# the following line both occur), so the trailing `\s*\{` spans newlines.
_CLASS_RE = re.compile(
    r"\b(?:public\s+|internal\s+|final\s+|dynamic\s+)*class\s+(\w+)"
    r"(?:\s+extends\s+([\w.]+))?"
    r"(?:\s+implements\s+([\w.,\s]+?))?"
    r"\s*\{"
)

# Interfaces may extend several interfaces at once (`ISetupService extends
# IEventDispatcher`), so the extends clause is a list like `implements`.
_INTERFACE_RE = re.compile(
    r"\b(?:public\s+|internal\s+)*interface\s+(\w+)"
    r"(?:\s+extends\s+([\w.,\s]+?))?"
    r"\s*\{"
)

# Named functions only — an anonymous `function (…)` has no name to bind to.
# Getters and setters are captured under their property name.
_FUNCTION_RE = re.compile(r"\bfunction\s+(?:(?:get|set)\s+)?(\w+)\s*\(")

# Constructor calls. The leading-capital rule is how AS3 code is written and it
# keeps `new` on non-types out of the graph.
_NEW_RE = re.compile(r"\bnew\s+([A-Z][\w.]*)\s*\(")

# Class-level metadata: [Bindable], [Embed(source='…')], [ResourceBundle("bundle")].
_METADATA_RE = re.compile(r"^[ \t]*\[(\w+)\s*(?:\(([^\]]*)\))?\]", re.MULTILINE)
_EMBED_SOURCE_RE = re.compile(r"source\s*=\s*['\"]([^'\"]+)['\"]")
_FIRST_STRING_RE = re.compile(r"['\"]([^'\"]+)['\"]")

# Types that are never imported because they are language-level. Without this
# filter they become god-nodes accumulating an edge from nearly every file —
# the same concern `base.py` documents for its own builtin-globals list.
_AS3_BUILTINS = frozenset({
    "Object", "String", "Number", "Boolean", "Array", "int", "uint", "void",
    "Function", "Class", "Error", "Date", "RegExp", "Math", "JSON",
    "XML", "XMLList", "Vector", "Namespace", "QName", "Arguments",
    "ArgumentError", "DefinitionError", "EvalError", "RangeError",
    "ReferenceError", "SecurityError", "SyntaxError", "TypeError",
    "URIError", "VerifyError",
})

# `mx.core.FlexGlobals` is a static accessor for the application singleton,
# imported by any file that touches it. As an import target it says nothing that
# the `uses_global` edges do not say more precisely, while as a node it is a hub
# joining every unrelated file that reaches the application — enough to make
# `graphify path` route most questions through it. The usage itself is still
# recorded; only the redundant import edge is dropped.
_REDUNDANT_IMPORTS = frozenset({"mx.core.FlexGlobals"})



# ── Edge arbitration ─────────────────────────────────────────────────────────

# graphify builds a non-multigraph: one pair of nodes holds exactly one edge
# (`G.add_edge` in build.py overwrites). A class that is both imported and
# subclassed therefore cannot keep both facts, and whichever edge the build
# happens to add last wins. Deciding here instead keeps the informative relation
# and makes the extracted counts honest, rather than reporting edges that the
# build will silently drop. `imports` ranks last on purpose: it is implied by
# every other relation to the same target.
_RELATION_PRIORITY = {
    "inherits": 0, "implements": 1, "renders": 2, "includes": 3,
    "relays": 4, "declares_event": 5, "dispatches": 6, "listens": 7,
    "instantiates": 8, "uses_global": 9, "embeds": 10, "references_i18n": 11,
    "declares_state": 12, "references": 13, "contains": 14, "imports": 15,
}

# A component that both emits an event and subscribes to it is *relaying* it —
# the common shape for a manager that lifts its delegates' events up to the
# application. Arbitrating between the two halves would drop one of them and
# report a dispatcher with no listener, so the pair becomes a single relation
# that states more than either half alone.
_RELAY = frozenset({"dispatches", "listens"})


def _collapse_edges(edges: list[dict]) -> list[dict]:
    """Keep one edge per (source, target): the most specific relation."""
    grouped: dict[tuple[str, str], list[dict]] = {}
    order: list[tuple[str, str]] = []
    for edge in edges:
        key = (edge["source"], edge["target"])
        if key not in grouped:
            grouped[key] = []
            order.append(key)
        grouped[key].append(edge)

    collapsed: list[dict] = []
    for key in order:
        group = grouped[key]
        if _RELAY <= {edge["relation"] for edge in group}:
            halves = [edge for edge in group if edge["relation"] in _RELAY]
            relay = dict(halves[0])
            relay["relation"] = "relays"
            relay["weight"] = sum(edge.get("weight", 1.0) for edge in halves)
            collapsed.append(relay)
            continue
        collapsed.append(
            min(group, key=lambda e: _RELATION_PRIORITY.get(e["relation"], 99))
        )
    return collapsed


# ── Event wiring ─────────────────────────────────────────────────────────────

# Flex couples components by *string*, not by type: a class publishes
# `public static const X:String = 'some-event'` and everyone else dispatches or
# listens for it. None of that traffic appears in the import graph, and it is
# where this application's real control flow lives.
_STATIC_CONST_RE = re.compile(
    r"\bstatic\s+const\s+(\w+)\s*:\s*String\s*=\s*(['\"])([^'\"]*)\2"
)
_DISPATCH_RE = re.compile(r"\bdispatchEvent\s*\(\s*new\s+(\w+)\s*\(\s*([^,)]+)")
_LISTEN_RE = re.compile(r"\baddEventListener\s*\(\s*([^,]+?)\s*,\s*([\w.]+)")
_EVENT_META_RE = re.compile(
    r'name\s*=\s*["\'](\w+)["\']\s*,\s*type\s*=\s*["\']([\w.]+)["\']'
)

# `FlexGlobals.topLevelApplication.<name>` reaches the application singleton
# directly. These are edges to the root component that no import records.
_FLEXGLOBALS_RE = re.compile(r"\bFlexGlobals\.topLevelApplication\.(\w+)")

# Properties of the Flex Application class itself. They say nothing about this
# application's own structure, and `currentState` alone would otherwise be a
# god node wired to a third of the codebase.
_FLEX_APPLICATION_MEMBERS = frozenset({
    "currentState", "states", "systemManager", "parameters", "stage",
    "nativeWindow", "nativeApplication", "applicationDPI", "pageTitle",
    "preloader", "resourceManager", "styleManager", "loaderInfo", "root",
    "width", "height", "visible", "enabled", "addEventListener",
    "removeEventListener", "dispatchEvent",
})


@lru_cache(maxsize=1024)
def _string_constants(file_path: str) -> tuple[tuple[str, str], ...]:
    """`NAME -> literal` for the String constants a file declares.

    Read across files on purpose. The dispatch side of this codebase is mostly
    literals (`new Event('service-loaded')`) while the listen side is mostly
    qualified constants (`RfidTags.SERVICE_RFIDTAGS_LOADED`), so keying events on
    the constant *name* would leave the two halves in separate nodes. Resolving
    the constant to its value makes them meet. Reads are bounded — one file per
    distinct qualifier — and cached for the life of the worker process, the same
    latitude ``dart.py`` takes when it follows a ``part of`` to its parent.
    """
    try:
        text = Path(file_path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ()
    return tuple(
        (match.group(1), match.group(3))
        for match in _STATIC_CONST_RE.finditer(_blank_comments(text))
    )


# ── Name resolution ──────────────────────────────────────────────────────────


def _source_root(path: Path, package: str) -> Path:
    """Derive the source root from the file's own package declaration.

    ``<root>/com/example/net/HttpClient.as`` declaring
    ``package com.example.net`` yields ``<root>``. This is what lets the
    extractor resolve a fully-qualified name back to a real file without being
    told where the project root is — the per-file extractor contract passes only
    the path.
    """
    root = path.parent
    for _ in [part for part in package.split(".") if part]:
        root = root.parent
    return root


def _resolve_to_file(root: Path, fqn: str) -> str:
    """Map a fully-qualified name to its defining file, or keep it as a concept.

    Returning the real path makes the reference share the *file node's* ID, so
    an import and the class declaration it points at converge on one node. This
    mirrors what ``twig.py`` does for template paths, and matters for the same
    reason: without it every import would mint an orphan.
    """
    relative = fqn.replace(".", "/")
    for extension in (".as", ".mxml"):
        candidate = root / (relative + extension)
        if candidate.is_file():
            return str(candidate)
    return fqn


class _Scope:
    """The import table and package of one file, used to qualify bare names."""

    def __init__(self, package: str, root: Path) -> None:
        self.package = package
        self.root = root
        self.by_simple_name: dict[str, str] = {}
        self.wildcards: list[str] = []

    def add_import(self, fqn: str) -> None:
        if fqn.endswith(".*"):
            self.wildcards.append(fqn[:-2])
        else:
            self.by_simple_name[fqn.rsplit(".", 1)[-1]] = fqn

    def qualify(self, name: str) -> str | None:
        """Resolve a type name as the AS3 compiler would. None = not a type."""
        name = name.strip()
        if not name or name in _AS3_BUILTINS:
            return None
        if "." in name:
            return name
        explicit = self.by_simple_name.get(name)
        if explicit:
            return explicit
        # A wildcard import only counts if it actually resolves to a file;
        # otherwise `import mx.controls.*` would claim every unknown name.
        for package in self.wildcards:
            candidate = f"{package}.{name}"
            if _resolve_to_file(self.root, candidate) != candidate:
                return candidate
        # Same-package types need no import — this is AS3's own last resort.
        return f"{self.package}.{name}" if self.package else name


# ── Extraction ───────────────────────────────────────────────────────────────


def extract_actionscript(path: Path) -> dict:
    """Extract packages, imports, types, members and instantiations from a .as file."""
    try:
        raw = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return {"nodes": [], "edges": [], "error": f"cannot read {path}"}

    return extract_actionscript_source(raw, path)


def extract_actionscript_source(
    raw: str,
    path: Path,
    line_offset: int = 0,
    root: Path | None = None,
    package: str | None = None,
) -> dict:
    """Extract from an ActionScript source string.

    Split out from :func:`extract_actionscript` so the MXML extractor can feed it
    the body of an ``<fx:Script><![CDATA[ … ]]></fx:Script>`` block and get the
    same relations, rather than maintaining a second, divergent set of patterns.

    ``line_offset`` is the 0-based line at which ``raw`` starts inside the host
    file, so reported line numbers stay those of the real file. ``root`` and
    ``package`` let a caller impose the scope: an MXML script block carries no
    ``package`` declaration of its own, so without them its imports would be
    resolved against the wrong source root.
    """
    src = _blank_comments(raw)
    str_path = str(path)

    if package is None:
        package_match = _PACKAGE_RE.search(src)
        package = package_match.group(1) if package_match else ""
    if root is None:
        root = _source_root(path, package)
    scope = _Scope(package, root)

    file_nid = _make_id(str_path)
    nodes: list[dict] = [{
        "id": file_nid, "label": path.name, "file_type": "code",
        "source_file": str_path, "source_location": None,
    }]
    edges: list[dict] = []
    seen: set[str] = {file_nid}
    # A property declared as a `get`/`set` pair, or a type instantiated at
    # several call sites, would otherwise emit the same edge repeatedly. They are
    # collapsed onto one edge whose weight counts the occurrences, which is what
    # `weight` is for and keeps edge counts meaningful.
    edge_index: dict[tuple[str, str, str], dict] = {}

    def line_at(offset: int) -> str:
        return f"L{src.count(chr(10), 0, offset) + 1 + line_offset}"

    def add_node(
        nid: str,
        label: str,
        location: str | None,
        file_type: str = "code",
        source_file: str | None = None,
        shared: bool = False,
    ) -> None:
        """Create a node once.

        `source_file` and `shared` both exist to survive graphify's
        `_disambiguate_colliding_node_ids` pass, which salts an id with the
        referencing path as soon as one id carries two different source_files.
        Left unhandled, an event dispatched from fifteen files becomes fifteen
        nodes and the graph stops answering the questions it was built for.

        So a symbol that resolves to a file in the corpus is attributed to the
        file that *defines* it, and an entity with no defining file (an SDK type,
        an event, a singleton) is marked as a module anchor — the exemption
        graphify documents for exactly this case.
        """
        if nid in seen:
            return
        seen.add(nid)
        node = {
            "id": nid, "label": label, "file_type": file_type,
            "source_file": str_path if source_file is None else source_file,
            "source_location": location,
        }
        if shared:
            node["type"] = "module"
        nodes.append(node)

    def add_edge(source: str, target: str, relation: str, location: str) -> None:
        key = (source, target, relation)
        existing = edge_index.get(key)
        if existing is not None:
            existing["weight"] += 1.0
            return
        edge = {
            "source": source, "target": target, "relation": relation,
            "confidence": "EXTRACTED", "confidence_score": 1.0,
            "source_file": str_path, "source_location": location, "weight": 1.0,
        }
        edge_index[key] = edge
        edges.append(edge)

    def reference(fqn: str, relation: str, source_nid: str, offset: int) -> None:
        """Emit an edge to a type, resolving it to its defining file when possible."""
        location = line_at(offset)
        target_key = _resolve_to_file(root, fqn)
        target_nid = _make_id(target_key)
        if not target_nid:
            return
        # A type that resolves to a file gets that file's node, attributed to
        # the file that declares it; one that does not is an SDK/external type,
        # shared by every file that mentions it.
        if target_key != fqn:
            add_node(target_nid, Path(target_key).name, None, source_file=target_key)
        else:
            add_node(target_nid, fqn.rsplit(".", 1)[-1], location, shared=True)
        add_edge(source_nid, target_nid, relation, location)

    # Imports first: everything below resolves bare names through this table.
    for match in _IMPORT_RE.finditer(src):
        scope.add_import(match.group(1))
    for match in _IMPORT_RE.finditer(src):
        fqn = match.group(1)
        if fqn in _REDUNDANT_IMPORTS:
            continue
        if fqn.endswith(".*"):
            # A wildcard names a package, not a type, so it has no file to
            # resolve to — but it is still a declared dependency and is kept as
            # a concept node rather than dropped.
            package_name = fqn[:-2]
            location = line_at(match.start())
            package_nid = _make_id(package_name)
            add_node(package_nid, package_name, location, file_type="concept", shared=True)
            add_edge(file_nid, package_nid, "imports", location)
            continue
        reference(fqn, "imports", file_nid, match.start())

    # Types declared in this file. ActionScript allows one public type per file
    # and requires it to be named after the file, so the *file node is the type*
    # — no separate class node is emitted. Emitting one would split every symbol
    # in two and leave `Foo` (the class) ambiguous against `Foo.as` (the file),
    # which is enough to make `graphify affected` refuse to resolve the name.
    declared_types: set[str] = set()

    for match in _CLASS_RE.finditer(src):
        name, extends, implements = match.group(1), match.group(2), match.group(3)
        declared_types.add(name)
        if extends:
            qualified = scope.qualify(extends)
            if qualified:
                reference(qualified, "inherits", file_nid, match.start())
        for raw_name in (implements or "").split(","):
            qualified = scope.qualify(raw_name)
            if qualified:
                reference(qualified, "implements", file_nid, match.start())

    for match in _INTERFACE_RE.finditer(src):
        declared_types.add(match.group(1))
        for raw_name in (match.group(2) or "").split(","):
            qualified = scope.qualify(raw_name)
            if qualified:
                reference(qualified, "inherits", file_nid, match.start())

    # Members. The constructor is skipped: it carries the type's own name, so it
    # would collide with the file node under any name-based lookup, and calling
    # it is already recorded as an `instantiates` edge from the caller.
    for match in _FUNCTION_RE.finditer(src):
        name = match.group(1)
        if name in declared_types:
            continue
        location = line_at(match.start())
        method_nid = _make_id(file_nid, name)
        add_node(method_nid, name, location)
        add_edge(file_nid, method_nid, "contains", location)

    for match in _NEW_RE.finditer(src):
        qualified = scope.qualify(match.group(1))
        if not qualified:
            continue
        reference(qualified, "instantiates", file_nid, match.start())

    def add_concept(value: str, relation: str, location: str) -> None:
        """Edge to a non-type target: an embedded asset, a resource bundle."""
        target_nid = _make_id(value)
        if not target_nid:
            return
        add_node(target_nid, Path(value).name, location, file_type="concept", shared=True)
        add_edge(file_nid, target_nid, relation, location)

    # Constants this file declares, used to resolve its own bare references.
    local_constants = {m.group(1): m.group(3) for m in _STATIC_CONST_RE.finditer(src)}

    def event_key(token: str) -> str | None:
        """Identity of an event: its literal value wherever that is knowable.

        A dispatch usually writes the literal and a listener usually writes the
        constant, so both are reduced to the value. `Class.CONST` is resolved by
        reading the declaring file; anything that cannot be resolved keeps its
        written form, which still groups the sites that spell it the same way.
        """
        token = token.strip()
        if not token:
            return None
        if token[0] in "\"'":
            return token[1:-1].strip() or None
        if "." in token:
            owner, _, name = token.rpartition(".")
            qualified = scope.qualify(owner)
            if qualified:
                declaring_file = _resolve_to_file(root, qualified)
                if declaring_file != qualified:
                    constants = dict(_string_constants(declaring_file))
                    if name in constants:
                        return constants[name]
            return token
        return local_constants.get(token, token)

    def add_event(token: str, relation: str, source_nid: str, offset: int) -> None:
        key = event_key(token)
        if not key:
            return
        location = line_at(offset)
        event_nid = _make_id("event", key)
        if not event_nid:
            return
        add_node(event_nid, key, location, file_type="concept", shared=True)
        add_edge(source_nid, event_nid, relation, location)

    # Metadata carrying a real target. [Embed(source='…')] pins a compile-time
    # asset dependency and [ArrayElementType("PaymentMode")] a collection's
    # element type — neither is visible to the import graph. [Bindable] and
    # [Inspectable] are compiler hints with nothing to point at, so they are
    # skipped rather than turned into empty nodes.
    for match in _METADATA_RE.finditer(src):
        tag, args = match.group(1), match.group(2) or ""
        location = line_at(match.start())
        if tag == "Embed":
            value_match = _EMBED_SOURCE_RE.search(args) or _FIRST_STRING_RE.search(args)
            if value_match:
                add_concept(value_match.group(1), "embeds", location)
        elif tag == "ResourceBundle":
            value_match = _FIRST_STRING_RE.search(args)
            if value_match:
                add_concept(value_match.group(1), "references", location)
        elif tag == "ArrayElementType":
            value_match = _FIRST_STRING_RE.search(args)
            if value_match:
                qualified = scope.qualify(value_match.group(1))
                if qualified:
                    reference(qualified, "references", file_nid, match.start())
        elif tag == "Event":
            # [Event(name="OK", type="classes.payment.TransactionEvent")] is the
            # declarative half of the wiring: the class advertises what it emits.
            meta = _EVENT_META_RE.search(args)
            if meta:
                add_event(f"'{meta.group(1)}'", "declares_event", file_nid, match.start())
                qualified = scope.qualify(meta.group(2))
                if qualified:
                    reference(qualified, "references", file_nid, match.start())

    # Dispatchers and listeners, attributed to the enclosing type so the graph
    # answers "who emits this" and "who reacts to it" at class granularity.
    for match in _DISPATCH_RE.finditer(src):
        add_event(match.group(2), "dispatches", file_nid, match.start())

    for match in _LISTEN_RE.finditer(src):
        add_event(match.group(1), "listens", file_nid, match.start())

    # Direct reach into the application singleton — the second body of structure
    # that no import statement records.
    for match in _FLEXGLOBALS_RE.finditer(src):
        name = match.group(1)
        if name in _FLEX_APPLICATION_MEMBERS:
            continue
        location = line_at(match.start())
        global_nid = _make_id("global", name)
        if not global_nid:
            continue
        add_node(global_nid, name, location, file_type="concept", shared=True)
        add_edge(file_nid, global_nid, "uses_global", location)

    return {"nodes": nodes, "edges": _collapse_edges(edges)}
