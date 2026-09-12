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

The parser imports :mod:`graphify.detect` lazily only when it must validate
an explicit extension.  This avoids a module-level import cycle while keeping
typos from silently disabling classification.
"""
from __future__ import annotations

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

    Returned keys: ``viz_node_limit`` (int) and ``languages``
    (``{".inc": ".php", ...}``) — each present only when the file sets it.
    Unknown keys are ignored so a newer graphify's options do not break an
    older one. Malformed lines raise ``ValueError`` naming the line.
    """
    rc_path = Path(root) / RC_FILENAME
    if not rc_path.is_file():
        return {}

    cfg: dict = {}
    languages: dict[str, str] = {}
    content = rc_path.read_text(encoding="utf-8")
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
    if languages:
        cfg["languages"] = languages
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
    """Load ``<root>/.graphifyrc`` and make its language overrides active.

    A malformed file is reported once per root on stderr and treated as
    having no overrides — a scan must not die on a config typo, but the
    user must hear about it, or their ``.inc`` silently stays Pascal.
    Returns the mapping now active.
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
    """Extra cache-key material for a remapped file, else ``None``.

    An AST cache entry is keyed by content, and the same bytes parse to a
    different graph under a different extractor — so a ``.inc`` cached as
    Pascal must not be served once the project declares it PHP.
    """
    active = _active()
    if not active:
        return None
    target = active.get(Path(path).suffix.lower())
    return f"language={target}" if target else None
