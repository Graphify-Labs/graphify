#!/usr/bin/env python3
"""Cross-platform driver for the offline Windows installer build.

Wraps the same workflow as `tools/build_windows_installer.sh` but in
Python so it can be driven from CI (Linux/macOS) when a Windows VM
runner is available. On a non-Windows host this script downloads the
wheels and prepares the wheelhouse, but the actual Nuitka compilation
requires a Windows runner (it shells out to cl.exe or MinGW).

For local end-to-end builds, use `tools/build_windows_installer.sh`
on the Windows host directly.
"""

from __future__ import annotations

import argparse
import platform
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--skip-nuitka",
        action="store_true",
        help="only download wheels; skip the Nuitka compilation step",
    )
    parser.add_argument(
        "--python",
        default=sys.executable,
        help="Python interpreter to use (default: current)",
    )
    args = parser.parse_args()

    wheelhouse = REPO_ROOT / "wheelhouse-windows"
    wheelhouse.mkdir(exist_ok=True)
    dist = REPO_ROOT / "dist"
    dist.mkdir(exist_ok=True)

    # 1. Resolve the wheel list from pyproject.toml.
    import tomllib
    pyproject = tomllib.loads(REPO_ROOT.joinpath("pyproject.toml").read_text("rb" if False else "utf-8"))
    wheels = pyproject["project"]["optional-dependencies"]["windows-offline"]
    req_file = wheelhouse / "_requirements.txt"
    req_file.write_text("\n".join(wheels) + "\n", encoding="utf-8")

    # 2. Download wheels.
    print(f"==> Downloading {len(wheels)} wheels to {wheelhouse}")
    subprocess.run(
        [
            args.python, "-m", "pip", "download",
            "--dest", str(wheelhouse),
            "--python-version", "3.10",
            "--platform", "win_amd64",
            "--only-binary=:all:",
            "--requirement", str(req_file),
        ],
        check=True,
    )

    if args.skip_nuitka:
        print("==> --skip-nuitka set; stopping after wheel download.")
        return 0

    # 3. Compile via Nuitka. Only do this on a Windows host.
    if platform.system() != "Windows":
        print("==> Non-Windows host: skipping Nuitka compilation.")
        print("    Re-run on Windows to produce the .exe artifacts.")
        return 0

    venv = REPO_ROOT / ".venv-offline-build"
    if venv.exists():
        shutil.rmtree(venv)
    subprocess.run([args.python, "-m", "venv", str(venv)], check=True)
    py = venv / "Scripts" / "python.exe"
    subprocess.run(
        [str(py), "-m", "pip", "install", "--no-index",
         "--find-links", str(wheelhouse), "graphifyy"],
        check=True,
    )
    # (Nuitka invocations are identical to the .sh script; not duplicated here
    # to avoid drift. For a real Windows build, just call the .sh script.)
    print("==> This driver only does wheel download. On Windows, run:")
    print("       tools/build_windows_installer.sh")
    return 0


if __name__ == "__main__":
    sys.exit(main())
