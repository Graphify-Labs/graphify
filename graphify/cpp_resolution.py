"""Conservative C++ type lookup for declared member-call receivers.

This is lexical name lookup, not a C++ compiler: dependent types, alias templates,
transitive using directives and arbitrary template specializations remain unresolved.
"""
from __future__ import annotations

import re
import posixpath
from bisect import bisect_left


_IDENTIFIER = r"(?:::)?[A-Za-z_]\w*(?:::[A-Za-z_]\w*)*"


class CppTypeLookup:
    """Reuse persisted AST facts while keeping scope/include lookup out of extract.py."""

    def __init__(self, nodes: list[dict], edges: list[dict]):
        self.nodes = {n["id"]: n for n in nodes}
        self.files = {n["id"]: n for n in nodes if "_cpp_type_bindings" in n}
        self.bindings: dict[str, list[tuple[str, dict]]] = {}
        self.types: dict[str, set[str]] = {}
        self.class_scopes: set[str] = set()
        self.imports: dict[str, list[tuple[str, int]]] = {}
        self.namespaces: set[str] = set()
        self.directives: dict[str, list[tuple[str, dict]]] = {}
        self._reachable_cache: dict[tuple[str, int], frozenset[str]] = {}
        self._member_cache: dict[tuple[str, str, str, int], str | bool | None] = {}
        for node in self.files.values():
            source = node["source_file"]
            for binding in node["_cpp_type_bindings"]:
                identity = "::".join(filter(None, (binding["scope"], binding["name"])))
                if binding.get("complete"):
                    self.class_scopes.add(identity)
                if binding["namespace"]:
                    self.namespaces.add(identity)
                if binding["directive"]:
                    self.directives.setdefault(binding["scope"], []).append((source, binding))
                    continue
                self.bindings.setdefault(identity, []).append((source, binding))
        for node in nodes:
            if "_cpp_fields" in node and node.get("_cpp_qualified"):
                self.types.setdefault(node["_cpp_qualified"], set()).add(node["id"])
        files_by_source = {node["source_file"]: node for node in self.files.values()}
        files_by_path = {posixpath.normpath(path.replace("\\", "/")): node
                         for path, node in files_by_source.items()}
        for edge in edges:
            source = self.files.get(edge.get("source"))
            target = self.files.get(edge.get("target"))
            if target is None:
                target = files_by_source.get(self.nodes.get(edge.get("target"), {}).get("source_file"))
            if edge.get("relation") == "imports" and source:
                line = str(edge.get("source_location", "")).removeprefix("L")
                position = source.get("_cpp_include_positions", {}).get(line)
                path = source.get("_cpp_include_paths", {}).get(line)
                if path is not None:
                    literal = posixpath.normpath(path.replace("\\", "/"))
                    path = posixpath.normpath(posixpath.join(
                        posixpath.dirname(source["source_file"].replace("\\", "/")), literal,
                    ))
                    target = files_by_path.get(path) or files_by_path.get(literal) or target
                if position is not None and target:
                    self.imports.setdefault(source["source_file"], []).append((target["source_file"], position))
        for imports in self.imports.values():
            imports.sort(key=lambda item: item[1])
        self.include_positions = {source: [at for _, at in imports] for source, imports in self.imports.items()}

    def reachable(self, source: str, position: int) -> frozenset[str]:
        key = source, bisect_left(self.include_positions.get(source, []), position)
        if key in self._reachable_cache:
            return self._reachable_cache[key]
        visible = {source}
        pending = [(source, position)]
        while pending:
            current, before = pending.pop()
            for target, at in self.imports.get(current, []):
                if at < before and target not in visible:
                    visible.add(target)
                    pending.append((target, 2**63))
        self._reachable_cache[key] = frozenset(visible)
        return self._reachable_cache[key]

    def _binding(self, name: str, scope: str, source: str, position: int,
                 completion: tuple[str, int, frozenset[str]] | None):
        visible = self.reachable(source, position)
        contexts = [(source, position, visible)]
        if completion is not None:
            contexts.append(completion)
        absolute = name.startswith("::")
        name = name.removeprefix("::")
        scopes = [""] if absolute else []
        while not absolute and scope:
            scopes.append(scope)
            scope = scope.rsplit("::", 1)[0] if "::" in scope else ""
        if not absolute:
            scopes.append("")
        for enclosing in scopes:
            identity = "::".join(filter(None, (enclosing, name)))
            candidates = [(file, b) for file, b in self.bindings.get(identity, [])
                          if not ((absolute or "::" in name) and b.get("implicit_anonymous"))
                          and file in visible and (not b["local"] if file != source else
                                                  b["start"] <= position < b["end"])]
            if any(file == source and not b["local"] and b["start"] > position
                   and b["scope"] in self.class_scopes for file, b in self.bindings.get(identity, [])):
                return None
            if not candidates and "::" in name:
                prefix = "::".join(filter(None, (enclosing, name.split("::", 1)[0])))
                if any(file in visible and (not b["local"] if file != source else
                                            b["start"] <= position < b["end"])
                       for file, b in self.bindings.get(prefix, [])):
                    return None
            if not candidates and not absolute and "::" not in name:
                for file, directive in self.directives.get(enclosing, []):
                    if file not in visible or (directive["local"] if file != source else
                                                not directive["start"] <= position < directive["end"]):
                        continue
                    namespace = directive["target"].removeprefix("::")
                    prefixes = [""] if directive["target"].startswith("::") else scopes[scopes.index(enclosing):]
                    for prefix in prefixes:
                        qualified = "::".join(filter(None, (prefix, namespace)))
                        if qualified in self.namespaces:
                            candidates.extend((f, b) for f, b in self.bindings.get(f"{qualified}::{name}", [])
                                              if f in visible and (not b["local"] if f != source else
                                                                    b["start"] <= position < b["end"]))
                            break
            if not candidates:
                continue
            # A block declaration shadows enclosing declarations, including unknown aliases.
            depth = max(b["block"] if file == source else 0 for file, b in candidates)
            candidates = [(file, b) for file, b in candidates
                          if (b["block"] if file == source else 0) == depth]
            if any(b["alias"] for _, b in candidates):
                return candidates[0] if len(candidates) == 1 else None
            targets = set().union(*(self.types.get("::".join(filter(None, (b["scope"], b["name"]))), set())
                                    for _, b in candidates))
            complete_targets = set()
            for nid in targets:
                definition = self.nodes[nid]
                definitions = []
                for file, binding in self.bindings.get(definition["_cpp_qualified"], []):
                    if not binding.get("complete"):
                        continue
                    if any(file in reachable and (file != at_source or binding["start"] <= at)
                           for at_source, at, reachable in contexts):
                        definitions.append(file)
                if len(definitions) == 1 and definitions[0] == definition.get("source_file"):
                    complete_targets.add(nid)
            return next(iter(complete_targets)) if len(complete_targets) == 1 else None
        return None

    def _expand(self, name: str, scope: str, source: str, position: int, seen: set,
                depth: int = 0, completion: tuple[str, int, frozenset[str]] | None = None) -> tuple[str, str] | None:
        # shortcut: cap static expansion at 32 hops; raise only with a compiler-backed resolver.
        if depth >= 32:
            return None
        name = re.sub(r"\b(const|volatile)\b", "", name).strip()
        reference = "&" if name.endswith("&") else ""
        name = re.sub(r"\s*&&?\s*$", "", name).strip()
        smart = re.fullmatch(r"(?:::)?std::(?:unique_ptr|shared_ptr)\s*<\s*(.+)\s*>", name)
        if smart:
            if not name.startswith("::") and self.shadowed_prefix("std", scope, source, position):
                return None
            pointee = self._expand(smart[1], scope, source, position, seen, depth + 1, completion)
            return (pointee[0], "smart" + reference) if pointee and not pointee[1] else None
        match = re.fullmatch(rf"({_IDENTIFIER})\s*((?:\*\s*)*)", name)
        if not match:
            return None
        binding = self._binding(match[1], scope, source, position, completion)
        shape = re.sub(r"\s+", "", match[2])
        if isinstance(binding, str):
            return binding, shape + reference
        if binding is None:
            return None
        file, alias = binding
        key = (file, alias["start"])
        if key in seen or not alias["target"]:
            return None
        target = self._expand(alias["target"], alias["scope"], file, alias["start"], seen | {key}, depth + 1, completion)
        if target is None or (shape and target[1] == "smart"):
            return None
        return target[0], target[1] + shape + reference

    def resolve(self, name: str, scope: str, source: str, position: int, operator: str, *,
                use_source: str | None = None, use_position: int | None = None) -> str | None:
        completion = source, position, self.reachable(source, position)
        if use_source is not None and use_position is not None:
            completion = use_source, use_position, self.reachable(use_source, use_position)
        target = self._expand(name, scope, source, position, set(), completion=completion)
        shape = target[1].rstrip("&") if target else ""
        if target and ((operator == "." and not shape) or
                       (operator == "->" and shape in {"*", "smart"})):
            return target[0]
        return None

    def shadowed_prefix(self, prefix: str, scope: str, source: str, position: int) -> bool:
        visible = self.reachable(source, position)
        while scope:
            if any(file in visible and (not b["local"] if file != source else
                                        b["start"] <= position < b["end"] or
                                        (not b["local"] and b["scope"] in self.class_scopes))
                   for file, b in self.bindings.get(f"{scope}::{prefix}", [])):
                return True
            scope = scope.rsplit("::", 1)[0] if "::" in scope else ""
        return False

    def is_alias(self, name: str, scope: str, source: str, position: int) -> bool:
        """An unresolved lexical alias must not become an unrelated cross-repo class."""
        visible = self.reachable(source, position)
        while True:
            identity = "::".join(filter(None, (scope, name)))
            if any(b["alias"] and file in visible and (
                (not b["local"]) if file != source else
                (b["start"] <= position < b["end"] or (not b["local"] and b["scope"] in self.class_scopes))
            ) for file, b in self.bindings.get(identity, [])):
                return True
            if not scope:
                return False
            scope = scope.rsplit("::", 1)[0] if "::" in scope else ""

    def member_owner(self, type_nid: str, name: str, kind: str,
                     seen: frozenset[str] = frozenset()) -> str | bool | None:
        """Return an owner, None for absent, or False for an unknown/ambiguous lookup."""
        if type_nid in seen or len(seen) >= 32:
            return False
        key = type_nid, name, kind, 32 - len(seen)
        if key in self._member_cache:
            return self._member_cache[key]
        node = self.nodes[type_nid]
        facts = node.get("_cpp_lookup")
        if facts is None:
            return False
        if name in facts["members"]:
            if kind == "field":
                result = type_nid if name in node.get("_cpp_fields", {}) else False
            else:
                result = type_nid if facts["methods"].get(name) == 1 else False
            self._member_cache[key] = result
            return result
        owners = []
        for base in facts["bases"]:
            scope = node["_cpp_qualified"].rsplit("::", 1)[0] if "::" in node["_cpp_qualified"] else ""
            parent = None if base["virtual"] else self.resolve(
                base["type"], scope, node["source_file"], base["position"], ".",
            )
            if parent is None:
                self._member_cache[key] = False
                return False
            owner = self.member_owner(parent, name, kind, seen | {type_nid})
            if owner is False:
                self._member_cache[key] = False
                return False
            if owner is not None:
                owners.append(owner)
        result = owners[0] if len(owners) == 1 else (False if owners else None)
        self._member_cache[key] = result
        return result
