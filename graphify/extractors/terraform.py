"""Terraform block extraction and local module-source topology."""
from __future__ import annotations


import hashlib
import json
import re
from collections.abc import Sequence
from pathlib import Path
from graphify.extractors.base import _make_id
from graphify.security import (
    _CONTROL_CHAR_RE,
    _METADATA_MAX_ATTRIBUTES,
    _METADATA_MAX_LIST_ITEMS,
    _METADATA_MAX_VALUE_LEN,
)



_TF_META_HEADS = frozenset({"count", "each", "self", "path", "terraform"})

# Attribute values are persisted verbatim into graph.json and surfaced to the
# model via the MCP query/get_node paths, so a hardcoded credential in a `.tf`
# file would leak. Redact the VALUE of any attribute whose key names a secret,
# keeping the key itself so `instance_type`/`ami` queries still work and a user
# can still see THAT a secret is set. Substring match (case-insensitive) so
# `db_password`, `aws_secret_access_key`, `client_secret` are all caught.
_SENSITIVE_KEY_RE = re.compile(
    r"(password|passwd|secret|token|api[-_]?key|access[-_]?key|"
    r"private[-_]?key|credential|client[-_]?secret|connection[-_]?string|"
    r"sas[-_]?token|auth|passphrase)",
    re.IGNORECASE,
)
_REDACTED = "[redacted]"


