"""Deterministic source reflection for HLSL, GLSL, and Slang shaders."""
from __future__ import annotations

import importlib
import re
import warnings
from pathlib import Path

from graphify.extractors.base import _file_stem, _make_id, _read_text
from graphify.security import sanitize_metadata


_MODULES = {
    "hlsl": "tree_sitter_hlsl",
    "glsl": "tree_sitter_glsl",
    "slang": "tree_sitter_slang",
}

_STAGES = {
    "pixel": "fragment",
    "fragment": "fragment",
    "vertex": "vertex",
    "compute": "compute",
    "geometry": "geometry",
    "hull": "hull",
    "domain": "domain",
    "mesh": "mesh",
    "amplification": "amplification",
    "raygeneration": "raygeneration",
    "closesthit": "closesthit",
    "anyhit": "anyhit",
    "intersection": "intersection",
    "miss": "miss",
    "callable": "callable",
}

_INTRINSICS = frozenset({
    "abs", "acos", "all", "any", "asin", "atan", "atan2", "ceil", "clamp",
    "cos", "cross", "ddx", "ddy", "degrees", "determinant", "distance", "dot",
    "exp", "exp2", "faceforward", "floor", "fmod", "frac", "frexp", "fwidth",
    "imageAtomicAdd", "imageLoad", "imageStore", "isinf", "isnan", "length", "lerp",
    "log", "log2", "max", "min", "mix", "mod", "mul", "normalize", "pow",
    "radians", "reflect", "refract", "round", "rsqrt", "saturate", "sign", "sin",
    "smoothstep", "sqrt", "step", "tan", "texelFetch", "texture", "textureGrad",
    "textureLod", "transpose", "trunc",
})

_RESOURCE_HEADS = (
    "Texture", "RWTexture", "Sampler", "Buffer", "RWBuffer", "StructuredBuffer",
    "RWStructuredBuffer", "AppendStructuredBuffer", "ConsumeStructuredBuffer",
    "ByteAddressBuffer", "RWByteAddressBuffer", "ConstantBuffer", "RasterizerOrdered",
    "RaytracingAccelerationStructure", "ParameterBlock", "image", "sampler", "subpassInput",
)

_SCALAR_RE = re.compile(
    r"^(?:void|bool|half|float|double|int|uint|short|ushort|long|ulong|fixed|"
    r"[biud]?vec[234]|mat[234](?:x[234])?|(?:bool|half|float|double|int|uint)[1-4](?:x[1-4])?)$"
)


def _mask_comments(text: str) -> str:
    """Blank comments without changing offsets or line numbers."""
    def blank(match: re.Match[str]) -> str:
        return re.sub(r"[^\r\n]", " ", match.group(0))

    text = re.sub(r"/\*.*?\*/", blank, text, flags=re.DOTALL)
    return re.sub(r"//[^\r\n]*", blank, text)


def _split_csv(text: str) -> list[str]:
    parts: list[str] = []
    start = depth = 0
    for index, char in enumerate(text):
        if char in "<([":
            depth += 1
        elif char in ">)]":
            depth = max(0, depth - 1)
        elif char == "," and depth == 0:
            if item := text[start:index].strip():
                parts.append(item)
            start = index + 1
    if item := text[start:].strip():
        parts.append(item)
    return parts


def _is_builtin_type(name: str) -> bool:
    return bool(_SCALAR_RE.match(name)) or name in {
        "vector", "matrix", "array", "atomic_uint", "sampler", "SamplerState",
        "SamplerComparisonState",
    }


def _resource_kind(type_name: str, qualifiers: set[str]) -> tuple[str, str] | None:
    head = type_name.split("<", 1)[0].strip()
    if head in ("cbuffer", "ConstantBuffer"):
        return "uniform_buffer", "read"
    if head == "tbuffer":
        return "texture_buffer", "read"
    if head == "ParameterBlock":
        return "parameter_block", "read"
    if "RaytracingAccelerationStructure" in head:
        return "acceleration_structure", "read"
    if head.startswith("AppendStructuredBuffer"):
        return "storage_resource", "write"
    if head.startswith("ConsumeStructuredBuffer"):
        return "buffer", "read"
    if head.startswith(("RW", "RasterizerOrdered")):
        return "storage_resource", "read_write"
    if head.startswith("Sampler") or head.startswith("sampler"):
        return "sampler", "read"
    if head.startswith("image"):
        access = "write" if "writeonly" in qualifiers else "read" if "readonly" in qualifiers else "read_write"
        return "image", access
    if head.startswith("Texture"):
        return "texture", "read"
    if head.startswith(("StructuredBuffer", "ByteAddressBuffer", "Buffer")):
        return "buffer", "read"
    return None


