"""Offline Windows installer orchestrator.

The single entry points are `install()` and `uninstall()` — the rest of the
package is helpers. The compiled `graphify-installer.exe` (built from
`tools/installer_main.py`) calls these.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path
from typing import List, Optional

from graphify.installer import host_probe, manifest, path_win, skill_copy

# Re-export the helpers at the package level. Two reasons:
#   1. Tests `monkeypatch.setattr("graphify.installer.<name>", ...)` need
#      the names reachable on the package itself; submodule-only lookups
#      would miss the patch.
#   2. `install()` / `uninstall()` below look up these names through the
#      module globals, so the same patch chain applies in production code.
detect_hosts = host_probe.detect_hosts
add_to_user_path = path_win.add_to_user_path
remove_from_user_path = path_win.remove_from_user_path


def install(
    *,
    install_path: Path,
    user_root: Path,
    version: str,
    manifest_target: Optional[Path] = None,
) -> manifest.InstallManifest:
    """Run the offline install.

    Steps:
    1. Probe `user_root` for installed hosts.
    2. Copy each host's SKILL.md (+ references/) into the host's skill dir.
    3. Register `install_path / bin` on the user-level PATH.
    4. Write the install manifest.
    """
    hosts = detect_hosts(root=user_root)
    skill_dirs: List[str] = []

    for host in hosts:
        try:
            out_dir = skill_copy.copy_skill(host, root=user_root)
            skill_dirs.append(str(out_dir))
        except Exception as exc:  # noqa: BLE001
            # We never abort the install for a single host failure; record it.
            print(
                f"[graphify-installer] warn: failed to install skill for "
                f"{host.name}: {exc}",
                file=sys.stderr,
            )

    bin_path = install_path / "bin"
    try:
        add_to_user_path(str(bin_path))
        user_path_added = True
    except path_win.PathWinError as exc:
        print(
            f"[graphify-installer] warn: could not register PATH ({exc}); "
            f"add {bin_path} to your PATH manually.",
            file=sys.stderr,
        )
        user_path_added = False

    m = manifest.InstallManifest(
        version=version,
        install_path=install_path,
        hosts=[h.name for h in hosts],
        user_path_added=user_path_added,
        skill_dirs=skill_dirs,
    )
    target = manifest_target or (install_path / ".graphify_install.json")
    manifest.save_manifest(m, target)
    return m


def uninstall(*, manifest_file: Path) -> None:
    """Reverse a previous install: remove skill dirs, drop PATH, delete manifest."""
    if not manifest_file.exists():
        raise FileNotFoundError(f"No install manifest at {manifest_file}")
    m = manifest.load_manifest(manifest_file)

    for skill_dir_str in m.skill_dirs:
        skill_dir = Path(skill_dir_str)
        if skill_dir.exists():
            shutil.rmtree(skill_dir, ignore_errors=True)

    if m.user_path_added:
        try:
            remove_from_user_path(str(m.install_path / "bin"))
        except path_win.PathWinError as exc:
            print(
                f"[graphify-installer] warn: could not remove PATH entry ({exc}); "
                f"remove it manually.",
                file=sys.stderr,
            )

    if m.install_path.exists():
        shutil.rmtree(m.install_path, ignore_errors=True)

    manifest_file.unlink(missing_ok=True)
