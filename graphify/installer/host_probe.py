"""Detect which AI-coding hosts are installed on the user's machine.

Probes a small set of well-known home-directory signatures (e.g.
`~/.claude/`, `~/.config/opencode/`, `~/.mobilecoder/`). Used by the offline
installer to decide which host(s) to register the SKILL.md for, and by
`skill_copy` to resolve the per-host skill directory.

For hosts that ARE in `graphify.__main__._PLATFORM_CONFIG` we set
`uses_graphify_install=True` (the installer can call `graphify install <host>`
to do the copy). For hosts that AREN'T (e.g. `mobilecoder`), we set
`uses_graphify_install=False` and the installer must `shutil.copy` SKILL.md
directly to the host's convention path.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List

# Hosts that graphify's `_PLATFORM_CONFIG` knows about; the installer can
# delegate to `graphify install <host>` for these.
_GRAPHIFY_INSTALL_HOSTS = frozenset({
    "claude", "codex", "kilo", "aider", "copilot", "claw", "droid",
    "trae", "trae-cn", "hermes", "kiro", "pi", "codebuddy", "antigravity",
    "windows", "amp", "agents", "vscode",
})


@dataclass(frozen=True)
class Host:
    """A known AI-coding host.

    Attributes:
        name: short identifier (e.g. "claude", "opencode", "mobilecoder").
        marker: a path relative to the user's home directory whose existence
            means this host is installed. Detection is "any file/dir under
            this path" — we just stat the path itself.
        skill_subpath: path relative to `root` where the SKILL.md should
            be written (typically `<root>/<host-home>/skills/graphify/SKILL.md`).
        uses_graphify_install: True if the host is in `_PLATFORM_CONFIG` and
            we should call `graphify install <host>`; False if we must do a
            direct `shutil.copy` (the host isn't first-class supported).
    """
    name: str
    marker: Path
    skill_subpath: Path
    uses_graphify_install: bool


def _host(name: str, marker: str, sub: str, *, in_graphify: bool) -> Host:
    return Host(
        name=name,
        marker=Path(marker),
        skill_subpath=Path(sub),
        uses_graphify_install=in_graphify,
    )


KNOWN_HOSTS: tuple[Host, ...] = (
    _host("claude",      ".claude",                      "skills/graphify",            in_graphify=True),
    _host("codex",       ".codex",                       "skills/graphify",            in_graphify=True),
    _host("opencode",    ".config/opencode",             "skills/graphify",            in_graphify=True),
    _host("kilo",        ".config/kilo",                 "skills/graphify",            in_graphify=True),
    _host("aider",       ".aider",                       "graphify",                   in_graphify=True),
    _host("copilot",     ".copilot",                     "skills/graphify",            in_graphify=True),
    _host("codebuddy",   ".codebuddy",                   "skills/graphify",            in_graphify=True),
    _host("kiro",        ".kiro",                        "skills/graphify",            in_graphify=True),
    _host("droid",       ".factory",                     "skills/graphify",            in_graphify=True),
    _host("trae",        ".trae",                        "skills/graphify",            in_graphify=True),
    _host("trae-cn",     ".trae-cn",                     "skills/graphify",            in_graphify=True),
    _host("hermes",      ".hermes",                      "skills/graphify",            in_graphify=True),
    _host("pi",          ".pi",                          "agent/skills/graphify",      in_graphify=True),
    _host("claw",        ".openclaw",                    "skills/graphify",            in_graphify=True),
    _host("antigravity", ".agents",                      "skills/graphify",            in_graphify=True),
    _host("vscode",      ".vscode",                      "skills/graphify",            in_graphify=True),
    _host("amp",         ".config/amp",                  "skills/graphify",            in_graphify=True),
    _host("agents",      ".config/agents",               "skills/graphify",            in_graphify=True),
    # Unknown to graphify but probed: mobilecoder. Copy SKILL.md directly.
    _host("mobilecoder", ".mobilecoder",                 "skills/graphify",            in_graphify=False),
    _host("cursor",      ".cursor",                      "rules",                      in_graphify=True),
    _host("gemini",      ".gemini",                      "skills/graphify",            in_graphify=True),
)


def detect_hosts(*, root: Path | None = None) -> List[Host]:
    """Return the list of installed hosts under `root` (default: $USERPROFILE).

    A host is "installed" when its marker path exists under `root`. Order
    of KNOWN_HOSTS is preserved in the result.
    """
    if root is None:
        root = Path.home()
    found: list[Host] = []
    for host in KNOWN_HOSTS:
        if (root / host.marker).exists():
            found.append(host)
    return found


def host_skill_dir(host: Host, *, root: Path) -> Path:
    """Absolute directory where SKILL.md should be written for `host`."""
    return root / host.marker / host.skill_subpath