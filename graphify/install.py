"""graphify install/uninstall subsystem.

The per-platform skill/hook installers and uninstallers, extracted verbatim from
graphify/__main__.py so the CLI dispatcher (`main`) stays readable. Import path is
unchanged: `graphify.__main__` re-exports every name defined here, so
`from graphify.__main__ import claude_install` (etc.) keeps working.

Lives at graphify/install.py (same package dir as __main__) on purpose: the
installers resolve packaged assets via `Path(__file__).parent / "always_on"` and
`/ "skills"`, which only works from within the graphify/ directory.
"""

from __future__ import annotations
import contextlib
import errno
import functools
import hashlib
import json
import os
import platform
import re
import shutil
import stat
import sys
import threading
import time
from pathlib import Path
from typing import NoReturn

if sys.platform == "win32":
    import msvcrt
    fcntl = None
else:
    import fcntl
    msvcrt = None

try:
    from importlib.metadata import version as _pkg_version

    __version__ = _pkg_version("graphifyy")
except Exception:
    __version__ = "unknown"

from graphify.paths import GRAPHIFY_OUT as _GRAPHIFY_OUT
from graphify.paths import os_replace_with_fallback as _os_replace_with_fallback
from graphify.paths import write_text_atomic as _write_text_atomic


def _skill_lock_path(skill_dir: Path) -> Path:
    """The lock file for ``skill_dir``, kept out of the skill directory."""
    try:
        real = skill_dir.resolve()
    except (OSError, RuntimeError):
        real = skill_dir.absolute()
    digest = hashlib.sha256(os.path.normcase(str(real)).encode("utf-8")).hexdigest()[:16]
    return Path.home() / ".cache" / "graphify" / "skill-locks" / f"{digest}.lock"


_held_skill_locks = threading.local()


def _try_skill_lock(fh) -> bool:
    try:
        if fcntl is not None:
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        else:
            fh.seek(0)
            msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
    except OSError as exc:
        if exc.errno in (errno.EAGAIN, errno.EWOULDBLOCK, errno.EACCES):
            return False
        raise
    return True


def _release_skill_lock(fh) -> None:
    with contextlib.suppress(OSError):
        if fcntl is not None:
            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
        else:
            fh.seek(0)
            msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)


@contextlib.contextmanager
def _skill_lock(skill_dir: Path, *, wait: bool = True):
    path = _skill_lock_path(skill_dir)
    held = _held_skill_locks.__dict__.setdefault("paths", set())
    if path in held:
        yield True
        return
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        fh = open(path, "a+b")
    except OSError:
        fh = None
    if fh is None:
        yield None
        return
    with fh:
        try:
            locked = _try_skill_lock(fh)
            while not locked and wait:
                time.sleep(0.05)
                locked = _try_skill_lock(fh)
        except OSError:
            locked = None
        if not locked:
            yield locked
            return
        held.add(path)
        try:
            yield True
        finally:
            held.discard(path)
            _release_skill_lock(fh)


def _write_version_stamp(skill_dst: Path, version: str) -> None:
    version_file = skill_dst.parent / ".graphify_version"
    tmp = version_file.with_name(".graphify_version.tmp")
    try:
        tmp.write_text(version, encoding="utf-8")
        _os_replace_with_fallback(tmp, version_file)
    except Exception:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
        raise


@functools.lru_cache(maxsize=None)
def _always_on(basename: str) -> str:
    path = Path(__file__).parent / "always_on" / f"{basename}.md"
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        raise RuntimeError(
            f"graphify install is incomplete: missing always-on block '{basename}' "
            f"at {path}. Reinstall graphifyy (e.g. `uv tool install --reinstall graphifyy`)."
        ) from exc


def _mimo_global_config_dir() -> Path:
    if os.environ.get("MIMOCODE_HOME"):
        return Path(os.environ["MIMOCODE_HOME"]) / "config"
    if os.environ.get("XDG_CONFIG_HOME"):
        return Path(os.environ["XDG_CONFIG_HOME"]) / "mimocode"
    return Path.home() / ".config" / "mimocode"


def _platform_skill_destination(platform_name: str, *, project: bool = False, project_dir: Path | None = None) -> Path:
    if platform_name == "gemini":
        if project:
            return (project_dir or Path(".")) / ".gemini" / "skills" / "graphify" / "SKILL.md"
        if platform.system() == "Windows":
            return Path.home() / ".agents" / "skills" / "graphify" / "SKILL.md"
        return Path.home() / ".gemini" / "skills" / "graphify" / "SKILL.md"

    if platform_name == "opencode":
        if project:
            return (project_dir or Path(".")) / ".opencode" / "skills" / "graphify" / "SKILL.md"
        return Path.home() / ".config" / "opencode" / "skills" / "graphify" / "SKILL.md"

    if platform_name == "hermes":
        if project:
            return (project_dir or Path(".")) / ".hermes" / "skills" / "graphify" / "SKILL.md"
        if platform.system() == "Windows":
            local_appdata = Path(os.environ.get("LOCALAPPDATA") or (Path.home() / "AppData" / "Local"))
            return local_appdata / "hermes" / "skills" / "graphify" / "SKILL.md"
        return Path.home() / ".hermes" / "skills" / "graphify" / "SKILL.md"

    if platform_name == "devin":
        if project:
            return (project_dir or Path(".")) / ".devin" / "skills" / "graphify" / "SKILL.md"
        return Path.home() / ".config" / "devin" / "skills" / "graphify" / "SKILL.md"

    if platform_name == "amp":
        if project:
            return (project_dir or Path(".")) / ".agents" / "skills" / "graphify" / "SKILL.md"
        return Path.home() / ".config" / "agents" / "skills" / "graphify" / "SKILL.md"

    if platform_name == "agents":
        if project:
            return (project_dir or Path(".")) / ".agents" / "skills" / "graphify" / "SKILL.md"
        return Path.home() / ".agents" / "skills" / "graphify" / "SKILL.md"

    if platform_name in ("antigravity", "antigravity-windows"):
        if project:
            return (project_dir or Path(".")) / ".agents" / "skills" / "graphify" / "SKILL.md"
        return Path.home() / ".gemini" / "config" / "skills" / "graphify" / "SKILL.md"

    if platform_name in ("mimo", "mimo-windows"):
        if project:
            return (project_dir or Path(".")) / ".mimocode" / "skills" / "graphify" / "SKILL.md"
        return _mimo_global_config_dir() / "skills" / "graphify" / "SKILL.md"

    cfg = _PLATFORM_CONFIG[platform_name]
    if project:
        return (project_dir or Path(".")) / cfg["skill_dst"]

    if platform_name in ("claude", "windows") and os.environ.get("CLAUDE_CONFIG_DIR"):
        return Path(os.environ["CLAUDE_CONFIG_DIR"]) / "skills" / "graphify" / "SKILL.md"
    return Path.home() / cfg["skill_dst"]


def _packaged_skill_refs_dir(platform_name: str) -> Path | None:
    if platform_name == "gemini":
        bundle = "claude"
    else:
        bundle = _PLATFORM_CONFIG[platform_name].get("skill_refs")
    if not bundle:
        return None
    bundle_dir = Path(__file__).parent / "skills" / bundle
    if not bundle_dir.is_dir():
        return None
    return bundle_dir / "references"


def _install_skill_references(skill_dst: Path, refs_src: Path) -> None:
    refs_dst = skill_dst.parent / "references"
    refs_staged = skill_dst.parent / "references.tmp"
    if refs_staged.exists():
        shutil.rmtree(refs_staged)
    try:
        shutil.copytree(refs_src, refs_staged)
        for path in (refs_staged, *refs_staged.rglob("*")):
            path.chmod(path.stat().st_mode | stat.S_IWUSR)
        if refs_dst.exists():
            shutil.rmtree(refs_dst)
        os.replace(refs_staged, refs_dst)
    except Exception:
        if refs_staged.exists():
            shutil.rmtree(refs_staged, ignore_errors=True)
        raise


def _copy_skill_file(platform_name: str, *, project: bool = False, project_dir: Path | None = None) -> Path:
    skill_file = "skill.md" if platform_name == "gemini" else _PLATFORM_CONFIG[platform_name]["skill_file"]
    skill_src = Path(__file__).parent / skill_file
    if not skill_src.exists():
        print(f"error: {skill_file} not found in package - reinstall graphify", file=sys.stderr)
        sys.exit(1)

    refs_src = _packaged_skill_refs_dir(platform_name)
    if refs_src is not None and not refs_src.exists():
        print(
            f"error: references for '{platform_name}' not found in package "
            f"({refs_src}) - reinstall graphify",
            file=sys.stderr,
        )
        sys.exit(1)

    skill_dst = _platform_skill_destination(platform_name, project=project, project_dir=project_dir)
    with _skill_lock(skill_dst.parent):
        skill_dst.parent.mkdir(parents=True, exist_ok=True)
        if refs_src is not None:
            _install_skill_references(skill_dst, refs_src)
            print(f"  references       ->  {skill_dst.parent / 'references'}")
        else:
            orphan_refs = skill_dst.parent / "references"
            if orphan_refs.exists():
                shutil.rmtree(orphan_refs)

        try:
            if skill_dst.exists() and skill_dst.read_bytes() != skill_src.read_bytes():
                backup = skill_dst.with_suffix(skill_dst.suffix + ".bak")
                shutil.copy2(skill_dst, backup)
                print(f"  previous copy    ->  {backup} (differed from the packaged skill)")
        except OSError:
            pass

        tmp_dst = skill_dst.with_suffix(skill_dst.suffix + ".tmp")
        try:
            shutil.copy(skill_src, tmp_dst)
            _os_replace_with_fallback(tmp_dst, skill_dst)
        except Exception:
            try:
                tmp_dst.unlink(missing_ok=True)
            except OSError:
                pass
            raise

        _write_version_stamp(skill_dst, __version__)
        print(f"  skill installed  ->  {skill_dst}")
    return skill_dst


def _remove_skill_file(platform_name: str, *, project: bool = False, project_dir: Path | None = None) -> bool:
    skill_dst = _platform_skill_destination(platform_name, project=project, project_dir=project_dir)
    removed = False
    with _skill_lock(skill_dst.parent):
        if skill_dst.exists():
            skill_dst.unlink()
            print(f"  skill removed    ->  {skill_dst}")
            removed = True
        version_file = skill_dst.parent / ".graphify_version"
        if version_file.exists():
            version_file.unlink()
            removed = True
        refs_dir = skill_dst.parent / "references"
        if refs_dir.exists():
            shutil.rmtree(refs_dir)
            removed = True
        for d in (skill_dst.parent, skill_dst.parent.parent, skill_dst.parent.parent.parent):
            try:
                d.rmdir()
            except OSError:
                break
    return removed


def _project_scope_root(path: Path, project_dir: Path) -> Path:
    try:
        rel = path.relative_to(project_dir)
    except ValueError:
        return path
    return project_dir / rel.parts[0] if rel.parts else path


def _remove_claude_skill_registration(project_dir: Path) -> None:
    claude_md = project_dir / ".claude" / "CLAUDE.md"
    if not claude_md.exists():
        return
    content, newline = _read_keep_newline(claude_md)
    cleaned = _remove_marker_section(content, _SKILL_REGISTRATION_MARKER, boundary_prefix="# ")
    if cleaned is None:
        return
    if cleaned or claude_md.is_symlink():
        _write_keep_newline(claude_md, cleaned + "\n", newline)
        print(f"  CLAUDE.md        ->  graphify skill registration removed from {_shown_path(claude_md)}")
    else:
        claude_md.unlink()
        print(f"  CLAUDE.md        ->  deleted {claude_md}")


def _print_project_git_add_hint(paths: list[Path]) -> None:
    unique: list[str] = []
    for path in paths:
        text = path.as_posix().rstrip("/")
        if path.exists() and path.is_dir():
            text += "/"
        if text not in unique:
            unique.append(text)
    if not unique:
        return
    print()
    print("Project-scoped install. Add to version control:")
    print(f"  git add {' '.join(unique)}")


def _claude_pretooluse_hooks(strict: bool = False, project: bool = False) -> list[dict]:
    exe = _resolve_graphify_exe(project=project)
    if " " in exe and not exe.startswith('"'):
        exe = f'"{exe}"'
    read_cmd = f"{exe} hook-guard read" + (" --strict" if strict else "")
    return [
        {"matcher": "Bash|Grep", "hooks": [{"type": "command", "command": f"{exe} hook-guard search", "timeout": 10}]},
        {"matcher": "Read|Glob", "hooks": [{"type": "command", "command": read_cmd, "timeout": 10}]},
    ]


_GRAPHIFY_HOOK_SUBCOMMANDS = ("hook-guard", "hook-check")
_GRAPHIFY_LEGACY_HOOK_MARKER = "graphify-out/"


def _is_graphify_hook_command(command: str) -> bool:
    """True when a hook ``command`` string is one graphify installed."""
    lowered = command.lower()
    if "graphify" not in lowered:
        return False
    if any(sub in lowered for sub in _GRAPHIFY_HOOK_SUBCOMMANDS):
        return True
    return _GRAPHIFY_LEGACY_HOOK_MARKER in lowered


def _is_graphify_hook_entry(entry: object) -> bool:
    """True when a single ``hooks[]`` element is a graphify command entry."""
    if not isinstance(entry, dict) or entry.get("type") != "command":
        return False
    command = entry.get("command")
    return isinstance(command, str) and _is_graphify_hook_command(command)


def _strip_graphify_hooks(groups: list) -> list:
    """Drop graphify's own hook entries from *groups*, keeping everything else."""
    kept: list = []
    for group in groups:
        if not isinstance(group, dict):
            kept.append(group)
            continue
        entries = group.get("hooks")
        if not isinstance(entries, list):
            kept.append(group)
            continue
        remaining = [e for e in entries if not _is_graphify_hook_entry(e)]
        if len(remaining) == len(entries):
            kept.append(group)
        elif remaining:
            kept.append({**group, "hooks": remaining})
    return kept


def _skill_registration(skill_path: str = "~/.claude/skills/graphify/SKILL.md") -> str:
    return (
        "# graphify\n"
        f"- **graphify** (`{skill_path}`) "
        "- any input to knowledge graph. Trigger: `/graphify`\n"
        "When the user types `/graphify`, use the installed graphify skill "
        "or instructions before doing anything else.\n"
    )


