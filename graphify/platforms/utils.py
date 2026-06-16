"""Shared utilities for platform installers."""

from __future__ import annotations

import functools
import json
import os
import platform
import re
import shutil
import sys
from pathlib import Path

try:
    from importlib.metadata import version as _pkg_version

    __version__ = _pkg_version("graphifyy")
except Exception:
    __version__ = "unknown"

_GRAPHIFY_OUT = os.environ.get("GRAPHIFY_OUT", "graphify-out")


@functools.lru_cache(maxsize=None)
def _always_on(basename: str) -> str:
    path = Path(__file__).parent.parent / "always_on" / f"{basename}.md"
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        raise RuntimeError(
            f"graphify install is incomplete: missing always-on block '{basename}' "
            f"at {path}. Reinstall graphifyy (e.g. `uv tool install --reinstall graphifyy`)."
        ) from exc


_ALWAYS_ON_ALIASES = {
    "_CLAUDE_MD_SECTION": "claude-md",
    "_AGENTS_MD_SECTION": "agents-md",
    "_GEMINI_MD_SECTION": "gemini-md",
    "_VSCODE_INSTRUCTIONS_SECTION": "vscode-instructions",
    "_ANTIGRAVITY_RULES": "antigravity-rules",
    "_KIRO_STEERING": "kiro-steering",
}


def _platform_skill_destination(
    platform_name: str, *, project: bool = False, project_dir: Path | None = None
) -> Path:
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

    if platform_name == "devin":
        if project:
            return (project_dir or Path(".")) / ".devin" / "skills" / "graphify" / "SKILL.md"
        return Path.home() / ".config" / "devin" / "skills" / "graphify" / "SKILL.md"

    if platform_name == "amp":
        if project:
            return (project_dir or Path(".")) / ".agents" / "skills" / "graphify" / "SKILL.md"
        return Path.home() / ".config" / "agents" / "skills" / "graphify" / "SKILL.md"

    if platform_name in ("antigravity", "antigravity-windows"):
        if project:
            return (project_dir or Path(".")) / ".agents" / "skills" / "graphify" / "SKILL.md"
        return Path.home() / ".gemini" / "config" / "skills" / "graphify" / "SKILL.md"

    cfg = PLATFORM_CONFIG[platform_name]
    if project:
        return (project_dir or Path(".")) / cfg["skill_dst"]

    if platform_name in ("claude", "windows") and os.environ.get("CLAUDE_CONFIG_DIR"):
        return Path(os.environ["CLAUDE_CONFIG_DIR"]) / "skills" / "graphify" / "SKILL.md"
    return Path.home() / cfg["skill_dst"]


def _packaged_skill_refs_dir(platform_name: str) -> Path | None:
    if platform_name == "gemini":
        bundle = "claude"
    else:
        bundle = PLATFORM_CONFIG[platform_name].get("skill_refs")
    if not bundle:
        return None
    bundle_dir = Path(__file__).parent.parent / "skills" / bundle
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
        if refs_dst.exists():
            shutil.rmtree(refs_dst)
        os.replace(refs_staged, refs_dst)
    except Exception:
        if refs_staged.exists():
            shutil.rmtree(refs_staged, ignore_errors=True)
        raise


def _copy_skill_file(
    platform_name: str, *, project: bool = False, project_dir: Path | None = None
) -> Path:
    skill_file = (
        "skill.md" if platform_name == "gemini" else PLATFORM_CONFIG[platform_name]["skill_file"]
    )
    skill_src = Path(__file__).parent.parent / skill_file
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
    skill_dst.parent.mkdir(parents=True, exist_ok=True)

    if refs_src is not None:
        _install_skill_references(skill_dst, refs_src)
        print(f"  references       ->  {skill_dst.parent / 'references'}")
    else:
        orphan_refs = skill_dst.parent / "references"
        if orphan_refs.exists():
            shutil.rmtree(orphan_refs)

    tmp_dst = skill_dst.with_suffix(skill_dst.suffix + ".tmp")
    try:
        shutil.copy(skill_src, tmp_dst)
        os.replace(tmp_dst, skill_dst)
    except Exception:
        try:
            tmp_dst.unlink(missing_ok=True)
        except OSError:
            pass
        raise

    (skill_dst.parent / ".graphify_version").write_text(__version__, encoding="utf-8")
    print(f"  skill installed  ->  {skill_dst}")
    return skill_dst


