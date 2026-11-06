"""Resolve Luau ``require()`` calls through Rojo project files (#2520).

A Roblox codebase managed by Rojo requires modules by *instance path*, not by
file name: ``require(ReplicatedStorage.Shared.Util.Logger)``,
``require(script.Parent.Config)``. A ``*.project.json`` maps instance paths
onto disk folders through ``"$path"``. The Lua require handler reads the
argument as a dotted module name, so on such a repository nearly every
require became an external stub and the graph had no file-to-file
dependencies.

The per-file Luau extractor records each file's require arguments, local
bindings and returned table as instance-path chains
(:mod:`graphify.extractors.luau_facts`). :func:`resolve_rojo_requires` runs
once per extraction, before the id-remap passes. For every ``.luau`` file
below a ``*.project.json`` it evaluates the chains against the project's
mounts and rebuilds the file's ``imports`` edges:

* a require whose instance path maps to a script points at that file,
  stamped with ``target_file`` like any resolved import, so the remap
  canonicalizes it even when the target is an unchanged file of an
  incremental rebuild;
* a path with no script behind it (a RemoteEvent, a package that is not
  checked out) points at an external node named after the instance path;
* anything else, such as ``require(module)`` on a parameter, keeps the target
  the Lua handler gives it.

A local bound to the ``require`` of a module that returns a table of instance
paths (a locator such as ``return { Systems = Server.Systems }``) resolves
through that table. A string argument resolves relative to the file on disk,
Lune style.

``.lua`` files and ``.luau`` files with no project file above them keep the
Lua handler's edges unchanged.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any, Callable

from graphify.extractors.base import _make_id
from graphify.extractors.luau_facts import LUAU_FACTS_KEY, parse_luau_facts
from graphify.extractors.resolution import _resolve_lua_import_target


_SCRIPT_SUFFIXES = (".server.luau", ".client.luau", ".luau", ".server.lua", ".client.lua", ".lua")
_INIT_FILES = tuple("init" + suffix for suffix in _SCRIPT_SUFFIXES)
_LUA_SUFFIXES = (".luau", ".lua")
_PROJECT_SUFFIX = ".project.json"
_DEFAULT_PROJECT = "default.project.json"

# Instances a client script reaches under its player at runtime but that Rojo
# syncs under the Starter containers.
_RUNTIME_ALIASES: tuple[tuple[tuple[str, ...], tuple[str, ...]], ...] = (
    (("Players", "LocalPlayer", "PlayerScripts"), ("StarterPlayer", "StarterPlayerScripts")),
    (("Players", "LocalPlayer", "PlayerGui"), ("StarterGui",)),
)
# Modules Roblox itself inserts at runtime: anything below them is one
# external dependency.
_ROBLOX_RUNTIME_MODULES: tuple[tuple[str, ...], ...] = (
    ("StarterPlayer", "StarterPlayerScripts", "PlayerModule"),
)
_GLOBALS: dict[str, tuple[str, ...]] = {"game": (), "workspace": ("Workspace",)}


# --- Rojo project files -----------------------------------------------------


def _strip_script_suffix(name: str) -> str | None:
    for suffix in _SCRIPT_SUFFIXES:
        if name.endswith(suffix):
            return name[: -len(suffix)]
    return None


def _safe_names(names: tuple[str, ...]) -> bool:
    return all(n and n not in (".", "..") and "/" not in n and "\\" not in n for n in names)


@dataclass
class _Project:
    """Mounts of one project file: instance path -> absolute disk path."""

    path: str
    mounts: list[tuple[tuple[str, ...], str]] = field(default_factory=list)

    @classmethod
    def load(cls, path: str) -> _Project | None:
        project = cls(path)
        if not project._load_tree(path, (), frozenset()):
            return None
        project.mounts.sort(key=lambda m: -len(m[0]))
        return project

    def _load_tree(self, path: str, at: tuple[str, ...], including: frozenset[str]) -> bool:
        """Mount ``path``'s tree at ``at``; ``including`` guards include cycles."""
        if path in including:
            return False
        try:
            with open(path, encoding="utf-8") as handle:
                tree = json.load(handle).get("tree")
        except (OSError, ValueError, AttributeError):
            return False
        if not isinstance(tree, dict):
            return False
        self._walk(tree, at, os.path.dirname(path), including | {path})
        return True

    def _walk(
        self, node: dict, at: tuple[str, ...], base: str, including: frozenset[str]
    ) -> None:
        disk = node.get("$path")
        if isinstance(disk, dict):
            disk = disk.get("optional")
        if isinstance(disk, str) and disk:
            full = os.path.normpath(os.path.join(base, disk.replace("\\", "/")))
            if full.endswith(_PROJECT_SUFFIX):
                self._load_tree(full, at, including)
            else:
                self.mounts.append((at, full))
        for key, child in node.items():
            if not key.startswith("$") and isinstance(child, dict):
                self._walk(child, at + (key,), base, including)

    def instance_of(self, file: str) -> tuple[str, ...] | None:
        """The instance a script file becomes (``init.*`` is its folder)."""
        best: tuple[tuple[str, ...], str] | None = None
        for inst, disk in self.mounts:
            if file == disk:
                return inst
            if file.startswith(disk + os.sep) and (best is None or len(disk) > len(best[1])):
                best = (inst, disk)
        if best is None:
            return None
        parts = file[len(best[1]) + 1:].split(os.sep)
        name = _strip_script_suffix(parts[-1])
        if name is None:
            return None
        folders = tuple(parts[:-1])
        return best[0] + (folders if name == "init" else folders + (name,))

    def file_of(self, inst: tuple[str, ...], exists: Callable[[str], bool]) -> str | None:
        """The script file an instance path names, or None."""
        for mount, disk in self.mounts:
            if inst[: len(mount)] != mount:
                continue
            rest = inst[len(mount):]
            if not _safe_names(rest):
                return None
            if not rest:
                if exists(disk):
                    return disk
                candidates = [os.path.join(disk, i) for i in _INIT_FILES]
            else:
                folder = os.path.join(disk, *rest[:-1])
                candidates = [os.path.join(folder, rest[-1] + s) for s in _SCRIPT_SUFFIXES]
                candidates += [os.path.join(folder, rest[-1], i) for i in _INIT_FILES]
            return next((c for c in candidates if exists(c)), None)
        return None