def _shown_path(path: Path) -> str:
    if path.is_symlink():
        return f"{path} -> {path.resolve()}"
    return str(path)


def _register_always_on_block(target: Path, prefix: str, registration: str) -> None:
    """Idempotently add or refresh an always-on registration in *target*, degrading
    instead of raising.
    """
    try:
        existed = target.exists()
        content, newline = _read_keep_newline(target) if existed else ("", "\n")
        new_content = _replace_or_append_section(
            content, _SKILL_REGISTRATION_MARKER, registration, boundary_prefix="# "
        )
        if existed and new_content == content:
            print(f"{prefix}already registered (no change)")
        elif existed:
            _write_keep_newline(target, new_content, newline)
            print(f"{prefix}skill registered in {_shown_path(target)}")
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            _write_keep_newline(target, new_content, newline)
            print(f"{prefix}created at {_shown_path(target)}")
    except OSError as exc:
        print(f"{prefix}skipped: {exc.__class__.__name__}: {exc}", file=sys.stderr)
        print(
            f"  hint: the skill files were installed; add the graphify block to "
            f"{target} manually to finish always-on registration",
            file=sys.stderr,
        )


_PLATFORM_CONFIG: dict[str, dict] = {
    "claude": {"skill_file": "skill.md", "skill_dst": Path(".claude") / "skills" / "graphify" / "SKILL.md", "claude_md": True, "skill_refs": "claude"},
    "codex": {"skill_file": "skill-codex.md", "skill_dst": Path(".codex") / "skills" / "graphify" / "SKILL.md", "claude_md": False, "skill_refs": "codex"},
    "opencode": {"skill_file": "skill-opencode.md", "skill_dst": Path(".config") / "opencode" / "skills" / "graphify" / "SKILL.md", "claude_md": False, "skill_refs": "opencode"},
    "kilo": {"skill_file": "skill-kilo.md", "skill_dst": Path(".config") / "kilo" / "skills" / "graphify" / "SKILL.md", "claude_md": False, "skill_refs": "kilo"},
    "aider": {"skill_file": "skill-aider.md", "skill_dst": Path(".aider") / "graphify" / "SKILL.md", "claude_md": False},
    "copilot": {"skill_file": "skill-copilot.md", "skill_dst": Path(".copilot") / "skills" / "graphify" / "SKILL.md", "claude_md": False, "skill_refs": "copilot"},
    "claw": {"skill_file": "skill-claw.md", "skill_dst": Path(".openclaw") / "skills" / "graphify" / "SKILL.md", "claude_md": False, "skill_refs": "claw"},
    "droid": {"skill_file": "skill-droid.md", "skill_dst": Path(".factory") / "skills" / "graphify" / "SKILL.md", "claude_md": False, "skill_refs": "droid"},
    "trae": {"skill_file": "skill-trae.md", "skill_dst": Path(".trae") / "skills" / "graphify" / "SKILL.md", "claude_md": False, "skill_refs": "trae"},
    "trae-cn": {"skill_file": "skill-trae.md", "skill_dst": Path(".trae-cn") / "skills" / "graphify" / "SKILL.md", "claude_md": False, "skill_refs": "trae"},
    "hermes": {"skill_file": "skill-claw.md", "skill_dst": Path(".hermes") / "skills" / "graphify" / "SKILL.md", "claude_md": False, "skill_refs": "claw"},
    "kiro": {"skill_file": "skill-kiro.md", "skill_dst": Path(".kiro") / "skills" / "graphify" / "SKILL.md", "claude_md": False, "skill_refs": "kiro"},
    "pi": {"skill_file": "skill-pi.md", "skill_dst": Path(".pi") / "agent" / "skills" / "graphify" / "SKILL.md", "claude_md": False, "skill_refs": "pi"},
    "codebuddy": {"skill_file": "skill.md", "skill_dst": Path(".codebuddy") / "skills" / "graphify" / "SKILL.md", "claude_md": False, "skill_refs": "claude"},
    "antigravity": {"skill_file": "skill.md", "skill_dst": Path(".agents") / "skills" / "graphify" / "SKILL.md", "claude_md": False, "skill_refs": "claude"},
    "antigravity-windows": {"skill_file": "skill-windows.md", "skill_dst": Path(".agents") / "skills" / "graphify" / "SKILL.md", "claude_md": False, "skill_refs": "windows"},
    "mimo": {"skill_file": "skill-opencode.md", "skill_dst": Path(".config") / "mimocode" / "skills" / "graphify" / "SKILL.md", "claude_md": False, "skill_refs": "opencode"},
    "mimo-windows": {"skill_file": "skill-windows.md", "skill_dst": Path(".config") / "mimocode" / "skills" / "graphify" / "SKILL.md", "claude_md": False, "skill_refs": "windows"},
    "windows": {"skill_file": "skill-windows.md", "skill_dst": Path(".claude") / "skills" / "graphify" / "SKILL.md", "claude_md": True, "skill_refs": "windows"},
    "kimi": {"skill_file": "skill.md", "skill_dst": Path(".kimi") / "skills" / "graphify" / "SKILL.md", "claude_md": False, "skill_refs": "claude"},
    "amp": {"skill_file": "skill-amp.md", "skill_dst": Path(".agents") / "skills" / "graphify" / "SKILL.md", "claude_md": False, "skill_refs": "amp"},
    "agents": {"skill_file": "skill-agents.md", "skill_dst": Path(".agents") / "skills" / "graphify" / "SKILL.md", "claude_md": False, "skill_refs": "agents"},
    "devin": {"skill_file": "skill-devin.md", "skill_dst": Path(".config") / "devin" / "skills" / "graphify" / "SKILL.md", "claude_md": False},
}

_PLATFORM_ALIASES: dict[str, str] = {"skills": "agents"}


def _canonical_platform(platform_name: str) -> str:
    return _PLATFORM_ALIASES.get(platform_name, platform_name)


def _replace_or_append_section(
    content: str, marker: str, new_section: str, boundary_prefix: str = "## "
) -> str:
    lines = content.split("\n")
    starts = [i for i, line in enumerate(lines) if line.strip() == marker]
    if not starts:
        if content.strip():
            return content.rstrip() + "\n\n" + new_section.lstrip()
        return new_section.lstrip()

    start = starts[-1]
    end = len(lines)
    for j in range(start + 1, len(lines)):
        if lines[j].startswith(boundary_prefix):
            end = j
            break

    head = "\n".join(lines[:start]).rstrip()
    tail = "\n".join(lines[end:]).lstrip()
    section = new_section.strip()

    parts: list[str] = []
    if head:
        parts.append(head)
    parts.append(section)
    if tail:
        parts.append(tail)
    out = "\n\n".join(parts)
    if not out.endswith("\n"):
        out += "\n"
    return out


def _remove_marker_section(content: str, marker: str, boundary_prefix: str = "## ") -> str | None:
    lines = content.split("\n")
    removed = False
    while True:
        starts = [i for i, line in enumerate(lines) if line.strip() == marker]
        if not starts:
            break
        start = starts[-1]
        end = len(lines)
        for j in range(start + 1, len(lines)):
            if lines[j].startswith(boundary_prefix):
                end = j
                break
        head = "\n".join(lines[:start]).rstrip()
        tail = "\n".join(lines[end:]).lstrip()
        merged = head + "\n\n" + tail if head and tail else (head or tail)
        lines = merged.split("\n")
        removed = True
    if not removed:
        return None
    return "\n".join(lines).rstrip()


def _read_keep_newline(path: Path) -> tuple[str, str]:
    """Read *path* as UTF-8 and return ``(text, newline)``."""
    raw = path.read_bytes().decode("utf-8")
    newline = "\r\n" if "\r\n" in raw else "\n"
    return raw.replace("\r\n", "\n").replace("\r", "\n"), newline


def _write_keep_newline(path: Path, text: str, newline: str = "\n") -> None:
    """Write bare-``\n`` *text* using *newline* endings, without translation."""
    if newline != "\n":
        text = text.replace("\n", newline)
    path.write_text(text, encoding="utf-8", newline="")


_BANNER_LOGO = """\
     ▄▄▀█▀▄▄
 ▄▄▀▀  ▄█▄  ▀▀▄▄
██▀▀▀▀▀███▀▀▀▀▀▀▀    ▄█████▄                            ██       ██  ▄████
█ ▀▄  ▄▀             ██▀   ▀▀▀ ██▄███  ██████▄ ██▄████▄ ██▄████▄ ▄▄ █████  ██    ██
█   ███    ███▀▀█   ██  █████ ██▀     ▄▄▄▄▄██ ██▀  ▀██ ██▀  ▀██ ██  ██    ▀██  ██▀
█   ▀▀█▄   ▀▀▀▄ █   ██▄   ▄██ ██     ██▀▀▀▀██ ██▄  ▄██ ██    ██ ██  ██     ▀█▄▄█▀
█      ███     ▀█    ▀████▀██ ██     ▀██████▀ ██▀████▀ ██    ██ ██  ██      ▀██▀
▀██▀▀▀▀▀█▀▀▀▀▀██▀                               ██                           ▄██
   ▀▀▄▄ █ ▄▄▀▀                                 ██                          ██▀
       ▀▀▀"""


def _print_banner() -> None:
    if not sys.stdout.isatty():
        return
    try:
        if sys.platform == "win32":
            import ctypes
            ctypes.windll.kernel32.SetConsoleMode(
                ctypes.windll.kernel32.GetStdHandle(-11), 7
            )
        G = "\033[38;2;17;141;79m"
        D = "\033[2m"
        R = "\033[0m"
        lines = [f"  {G}{line}{R}" for line in _BANNER_LOGO.splitlines()]
        lines[6] += f"  {D}{__version__}{R}"
        print("\n" + "\n".join(lines) + "\n")
    except Exception:
        pass


def install(platform: str = "claude", *, project: bool = False, project_dir: Path | None = None) -> None:
    _print_banner()
    platform = _canonical_platform(platform)
    if platform == "gemini":
        gemini_install(project_dir=project_dir, project=project)
        return
    if platform == "cursor":
        _cursor_install(Path("."))
        return
    if platform == "antigravity" and sys.platform == "win32":
        platform = "antigravity-windows"
    if platform == "mimo" and sys.platform == "win32":
        platform = "mimo-windows"
    if platform in ("mimo", "mimo-windows"):
        _mimo_install((project_dir or Path(".")) if project else Path("."), project=project)
        return
    if platform not in _PLATFORM_CONFIG:
        print(
            f"error: unknown platform '{platform}'. Choose from: {', '.join(_PLATFORM_CONFIG)}, gemini, cursor",
            file=sys.stderr,
        )
        sys.exit(1)

    cfg = _PLATFORM_CONFIG[platform]
    project_dir = project_dir or Path(".")
    skill_dst = _copy_skill_file(platform, project=project, project_dir=project_dir)

    if platform == "kilo":
        command_src = Path(__file__).parent / "command-kilo.md"
        if not command_src.exists():
            print("error: command-kilo.md not found in package - reinstall graphify", file=sys.stderr)
            sys.exit(1)
        command_dst = Path.home() / ".config" / "kilo" / "command" / "graphify.md"
        command_dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(command_src, command_dst)
        print(f"  command installed ->  {command_dst}")

    if cfg["claude_md"]:
        if project:
            claude_md = project_dir / ".claude" / "CLAUDE.md"
            skill_ref = ".claude/skills/graphify/SKILL.md"
        elif os.environ.get("CLAUDE_CONFIG_DIR"):
            config_dir = Path(os.environ["CLAUDE_CONFIG_DIR"])
            claude_md = config_dir / "CLAUDE.md"
            skill_ref = str(config_dir / "skills" / "graphify" / "SKILL.md")
        else:
            claude_md = Path.home() / ".claude" / "CLAUDE.md"
            skill_ref = "~/.claude/skills/graphify/SKILL.md"
        _register_always_on_block(
            claude_md, "  CLAUDE.md        ->  ", _skill_registration(skill_ref)
        )

    if platform == "codebuddy":
        _register_always_on_block(
            Path.home() / ".codebuddy" / "CODEBUDDY.md",
            "  CODEBUDDY.md     ->  ",
            _skill_registration("~/.codebuddy/skills/graphify/SKILL.md"),
        )

    if platform == "opencode":
        _install_opencode_plugin(project_dir if project else Path("."))

    if project:
        _print_project_git_add_hint([_project_scope_root(skill_dst, project_dir)])

    print()
    print("Done. Open your AI coding assistant and type:")
    print()
    print("  /graphify .")
    print()
    print("Prefer a hosted version? Try the graphify platform free for 14 days:")
    print("https://app.graphify.com")
    print()


def _print_install_usage() -> None:
    platforms = ", ".join([*_PLATFORM_CONFIG, "gemini", "cursor"])
    print("Usage: graphify install [--project] [--strict] [--platform P|P]")
    print(f"Platforms: {platforms}")
    print("  --strict  block the first raw file read per session until one "
          "`graphify query` runs (Claude Code project hook only; needs --project)")


_CLAUDE_MD_MARKER = "## graphify"
_CODEBUDDY_MD_MARKER = "## graphify"
_AGENTS_MD_MARKER = "## graphify"
_GEMINI_MD_MARKER = "## graphify"
_SKILL_REGISTRATION_MARKER = "# graphify"


def _gemini_hook(project: bool = False) -> dict:
    exe = _resolve_graphify_exe(project=project)
    if " " in exe and not exe.startswith('"'):
        exe = f'"{exe}"'
    return {
        "matcher": "read_file|list_directory",
        "hooks": [{"type": "command", "command": f"{exe} hook-guard gemini"}],
    }


def gemini_install(project_dir: Path | None = None, *, project: bool = False) -> None:
    project_dir = project_dir or Path(".")
    skill_dst = _copy_skill_file("gemini", project=project, project_dir=project_dir)
    target = project_dir / "GEMINI.md"

    if target.exists():
        content, newline = _read_keep_newline(target)
        new_content = _replace_or_append_section(
            content, _GEMINI_MD_MARKER, _always_on("gemini-md")
        )
    else:
        content, newline = "", "\n"
        new_content = _always_on("gemini-md")

    if target.exists() and new_content == content:
        print(f"graphify already configured in {target.resolve()} (no change)")
    else:
        _write_keep_newline(target, new_content, newline)
        print(f"graphify section written to {target.resolve()}")

    _install_gemini_hook(project_dir, project=project)
    if project:
        _print_project_git_add_hint([_project_scope_root(skill_dst, project_dir), project_dir / "GEMINI.md", project_dir / ".gemini"])
    print()
    print("Gemini CLI will now check the knowledge graph before answering")
    print("codebase questions and rebuild it after code changes.")