def _remove_skill_file(
    platform_name: str, *, project: bool = False, project_dir: Path | None = None
) -> bool:
    skill_dst = _platform_skill_destination(platform_name, project=project, project_dir=project_dir)
    removed = False
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
    content = claude_md.read_text(encoding="utf-8")
    if "# graphify" not in content:
        return
    cleaned = re.sub(r"\n*# graphify\n.*?(?=\n# |\Z)", "", content, flags=re.DOTALL).rstrip()
    if cleaned:
        claude_md.write_text(cleaned + "\n", encoding="utf-8")
        print(f"  CLAUDE.md        ->  graphify skill registration removed from {claude_md}")
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


def _replace_or_append_section(content: str, marker: str, new_section: str) -> str:
    if marker not in content:
        if content.strip():
            return content.rstrip() + "\n\n" + new_section.lstrip()
        return new_section.lstrip()

    lines = content.split("\n")
    start = next((i for i, line in enumerate(lines) if marker in line), None)
    if start is None:
        return content.rstrip() + "\n\n" + new_section.lstrip()

    end = len(lines)
    for j in range(start + 1, len(lines)):
        if lines[j].startswith("## "):
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


def _print_banner() -> None:
    if not sys.stdout.isatty():
        return
    try:
        if sys.platform == "win32":
            import ctypes

            ctypes.windll.kernel32.SetConsoleMode(ctypes.windll.kernel32.GetStdHandle(-11), 7)
        A = "\033[38;5;214m"
        D = "\033[38;5;130m"
        R = "\033[0m"
        print(f"""{A}
  ╭──◉──╮     ╭──◉──╮
 ╱  ◉   ◉ ╲ ╱ ◉   ◉  ╲
│   ◉─◉─◉  ◉  ◉─◉─◉   │
│    ◉   ◉ │ ◉   ◉    │
│   ◉─◉─◉  ◉  ◉─◉─◉   │
 ╲  ◉   ◉ ╱ ╲ ◉   ◉  ╱
  ╰──◉──╯     ╰──◉──╯
           ◉

  █▀▀ █▀█ ▄▀█ █▀█ █ █ █ █▀▀ █▄█
  █▄█ █▀▄ █▀█ █▀▀ █▀█ █ █▀   █{D}  {__version__}{R}
""")
    except Exception:
        pass


def _check_skill_version(skill_dst: Path) -> None:
    version_file = skill_dst.parent / ".graphify_version"
    try:
        if not version_file.exists():
            return
    except OSError:
        return
    try:
        skill_exists = skill_dst.exists()
    except OSError:
        return
    if not skill_exists:
        print(
            "  warning: skill dir exists but SKILL.md is missing. Run 'graphify install' to repair."
        )
        return
    try:
        body = skill_dst.read_text(encoding="utf-8")
    except OSError:
        body = ""
    if "references/" in body and not (skill_dst.parent / "references").exists():
        print(
            "  warning: skill references/ sidecar is missing. Run 'graphify install' to repair.",
            file=sys.stderr,
        )
    try:
        installed = version_file.read_text(encoding="utf-8").strip()
    except OSError:
        return
    if installed != __version__:
        print(
            f"  warning: skill is from graphify {installed}, package is {__version__}. Run 'graphify install' to update.",
            file=sys.stderr,
        )


def _refresh_all_version_stamps() -> None:
    for name in PLATFORM_CONFIG:
        skill_dst = _platform_skill_destination(name)
        vf = skill_dst.parent / ".graphify_version"
        if skill_dst.exists():
            vf.write_text(__version__, encoding="utf-8")


