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

import os
from pathlib import Path

import packaging
from packaging import version

try:
    from importlib import metadata as importlib_metadata
except ImportError:  # pragma: no cover - Python <3.8 fallback
    import importlib_metadata  # type: ignore


def _read_version_file(path: Path) -> str:
    if path.is_file():
        return path.read_text(encoding="utf-8").strip()
    return ""


def _read_pkg_info(start_path: Path) -> str:
    for candidate in (start_path, *start_path.parents):
        pkg_info = candidate / "PKG-INFO"
        if pkg_info.is_file():
            for line in pkg_info.read_text(encoding="utf-8").splitlines():
                if line.startswith("Version: "):
                    return line.split("Version: ", 1)[1].strip()
    return ""


def _load_version() -> str:
    try:
        return importlib_metadata.version("neug")
    except importlib_metadata.PackageNotFoundError:
        pass

    module_dir = Path(__file__).resolve().parent
    try:
        repo_root = module_dir.parents[2]
    except IndexError:
        repo_root = module_dir
    version_value = _read_version_file(repo_root / "NEUG_VERSION")
    if version_value:
        return version_value

    version_value = _read_pkg_info(module_dir)
    if version_value:
        return version_value

    return "0.0.0"


sv = version.parse(_load_version())
__is_prerelease__ = sv.is_prerelease
__version__ = str(sv)

__version_tuple__ = (v for v in __version__.split("."))