def _refuse_to_modify(settings_path: Path) -> NoReturn:
    print(
        f"[graphify] refusing to modify {settings_path}: not valid JSON "
        "(fix or move it and re-run)",
        file=sys.stderr,
    )
    sys.exit(1)


def _read_settings_for_merge(settings_path: Path) -> dict:
    if not settings_path.exists():
        return {}
    try:
        settings = json.loads(settings_path.read_text(encoding="utf-8-sig"))
    except (json.JSONDecodeError, UnicodeDecodeError, OSError):
        settings = None
    if not isinstance(settings, dict):
        _refuse_to_modify(settings_path)
    return settings


def _write_settings_with_backup(settings_path: Path, settings: dict) -> None:
    output = json.dumps(settings, indent=2)
    if settings_path.exists():
        if settings_path.read_text(encoding="utf-8") == output:
            return
        backup = settings_path.with_name(settings_path.name + ".graphify-bak")
        shutil.copy2(settings_path, backup)
    settings_path.write_text(output, encoding="utf-8")


def _install_gemini_hook(project_dir: Path, project: bool = False) -> None:
    settings_path = project_dir / ".gemini" / "settings.json"
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings = _read_settings_for_merge(settings_path)
    hooks = settings.setdefault("hooks", {})
    if not isinstance(hooks, dict):
        _refuse_to_modify(settings_path)
    before_tool = hooks.setdefault("BeforeTool", [])
    if not isinstance(before_tool, list):
        _refuse_to_modify(settings_path)
    hooks["BeforeTool"] = _strip_graphify_hooks(before_tool)
    hooks["BeforeTool"].append(_gemini_hook(project=project))
    _write_settings_with_backup(settings_path, settings)
    print("  .gemini/settings.json  ->  BeforeTool hook registered")


