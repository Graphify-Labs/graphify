"""Extractor plugins: add a language to graphify by installing a package.

A plugin is a small description of "which files, and how to turn them into
nodes and edges". Packages publish one through the Python entry-point group
``graphify.extractors``::

    # the plugin package's pyproject.toml
    [project.entry-points."graphify.extractors"]
    mylang = "mypkg.graphify_plugin:PLUGIN"

``PLUGIN`` may be an :class:`ExtractorPlugin`, a plain ``dict`` with the same
keys (so a plugin package need not import graphify at all), any object with the
same attributes, a zero-argument callable returning one of those, or a list of
them. Nothing in graphify names a plugin: install the package and its files are
picked up by ``detect`` and ``extract``.

Two extraction styles, pick one per plugin:

``extract(path[, ctx]) -> dict``
    Called once per file, possibly in a worker process. Results are cached per
    file like any built-in extractor (set ``cross_file=True`` to opt out).

``extract_batch(paths, ctx) -> {path: dict}``
    Called once per extraction, in the main process, with every file the plugin
    matched. For tools that resolve names across files or are costly to start.
    Results are never cached per file.

Result dict: ``{"nodes": [...], "edges": [...]}`` in graphify's extraction
schema. Missing optional fields are filled in and malformed output becomes a
visible per-file ``error`` instead of corrupting the graph. There is no
fallback: a plugin that fails leaves its files with that error.

Optional fields: ``suffixes`` / ``filenames`` / ``globs`` / ``shebangs`` (what it
matches), ``file_type``, ``priority``, ``override_builtin``, ``cache_key``
(bumped to invalidate cached results), ``available()`` (return ``None`` when
usable, else a reason string), ``post_process(result, path, ctx)``.

Environment:

``GRAPHIFY_PLUGINS``
    ``off`` disables plugins; otherwise a comma list of extra ``module:attr``
    specs loaded in addition to entry points (for plugins not installed as a
    package). Plugins are never loaded from a project's ``.graphifyrc``: that
    file belongs to the repo being scanned, and loading code named by it would
    let a scanned repo run code.
``GRAPHIFY_DISABLE_PLUGINS``
    Comma list of plugin names to skip.
"""
from __future__ import annotations

import fnmatch
import importlib
import inspect
import os
import sys
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable

API_VERSION = 1
ENTRY_POINT_GROUP = "graphify.extractors"
ENV_PLUGINS = "GRAPHIFY_PLUGINS"
ENV_DISABLE = "GRAPHIFY_DISABLE_PLUGINS"

_FILE_TYPES = {"code", "document", "paper", "image", "video"}
_DEFAULT_SCORES = {"EXTRACTED": 1.0, "INFERRED": 0.7, "AMBIGUOUS": 0.3}


@dataclass
class PluginContext:
    """What graphify tells a plugin about the current extraction."""

    root: Path
    paths: list[Path] = field(default_factory=list)
    log: Callable[[str], None] = lambda msg: print(msg, flush=True)


@dataclass
class ExtractorPlugin:
    name: str
    suffixes: tuple[str, ...] = ()
    filenames: tuple[str, ...] = ()
    globs: tuple[str, ...] = ()
    shebangs: tuple[str, ...] = ()
    extract: Callable[..., dict] | None = None
    extract_batch: Callable[..., dict] | None = None
    file_type: str = "code"
    priority: int = 0
    override_builtin: bool = False
    cross_file: bool = False
    cache_key: str = ""
    available: Callable[[], str | None] | None = None
    post_process: Callable[..., dict | None] | None = None
    api: int = API_VERSION
    source: str = ""  # where it came from, for `graphify plugins`

    @property
    def batch(self) -> bool:
        return self.extract_batch is not None


@dataclass
class _Registry:
    plugins: dict[str, ExtractorPlugin] = field(default_factory=dict)
    errors: list[tuple[str, str]] = field(default_factory=list)  # (source, message)
    by_suffix: dict[str, list[ExtractorPlugin]] = field(default_factory=dict)
    others: list[ExtractorPlugin] = field(default_factory=list)  # filename/glob/shebang matchers


_lock = threading.RLock()
_registry: _Registry | None = None
_extra: dict[str, ExtractorPlugin] = {}  # programmatic registrations (this process only)
_batch_results: dict[str, dict] = {}


# ── building plugins from whatever a package hands us ──────────────────────────

