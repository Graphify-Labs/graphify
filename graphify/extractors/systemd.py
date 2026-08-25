"""systemd unit extractor (#2848).

Units are INI, so no grammar is needed. A repo that keeps its units under
version control keeps its whole OS-level scheduled-job topology there — and
without this pass that topology is silently absent: the graph answers "what
runs on a schedule" from the application's in-process scheduler alone and
looks complete.

Handled: ``.service`` ``.timer`` ``.socket`` ``.target`` ``.path`` ``.mount``
``.slice``. Every unit becomes a file node. Edges, in the direction the
question is usually asked:

=================  ============================  =================================
relation           from -> to                    source key
=================  ============================  =================================
``activates``      timer/socket/path -> unit     ``[Timer] Unit=`` / ``[Socket]
                                                 Service=`` / ``[Path] Unit=``,
                                                 else the same-stem ``.service``
``runs``           service -> script             ``ExecStart=`` and friends,
                                                 after stripping systemd's
                                                 prefixes and ``/usr/bin/env``
                                                 + interpreter
``documented_by``  unit -> doc                   ``Documentation=file://...``
``after`` ``before`` ``wants`` ``requires``
``binds_to`` ``part_of`` ``conflicts``
``wanted_by`` ``required_by``
                   unit -> unit                  the ``[Unit]`` / ``[Install]``
                                                 ordering and dependency keys
=================  ============================  =================================

Unit -> unit edges are emitted only when the target unit is a file beside
this one (units of one deployment live in one directory): ``After=
network-online.target`` names the host's unit, and manufacturing a node
for every system target would put a phantom hub in every repo. A
template's instance (``backup@nightly.service``) resolves to the template
file (``backup@.service``).

Script and doc targets are deployment paths (``ExecStart=/opt/app/bin/
run.py``), so they rarely exist at that path inside the repo. Resolution
tries the literal path (relative to the unit's directory, then absolute),
then walks up from the unit's directory looking for the same tail
(``bin/run.py``, then ``run.py``) — the common "units/ beside bin/" layout.
A target that resolves is minted the way every other extractor mints a
file reference (``_make_id(str(resolved))``), which extract() rewires onto
the real file node; one that does not is skipped, not fabricated.
"""
from __future__ import annotations

import re
from pathlib import Path, PurePosixPath

from graphify.extractors.base import _make_id

SYSTEMD_UNIT_EXTENSIONS: frozenset[str] = frozenset({
    ".service", ".timer", ".socket", ".target", ".path", ".mount", ".slice",
})

# [Unit] / [Install] keys that name other units, and the relation each becomes.
_UNIT_REF_KEYS: dict[str, str] = {
    "after": "after",
    "before": "before",
    "wants": "wants",
    "requires": "requires",
    "requisite": "requires",
    "bindsto": "binds_to",
    "partof": "part_of",
    "conflicts": "conflicts",
    "wantedby": "wanted_by",
    "requiredby": "required_by",
    "upholds": "wants",
}

# The key that names what an activating unit starts, per section.
_ACTIVATES_KEY: dict[str, str] = {"timer": "unit", "socket": "service", "path": "unit"}

_EXEC_KEYS = ("execstart", "execstartpre", "execstartpost", "execreload",
              "execstop", "execstoppost", "execcondition")

# Interpreters whose first argument is the real script.
_INTERPRETERS: frozenset[str] = frozenset({
    "sh", "bash", "zsh", "dash", "ksh", "fish",
    "python", "python2", "python3", "pypy", "pypy3",
    "node", "nodejs", "deno", "bun", "ruby", "perl", "php", "lua", "Rscript",
    "uv", "uvx", "npx", "pipx", "poetry", "pnpm", "npm", "yarn",
})
_INTERPRETER_RE = re.compile(r"^(?:python|pypy)\d+(?:\.\d+)?$")

_SECTION_RE = re.compile(r"^\s*\[([^\]]+)\]\s*$")
_SPLIT_WS_RE = re.compile(r"\s+")