class _Extractor:
    def __init__(self, path: Path, language: str, source: bytes, root) -> None:
        self.path = path
        self.language = language
        self.source = source
        self.text = source.decode("utf-8", errors="replace")
        self.masked = _mask_comments(self.text)
        self.root = root
        self.stem = _file_stem(path)
        self.str_path = str(path)
        self.file_nid = _make_id(self.str_path)
        self.nodes: list[dict] = []
        self.edges: list[dict] = []
        self.node_by_id: dict[str, dict] = {}
        self.functions: list[dict] = []
        self.types: dict[str, list[dict]] = {}
        self.resources: dict[str, dict] = {}
        self.glsl_io: list[tuple[str, str]] = []
        self.raw_calls: list[dict] = []

    def shader_meta(self, kind: str, **values) -> dict:
        shader = {"language": self.language, "kind": kind}
        shader.update({key: value for key, value in values.items() if value not in (None, [], {}, "")})
        return {"shader": shader}

    def add_node(self, nid: str, label: str, line: int, kind: str, *, node_type: str | None = None, **meta) -> str:
        metadata = self.shader_meta(kind, **meta)
        if nid in self.node_by_id:
            old = self.node_by_id[nid].setdefault("metadata", {}).setdefault("shader", {})
            old.update(metadata["shader"])
            return nid
        node = {
            "id": nid,
            "label": label,
            "file_type": "code",
            "source_file": self.str_path,
            "source_location": f"L{line}",
            "confidence_score": 1.0,
            "metadata": sanitize_metadata(metadata),
        }
        if node_type:
            node["type"] = node_type
        self.node_by_id[nid] = node
        self.nodes.append(node)
        return nid

    def add_external(self, name: str, line: int) -> str:
        nid = _make_id(name)
        if nid not in self.node_by_id:
            node = {
                "id": nid,
                "label": name,
                "file_type": "code",
                "source_file": "",
                "source_location": "",
                "origin_file": self.str_path,
            }
            self.node_by_id[nid] = node
            self.nodes.append(node)
        return nid

    def add_edge(self, source: str, target: str, relation: str, line: int, *, context: str | None = None, target_file: str | None = None, **meta) -> None:
        edge = {
            "source": source,
            "target": target,
            "relation": relation,
            "confidence": "EXTRACTED",
            "confidence_score": 1.0,
            "source_file": self.str_path,
            "source_location": f"L{line}",
            "weight": 1.0,
        }
        if context:
            edge["context"] = context
        if target_file:
            edge["target_file"] = target_file
        if meta:
            edge["metadata"] = sanitize_metadata(self.shader_meta("relationship", **meta))
        self.edges.append(edge)

    def field_children(self, node, field: str) -> list:
        return [child for index, child in enumerate(node.children) if node.field_name_for_child(index) == field]

    def declarators(self, node) -> list:
        """Return declared symbols, excluding HLSL semantic suffixes."""
        return [
            child for child in self.field_children(node, "declarator")
            if child.type not in ("semantics", "bitfield_clause")
        ]

    def declarator_layout(self, declarator, layout: dict | None = None) -> dict:
        result = dict(layout or {})
        dimensions = [
            value.strip()
            for value in re.findall(r"\[\s*([^\]]*)\s*\]", _read_text(declarator, self.source))
        ]
        if dimensions:
            result["array_dimensions"] = dimensions
        return result

    def descendant(self, node, types: set[str]):
        if node is None or node.type == "ERROR":
            return None
        if node.type in types:
            return node
        for child in node.children:
            if found := self.descendant(child, types):
                return found
        return None

    def declarator_name(self, node) -> str | None:
        if node is None:
            return None
        if node.type in ("identifier", "field_identifier", "type_identifier"):
            return _read_text(node, self.source)
        nested = node.child_by_field_name("declarator") or node.child_by_field_name("name")
        if nested is not None:
            return self.declarator_name(nested)
        for child in node.children:
            if child.type != "ERROR" and child.is_named:
                if name := self.declarator_name(child):
                    return name
        return None

    def type_text(self, node) -> str:
        type_node = node.child_by_field_name("type")
        return _read_text(type_node, self.source).strip() if type_node is not None else ""

    def parameters(self, declarator) -> list:
        params = declarator.child_by_field_name("parameters")
        return [child for child in params.children if child.type == "parameter_declaration"] if params else []

    def parameter_signature(self, parameter) -> str:
        raw = _read_text(parameter, self.source)
        direction = next((q for q in ("inout", "out", "in") if re.search(rf"\b{q}\b", raw)), "")
        dimensions = "".join(f"[{value.strip()}]" for value in re.findall(r"\[\s*([^\]]*)\s*\]", raw))
        return " ".join(part for part in (direction, f"{self.type_text(parameter)}{dimensions}") if part)

    def semantic(self, node) -> str | None:
        if node is None:
            return None
        if node.type in ("semantics", "bitfield_clause"):
            names = re.findall(r"[A-Za-z_]\w*", _read_text(node, self.source))
            return names[-1] if names else None
        for child in node.children:
            if child.type in ("semantics", "bitfield_clause"):
                names = re.findall(r"[A-Za-z_]\w*", _read_text(child, self.source))
                return names[-1] if names else None
        return None

    def layout(self, text: str) -> dict:
        match = re.search(r"\blayout\s*\((.*?)\)", text, re.DOTALL)
        if not match:
            return {}
        result: dict[str, int | str | bool] = {}
        for item in _split_csv(match.group(1)):
            key, sep, value = item.partition("=")
            if not sep:
                result[key.strip()] = True
            else:
                value = value.strip()
                result[key.strip()] = int(value, 0) if re.fullmatch(r"[-+]?\d+", value) else value
        return result

    def bindings(self, text: str, layout: dict | None = None) -> list[dict]:
        bindings: list[dict] = []
        for match in re.finditer(r"\bregister\s*\(\s*([bstu]\d+)\s*(?:,\s*space(\d+))?\s*\)", text):
            binding = {"kind": "register", "register": match.group(1)}
            if match.group(2) is not None:
                binding["space"] = int(match.group(2))
            bindings.append(binding)
        for match in re.finditer(r"vk::binding\s*\(\s*(\d+)\s*(?:,\s*(\d+))?\s*\)", text):
            binding = {"kind": "vulkan", "binding": int(match.group(1))}
            if match.group(2) is not None:
                binding["set"] = int(match.group(2))
            bindings.append(binding)
        if layout and "binding" in layout:
            bindings.append({"kind": "descriptor", "set": layout.get("set", 0), "binding": layout["binding"]})
        return bindings

    def emit_type_refs(self, source_nid: str, type_name: str, line: int, context: str) -> None:
        for name in re.findall(r"[A-Za-z_]\w*", type_name):
            if _is_builtin_type(name) or name in _RESOURCE_HEADS or any(name.startswith(head) for head in _RESOURCE_HEADS):
                continue
            target = _make_id(self.stem, name) if name in self.types else self.add_external(name, line)
            if target != source_nid:
                self.add_edge(source_nid, target, "references", line, context=context)

    def resolve_target(self, raw: str, default_suffix: str | None = None) -> Path | None:
        cleaned = raw.strip().strip('"<>').replace("\\", "/")
        candidates = [self.path.parent / cleaned]
        if default_suffix and not Path(cleaned).suffix:
            candidates.append((self.path.parent / cleaned).with_suffix(default_suffix))
            module_path = cleaned.replace(".", "/")
            candidates.append((self.path.parent / module_path).with_suffix(default_suffix))
            candidates.append((self.path.parent / module_path.replace("_", "-")).with_suffix(default_suffix))
        for candidate in candidates:
            try:
                if candidate.is_file():
                    return candidate.resolve()
            except OSError:
                pass
        return None

    def emit_import(self, raw: str, line: int, relation: str = "imports_from", context: str = "include") -> None:
        suffix = ".slang" if self.language == "slang" else None
        resolved = self.resolve_target(raw, suffix)
        if resolved is not None:
            self.add_edge(self.file_nid, _make_id(str(resolved)), relation, line, context=context, target_file=str(resolved))
            return
        target = _make_id("shader_module", raw)
        self.add_node(target, raw, line, "module_reference", node_type="module")
        self.add_edge(self.file_nid, target, relation, line, context=context)

    def emit_imports(self, node) -> bool:
        text = _read_text(node, self.source)
        line = node.start_point[0] + 1
        if node.type == "preproc_include":
            match = re.search(r"#\s*include\s*([<\"].*?[>\"])", text)
            if match:
                self.emit_import(match.group(1), line)
            return True
        if self.language == "slang" and node.type == "module_declaration":
            name = re.sub(r"^\s*module\s+|\s*;\s*$", "", text).strip()
            nid = self.add_node(_make_id(self.stem, name), name, line, "module", node_type="module")
            self.add_edge(self.file_nid, nid, "contains", line)
            return True
        if self.language == "slang" and node.type == "import_statement":
            match = re.search(r"\bimport\s+([\w.]+)", text)
            if match:
                relation = "re_exports" if "__exported" in text else "imports_from"
                self.emit_import(match.group(1), line, relation, "import")
            return True
        return False

    def emit_field(self, node, owner_nid: str, owner_name: str) -> None:
        declarators = self.declarators(node)
        if declarators and self.descendant(declarators[0], {"function_declarator"}):
            self.emit_function(node, owner_nid)
            return
        line = node.start_point[0] + 1
        type_name = self.type_text(node)
        raw = _read_text(node, self.source)
        semantic = self.semantic(node)
        resource = _resource_kind(type_name, set(raw.split()))
        kind = "resource_member" if resource else "member"
        for declarator in declarators:
            name = self.declarator_name(declarator)
            if not name:
                continue
            layout = self.declarator_layout(declarator)
            if match := re.search(r"packoffset\s*\(([^)]+)\)", raw):
                layout["packoffset"] = match.group(1)
            nid = self.add_node(
                _make_id(owner_nid, name), name, line, kind,
                type=type_name,
                access=resource[1] if resource else None,
                resource_kind=resource[0] if resource else None,
                interface={"semantic": semantic, "builtin": semantic.upper().startswith("SV_")} if semantic else None,
                layout=layout,
            )
            self.add_edge(owner_nid, nid, "contains", line)
            self.emit_type_refs(nid, type_name, line, "field")
            self.types.setdefault(owner_name, []).append({"nid": nid, "name": name, "type": type_name, "semantic": semantic})

    def type_header(self, text: str, name: str) -> tuple[list[str], list[str], list[str]]:
        header = text.split("{", 1)[0]
        generics: list[str] = []
        name_at = header.find(name)
        tail = header[name_at + len(name):] if name_at >= 0 else header
        if tail.lstrip().startswith("<"):
            start = tail.find("<")
            depth = 0
            for index, char in enumerate(tail[start:], start):
                depth += char == "<"
                depth -= char == ">"
                if depth == 0:
                    generics = _split_csv(tail[start + 1:index])
                    tail = tail[index + 1:]
                    break
        constraints = [item.strip() for item in re.findall(r"\bwhere\s+([^\{]+?)(?=\bwhere\b|$)", tail)]
        base_text = tail.split("where", 1)[0]
        bases = _split_csv(base_text.split(":", 1)[1]) if ":" in base_text else []
        return generics, constraints, [re.sub(r"<.*", "", base).strip() for base in bases if base.strip()]

    def emit_type(self, node) -> None:
        name_node = node.child_by_field_name("name")
        name = self.declarator_name(name_node)
        if not name:
            return
        line = node.start_point[0] + 1
        raw = _read_text(node, self.source)
        interface = node.type == "interface_specifier"
        generics, constraints, bases = self.type_header(raw, name)
        nid = self.add_node(
            _make_id(self.stem, name), name, line, "interface" if interface else "struct",
            node_type="interface" if interface else "type",
            generics=generics, constraints=constraints,
        )
        self.types.setdefault(name, [])
        self.add_edge(self.file_nid, nid, "contains", line)
        for base in bases:
            self.add_edge(nid, self.add_external(base, line), "implements" if self.language == "slang" else "inherits", line)
        body = node.child_by_field_name("body")
        if body is not None:
            for child in body.children:
                if child.type in ("field_declaration", "function_definition"):
                    if child.type == "function_definition":
                        self.emit_function(child, nid)
                    else:
                        self.emit_field(child, nid, name)
                elif child.type == "associatedtype_declaration":
                    assoc = next((c for c in child.children if c.type == "type_identifier"), None)
                    if assoc is not None:
                        assoc_name = _read_text(assoc, self.source)
                        assoc_nid = self.add_node(_make_id(nid, assoc_name), assoc_name, child.start_point[0] + 1, "associated_type")
                        self.add_edge(nid, assoc_nid, "contains", child.start_point[0] + 1)

    def function_attributes(self, node) -> str:
        prefix = _mask_comments(
            self.source[max(0, node.start_byte - 1024):node.start_byte].decode("utf-8", errors="replace")
        )
        prefix = re.split(r"[;{}]", prefix)[-1]
        header = _mask_comments(_read_text(node, self.source)).split("{", 1)[0]
        return prefix + header

    def emit_function(self, node, owner_nid: str | None = None) -> None:
        declarator = self.descendant(node.child_by_field_name("declarator"), {"function_declarator"})
        if declarator is None:
            return
        name = self.declarator_name(declarator.child_by_field_name("declarator"))
        if not name:
            return
        line = node.start_point[0] + 1
        attrs = self.function_attributes(node)
        shader_match = re.search(r"\bshader\s*\(\s*[\"']([^\"']+)", attrs)
        threads = re.search(r"\bnumthreads\s*\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\)", attrs)
        stage = _STAGES.get(shader_match.group(1).lower()) if shader_match else "compute" if threads else None
        if self.language == "glsl" and name == "main":
            stage = self.glsl_stage()
        params = self.parameters(declarator)
        hlsl_semantic_entry = self.language == "hlsl" and (
            self.semantic(declarator) is not None or any(self.semantic(param) is not None for param in params)
        )
        if hlsl_semantic_entry and stage is None:
            stage = "unknown"
        entry = bool(stage) or (self.language == "glsl" and name == "main")
        thread_group_size = (
            [int(threads.group(i)) for i in range(1, 4)]
            if threads else self.glsl_thread_group_size() if self.language == "glsl" and name == "main" else None
        )
        return_type = self.type_text(node)
        generic_match = re.search(rf"\b{re.escape(name)}\s*<(.+?)>\s*\(", _read_text(declarator, self.source), re.DOTALL)
        parameter_types = [self.parameter_signature(param) for param in params]
        signature = f"{name}({', '.join(parameter_types)})"
        capabilities = [part.strip() for body in re.findall(r"\brequire\s*\(([^)]*)\)", attrs) for part in _split_csv(body)]
        parent = owner_nid or self.file_nid
        id_parts = [parent if owner_nid else self.stem, name]
        if parameter_types:
            id_parts.append(",".join(parameter_types))
        nid = self.add_node(
            _make_id(*id_parts), f"{name}()", line,
            "entry_point" if entry else "method" if owner_nid else "function",
            entry_point=entry or None, stage=stage,
            thread_group_size=thread_group_size,
            type=return_type, generics=_split_csv(generic_match.group(1)) if generic_match else None,
            capabilities=capabilities, signature=signature, arity=len(params),
        )
        self.node_by_id[nid]["_callable"] = True
        self.add_edge(parent, nid, "method" if owner_nid else "contains", line)
        if return_type:
            self.emit_type_refs(nid, return_type, line, "return_type")
        fact = {
            "nid": nid, "name": name, "node": node, "declarator": declarator,
            "body": node.child_by_field_name("body"), "entry": entry, "stage": stage,
            "return_type": return_type, "arity": len(params),
        }
        self.functions.append(fact)

    def emit_declaration(self, node) -> None:
        raw = _read_text(node, self.source)
        line = node.start_point[0] + 1
        if self.language == "slang" and re.match(r"\s*implementing\b", raw):
            name = re.findall(r"\bimplementing\s+([\w.]+)", raw)
            if name:
                self.emit_import(name[0], line, "imports_from", "implementing")
            return
        if self.language == "slang" and re.match(r"\s*type_param\b", raw):
            match = re.search(r"\btype_param\s+(\w+)\s*(?::\s*([^;]+))?", raw)
            if match:
                nid = self.add_node(_make_id(self.stem, match.group(1)), match.group(1), line, "generic_parameter", constraints=[match.group(2)] if match.group(2) else None)
                self.add_edge(self.file_nid, nid, "contains", line)
            return
        layout = self.layout(raw)
        direct_tokens = {_read_text(child, self.source) for child in node.children if not child.is_named}
        qualifiers = direct_tokens | set(re.findall(r"\b(?:readonly|writeonly|uniform|buffer|in|out|flat|smooth|centroid|sample|noperspective)\b", raw))
        field_list = next((child for child in node.children if child.type == "field_declaration_list"), None)
        if self.language == "glsl" and field_list is not None:
            field_index = next(index for index, child in enumerate(node.children) if child == field_list)
            block_node = next((child for child in node.children[:field_index] if child.type == "identifier"), None)
            instance = next((child for child in node.children[field_index + 1:] if child.is_named), None)
            block_name = _read_text(block_node, self.source) if block_node is not None else "block"
            name = self.declarator_name(instance) or block_name
            block_layout = self.declarator_layout(instance, layout) if instance is not None else dict(layout)
            is_interface = ("in" in qualifiers or "out" in qualifiers) and "uniform" not in qualifiers and "buffer" not in qualifiers
            if is_interface:
                direction = "input" if "in" in qualifiers else "output"
                nid = self.add_node(
                    _make_id(self.stem, "io", name), name, line, "stage_io_block",
                    type=block_name,
                    interface={
                        "direction": direction,
                        "location": layout.get("location"),
                        "interpolation": sorted(qualifiers & {"flat", "smooth", "centroid", "sample", "noperspective"}),
                    },
                    layout=block_layout,
                )
                self.glsl_io.append((nid, f"stage_{direction}"))
                self.add_edge(self.file_nid, nid, "contains", line)
                self.types.setdefault(block_name, [])
                for child in field_list.children:
                    if child.type == "field_declaration":
                        self.emit_field(child, nid, block_name)
                return
            kind = "push_constant" if layout.get("push_constant") else "storage_buffer" if "buffer" in qualifiers else "uniform_buffer"
            access = "read" if kind != "storage_buffer" or "readonly" in qualifiers else "write" if "writeonly" in qualifiers else "read_write"
            nid = self.add_node(_make_id(self.stem, "resource", name), name, line, kind, type=block_name, access=access, resource_kind=kind, bindings=self.bindings(raw, layout), layout=block_layout, block_name=block_name)
            self.resources[name] = {"nid": nid, "access": access}
            self.add_edge(self.file_nid, nid, "contains", line)
            self.types.setdefault(block_name, [])
            for child in field_list.children:
                if child.type == "field_declaration":
                    self.emit_field(child, nid, block_name)
            return
        declarators = self.declarators(node)
        if self.language == "glsl" and ("in" in qualifiers or "out" in qualifiers) and "uniform" not in qualifiers and "buffer" not in qualifiers:
            direction = "input" if "in" in qualifiers else "output"
            for declarator in declarators:
                name = self.declarator_name(declarator)
                if not name:
                    continue
                io_layout = self.declarator_layout(declarator, layout)
                nid = self.add_node(_make_id(self.stem, "io", name), name, line, "stage_io", type=self.type_text(node), interface={"direction": direction, "location": layout.get("location"), "interpolation": sorted(qualifiers & {"flat", "smooth", "centroid", "sample", "noperspective"})}, layout=io_layout)
                self.glsl_io.append((nid, f"stage_{direction}"))
                self.add_edge(self.file_nid, nid, "contains", line)
            return
        type_name = self.type_text(node)
        if self.language == "hlsl" and type_name in {"cbuffer", "tbuffer"}:
            # The grammar splits these into a declaration plus a detached body;
            # recover the complete block once in recover_known_forms().
            return
        resource = _resource_kind(type_name, qualifiers)
        for declarator in declarators:
            name = self.declarator_name(declarator)
            if not name:
                continue
            decl_layout = self.declarator_layout(declarator, layout)
            if "constant_id" in layout:
                nid = self.add_node(_make_id(self.stem, name), name, line, "specialization_constant", type=type_name, layout=decl_layout)
                self.add_edge(self.file_nid, nid, "contains", line)
                continue
            if resource or "uniform" in qualifiers:
                kind, access = resource or ("uniform", "read")
                nid = self.add_node(_make_id(self.stem, "resource", name), name, line, kind, type=type_name, access=access, resource_kind=kind, bindings=self.bindings(raw, layout), layout=decl_layout)
                self.resources[name] = {"nid": nid, "access": access}
                self.add_edge(self.file_nid, nid, "contains", line)
                self.emit_type_refs(nid, type_name, line, "resource_type")

    def walk(self, node) -> None:
        if node.type == "ERROR":
            return
        if self.emit_imports(node):
            return
        if node.type in ("struct_specifier", "interface_specifier"):
            self.emit_type(node)
            return
        if node.type == "function_definition":
            self.emit_function(node)
            return
        if node.type == "declaration":
            self.emit_declaration(node)
            return
        for child in node.children:
            self.walk(child)

    def glsl_stage(self) -> str:
        match = re.search(r"#\s*pragma\s+shader_stage\s*\(\s*(\w+)\s*\)", self.masked)
        if match:
            return _STAGES.get(match.group(1).lower(), match.group(1).lower())
        if re.search(r"\blayout\s*\([^)]*local_size_[xyz]", self.masked):
            return "compute"
        return "unknown"

    def glsl_thread_group_size(self) -> list[int] | None:
        values: list[int] = []
        for axis in "xyz":
            match = re.search(rf"\blocal_size_{axis}\s*=\s*(\d+)", self.masked)
            values.append(int(match.group(1)) if match else 1)
        return values if any(re.search(rf"\blocal_size_{axis}\s*=", self.masked) for axis in "xyz") else None

    def recover_known_forms(self) -> None:
        if self.language == "slang":
            for match in re.finditer(r"(?m)^\s*__include\s+(?:\"([^\"]+)\"|([\w.]+))\s*;", self.masked):
                self.emit_import(match.group(1) or match.group(2), self.text.count("\n", 0, match.start()) + 1)
            # tree-sitter-slang currently splits an unattributed top-level
            # ParameterBlock declaration into `template_type` + `expression_statement`.
            children = self.root.named_children
            for type_node, declarator in zip(children, children[1:]):
                type_name = _read_text(type_node, self.source).strip()
                if type_node.type != "template_type" or not type_name.startswith("ParameterBlock<"):
                    continue
                if declarator.type != "expression_statement":
                    continue
                name = self.declarator_name(declarator)
                if not name:
                    continue
                line = type_node.start_point[0] + 1
                raw = self.source[type_node.start_byte:declarator.end_byte].decode("utf-8", errors="replace")
                nid = self.add_node(
                    _make_id(self.stem, "resource", name), name, line, "parameter_block",
                    type=type_name, access="read", resource_kind="parameter_block",
                    bindings=self.bindings(raw), layout=self.declarator_layout(declarator),
                )
                self.resources[name] = {"nid": nid, "access": "read"}
                if not any(edge["source"] == self.file_nid and edge["target"] == nid for edge in self.edges):
                    self.add_edge(self.file_nid, nid, "contains", line)
                self.emit_type_refs(nid, type_name, line, "resource_type")
        if self.language != "hlsl":
            return
        # ponytail: flat cbuffer syntax only; compiler reflection is the upgrade path for macro-generated layouts.
        pattern = re.compile(r"\b(cbuffer|tbuffer)\s+(\w+)\s*([^\{;]*)\{([^{}]*)\}\s*;?", re.DOTALL)
        for match in pattern.finditer(self.masked):
            block_kind, name, suffix, body = match.groups()
            line = self.text.count("\n", 0, match.start()) + 1
            resource_kind = "uniform_buffer" if block_kind == "cbuffer" else "texture_buffer"
            nid = self.add_node(_make_id(self.stem, name), name, line, resource_kind, type=block_kind, access="read", resource_kind=resource_kind, bindings=self.bindings(suffix))
            self.resources[name] = {"nid": nid, "access": "read"}
            if not any(edge["source"] == self.file_nid and edge["target"] == nid for edge in self.edges):
                self.add_edge(self.file_nid, nid, "contains", line)
            self.types.setdefault(name, [])
            body_offset = match.start(4)
            for field in re.finditer(r"\s*((?:row_major|column_major|const|static)\s+)*([\w:<>,]+)\s+(\w+)(\s*\[[^;]*?\])?\s*(?::\s*packoffset\s*\(([^)]+)\))?\s*;", body):
                fline = self.text.count("\n", 0, body_offset + field.start()) + 1
                fname, ftype = field.group(3), field.group(2)
                fnid = self.add_node(_make_id(nid, fname), fname, fline, "member", type=ftype, layout={"array_dimensions": re.findall(r"\[\s*([^\]]*)", field.group(4) or ""), "packoffset": field.group(5), "major": (field.group(1) or "").strip() or None})
                self.add_edge(nid, fnid, "contains", fline)
                self.types[name].append({"nid": fnid, "name": fname, "type": ftype, "semantic": None})

    def emit_stage_io(self) -> None:
        for fact in self.functions:
            if not fact["entry"]:
                continue
            if self.language == "glsl":
                for target, relation in self.glsl_io:
                    self.add_edge(fact["nid"], target, relation, int(self.node_by_id[target]["source_location"][1:]))
                continue
            declarator = fact["declarator"]
            params = declarator.child_by_field_name("parameters")
            if params is not None:
                for param in params.children:
                    if param.type != "parameter_declaration":
                        continue
                    ptype = self.type_text(param)
                    pname = self.declarator_name(param.child_by_field_name("declarator")) or "parameter"
                    semantic = self.semantic(param.child_by_field_name("declarator")) or self.semantic(param)
                    raw = _read_text(param, self.source)
                    direction = "inout" if re.search(r"\binout\b", raw) else "output" if re.search(r"\bout\b", raw) else "input"
                    relation = f"stage_{direction}"
                    if semantic:
                        line = param.start_point[0] + 1
                        io = self.add_node(_make_id(fact["nid"], direction, semantic, pname), f"{pname} : {semantic}", line, "stage_io", type=ptype, interface={"direction": direction, "semantic": semantic, "builtin": semantic.upper().startswith("SV_")})
                        self.add_edge(fact["nid"], io, relation, line)
                    elif ptype in self.types:
                        for field in self.types[ptype]:
                            if field.get("semantic"):
                                line = int(self.node_by_id[field["nid"]]["source_location"][1:])
                                self.add_edge(fact["nid"], field["nid"], relation, line, parameter=pname)
            return_semantic = self.semantic(declarator)
            if return_semantic:
                io = self.add_node(_make_id(fact["nid"], "return", return_semantic), f"return : {return_semantic}", fact["node"].start_point[0] + 1, "stage_io", type=fact["return_type"], interface={"direction": "output", "semantic": return_semantic, "builtin": return_semantic.upper().startswith("SV_")})
                self.add_edge(fact["nid"], io, "stage_output", fact["node"].start_point[0] + 1)
            elif fact["return_type"] in self.types:
                for field in self.types[fact["return_type"]]:
                    if field.get("semantic"):
                        self.add_edge(fact["nid"], field["nid"], "stage_output", fact["node"].start_point[0] + 1)

    def emit_calls_and_uses(self) -> None:
        by_name: dict[str, list[dict]] = {}
        for fact in self.functions:
            by_name.setdefault(fact["name"], []).append(fact)
        for fact in self.functions:
            body = fact["body"]
            if body is None:
                continue
            accesses: dict[str, dict[str, int]] = {}
            local_names: set[str] = set()

            def remember_locals(node) -> None:
                if node.type in ("parameter_declaration", "declaration"):
                    for declarator in self.declarators(node):
                        if name := self.declarator_name(declarator):
                            local_names.add(name)
                for child in node.children:
                    remember_locals(child)

            params = fact["declarator"].child_by_field_name("parameters")
            if params is not None:
                remember_locals(params)
            remember_locals(body)

            def access(name: str, mode: str, line: int) -> None:
                if name in self.resources and name not in local_names:
                    locations = accesses.setdefault(name, {})
                    locations[mode] = min(line, locations.get(mode, line))

            def visit(node, mode: str = "read") -> None:
                if node.type == "assignment_expression":
                    left, right = node.child_by_field_name("left"), node.child_by_field_name("right")
                    if left is not None:
                        visit(left, "write")
                    if right is not None:
                        visit(right, "read")
                    return
                if node.type == "update_expression":
                    for child in node.children:
                        visit(child, "read_write")
                    return
                if node.type == "call_expression":
                    fn = node.child_by_field_name("function")
                    args = node.child_by_field_name("arguments")
                    call_name = None
                    if fn is not None and fn.type == "identifier":
                        call_name = fn
                    elif fn is not None and fn.type == "template_function":
                        call_name = fn.child_by_field_name("name") or self.descendant(fn, {"identifier"})
                    if call_name is not None:
                        callee = _read_text(call_name, self.source)
                        arg_nodes = [child for child in args.children if child.is_named] if args is not None else []
                        if callee in {"imageStore"} and arg_nodes:
                            visit(arg_nodes[0], "write")
                            for arg in arg_nodes[1:]:
                                visit(arg)
                        else:
                            for arg in arg_nodes:
                                visit(arg)
                        targets = {target["nid"] for target in by_name.get(callee, []) if target["arity"] == len(arg_nodes)}
                        if len(targets) == 1:
                            self.add_edge(fact["nid"], next(iter(targets)), "calls", node.start_point[0] + 1, context="call")
                        elif not targets and callee not in _INTRINSICS and not _is_builtin_type(callee) and callee not in self.types:
                            self.raw_calls.append({
                                "caller_nid": fact["nid"], "callee": callee,
                                "arg_count": len(arg_nodes), "is_member_call": False,
                                "language": "shader", "source_file": self.str_path,
                                "source_location": f"L{node.start_point[0] + 1}",
                            })
                        return
                    if fn is not None and fn.type == "field_expression":
                        receiver = fn.child_by_field_name("argument")
                        method = fn.child_by_field_name("field")
                        method_name = _read_text(method, self.source).lower() if method is not None else ""
                        if method_name in {"store", "append", "incrementcounter", "decrementcounter"}:
                            receiver_mode = "write"
                        elif method_name.startswith("interlocked") or method_name.startswith("atomic"):
                            receiver_mode = "read_write"
                        else:
                            receiver_mode = "read"
                        if receiver is not None:
                            visit(receiver, receiver_mode)
                        if args is not None:
                            for child in args.children:
                                if child.is_named:
                                    visit(child)
                        return
                if node.type == "identifier":
                    access(_read_text(node, self.source), mode, node.start_point[0] + 1)
                    return
                for child in node.children:
                    visit(child, mode)

            visit(body)
            for name, locations in accesses.items():
                modes = set(locations)
                access_name = "read_write" if "read_write" in modes or {"read", "write"} <= modes else next(iter(modes))
                self.add_edge(fact["nid"], self.resources[name]["nid"], "uses", min(locations.values()), access=access_name)

    def result(self) -> dict:
        self.add_node(self.file_nid, self.path.name, 1, "file")
        self.walk(self.root)
        self.recover_known_forms()
        self.emit_stage_io()
        self.emit_calls_and_uses()
        errors = []
        stack = [self.root]
        while stack:
            node = stack.pop()
            if node.type == "ERROR" or node.is_missing:
                errors.append(node)
            stack.extend(node.children)
        if errors:
            shader = self.node_by_id[self.file_nid]["metadata"]["shader"]
            shader.update({"parse_error_count": len(errors), "reflection_partial": True})
        result = {"nodes": self.nodes, "edges": self.edges, "raw_calls": self.raw_calls}
        if errors:
            result["parse_errors"] = {
                "first_error_line": min(node.start_point[0] + 1 for node in errors),
                "multiline_error": any(node.end_point[0] > node.start_point[0] for node in errors),
                "count": len(errors),
            }
        return result


