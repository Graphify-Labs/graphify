"""MXML extractor (Adobe Flex / AIR / Apache Royale component markup).

MXML is the markup half of a Flex application: XML that declares a component
tree, with ActionScript embedded in ``<fx:Script><![CDATA[ … ]]></fx:Script>``.
This is the same shape ``razor.py`` handles for ``.cshtml`` and
``pascal_forms.py`` for Delphi ``.dfm`` — markup paired with a real language.

The embedded script is handed to :mod:`graphify.extractors.actionscript` rather
than re-parsed here, so the two never drift apart.

Parsing is regex-based rather than XML-tree-based on purpose: an XML parser
gives no line numbers, and ``file:line`` is most of what makes the extracted
graph navigable.

Four dependency mechanisms in MXML are invisible to an import graph, and they
are the reason this extractor earns its keep:

* ``xmlns:layout="classes.layout.*"`` maps a tag prefix to a package, so
  ``<layout:Foo/>`` is a reference to ``classes.layout.Foo`` with no import line.
* ``@Embed(source='/assets/…')`` pins a compile-time asset dependency.
* Event handlers live in attribute values — ``click="onClick(event)"``.
* ``skinClass="…"`` binds a component to its skin.
"""
from __future__ import annotations

import re
from pathlib import Path

from graphify.extractors.actionscript import (
    _PACKAGE_RE,
    _collapse_edges,
    _Scope,
    _resolve_to_file,
    extract_actionscript_source,
)
from graphify.extractors.base import _make_id

# ── Patterns ─────────────────────────────────────────────────────────────────

# xmlns:layout="classes.layout.*" — a package. Library namespaces
# (`library://ns.adobe.com/flex/spark`, `http://ns.adobe.com/mxml/2009`) are SDK
# URIs and are deliberately not packages.
_XMLNS_RE = re.compile(r'xmlns:(\w+)\s*=\s*"([^"]+)"')

# <layout:ClubActionProposalDisplay …>. Only prefixed tags can be app
# components; a bare <Foo> in MXML is not valid without a default namespace.
# The attribute blob is captured so `includeIn` can be read off the same match.
_TAG_RE = re.compile(
    r"<(\w+):(\w+)((?:[^>\"']|\"[^\"]*\"|'[^']*')*)>", re.DOTALL
)
_INCLUDE_IN_RE = re.compile(r'\bincludeIn\s*=\s*"([^"]+)"')

_SCRIPT_CDATA_RE = re.compile(
    r"<fx:Script[^>]*>\s*<!\[CDATA\[(.*?)\]\]>\s*</fx:Script>", re.DOTALL
)
# <fx:Script source="MyLogic.as"/> — code-behind kept in a separate file.
_SCRIPT_SOURCE_RE = re.compile(r'<fx:Script[^>]*\bsource\s*=\s*"([^"]+)"')

_SKIN_RE = re.compile(r'skinClass\s*=\s*"\s*([\w.]+)\s*"')
_EMBED_RE = re.compile(r"@Embed\s*\(\s*(?:source\s*=\s*)?['\"]([^'\"]+)['\"]")
_RESOURCE_RE = re.compile(
    r"resourceManager\.getString\(\s*['\"]([^'\"]+)['\"]\s*,\s*['\"]([^'\"]+)['\"]"
)
_STATE_RE = re.compile(r'<s:State\s+[^>]*name\s*=\s*"([^"]+)"')

# A skin declares the Spark interaction states of a single component; an
# application declares its view states. Only the latter describe architecture.
# Without this split, `state:up` and `state:disabled` become god nodes wired to
# every button skin in the project while carrying no navigational meaning —
# the failure mode `base.py` guards against for language builtins.
_SKIN_ROOT_RE = re.compile(r"<\w+:(\w*Skin)\b")
_SKIN_STATE_NAMES = frozenset({
    "up", "over", "down", "disabled", "normal", "selected",
    "upAndSelected", "overAndSelected", "downAndSelected", "disabledAndSelected",
    "normalWithPrompt", "disabledWithPrompt", "open", "closed",
    "inactive", "active", "editable", "uneditable",
})