def _read_unit(path: Path) -> list[tuple[str, str, str, int]]:
    """Yield ``(section, key, value, line)`` with ``\\``-continuations joined.

    Sections and keys are lower-cased; values are stripped. Comments (``#``,
    ``;``) and blank lines are dropped. ``line`` is the 1-based line the
    logical entry started on.
    """
    text = path.read_text(encoding="utf-8", errors="replace")
    entries: list[tuple[str, str, str, int]] = []
    section = ""
    pending: list[str] = []
    pending_line = 0
    for lineno, raw in enumerate(text.splitlines(), 1):
        if pending:
            piece = raw.rstrip()
            if piece.endswith("\\"):
                pending.append(piece[:-1].strip())
                continue
            pending.append(piece.strip())
            logical, start = " ".join(p for p in pending if p), pending_line
            pending = []
        else:
            stripped = raw.strip()
            if not stripped or stripped[0] in "#;":
                continue
            m = _SECTION_RE.match(stripped)
            if m:
                section = m.group(1).strip().lower()
                continue
            if stripped.endswith("\\"):
                pending = [stripped[:-1].strip()]
                pending_line = lineno
                continue
            logical, start = stripped, lineno
        if "=" not in logical:
            continue
        key, value = logical.split("=", 1)
        entries.append((section, key.strip().lower(), value.strip(), start))
    return entries


def _template_of(name: str) -> str | None:
    """``backup@nightly.service`` -> ``backup@.service``; else None."""
    stem, dot, ext = name.rpartition(".")
    if not dot or "@" not in stem or stem.endswith("@"):
        return None
    return stem.split("@", 1)[0] + "@." + ext


def _sibling_unit(unit_dir: Path, name: str) -> Path | None:
    """The unit file ``name`` beside this unit, or its template, if present."""
    name = name.strip()
    if not name or "/" in name or "\\" in name:
        return None
    if Path(name).suffix.lower() not in SYSTEMD_UNIT_EXTENSIONS:
        return None
    candidate = unit_dir / name
    if candidate.is_file():
        return candidate
    template = _template_of(name)
    if template and (unit_dir / template).is_file():
        return unit_dir / template
    return None


def _resolve_path_target(unit_dir: Path, raw: str) -> Path | None:
    """Resolve a deployment path named by a unit to a file in the repo."""
    raw = raw.strip().strip('"').strip("'")
    if not raw or raw.startswith("$"):
        return None
    # Deployment paths are POSIX by definition (systemd is Linux); parse them
    # as such so `/opt/app/run.py` is absolute on every host graphify runs on.
    p = PurePosixPath(raw)
    if not p.is_absolute():
        direct = unit_dir / Path(*p.parts)
        return direct if direct.is_file() else None
    bases = _search_bases(unit_dir)
    # An absolute path is a HOST path. It may only resolve to a file inside
    # the corpus: on a Linux host `/usr/bin/mkdir` exists, and an edge to it
    # would be an edge to the machine graphify happens to run on.
    direct = Path(raw)
    if direct.is_file() and any(_is_under(direct, b) for b in bases):
        return direct
    # /opt/app/bin/run.py -> look for bin/run.py, then run.py, walking up
    # from the unit's directory; deepest match wins, shortest tail last.
    parts = p.parts[1:]  # drop the anchor
    if not parts or not p.suffix:
        return None
    for start in range(max(0, len(parts) - 3), len(parts)):
        tail = Path(*parts[start:])
        for base in bases:
            candidate = base / tail
            if candidate.is_file():
                return candidate
    return None


def _search_bases(unit_dir: Path) -> list[Path]:
    """Directories a deployment path may resolve under: the unit's directory
    and its ancestors up to the scan root. Outside a scan (a direct call)
    the walk is bounded to a few levels so it can never reach the host's
    ``/`` — where `usr/bin/python3.12` would otherwise match."""
    try:
        import graphify.extract as _extract
        root = getattr(_extract, "_XAML_ACTIVE_EXTRACT_ROOT", None)
    except Exception:  # pragma: no cover
        root = None
    bases = [unit_dir]
    for parent in unit_dir.parents:
        if root is not None:
            if not _is_under(parent, Path(root)):
                break
        elif len(bases) > 3:
            break
        bases.append(parent)
    return bases


def _is_under(path: Path, base: Path) -> bool:
    try:
        path.resolve().relative_to(base.resolve())
        return True
    except (ValueError, OSError):
        return False