def _skill_registration(skill_path: str = "~/.claude/skills/graphify/SKILL.md") -> str:
    return (
        "\n# graphify\n"
        f"- **graphify** (`{skill_path}`) "
        "- any input to knowledge graph. Trigger: `/graphify`\n"
        "When the user types `/graphify`, invoke the Skill tool "
        'with `skill: "graphify"` before doing anything else.\n'
    )


PLATFORM_CONFIG: dict[str, dict] = {
    "claude": {
        "skill_file": "skill.md",
        "skill_dst": Path(".claude") / "skills" / "graphify" / "SKILL.md",
        "claude_md": True,
        "skill_refs": "claude",
    },
    "codex": {
        "skill_file": "skill-codex.md",
        "skill_dst": Path(".codex") / "skills" / "graphify" / "SKILL.md",
        "claude_md": False,
        "skill_refs": "codex",
    },
    "opencode": {
        "skill_file": "skill-opencode.md",
        "skill_dst": Path(".config") / "opencode" / "skills" / "graphify" / "SKILL.md",
        "claude_md": False,
        "skill_refs": "opencode",
    },
    "kilo": {
        "skill_file": "skill-kilo.md",
        "skill_dst": Path(".config") / "kilo" / "skills" / "graphify" / "SKILL.md",
        "claude_md": False,
        "skill_refs": "kilo",
    },
    "aider": {
        "skill_file": "skill-aider.md",
        "skill_dst": Path(".aider") / "graphify" / "SKILL.md",
        "claude_md": False,
    },
    "copilot": {
        "skill_file": "skill-copilot.md",
        "skill_dst": Path(".copilot") / "skills" / "graphify" / "SKILL.md",
        "claude_md": False,
        "skill_refs": "copilot",
    },
    "claw": {
        "skill_file": "skill-claw.md",
        "skill_dst": Path(".openclaw") / "skills" / "graphify" / "SKILL.md",
        "claude_md": False,
        "skill_refs": "claw",
    },
    "droid": {
        "skill_file": "skill-droid.md",
        "skill_dst": Path(".factory") / "skills" / "graphify" / "SKILL.md",
        "claude_md": False,
        "skill_refs": "droid",
    },
    "trae": {
        "skill_file": "skill-trae.md",
        "skill_dst": Path(".trae") / "skills" / "graphify" / "SKILL.md",
        "claude_md": False,
        "skill_refs": "trae",
    },
    "trae-cn": {
        "skill_file": "skill-trae.md",
        "skill_dst": Path(".trae-cn") / "skills" / "graphify" / "SKILL.md",
        "claude_md": False,
        "skill_refs": "trae",
    },
    "hermes": {
        "skill_file": "skill-claw.md",
        "skill_dst": Path(".hermes") / "skills" / "graphify" / "SKILL.md",
        "claude_md": False,
        "skill_refs": "claw",
    },
    "kiro": {
        "skill_file": "skill-kiro.md",
        "skill_dst": Path(".kiro") / "skills" / "graphify" / "SKILL.md",
        "claude_md": False,
        "skill_refs": "kiro",
    },
    "pi": {
        "skill_file": "skill-pi.md",
        "skill_dst": Path(".pi") / "agent" / "skills" / "graphify" / "SKILL.md",
        "claude_md": False,
        "skill_refs": "pi",
    },
    "codebuddy": {
        "skill_file": "skill.md",
        "skill_dst": Path(".codebuddy") / "skills" / "graphify" / "SKILL.md",
        "claude_md": False,
        "skill_refs": "claude",
    },
    "antigravity": {
        "skill_file": "skill.md",
        "skill_dst": Path(".agents") / "skills" / "graphify" / "SKILL.md",
        "claude_md": False,
        "skill_refs": "claude",
    },
    "antigravity-windows": {
        "skill_file": "skill-windows.md",
        "skill_dst": Path(".agents") / "skills" / "graphify" / "SKILL.md",
        "claude_md": False,
        "skill_refs": "windows",
    },
    "windows": {
        "skill_file": "skill-windows.md",
        "skill_dst": Path(".claude") / "skills" / "graphify" / "SKILL.md",
        "claude_md": True,
        "skill_refs": "windows",
    },
    "kimi": {
        "skill_file": "skill.md",
        "skill_dst": Path(".kimi") / "skills" / "graphify" / "SKILL.md",
        "claude_md": False,
        "skill_refs": "claude",
    },
    "amp": {
        "skill_file": "skill-amp.md",
        "skill_dst": Path(".agents") / "skills" / "graphify" / "SKILL.md",
        "claude_md": False,
        "skill_refs": "amp",
    },
    "devin": {
        "skill_file": "skill-devin.md",
        "skill_dst": Path(".config") / "devin" / "skills" / "graphify" / "SKILL.md",
        "claude_md": False,
    },
}


