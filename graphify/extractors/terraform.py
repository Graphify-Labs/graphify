"""Terraform extractor. Moved verbatim from graphify/extract.py."""
from __future__ import annotations


from pathlib import Path
from graphify.extractors.base import _make_id


_TF_META_HEADS = frozenset({"count", "each", "self", "path", "terraform"})

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

    str_path = str(path)
    file_nid = _make_id(str_path)
    scope = path.parent.name or "tf"

    nodes: list[dict] = [{"id": file_nid, "label": path.name, "file_type": "code",
                          "source_file": str_path, "source_location": None}]
    edges: list[dict] = []
    seen_ids: set[str] = {file_nid}
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
            _collect_refs(blk_body, owner, "references")

    return {"nodes": nodes, "edges": edges}