def _script_from_exec(value: str) -> str | None:
    """The script a systemd ``Exec*=`` line runs, or None for a bare binary."""
    v = value.strip()
    # systemd's executable prefixes: -, @, :, +, !, !! (any combination).
    while v and v[0] in "-@:+!":
        v = v[1:]
    tokens = _SPLIT_WS_RE.split(v.strip())
    if not tokens or not tokens[0]:
        return None
    i = 0
    # `@/path/to/prog argv0 ...` — with `@` the second token is argv[0], skip it.
    if value.strip().startswith("@") and len(tokens) > 1:
        tokens = [tokens[0]] + tokens[2:]
    while i < len(tokens):
        tok = tokens[i]
        base = Path(tok).name
        if base == "env":
            # skip `env`, its VAR=val assignments and -S/-i style flags
            i += 1
            while i < len(tokens) and ("=" in tokens[i] or tokens[i].startswith("-")):
                i += 1
            continue
        if base in _INTERPRETERS or _INTERPRETER_RE.match(base):
            # `python3 -m pkg.mod` is a module, not a file; `uv run script.py`
            # and `npx tsx script.ts` carry the script one token further on.
            i += 1
            while i < len(tokens) and tokens[i].startswith("-"):
                if tokens[i] in ("-m", "--module"):
                    return None
                i += 1
            if base in ("uv", "uvx", "npx", "pipx", "poetry", "pnpm", "npm", "yarn"):
                if i < len(tokens) and tokens[i] in ("run", "exec", "tsx", "ts-node"):
                    i += 1
                while i < len(tokens) and tokens[i].startswith("-"):
                    i += 1
            continue
        return tok
    return None


def extract_systemd(path: Path) -> dict:
    """Extract a systemd unit: one file node plus its activation, script,
    documentation and ordering edges. See the module docstring."""
    try:
        entries = _read_unit(path)
    except OSError:
        return {"nodes": [], "edges": [], "error": f"cannot read {path}"}

    str_path = str(path)
    file_nid = _make_id(str_path)
    unit_dir = path.parent
    nodes: list[dict] = [{"id": file_nid, "label": path.name, "file_type": "code",
                          "source_file": str_path, "source_location": None}]
    edges: list[dict] = []
    seen: set[tuple[str, str]] = set()

    def _edge(target: Path, relation: str, line: int) -> None:
        target_nid = _make_id(str(target))
        if target_nid == file_nid or (target_nid, relation) in seen:
            return
        seen.add((target_nid, relation))
        edges.append({
            "source": file_nid, "target": target_nid, "relation": relation,
            "confidence": "EXTRACTED", "source_file": str_path,
            "source_location": f"{path.name}:{line}", "weight": 1.0,
            # Transient stamp consumed by the corpus-level id disambiguation:
            # `x.service` and `x.timer` share the extension-less file-node id,
            # and without naming the target FILE the edge would be resolved
            # against this unit's own path and turn into a self-loop.
            "target_file": str(target),
        })

    unit_kind = path.suffix.lower().lstrip(".")
    activates_key = _ACTIVATES_KEY.get(unit_kind)
    explicit_activation = False

    for section, key, value, line in entries:
        if section == unit_kind and key == activates_key:
            explicit_activation = True
            target = _sibling_unit(unit_dir, value)
            if target is not None:
                _edge(target, "activates", line)
        elif section in ("unit", "install") and key in _UNIT_REF_KEYS:
            for name in _SPLIT_WS_RE.split(value):
                target = _sibling_unit(unit_dir, name)
                if target is not None:
                    _edge(target, _UNIT_REF_KEYS[key], line)
        elif section == "unit" and key == "documentation":
            for ref in _SPLIT_WS_RE.split(value):
                if ref.startswith("file://"):
                    target = _resolve_path_target(unit_dir, ref[len("file://"):])
                    if target is not None:
                        _edge(target, "documented_by", line)
        elif section == "service" and key in _EXEC_KEYS:
            script = _script_from_exec(value)
            if script:
                target = _resolve_path_target(unit_dir, script)
                if target is not None:
                    _edge(target, "runs", line)

    # A timer/socket/path with no explicit Unit= activates the same-stem
    # .service by systemd's own convention.
    if activates_key and not explicit_activation:
        implied = _sibling_unit(unit_dir, path.stem + ".service")
        if implied is not None:
            _edge(implied, "activates", 1)

    return {"nodes": nodes, "edges": edges}