SETTINGS_HOOK = {
    "matcher": "Bash",
    "hooks": [
        {
            "type": "command",
            "command": (
                'CMD=$(python3 -c "'
                "import json,sys; d=json.load(sys.stdin); "
                "print(d.get('tool_input',d).get('command',''))\" 2>/dev/null || true); "
                'case "$CMD" in '
                r"*grep*|*rg\ *|*ripgrep*|*find\ *|*fd\ *|*ack\ *|*ag\ *) "
                "  [ -f graphify-out/graph.json ] && "
                r"""  echo '{"hookSpecificOutput":{"hookEventName":"PreToolUse","additionalContext":"MANDATORY: graphify-out/graph.json exists. You MUST run `graphify query \"<question>\"` before grepping raw files. Only grep after graphify has oriented you, or to modify/debug specific lines."}}' """
                "  || true ;; "
                "esac"
            ),
        }
    ],
}

READ_SETTINGS_HOOK = {
    "matcher": "Read|Glob",
    "hooks": [
        {
            "type": "command",
            "command": (
                'HIT=$(python3 -c "'
                "import json,sys;"
                "d=json.load(sys.stdin);"
                "t=d.get('tool_input',d);"
                "s=(str(t.get('file_path') or '')+' '+str(t.get('pattern') or '')+' '+str(t.get('path') or '')).lower().replace(chr(92),'/');"
                "exts=('.py','.js','.ts','.tsx','.jsx','.go','.rs','.java','.rb','.c','.h','.cpp','.hpp','.cc','.cs','.kt','.swift','.php','.scala','.lua','.sh','.md','.rst','.txt','.mdx');"
                "sys.stdout.write('1' if 'graphify-out/' not in s and any(e in s for e in exts) else '')\" 2>/dev/null || true); "
                'if [ "$HIT" = 1 ] && [ -f graphify-out/graph.json ]; then '
                r"""echo '{"hookSpecificOutput":{"hookEventName":"PreToolUse","additionalContext":"MANDATORY: graphify-out/graph.json exists. You MUST run graphify before reading source files. Use: `graphify query \"<question>\"` (scoped subgraph), `graphify explain \"<concept>\"`, or `graphify path \"<A>\" \"<B>\"`. Only read raw files after graphify has oriented you, or to modify/debug specific lines. This rule applies to subagents too — include it in every subagent prompt involving code exploration."}}'; """
                "fi || true"
            ),
        }
    ],
}

GEMINI_HOOK = {
    "matcher": "read_file|list_directory",
    "hooks": [
        {
            "type": "command",
            "command": (
                'python -c "'
                "import sys,pathlib,json;"
                "e=pathlib.Path('graphify-out/graph.json').exists();"
                "d={'decision':'allow'};"
                "e and d.update({'additionalContext':'graphify: knowledge graph at graphify-out/. For focused questions, run `graphify query \"<question>\"` (scoped subgraph, usually much smaller than GRAPH_REPORT.md) instead of grepping raw files. Read GRAPH_REPORT.md only for broad architecture context.'});"
                "sys.stdout.write(json.dumps(d))"
                '"'
            ),
        }
    ],
}

CLAUDE_MD_MARKER = "## graphify"
GEMINI_MD_MARKER = "## graphify"
