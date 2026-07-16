#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# Copyright 2020 Alibaba Group Holding Limited. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
import glob
import logging
import os
import platform
import sys

from packaging.version import InvalidVersion
from packaging.version import Version

import neug
from neug.version import __version__

logger = logging.getLogger("neug")

_PROTOBUF_VERSION_OVERRIDE_ENV = "NEUG_EXPECTED_PROTOBUF_VERSION"
_PROTOBUF_CHECK_SKIP_ENV = "NEUG_SKIP_PROTOBUF_CHECK"
_EXPECTED_PROTOBUF_VERSION = os.environ.get(_PROTOBUF_VERSION_OVERRIDE_ENV, "5.29.6")


def _ensure_protobuf_runtime_matches() -> None:
    """Fail fast when google.protobuf's Python wheel does not match the bundled C++ runtime."""

    skip_check = os.environ.get(_PROTOBUF_CHECK_SKIP_ENV, "0").upper() in {
        "1",
        "TRUE",
        "ON",
        "YES",
    }
    if skip_check:
        logger.warning(
            "Skipping protobuf compatibility guard because %s is set.",
            _PROTOBUF_CHECK_SKIP_ENV,
        )
        return

    try:
        from google.protobuf import __version__ as protobuf_version  # type: ignore
    except ImportError as exc:
        raise ImportError(
            "NeuG requires the 'protobuf' package. Install it via 'python3 -m pip install protobuf==%s'."
            % _EXPECTED_PROTOBUF_VERSION
        ) from exc

    normalized_version = protobuf_version.split("+")[0]
    try:
        expected = Version(_EXPECTED_PROTOBUF_VERSION)
        current = Version(normalized_version)
    except InvalidVersion:
        logger.warning(
            "Unable to parse protobuf versions (expected=%s, installed=%s); proceeding without ABI guard.",
            _EXPECTED_PROTOBUF_VERSION,
            protobuf_version,
        )
        return

    if current != expected:
        raise ImportError(
            "NeuG bundles protobuf %s, but python loaded protobuf %s. "
            "Install the matching wheel (python3 -m pip install protobuf==%s) or override via %s."
            % (
                expected,
                protobuf_version,
                expected,
                _PROTOBUF_VERSION_OVERRIDE_ENV,
            )
        )


def config_logging(log_level):
    """Set log level basic on config.
    Args:
        log_level (str): Log level of stdout handler
    """
    logging.basicConfig(level=logging.CRITICAL)

    # `NOTSET` is special as it doesn't show log in Python
    if isinstance(log_level, str):
        log_level = getattr(logging, log_level.upper())
    if log_level == logging.NOTSET:
        log_level = logging.DEBUG

    logger = logging.getLogger("neug")
    logger.setLevel(log_level)


def get_build_lib_dir() -> str:
    """
    Get the build lib directory for the current development environment.
    The path is {CUR_DIR}/../build/lib.{OS}-{ARCH}-{PYTHON_VERSION}
    #OS is the operating system name (e.g., 'linux', 'macosx-version', 'win32')
    #ARCH is the architecture of the machine (e.g., 'x86_64', 'arm64')
    #PYTHON_VERSION is the version of Python (e.g., '3.8')
    Returns:
        str: The build lib directory.
    """
    cur_dir = os.path.dirname(__file__)
    os_name = platform.system().lower()
    build_dir = None
    if os_name == "darwin":
        # find the directory start with lib.macosx-* under build
        # and get the first one
        build_dir_parent = os.path.join(cur_dir, "..", "build")
        if os.path.exists(build_dir_parent):
            build_dirs = [
                d for d in os.listdir(build_dir_parent) if d.startswith("lib.macosx-")
            ]
            if build_dirs:
                # select the most matching directory, the directories are like lib.macosx-11.0-arm64-cpython-312
                # we should get the one matches current python version
                logger.info("Found build directories: %s", build_dirs)
                build_dirs.sort(
                    key=lambda x: (
                        x.split("-")[-1],  # e.g., cpython-312
                        x.split("-")[2],  # e.g., arm64
                    ),
                    reverse=True,
                )
                # select the directory that matches the current Python version
                py_version = f"cpython-{sys.version_info.major}{sys.version_info.minor}"
                matching_dirs = [
                    d for d in build_dirs if py_version in d and os.uname().machine in d
                ]
                if matching_dirs:
                    first = matching_dirs[0]
                    logger.info("Selected build directory: %s", first)
                    build_dir = os.path.join(build_dir_parent, first)
                else:
                    raise RuntimeError(
                        f"No matching build directory found for Python {sys.version_info.major}.{sys.version_info.minor} and architecture {os.uname().machine}."
                    )
                logger.info("Selected build directory: %s", first)
                if (
                    first.find(
                        f"cpython-{sys.version_info.major}{sys.version_info.minor}"
                    )
                    != -1
                    and first.find(os.uname().machine) != -1
                ):
                    build_dir = os.path.join(build_dir_parent, first)
            else:
                build_dir = None
        else:
            build_dir = None
    else:
        # Try multiple build directory patterns in order of preference
        build_dir_patterns = [
            # Modern pattern with cpython tag (Python 3.8+)
            f"lib.{os_name}-{os.uname().machine}-cpython-{sys.version_info.major}{sys.version_info.minor}",
            # Legacy pattern with version
            f"lib.{os_name}-{os.uname().machine}-{sys.version_info.major}.{sys.version_info.minor}",
            # Very old pattern without version suffix
            f"lib.{os_name}-{os.uname().machine}",
        ]

        build_dir = None
        for pattern in build_dir_patterns:
            candidate = os.path.join(cur_dir, "..", "build", pattern)
            if os.path.exists(candidate):
                build_dir = candidate
                break
    if build_dir is not None:
        if os.path.exists(build_dir):
            logger.debug("Using build directory: %s", build_dir)
    return build_dir