# ── Scope resolution ─────────────────────────────────────────────────────────


def _source_root(path: Path, packages: list[str]) -> Path:
    """Locate the source root for an MXML file, which declares no package.

    First tries the packages named by the file's own ``xmlns`` declarations: the
    root is the ancestor directory under which ``classes/layout`` (say) actually
    exists. Falls back to reading the ``package`` declaration of the nearest
    ``.as`` file up the tree, which pins the root the same way.
    """
    candidates = [path.parent, *path.parents]
    for candidate in candidates:
        for package in packages:
            if (candidate / package.replace(".", "/")).is_dir():
                return candidate

    for candidate in candidates[:8]:
        for sibling in sorted(candidate.glob("*.as")):
            try:
                head = sibling.read_text(encoding="utf-8", errors="replace")[:4096]
            except OSError:
                continue
            match = _PACKAGE_RE.search(head)
            if not match or not match.group(1):
                continue
            root = candidate
            for _ in match.group(1).split("."):
                root = root.parent
            return root

    return path.parent


def _package_of(path: Path, root: Path) -> str:
    """Package an MXML file belongs to, derived from its location under root."""
    try:
        relative = path.parent.relative_to(root)
    except ValueError:
        return ""
    return ".".join(relative.parts)


# ── Extraction ───────────────────────────────────────────────────────────────


