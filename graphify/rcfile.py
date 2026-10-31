"""Project-level configuration: ``<root>/.graphifyrc``.

One ``key=value`` per line, ``#`` comments, blank lines ignored. Keys:

``viz_node_limit=<int>``
    Baked into the generated git hooks (see :mod:`graphify.hooks`).

``language.<ext>=<language | .ext>``
    Treat files with extension ``<ext>`` as the named language for
    classification, extractor dispatch and cross-file resolution (#2961).
    ``<ext>`` may be written with or without its leading dot; the value is
    either a language name from :data:`LANGUAGE_ALIASES` or an explicit
    extension graphify already knows (``.php``, ``.pas``, ``.sql``, ...)::

        # pfSense: every .inc under this repo is PHP, not Pascal
        language.inc=php
        # a repo whose templates are plain TypeScript
        language.tpl=.ts

    An ambiguous extension (``.inc`` is PHP, Pascal, SQL or assembly
    depending on the project; ``.m`` is Objective-C or MATLAB; ``.h`` is C or
    C++) has no single correct global mapping, so the project declares it.

``json.include=<glob>``
    Index an otherwise-unknown JSON object as a config/manifest (#4898).
    The default classifier only recognises a short filename/root-key list and
    skips everything else as data JSON (#1224). Project-specific configs
    (allowlists, registries, gate definitions) fall outside that list. Each
    matching path bypasses only the classifier: .gitignore/.graphifyignore and
    the secret-file filter still win. Repeat the key for multiple globs::

        json.include=config/**/*.json
        json.include=hooks/**/*.json

    ``json.include=all`` indexes every JSON object. JSON Schema documents stay
    skipped even under ``all`` (#2255). The glob is matched against the
    scan-root-relative POSIX path. ``**`` crosses directories and ``*`` does not.

The parser imports :mod:`graphify.detect` lazily only when it must validate
an explicit extension.  This avoids a module-level import cycle while keeping
typos from silently disabling classification.
"""
from __future__ import annotations

import hashlib
import re
import sys
import threading
from pathlib import Path

RC_FILENAME = ".graphifyrc"

# Language name -> the canonical extension graphify dispatches it under.
# Deliberately a short list of names a user is likely to type; any known
# extension can be given directly instead (``language.inc=.php``).
LANGUAGE_ALIASES: dict[str, str] = {
    "php": ".php",
    "pascal": ".pas", "delphi": ".pas", "freepascal": ".pas",
    "sql": ".sql",
    "python": ".py",
    "javascript": ".js", "js": ".js",
    "typescript": ".ts", "ts": ".ts",
    "c": ".c",
    "cpp": ".cpp", "c++": ".cpp", "cxx": ".cpp",
    "objc": ".mm", "objective-c": ".mm", "objectivec": ".mm",
    "java": ".java",
    "kotlin": ".kt",
    "scala": ".scala",
    "groovy": ".groovy",
    "go": ".go", "golang": ".go",
    "rust": ".rs",
    "ruby": ".rb",
    "csharp": ".cs", "c#": ".cs",
    "swift": ".swift",
    "lua": ".lua",
    "zig": ".zig",
    "elixir": ".ex",
    "julia": ".jl",
    "dart": ".dart",
    "r": ".r",
    "fortran": ".f90",
    "shell": ".sh", "bash": ".sh", "sh": ".sh",
    "powershell": ".ps1",
    "verilog": ".v", "systemverilog": ".sv",
    "terraform": ".tf", "hcl": ".hcl",
    "ocaml": ".ml",
    "lisp": ".lisp", "commonlisp": ".lisp",
    "markdown": ".md",
    "json": ".json",
    "yaml": ".yaml",
    "html": ".html",
}


def _normalise_ext(raw: str) -> str:
    ext = raw.strip().lower()
    if not ext.startswith("."):
        ext = "." + ext
    return ext


def parse_language_value(value: str) -> str:
    """Resolve the right-hand side of ``language.<ext>=`` to a canonical suffix.

    Accepts a name from :data:`LANGUAGE_ALIASES` (case-insensitive) or an
    explicit dotted extension. Raises ``ValueError`` for anything else.
    """
    v = value.strip()
    if not v:
        raise ValueError("empty value")
    if v.startswith("."):
        ext = _normalise_ext(v)
        if len(ext) < 2 or any(ch.isspace() for ch in ext):
            raise ValueError(f"{value!r} is not an extension")
        from graphify.detect import CODE_EXTENSIONS, DOC_EXTENSIONS
        if ext not in CODE_EXTENSIONS and ext not in DOC_EXTENSIONS:
            raise ValueError(f"unknown extension {value!r}")
        return ext
    try:
        return LANGUAGE_ALIASES[v.lower()]
    except KeyError:
        known = ", ".join(sorted(LANGUAGE_ALIASES))
        raise ValueError(
            f"unknown language {value!r} (use one of: {known}; "
            f"or an explicit extension such as .php)"
        ) from None