def _redact_value(key: str, value: object) -> object:
    """Redact a sensitive attribute value; recurse into map AND list values so a
    nested `password` inside a `tags`/`connection` map — or inside a list of
    objects — is redacted too.

    HCL routinely nests objects inside tuples (`list(object(...))` variables,
    `dynamic` blocks, tuple defaults), and `_parse_attr_value` turns those into
    Python lists of dicts. Recursing into dicts but not lists left
    `configs = [{ password = "x" }]` leaking verbatim while the map form
    `config = { password = "x" }` was redacted — the value still reaches
    graph.json and the MCP query/get_node surface unsanitized (#3644 follow-up).
    List elements are recursed under the same key: the list branch is only
    reached when `key` is NOT itself sensitive (a sensitive key redacts the whole
    value above), so a scalar element carries no key signal and is returned
    as-is, while a dict element is checked against its own inner keys."""
    if _SENSITIVE_KEY_RE.search(key):
        return _REDACTED
    if isinstance(value, dict):
        return {k: _redact_value(str(k), v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_redact_value(key, item) for item in value]
    return value


def _scope_id(directory: str) -> str:
    # Hash the exact path too: make_id folds case and punctuation, which must
    # not merge e.g. dev/app with prod/app, or a-b with a_b.
    digest = hashlib.sha256(directory.encode("utf-8")).hexdigest()[:16]
    return _make_id("terraform", directory, digest)


def prepare_terraform(result: dict, path: Path, root: Path) -> None:
    """Make cached directory-scoped IDs portable before the common merge passes."""
    directory = path.parent.resolve()
    try:
        relative = directory.relative_to(root).as_posix()
    except ValueError:
        return
    old, new = _scope_id(directory.as_posix()), _scope_id(relative)
    for node in result.get("nodes", []):
        nid = node["id"]
        if nid.startswith(old + "_"):
            node["id"] = new + nid[len(old):]
        node["_terraform_directory"] = relative
    for edge in result.get("edges", []):
        for key in ("source", "target"):
            nid = edge[key]
            if nid.startswith(old + "_"):
                edge[key] = new + nid[len(old):]
    # Resolve paths only here, with the scan boundary available. The per-file
    # cache keeps syntax facts, never filesystem-dependent topology.
    for node in result.get("nodes", []):
        source = node.get("module_source", "")
        if not source.startswith(("./", "../")):
            continue
        try:
            target = (directory / source).resolve().relative_to(root)
        except (ValueError, OSError, RuntimeError):
            continue
        node["_terraform_source_directory"] = target.as_posix()


def resolve_terraform_modules(per_file: list[dict], nodes: list[dict], edges: list[dict]) -> None:
    """Connect module calls to scanned .tf directories without reading new files."""
    files: dict[str, list[dict]] = {}
    anchors = {}
    for node in nodes:
        directory = node.get("_terraform_directory")
        if directory is None:
            continue
        if node.get("type") == "terraform_file" and Path(node["source_file"]).suffix == ".tf":
            files.setdefault(directory, []).append(node)
        elif node.get("type") == "module" and node.get("language") == "terraform":
            anchors[directory] = node["id"]
    fresh_files = {
        node["id"] for result in per_file for node in result.get("nodes", [])
        if node.get("type") == "terraform_file"
    }
    known_ids = {n["id"] for n in nodes}
    for directory, members in sorted(files.items()):
        anchor = anchors.setdefault(directory, _make_id(_scope_id(directory), "directory"))
        if anchor not in known_ids:
            owner = min(members, key=lambda n: n["source_file"])
            nodes.append({
                "id": anchor, "label": f"Terraform module: {directory}",
                "type": "module", "language": "terraform", "file_type": "code",
                "source_file": owner["source_file"], "source_location": None,
                "_terraform_directory": directory,
            })
            known_ids.add(anchor)
        for member in members:
            if member["id"] in fresh_files:
                edges.append({
                    "source": anchor, "target": member["id"], "relation": "contains",
                    "confidence": "EXTRACTED", "weight": 1.0,
                    "source_file": member["source_file"], "source_location": None,
                })
    fresh_calls = {
        node["id"] for result in per_file for node in result.get("nodes", [])
        if "module_source" in node
    }
    for node in nodes:
        if node["id"] not in fresh_calls:
            continue
        target = anchors.get(node.get("_terraform_source_directory"))
        if target is not None:
            edges.append({
                "source": node["id"], "target": target, "relation": "module_source",
                "confidence": "EXTRACTED", "weight": 1.0,
                "source_file": node["source_file"],
                "source_location": node["module_source_location"],
            })


def refresh_terraform_paths(
    changed: list[Path], corpus: list[Path], invalidated: Sequence[Path] = (),
) -> list[Path]:
    """Reconcile directory ownership and incoming links on incremental scans.

    Callers pass only the permitted, live corpus. Cached syntax is reused for
    unchanged Terraform files; other languages keep their incremental behavior.
    """
    if not any(p.suffix == ".tf" or p.name in (".gitignore", ".graphifyignore")
               for p in [*changed, *invalidated]):
        return changed
    return list(dict.fromkeys([*changed, *(p for p in corpus if p.suffix == ".tf")]))


def extract_terraform(path: Path) -> dict:
    """Extract Terraform/HCL blocks and the references between them via tree-sitter.

    Nodes: resources, data sources, modules, variables, outputs, providers, and
    locals. Edges: `contains` (file -> block), `references` (block -> the blocks
    it interpolates, e.g. `aws_instance.web` -> `var.region`), and `depends_on`
    (explicit dependency edges).

    Node IDs are scoped by the parent directory, not the file stem, because
    Terraform resources are module(directory)-scoped: a resource defined in
    main.tf is referenced from other .tf files in the same directory. Directory
    scoping lets those cross-file references resolve when per-file extractions
    are merged (stem scoping would split a definition from its references).
    """
    try:
        import tree_sitter_hcl as tshcl
        from tree_sitter import Language, Parser
    except ImportError:
        return {"nodes": [], "edges": [], "error": "tree_sitter_hcl not installed. Run: pip install tree-sitter-hcl"}

    try:
        language = Language(tshcl.language())
        parser = Parser(language)
        source = path.read_bytes()
        tree = parser.parse(source)
        root = tree.root_node
    except Exception as e:
        return {"nodes": [], "edges": [], "error": str(e)}

    str_path = str(path.parent.resolve() / path.name)
    file_nid = _make_id(str_path)
    scope = _scope_id(path.parent.resolve().as_posix())

    nodes: list[dict] = [{"id": file_nid, "label": path.name, "file_type": "code",
                          "source_file": str_path, "source_location": None,
                          "type": "terraform_file"}]
    edges: list[dict] = []
    seen_ids: set[str] = {file_nid}
    nodes_by_id = {file_nid: nodes[0]}
    seen_edges: set[tuple[str, str, str]] = set()

    def _read(n) -> str:
        return source[n.start_byte:n.end_byte].decode("utf-8", errors="replace")

    def _label_text(n) -> str:
        return _read(n).strip().strip('"')

    def _add_node(address: str, label: str, line: int) -> str:
        nid = _make_id(scope, address)
        if nid not in seen_ids:
            seen_ids.add(nid)
            nodes.append({"id": nid, "label": label, "file_type": "code",
                          "source_file": str_path, "source_location": f"L{line}"})
            nodes_by_id[nid] = nodes[-1]
            edges.append({"source": file_nid, "target": nid, "relation": "contains",
                          "confidence": "EXTRACTED", "source_file": str_path,
                          "source_location": f"L{line}", "weight": 1.0})
        return nid

    def _add_edge(src: str, address: str, relation: str, line: int) -> None:
        tgt = _make_id(scope, address)
        if src == tgt:
            return
        key = (src, tgt, relation)
        if key in seen_edges:
            return
        seen_edges.add(key)
        edges.append({"source": src, "target": tgt, "relation": relation,
                      "confidence": "EXTRACTED", "source_file": str_path,
                      "source_location": f"L{line}", "weight": 1.0})

    def _block_parts(block) -> tuple:
        btype = None
        labels: list[str] = []
        for c in block.children:
            if c.type in ("block_start", "body", "block_end"):
                break
            if c.type == "identifier" and btype is None:
                btype = _read(c)
            elif c.type in ("string_lit", "identifier"):
                labels.append(_label_text(c))
        return btype, labels

    def _ref_address(expr):
        head = _read(expr)
        parent = expr.parent
        attrs: list[str] = []
        if parent is not None:
            seen_self = False
            for c in parent.children:
                if c.id == expr.id:
                    seen_self = True
                    continue
                if seen_self and c.type == "get_attr":
                    name = None
                    for gc in c.children:
                        if gc.type == "identifier":
                            name = _read(gc)
                            break
                    if name is None:
                        break
                    attrs.append(name)
                elif seen_self and c.type not in ("get_attr",):
                    break
        if head in _TF_META_HEADS or not head:
            return None
        if head == "var":
            return f"var.{attrs[0]}" if attrs else None
        if head == "local":
            return f"local.{attrs[0]}" if attrs else None
        if head == "module":
            return f"module.{attrs[0]}" if attrs else None
        if head == "data":
            return f"data.{attrs[0]}.{attrs[1]}" if len(attrs) >= 2 else None
        return f"{head}.{attrs[0]}" if attrs else None

    def _collect_refs(node, owner_nid: str, relation: str) -> None:
        rel = relation
        if node.type == "attribute":
            key_node = node.child_by_field_name("key") or (
                node.children[0] if node.children else None
            )
            if key_node is not None and _read(key_node) == "depends_on":
                rel = "depends_on"
        if node.type == "variable_expr":
            addr = _ref_address(node)
            if addr:
                _add_edge(owner_nid, addr, rel, node.start_point[0] + 1)
        for c in node.children:
            if c.is_named:
                _collect_refs(c, owner_nid, rel)

    def _clean_val_str(text: str) -> str:
        text = _CONTROL_CHAR_RE.sub("", str(text))
        if len(text) > _METADATA_MAX_VALUE_LEN:
            text = text[:_METADATA_MAX_VALUE_LEN]
        return text

    def _parse_attr_value(node, depth: int = 0):
        if depth > 5:
            return _clean_val_str(_read(node).strip())
        cur = node
        while cur.type in ("expression", "literal_value", "collection_value") and len(cur.named_children) == 1:
            cur = cur.named_children[0]

        t = cur.type
        raw = _read(cur).strip()

        if t == "bool_lit":
            return raw == "true"
        elif t == "numeric_lit":
            try:
                return int(raw)
            except ValueError:
                try:
                    return float(raw)
                except ValueError:
                    return _clean_val_str(raw)
        elif t == "null_lit":
            return None
        elif t == "string_lit":
            if raw.startswith('"') and raw.endswith('"'):
                try:
                    return _clean_val_str(json.loads(raw))
                except Exception:
                    return _clean_val_str(raw[1:-1])
            return _clean_val_str(raw)
        elif t == "tuple":
            items = []
            for c in cur.named_children:
                if c.type not in ("tuple_start", "tuple_end"):
                    items.append(_parse_attr_value(c, depth + 1))
                    if len(items) >= _METADATA_MAX_LIST_ITEMS:
                        break
            return items
        elif t == "object":
            obj = {}
            for c in cur.children:
                if c.type == "object_elem":
                    k_node = c.child_by_field_name("key") or (c.named_children[0] if c.named_children else None)
                    v_node = c.child_by_field_name("val") or (c.named_children[-1] if len(c.named_children) > 1 else None)
                    if k_node and v_node:
                        k_val = _parse_attr_value(k_node, depth + 1)
                        k_str = str(k_val) if k_val is not None else _read(k_node).strip().strip('"')
                        k_str = _clean_val_str(k_str)
                        obj[k_str] = _parse_attr_value(v_node, depth + 1)
                        if len(obj) >= _METADATA_MAX_LIST_ITEMS:
                            break
            return obj
        else:
            return _clean_val_str(raw)

    def _collect_direct_attributes(blk_body) -> dict:
        attrs = {}
        for child in blk_body.children:
            if child.type != "attribute":
                continue
            k_node = child.child_by_field_name("key") or (child.children[0] if child.children else None)
            if k_node is None:
                continue
            key = _clean_val_str(_read(k_node).strip())
            if not key:
                continue
            val_node = child.named_children[-1] if child.named_children else None
            if val_node is None:
                continue
            attrs[key] = _redact_value(key, _parse_attr_value(val_node))
            if len(attrs) >= _METADATA_MAX_ATTRIBUTES:
                break
        return attrs

    def _body_of(block):
        for c in block.children:
            if c.type == "body":
                return c
        return None

    body = next((c for c in root.children if c.type == "body"), root)
    for block in body.children:
        if block.type != "block":
            continue
        btype, labels = _block_parts(block)
        line = block.start_point[0] + 1
        blk_body = _body_of(block)
        if btype == "resource" and len(labels) >= 2:
            owner = _add_node(f"{labels[0]}.{labels[1]}", f"{labels[0]}.{labels[1]}", line)
        elif btype == "data" and len(labels) >= 2:
            owner = _add_node(f"data.{labels[0]}.{labels[1]}", f"data.{labels[0]}.{labels[1]}", line)
        elif btype == "module" and labels:
            owner = _add_node(f"module.{labels[0]}", f"module.{labels[0]}", line)
            if blk_body is not None and path.suffix == ".tf":
                for attr in blk_body.named_children:
                    if attr.type != "attribute" or _read(attr.named_children[0]) != "source":
                        continue
                    # Accept a plain quoted literal only, not interpolation,
                    # heredocs, or constant expressions requiring evaluation.
                    value = attr.named_children[-1]
                    while value.type in ("expression", "literal_value") and len(value.named_children) == 1:
                        value = value.named_children[0]
                    if value.type != "string_lit" or value.has_error:
                        continue
                    try:
                        module_source = json.loads(_read(value))
                    except (ValueError, TypeError):
                        continue
                    if not isinstance(module_source, str):
                        continue
                    nodes_by_id[owner]["module_source"] = module_source.replace("$${", "${").replace("%%{", "%{")
                    nodes_by_id[owner]["module_source_location"] = f"L{attr.start_point[0] + 1}"
        elif btype == "variable" and labels:
            owner = _add_node(f"var.{labels[0]}", f"var.{labels[0]}", line)
        elif btype == "output" and labels:
            owner = _add_node(f"output.{labels[0]}", f"output.{labels[0]}", line)
        elif btype == "provider" and labels:
            owner = _add_node(f"provider.{labels[0]}", f"provider.{labels[0]}", line)
        elif btype == "locals" and blk_body is not None:
            for attr in blk_body.children:
                if attr.type != "attribute":
                    continue
                key_node = attr.children[0] if attr.children else None
                if key_node is None:
                    continue
                key = _read(key_node)
                lnid = _add_node(f"local.{key}", f"local.{key}", attr.start_point[0] + 1)
                _collect_refs(attr, lnid, "references")
            continue
        else:
            continue
        if blk_body is not None:
            attrs = _collect_direct_attributes(blk_body)
            if attrs:
                nodes_by_id[owner]["attributes"] = attrs
            _collect_refs(blk_body, owner, "references")

    return {"nodes": nodes, "edges": edges}