def extract_mxml(path: Path) -> dict:
    """Extract component references, script, handlers, skins and assets from .mxml."""
    try:
        src = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return {"nodes": [], "edges": [], "error": f"cannot read {path}"}

    str_path = str(path)
    file_nid = _make_id(str_path)

    # Prefix -> package, for the namespaces that name a package rather than an
    # SDK library URI.
    namespaces: dict[str, str] = {}
    for match in _XMLNS_RE.finditer(src):
        prefix, value = match.group(1), match.group(2)
        if value.endswith(".*"):
            namespaces[prefix] = value[:-2]

    root = _source_root(path, list(namespaces.values()))
    package = _package_of(path, root)
    scope = _Scope(package, root)
    for imported in namespaces.values():
        scope.wildcards.append(imported)

    nodes: list[dict] = [{
        "id": file_nid, "label": path.name, "file_type": "code",
        "source_file": str_path, "source_location": None,
    }]
    edges: list[dict] = []
    seen: set[str] = {file_nid}
    edge_index: dict[tuple[str, str, str], dict] = {}

    def line_at(offset: int) -> str:
        return f"L{src.count(chr(10), 0, offset) + 1}"

    def add_node(
        nid: str,
        label: str,
        location: str | None,
        file_type: str = "code",
        source_file: str | None = None,
        shared: bool = False,
    ) -> None:
        """Create a node once. See the same helper in `actionscript.py` for why
        `source_file` and `shared` exist: without them graphify's
        id-disambiguation pass splits every shared entity into one node per
        referencing file."""
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

    def reference(fqn: str, relation: str, offset: int) -> None:
        location = line_at(offset)
        target_key = _resolve_to_file(root, fqn)
        target_nid = _make_id(target_key)
        if not target_nid:
            return
        if target_key != fqn:
            add_node(target_nid, Path(target_key).name, None, source_file=target_key)
        else:
            add_node(target_nid, fqn.rsplit(".", 1)[-1], location, shared=True)
        add_edge(file_nid, target_nid, relation, location)

    def add_concept(value: str, label: str, relation: str, location: str) -> None:
        target_nid = _make_id(value)
        if not target_nid:
            return
        add_node(target_nid, label, location, file_type="concept", shared=True)
        add_edge(file_nid, target_nid, relation, location)

    # The namespaces themselves are declared dependencies on a package.
    for match in _XMLNS_RE.finditer(src):
        prefix = match.group(1)
        if prefix in namespaces:
            location = line_at(match.start())
            add_concept(namespaces[prefix], namespaces[prefix], "imports", location)

    # Custom component tags. Tags in SDK namespaces (s:, fx:, mx:) are skipped:
    # they are layout containers and buttons, and indexing them would bury the
    # application's own components under a few hundred `s:Group` nodes.
    #
    # `includeIn="Cart"` binds the component to a view state. Reading it here
    # rather than guessing from filenames is what makes the state graph correct
    # when one component serves several states.
    for match in _TAG_RE.finditer(src):
        prefix, name, attributes = match.group(1), match.group(2), match.group(3)
        package_of_prefix = namespaces.get(prefix)
        if not package_of_prefix:
            continue
        fqn = f"{package_of_prefix}.{name}"
        reference(fqn, "instantiates", match.start())

        include_in = _INCLUDE_IN_RE.search(attributes)
        if not include_in:
            continue
        component_nid = _make_id(_resolve_to_file(root, fqn))
        if not component_nid:
            continue
        location = line_at(match.start())
        for state_name in include_in.group(1).split(","):
            state_name = state_name.strip()
            if not state_name:
                continue
            state_nid = _make_id(f"state:{state_name}")
            add_node(state_nid, state_name, location, file_type="concept", shared=True)
            add_edge(state_nid, component_nid, "renders", location)

    # Code-behind kept in a separate file.
    for match in _SCRIPT_SOURCE_RE.finditer(src):
        target = (path.parent / match.group(1)).resolve()
        location = line_at(match.start())
        key = str(target) if target.is_file() else match.group(1)
        target_nid = _make_id(key)
        if target_nid:
            add_node(target_nid, Path(key).name, None,
                     source_file=key if target.is_file() else None,
                     shared=not target.is_file())
            add_edge(file_nid, target_nid, "includes", location)

    # Embedded script, delegated to the ActionScript extractor so that imports,
    # inheritance, members and instantiations inside CDATA are described exactly
    # as they would be in a .as file.
    for match in _SCRIPT_CDATA_RE.finditer(src):
        body = match.group(1)
        body_offset = match.start(1)
        line_offset = src.count("\n", 0, body_offset)
        inner = extract_actionscript_source(
            body, path, line_offset=line_offset, root=root, package=package
        )
        for node in inner["nodes"]:
            if node["id"] not in seen:
                seen.add(node["id"])
                nodes.append(node)
        for edge in inner["edges"]:
            key = (edge["source"], edge["target"], edge["relation"])
            if key in edge_index:
                edge_index[key]["weight"] += edge.get("weight", 1.0)
                continue
            edge_index[key] = edge
            edges.append(edge)

    # Inline handlers (`click="onPay(event)"`) are deliberately NOT emitted as
    # `calls` edges. graphify builds a non-multigraph, so only one relation can
    # exist between any pair of nodes (build.py, `G.add_edge`) — and a handler is
    # normally defined in the same file's script block, which already yields a
    # `contains` edge for exactly that pair. Emitting the handler edge as well
    # only produces edges the build silently overwrites.

    # Skins, assets, translation keys.
    for match in _SKIN_RE.finditer(src):
        qualified = scope.qualify(match.group(1))
        if qualified:
            reference(qualified, "references", match.start())

    for match in _EMBED_RE.finditer(src):
        value = match.group(1)
        add_concept(value, Path(value).name, "embeds", line_at(match.start()))

    for match in _RESOURCE_RE.finditer(src):
        bundle, key = match.group(1), match.group(2)
        add_concept(f"{bundle}:{key}", key, "references_i18n", line_at(match.start()))

    # <s:State name="Cart"/> — the application's declared view states. The state
    # is its own node; the components that render it are attached by the
    # `includeIn` pass above, giving a real two-hop path
    # (application -> state -> component). Skin interaction states are excluded,
    # see _SKIN_STATE_NAMES.
    is_skin = bool(_SKIN_ROOT_RE.search(src))
    for match in _STATE_RE.finditer(src):
        name = match.group(1)
        if is_skin or name in _SKIN_STATE_NAMES:
            continue
        add_concept(f"state:{name}", name, "declares_state", line_at(match.start()))

    return {"nodes": nodes, "edges": _collapse_edges(edges)}
