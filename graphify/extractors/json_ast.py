"""JSON AST extractor for config/manifest files."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .registry import register
from ._utils import make_id, file_stem

_CONFIG_JSON_NAMES = frozenset(
    {
        "package.json",
        "tsconfig.json",
        "jsconfig.json",
        "composer.json",
        "deno.json",
        "deno.jsonc",
        "bower.json",
        "manifest.json",
        "app.json",
        "now.json",
        "vercel.json",
        "angular.json",
        "nest-cli.json",
        "biome.json",
        "biome.jsonc",
        "renovate.json",
        ".babelrc",
        ".babelrc.json",
        ".eslintrc.json",
        ".prettierrc.json",
        ".prettierrc",
        "babel.config.json",
    }
)

_CONFIG_JSON_KEYS = frozenset(
    {
        "dependencies",
        "devDependencies",
        "peerDependencies",
        "optionalDependencies",
        "bundleDependencies",
        "bundledDependencies",
        "extends",
        "$ref",
        "$schema",
        "compilerOptions",
    }
)


def _read_text(node, source: bytes) -> str:
    return source[node.start_byte : node.end_byte].decode("utf-8", errors="replace")


def _is_config_json(path: Path, obj_node, source: bytes) -> bool:
    """True if a .json file is a recognized config/manifest worth AST-extracting.

    Matches by filename first (cheap), then falls back to a top-level key probe
    so arbitrarily-named config files (e.g. ``api.tsconfig.json``,
    ``foo.eslintrc.json``) are still picked up. Returns False for data JSON so it
    is skipped by the structural pass (#1224)."""
    name = path.name.casefold()
    if name in _CONFIG_JSON_NAMES:
        return True
    if name.endswith(
        (".eslintrc.json", ".prettierrc.json", ".babelrc.json", "tsconfig.json", "jsconfig.json")
    ):
        return True
    for top_key in obj_node.children:
        if top_key.type != "pair":
            continue
        key_node = top_key.child_by_field_name("key")
        if key_node is None:
            continue
        kc = key_node.child_by_field_name("string_content")
        text = _read_text(kc, source) if kc else _read_text(key_node, source).strip("\"'")
        if text in _CONFIG_JSON_KEYS:
            return True
    return False


@register({".json"})
def extract_json(path: Path) -> dict:
    """Extract structure and dependency edges from a *config/manifest* .json file.

    Data-shaped JSON (eval fixtures, datasets, GeoJSON, API response dumps) is
    deliberately skipped — AST-walking it produced hundreds of orphan key-nodes
    and duplicate communities that swamped real structure (#1224). Recognition
    is by filename (package.json, tsconfig.json, …) or a top-level key probe
    (dependencies / extends / $ref / $schema / compilerOptions)."""
    _JSON_MAX_BYTES = 1_048_576

    try:
        import tree_sitter_json as tsjson
        from tree_sitter import Language, Parser
    except ImportError:
        return {"nodes": [], "edges": [], "error": "tree-sitter-json not installed"}

    try:
        with path.open("rb") as _f:
            source = _f.read(_JSON_MAX_BYTES + 1)
        if len(source) > _JSON_MAX_BYTES:
            return {"nodes": [], "edges": [], "error": "json file too large to index"}
        language = Language(tsjson.language())
        parser = Parser(language)
        tree = parser.parse(source)
        root = tree.root_node
    except Exception as e:
        return {"nodes": [], "edges": [], "error": str(e)}

    stem = file_stem(path)
    str_path = str(path)
    nodes: list[dict] = []
    edges: list[dict] = []
    seen_ids: set[str] = set()

    _DEP_KEYS = frozenset(
        {
            "dependencies",
            "devDependencies",
            "peerDependencies",
            "optionalDependencies",
            "bundleDependencies",
            "bundledDependencies",
        }
    )

    def add_node(nid: str, label: str, line: int) -> None:
        if nid and nid not in seen_ids:
            seen_ids.add(nid)
            nodes.append(
                {
                    "id": nid,
                    "label": label,
                    "file_type": "code",
                    "source_file": str_path,
                    "source_location": f"L{line}",
                }
            )

    def add_edge(src: str, tgt: str, relation: str, line: int, context: str | None = None) -> None:
        if not src or not tgt or src == tgt:
            return
        edge = {
            "source": src,
            "target": tgt,
            "relation": relation,
            "confidence": "EXTRACTED",
            "source_file": str_path,
            "source_location": f"L{line}",
            "weight": 1.0,
        }
        if context:
            edge["context"] = context
        edges.append(edge)

    file_nid = make_id(str(path))
    add_node(file_nid, path.name, 1)

    def _key_text(pair_node) -> str | None:
        """Extract the string content of a pair's key."""
        key_node = pair_node.child_by_field_name("key")
        if key_node is None:
            return None
        if key_node.type == "string":
            content = key_node.child_by_field_name("string_content")
            if content:
                return _read_text(content, source)
            raw = _read_text(key_node, source)
            return raw.strip("\"'")
        return _read_text(key_node, source)

    def _val_node(pair_node):
        return pair_node.child_by_field_name("value")

    def walk_object(
        obj_node, parent_nid: str, parent_key: str | None, depth: int, pair_count: list
    ) -> None:
        if depth > 6:
            return
        for child in obj_node.children:
            if child.type != "pair":
                continue
            if pair_count[0] >= 500:
                return
            pair_count[0] += 1
            key = _key_text(child)
            if not key:
                continue
            key_nid = make_id(stem, *(([parent_key] if parent_key else []) + [key]))
            if not key_nid:
                continue
            line = child.start_point[0] + 1
            add_node(key_nid, key, line)
            add_edge(parent_nid, key_nid, "contains", line)

            val = _val_node(child)
            if val is None:
                continue

            if val.type == "object":
                walk_object(val, key_nid, key, depth + 1, pair_count)

            elif val.type == "array":
                for item in val.children:
                    if item.type == "string":
                        content = item.child_by_field_name("string_content")
                        ref = (
                            _read_text(content, source)
                            if content
                            else _read_text(item, source).strip("\"'")
                        )
                        if ref:
                            ref_nid = make_id("ref", ref)
                            if ref_nid:
                                add_edge(key_nid, ref_nid, "extends", line, context="import")

            elif val.type == "string":
                content = val.child_by_field_name("string_content")
                val_text = (
                    _read_text(content, source) if content else _read_text(val, source).strip("\"'")
                )
                line = val.start_point[0] + 1

                if key == "extends" and val_text:
                    ref_nid = make_id("ref", val_text)
                    if ref_nid:
                        add_edge(file_nid, ref_nid, "extends", line, context="import")

                elif key == "$ref" and val_text:
                    ref_nid = make_id("ref", val_text)
                    if ref_nid:
                        add_edge(parent_nid, ref_nid, "references", line)

                elif parent_key in _DEP_KEYS and val_text:
                    dep_nid = make_id(key)
                    if dep_nid:
                        add_edge(key_nid, dep_nid, "imports", line, context="import")

    doc = root
    if doc.type == "document" and doc.child_count > 0:
        doc = doc.children[0]
    if doc.type == "object":
        if not _is_config_json(path, doc, source):
            return {"nodes": [], "edges": [], "skipped": "data json (not a config/manifest)"}
        walk_object(doc, file_nid, None, 0, [0])
    else:
        return {"nodes": [], "edges": [], "skipped": "data json (non-object root)"}

    return {"nodes": nodes, "edges": edges}
