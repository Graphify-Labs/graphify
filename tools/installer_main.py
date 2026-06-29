"""Standalone entry point for the offline Windows installer.

This script is the entry point for the Nuitka-compiled
`graphify-installer.exe`. It accepts:

    graphify-installer.exe install     # run the install wizard
    graphify-installer.exe uninstall   # reverse a previous install
    graphify-installer.exe --version
    graphify-installer.exe --help

It does NOT import `graphify.__main__` (which has click-style side effects
and the full CLI surface). It imports only the installer subpackage, which
is what the compiled .exe needs to do its job.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Make `graphify` importable when this script is run as a Nuitka-compiled
# entry point. The compiled binary has the package frozen in, so this
# import works in both modes (script and frozen).
from graphify.installer import install as _install, uninstall as _uninstall
from graphify.installer.manifest import manifest_path as _default_manifest
from graphify.installer.host_probe import detect_hosts as _detect_hosts

try:
    from importlib.metadata import version as _pkg_version
    __version__ = _pkg_version("graphifyy")
except Exception:
    __version__ = "unknown"


def _print_banner() -> None:
    print(f"graphify offline installer {__version__}")
    print(f"  install path: {_default_manifest().parent}")


def cmd_install(args: argparse.Namespace) -> int:
    _print_banner()
    hosts = _detect_hosts()
    if not hosts:
        print("warning: no known AI-coding host detected on this machine.")
        print("         The graphify binary will still be installed;")
        print("         you'll need to copy SKILL.md to your host manually.")
    else:
        names = ", ".join(h.name for h in hosts)
        print(f"  detected hosts: {names}")

    target = Path(args.path) if args.path else _default_manifest().parent
    print(f"  installing to: {target}")

    manifest = _install(
        install_path=target,
        user_root=Path.home(),
        version=__version__,
    )
    print("  done.")
    if manifest.user_path_added:
        print(f"  user PATH registered: {target / 'bin'}")
        print("  (open a new cmd window for PATH changes to take effect)")
    return 0


def cmd_uninstall(args: argparse.Namespace) -> int:
    _print_banner()
    manifest_file = _default_manifest()
    if not manifest_file.exists():
        print(f"no install manifest at {manifest_file}")
        print("nothing to uninstall.")
        return 1
    _uninstall(manifest_file=manifest_file)
    print("  done.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="graphify-installer",
        description="Offline Windows installer for graphify.",
    )
    parser.add_argument("--version", action="store_true")
    sub = parser.add_subparsers(dest="command")

    p_install = sub.add_parser("install", help="install graphify to %%LOCALAPPDATA%%\\graphify")
    p_install.add_argument("--path", help="override install path")

    p_uninstall = sub.add_parser("uninstall", help="reverse a previous install")

    ns = parser.parse_args(argv)
    if ns.version:
        print(f"graphify-installer {__version__}")
        return 0
    if ns.command == "install":
        return cmd_install(ns)
    if ns.command == "uninstall":
        return cmd_uninstall(ns)
    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())