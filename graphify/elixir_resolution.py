"""Cross-file resolution for Elixir remote calls (``Module.function()``).

Elixir has no import-based call resolution: any module is callable from any
file by its fully-qualified name, and ``alias`` shortens it lexically. The
extractor records each remote call's ``receiver`` (the dotted module path) and
a per-file alias table; this resolver turns them into precise cross-file
``calls`` edges:

  * ``ChatServer.Channels.create(...)``  -> the ``create/1`` function node
    (or the ``ChatServer.Channels`` module node when the function is not in
    the corpus, e.g. a macro or a dynamically-defined name)
  * ``Channels.create(...)`` after ``alias ChatServer.Channels`` -> same,
    resolved through the caller file's alias table
  * ``Channels.create(...)`` with no alias -> only when exactly one module in
    the corpus ends with ``.Channels`` (god-node guard); ambiguous -> no edge
  * ``Application.get_env(...)`` -> nothing: a stdlib-rooted receiver is the
    stdlib module, never the app's own ``MyApp.Application`` (Elixir has no
    relative module resolution), so it is excluded from that fallback

Every emitted edge is EXTRACTED (1.0): a remote call names its module in
source, so resolution is by explicit reference, never by global bare-name
matching. The shared cross-file call pass skips all member calls, so this
pass is purely additive.

Opt-in via ``GRAPHIFY_ELIXIR_REMOTE_CALLS=1``: ExUnit spec bodies contribute
most of these raw_calls (``test``/``describe``/``setup`` blocks), and the
resulting spec -> module coverage edges roughly double an Elixir corpus's
edge count. Gated so existing users see no graph change until they opt in.
Registered into graphify.resolver_registry and run by extract() after id
disambiguation, so node ids and raw_call caller_nids are final.
"""

from __future__ import annotations

import os
import re
from typing import Any

_MODULE_LABEL_RE = re.compile(r"^[A-Z][A-Za-z0-9_]*(?:\.[A-Z][A-Za-z0-9_]*)*$")

# Elixir/OTP standard-library roots. A bare `Application.get_env()` is *always*
# the stdlib module: Elixir has no relative module resolution, so an unaliased
# receiver never means the app's own `MyApp.Application`. These modules live
# outside the corpus, so the unique-last-segment fallback would otherwise bind
# them to whichever app module happens to share the last segment — and app
# modules named `Application`/`Supervisor`/`Base`/`Registry` are the norm, not
# the exception. Measured on a 306-file Phoenix corpus: 112 of 1726 resolved
# edges were this mistake, concentrated on hub modules where a wrong edge does
# the most damage to blast-radius and god-node queries.
#
# Scoped to the fallback only: an explicit `alias MyApp.Telegram.Base` still
# resolves `Base.encode()`, because the exact fully-qualified lookup runs first
# and that binding is stated in source.
_ELIXIR_STDLIB_ROOTS: frozenset[str] = frozenset({
    # Kernel & language
    "Kernel", "Module", "Macro", "Code", "Protocol", "Record", "Behaviour",
    "Exception", "Access", "Function", "Version", "Config",
    # Data types
    "Atom", "Base", "Bitwise", "Enum", "Float", "Integer", "Keyword", "List",
    "Map", "MapSet", "Range", "Regex", "Stream", "String", "StringIO", "Tuple",
    "Collectable", "Enumerable", "Inspect", "String.Chars",
    # Calendar
    "Calendar", "Date", "DateTime", "NaiveDateTime", "Time", "Duration",
    # Processes, applications, supervision
    "Agent", "Application", "DynamicSupervisor", "GenServer", "Node",
    "PartitionSupervisor", "Port", "Process", "Registry", "Supervisor", "Task",
    # IO & system
    "File", "IO", "OptionParser", "Path", "Port", "System", "URI",
    # Tooling (present in .exs and mix tasks)
    "Logger", "Mix", "ExUnit", "IEx",
})


def _key(label: str) -> str:
    """Normalize a module/function label to a comparison key (drop punctuation)."""
    return re.sub(r"[^a-zA-Z0-9]+", "", str(label)).lower()


def _enabled() -> bool:
    raw = os.environ.get("GRAPHIFY_ELIXIR_REMOTE_CALLS", "").strip().lower()
    return raw in ("1", "true", "yes")


