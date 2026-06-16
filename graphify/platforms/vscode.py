"""VS Code Copilot Chat platform installer."""

from __future__ import annotations

import os
import shutil
from pathlib import Path

from .base import BasePlatformInstaller
from .registry import register

_VSCODE_INSTRUCTIONS_MARKER = "## graphify"


def _get_version() -> str:
    try:
        from importlib.metadata import version as _pkg_version

        return _pkg_version("graphifyy")
    except Exception:
        return "unknown"


def _always_on(basename: str) -> str:
    path = Path(__file__).parent.parent / "always_on" / f"{basename}.md"
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        raise RuntimeError(
            f"graphify install is incomplete: missing always-on block '{basename}' "
            f"at {path}. Reinstall graphifyy (e.g. `uv tool install --reinstall graphifyy`)."
        ) from exc


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


@register("vscode")
class VSCodeInstaller(BasePlatformInstaller):
    name = "vscode"

    def install(self, project_dir: Path | None = None, *, project: bool = False) -> None:
        skill_src = Path(__file__).parent.parent / "skill-vscode.md"
        refs_bundle = "vscode"
        if not skill_src.exists():
            skill_src = Path(__file__).parent.parent / "skill-copilot.md"
            refs_bundle = "copilot"
        skill_dst = Path.home() / ".copilot" / "skills" / "graphify" / "SKILL.md"
        skill_dst.parent.mkdir(parents=True, exist_ok=True)
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
        refs_src = Path(__file__).parent.parent / "skills" / refs_bundle / "references"
        if refs_src.exists():
            _install_skill_references(skill_dst, refs_src)
            print(f"  references       ->  {skill_dst.parent / 'references'}")
        else:
            orphan_refs = skill_dst.parent / "references"
            if orphan_refs.exists():
                shutil.rmtree(orphan_refs)
        (skill_dst.parent / ".graphify_version").write_text(_get_version(), encoding="utf-8")
        print(f"  skill installed  ->  {skill_dst}")

        instructions = (project_dir or Path(".")) / ".github" / "copilot-instructions.md"
        instructions.parent.mkdir(parents=True, exist_ok=True)
        if instructions.exists():
            content = instructions.read_text(encoding="utf-8")
            new_content = _replace_or_append_section(
                content, _VSCODE_INSTRUCTIONS_MARKER, _always_on("vscode-instructions")
            )
            if new_content == content:
                print(f"  {instructions}  ->  already configured (no change)")
            else:
                instructions.write_text(new_content, encoding="utf-8")
                print(
                    f"  {instructions}  ->  graphify section {'updated' if _VSCODE_INSTRUCTIONS_MARKER in content else 'added'}"
                )
        else:
            instructions.write_text(_always_on("vscode-instructions"), encoding="utf-8")
            print(f"  {instructions}  ->  created")

        print()
        print(
            "VS Code Copilot Chat configured. Type /graphify in the chat panel to build the graph."
        )
        print("Note: for GitHub Copilot CLI (terminal), use: graphify copilot install")

    def uninstall(self, project_dir: Path | None = None, *, project: bool = False) -> None:
        skill_dst = Path.home() / ".copilot" / "skills" / "graphify" / "SKILL.md"
        if skill_dst.exists():
            skill_dst.unlink()
            print(f"  skill removed    ->  {skill_dst}")
        version_file = skill_dst.parent / ".graphify_version"
        if version_file.exists():
            version_file.unlink()
        refs_dir = skill_dst.parent / "references"
        if refs_dir.exists():
            shutil.rmtree(refs_dir)
        for d in (
            skill_dst.parent,
            skill_dst.parent.parent,
            skill_dst.parent.parent.parent,
        ):
            try:
                d.rmdir()
            except OSError:
                break

        instructions = (project_dir or Path(".")) / ".github" / "copilot-instructions.md"
        if not instructions.exists():
            return
        content = instructions.read_text(encoding="utf-8")
        if _VSCODE_INSTRUCTIONS_MARKER not in content:
            return
        import re

        cleaned = re.sub(r"\n*## graphify\n.*?(?=\n## |\Z)", "", content, flags=re.DOTALL).rstrip()
        if cleaned:
            instructions.write_text(cleaned + "\n", encoding="utf-8")
            print(f"  graphify section removed from {instructions}")
        else:
            instructions.unlink()
            print(f"  {instructions}  ->  deleted (was empty after removal)")