def _find_neug_py_bind_dir():
    """Locate the directory containing neug_py_bind*.so.

    Priority:
      1. Package dir itself (wheel install — setup.py copied .so + libneug here).
      2. NEUG_BUILD_DIR / default <repo_root>/build/tools/python_bind (dev: root build).
      3. Legacy get_build_lib_dir() walk (back-compat for external scripts).
    """
    cur_dir = os.path.dirname(os.path.abspath(__file__))

    if glob.glob(os.path.join(cur_dir, "neug_py_bind*.so")):
        return cur_dir

    # Assume layout: <repo>/tools/python_bind/neug/__init__.py → repo is 3 up.
    repo_root = os.path.abspath(os.path.join(cur_dir, "..", "..", ".."))
    root_build = os.environ.get("NEUG_BUILD_DIR", os.path.join(repo_root, "build"))
    candidate = os.path.join(root_build, "tools", "python_bind")
    if glob.glob(os.path.join(candidate, "neug_py_bind*.so")):
        return candidate

    return get_build_lib_dir()


config_logging("INFO")
_ensure_protobuf_runtime_matches()

_bind_dir = _find_neug_py_bind_dir()
if _bind_dir and _bind_dir not in sys.path:
    logger.info("Adding bindings directory to sys.path: %s", _bind_dir)
    sys.path.insert(0, _bind_dir)

try:
    import neug_py_bind  # noqa: F401
except ImportError as e:
    if os.environ.get("BUILD_DOC", "OFF") == "ON":
        logger.warning("Building docs, skipping C++ extension import.")
    else:
        raise ImportError(
            f"NeuG is not installed. Install via pip or build from source: {e}"
        ) from e

# Resolve where loaded extensions live (loader appends /extension/<name>/):
#  - dev (root build): _bind_dir is <root_build>/tools/python_bind/, but
#    extensions are written by cmake to <root_build>/extension/<name>/, so the
#    extension home is two dirs up from _bind_dir.
#  - wheel install: _bind_dir is None (neug_py_bind*.so sits at site-packages
#    root, not in the neug/ package). CI copies extensions to
#    <site-packages>/extension/<name>/, matching parent-of-__init__.
#  - legacy lib.<plat>-* fallback: extensions used to be colocated with the .so.
_norm_bind = os.path.normpath(_bind_dir) if _bind_dir else ""
if _norm_bind.endswith(os.sep + os.path.join("tools", "python_bind")):
    _extension_home = os.path.abspath(os.path.join(_norm_bind, "..", ".."))
else:
    _extension_home = _bind_dir or os.path.join(os.path.dirname(__file__), "..")
os.environ["NEUG_EXTENSION_HOME_PYENV"] = _extension_home
logger.info("Extension home: %s", os.environ["NEUG_EXTENSION_HOME_PYENV"])

from neug.async_connection import AsyncConnection
from neug.connection import Connection
from neug.database import Database
from neug.query_result import QueryResult
from neug.session import Session