def _runtime_path(inst: tuple[str, ...]) -> tuple[str, ...]:
    for alias, synced in _RUNTIME_ALIASES:
        if inst[: len(alias)] == alias:
            return synced + inst[len(alias):]
    return inst


# --- evaluation -------------------------------------------------------------


@dataclass
class _Binding:
    chain: list | None
    start: int
    visible_from: int
    scope_end: int


@dataclass
class _Context:
    """One file evaluated under one project."""

    file: str
    project: _Project
    me: tuple[str, ...] | None
    bindings: dict[str, list[_Binding]]
    values: dict[int, Any] = field(default_factory=dict)


@dataclass
class _LuauFile:
    nid: str
    source_file: str
    facts: dict


class _RojoResolver:
    def __init__(self, per_file: list[dict], all_nodes: list[dict], root: str) -> None:
        self.root = os.path.realpath(root)
        self.luau: dict[str, _LuauFile] = {}
        for result in per_file:
            if not isinstance(result, dict) or LUAU_FACTS_KEY not in result:
                continue
            node = _file_node(result.get("nodes") or [])
            if node is not None:
                self.luau[os.path.abspath(node["source_file"])] = _LuauFile(
                    node["id"], node["source_file"], result[LUAU_FACTS_KEY] or {}
                )
        self.batch: dict[str, tuple[str, str]] = {}
        for node in all_nodes:
            source_file = str(node.get("source_file") or "")
            if source_file.endswith(_LUA_SUFFIXES) and _is_file_node(node):
                self.batch.setdefault(os.path.abspath(source_file), (node["id"], source_file))
        self._projects: dict[str, tuple[_Project, ...]] = {}
        self._contexts: dict[tuple[str, str], _Context] = {}
        self._locators: dict[tuple[str, str], dict | None] = {}
        self._disk_facts: dict[str, dict] = {}
        self._exists: dict[str, bool] = {}

    # -- environment --

    def projects_for(self, directory: str) -> tuple[_Project, ...]:
        """Project files of the nearest directory at or above ``directory``.

        The walk never leaves the scan root: a project file above it (or a
        stray one in a parent temp dir) does not describe the scanned code.
        """
        if directory in self._projects:
            return self._projects[directory]
        found: tuple[_Project, ...] = ()
        real = os.path.realpath(directory)
        if real == self.root or real.startswith(self.root + os.sep):
            try:
                names = sorted(
                    (n for n in os.listdir(directory) if n.endswith(_PROJECT_SUFFIX)),
                    key=lambda n: (n != _DEFAULT_PROJECT, n),
                )
            except OSError:
                names = []
            loaded = (_Project.load(os.path.join(directory, n)) for n in names)
            found = tuple(p for p in loaded if p is not None)
            parent = os.path.dirname(directory)
            if not names and real != self.root and parent != directory:
                found = self.projects_for(parent)
        self._projects[directory] = found
        return found

    def exists(self, path: str) -> bool:
        if path in self.batch:
            return True
        if path not in self._exists:
            self._exists[path] = os.path.isfile(path)
        return self._exists[path]

    def facts_of(self, file: str) -> dict:
        if file in self.luau:
            return self.luau[file].facts
        if file not in self._disk_facts:
            self._disk_facts[file] = parse_luau_facts(file) if file.endswith(".luau") else {}
        return self._disk_facts[file]

    def context(self, file: str, project: _Project) -> _Context:
        key = (file, project.path)
        if key not in self._contexts:
            bindings: dict[str, list[_Binding]] = {}
            for name, chain, start, visible_from, scope_end in self.facts_of(file).get("bindings", []):
                bindings.setdefault(name, []).append(_Binding(chain, start, visible_from, scope_end))
            self._contexts[key] = _Context(file, project, project.instance_of(file), bindings)
        return self._contexts[key]

    def contexts_for(self, file: str) -> list[_Context]:
        projects = self.projects_for(os.path.dirname(file))
        mounting = [p for p in projects if p.instance_of(file) is not None]
        return [self.context(file, p) for p in (mounting or projects)]

    # -- chains --

    def lookup(self, ctx: _Context, name: str, pos: int) -> Any:
        best: _Binding | None = None
        for binding in ctx.bindings.get(name, ()):
            if binding.visible_from <= pos < binding.scope_end and (
                best is None or binding.visible_from >= best.visible_from
            ):
                best = binding
        if best is None:
            if name == "script":
                return ctx.me
            return _GLOBALS.get(name)
        key = id(best)
        if key not in ctx.values:
            ctx.values[key] = None
            ctx.values[key] = self.evaluate(ctx, best.chain, best.start)
        return ctx.values[key]

    def evaluate(self, ctx: _Context, chain: list | None, pos: int) -> Any:
        """Instance path (tuple), locator table (dict) or None."""
        if chain is None:
            return None
        if chain[0] == "any":
            return next(
                (v for v in (self.evaluate(ctx, c, pos) for c in chain[1]) if v is not None), None
            )
        if chain[0] == "require":
            target = self.target(ctx, chain[1], pos)
            return self.locator(target[1], ctx.project) if target and target[0] == "file" else None
        if chain[0] != "path":
            return None
        head = chain[1]
        cur: Any = (
            self.lookup(ctx, head, pos) if isinstance(head, str) else self.evaluate(ctx, head, pos)
        )
        for op, name in chain[2]:
            if cur is None:
                return None
            if isinstance(cur, dict):
                cur = cur.get(name) if op == "child" else None
            elif op == "service":
                cur = (name,)
            elif op == "child":
                cur = cur + (name,)
            elif op == "parent":
                cur = cur[:-1] if cur else None
            elif op == "ancestor":
                cur = next((cur[:i] for i in range(len(cur) - 1, 0, -1) if cur[i - 1] == name), None)
            else:
                return None
        return cur

    def locator(self, file: str, project: _Project) -> dict | None:
        """Fields of a module returning a table of instance paths."""
        key = (file, project.path)
        if key in self._locators:
            return self._locators[key]
        self._locators[key] = None
        returned = self.facts_of(file).get("returns") or []
        table: dict[str, Any] = {}
        if returned:
            ctx = self.context(file, project)
            for name, chain in returned[1]:
                value = self.evaluate(ctx, chain, returned[0])
                if value is not None:
                    table[name] = value
        self._locators[key] = table or None
        return self._locators[key]

    def target(self, ctx: _Context, chain: list | None, pos: int) -> tuple[str, Any] | None:
        """``("file", path)``, ``("instance", path)`` or None for a require argument."""
        if chain is None:
            return None
        if chain[0] == "any":
            fallback = None
            for option in chain[1]:
                found = self.target(ctx, option, pos)
                if found is not None and found[0] == "file":
                    return found
                fallback = fallback or found
            return fallback
        if chain[0] == "str":
            return self.string_target(ctx.file, chain[1])
        value = self.evaluate(ctx, chain, pos)
        if not isinstance(value, tuple) or not value:
            return None
        inst = _runtime_path(value)
        for module in _ROBLOX_RUNTIME_MODULES:
            if inst[: len(module)] == module:
                return ("instance", module)
        path = ctx.project.file_of(inst, self.exists)
        return ("file", path) if path else ("instance", inst)

    def string_target(self, file: str, text: str) -> tuple[str, Any] | None:
        if not text.startswith(("./", "../")):
            return None
        base = os.path.normpath(os.path.join(os.path.dirname(file), text))
        candidates = [base] if base.endswith(_LUA_SUFFIXES) else []
        candidates += [base + s for s in _LUA_SUFFIXES]
        candidates += [os.path.join(base, "init" + s) for s in _LUA_SUFFIXES]
        found = next((c for c in candidates if self.exists(c)), None)
        return ("file", found) if found else None

    # -- edges --

    def edges_for(self, file: str, luau: _LuauFile) -> list[dict] | None:
        """Rebuilt ``imports`` edges of one file, or None outside any project."""
        contexts = self.contexts_for(file)
        if not contexts:
            return None
        edges: list[dict] = []
        seen: set[str] = set()
        for line, pos, chain, token in luau.facts.get("requires", []):
            found = None
            for ctx in contexts:
                candidate = self.target(ctx, chain, pos)
                if candidate is not None and candidate[0] == "file":
                    found = candidate
                    break
                found = found or candidate
            edge = self.edge(luau, line, found, token)
            if edge is not None and edge["target"] not in seen and edge["target"] != luau.nid:
                seen.add(edge["target"])
                edges.append(edge)
        return edges

    def edge(self, luau: _LuauFile, line: int, found: tuple[str, Any] | None, token: str) -> dict | None:
        target_file = None
        if found is not None and found[0] == "file":
            target, target_file = self.batch.get(found[1], (_make_id(found[1]), found[1]))
        elif found is not None:
            target = _make_id(".".join(found[1]))
        else:
            target = _resolve_lua_import_target(token, luau.source_file) if token else ""
        if not target:
            return None
        edge = {
            "source": luau.nid,
            "target": target,
            "relation": "imports",
            "context": "import",
            "confidence": "EXTRACTED",
            "confidence_score": 1.0,
            "source_file": luau.source_file,
            "source_location": f"L{line}",
            "weight": 1.0,
        }
        if target_file is not None:
            edge["target_file"] = target_file
        return edge


