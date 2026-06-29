"""Install manifest: records what the offline installer did, so uninstall
can reverse it cleanly.

Stored at `<install_root>/.graphify_install.json` (typically
`%LOCALAPPDATA%\graphify\.graphify_install.json` on Windows).
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import List, Optional


@dataclass
class InstallManifest:
    """Snapshot of an offline install, written to disk for later uninstall."""

    version: str
    install_path: Path
    hosts: List[str] = field(default_factory=list)
    user_path_added: bool = False
    created_shortcut: bool = False
    # Per-host record of the exact skill directory we wrote to, so uninstall
    # can `rmtree` it without re-probing the filesystem.
    skill_dirs: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["install_path"] = str(self.install_path)
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "InstallManifest":
        return cls(
            version=d["version"],
            install_path=Path(d["install_path"]),
            hosts=list(d.get("hosts", [])),
            user_path_added=bool(d.get("user_path_added", False)),
            created_shortcut=bool(d.get("created_shortcut", False)),
            skill_dirs=list(d.get("skill_dirs", [])),
        )


def manifest_path() -> Path:
    """Default manifest location: %LOCALAPPDATA%\\graphify\\.graphify_install.json.

    On non-Windows the function still returns a sensible path under the user's
    home; the installer is Windows-only but this helper is import-safe on every
    platform.
    """
    base = os.environ.get("LOCALAPPDATA") or str(Path.home())
    return Path(base) / "graphify" / ".graphify_install.json"


def save_manifest(m: InstallManifest, path: Path) -> None:
    """Write `m` to `path` as JSON. Creates parent directories as needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(m.to_dict(), indent=2), encoding="utf-8")


def load_manifest(path: Path) -> InstallManifest:
    """Load and validate a manifest from `path`. Raises FileNotFoundError."""
    if not path.exists():
        raise FileNotFoundError(f"No install manifest at {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    return InstallManifest.from_dict(data)