def _get(obj: Any, key: str, default: Any = None) -> Any:
    return obj.get(key, default) if isinstance(obj, dict) else getattr(obj, key, default)


def _tuple(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    return tuple(value)


def coerce(obj: Any, source: str = "") -> list[ExtractorPlugin]:
    """Turn an entry-point value into plugins. Raises ``ValueError`` when invalid."""
    if isinstance(obj, ExtractorPlugin):
        obj.source = obj.source or source
        return [obj]
    if isinstance(obj, (list, tuple)):
        return [p for item in obj for p in coerce(item, source)]
    if callable(obj) and not isinstance(obj, dict) and _get(obj, "name") is None:
        return coerce(obj(), source)
    name = _get(obj, "name")
    if not isinstance(name, str) or not name:
        raise ValueError("a plugin needs a non-empty string `name`")
    plugin = ExtractorPlugin(
        name=name,
        suffixes=tuple(s if s.startswith(".") else "." + s for s in map(str.lower, _tuple(_get(obj, "suffixes")))),
        filenames=_tuple(_get(obj, "filenames")),
        globs=_tuple(_get(obj, "globs")),
        shebangs=_tuple(_get(obj, "shebangs")),
        extract=_get(obj, "extract"),
        extract_batch=_get(obj, "extract_batch"),
        file_type=_get(obj, "file_type", "code"),
        priority=int(_get(obj, "priority", 0)),
        override_builtin=bool(_get(obj, "override_builtin", False)),
        cross_file=bool(_get(obj, "cross_file", False)),
        cache_key=str(_get(obj, "cache_key", "") or ""),
        available=_get(obj, "available"),
        post_process=_get(obj, "post_process"),
        api=int(_get(obj, "api", API_VERSION)),
        source=source,
    )
    _validate(plugin)
    return [plugin]


def _validate(p: ExtractorPlugin) -> None:
    if p.api > API_VERSION:
        raise ValueError(f"plugin {p.name!r} needs plugin API {p.api}; this graphify has {API_VERSION}")
    if not (p.suffixes or p.filenames or p.globs or p.shebangs):
        raise ValueError(f"plugin {p.name!r} matches nothing: give suffixes, filenames, globs or shebangs")
    if bool(p.extract) == bool(p.extract_batch):
        raise ValueError(f"plugin {p.name!r} needs exactly one of `extract` and `extract_batch`")
    if p.file_type not in _FILE_TYPES:
        raise ValueError(f"plugin {p.name!r}: file_type {p.file_type!r} is not one of {sorted(_FILE_TYPES)}")


# ── discovery ──────────────────────────────────────────────────────────────────

def _entry_points() -> Iterable[Any]:
    from importlib.metadata import entry_points

    return entry_points(group=ENTRY_POINT_GROUP)


def _load_spec(spec: str) -> Any:
    module, _, attr = spec.partition(":")
    if not module or not attr:
        raise ValueError(f"{spec!r} is not of the form module:attr")
    return getattr(importlib.import_module(module), attr)


def _build() -> _Registry:
    reg = _Registry()
    if os.environ.get(ENV_PLUGINS, "").strip().lower() == "off":
        return reg
    disabled = {n.strip() for n in os.environ.get(ENV_DISABLE, "").split(",") if n.strip()}
    found: list[tuple[str, Callable[[], Any]]] = []
    try:
        for ep in _entry_points():
            found.append((f"entry point {ep.name} ({ep.value})", ep.load))
    except Exception as exc:  # a broken metadata dir must not take graphify down
        reg.errors.append(("entry points", f"{type(exc).__name__}: {exc}"))
    for spec in (s.strip() for s in os.environ.get(ENV_PLUGINS, "").split(",")):
        if spec:
            found.append((f"{ENV_PLUGINS} {spec}", lambda spec=spec: _load_spec(spec)))
    for source, load in found:
        try:
            plugins = coerce(load(), source)
        except Exception as exc:
            reg.errors.append((source, f"{type(exc).__name__}: {exc}"))
            continue
        for p in plugins:
            if p.name in disabled:
                continue
            if p.name in reg.plugins:
                reg.errors.append((source, f"duplicate plugin name {p.name!r}; keeping {reg.plugins[p.name].source}"))
                continue
            reg.plugins[p.name] = p
    for p in _extra.values():
        reg.plugins[p.name] = p
    for p in list(reg.plugins.values()):
        reason = _unavailable(p)
        if reason:
            reg.errors.append((p.source or p.name, f"plugin {p.name!r} unavailable: {reason}"))
            del reg.plugins[p.name]
    for p in sorted(reg.plugins.values(), key=lambda p: -p.priority):
        for s in p.suffixes:
            reg.by_suffix.setdefault(s, []).append(p)
        if p.filenames or p.globs or p.shebangs:
            reg.others.append(p)
    for source, message in reg.errors:
        print(f"  warning: graphify plugin: {source}: {message}", file=sys.stderr)
    return reg


def _unavailable(p: ExtractorPlugin) -> str | None:
    if p.available is None:
        return None
    try:
        return p.available() or None
    except Exception as exc:
        return f"availability check raised {type(exc).__name__}: {exc}"


def registry() -> _Registry:
    global _registry
    with _lock:
        if _registry is None:
            _registry = _build()
        return _registry


def reload() -> None:
    """Forget what was discovered; the next lookup rediscovers. Mostly for tests."""
    global _registry
    with _lock:
        _registry = None
        _batch_results.clear()


def register(plugin: Any, source: str = "register()") -> list[ExtractorPlugin]:
    """Register plugin(s) programmatically. Process-local: spawn workers do not see it."""
    plugins = coerce(plugin, source)
    with _lock:
        for p in plugins:
            _extra[p.name] = p
    reload()
    return plugins


def unregister(name: str) -> None:
    with _lock:
        _extra.pop(name, None)
    reload()


def all_plugins() -> list[ExtractorPlugin]:
    return sorted(registry().plugins.values(), key=lambda p: (-p.priority, p.name))


# ── matching ───────────────────────────────────────────────────────────────────

def match(path: Path | str, suffix: str | None = None, *, builtin_claims: bool | None = None) -> ExtractorPlugin | None:
    """The plugin that handles ``path``, or None.

    ``builtin_claims``: True when a built-in extractor already handles the file;
    then only a plugin with ``override_builtin`` wins. None means "unknown" and
    is treated as False (any matching plugin wins).
    """
    reg = registry()
    if not reg.plugins:
        return None
    p = Path(path)
    suffix = (suffix if suffix is not None else p.suffix).lower()
    candidates = list(reg.by_suffix.get(suffix, ()))
    name = p.name
    for plug in reg.others:
        if (
            name in plug.filenames
            or any(fnmatch.fnmatch(name, g) for g in plug.globs)
            or (plug.shebangs and not suffix and _shebang_matches(p, plug.shebangs))
        ):
            candidates.append(plug)
    if builtin_claims:
        candidates = [c for c in candidates if c.override_builtin]
    return max(candidates, key=lambda c: c.priority, default=None)


def _shebang_matches(path: Path, interpreters: tuple[str, ...]) -> bool:
    try:
        from graphify.detect import _shebang_interpreter

        return _shebang_interpreter(path) in interpreters
    except Exception:
        return False


def file_type_for(path: Path | str, suffix: str | None = None) -> str | None:
    p = match(path, suffix)
    return p.file_type if p else None


def salt_for(path: Path | str) -> str | None:
    """Cache-key material: a plugin's result depends on the plugin and its version."""
    p = match(path)
    return f"plugin={p.name}@{p.cache_key}" if p else None


def is_cross_file(path: Path | str) -> bool:
    p = match(path)
    return bool(p and (p.cross_file or p.batch))


# ── running ────────────────────────────────────────────────────────────────────

def _call(fn: Callable[..., Any], *args: Any, ctx: PluginContext) -> Any:
    """Pass ``ctx`` only to functions that take one more positional argument."""
    try:
        params = [
            q for q in inspect.signature(fn).parameters.values()
            if q.kind in (q.POSITIONAL_ONLY, q.POSITIONAL_OR_KEYWORD, q.VAR_POSITIONAL)
        ]
        wants_ctx = any(q.kind == q.VAR_POSITIONAL for q in params) or len(params) > len(args)
    except (TypeError, ValueError):
        wants_ctx = False
    return fn(*args, ctx) if wants_ctx else fn(*args)


def _error(plugin: ExtractorPlugin, message: str) -> dict:
    return {"nodes": [], "edges": [], "error": f"plugin {plugin.name}: {message}"}


def normalise(result: Any, path: Path, plugin: ExtractorPlugin) -> dict:
    """Fill optional fields; turn malformed output into a visible error."""
    if not isinstance(result, dict):
        return _error(plugin, f"returned {type(result).__name__}, expected a dict")
    if result.get("error"):
        return {"nodes": [], "edges": [], "error": f"plugin {plugin.name}: {result['error']}"}
    nodes, edges = result.get("nodes", []), result.get("edges", [])
    if not isinstance(nodes, list) or not isinstance(edges, list):
        return _error(plugin, "`nodes` and `edges` must be lists")
    out_nodes, ids = [], set()
    for i, n in enumerate(nodes):
        if not isinstance(n, dict) or not n.get("id") or not n.get("label"):
            return _error(plugin, f"node #{i} needs an `id` and a `label`")
        n = dict(n)
        n.setdefault("file_type", "code")
        n["source_file"] = n.get("source_file") or str(path)
        ids.add(n["id"])
        out_nodes.append(n)
    out_edges = []
    for i, e in enumerate(edges):
        if not isinstance(e, dict) or not all(e.get(k) for k in ("source", "target", "relation")):
            return _error(plugin, f"edge #{i} needs `source`, `target` and `relation`")
        e = dict(e)
        e["confidence"] = e.get("confidence") or "EXTRACTED"
        e.setdefault("confidence_score", _DEFAULT_SCORES.get(e["confidence"], 1.0))
        e["source_file"] = e.get("source_file") or str(path)
        out_edges.append(e)
    out = {**result, "nodes": out_nodes, "edges": out_edges}
    return out


def _report(res: dict, path: Path) -> dict:
    """graphify only records *which* file failed; say why, once, on stderr."""
    if res.get("error"):
        print(f"  warning: {res['error']} ({path})", file=sys.stderr)
    return res


def extract_one(plugin: ExtractorPlugin, path: Path, root: Path) -> dict:
    """Run a per-file plugin on one file. Never raises."""
    ctx = PluginContext(root=root, paths=[path])
    try:
        res = normalise(_call(plugin.extract, path, ctx=ctx), path, plugin)
        if plugin.post_process and "error" not in res:
            res = normalise(_call(plugin.post_process, res, path, ctx=ctx) or res, path, plugin)
    except Exception as exc:
        res = _error(plugin, f"{type(exc).__name__}: {exc}")
    return _report(res, path)


def run_batches(paths: list[Path], root: Path) -> dict[str, dict]:
    """Run every matching batch plugin once. Results are kept for :func:`batch_result`.

    Returns {resolved path: result} for the files handled.
    """
    _batch_results.clear()
    groups: dict[str, list[Path]] = {}
    plugins: dict[str, ExtractorPlugin] = {}
    for path in paths:
        p = match(path)
        if p is not None and p.batch:
            groups.setdefault(p.name, []).append(path)
            plugins[p.name] = p
    for name, files in groups.items():
        plugin = plugins[name]
        ctx = PluginContext(root=root, paths=files)
        try:
            raw = _call(plugin.extract_batch, files, ctx=ctx)
            if not isinstance(raw, dict):
                raise TypeError(f"extract_batch returned {type(raw).__name__}, expected {{path: result}}")
            by_path = {str(Path(k).resolve()): v for k, v in raw.items()}
        except Exception as exc:
            msg = f"{type(exc).__name__}: {exc}"
            print(f"  warning: graphify plugin {name} failed: {msg}", file=sys.stderr)
            by_path, failure = {}, _error(plugin, msg)
            for f in files:
                _batch_results[str(Path(f).resolve())] = failure
            continue
        for f in files:
            key = str(Path(f).resolve())
            if key in by_path:
                res = normalise(by_path[key], f, plugin)
                if plugin.post_process and "error" not in res:
                    try:
                        res = normalise(_call(plugin.post_process, res, f, ctx=ctx) or res, f, plugin)
                    except Exception as exc:
                        res = _error(plugin, f"post_process: {type(exc).__name__}: {exc}")
            else:  # the plugin looked at the batch and declined this file
                res = {"nodes": [], "edges": [], "skipped": f"plugin {name} returned nothing for this file"}
            _report(res, f)
            _batch_results[key] = res
    return dict(_batch_results)


def batch_result(path: Path | str) -> dict | None:
    return _batch_results.get(str(Path(path).resolve()))