def _extract(path: Path, language: str) -> dict:
    try:
        module = importlib.import_module(_MODULES[language])
        from tree_sitter import Language, Parser

        # HLSL/GLSL 0.2 still expose an integer language pointer. Tree-sitter
        # 0.25 supports it but warns; the <0.26 dependency cap preserves this
        # compatibility until those grammar wheels move to PyCapsule.
        with warnings.catch_warnings():
            warnings.filterwarnings(
                "ignore", message="int argument support is deprecated",
                category=DeprecationWarning,
            )
            ts_language = Language(module.language())
        parser = Parser(ts_language)
        source = path.read_bytes()
        root = parser.parse(source).root_node
    except ImportError:
        return {"nodes": [], "edges": [], "error": f"{_MODULES[language]} not installed"}
    except Exception as exc:
        return {"nodes": [], "edges": [], "error": str(exc)}
    return _Extractor(path, language, source, root).result()


def extract_hlsl(path: Path) -> dict:
    """Reflect HLSL/HLSLI declarations, entry points, resources, calls, and includes."""
    return _extract(path, "hlsl")


def extract_glsl(path: Path) -> dict:
    """Reflect generic .glsl declarations, resources, stage I/O, and calls."""
    return _extract(path, "glsl")


def extract_slang(path: Path) -> dict:
    """Reflect Slang modules, interfaces/generics, resources, entry points, and calls."""
    return _extract(path, "slang")