def _uninstall_gemini_hook(project_dir: Path) -> None:
    settings_path = project_dir / ".gemini" / "settings.json"
    if not settings_path.exists():
        return
    try:
        settings = json.loads(settings_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return
    before_tool = settings.get("hooks", {}).get("BeforeTool", [])
    if not isinstance(before_tool, list):
        return
    filtered = _strip_graphify_hooks(before_tool)
    if filtered == before_tool:
        return
    settings["hooks"]["BeforeTool"] = filtered
    _write_settings_with_backup(settings_path, settings)
    print("  .gemini/settings.json  ->  BeforeTool hook removed")


def gemini_uninstall(project_dir: Path | None = None, *, project: bool = False, remove_user_skill: bool | None = None) -> None:
    explicit_dir = project_dir is not None
    project_dir = project_dir or Path(".")
    if remove_user_skill is None:
        remove_user_skill = not project and not explicit_dir
    if project or (explicit_dir and not remove_user_skill):
        _remove_skill_file("gemini", project=True, project_dir=project_dir)
    if remove_user_skill:
        _remove_skill_file("gemini", project=False)

    target = project_dir / "GEMINI.md"
    if not target.exists():
        print("No GEMINI.md found in current directory - nothing to do")
        return
    content, newline = _read_keep_newline(target)
    cleaned = _remove_marker_section(content, _GEMINI_MD_MARKER)
    if cleaned is None:
        print("graphify section not found in GEMINI.md - nothing to do")
        return
    if cleaned or target.is_symlink():
        _write_keep_newline(target, cleaned + "\n", newline)
        print(f"graphify section removed from {target.resolve()}")
    else:
        target.unlink()
        print(f"GEMINI.md was empty after removal - deleted {target.resolve()}")
    _uninstall_gemini_hook(project_dir)


_VSCODE_INSTRUCTIONS_MARKER = "## graphify"


def _vscode_skill_destination() -> Path:
    return Path.home() / ".copilot" / "skills" / "graphify" / "SKILL.md"


def vscode_install(project_dir: Path | None = None) -> None:
    skill_src = Path(__file__).parent / "skill-vscode.md"
    refs_bundle = "vscode"
    if not skill_src.exists():
        skill_src = Path(__file__).parent / "skill-copilot.md"
        refs_bundle = "copilot"
    skill_dst = _vscode_skill_destination()
    with _skill_lock(skill_dst.parent):
        skill_dst.parent.mkdir(parents=True, exist_ok=True)
        tmp_dst = skill_dst.with_suffix(skill_dst.suffix + ".tmp")
        try:
            shutil.copy(skill_src, tmp_dst)
            _os_replace_with_fallback(tmp_dst, skill_dst)
        except Exception:
            try:
                tmp_dst.unlink(missing_ok=True)
            except OSError:
                pass
            raise
        refs_src = Path(__file__).parent / "skills" / refs_bundle / "references"
        if refs_src.exists():
            _install_skill_references(skill_dst, refs_src)
            print(f"  references       ->  {skill_dst.parent / 'references'}")
        else:
            orphan_refs = skill_dst.parent / "references"
            if orphan_refs.exists():
                shutil.rmtree(orphan_refs)
        _write_version_stamp(skill_dst, __version__)
        print(f"  skill installed  ->  {skill_dst}")

    instructions = (project_dir or Path(".")) / ".github" / "copilot-instructions.md"
    instructions.parent.mkdir(parents=True, exist_ok=True)
    if instructions.exists():
        content, newline = _read_keep_newline(instructions)
        new_content = _replace_or_append_section(
            content, _VSCODE_INSTRUCTIONS_MARKER, _always_on("vscode-instructions")
        )
        if new_content == content:
            print(f"  {instructions}  ->  already configured (no change)")
        else:
            _write_keep_newline(instructions, new_content, newline)
            print(f"  {instructions}  ->  graphify section {'updated' if _VSCODE_INSTRUCTIONS_MARKER in content else 'added'}")
    else:
        _write_keep_newline(instructions, _always_on("vscode-instructions"))
        print(f"  {instructions}  ->  created")

    print()
    print(
        "VS Code Copilot Chat configured. Type /graphify in the chat panel to build the graph."
    )
    print("Note: for GitHub Copilot CLI (terminal), use: graphify copilot install")


def vscode_uninstall(project_dir: Path | None = None) -> None:
    skill_dst = _vscode_skill_destination()
    with _skill_lock(skill_dst.parent):
        if skill_dst.exists():
            skill_dst.unlink()
            print(f"  skill removed    ->  {skill_dst}")
        version_file = skill_dst.parent / ".graphify_version"
        if version_file.exists():
            version_file.unlink()
        refs_dir = skill_dst.parent / "references"
        if refs_dir.exists():
            shutil.rmtree(refs_dir)
        for d in (skill_dst.parent, skill_dst.parent.parent, skill_dst.parent.parent.parent):
            try:
                d.rmdir()
            except OSError:
                break

    instructions = (project_dir or Path(".")) / ".github" / "copilot-instructions.md"
    if not instructions.exists():
        return
    content, newline = _read_keep_newline(instructions)
    cleaned = _remove_marker_section(content, _VSCODE_INSTRUCTIONS_MARKER)
    if cleaned is None:
        return
    if cleaned or instructions.is_symlink():
        _write_keep_newline(instructions, cleaned + "\n", newline)
        print(f"  graphify section removed from {instructions}")
    else:
        instructions.unlink()
        print(f"  {instructions}  ->  deleted (was empty after removal)")


_ANTIGRAVITY_RULES_PATH = Path(".agents") / "rules" / "graphify.md"
_ANTIGRAVITY_WORKFLOW_PATH = Path(".agents") / "workflows" / "graphify.md"
_ANTIGRAVITY_WORKFLOW = """\
---
name: graphify
description: Turn any folder of files into a navigable knowledge graph
---

# Workflow: graphify

Follow the graphify skill to run the full pipeline.

If no path argument is given, use `.` (current directory).
"""


def _kiro_install(project_dir: Path) -> None:
    project_dir = project_dir or Path(".")
    _copy_skill_file("kiro", project=True, project_dir=project_dir)
    steering_dir = project_dir / ".kiro" / "steering"
    steering_dir.mkdir(parents=True, exist_ok=True)
    steering_dst = steering_dir / "graphify.md"
    if steering_dst.exists() and steering_dst.read_text(encoding="utf-8") == _always_on("kiro-steering"):
        print(f"  .kiro/steering/graphify.md  ->  already configured (no change)")
    else:
        action = "updated" if steering_dst.exists() else "written"
        steering_dst.write_text(_always_on("kiro-steering"), encoding="utf-8")
        print(f"  .kiro/steering/graphify.md  ->  always-on steering {action}")

    print()
    print("Kiro will now read the knowledge graph before every conversation.")
    print("Use /graphify to build or update the graph.")


def _kiro_uninstall(project_dir: Path) -> None:
    project_dir = project_dir or Path(".")
    removed = []
    skill_dst = _platform_skill_destination("kiro", project=True, project_dir=project_dir)
    if _remove_skill_file("kiro", project=True, project_dir=project_dir):
        removed.append(str(skill_dst.relative_to(project_dir)))
    steering_dst = project_dir / ".kiro" / "steering" / "graphify.md"
    if steering_dst.exists():
        steering_dst.unlink()
        removed.append(str(steering_dst.relative_to(project_dir)))
    print("Removed: " + (", ".join(removed) if removed else "nothing to remove"))


def _antigravity_finalize(skill_dst: Path, project_dir: Path) -> None:
    if skill_dst.exists():
        content = skill_dst.read_text(encoding="utf-8")
        if not content.startswith("---\n"):
            frontmatter = "---\nname: graphify-manager\ndescription: Rebuild the code graph or perform manual CLI queries when MCP server is offline.\n---\n\n"
            skill_dst.write_text(frontmatter + content, encoding="utf-8")

    rules_path = project_dir / _ANTIGRAVITY_RULES_PATH
    rules_path.parent.mkdir(parents=True, exist_ok=True)
    if rules_path.exists():
        existing = rules_path.read_text(encoding="utf-8")
        if _always_on("antigravity-rules").strip() != existing.strip():
            rules_path.write_text(_always_on("antigravity-rules"), encoding="utf-8")
            print(f"graphify rule updated at {rules_path.resolve()}")
        else:
            print(f"graphify rule already configured at {rules_path.resolve()} (no change)")
    else:
        rules_path.write_text(_always_on("antigravity-rules"), encoding="utf-8")
        print(f"graphify rule written to {rules_path.resolve()}")

    wf_path = project_dir / _ANTIGRAVITY_WORKFLOW_PATH
    wf_path.parent.mkdir(parents=True, exist_ok=True)
    if wf_path.exists():
        existing = wf_path.read_text(encoding="utf-8")
        if _ANTIGRAVITY_WORKFLOW.strip() != existing.strip():
            wf_path.write_text(_ANTIGRAVITY_WORKFLOW, encoding="utf-8")
            print(f"graphify workflow updated at {wf_path.resolve()}")
        else:
            print(f"graphify workflow already configured at {wf_path.resolve()} (no change)")
    else:
        wf_path.write_text(_ANTIGRAVITY_WORKFLOW, encoding="utf-8")
        print(f"graphify workflow written to {wf_path.resolve()}")


def _antigravity_install(project_dir: Path) -> None:
    install(platform="antigravity")
    _antigravity_finalize(_platform_skill_destination("antigravity"), project_dir)
    print()
    print("Antigravity will now check the knowledge graph before answering")
    print("codebase questions. Run /graphify first to build the graph.")


def _antigravity_uninstall(project_dir: Path, *, project: bool = False) -> None:
    rules_path = project_dir / _ANTIGRAVITY_RULES_PATH
    if rules_path.exists():
        rules_path.unlink()
        print(f"graphify rule removed from {rules_path.resolve()}")
    else:
        print("No graphify Antigravity rule found - nothing to do")

    wf_path = project_dir / _ANTIGRAVITY_WORKFLOW_PATH
    if wf_path.exists():
        wf_path.unlink()
        print(f"graphify workflow removed from {wf_path.resolve()}")

    skill_dst = _platform_skill_destination("antigravity", project=project, project_dir=project_dir)
    with _skill_lock(skill_dst.parent):
        if skill_dst.exists():
            skill_dst.unlink()
            print(f"graphify skill removed from {skill_dst}")
        version_file = skill_dst.parent / ".graphify_version"
        if version_file.exists():
            version_file.unlink()
        refs_dir = skill_dst.parent / "references"
        if refs_dir.exists():
            shutil.rmtree(refs_dir)
        for d in (skill_dst.parent, skill_dst.parent.parent, skill_dst.parent.parent.parent):
            try:
                d.rmdir()
            except OSError:
                break


_CURSOR_RULE_PATH = Path(".cursor") / "rules" / "graphify.mdc"
_CURSOR_RULE = """\
---
description: graphify knowledge graph context
alwaysApply: true
---

This project has a graphify knowledge graph at graphify-out/.

**MANDATORY: Before using Read, Grep, Glob, or Bash to explore the codebase, you MUST run graphify first:**
- `graphify query "<question>"` — scoped subgraph for any codebase or architecture question

- `graphify path "<A>" "<B>"` — dependency path between two symbols

- `graphify explain "<concept>"` — all nodes related to a concept


This applies to YOU and to every subagent you spawn. Include this rule explicitly in every subagent prompt that involves code exploration. Do not skip graphify because files are "already known" or because you are executing a plan — the graph surfaces cross-file dependencies and INFERRED edges that grep and Read cannot find.

Only use Read/Grep/Glob directly when:
1. graphify has already oriented you and you need to modify or debug specific lines

2. `graphify-out/graph.json` does not exist yet

- If `graphify-out/wiki/index.md` exists, navigate it instead of reading raw files

- Read `graphify-out/GRAPH_REPORT.md` only for broad architecture review when query/path/explain do not surface enough context

- After modifying code files, run `graphify update .` to keep the graph current (AST-only, no API cost)

"""


def _cursor_install(project_dir: Path) -> None:
    rule_path = (project_dir or Path(".")) / _CURSOR_RULE_PATH
    rule_path.parent.mkdir(parents=True, exist_ok=True)
    if rule_path.exists() and rule_path.read_text(encoding="utf-8") == _CURSOR_RULE:
        print(f"graphify rule at {rule_path} already configured (no change)")
        return
    action = "updated" if rule_path.exists() else "written"
    rule_path.write_text(_CURSOR_RULE, encoding="utf-8")
    print(f"graphify rule {action} at {rule_path.resolve()}")
    print()
    print("Cursor will now always include the knowledge graph context.")
    print("Run /graphify . first to build the graph if you haven't already.")


def _cursor_uninstall(project_dir: Path) -> None:
    rule_path = (project_dir or Path(".")) / _CURSOR_RULE_PATH
    if not rule_path.exists():
        print("No graphify Cursor rule found - nothing to do")
        return
    rule_path.unlink()
    print(f"graphify Cursor rule removed from {rule_path.resolve()}")


_DEVIN_RULES_PATH = Path(".windsurf") / "rules" / "graphify.md"
_DEVIN_RULES = """\
## graphify

This project has a graphify knowledge graph at graphify-out/.

Rules:
- For codebase or architecture questions, when `graphify-out/graph.json` exists, first run `graphify query "<question>"` (or `graphify path "<A>" "<B>"` / `graphify explain "<concept>"`). These return a scoped subgraph, usually much smaller than `GRAPH_REPORT.md` or raw grep output.

- If graphify-out/wiki/index.md exists, navigate it instead of reading raw files

- Read graphify-out/GRAPH_REPORT.md only for broad architecture review or when query/path/explain do not surface enough context

- After modifying code files in this session, run `graphify update .` to keep the graph current (AST-only, no API cost)

"""


def _devin_rules_install(project_dir: Path) -> None:
    rules_path = (project_dir or Path(".")) / _DEVIN_RULES_PATH
    rules_path.parent.mkdir(parents=True, exist_ok=True)
    if rules_path.exists() and rules_path.read_text(encoding="utf-8") == _DEVIN_RULES:
        print(f"  {rules_path}  ->  already configured (no change)")
        return
    action = "updated" if rules_path.exists() else "written"
    rules_path.write_text(_DEVIN_RULES, encoding="utf-8")
    print(f"  rules {action}  ->  {rules_path}")


def _devin_rules_uninstall(project_dir: Path) -> None:
    rules_path = (project_dir or Path(".")) / _DEVIN_RULES_PATH
    if not rules_path.exists():
        return
    rules_path.unlink()
    print(f"  rules removed  ->  {rules_path}")


_KILO_PLUGIN_JS = """\
// graphify Kilo plugin
// Injects a knowledge graph reminder before bash tool calls when the graph exists.
import { existsSync } from "fs";
import { join } from "path";

export const GraphifyPlugin = async ({ directory }) => {
  let reminded = false;

  return {
    "tool.execute.before": async (input, output) => {
      if (reminded) return;
      if (!existsSync(join(directory, "graphify-out", "graph.json"))) return;

      if (input.tool === "bash") {
        output.args.command =
          'echo "[graphify] Knowledge graph available. Read graphify-out/GRAPH_REPORT.md for god nodes and architecture context before searching files." ; ' +
          output.args.command;
        reminded = true;
      }
    },
  };
};
"""
_KILO_PLUGIN_PATH = Path(".kilo") / "plugins" / "graphify.js"
_KILO_CONFIG_JSON_PATH = Path(".kilo") / "kilo.json"
_KILO_CONFIG_JSONC_PATH = Path(".kilo") / "kilo.jsonc"


def _strip_json_comments(raw: str) -> str:
    result: list[str] = []
    in_string = False
    escaped = False
    line_comment = False
    block_comment = False
    i = 0
    n = len(raw)

    while i < n:
        ch = raw[i]
        nxt = raw[i + 1] if i + 1 < n else ""
        if line_comment:
            if ch == "\n":
                line_comment = False
                result.append(ch)
            i += 1
            continue
        if block_comment:
            if ch == "*" and nxt == "/":
                block_comment = False
                i += 2
            else:
                i += 1
            continue
        if in_string:
            result.append(ch)
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            i += 1
            continue
        if ch == "/" and nxt == "/":
            line_comment = True
            i += 2
            continue
        if ch == "/" and nxt == "*":
            block_comment = True
            i += 2
            continue
        result.append(ch)
        if ch == '"':
            in_string = True
        i += 1

    no_comments = "".join(result)
    parts: list[str] = []
    last_end = 0
    for match in re.finditer(r'"(?:\\.|[^"\\])*"', no_comments, re.DOTALL):
        non_string = no_comments[last_end : match.start()]
        parts.append(re.sub(r",(\s*[}\]])", r"\1", non_string))
        parts.append(match.group(0))
        last_end = match.end()

    non_string = no_comments[last_end:]
    parts.append(re.sub(r",(\s*[}\]])", r"\1", non_string))
    return "".join(parts)


def _load_json_like(config_file: Path) -> dict:
    if not config_file.exists():
        return {}
    try:
        raw = config_file.read_text(encoding="utf-8")
        if config_file.suffix == ".jsonc":
            raw = _strip_json_comments(raw)
        loaded = json.loads(raw)
    except (OSError, json.JSONDecodeError):
        return {}
    return loaded if isinstance(loaded, dict) else {}


def _kilo_config_path(project_dir: Path) -> Path:
    kilo_dir = (project_dir or Path(".")) / ".kilo"
    json_path = kilo_dir / _KILO_CONFIG_JSON_PATH.name
    if json_path.exists():
        return json_path
    jsonc_path = kilo_dir / _KILO_CONFIG_JSONC_PATH.name
    if jsonc_path.exists():
        return jsonc_path
    return json_path


def _kilo_config_write_path(project_dir: Path) -> Path:
    kilo_dir = (project_dir or Path(".")) / ".kilo"
    return kilo_dir / _KILO_CONFIG_JSON_PATH.name


def _install_kilo_plugin(project_dir: Path) -> None:
    plugin_file = project_dir / _KILO_PLUGIN_PATH
    plugin_file.parent.mkdir(parents=True, exist_ok=True)
    plugin_file.write_text(_KILO_PLUGIN_JS, encoding="utf-8")
    print(f"  {_KILO_PLUGIN_PATH}  ->  tool.execute.before hook written")

    config_file = _kilo_config_path(project_dir)
    write_config_file = _kilo_config_write_path(project_dir)
    write_config_file.parent.mkdir(parents=True, exist_ok=True)
    config = _load_json_like(config_file)
    plugins = config.get("plugin")
    if not isinstance(plugins, list):
        plugins = []
        config["plugin"] = plugins
    entry = plugin_file.resolve().as_uri()
    if entry not in plugins:
        plugins.append(entry)
        write_config_file.write_text(json.dumps(config, indent=2), encoding="utf-8")
        print(f"  {write_config_file.relative_to(project_dir)}  ->  plugin registered")
    else:
        print(f"  {config_file.relative_to(project_dir)}  ->  plugin already registered (no change)")


def _uninstall_kilo_plugin(project_dir: Path) -> None:
    plugin_file = project_dir / _KILO_PLUGIN_PATH
    if plugin_file.exists():
        plugin_file.unlink()
        print(f"  {_KILO_PLUGIN_PATH}  ->  removed")

    config_file = _kilo_config_path(project_dir)
    if not config_file.exists():
        return
    write_config_file = _kilo_config_write_path(project_dir)
    config = _load_json_like(config_file)
    plugins = config.get("plugin", [])
    if not isinstance(plugins, list):
        plugins = []
    entry = plugin_file.resolve().as_uri()
    if entry in plugins:
        config["plugin"] = [plugin for plugin in plugins if plugin != entry]
        if not config["plugin"]:
            config.pop("plugin")
        write_config_file.parent.mkdir(parents=True, exist_ok=True)
        write_config_file.write_text(json.dumps(config, indent=2), encoding="utf-8")
        print(f"  {write_config_file.relative_to(project_dir)}  ->  plugin deregistered")


_OPENCODE_PLUGIN_JS = """\
// graphify OpenCode plugin
// Injects a knowledge graph reminder before the first shell command of a
// session when the graph exists.
//
// One file for both runtimes. OpenCode 2 reads `id` and `setup()` from the
// default export; OpenCode 1 (1.3.4 and later) reads `server()` from it. Each
// ignores the other's function. Nothing is imported from an opencode package:
// a plain file in .opencode/plugins/ cannot resolve one.
//
// IMPORTANT: keep the reminder string free of backticks and $(...) constructs.
// The hook prepends `echo "<reminder>" ; <cmd>` to the user's shell command;
// backticks inside the double-quoted echo trigger command substitution,
// which both corrupts tool output and silently executes the very graphify
// command we are only suggesting. Plain words render fine in opencode's TUI.
import { existsSync } from "fs";
import { join } from "path";

// ';' not '&&' — Windows PowerShell 5.1 rejects '&&' as a statement
// separator, breaking the first shell command of the session (#1646).
const REMINDER =
  'echo "[graphify] knowledge graph at graphify-out/. For focused questions, run graphify query with your question (scoped subgraph, usually much smaller than GRAPH_REPORT.md) instead of grepping raw files. Read GRAPH_REPORT.md only for broad architecture context." ; ';

const hasGraph = (directory) => existsSync(join(directory, "graphify-out", "graph.json"));

// A project and a directory above it (often ~) can each hold a copy of this
// file, and OpenCode loads both. OpenCode 2 fails the second plugin with the
// same id ("Duplicate plugin ID"), so the id carries this file's location. The
// copies share one record of who was reminded, so a command gets one reminder.
const location = [...import.meta.url].reduce((hash, ch) => (Math.imul(hash, 31) + ch.charCodeAt(0)) >>> 0, 7);
const reminded = (globalThis.__graphifyReminded ??= new Set());

export default {
  id: `graphify-${location.toString(16)}`,

  // OpenCode 2: the command tool is "shell", and one server outlives many
  // sessions, so the reminder is tracked per session.
  async setup(ctx) {
    await ctx.tool.hook("execute.before", (event) => {
      if (event.tool !== "shell" || typeof event.input?.command !== "string") return;
      if (reminded.has(event.sessionID)) return;
      if (!hasGraph(ctx.location.directory)) return;

      event.input = { ...event.input, command: REMINDER + event.input.command };
      reminded.add(event.sessionID);
    });
  },

  // OpenCode 1: the command tool is "bash", and the server lives as long as
  // the session, so the reminder is tracked per project directory.
  async server({ directory }) {
    return {
      "tool.execute.before": async (input, output) => {
        if (input.tool !== "bash" || typeof output.args?.command !== "string") return;
        if (reminded.has(directory)) return;
        if (!hasGraph(directory)) return;

        output.args.command = REMINDER + output.args.command;
        reminded.add(directory);
      },
    };
  },
};
"""
_OPENCODE_PLUGIN_PATH = Path(".opencode") / "plugins" / "graphify.js"
_OPENCODE_CONFIG_PATH = Path(".opencode") / "opencode.json"
_OPENCODE_PLUGIN_HEADER = "// graphify OpenCode plugin"


def _opencode_plugin_is_v1_only(body: str) -> bool:
    return body.startswith(_OPENCODE_PLUGIN_HEADER) and "export default" not in body


def _opencode_config_names_plugin(project_dir: Path) -> bool:
    try:
        raw = (project_dir / _OPENCODE_CONFIG_PATH).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return False
    return f'"{_OPENCODE_PLUGIN_PATH.as_posix()}"' in raw


def _drop_opencode_config_entry(project_dir: Path) -> bool:
    config_file = project_dir / _OPENCODE_CONFIG_PATH
    entry = _OPENCODE_PLUGIN_PATH.as_posix()
    try:
        raw = config_file.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return False
    try:
        config = json.loads(raw)
    except ValueError:
        if f'"{entry}"' in raw:
            print(
                f"  {_OPENCODE_CONFIG_PATH}  ->  not plain JSON, left as is; "
                f'remove "{entry}" from its plugin list by hand'
            )
        return False
    if not isinstance(config, dict):
        return False
    changed = False
    for key in ("plugin", "plugins"):
        plugins = config.get(key)
        if isinstance(plugins, list) and entry in plugins:
            config[key] = [p for p in plugins if p != entry]
            if not config[key]:
                config.pop(key)
            changed = True
    if changed:
        _write_text_atomic(config_file, json.dumps(config, indent=2, ensure_ascii=False))
    return changed


def _install_opencode_plugin(project_dir: Path) -> None:
    plugin_file = project_dir / _OPENCODE_PLUGIN_PATH
    _write_text_atomic(plugin_file, _OPENCODE_PLUGIN_JS)
    print(f"  {_OPENCODE_PLUGIN_PATH}  ->  tool.execute.before hook written")

    if _drop_opencode_config_entry(project_dir):
        print(f"  {_OPENCODE_CONFIG_PATH}  ->  stale plugin entry removed")


def _uninstall_opencode_plugin(project_dir: Path) -> None:
    plugin_file = project_dir / _OPENCODE_PLUGIN_PATH
    if plugin_file.exists():
        plugin_file.unlink()
        print(f"  {_OPENCODE_PLUGIN_PATH}  ->  removed")

    if _drop_opencode_config_entry(project_dir):
        print(f"  {_OPENCODE_CONFIG_PATH}  ->  plugin deregistered")


# Xiaomi MiMo Code chat.message + tool.execute.before plugin
_MIMO_PLUGIN_JS = """\
// graphify Xiaomi MiMo Code plugin
import { existsSync } from "fs";
import { join, resolve, isAbsolute, sep } from "path";
import { spawn } from "child_process";

export const GraphifyPlugin = async (ctx = {}) => {
  const workspaceRoot = ctx?.directory || process.cwd();
  const graphPath = join(workspaceRoot, "graphify-out", "graph.json");
  const seenMessageIds = new Set();
  let lastQueriedPrompt = "";
  let isQuerying = false;
  let toolReminded = false;

  const resolveGraphifyBin = () => {
    const isWindows = process.platform === "win32";
    const normWorkspace = resolve(workspaceRoot).toLowerCase();

    if (process.env.GRAPHIFY_EXE && process.env.GRAPHIFY_EXE.trim()) {
      const custom = resolve(process.env.GRAPHIFY_EXE.trim());
      const customNorm = custom.toLowerCase();
      if (isAbsolute(custom) && customNorm !== normWorkspace && !customNorm.startsWith(normWorkspace + sep)) {
        try {
          if (existsSync(custom)) return custom;
        } catch {}
      }
      return null;
    }

    const pathSep = isWindows ? ";" : ":";
    const pathStr = process.env.PATH || process.env.Path || "";
    const dirs = pathStr.split(pathSep).filter((d) => d && d.trim());
    const extensions = isWindows
      ? (process.env.PATHEXT || ".EXE;.CMD;.BAT;.COM").split(";").filter(Boolean)
      : [""];

    for (const rawDir of dirs) {
      const trimmedDir = rawDir.trim();
      if (!isAbsolute(trimmedDir)) continue;

      const resolvedDir = resolve(trimmedDir);
      const resolvedNorm = resolvedDir.toLowerCase();
      if (resolvedNorm === normWorkspace || resolvedNorm.startsWith(normWorkspace + sep)) {
        continue;
      }

      for (const ext of extensions) {
        const candidate = join(resolvedDir, isWindows ? `graphify${ext.toLowerCase()}` : "graphify");
        const candidateUpper = isWindows ? join(resolvedDir, `graphify${ext.toUpperCase()}`) : candidate;
        try {
          if (existsSync(candidate)) return candidate;
          if (isWindows && existsSync(candidateUpper)) return candidateUpper;
        } catch {}
      }
    }
    return null;
  };

  const runGraphifyQuery = (question) => {
    return new Promise((res) => {
      if (!existsSync(graphPath) || !question || isQuerying) return res(null);
      isQuerying = true;
      try {
        const trimmedQuestion = question.trim().slice(0, 500);
        if (!trimmedQuestion) {
          isQuerying = false;
          return res(null);
        }

        const bin = resolveGraphifyBin();
        if (!bin || !isAbsolute(bin)) {
          isQuerying = false;
          return res(null);
        }

        try {
          if (!existsSync(bin)) {
            isQuerying = false;
            return res(null);
          }
        } catch {
          isQuerying = false;
          return res(null);
        }

        const args = ["query", trimmedQuestion, "--graph", graphPath, "--budget", "1500"];
        let stdout = "";
        let timer = null;
        let killed = false;

        const child = spawn(bin, args, {
          cwd: workspaceRoot,
          shell: false,
          windowsHide: true,
        });

        timer = setTimeout(() => {
          killed = true;
          try { child.kill("SIGKILL"); } catch {}
          isQuerying = false;
          res(null);
        }, 4000);

        child.stdout?.on("data", (chunk) => {
          stdout += chunk.toString("utf-8");
          if (stdout.length > 16000) {
            try { child.kill(); } catch {}
          }
        });

        child.on("error", () => {
          if (timer) clearTimeout(timer);
          isQuerying = false;
          res(null);
        });

        child.on("close", (code) => {
          if (timer) clearTimeout(timer);
          isQuerying = false;
          if (!killed && code === 0 && stdout && stdout.trim()) {
            const text = stdout.trim();
            return res(text.length > 8000 ? text.slice(0, 8000) + "\\n...[truncated]" : text);
          }
          res(null);
        });
      } catch {
        isQuerying = false;
        res(null);
      }
    });
  };

  return {
    "chat.message": async (input, output) => {
      if (!existsSync(graphPath)) return;
      const msgId = input?.message?.id || input?.messageID;
      if (msgId && seenMessageIds.has(msgId)) return;
      const parts = output?.parts;
      if (!Array.isArray(parts)) return;

      const textParts = parts.filter((p) => p && p.type === "text" && typeof p.text === "string");
      const userText = textParts.map((p) => p.text).join("\\n").trim();
      if (!userText || userText === lastQueriedPrompt) return;

      if (msgId) seenMessageIds.add(msgId);
      lastQueriedPrompt = userText;

      const graphContext = await runGraphifyQuery(userText);
      if (graphContext) {
        const injected = `\\n\\n<!-- Graphify Knowledge Graph Context -->\\n${graphContext}\\n<!-- End Graphify Context -->`;
        if (textParts.length > 0) {
          textParts[textParts.length - 1].text += injected;
        } else {
          parts.push({ type: "text", text: injected });
        }
      }
    },
    "tool.execute.before": async (input, output) => {
      if (toolReminded || !existsSync(graphPath)) return;
      if (input && input.tool === "bash" && output && output.args && typeof output.args.command === "string") {
        output.args.command =
          'echo "[graphify] Knowledge graph active at graphify-out/. Use \\'graphify query\\' for targeted questions." ; ' +
          output.args.command;
        toolReminded = true;
      }
    },
  };
};

export default GraphifyPlugin;
"""


def _tokenize_jsonc(raw: str) -> list[tuple[str, int, int, str]]:
    tokens = []
    i = 0
    n = len(raw)
    while i < n:
        ch = raw[i]
        nxt = raw[i + 1] if i + 1 < n else ""
        if ch == "/" and nxt == "/":
            start = i
            i += 2
            while i < n and raw[i] != "\n":
                i += 1
            tokens.append(("LINE_COMMENT", start, i, raw[start:i]))
        elif ch == "/" and nxt == "*":
            start = i
            i += 2
            while i + 1 < n and not (raw[i] == "*" and raw[i + 1] == "/"):
                i += 1
            i = i + 2 if i + 1 < n else n
            tokens.append(("BLOCK_COMMENT", start, i, raw[start:i]))
        elif ch == '"':
            start = i
            i += 1
            escaped = False
            while i < n:
                c = raw[i]
                if escaped:
                    escaped = False
                elif c == "\\":
                    escaped = True
                elif c == '"':
                    i += 1
                    break
                i += 1
            tokens.append(("STRING", start, i, raw[start:i]))
        elif ch in "{}[],:":
            tokens.append(("PUNCT", i, i + 1, ch))
            i += 1
        elif ch.isspace():
            start = i
            while i < n and raw[i].isspace():
                i += 1
            tokens.append(("WHITESPACE", start, i, raw[start:i]))
        else:
            start = i
            while i < n and not (raw[i].isspace() or raw[i] in '{}[],:"' or (raw[i] == "/" and i + 1 < n and raw[i + 1] in "/*")):
                i += 1
            tokens.append(("OTHER", start, i, raw[start:i]))
    return tokens


def _is_mimo_plugin_entry(candidate: object, possible_entries: set[str] | None = None) -> bool:
    if not isinstance(candidate, str) or not possible_entries:
        return False
    if candidate in possible_entries:
        return True
    if sys.platform == "win32":
        cand_norm = candidate.replace("/", "\\").lower()
        for p in possible_entries:
            if p.replace("/", "\\").lower() == cand_norm or candidate.lower() == p.lower():
                return True
    return False


def _verify_mimo_plugins_val(data: dict, config_path: Path | None = None) -> None:
    for key in ("plugin", "plugins"):
        val = data.get(key)
        if val is not None and not isinstance(val, (str, list)):
            target = config_path or Path("mimocode.json")
            print(
                f"[graphify] refusing to modify {target}: '{key}' must be a string or array (found {type(val).__name__})",
                file=sys.stderr,
            )
            sys.exit(1)


def _preserve_jsonc_plugin_add(raw: str, entry: str) -> str:
    try:
        stripped = _strip_json_comments(raw)
        data = json.loads(stripped)
    except Exception as exc:
        raise ValueError(f"Invalid JSON/JSONC: {exc}") from exc

    if not isinstance(data, dict):
        raise ValueError("JSONC root must be an object")

    _verify_mimo_plugins_val(data)
    existing_plugins = data.get("plugin")
    if isinstance(existing_plugins, list) and entry in existing_plugins:
        return raw
    if isinstance(existing_plugins, str) and existing_plugins == entry:
        return raw

    tokens = _tokenize_jsonc(raw)
    root_open_idx = next((i for i, t in enumerate(tokens) if t[0] == "PUNCT" and t[3] == "{"), None)
    root_close_idx = next((i for i in range(len(tokens) - 1, -1, -1) if tokens[i][0] == "PUNCT" and tokens[i][3] == "}"), None)
    if root_open_idx is None or root_close_idx is None:
        raise ValueError("Could not find root object braces in JSONC")

    plugin_key_tok_idx = None
    depth = 0
    for idx in range(root_open_idx + 1, root_close_idx):
        tok = tokens[idx]
        if tok[0] == "PUNCT":
            if tok[3] in "{[":
                depth += 1
            elif tok[3] in "}]":
                depth -= 1
        elif depth == 0 and tok[0] == "STRING" and tok[3] == '"plugin"':
            plugin_key_tok_idx = idx
            break

    entry_str = json.dumps(entry)

    if plugin_key_tok_idx is not None:
        colon_idx = next(i for i in range(plugin_key_tok_idx + 1, root_close_idx) if tokens[i][0] == "PUNCT" and tokens[i][3] == ":")
        val_start_idx = next(i for i in range(colon_idx + 1, root_close_idx) if tokens[i][0] not in ("WHITESPACE", "LINE_COMMENT", "BLOCK_COMMENT"))
        val_tok = tokens[val_start_idx]

        if val_tok[0] == "PUNCT" and val_tok[3] == "[":
            arr_open_idx = val_start_idx
            arr_depth = 0
            arr_close_idx = None
            for j in range(arr_open_idx, len(tokens)):
                if tokens[j][0] == "PUNCT":
                    if tokens[j][3] == "[":
                        arr_depth += 1
                    elif tokens[j][3] == "]":
                        arr_depth -= 1
                        if arr_depth == 0:
                            arr_close_idx = j
                            break
            if arr_close_idx is None:
                raise ValueError("Unmatched array bracket")

            inner_items = [t for t in tokens[arr_open_idx + 1 : arr_close_idx] if t[0] in ("STRING", "OTHER") or (t[0] == "PUNCT" and t[3] in "{[")]
            if not inner_items:
                close_pos = tokens[arr_close_idx][1]
                return raw[:close_pos] + f"\n    {entry_str}\n  " + raw[close_pos:]

            last_item = inner_items[-1]
            last_item_end = last_item[2]
            comma_exists = any(tokens[k][0] == "PUNCT" and tokens[k][3] == "," for k in range(tokens.index(last_item) + 1, arr_close_idx))

            raw_mid = raw[:last_item_end] + "," + raw[last_item_end:] if not comma_exists else raw
            arr_close_pos = tokens[arr_close_idx][1] + (1 if not comma_exists else 0)
            pre = raw_mid[:arr_close_pos]
            post = raw_mid[arr_close_pos:]
            ws_match = re.search(r"(\n[ \t]*)$", pre)
            if ws_match:
                return pre[:ws_match.start(1)] + f"\n    {entry_str}" + pre[ws_match.start(1):] + post
            return pre + f"\n    {entry_str}\n  " + post

        if val_tok[0] == "STRING":
            replacement = f"[\n    {val_tok[3]},\n    {entry_str}\n  ]"
            return raw[:val_tok[1]] + replacement + raw[val_tok[2]:]
        raise ValueError("'plugin' value is neither string nor array")

    bracket_close_pos = tokens[root_close_idx][1]
    indent = "  "
    plugin_block = f'{indent}"plugin": [\n{indent}  {entry_str}\n{indent}]'

    if len(data) > 0:
        last_prop_tok = next(tokens[j] for j in range(root_close_idx - 1, root_open_idx, -1) if tokens[j][0] not in ("WHITESPACE", "LINE_COMMENT", "BLOCK_COMMENT"))
        comma_needed = not (last_prop_tok[0] == "PUNCT" and last_prop_tok[3] == ",")

        if comma_needed:
            insertion_point = last_prop_tok[2]
            raw_comma = raw[:insertion_point] + "," + raw[insertion_point:]
            bracket_close_pos += 1
        else:
            raw_comma = raw

        pre = raw_comma[:bracket_close_pos]
        post = raw_comma[bracket_close_pos:]
        ws_match = re.search(r"(\n[ \t]*)$", pre)
        if ws_match:
            return pre[:ws_match.start(1)] + f"\n{plugin_block}" + pre[ws_match.start(1):] + post
        return pre + f"\n{plugin_block}\n" + post

    return raw[:bracket_close_pos] + f"\n{plugin_block}\n" + raw[bracket_close_pos:]


def _preserve_jsonc_plugin_remove(raw: str, possible_entries: set[str] | None = None) -> str:
    try:
        data = json.loads(_strip_json_comments(raw))
    except Exception:
        return raw

    if not isinstance(data, dict) or "plugin" not in data:
        return raw

    tokens = _tokenize_jsonc(raw)
    plugin_key_idx = next((i for i, t in enumerate(tokens) if t[0] == "STRING" and t[3] == '"plugin"'), None)
    if plugin_key_idx is None:
        return raw

    colon_idx = next((i for i in range(plugin_key_idx + 1, len(tokens)) if tokens[i][0] == "PUNCT" and tokens[i][3] == ":"), None)
    if colon_idx is None:
        return raw

    val_idx = next((i for i in range(colon_idx + 1, len(tokens)) if tokens[i][0] not in ("WHITESPACE", "LINE_COMMENT", "BLOCK_COMMENT")), None)
    if val_idx is None:
        return raw

    val_tok = tokens[val_idx]
    if val_tok[0] == "STRING":
        if _is_mimo_plugin_entry(json.loads(val_tok[3]), possible_entries):
            start_pos = tokens[plugin_key_idx][1]
            next_comma = next((i for i in range(val_idx + 1, len(tokens)) if tokens[i][0] == "PUNCT" and tokens[i][3] == ","), None)
            end_pos = tokens[next_comma][2] if next_comma else val_tok[2]
            return (raw[:start_pos] + raw[end_pos:]).strip() + "\n"

    elif val_tok[0] == "PUNCT" and val_tok[3] == "[":
        for idx in range(val_idx + 1, len(tokens)):
            if tokens[idx][0] == "STRING" and _is_mimo_plugin_entry(json.loads(tokens[idx][3]), possible_entries):
                match_tok = tokens[idx]
                next_c = next((k for k in range(idx + 1, len(tokens)) if tokens[k][0] == "PUNCT" and tokens[k][3] == ","), None)
                if next_c:
                    return raw[:match_tok[1]] + raw[tokens[next_c][2]:]
                prev_c = next((k for k in range(idx - 1, val_idx, -1) if tokens[k][0] == "PUNCT" and tokens[k][3] == ","), None)
                if prev_c:
                    return raw[:tokens[prev_c][1]] + raw[match_tok[2]:]
                return raw[:match_tok[1]] + raw[match_tok[2]:]
    return raw


def _prepare_mimo_config(project_dir: Path, *, project: bool = False) -> tuple[Path, str, bool]:
    mimo_dir = (project_dir / ".mimocode") if project else _mimo_global_config_dir()
    jsonc_file = mimo_dir / "mimocode.jsonc"
    json_file = mimo_dir / "mimocode.json"
    config_file = jsonc_file if jsonc_file.exists() else json_file
    plugin_file = mimo_dir / "plugins" / "graphify.js"
    entry = "./plugins/graphify.js" if project else plugin_file.resolve().as_uri()

    if not config_file.exists():
        return config_file, json.dumps({"plugin": [entry]}, indent=2) + "\n", False

    raw = config_file.read_text(encoding="utf-8-sig")
    is_jsonc = (config_file.suffix == ".jsonc") or ("//" in raw) or ("/*" in raw)

    try:
        data = json.loads(_strip_json_comments(raw) if is_jsonc else raw)
    except Exception:
        _refuse_to_modify(config_file)
    if not isinstance(data, dict):
        _refuse_to_modify(config_file)

    _verify_mimo_plugins_val(data, config_file)

    existing = data.get("plugin")
    if (isinstance(existing, list) and entry in existing) or (isinstance(existing, str) and existing == entry):
        return config_file, raw, True

    if is_jsonc:
        new_content = _preserve_jsonc_plugin_add(raw, entry)
        return config_file, new_content, False

    if isinstance(existing, list):
        existing.append(entry)
    elif isinstance(existing, str):
        data["plugin"] = [existing, entry]
    else:
        data["plugin"] = [entry]

    return config_file, json.dumps(data, indent=2) + "\n", False


def _install_mimo_plugin_files(
    project_dir: Path,
    config_file: Path,
    config_content: str,
    already_registered: bool,
    *,
    project: bool = False,
) -> None:
    plugin_file = ((project_dir / ".mimocode") if project else _mimo_global_config_dir()) / "plugins" / "graphify.js"
    plugin_file.parent.mkdir(parents=True, exist_ok=True)
    _write_text_atomic(plugin_file, _MIMO_PLUGIN_JS)
    shown_plugin = plugin_file.relative_to(project_dir) if project else plugin_file
    print(f"  {shown_plugin}  ->  chat.message + tool.execute.before hook written")

    shown_config = config_file.relative_to(project_dir) if project else config_file
    if not already_registered:
        config_file.parent.mkdir(parents=True, exist_ok=True)
        if config_file.exists():
            backup = config_file.with_name(config_file.name + ".graphify-bak")
            shutil.copy2(config_file, backup)
        _write_text_atomic(config_file, config_content)
        print(f"  {shown_config}  ->  plugin registered")
    else:
        print(f"  {shown_config}  ->  plugin already registered (no change)")


def _install_mimo_plugin(project_dir: Path, *, project: bool = False) -> None:
    config_file, config_content, already_registered = _prepare_mimo_config(project_dir, project=project)
    _install_mimo_plugin_files(project_dir, config_file, config_content, already_registered, project=project)


def _prepare_mimo_uninstall(project_dir: Path, *, project: bool = False) -> tuple[Path, list[tuple[Path, str]]]:
    mimo_dir = (project_dir / ".mimocode") if project else _mimo_global_config_dir()
    plugin_file = mimo_dir / "plugins" / "graphify.js"
    possible = {plugin_file.resolve().as_uri(), "./plugins/graphify.js", str(plugin_file)}
    planned: list[tuple[Path, str]] = []

    for cfg in (mimo_dir / "mimocode.json", mimo_dir / "mimocode.jsonc"):
        if not cfg.exists():
            continue
        try:
            raw = cfg.read_text(encoding="utf-8-sig")
            updated = _preserve_jsonc_plugin_remove(raw, possible)
            if updated != raw:
                planned.append((cfg, updated))
        except Exception:
            pass
    return plugin_file, planned


def _uninstall_mimo_plugin(project_dir: Path, *, project: bool = False) -> None:
    plugin_file, planned_writes = _prepare_mimo_uninstall(project_dir, project=project)
    shown_plugin = plugin_file.relative_to(project_dir) if project else plugin_file
    if plugin_file.exists():
        plugin_file.unlink()
        print(f"  {shown_plugin}  ->  removed")
        try:
            plugin_file.parent.rmdir()
        except OSError:
            pass

    for config_file, new_content in planned_writes:
        shown_config = config_file.relative_to(project_dir) if project else config_file
        _write_text_atomic(config_file, new_content)
        print(f"  {shown_config}  ->  plugin deregistered")


def _write_mimo_agents_instruction(target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    existed = target.exists()
    content, newline = _read_keep_newline(target) if existed else ("", "\n")
    new_content = _replace_or_append_section(content, _AGENTS_MD_MARKER, _always_on("agents-md"))
    if not (existed and new_content == content):
        _write_keep_newline(target, new_content, newline)
        print(f"  {target.resolve()}  ->  instructions written")


def _mimo_install(project_dir: Path, *, project: bool = False) -> None:
    project_dir = project_dir or Path(".")
    config_file, config_content, already_registered = _prepare_mimo_config(project_dir, project=project)
    platform_name = "mimo-windows" if sys.platform == "win32" else "mimo"

    skill_dst = _copy_skill_file(platform_name, project=project, project_dir=project_dir)
    _install_mimo_plugin_files(project_dir, config_file, config_content, already_registered, project=project)

    agents_file = (project_dir / "AGENTS.md") if project else (_mimo_global_config_dir() / "AGENTS.md")
    _write_mimo_agents_instruction(agents_file)

    if project:
        _print_project_git_add_hint([_project_scope_root(skill_dst, project_dir), project_dir / ".mimocode", project_dir / "AGENTS.md"])

    print()
    print("Xiaomi MiMo Code will now automatically check the knowledge graph before")
    print("answering codebase questions. Run /graphify first to build the graph.")


def _mimo_uninstall(project_dir: Path, *, project: bool = False) -> None:
    project_dir = project_dir or Path(".")
    platform_name = "mimo-windows" if sys.platform == "win32" else "mimo"
    _uninstall_mimo_plugin(project_dir, project=project)
    _remove_skill_file(platform_name, project=project, project_dir=project_dir)

    target = (project_dir / "AGENTS.md") if project else (_mimo_global_config_dir() / "AGENTS.md")
    if target.exists():
        content, newline = _read_keep_newline(target)
        cleaned = _remove_marker_section(content, _AGENTS_MD_MARKER)
        if cleaned is not None:
            if cleaned:
                _write_keep_newline(target, cleaned + "\n", newline)
            else:
                target.unlink()


def _read_graph_stats(graph_file: Path) -> str:
    if not graph_file.exists():
        return f"No graph at {graph_file}."
    try:
        raw = json.loads(graph_file.read_text(encoding="utf-8"))
        n = len(raw.get("nodes", []))
        e = len(raw.get("links", raw.get("edges", [])))
        return f"Active graph with {n} nodes, {e} edges"
    except Exception:
        return "Graph exists (unparsed)"


def _mimo_status(project_dir: Path, *, project: bool = False) -> None:
    project_dir = project_dir or Path(".")
    mimo_dir = (project_dir / ".mimocode") if project else _mimo_global_config_dir()
    platform_name = "mimo-windows" if sys.platform == "win32" else "mimo"
    skill = _platform_skill_destination(platform_name, project=project, project_dir=project_dir)

    print(f"Xiaomi MiMo Code Status ({'Project' if project else 'Global'}):\n")
    print(f"  Skill:        {'Installed' if skill.exists() else 'Not installed'} ({skill})")

    plugin = mimo_dir / "plugins" / "graphify.js"
    print(f"  Plugin:       {'Installed' if plugin.exists() else 'Not installed'}")

    agents = (project_dir / "AGENTS.md") if project else (_mimo_global_config_dir() / "AGENTS.md")
    has_agents = agents.exists() and _AGENTS_MD_MARKER in agents.read_text(encoding="utf-8")
    print(f"  Instructions: {'Configured' if has_agents else 'Missing'}")
    print(f"  Knowledge:    {_read_graph_stats(project_dir / 'graphify-out' / 'graph.json')}")


def _resolve_graphify_exe(project: bool = False) -> str:
    if project:
        return "graphify"
    found = shutil.which("graphify")
    if not found:
        scripts_dir = Path(sys.executable).parent
        for name in ("graphify.exe", "graphify"):
            candidate = scripts_dir / name
            if candidate.exists():
                found = str(candidate)
                break
    return (found or "graphify").replace("\\", "/")


def _install_codex_hook(project_dir: Path, project: bool = False) -> None:
    hooks_path = project_dir / ".codex" / "hooks.json"
    hooks_path.parent.mkdir(parents=True, exist_ok=True)
    existing = _read_settings_for_merge(hooks_path)
    graphify_exe = _resolve_graphify_exe(project=project)
    if " " in graphify_exe and not graphify_exe.startswith('"'):
        graphify_exe = f'"{graphify_exe}"'
    hook_entry = {
        "hooks": {
            "PreToolUse": [
                {
                    "matcher": "Bash",
                    "hooks": [{"type": "command", "command": f"{graphify_exe} hook-check"}],
                }
            ]
        }
    }
    hooks = existing.setdefault("hooks", {})
    if not isinstance(hooks, dict):
        _refuse_to_modify(hooks_path)
    pre_tool = hooks.setdefault("PreToolUse", [])
    if not isinstance(pre_tool, list):
        _refuse_to_modify(hooks_path)
    hooks["PreToolUse"] = _strip_graphify_hooks(pre_tool)
    hooks["PreToolUse"].extend(hook_entry["hooks"]["PreToolUse"])
    _write_settings_with_backup(hooks_path, existing)
    print(
        f"  .codex/hooks.json  ->  PreToolUse hook registered ({graphify_exe} hook-check"
        " - intentional no-op; Codex Desktop rejects additionalContext on PreToolUse,"
        " so graph guidance comes from AGENTS.md)"
    )


def _uninstall_codex_hook(project_dir: Path) -> None:
    hooks_path = project_dir / ".codex" / "hooks.json"
    if not hooks_path.exists():
        return
    try:
        existing = json.loads(hooks_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return
    pre_tool = existing.get("hooks", {}).get("PreToolUse", [])
    if not isinstance(pre_tool, list):
        return
    filtered = _strip_graphify_hooks(pre_tool)
    if filtered == pre_tool:
        return
    existing["hooks"]["PreToolUse"] = filtered
    _write_settings_with_backup(hooks_path, existing)
    print(f"  .codex/hooks.json  ->  PreToolUse hook removed")


def _agents_install(project_dir: Path, platform: str, project: bool = False) -> None:
    target = (project_dir or Path(".")) / "AGENTS.md"
    if target.exists():
        content, newline = _read_keep_newline(target)
        new_content = _replace_or_append_section(
            content, _AGENTS_MD_MARKER, _always_on("agents-md")
        )
    else:
        content, newline = "", "\n"
        new_content = _always_on("agents-md")

    if target.exists() and new_content == content:
        print(f"graphify already configured in {target.resolve()} (no change)")
    else:
        _write_keep_newline(target, new_content, newline)
        print(f"graphify section written to {target.resolve()}")

    if platform == "codex":
        _install_codex_hook(project_dir or Path("."), project=project)
    elif platform == "opencode":
        _install_opencode_plugin(project_dir or Path("."))
    elif platform == "kilo":
        _install_kilo_plugin(project_dir or Path("."))
    elif platform in ("mimo", "mimo-windows"):
        _install_mimo_plugin(project_dir or Path("."), project=project)

    print()
    print(
        f"{platform.capitalize()} will now check the knowledge graph before answering"
    )
    print("codebase questions and rebuild it after code changes.")
    if platform not in ("codex", "opencode", "kilo", "mimo"):
        print()
        print("Note: unlike Claude Code, there is no PreToolUse hook equivalent for")
        print(
            f"{platform.capitalize()} — the AGENTS.md rules are the always-on mechanism."
        )


def _amp_legacy_cleanup() -> None:
    legacy = Path.home() / ".amp" / "skills" / "graphify"
    if legacy.exists():
        shutil.rmtree(legacy, ignore_errors=True)
        if not legacy.exists():
            print(f"  legacy removed   ->  {legacy}")


def _amp_install(project_dir: Path | None = None) -> None:
    _amp_legacy_cleanup()
    _copy_skill_file("amp")
    _agents_install(project_dir or Path("."), "amp")


def _amp_uninstall(project_dir: Path | None = None) -> None:
    removed = _remove_skill_file("amp")
    if removed:
        print("skill removed")
    _agents_uninstall(project_dir or Path("."), platform="amp")


def _agents_platform_install(project_dir: Path | None = None) -> None:
    _copy_skill_file("agents")
    _agents_install(project_dir or Path("."), "agents")


def _agents_platform_uninstall(project_dir: Path | None = None) -> None:
    removed = _remove_skill_file("agents")
    if removed:
        print("skill removed")
    _agents_uninstall(project_dir or Path("."), platform="agents")


def _project_install(platform_name: str, project_dir: Path | None = None, strict: bool = False) -> None:
    project_dir = project_dir or Path(".")
    platform_name = _canonical_platform(platform_name)
    if platform_name in ("claude", "windows"):
        install(platform=platform_name, project=True, project_dir=project_dir)
        claude_install(project_dir, strict=strict, project=True)
        _print_project_git_add_hint([project_dir / ".claude", project_dir / "CLAUDE.md"])
    elif platform_name == "gemini":
        gemini_install(project_dir, project=True)
    elif platform_name == "cursor":
        _cursor_install(project_dir)
        _print_project_git_add_hint([project_dir / ".cursor"])
    elif platform_name == "kiro":
        _kiro_install(project_dir)
        _print_project_git_add_hint([project_dir / ".kiro"])
    elif platform_name in ("aider", "amp", "codex", "opencode", "claw", "droid", "trae", "trae-cn", "hermes"):
        skill_dst = _copy_skill_file(platform_name, project=True, project_dir=project_dir)
        _agents_install(project_dir, platform_name, project=True)
        hint_paths = [_project_scope_root(skill_dst, project_dir), project_dir / "AGENTS.md"]
        if platform_name == "opencode":
            hint_paths.append(project_dir / ".opencode")
        elif platform_name == "codex":
            hint_paths.append(project_dir / ".codex")
        _print_project_git_add_hint(hint_paths)
    elif platform_name == "devin":
        skill_dst = _copy_skill_file("devin", project=True, project_dir=project_dir)
        _devin_rules_install(project_dir)
        _print_project_git_add_hint([_project_scope_root(skill_dst, project_dir), project_dir / ".windsurf"])
    elif platform_name == "antigravity":
        skill_dst = _copy_skill_file("antigravity", project=True, project_dir=project_dir)
        _antigravity_finalize(skill_dst, project_dir)
        _print_project_git_add_hint([_project_scope_root(skill_dst, project_dir), project_dir / ".agents"])
    elif platform_name in ("mimo", "mimo-windows"):
        _mimo_install(project_dir, project=True)
    elif platform_name in ("copilot", "pi", "kimi", "agents"):
        skill_dst = _copy_skill_file(platform_name, project=True, project_dir=project_dir)
        _print_project_git_add_hint([_project_scope_root(skill_dst, project_dir)])
    else:
        install(platform=platform_name, project=True, project_dir=project_dir)


def _project_uninstall(platform_name: str, project_dir: Path | None = None) -> None:
    project_dir = project_dir or Path(".")
    platform_name = _canonical_platform(platform_name)
    if platform_name in ("claude", "windows"):
        _remove_skill_file(platform_name, project=True, project_dir=project_dir)
        _remove_claude_skill_registration(project_dir)
        claude_uninstall(project_dir, project=True)
    elif platform_name == "gemini":
        gemini_uninstall(project_dir, project=True)
    elif platform_name == "cursor":
        _cursor_uninstall(project_dir)
    elif platform_name == "kiro":
        _kiro_uninstall(project_dir)
    elif platform_name in ("aider", "amp", "codex", "opencode", "claw", "droid", "trae", "trae-cn", "hermes"):
        _remove_skill_file(platform_name, project=True, project_dir=project_dir)
        _agents_uninstall(project_dir, platform=platform_name)
        if platform_name == "codex":
            _uninstall_codex_hook(project_dir)
    elif platform_name == "antigravity":
        _antigravity_uninstall(project_dir, project=True)
    elif platform_name in ("mimo", "mimo-windows"):
        _mimo_uninstall(project_dir, project=True)
    elif platform_name == "devin":
        removed = _remove_skill_file("devin", project=True, project_dir=project_dir)
        _devin_rules_uninstall(project_dir)
        if not removed:
            print("nothing to remove")
    elif platform_name in ("copilot", "pi", "kimi", "agents"):
        removed = _remove_skill_file(platform_name, project=True, project_dir=project_dir)
        if not removed:
            print("nothing to remove")
    elif platform_name == "codebuddy":
        codebuddy_uninstall(project_dir, project=True)
    else:
        _remove_skill_file(platform_name, project=True, project_dir=project_dir)


def _project_uninstall_all(project_dir: Path | None = None) -> None:
    project_dir = project_dir or Path(".")
    print("Uninstalling project-scoped graphify files...\n")
    for platform_name in _PLATFORM_CONFIG:
        _project_uninstall(platform_name, project_dir)
    for platform_name in ("gemini", "cursor"):
        _project_uninstall(platform_name, project_dir)
    print("\nDone.")


def _agents_uninstall(project_dir: Path, platform: str = "") -> None:
    target = (project_dir or Path(".")) / "AGENTS.md"

    if not target.exists():
        print("No AGENTS.md found in current directory - nothing to do")
        if platform == "opencode":
            _uninstall_opencode_plugin(project_dir or Path("."))
        elif platform == "kilo":
            _uninstall_kilo_plugin(project_dir or Path("."))
        elif platform in ("mimo", "mimo-windows"):
            _uninstall_mimo_plugin(project_dir or Path("."), project=True)
        return

    content, newline = _read_keep_newline(target)
    cleaned = _remove_marker_section(content, _AGENTS_MD_MARKER)
    if cleaned is None:
        print("graphify section not found in AGENTS.md - nothing to do")
        if platform == "opencode":
            _uninstall_opencode_plugin(project_dir or Path("."))
        elif platform == "kilo":
            _uninstall_kilo_plugin(project_dir or Path("."))
        elif platform in ("mimo", "mimo-windows"):
            _uninstall_mimo_plugin(project_dir or Path("."), project=True)
        return

    if cleaned or target.is_symlink():
        _write_keep_newline(target, cleaned + "\n", newline)
        print(f"graphify section removed from {target.resolve()}")
    else:
        target.unlink()
        print(f"AGENTS.md was empty after removal - deleted {target.resolve()}")

    if platform == "opencode":
        _uninstall_opencode_plugin(project_dir or Path("."))
    elif platform == "kilo":
        _uninstall_kilo_plugin(project_dir or Path("."))
    elif platform in ("mimo", "mimo-windows"):
        _uninstall_mimo_plugin(project_dir or Path("."), project=True)


def _kilo_uninstall_global() -> list[str]:
    removed = []
    command_dst = Path.home() / ".config" / "kilo" / "command" / "graphify.md"
    if command_dst.exists():
        command_dst.unlink()
        removed.append(f"command removed: {command_dst}")
    try:
        command_dst.parent.rmdir()
    except OSError:
        pass

    skill_dst = Path.home() / _PLATFORM_CONFIG["kilo"]["skill_dst"]
    with _skill_lock(skill_dst.parent):
        if skill_dst.exists():
            skill_dst.unlink()
            removed.append(f"skill removed: {skill_dst}")
        version_file = skill_dst.parent / ".graphify_version"
        if version_file.exists():
            version_file.unlink()
        for d in (
            skill_dst.parent,
            skill_dst.parent.parent,
            skill_dst.parent.parent.parent,
        ):
            try:
                d.rmdir()
            except OSError:
                break

    return removed


def _kilo_install(project_dir: Path) -> None:
    install(platform="kilo")
    _agents_install(project_dir or Path("."), "kilo")


def _kilo_uninstall(project_dir: Path) -> None:
    _agents_uninstall(project_dir or Path("."), platform="kilo")
    removed = _kilo_uninstall_global()
    print("; ".join(removed) if removed else "nothing to remove")


def claude_install(project_dir: Path | None = None, strict: bool = False, project: bool = False) -> None:
    target = (project_dir or Path(".")) / "CLAUDE.md"

    if target.exists():
        content, newline = _read_keep_newline(target)
        new_content = _replace_or_append_section(
            content, _CLAUDE_MD_MARKER, _always_on("claude-md")
        )
    else:
        content, newline = "", "\n"
        new_content = _always_on("claude-md")

    if target.exists() and new_content == content:
        print(f"graphify already configured in {target.resolve()} (no change)")
    else:
        _write_keep_newline(target, new_content, newline)
        print(f"graphify section written to {target.resolve()}")

    _install_claude_hook(project_dir or Path("."), strict=strict, project=project)

    print()
    print("Claude Code will now check the knowledge graph before answering")
    print("codebase questions and rebuild it after code changes.")
    if strict:
        print("Strict mode: the first raw file read per session is blocked until")
        print("one `graphify query` runs (toggle with GRAPHIFY_HOOK_STRICT=0).")


def _install_claude_hook(project_dir: Path, strict: bool = False, project: bool = False) -> None:
    settings_path = project_dir / ".claude" / "settings.json"
    settings_path.parent.mkdir(parents=True, exist_ok=True)

    settings = _read_settings_for_merge(settings_path)

    hooks = settings.setdefault("hooks", {})
    if not isinstance(hooks, dict):
        _refuse_to_modify(settings_path)
    pre_tool = hooks.setdefault("PreToolUse", [])
    if not isinstance(pre_tool, list):
        _refuse_to_modify(settings_path)

    hooks["PreToolUse"] = _strip_graphify_hooks(pre_tool)
    hooks["PreToolUse"].extend(_claude_pretooluse_hooks(strict=strict, project=project))
    _write_settings_with_backup(settings_path, settings)
    _mode = " (strict)" if strict else ""
    print(f"  .claude/settings.json  ->  PreToolUse hooks registered (Bash|Grep search + Read/Glob){_mode}")


def _uninstall_claude_hook(project_dir: Path) -> None:
    claude_dir = project_dir / ".claude"
    for name in ("settings.json", "settings.local.json"):
        _strip_graphify_hook(claude_dir / name)


def _strip_graphify_hook(settings_path: Path) -> None:
    if not settings_path.exists():
        return
    try:
        settings = json.loads(settings_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return
    pre_tool = settings.get("hooks", {}).get("PreToolUse", [])
    if not isinstance(pre_tool, list):
        return
    filtered = _strip_graphify_hooks(pre_tool)
    if filtered == pre_tool:
        return
    settings["hooks"]["PreToolUse"] = filtered
    _write_settings_with_backup(settings_path, settings)
    print(f"  .claude/{settings_path.name}  ->  PreToolUse hook removed")


def _unsafe_purge_reason(out: Path, project_dir: Path) -> str | None:
    """Why ``rmtree(out)`` must not run for ``--purge``, or None when it is safe."""
    target = out.resolve()
    project = project_dir.resolve()
    home = Path.home().resolve()
    if target == project or target in project.parents:
        return "the project folder or one of its parents"
    if target == home or target in home.parents:
        return "your home folder or one of its parents"
    if target == Path(target.anchor):
        return "a filesystem root"
    return None


def uninstall_all(project_dir: Path | None = None, purge: bool = False) -> None:
    pd = project_dir or Path(".")
    out = pd / _GRAPHIFY_OUT
    if purge:
        reason = _unsafe_purge_reason(out, pd)
        if reason:
            print(
                f"error: refusing --purge: {out.resolve()} is {reason}. "
                "Nothing was changed. Check the GRAPHIFY_OUT environment variable.",
                file=sys.stderr,
            )
            sys.exit(1)
    print("Uninstalling graphify from all detected platforms...\n")

    claude_uninstall(pd, remove_user_skill=True)
    codebuddy_uninstall(pd, remove_user_skill=True)
    gemini_uninstall(pd, remove_user_skill=True)
    vscode_uninstall(pd)
    _cursor_uninstall(pd)
    _kiro_uninstall(pd)
    _antigravity_uninstall(pd)
    _agents_uninstall(pd)
    _remove_skill_file("amp")
    _remove_skill_file("agents")
    _uninstall_opencode_plugin(pd)
    _uninstall_codex_hook(pd)
    _mimo_uninstall(pd)

    try:
        from graphify.hooks import uninstall as hook_uninstall
        result = hook_uninstall(pd)
        if result:
            print(result)
    except Exception:
        pass

    if purge:
        import shutil as _shutil
        if out.exists():
            _shutil.rmtree(out)
            print(f"\n  {_GRAPHIFY_OUT}/  ->  deleted (--purge)")
        else:
            print(f"\n  {_GRAPHIFY_OUT}/  ->  not found (nothing to purge)")

    print("\nDone. Run 'pip uninstall graphifyy' to remove the package itself.")


def claude_uninstall(project_dir: Path | None = None, *, project: bool = False, remove_user_skill: bool | None = None) -> None:
    explicit_dir = project_dir is not None
    project_dir = project_dir or Path(".")
    if remove_user_skill is None:
        remove_user_skill = not project and not explicit_dir
    if project or (explicit_dir and not remove_user_skill):
        _remove_skill_file("claude", project=True, project_dir=project_dir)
    if remove_user_skill:
        _remove_skill_file("claude", project=False)

    md_targets = [
        project_dir / "CLAUDE.md",
        project_dir / "CLAUDE.local.md",
        project_dir / ".claude" / "CLAUDE.local.md",
    ]
    existing = [t for t in md_targets if t.exists()]
    removed_any = False
    for target in existing:
        if _strip_graphify_md_section(target):
            removed_any = True

    if not existing:
        print("No CLAUDE.md found in current directory - nothing to do")
    elif not removed_any:
        print("graphify section not found in CLAUDE.md - nothing to do")

    _uninstall_claude_hook(project_dir)


def _strip_graphify_md_section(target: Path) -> bool:
    try:
        content, newline = _read_keep_newline(target)
    except (OSError, UnicodeDecodeError):
        return False
    cleaned = _remove_marker_section(content, _CLAUDE_MD_MARKER)
    if cleaned is None:
        return False
    if cleaned or target.is_symlink():
        _write_keep_newline(target, cleaned + "\n", newline)
        print(f"graphify section removed from {target.resolve()}")
    else:
        target.unlink()
        print(f"{target.name} was empty after removal - deleted {target.resolve()}")
    return True


def codebuddy_install(project_dir: Path | None = None) -> None:
    _copy_skill_file("codebuddy", project=bool(project_dir), project_dir=project_dir)
    target = (project_dir or Path(".")) / "CODEBUDDY.md"

    if target.exists():
        content, newline = _read_keep_newline(target)
        new_content = _replace_or_append_section(
            content, _CODEBUDDY_MD_MARKER, _always_on("claude-md")
        )
    else:
        content, newline = "", "\n"
        new_content = _always_on("claude-md")

    if target.exists() and new_content == content:
        print(f"graphify already configured in {target.resolve()} (no change)")
    else:
        _write_keep_newline(target, new_content, newline)
        print(f"graphify section written to {target.resolve()}")

    _install_codebuddy_hook(project_dir or Path("."))

    print()
    print("CodeBuddy will now check the knowledge graph before answering")
    print("codebase questions and rebuild it after code changes.")


def _install_codebuddy_hook(project_dir: Path) -> None:
    settings_path = project_dir / ".codebuddy" / "settings.json"
    settings_path.parent.mkdir(parents=True, exist_ok=True)

    settings = _read_settings_for_merge(settings_path)

    hooks = settings.setdefault("hooks", {})
    if not isinstance(hooks, dict):
        _refuse_to_modify(settings_path)
    pre_tool = hooks.setdefault("PreToolUse", [])
    if not isinstance(pre_tool, list):
        _refuse_to_modify(settings_path)

    hooks["PreToolUse"] = _strip_graphify_hooks(pre_tool)
    hooks["PreToolUse"].extend(_claude_pretooluse_hooks())
    _write_settings_with_backup(settings_path, settings)
    print(f"  .codebuddy/settings.json  ->  PreToolUse hooks registered")


def _uninstall_codebuddy_hook(project_dir: Path) -> None:
    settings_path = project_dir / ".codebuddy" / "settings.json"
    if not settings_path.exists():
        return
    try:
        settings = json.loads(settings_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return
    pre_tool = settings.get("hooks", {}).get("PreToolUse", [])
    if not isinstance(pre_tool, list):
        return
    filtered = _strip_graphify_hooks(pre_tool)
    if filtered == pre_tool:
        return
    settings["hooks"]["PreToolUse"] = filtered
    _write_settings_with_backup(settings_path, settings)
    print(f"  .codebuddy/settings.json  ->  PreToolUse hook removed")


def codebuddy_uninstall(project_dir: Path | None = None, *, project: bool = False, remove_user_skill: bool | None = None) -> None:
    explicit_dir = project_dir is not None
    project_dir = project_dir or Path(".")
    if remove_user_skill is None:
        remove_user_skill = not project and not explicit_dir
    if project or (explicit_dir and not remove_user_skill):
        _remove_skill_file("codebuddy", project=True, project_dir=project_dir)
    if remove_user_skill:
        _remove_skill_file("codebuddy", project=False)
    target = project_dir / "CODEBUDDY.md"

    if not target.exists():
        print("No CODEBUDDY.md found in current directory - nothing to do")
        return

    content, newline = _read_keep_newline(target)
    cleaned = _remove_marker_section(content, _CODEBUDDY_MD_MARKER)
    if cleaned is None:
        print("graphify section not found in CODEBUDDY.md - nothing to do")
        return

    if cleaned or target.is_symlink():
        _write_keep_newline(target, cleaned + "\n", newline)
        print(f"graphify section removed from {target.resolve()}")
    else:
        target.unlink()
        print(f"CODEBUDDY.md was empty after removal - deleted {target.resolve()}")

    _uninstall_codebuddy_hook(project_dir or Path("."))


_CLI_INSTALL_COMMANDS = frozenset({
    "agents", "aider", "amp", "antigravity", "claude", "claw", "codebuddy",
    "codex", "copilot", "cursor", "devin", "droid", "gemini", "hermes",
    "install", "kilo", "kiro", "mimo", "opencode", "pi", "skills", "trae",
    "trae-cn", "uninstall", "vscode",
})


def dispatch_install_cli(cmd: str) -> bool:
    if cmd not in _CLI_INSTALL_COMMANDS:
        return False
    if cmd == "install":
        default_platform = "windows" if platform.system() == "Windows" else "claude"
        selected_platform: str | None = None
        project_scope = False
        strict = False
        args = sys.argv[2:]
        i = 0
        while i < len(args):
            arg = args[i]
            if arg in ("-h", "--help"):
                _print_install_usage()
                return True
            if arg == "--project":
                project_scope = True
                i += 1
            elif arg == "--strict":
                strict = True
                i += 1
            elif arg.startswith("--platform="):
                candidate = arg.split("=", 1)[1]
                if selected_platform and selected_platform != candidate:
                    print("error: specify install platform only once", file=sys.stderr)
                    sys.exit(1)
                selected_platform = candidate
                i += 1
            elif arg == "--platform":
                if i + 1 >= len(args):
                    print("error: --platform requires a value", file=sys.stderr)
                    sys.exit(1)
                candidate = args[i + 1]
                if selected_platform and selected_platform != candidate:
                    print("error: specify install platform only once", file=sys.stderr)
                    sys.exit(1)
                selected_platform = candidate
                i += 2
            elif arg.startswith("-"):
                print(f"error: unknown install option '{arg}'", file=sys.stderr)
                sys.exit(1)
            else:
                if selected_platform and selected_platform != arg:
                    print("error: specify install platform only once", file=sys.stderr)
                    sys.exit(1)
                selected_platform = arg
                i += 1
        chosen_platform = selected_platform or default_platform
        if project_scope:
            _project_install(chosen_platform, Path("."), strict=strict)
        else:
            if strict:
                print(
                    "note: --strict applies to the project PreToolUse hook; run "
                    "`graphify install --project --strict` or `graphify claude install --strict`.",
                    file=sys.stderr,
                )
            install(platform=chosen_platform)
        return True

    if cmd == "uninstall":
        args = sys.argv[2:]
        purge = "--purge" in args
        project_scope = "--project" in args
        selected_platform = None
        i = 0
        while i < len(args):
            arg = args[i]
            if arg in ("--purge", "--project"):
                i += 1
            elif arg.startswith("--platform="):
                selected_platform = arg.split("=", 1)[1]
                i += 1
            elif arg == "--platform":
                if i + 1 >= len(args):
                    print("error: --platform requires a value", file=sys.stderr)
                    sys.exit(1)
                selected_platform = args[i + 1]
                i += 2
            elif arg.startswith("-"):
                print(f"error: unknown uninstall option '{arg}'", file=sys.stderr)
                sys.exit(1)
            else:
                selected_platform = arg
                i += 1
        if project_scope:
            if selected_platform:
                _project_uninstall(selected_platform, Path("."))
            else:
                _project_uninstall_all(Path("."))
        else:
            uninstall_all(purge=purge)
        return True

    if cmd == "claude":
        subcmd = sys.argv[2] if len(sys.argv) > 2 else ""
        if subcmd == "install":
            _strict = "--strict" in sys.argv[3:]
            if "--project" in sys.argv[3:]:
                _project_install("claude", Path("."), strict=_strict)
            else:
                claude_install(strict=_strict)
        elif subcmd == "uninstall":
            if "--project" in sys.argv[3:]:
                _project_uninstall("claude", Path("."))
            else:
                claude_uninstall()
        else:
            print("Usage: graphify claude [install|uninstall]", file=sys.stderr)
            sys.exit(1)
        return True

    if cmd == "codebuddy":
        subcmd = sys.argv[2] if len(sys.argv) > 2 else ""
        if subcmd == "install":
            codebuddy_install()
        elif subcmd == "uninstall":
            codebuddy_uninstall()
        else:
            print("Usage: graphify codebuddy [install|uninstall]", file=sys.stderr)
            sys.exit(1)
        return True

    if cmd == "gemini":
        subcmd = sys.argv[2] if len(sys.argv) > 2 else ""
        if subcmd == "install":
            gemini_install(project=("--project" in sys.argv[3:]))
        elif subcmd == "uninstall":
            gemini_uninstall(project=("--project" in sys.argv[3:]))
        else:
            print("Usage: graphify gemini [install|uninstall]", file=sys.stderr)
            sys.exit(1)
        return True

    if cmd == "cursor":
        subcmd = sys.argv[2] if len(sys.argv) > 2 else ""
        if subcmd == "install":
            _cursor_install(Path("."))
        elif subcmd == "uninstall":
            _cursor_uninstall(Path("."))
        else:
            print("Usage: graphify cursor [install|uninstall]", file=sys.stderr)
            sys.exit(1)
        return True

    if cmd == "vscode":
        subcmd = sys.argv[2] if len(sys.argv) > 2 else ""
        if subcmd == "install":
            vscode_install()
        elif subcmd == "uninstall":
            vscode_uninstall()
        else:
            print("Usage: graphify vscode [install|uninstall]", file=sys.stderr)
            sys.exit(1)
        return True

    if cmd == "copilot":
        subcmd = sys.argv[2] if len(sys.argv) > 2 else ""
        if subcmd == "install":
            if "--project" in sys.argv[3:]:
                _project_install("copilot", Path("."))
            else:
                install(platform="copilot")
        elif subcmd == "uninstall":
            if "--project" in sys.argv[3:]:
                _project_uninstall("copilot", Path("."))
            else:
                removed = _remove_skill_file("copilot")
                print("skill removed" if removed else "nothing to remove")
        else:
            print("Usage: graphify copilot [install|uninstall]", file=sys.stderr)
            sys.exit(1)
        return True

    if cmd == "kilo":
        subcmd = sys.argv[2] if len(sys.argv) > 2 else ""
        if subcmd == "install":
            _kilo_install(Path("."))
        elif subcmd == "uninstall":
            _kilo_uninstall(Path("."))
        else:
            print("Usage: graphify kilo [install|uninstall]", file=sys.stderr)
            sys.exit(1)
        return True

    if cmd == "kiro":
        subcmd = sys.argv[2] if len(sys.argv) > 2 else ""
        if subcmd == "install":
            _kiro_install(Path("."))
        elif subcmd == "uninstall":
            _kiro_uninstall(Path("."))
        else:
            print("Usage: graphify kiro [install|uninstall]", file=sys.stderr)
            sys.exit(1)
        return True

    if cmd == "devin":
        subcmd = sys.argv[2] if len(sys.argv) > 2 else ""
        if subcmd == "install":
            if "--project" in sys.argv[3:]:
                _project_install("devin", Path("."))
            else:
                install(platform="devin")
        elif subcmd == "uninstall":
            if "--project" in sys.argv[3:]:
                _project_uninstall("devin", Path("."))
            else:
                removed = _remove_skill_file("devin")
                print("skill removed" if removed else "nothing to remove")
        else:
            print("Usage: graphify devin [install|uninstall]", file=sys.stderr)
            sys.exit(1)
        return True

    if cmd == "pi":
        subcmd = sys.argv[2] if len(sys.argv) > 2 else ""
        if subcmd == "install":
            if "--project" in sys.argv[3:]:
                _project_install("pi", Path("."))
            else:
                install("pi")
        elif subcmd == "uninstall":
            if "--project" in sys.argv[3:]:
                _project_uninstall("pi", Path("."))
            else:
                _remove_skill_file("pi")
        elif subcmd == "guard" and sys.argv[3:] in (["install"], ["uninstall"], ["path"]):
            package_path = Path(__file__).resolve().parent / "pi"
            if sys.argv[3] == "path":
                print(package_path)
                return True
            pi = shutil.which("pi")
            if not pi:
                print("error: install Pi (pi) and add it to PATH first", file=sys.stderr)
                sys.exit(1)
            import subprocess
            verb = "install" if sys.argv[3] == "install" else "remove"
            result = subprocess.run([pi, verb, str(package_path)], check=False)
            if result.returncode:
                sys.exit(result.returncode)
        else:
            print("Usage: graphify pi [install|uninstall] | graphify pi guard [install|uninstall|path]", file=sys.stderr)
            sys.exit(1)
        return True

    if cmd == "amp":
        subcmd = sys.argv[2] if len(sys.argv) > 2 else ""
        if subcmd == "install":
            if "--project" in sys.argv[3:]:
                _project_install("amp", Path("."))
            else:
                _amp_install(Path("."))
        elif subcmd == "uninstall":
            if "--project" in sys.argv[3:]:
                _project_uninstall("amp", Path("."))
            else:
                _amp_uninstall(Path("."))
        else:
            print("Usage: graphify amp [install|uninstall]", file=sys.stderr)
            sys.exit(1)
        return True

    if cmd in ("agents", "skills"):
        subcmd = sys.argv[2] if len(sys.argv) > 2 else ""
        if subcmd == "install":
            if "--project" in sys.argv[3:]:
                _project_install("agents", Path("."))
            else:
                _agents_platform_install(Path("."))
        elif subcmd == "uninstall":
            if "--project" in sys.argv[3:]:
                _project_uninstall("agents", Path("."))
            else:
                _agents_platform_uninstall(Path("."))
        else:
            print(f"Usage: graphify {cmd} [install|uninstall]", file=sys.stderr)
            sys.exit(1)
        return True

    if cmd in ("aider", "codex", "opencode", "claw", "droid", "trae", "trae-cn", "hermes"):
        subcmd = sys.argv[2] if len(sys.argv) > 2 else ""
        if subcmd == "install":
            if "--project" in sys.argv[3:]:
                _project_install(cmd, Path("."))
            else:
                _agents_install(Path("."), cmd)
        elif subcmd == "uninstall":
            if "--project" in sys.argv[3:]:
                _project_uninstall(cmd, Path("."))
            else:
                _agents_uninstall(Path("."), platform=cmd)
                if cmd == "codex":
                    _uninstall_codex_hook(Path("."))
        else:
            print(f"Usage: graphify {cmd} [install|uninstall]", file=sys.stderr)
            sys.exit(1)
        return True

    if cmd == "antigravity":
        subcmd = sys.argv[2] if len(sys.argv) > 2 else ""
        if subcmd == "install":
            if "--project" in sys.argv[3:]:
                _project_install("antigravity", Path("."))
            else:
                _antigravity_install(Path("."))
        elif subcmd == "uninstall":
            if "--project" in sys.argv[3:]:
                _project_uninstall("antigravity", Path("."))
            else:
                _antigravity_uninstall(Path("."))
        else:
            print("Usage: graphify antigravity [install|uninstall]", file=sys.stderr)
            sys.exit(1)
        return True

    if cmd == "mimo":
        subcmd = sys.argv[2] if len(sys.argv) > 2 else ""
        args = sys.argv[3:]
        project_scope = False
        i = 0
        while i < len(args):
            arg = args[i]
            if arg in ("-h", "--help"):
                print("Usage: graphify mimo [install|uninstall|status] [--project] [--scope project|global]", file=sys.stderr)
                return True
            elif arg in ("--project", "--scope=project"):
                project_scope = True
                i += 1
            elif arg == "--scope=global":
                project_scope = False
                i += 1
            elif arg == "--scope":
                if i + 1 >= len(args):
                    print("error: --scope requires a value (project|global)", file=sys.stderr)
                    sys.exit(1)
                val = args[i + 1]
                if val == "project":
                    project_scope = True
                elif val == "global":
                    project_scope = False
                else:
                    print(f"error: invalid scope '{val}'. Choose from: project, global", file=sys.stderr)
                    sys.exit(1)
                i += 2
            elif arg.startswith("-"):
                print(f"error: unknown mimo option '{arg}'", file=sys.stderr)
                sys.exit(1)
            else:
                print(f"error: unexpected argument '{arg}'", file=sys.stderr)
                sys.exit(1)

        if subcmd == "install":
            if project_scope:
                _project_install("mimo", Path("."))
            else:
                _mimo_install(Path("."))
        elif subcmd == "uninstall":
            if project_scope:
                _project_uninstall("mimo", Path("."))
            else:
                _mimo_uninstall(Path("."))
        elif subcmd == "status":
            _mimo_status(Path("."), project=project_scope)
        else:
            print("Usage: graphify mimo [install|uninstall|status] [--project]", file=sys.stderr)
            sys.exit(1)
        return True

    return False