"""Copy the right SKILL.md (and references/) to a host's skill directory.

Sources the bundle from the installed `graphify` package. For hosts whose
bundle is in `graphify/__main__:_PLATFORM_CONFIG` (claude, opencode, etc.),
we pick the host-specific file. For hosts NOT in the config (mobilecoder),
we fall back to `skill.md` (the Claude bundle) — the user is responsible
for adjusting the body if their host needs a different format.
"""

from __future__ import annotations

import shutil
from importlib.resources import files
from pathlib import Path
from typing import Optional

from graphify.installer.host_probe import Host, host_skill_dir

# Hosts detected on the user's machine but NOT supported by the offline
# installer. Their real install path is via `graphify install <host>` (which
# runs after the offline installer has placed the binary on PATH). The
# offline installer must NOT write a SKILL.md into their directories — that
# would silently fail (the host's own format is different — `.mdc`, hook
# into GEMINI.md, etc.).
_UNSUPPORTED_IN_OFFLINE_INSTALLER = frozenset({"cursor", "gemini"})

# Map host name -> the skill body filename in the graphify package.
# Hosts whose body is `skill.md` (the Claude bundle) don't need an entry.
_BODY_BY_HOST = {
    "claude":      "skill.md",
    "codex":       "skill-codex.md",
    "opencode":    "skill-opencode.md",
    "kilo":        "skill-kilo.md",
    "aider":       "skill-aider.md",
    "copilot":     "skill-copilot.md",
    "codebuddy":   "skill.md",       # reuses claude bundle
    "kiro":        "skill-kiro.md",
    "droid":       "skill-droid.md",
    "trae":        "skill-trae.md",
    "trae-cn":     "skill-trae.md",
    "hermes":      "skill-claw.md",
    "pi":          "skill-pi.md",
    "claw":        "skill-claw.md",
    "antigravity": "skill.md",       # reuses claude bundle
    "vscode":      "skill-vscode.md",
    "amp":         "skill-amp.md",
    "agents":      "skill-agents.md",
    "mobilecoder": "skill.md",       # not first-class; fall back to claude body
}

# Map host name -> the sidecar references directory inside the package
# (relative to the package root). None = no references/ to copy.
_REFS_BY_HOST = {
    "claude":      "skills/claude/references",
    "codex":       "skills/codex/references",
    "opencode":    "skills/opencode/references",
    "kilo":        "skills/kilo/references",
    "copilot":     "skills/copilot/references",
    "codebuddy":   "skills/claude/references",
    "kiro":        "skills/kiro/references",
    "droid":       "skills/droid/references",
    "trae":        "skills/trae/references",
    "hermes":      "skills/claw/references",
    "pi":          "skills/pi/references",
    "claw":        "skills/claw/references",
    "antigravity": "skills/claude/references",
    "vscode":      "skills/vscode/references",
    "amp":         "skills/amp/references",
    "agents":      "skills/agents/references",
}


def _pick_skill_body(host_name: str) -> str:
    """Return the text of the skill body for `host_name`.

    Looks up the body file in the installed graphify package. If the host
    has no specific entry, falls back to `skill.md` (the Claude bundle).
    """
    body_name = _BODY_BY_HOST.get(host_name, "skill.md")
    try:
        return (files("graphify").joinpath(body_name).read_text(encoding="utf-8"))
    except (FileNotFoundError, ModuleNotFoundError):
        # In tests we may be operating against a fake package; fall back to
        # the package_root passed by the test, if any.
        return ""


def copy_skill(
    host: Host,
    *,
    root: Path,
    package_root: Optional[Path] = None,
) -> Path:
    """Write SKILL.md (and references/) for `host` under `root`.

    `package_root` is the path to the `graphify` package directory; defaults
    to the installed package. It exists so tests can inject a fake package
    without `importlib.resources` finding real files.
    """
    out_dir = host_skill_dir(host, root=root)
    if host.name in _UNSUPPORTED_IN_OFFLINE_INSTALLER:
        # Skip silently — no SKILL.md, no references/. The user's next
        # `graphify install cursor` (or `graphify install gemini`) will
        # write the host's real config. We do NOT mkdir the target dir:
        # some hosts (notably `gemini`) are sensitive to empty dirs.
        import sys
        print(
            f"[graphify-installer] note: skipping {host.name}; "
            f"after install run `graphify install {host.name}` to register the skill.",
            file=sys.stderr,
        )
        return out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    # Read the body.
    body_name = _BODY_BY_HOST.get(host.name, "skill.md")
    if package_root is not None:
        body_path = package_root / body_name
        body = body_path.read_text(encoding="utf-8") if body_path.exists() else ""
    else:
        body = _pick_skill_body(host.name)

    (out_dir / "SKILL.md").write_text(body, encoding="utf-8")

    # Copy references/ if the host has them.
    refs_rel = _REFS_BY_HOST.get(host.name)
    if refs_rel:
        if package_root is not None:
            src_refs = package_root / refs_rel
        else:
            # Use importlib.resources traversal.
            from importlib.resources import as_file
            try:
                ref_resource = files("graphify").joinpath(*refs_rel.split("/"))
                with as_file(ref_resource) as p:
                    src_refs = p
            except (FileNotFoundError, ModuleNotFoundError, TypeError):
                src_refs = None
        if src_refs is not None and src_refs.exists():
            dst_refs = out_dir / "references"
            if dst_refs.exists():
                shutil.rmtree(dst_refs)
            shutil.copytree(src_refs, dst_refs)

    return out_dir
