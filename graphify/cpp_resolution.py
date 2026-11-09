"""Conservative C++ type lookup for declared member-call receivers.

This is lexical name lookup, not a C++ compiler: dependent types, alias templates,
transitive using directives and arbitrary template specializations remain unresolved.
"""
from __future__ import annotations

import re


_IDENTIFIER = r"(?:::)?[A-Za-z_]\w*(?:::[A-Za-z_]\w*)*"


class CppTypeLookup:
    """Reuse persisted AST facts while keeping scope/include lookup out of extract.py."""

    def __init__(self, nodes: list[dict], edges: list[dict]):
        self.nodes = {n["id"]: n for n in nodes}
        self.files = {n["id"]: n for n in nodes if "_cpp_type_bindings" in n}
        self.bindings: dict[str, list[tuple[str, dict]]] = {}
        self.types: dict[str, set[str]] = {}
        self.imports: dict[str, list[tuple[str, int]]] = {}
        self.namespaces: set[str] = set()
        self.directives: dict[str, list[tuple[str, dict]]] = {}
        for node in self.files.values():
            source = node["source_file"]
            for binding in node["_cpp_type_bindings"]:
                identity = "::".join(filter(None, (binding["scope"], binding["name"])))
                if binding["namespace"]:
                    self.namespaces.add(identity)
                if binding["directive"]:
                    self.directives.setdefault(binding["scope"], []).append((source, binding))
                    continue
                self.bindings.setdefault(identity, []).append((source, binding))
        for node in nodes:
            if "_cpp_fields" in node and node.get("_cpp_qualified"):
                self.types.setdefault(node["_cpp_qualified"], set()).add(node["id"])
        for edge in edges:
            source = self.files.get(edge.get("source"))
            target = self.files.get(edge.get("target"))
            if edge.get("relation") == "imports" and source and target:
                line = str(edge.get("source_location", "")).removeprefix("L")
                position = source.get("_cpp_include_positions", {}).get(line)
                if position is not None:
                    self.imports.setdefault(source["source_file"], []).append((target["source_file"], position))

    def reachable(self, source: str, position: int) -> set[str]:
        visible = {source}
        pending = [(source, position)]
        while pending:
            current, before = pending.pop()
            for target, at in self.imports.get(current, []):
                if at < before and target not in visible:
                    visible.add(target)
                    pending.append((target, 2**63))
        return visible

    def _binding(self, name: str, scope: str, source: str, position: int):
        visible = self.reachable(source, position)
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
                          if file in visible and (not b["local"] if file != source else
                                                  b["start"] <= position < b["end"])]
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
            targets = {nid for nid in targets if self.nodes[nid].get("source_file") in visible}
            return next(iter(targets)) if len(targets) == 1 else None
        return None

    def _expand(self, name: str, scope: str, source: str, position: int, seen: set) -> tuple[str, str] | None:
        name = re.sub(r"\b(const|volatile)\b", "", name).replace("&", "").strip()
        smart = re.fullmatch(r"std::(?:unique_ptr|shared_ptr)\s*<\s*(.+)\s*>", name)
        if smart:
            pointee = self._expand(smart[1], scope, source, position, seen)
            return (pointee[0], "smart") if pointee and not pointee[1] else None
        match = re.fullmatch(rf"({_IDENTIFIER})\s*((?:\*\s*)*)", name)
        if not match:
            return None
        binding = self._binding(match[1], scope, source, position)
        shape = match[2].replace(" ", "")
        if isinstance(binding, str):
            return binding, shape
        if binding is None:
            return None
        file, alias = binding
        key = (file, alias["start"])
        if key in seen or not alias["target"]:
            return None
        target = self._expand(alias["target"], alias["scope"], file, alias["start"], seen | {key})
        if target is None or (shape and target[1] == "smart"):
            return None
        return target[0], target[1] + shape

    def resolve(self, name: str, scope: str, source: str, position: int, operator: str) -> str | None:
        target = self._expand(name, scope, source, position, set())
        if target and ((operator == "." and not target[1]) or
                       (operator == "->" and target[1] in {"*", "smart"})):
            return target[0]
        return None
