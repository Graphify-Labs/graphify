"""Fail clearly when the pinned public embedded Helix wheel is unavailable."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import platform
import re
import sys
import urllib.request


def _pinned_version() -> str:
    # This check intentionally runs before dependency installation, including on
    # Python 3.10 where tomllib is not in the standard library. Keep it stdlib-only.
    project = Path("pyproject.toml").read_text(encoding="utf-8")
    match = re.search(
        r'^embedded_package\s*=\s*"helix-db-embedded==([^\"]+)"\s*$',
        project,
        flags=re.MULTILINE,
    )
    if match is None:
        raise RuntimeError("pyproject.toml must exactly pin helix-db-embedded")
    return match.group(1)


def _platform_tag(selected: str) -> str:
    if selected != "auto":
        return selected
    machine = platform.machine().lower()
    if sys.platform == "win32":
        return "windows-x86_64"
    if sys.platform == "darwin":
        return "macos-universal2"
    if machine in {"aarch64", "arm64"}:
        return "linux-aarch64"
    return "linux-x86_64"


def _matches(filename: str, selected: str) -> bool:
    name = filename.lower()
    if not name.endswith(".whl"):
        return False
    if selected == "windows-x86_64":
        return name.endswith("-win_amd64.whl")
    if selected == "macos-universal2":
        return "macosx" in name and "universal2" in name
    if selected == "linux-aarch64":
        return "manylinux" in name and "aarch64" in name
    if selected == "linux-x86_64":
        return "manylinux" in name and "x86_64" in name
    raise ValueError(f"unsupported platform selector: {selected}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--platform",
        default="auto",
        choices=(
            "auto",
            "windows-x86_64",
            "macos-universal2",
            "linux-x86_64",
            "linux-aarch64",
        ),
    )
    args = parser.parse_args()
    version = _pinned_version()
    selected = _platform_tag(args.platform)
    url = f"https://pypi.org/pypi/helix-db-embedded/{version}/json"
    try:
        with urllib.request.urlopen(url, timeout=20) as response:  # noqa: S310
            payload = json.load(response)
    except Exception as exc:
        print(f"error: could not inspect public Helix package metadata: {exc}", file=sys.stderr)
        return 2
    files = [item.get("filename", "") for item in payload.get("urls", [])]
    if any(_matches(filename, selected) for filename in files):
        print(f"public helix-db-embedded=={version} wheel available for {selected}")
        return 0
    expected = {
        "windows-x86_64": "*-win_amd64.whl",
        "macos-universal2": "*-macosx-*-universal2.whl",
        "linux-x86_64": "*-manylinux*-x86_64.whl",
        "linux-aarch64": "*-manylinux*-aarch64.whl",
    }[selected]
    print(
        f"error: public helix-db-embedded=={version} has no {expected} artifact; "
        "native Graphify support for this platform remains blocked",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