def load_graphifyrc(root: Path) -> dict:
    """Parse ``<root>/.graphifyrc``. Returns ``{}`` when absent.

    Returned keys: ``viz_node_limit`` (int), ``languages``
    (``{".inc": ".php", ...}``) and ``json_include`` (``["config/**/*.json"]``),
    each present only when the file sets it. Unknown keys are ignored so a
    newer graphify's options do not break an older one. Malformed lines raise
    ``ValueError`` naming the line.
    """
    rc_path = Path(root) / RC_FILENAME
    if not rc_path.is_file():
        return {}

    cfg: dict = {}
    languages: dict[str, str] = {}
    json_include: list[str] = []
    # utf-8-sig: Windows PowerShell 5.1 (`Set-Content -Encoding UTF8`) and older
    # Notepad save UTF-8 with a BOM. Read as plain utf-8, the BOM became part of
    # the first key, which then matched nothing and was ignored without a word.
    content = rc_path.read_text(encoding="utf-8-sig")
    for line_num, raw in enumerate(content.splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise ValueError(f"Invalid line {line_num} in {rc_path}: {raw!r} (expected key=value)")
        key, val = line.split("=", 1)
        key = key.strip()
        val = val.strip()
        if key == "viz_node_limit":
            try:
                parsed_val = int(val)
                if parsed_val < 0:
                    raise ValueError("must be a non-negative integer")
                cfg["viz_node_limit"] = parsed_val
            except ValueError as exc:
                raise ValueError(
                    f"Invalid viz_node_limit in {rc_path} at line {line_num}: {val!r}. "
                    f"Must be a non-negative integer."
                ) from exc
        elif key.startswith("language."):
            ext_part = key[len("language."):].strip()
            if not ext_part or any(ch.isspace() for ch in ext_part):
                raise ValueError(
                    f"Invalid language key in {rc_path} at line {line_num}: {key!r} "
                    f"(expected language.<ext>=<language>)"
                )
            try:
                target = parse_language_value(val)
            except ValueError as exc:
                raise ValueError(
                    f"Invalid {key} in {rc_path} at line {line_num}: {exc}"
                ) from None
            languages[_normalise_ext(ext_part)] = target
        elif key == "json.include":
            try:
                json_include.append(_normalise_json_include(val))
            except ValueError as exc:
                raise ValueError(
                    f"Invalid json.include in {rc_path} at line {line_num}: {exc}"
                ) from None
    if languages:
        cfg["languages"] = languages
    if json_include:
        cfg["json_include"] = json_include
    return cfg


# ---------------------------------------------------------------------------
# Active overrides for this process
# ---------------------------------------------------------------------------
#
# detect()/extract() activate the scan root's overrides for the run; the
# extraction pool forwards them to its workers (they do not inherit module
# state under ``spawn``). Stored lower-cased on both sides.

# Thread-local, not module-global: two extractions can run concurrently in one
# process (an MCP server, a threaded harness) with different roots, and a shared
# dict let one scan's `activate_language_overrides` clobber the other's while
# `effective_suffix`/`classify_file`/`cache_salt` read it — cross-contaminating
# which extractor a `.inc`/`.m`/`.h` file gets (#2961 review). Each thread now
# carries its own overrides. The dominant paths are unaffected: the CLI runs on
# the main thread, and a spawn pool worker sets its own copy in `_worker_init`
# on its main thread, the same thread that then runs `_extract_single_file`.
_local = threading.local()
_warned_roots: set[str] = set()  # warning-dedup only; harmless to share


def _active() -> dict[str, str]:
    got = getattr(_local, "active", None)
    if got is None:
        got = {}
        _local.active = got
    return got


def _normalise_json_include(raw: str) -> str:
    """Validate and normalise one ``json.include`` glob.

    Paths are repo-relative POSIX. A leading ``./`` is dropped. Absolute paths
    and parent traversal are rejected so a committed rc cannot reach outside
    the scanned tree. ``all`` is the explicit "every JSON object" sentinel.
    """
    raw = raw.strip().replace("\\", "/")
    if not raw:
        raise ValueError("empty glob")
    if raw == "all":
        return raw
    if raw.startswith("/") or re.match(r"^[A-Za-z]:/", raw):
        raise ValueError("glob must be relative to the scan root")
    while raw.startswith("./"):
        raw = raw[2:]
    if not raw:
        raise ValueError("empty glob")
    parts = raw.split("/")
    if any(part == ".." for part in parts):
        raise ValueError("glob must stay inside the scan root")
    return raw


def _glob_to_regex(pattern: str) -> re.Pattern[str]:
    """Compile a small, predictable glob into an anchored regex.

    ``**/`` matches zero or more directories, so ``config/**/*.json`` matches
    both ``config/a.json`` and ``config/sub/a.json`` (``PurePath.match`` gets
    the zero-directory case wrong). ``**`` elsewhere crosses directories;
    ``*`` and ``?`` do not.
    """
    out: list[str] = ["^"]
    i = 0
    while i < len(pattern):
        ch = pattern[i]
        if ch == "*":
            if pattern[i:i + 3] == "**/":
                out.append("(?:.*/)?")
                i += 3
                continue
            if pattern[i:i + 2] == "**":
                out.append(".*")
                i += 2
                continue
            out.append("[^/]*")
            i += 1
            continue
        if ch == "?":
            out.append("[^/]")
            i += 1
            continue
        out.append(re.escape(ch))
        i += 1
    out.append("$")
    return re.compile("".join(out))


def set_json_include(patterns: list[str] | tuple[str, ...] | None) -> None:
    """Replace this thread's JSON include globs."""
    _local.json_include = tuple(
        _normalise_json_include(p) for p in (patterns or ())
    )


def set_json_include_override(patterns: list[str] | tuple[str, ...] | None) -> None:
    """Pin the JSON policy for this thread, ignoring ``.graphifyrc``.

    The CLI flag is a per-run override, not another rc layer. Keeping it
    separate from the active tuple means every later
    ``activate_language_overrides(root)`` (detect, extract, watch) re-reads the
    rc without clobbering the flag.
    """
    _local.json_include_override = tuple(
        _normalise_json_include(p) for p in (patterns or ())
    )


def clear_json_include_override() -> None:
    """Drop a CLI override so the next activation reads ``.graphifyrc`` again."""
    if hasattr(_local, "json_include_override"):
        del _local.json_include_override


def get_json_include() -> tuple[str, ...]:
    return tuple(getattr(_local, "json_include", ()))


def json_include_matches(path: Path | str) -> bool:
    """True when *path* matches the active ``json.include`` policy.

    Matches the scan-root-relative POSIX path when a scan root is active,
    falling back to the current working directory, then to the path as given.
    The caller still applies ignore and secret filters; this only answers the
    "did the user ask for this JSON?" question.
    """
    patterns = get_json_include()
    if not patterns:
        return False
    if "all" in patterns:
        return True
    p = Path(path)
    candidates: list[str] = []
    try:
        resolved = p.resolve()
    except (OSError, RuntimeError):
        resolved = p
    bases: list[Path] = []
    try:
        from graphify.extractors.base import active_scan_root
        root = active_scan_root()
        if root is not None:
            bases.append(Path(root))
    except Exception:
        pass
    bases.append(Path.cwd())
    for base in bases:
        try:
            candidates.append(resolved.relative_to(base.resolve()).as_posix())
        except (OSError, ValueError):
            pass
    candidates.append(p.as_posix())
    for pat in patterns:
        rx = _glob_to_regex(pat)
        if any(rx.match(c) for c in candidates):
            return True
    return False


def set_language_overrides(mapping: dict[str, str] | None) -> None:
    """Replace this thread's extension overrides (``{".inc": ".php"}``)."""
    active = _active()
    active.clear()
    if mapping:
        for ext, target in mapping.items():
            active[_normalise_ext(ext)] = _normalise_ext(target)


def get_language_overrides() -> dict[str, str]:
    return dict(_active())


def activate_language_overrides(root: Path) -> dict[str, str]:
    """Load ``<root>/.graphifyrc`` and activate its project overrides.

    This covers both extension-to-language remaps and the JSON include policy.
    A malformed file is reported once per root on stderr and treated as having
    no overrides — a scan must not die on a config typo, but the user must hear
    about it, or their ``.inc`` silently stays Pascal and their config JSON
    silently stays absent. Returns the language mapping now active.
    """
    try:
        cfg = load_graphifyrc(Path(root))
    except (ValueError, OSError) as exc:
        key = str(root)
        if key not in _warned_roots:
            _warned_roots.add(key)
            print(f"[graphify] warning: ignoring {RC_FILENAME}: {exc}", file=sys.stderr)
        cfg = {}
    set_language_overrides(cfg.get("languages"))
    override = getattr(_local, "json_include_override", None)
    set_json_include(override if override is not None else cfg.get("json_include"))
    return get_language_overrides()


def effective_suffix(path: Path | str) -> str:
    """The suffix graphify should treat ``path`` as having.

    Returns the override target when the file's extension is remapped, else
    the real suffix untouched (case preserved, so callers that distinguish
    ``.F90`` from ``.f90`` keep doing so).
    """
    suffix = Path(path).suffix
    active = _active()
    if not active:
        return suffix
    return active.get(suffix.lower(), suffix)


def cache_salt(path: Path | str) -> str | None:
    """Extra cache-key material for a remapped or policy-controlled file.

    An AST cache entry is keyed by content, and the same bytes parse to a
    different graph under a different extractor or JSON policy. The manifest
    stores this under its generic ``language`` field, so a policy change also
    invalidates the incremental gate instead of serving a zero-node cache hit.
    """
    parts: list[str] = []
    active = _active()
    target = active.get(Path(path).suffix.lower()) if active else None
    if target:
        parts.append(f"language={target}")
    patterns = get_json_include()
    if patterns and Path(path).suffix.lower() == ".json":
        digest = hashlib.sha1("\0".join(sorted(patterns)).encode("utf-8")).hexdigest()[:12]
        parts.append(f"json_include={digest}")
    return ";".join(parts) or None
