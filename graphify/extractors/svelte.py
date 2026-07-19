"""Svelte author-AST extraction backed by a bundled ``svelte/compiler`` bridge.

The bridge uses ``parse(source, { modern: true })`` and returns compact facts at
the original author offsets.  Graphify never compiles components to generated
JavaScript.  Christian Winther's masking work in upstream PR #714 established
the original import-recovery requirement; this implementation retains that
credit while replacing source regexes with compiler-owned script ranges.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
from collections import OrderedDict
from dataclasses import dataclass
from importlib.resources import as_file, files
from pathlib import Path
from typing import Any, Iterable, Mapping

from graphify.extractors.base import _file_stem, _make_id, _read_text


SVELTE_AST_SCHEMA_VERSION = 2
SVELTE_COMPILER_VERSION = "5.56.6"
SVELTE2TSX_VERSION = "0.7.58"
TYPESCRIPT_VERSION = "5.9.3"
SVELTE_AST_CACHE_MAX_ENTRIES = 256
# Bound one Node request independently of the extraction-scoped fact context.
# The bridge performs TypeScript binding analysis per author source; an
# unbounded monorepo request can exceed the subprocess timeout and otherwise
# degrade every Svelte file together. Smaller requests also isolate a genuinely
# expensive or malformed source to one bounded group.
SVELTE_AST_BRIDGE_BATCH_MAX_FILES = 32
_BRIDGE_CACHE: OrderedDict[str, dict[str, Any]] = OrderedDict()


@dataclass(frozen=True)
class SvelteSourceFacts:
    """One compiler-owned author source within a top-level extraction."""

    path: Path
    source: str
    facts: dict[str, Any]

    @property
    def canonical_path(self) -> Path:
        return self.path.resolve()

    def masked_script(self, script: Mapping[str, Any]) -> bytes:
        return mask_svelte_script_facts(self.source, self.facts, script=script)


@dataclass(frozen=True)
class SvelteExtractionContext:
    """Extraction-scoped owner for source text and compiler facts.

    The process-global LRU can avoid compiler work across later watch runs, but
    downstream consumers always resolve through this canonical mapping. Thus an
    entry evicted while a large batch is cached cannot be parsed again during
    the extraction that already owns it.
    """

    by_canonical_path: dict[Path, SvelteSourceFacts]

    @classmethod
    def parse(cls, sources: Mapping[Path, str]) -> "SvelteExtractionContext":
        canonical_sources: dict[Path, str] = {}
        for path, source in sources.items():
            canonical_sources.setdefault(path.resolve(), source)
        parsed = parse_svelte_ast_batch(list(canonical_sources.items()))
        return cls({
            path: SvelteSourceFacts(path=path, source=source, facts=parsed[path])
            for path, source in canonical_sources.items()
        })

    @classmethod
    def read(cls, paths: Iterable[Path]) -> "SvelteExtractionContext":
        sources: dict[Path, str] = {}
        for path in paths:
            if path.suffix != ".svelte":
                continue
            try:
                sources[path] = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
        return cls.parse(sources)

    def get(self, path: Path) -> SvelteSourceFacts | None:
        return self.by_canonical_path.get(path.resolve())


def _diagnostic(code: str, message: str) -> dict[str, Any]:
    return {"code": code, "message": message, "degraded": True}


def _cache_key(path: Path, source: str) -> str:
    digest = hashlib.sha256()
    digest.update(source.encode("utf-8"))
    digest.update(b"\0modern=true\0")
    digest.update(str(SVELTE_AST_SCHEMA_VERSION).encode("ascii"))
    digest.update(b"\0")
    digest.update(SVELTE_COMPILER_VERSION.encode("ascii"))
    digest.update(b"\0")
    digest.update(SVELTE2TSX_VERSION.encode("ascii"))
    digest.update(b"\0")
    digest.update(TYPESCRIPT_VERSION.encode("ascii"))
    digest.update(b"\0")
    try:
        canonical_path = path.resolve()
    except OSError:
        canonical_path = path
    digest.update(str(canonical_path).encode("utf-8", errors="replace"))
    digest.update(b"\0")
    for parent in (canonical_path.parent, *canonical_path.parents):
        config = next(
            (
                parent / name
                for name in ("tsconfig.json", "jsconfig.json")
                if (parent / name).is_file()
            ),
            None,
        )
        if config is None:
            continue
        try:
            digest.update(config.read_bytes())
        except OSError:
            digest.update(str(config).encode("utf-8", errors="replace"))
        break
    return digest.hexdigest()


def _cache_put(key: str, fact: dict[str, Any]) -> None:
    _BRIDGE_CACHE[key] = fact
    _BRIDGE_CACHE.move_to_end(key)
    while len(_BRIDGE_CACHE) > SVELTE_AST_CACHE_MAX_ENTRIES:
        _BRIDGE_CACHE.popitem(last=False)


def clear_svelte_ast_cache() -> None:
    """Clear the in-process compiler fact cache (primarily for watch/tests)."""
    _BRIDGE_CACHE.clear()


def svelte_ast_cache_info() -> dict[str, int]:
    """Return bounded cache statistics without exposing cache contents."""
    return {
        "entries": len(_BRIDGE_CACHE),
        "max_entries": SVELTE_AST_CACHE_MAX_ENTRIES,
    }


def _node_executable() -> str | None:
    configured = os.environ.get("GRAPHIFY_NODE", "node").strip() or "node"
    return shutil.which(configured)


def _invoke_svelte_bridge(request: dict[str, Any]) -> dict[str, Any]:
    node = _node_executable()
    if node is None:
        raise RuntimeError("Node.js is not installed or not on PATH")
    resource = files("graphify").joinpath("vendor/svelte_ast_bridge.mjs")
    with as_file(resource) as bridge_path:
        completed = subprocess.run(  # noqa: S603 - fixed packaged bridge + discovered node
            [node, str(bridge_path)],
            input=json.dumps(request, ensure_ascii=False),
            encoding="utf-8",
            capture_output=True,
            timeout=60,
            check=False,
        )
    if completed.returncode != 0:
        detail = completed.stderr.strip() or f"bridge exited {completed.returncode}"
        raise RuntimeError(detail)
    try:
        response = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"bridge returned invalid JSON: {exc}") from exc
    if response.get("schema_version") != SVELTE_AST_SCHEMA_VERSION:
        raise RuntimeError(
            "Svelte AST bridge schema mismatch: "
            f"expected {SVELTE_AST_SCHEMA_VERSION}, got {response.get('schema_version')}"
        )
    if response.get("compiler_version") != SVELTE_COMPILER_VERSION:
        raise RuntimeError(
            "Svelte compiler version mismatch: "
            f"expected {SVELTE_COMPILER_VERSION}, got {response.get('compiler_version')}"
        )
    if response.get("svelte2tsx_version") != SVELTE2TSX_VERSION:
        raise RuntimeError(
            "svelte2tsx version mismatch: "
            f"expected {SVELTE2TSX_VERSION}, got {response.get('svelte2tsx_version')}"
        )
    if response.get("typescript_version") != TYPESCRIPT_VERSION:
        raise RuntimeError(
            "TypeScript version mismatch: "
            f"expected {TYPESCRIPT_VERSION}, got {response.get('typescript_version')}"
        )
    return response


def parse_svelte_ast_batch(items: list[tuple[Path, str]]) -> dict[Path, dict[str, Any]]:
    """Parse a batch once and return compiler facts keyed by input path.

    Cache identity includes source, bridge schema/config, compiler version, and
    filename.  Failures are explicit per-file diagnostics; no regex extraction
    is attempted when the Node runtime or bridge is unavailable.
    """
    output: dict[Path, dict[str, Any]] = {}
    missing: list[tuple[Path, str, str]] = []
    for path, source in items:
        key = _cache_key(path, source)
        cached = _BRIDGE_CACHE.get(key)
        if cached is not None:
            _BRIDGE_CACHE.move_to_end(key)
            output[path] = cached
        else:
            missing.append((path, source, key))
    if not missing:
        return output

    for batch_start in range(0, len(missing), SVELTE_AST_BRIDGE_BATCH_MAX_FILES):
        batch = missing[
            batch_start:batch_start + SVELTE_AST_BRIDGE_BATCH_MAX_FILES
        ]
        request_files = [
            {"id": str(index), "path": str(path.resolve()), "source": source}
            for index, (path, source, _key) in enumerate(batch)
        ]
        try:
            response = _invoke_svelte_bridge(
                {"schema_version": SVELTE_AST_SCHEMA_VERSION, "files": request_files}
            )
        except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
            for path, _source, key in batch:
                fact = {
                    "diagnostics": [
                        _diagnostic(
                            "svelte_ast_unavailable",
                            f"Svelte AST unavailable: {exc}",
                        )
                    ]
                }
                _cache_put(key, fact)
                output[path] = fact
            continue

        by_id = {
            str(item.get("id")): item
            for item in response.get("files", [])
            if isinstance(item, dict)
        }
        for index, (path, _source, key) in enumerate(batch):
            fact = by_id.get(str(index))
            if fact is None:
                fact = {
                    "diagnostics": [
                        _diagnostic(
                            "svelte_ast_missing_result",
                            "Svelte AST bridge omitted this source from its response",
                        )
                    ]
                }
            _cache_put(key, fact)
            output[path] = fact
    return output


def mask_svelte_script_facts(
    source: str,
    facts: dict[str, Any],
    *,
    language: str | None = None,
    script: Mapping[str, Any] | None = None,
) -> bytes:
    """Keep compiler-identified script bytes and blank all other UTF-8 bytes.

    Passing ``script`` selects one compiler-owned lexical program. Selecting by
    language remains available for compatibility helpers, but semantic callers
    parse scripts independently so module and instance scopes never merge.
    """
    encoded = source.encode("utf-8")
    output = bytearray(byte if byte in (10, 13) else 32 for byte in encoded)
    scripts = [script] if script is not None else facts.get("scripts", [])
    for candidate in scripts:
        if not isinstance(candidate, Mapping):
            continue
        if language is not None and candidate.get("language") != language:
            continue
        start = candidate.get("start_byte")
        end = candidate.get("end_byte")
        if not isinstance(start, int) or not isinstance(end, int):
            continue
        if 0 <= start <= end <= len(encoded):
            output[start:end] = encoded[start:end]
    return bytes(output)


def svelte_script_facts(facts: dict[str, Any]) -> list[dict[str, Any]]:
    """Return valid compiler script facts in author order."""
    return sorted(
        (
            script
            for script in facts.get("scripts", [])
            if isinstance(script, dict)
            and script.get("context") in ("module", "default")
            and script.get("language") in ("js", "ts")
            and isinstance(script.get("start_byte"), int)
            and isinstance(script.get("end_byte"), int)
        ),
        key=lambda script: int(script["start_byte"]),
    )


def svelte_script_languages(facts: dict[str, Any]) -> set[str]:
    """Return compiler-identified JS/TS script languages from parsed facts."""
    return {
        str(script.get("language"))
        for script in facts.get("scripts", [])
        if script.get("language") in ("js", "ts")
    }


def has_fatal_svelte_diagnostics(facts: dict[str, Any]) -> bool:
    """Return whether compiler diagnostics prevent author-AST extraction."""
    return any(
        not (
            isinstance(item, dict)
            and item.get("code") == "svelte_semantic_unavailable"
        )
        for item in facts.get("diagnostics", [])
    )


def _fact_metadata(fact: dict[str, Any], **extra: object) -> dict[str, object]:
    metadata: dict[str, object] = {
        "start_offset": fact.get("start"),
        "end_offset": fact.get("end"),
        "start_byte": fact.get("start_byte"),
        "end_byte": fact.get("end_byte"),
    }
    metadata.update(extra)
    return {key: value for key, value in metadata.items() if value is not None}


def augment_svelte_component(
    path: Path,
    source: str,
    facts: dict[str, Any],
    result: dict[str, Any],
    *,
    include_standalone_dynamic_targets: bool = True,
) -> None:
    """Create author-site nodes; canonical cross-file targets are joined later."""
    file_nid = _make_id(str(path))
    nodes = result.setdefault("nodes", [])
    edges = result.setdefault("edges", [])
    node_ids = {node.get("id") for node in nodes}
    edge_keys = {
        (
            edge.get("source"),
            edge.get("target"),
            edge.get("relation"),
            edge.get("source_location"),
            edge.get("context"),
        )
        for edge in edges
    }

    def add_node(
        nid: str,
        label: str,
        kind: str,
        fact: dict[str, Any],
        **metadata: object,
    ) -> None:
        if nid in node_ids:
            return
        node_ids.add(nid)
        nodes.append(
            {
                "id": nid,
                "label": label,
                "file_type": "code",
                "type": kind,
                "source_file": str(path),
                "source_location": f"L{fact['line']}",
                "metadata": _fact_metadata(fact, **metadata),
            }
        )

    def add_edge(
        source_id: str,
        target_id: str,
        relation: str,
        fact: dict[str, Any],
        context: str,
        **metadata: object,
    ) -> None:
        location = f"L{fact['line']}"
        key = (source_id, target_id, relation, location, context)
        if key in edge_keys:
            return
        edge_keys.add(key)
        edges.append(
            {
                "source": source_id,
                "target": target_id,
                "relation": relation,
                "context": context,
                "confidence": "EXTRACTED",
                "confidence_score": 1.0,
                "source_file": str(path),
                "source_location": location,
                "weight": 1.0,
                "metadata": _fact_metadata(fact, **metadata),
            }
        )

    for construction in facts.get("constructions", []):
        binding = construction.get("binding")
        constructor = construction.get("constructor")
        if not (isinstance(binding, str) and isinstance(constructor, str)):
            continue
        owner = _make_id(file_nid, "construction", binding, str(construction["start"]))
        add_node(
            owner,
            f"new {constructor}()",
            "svelte_construction",
            construction,
            binding=binding,
            binding_id=construction.get("binding_id"),
            constructor_binding_id=construction.get("constructor_binding_id"),
            type=constructor,
        )
        add_edge(file_nid, owner, "contains", construction, "svelte_construction")

    for prop in facts.get("props", []):
        binding = prop.get("binding")
        public = prop.get("public")
        type_name = prop.get("type_name")
        if not (
            isinstance(binding, str)
            and isinstance(public, str)
            and isinstance(type_name, str)
        ):
            continue
        owner = _make_id(file_nid, "prop", public, str(prop["start"]))
        add_node(
            owner,
            f"{public}: {type_name}",
            "svelte_prop",
            prop,
            prop=public,
            binding=binding,
            binding_id=prop.get("binding_id"),
            type_binding_id=prop.get("type_binding_id"),
            type=type_name,
        )
        add_edge(file_nid, owner, "contains", prop, "component_prop")

    for component in facts.get("components", []):
        tag = component.get("name")
        if not isinstance(tag, str):
            continue
        local = component.get("local")
        if not isinstance(local, str):
            local = tag.split(".", 1)[0]
        usage = _make_id(file_nid, "render", tag, str(component["start"]))
        add_node(
            usage,
            f"<{tag}>",
            "svelte_component_usage",
            component,
            tag=tag,
            imported_as=local,
            binding_id=component.get("binding_id"),
        )
        add_edge(file_nid, usage, "contains", component, "component_usage")

    if include_standalone_dynamic_targets:
        from graphify.extractors.resolution import (
            _canonical_js_file_identity,
            _resolve_js_module_path,
        )

        for imported in facts.get("dynamic_imports", []):
            raw = imported.get("source")
            if not isinstance(raw, str) or not raw:
                continue
            target_path = _resolve_js_module_path(raw, path.parent)
            if target_path is None or not target_path.is_file():
                continue
            canonical_path, target_id = _canonical_js_file_identity(target_path)
            if target_id not in node_ids:
                add_node(
                    target_id,
                    canonical_path.name,
                    "module",
                    imported,
                    module=raw,
                    resolved=True,
                )
                nodes[-1]["source_file"] = str(canonical_path)
            add_edge(
                file_nid,
                target_id,
                "dynamic_import",
                imported,
                "dynamic_import",
                module=raw,
                surface=imported.get("surface"),
            )
    result["svelte_ast_facts"] = facts


def augment_svelte_semantic_edges(
    paths: list[Path],
    per_file: list[dict[str, Any] | None],
    nodes: list[dict[str, Any]],
    edges: list[dict[str, Any]],
    root: Path,
    *,
    svelte_context: SvelteExtractionContext | None = None,
) -> None:
    """Join Svelte author facts to canonical node identities emitted by the resolver."""
    del root  # canonical identities come from existing nodes, never recomputed paths
    node_by_id = {str(node.get("id")): node for node in nodes if node.get("id")}
    file_id_by_path = {path.resolve(): _make_id(str(path)) for path in paths}
    edge_keys = {
        (
            edge.get("source"), edge.get("target"), edge.get("relation"),
            edge.get("source_location"), edge.get("context"),
        )
        for edge in edges
    }

    def add_edge(
        source: str,
        target: str,
        relation: str,
        fact: dict[str, Any],
        context: str,
        path: Path,
        **metadata: object,
    ) -> None:
        if source not in node_by_id or target not in node_by_id:
            return
        location = f"L{fact['line']}"
        key = (source, target, relation, location, context)
        if key in edge_keys:
            return
        edge_keys.add(key)
        edges.append({
            "source": source,
            "target": target,
            "relation": relation,
            "context": context,
            "confidence": "EXTRACTED",
            "confidence_score": 1.0,
            "source_file": str(path),
            "source_location": location,
            "weight": 1.0,
            "metadata": _fact_metadata(fact, **metadata),
        })

    method_targets: dict[tuple[str, str], str] = {}
    for edge in edges:
        if edge.get("relation") != "method":
            continue
        target = node_by_id.get(str(edge.get("target")))
        if target is None:
            continue
        member = str(target.get("label", "")).lstrip(".").removesuffix("()")
        if member:
            method_targets[(str(edge.get("source")), member)] = str(edge.get("target"))

    results_by_path: dict[Path, tuple[Path, dict[str, Any]]] = {}
    for path, result in zip(paths, per_file):
        if not isinstance(result, dict):
            continue
        source_facts = svelte_context.get(path) if svelte_context is not None else None
        facts = source_facts.facts if source_facts is not None else result.get("svelte_ast_facts")
        if isinstance(facts, dict):
            results_by_path[path.resolve()] = (path, facts)
    for resolved_path, (path, facts) in results_by_path.items():
        file_id = file_id_by_path.get(resolved_path)
        if file_id is None or file_id not in node_by_id:
            continue

        target_by_binding: dict[str, str] = {}
        for edge in edges:
            if edge.get("relation") != "imports" or edge.get("source") != file_id:
                continue
            target = str(edge.get("target"))
            if target not in node_by_id:
                continue
            metadata = edge.get("metadata") or {}
            aliases = metadata.get("aliases", []) if isinstance(metadata, dict) else []
            if not aliases and isinstance(metadata, dict):
                aliases = [metadata]
            for alias in aliases:
                if not isinstance(alias, dict):
                    continue
                binding_id = alias.get("binding_id")
                if isinstance(binding_id, str):
                    target_by_binding[binding_id] = target

        def imported_target(binding_id: object) -> str | None:
            return target_by_binding.get(binding_id) if isinstance(binding_id, str) else None

        typed_values: dict[str, tuple[str, str]] = {}
        for construction in facts.get("constructions", []):
            binding_id = construction.get("binding_id")
            target = imported_target(construction.get("constructor_binding_id"))
            if not isinstance(binding_id, str) or target is None:
                continue
            owner = _make_id(
                file_id, "construction", str(construction.get("binding")),
                str(construction["start"]),
            )
            target_label = str(node_by_id[target].get("label", construction.get("constructor")))
            add_edge(
                owner, target, "instantiates", construction, "constructor", path,
                binding=construction.get("binding"), type=target_label,
            )
            typed_values[binding_id] = (target, owner)

        for prop in facts.get("props", []):
            binding_id = prop.get("binding_id")
            target = imported_target(prop.get("type_binding_id"))
            if not isinstance(binding_id, str) or target is None:
                continue
            owner = _make_id(file_id, "prop", str(prop.get("public")), str(prop["start"]))
            target_label = str(node_by_id[target].get("label", prop.get("type_name")))
            add_edge(
                owner, target, "references", prop, "component_prop_type", path,
                prop=prop.get("public"), binding=prop.get("binding"), type=target_label,
            )
            typed_values[binding_id] = (target, owner)

        for component in facts.get("components", []):
            tag = component.get("name")
            target = imported_target(component.get("binding_id"))
            target_node = node_by_id.get(str(target)) if target is not None else None
            if not (
                isinstance(tag, str)
                and target_node is not None
                and str(target_node.get("source_file", "")).endswith(".svelte")
            ):
                continue
            usage = _make_id(file_id, "render", tag, str(component["start"]))
            add_edge(
                usage, str(target), "renders", component, "component_tag", path,
                tag=tag, imported_as=component.get("local") or tag.split(".", 1)[0],
            )
            for passed in component.get("props", []):
                typed = typed_values.get(str(passed.get("binding_id")))
                if typed is None:
                    continue
                type_target, owner = typed
                add_edge(
                    owner, usage, "passes_prop", passed, "component_prop", path,
                    prop=passed.get("prop"), binding=passed.get("binding"),
                    type=node_by_id[type_target].get("label"),
                )

        for member in facts.get("template_members", []):
            typed = typed_values.get(str(member.get("binding_id")))
            member_name = member.get("member")
            if typed is None or not isinstance(member_name, str):
                continue
            type_target, owner = typed
            target = method_targets.get((type_target, member_name))
            if target is None:
                target_source = node_by_id[type_target].get("source_file")
                target = next(
                    (
                        node_id for node_id, node in node_by_id.items()
                        if node.get("source_file") == target_source
                        and str(node.get("label", "")).lstrip(".").removesuffix("()") == member_name
                    ),
                    None,
                )
            if target is None:
                continue
            add_edge(
                owner,
                target,
                "calls" if member.get("call") else "accesses",
                member,
                "template_method_call" if member.get("call") else "template_member_read",
                path,
                binding=member.get("binding"), member=member_name,
                type=node_by_id[type_target].get("label"),
            )

        from graphify.extractors.resolution import _resolve_js_module_path
        for imported in facts.get("dynamic_imports", []):
            raw = imported.get("source")
            if not isinstance(raw, str) or not raw:
                continue
            target_path = _resolve_js_module_path(raw, path.parent)
            target = file_id_by_path.get(target_path.resolve()) if target_path is not None else None
            if target is None:
                continue
            add_edge(
                file_id, target, "dynamic_import", imported, "dynamic_import", path,
                module=raw, surface=imported.get("surface"),
            )


def augment_svelte_runes(path: Path, result: dict[str, Any]) -> None:
    """Represent exact compiler-recognised rune calls in original module source."""
    if not (path.name.endswith(".svelte.ts") or path.name.endswith(".svelte.js")):
        return
    try:
        from tree_sitter import Language, Parser

        if path.name.endswith(".ts"):
            import tree_sitter_typescript as grammar

            language = Language(grammar.language_typescript())
        else:
            import tree_sitter_javascript as grammar

            language = Language(grammar.language())
        source = path.read_bytes()
        root = Parser(language).parse(source).root_node
    except Exception:
        return

    nodes = result.setdefault("nodes", [])
    edges = result.setdefault("edges", [])
    seen_nodes = {node.get("id") for node in nodes}
    seen_edges = {
        (edge.get("source"), edge.get("target"), edge.get("relation"), edge.get("source_location"))
        for edge in edges
    }

    def walk(node):
        yield node
        for child in node.children:
            yield from walk(child)

    def add_node(nid: str, label: str, kind: str, line: int, rune: str) -> None:
        if nid in seen_nodes:
            return
        seen_nodes.add(nid)
        nodes.append(
            {
                "id": nid,
                "label": label,
                "file_type": "code",
                "type": kind,
                "source_file": str(path),
                "source_location": f"L{line}",
                "metadata": {"svelte_rune": rune, "static_certainty": "syntactic"},
            }
        )

    def add_edge(source_id: str, target_id: str, relation: str, line: int, context: str) -> None:
        key = (source_id, target_id, relation, f"L{line}")
        if key in seen_edges:
            return
        seen_edges.add(key)
        edges.append(
            {
                "source": source_id,
                "target": target_id,
                "relation": relation,
                "context": context,
                "confidence": "EXTRACTED",
                "confidence_score": 1.0,
                "source_file": str(path),
                "source_location": f"L{line}",
                "weight": 1.0,
                "metadata": {"static_certainty": "syntactic"},
            }
        )

    member_runes = {
        "$state": ("state", "svelte_state"),
        "$state.raw": ("state.raw", "svelte_state"),
        "$derived": ("derived", "svelte_derived"),
        "$derived.by": ("derived.by", "svelte_derived"),
    }
    effect_runes = {"$effect", "$effect.pre", "$effect.root"}

    def rune_callee(call) -> str:
        function = call.child_by_field_name("function")
        if function is None:
            return ""
        if function.type == "identifier":
            name = _read_text(function, source)
            return name if name in {"$state", "$derived", "$effect"} else ""
        if function.type != "member_expression":
            return ""
        obj = function.child_by_field_name("object")
        prop = function.child_by_field_name("property")
        if obj is None or prop is None or obj.type != "identifier" or prop.type != "property_identifier":
            return ""
        qualified = f"{_read_text(obj, source)}.{_read_text(prop, source)}"
        return qualified if qualified in member_runes or qualified in effect_runes else ""

    for class_node in (node for node in walk(root) if node.type == "class_declaration"):
        name_node = class_node.child_by_field_name("name")
        body = class_node.child_by_field_name("body")
        if name_node is None or body is None:
            continue
        class_name = _read_text(name_node, source)
        class_nid = _make_id(_file_stem(path), class_name)
        rune_members: dict[str, tuple[str, object, int]] = {}
        initialized_fields: set[str] = set()
        for field in body.children:
            if field.type not in ("public_field_definition", "field_definition"):
                continue
            name = field.child_by_field_name("name")
            value = field.child_by_field_name("value")
            if name is None or value is None:
                continue
            field_name = _read_text(name, source).lstrip("#")
            initialized_fields.add(field_name)
            if value.type != "call_expression":
                continue
            rune_info = member_runes.get(rune_callee(value))
            if rune_info is None:
                continue
            rune, kind = rune_info
            line = field.start_point[0] + 1
            field_nid = _make_id(class_nid, field_name)
            rune_members[field_name] = (field_nid, value, line)
            add_node(field_nid, f".{field_name}", kind, line, rune)
            add_edge(class_nid, field_nid, "contains", line, "svelte_rune_member")

        # Svelte also permits `$state` as the first assignment to a property
        # immediately inside a constructor. Restrict this to direct constructor
        # statements and track first assignment per property; nested/control-flow
        # uses are not compiler-valid declarations.
        assigned_in_constructor = set(initialized_fields)
        for method in body.children:
            if method.type != "method_definition":
                continue
            method_name = method.child_by_field_name("name")
            method_body = method.child_by_field_name("body")
            if (
                method_name is None
                or method_body is None
                or _read_text(method_name, source) != "constructor"
            ):
                continue
            for statement in method_body.children:
                if statement.type != "expression_statement":
                    continue
                assignment = next(
                    (child for child in statement.children if child.is_named),
                    None,
                )
                if assignment is None or assignment.type != "assignment_expression":
                    continue
                left = assignment.child_by_field_name("left")
                right = assignment.child_by_field_name("right")
                if left is None or left.type != "member_expression":
                    continue
                obj = left.child_by_field_name("object")
                prop = left.child_by_field_name("property")
                if obj is None or prop is None or _read_text(obj, source) != "this":
                    continue
                field_name = _read_text(prop, source).lstrip("#")
                if field_name in assigned_in_constructor:
                    continue
                assigned_in_constructor.add(field_name)
                if right is None or right.type != "call_expression":
                    continue
                callee = rune_callee(right)
                rune_info = member_runes.get(callee)
                if rune_info is None or rune_info[1] != "svelte_state":
                    continue
                rune, kind = rune_info
                line = assignment.start_point[0] + 1
                field_nid = _make_id(class_nid, field_name)
                rune_members[field_name] = (field_nid, right, line)
                add_node(field_nid, f".{field_name}", kind, line, rune)
                add_edge(class_nid, field_nid, "contains", line, "svelte_rune_member")

        def dependencies(node) -> set[str]:
            found: set[str] = set()
            for descendant in walk(node):
                if descendant.type != "member_expression":
                    continue
                obj = descendant.child_by_field_name("object")
                prop = descendant.child_by_field_name("property")
                if obj is not None and prop is not None and _read_text(obj, source) == "this":
                    name = _read_text(prop, source).lstrip("#")
                    if name in rune_members:
                        found.add(name)
            return found

        for name, (member_nid, value, line) in rune_members.items():
            result_node = next((node for node in nodes if node.get("id") == member_nid), None)
            if result_node is None or result_node.get("type") != "svelte_derived":
                continue
            for dependency in dependencies(value):
                if dependency != name:
                    add_edge(
                        member_nid,
                        rune_members[dependency][0],
                        "depends_on",
                        line,
                        "svelte_rune_dependency",
                    )

        for call in (node for node in walk(body) if node.type == "call_expression"):
            callee = rune_callee(call)
            if callee not in effect_runes:
                continue
            line = call.start_point[0] + 1
            effect_nid = _make_id(class_nid, "effect", str(line))
            add_node(effect_nid, f"{callee}@L{line}", "svelte_effect", line, callee[1:])
            add_edge(class_nid, effect_nid, "contains", line, "svelte_rune_effect")
            for dependency in dependencies(call):
                add_edge(
                    effect_nid,
                    rune_members[dependency][0],
                    "depends_on",
                    line,
                    "svelte_rune_dependency",
                )