def resolve_elixir_remote_calls(
    per_file: list[dict],
    all_nodes: list[dict],
    all_edges: list[dict],
) -> None:
    """Resolve Elixir ``Module.function()`` raw_calls to cross-file edges.

    No-op unless GRAPHIFY_ELIXIR_REMOTE_CALLS is set. Mutates ``all_edges``
    in place, matching the other registry resolvers.
    """
    if not _enabled():
        return

    node_by_id: dict[str, dict] = {n.get("id"): n for n in all_nodes}

    # Module index: module-shaped labels (``ChatServer.Channels``) defined in
    # .ex/.exs files. File nodes end in .ex/.exs (lowercase) and function
    # labels end in (), so the regex alone separates modules; no `contained`
    # guard is needed because the Elixir extractor never mints shadow nodes
    # for import targets.
    module_by_full: dict[str, list[str]] = {}
    module_by_last: dict[str, list[str]] = {}
    for n in all_nodes:
        label = str(n.get("label", ""))
        sf = str(n.get("source_file", ""))
        if not sf.endswith((".ex", ".exs")) or not _MODULE_LABEL_RE.match(label):
            continue
        nid = str(n.get("id"))
        module_by_full.setdefault(_key(label), []).append(nid)
        module_by_last.setdefault(_key(label.split(".")[-1]), []).append(nid)
    for k in list(module_by_full):
        module_by_full[k] = sorted(set(module_by_full[k]))
    for k in list(module_by_last):
        module_by_last[k] = sorted(set(module_by_last[k]))

    # (module_nid, function_key) -> function nid, from `method` edges.
    method_index: dict[tuple[str, str], str] = {}
    for e in all_edges:
        if e.get("relation") != "method":
            continue
        src, tgt = e.get("source"), e.get("target")
        tnode = node_by_id.get(tgt)
        if tnode is not None:
            method_index[(str(src), _key(tnode.get("label", "")))] = str(tgt)

    existing_pairs = {(e.get("source"), e.get("target")) for e in all_edges}

    def _emit(caller: str, target: str, rc: dict[str, Any]) -> None:
        if not caller or not target or caller == target:
            return
        if (caller, target) in existing_pairs:
            return
        existing_pairs.add((caller, target))
        all_edges.append({
            "source": caller,
            "target": target,
            "relation": "calls",
            "context": "call",
            "confidence": "EXTRACTED",
            "confidence_score": 1.0,
            "source_file": rc.get("source_file", ""),
            "source_location": rc.get("source_location"),
            "weight": 1.0,
        })

    def _resolve_module(full_name: str) -> str | None:
        """Fully-qualified name -> unique module nid, or None (bail on
        absence or ambiguity). Falls back to a unique last-segment match,
        except for stdlib-rooted receivers (see _ELIXIR_STDLIB_ROOTS)."""
        nids = module_by_full.get(_key(full_name), [])
        if len(nids) == 1:
            return nids[0]
        if len(nids) > 1:
            return None
        if full_name.split(".")[0] in _ELIXIR_STDLIB_ROOTS:
            return None
        nids = module_by_last.get(_key(full_name.split(".")[-1]), [])
        return nids[0] if len(nids) == 1 else None

    for result in per_file:
        if not isinstance(result, dict):
            continue
        raw_calls = result.get("raw_calls") or []
        if not raw_calls:
            continue
        aliases = result.get("elixir_aliases") or {}
        for rc in raw_calls:
            if not isinstance(rc, dict) or rc.get("lang") != "elixir":
                continue
            if not rc.get("is_member_call"):
                continue
            receiver = rc.get("receiver")
            callee = rc.get("callee")
            caller = str(rc.get("caller_nid", ""))
            if not receiver or not callee or not caller:
                continue
            sf = str(rc.get("source_file", ""))
            if not sf.endswith((".ex", ".exs")):
                continue

            receiver = str(receiver)
            # Alias expansion: exact receiver (`Channels` after
            # `alias ChatServer.Channels`), or a qualified path through an
            # aliased prefix (`Messages.broadcast` after `alias ChatServer`
            # is NOT expanded — `alias ChatServer` binds `ChatServer`, so a
            # first-segment lookup handles `ChatServer.Messages.broadcast`).
            full = aliases.get(receiver)
            if full is None:
                first, _, rest = receiver.partition(".")
                bound = aliases.get(first)
                full = f"{bound}.{rest}" if bound and rest else receiver

            module_nid = _resolve_module(full)
            if module_nid is None:
                continue
            method_nid = method_index.get((module_nid, _key(str(callee))))
            _emit(caller, method_nid or module_nid, rc)