def _is_file_node(node: dict) -> bool:
    source_file = str(node.get("source_file") or "")
    return bool(source_file) and node.get("label") == os.path.basename(source_file)


def _file_node(nodes: list[dict]) -> dict | None:
    return next((n for n in nodes if isinstance(n, dict) and _is_file_node(n)), None)


def resolve_rojo_requires(
    per_file: list[dict],
    all_nodes: list[dict],
    all_edges: list[dict],
    *,
    root: str | os.PathLike[str],
) -> None:
    """Rebuild the ``imports`` edges of every ``.luau`` file under a Rojo project.

    Must run before the id-remap passes: targets are minted the way the
    extractors mint file ids (``_make_id`` of the path) and stamped with
    ``target_file``. Project files are looked up from each file's directory
    up to the scan ``root``; a file with none is left untouched.
    """
    resolver = _RojoResolver(per_file, all_nodes, str(root))
    rebuilt: dict[tuple[str, str], list[dict]] = {}
    for file, luau in resolver.luau.items():
        edges = resolver.edges_for(file, luau)
        if edges is not None:
            rebuilt[(luau.nid, luau.source_file)] = edges
    if not rebuilt:
        return
    all_edges[:] = [
        e for e in all_edges
        if e.get("relation") != "imports"
        or (e.get("source"), e.get("source_file")) not in rebuilt
    ]
    for edges in rebuilt.values():
        all_edges.extend(edges)
