#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# Copyright 2021 Alibaba Group Holding Limited. All Rights Reserved.
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

#
# This file is originally from the GraphScope project
# (https://github.com/alibaba/GraphScope) Licensed under the Apache-2.0 License. Modified by
# Zhanglei in 2025 to support Neug-specific features.
#

import hashlib
import logging
import os
import shutil
import sys
import tarfile
import tempfile
import time
import urllib
import zipfile
from urllib.request import urlretrieve

from tqdm import tqdm

logger = logging.getLogger(__name__)

DATA_SITE = "https://graphscope.oss-cn-beijing.aliyuncs.com/neug-dataset"

MAX_RETRIES = 3

if sys.version_info >= (3, 6):

    def _path_to_string(path):
        if isinstance(path, os.PathLike):
            return os.fspath(path)
        return path

elif sys.version_info >= (3, 4):

    def _path_to_string(path):
        import pathlib

        if isinstance(path, pathlib.Path):
            return str(path)
        return path

else:

    def _path_to_string(path):
        return path


def _resolve_hasher(algorithm, file_hash=None):
    """Returns hash algorithm as hashlib function."""
    if algorithm == "sha256":
        return hashlib.sha256()
    if algorithm == "auto" and file_hash is not None and len(file_hash) == 64:
        return hashlib.sha256()
    return hashlib.md5()


def _hash_file(fpath, algorithm="sha256", chunk_size=65535):
    """Calculates a file sha256 or md5 hash.

    Examples:
        ..code:: python

        >>> _hash_file("/path/to/file")
        "ccd128ab673e5d7dd1cceeaa4ba5d65b67a18212c4a27b0cd090359bd7042b10"
    """
    if isinstance(algorithm, str):
        hasher = _resolve_hasher(algorithm)
    else:
        hasher = algorithm
    with open(fpath, "rb") as file:
        for chunk in iter(lambda: file.read(chunk_size), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def _is_within_directory(directory, target):
    abs_directory = os.path.abspath(directory)
    abs_target = os.path.abspath(target)
    return os.path.commonprefix([abs_directory, abs_target]) == abs_directory


def _safe_extractall(archive, path):
    """Extract archive contents, using filter='data' on Python 3.12+."""
    if sys.version_info >= (3, 12):
        archive.extractall(path, filter="data")
        return

    if isinstance(archive, zipfile.ZipFile):
        for member in archive.namelist():
            member_path = os.path.join(path, member)
            if not _is_within_directory(path, member_path):
                raise ValueError(
                    f"Refusing to extract zip entry outside target dir: {member!r}"
                )
    elif isinstance(archive, tarfile.TarFile):
        for member in archive.getmembers():
            member_path = os.path.join(path, member.name)
            if not _is_within_directory(path, member_path):
                raise ValueError(
                    f"Refusing to extract tar entry outside target dir: {member.name!r}"
                )
    archive.extractall(path)


def _extract_archive(fpath, path=".", archive_format="auto"):
    """Extracts an archive if it matches tar.gz, tar.bz, tar, or zip formats.

    Args:
        fpath: `PathLike` object of the archive file.
        path: path to extract the archive file.
        archive_format (str): Archive format to try for extracting the file.
            Options are "tar", "zip", "auto" or None.
            "tar" includes tar, tar.gz, tar.bz files.
            The default "auto" is ["tar", "zip"].
            None or an empty list will return no matches found.

    Returns:
        str: Path to the extracted directory or file.
    """
    if archive_format is None:
        return False
    if archive_format == "auto":
        archive_format = ["tar", "zip"]
    if isinstance(archive_format, str):
        archive_format = [archive_format]

    fpath = _path_to_string(fpath)
    path = _path_to_string(path)
    extracted_fpath = None

    for archive_type in archive_format:
        if archive_type == "tar":
            open_fn = tarfile.open
            is_match_fn = tarfile.is_tarfile
            extracted_fpath = fpath[:-7] if fpath.endswith(".tar.gz") else fpath[:-4]

        if archive_type == "zip":
            open_fn = zipfile.ZipFile
            is_match_fn = zipfile.is_zipfile
            extracted_fpath = fpath[:-4] if fpath.endswith(".zip") else fpath

        if is_match_fn(fpath):
            with open_fn(fpath) as archive:
                try:
                    _safe_extractall(archive, path)
                except (tarfile.TarError, RuntimeError, KeyboardInterrupt):
                    if os.path.exists(path):
                        if os.path.isfile(path):
                            os.remove(path)
                        else:
                            shutil.rmtree(path)
                    raise
            return extracted_fpath
    return None


def validate_file(fpath, file_hash, algorithm="auto", chunk_size=65535):
    """Validates a file against a sha256 or md5 hash.

    Args:
        fpath: `PathLike` object of the file being validated
        file_hash (str): The expected hash string of the file.
            The sha256 and md5 hash algorithms are both supported.
        algorithm (str): Hash algorithm, one of "auto", "sha256", or "md5".
             The default "auto" detects the hash algorithm in use.
        chunk_size (int): Bytes to read at a time, important for large files.

    Returns (bool): Whether the file is valid.
    """
    hasher = _resolve_hasher(algorithm, file_hash)
    if str(_hash_file(fpath, hasher, chunk_size)) == str(file_hash):
        return True
    return False


def download_file(  # noqa: C901
    fname,
    origin,
    file_hash=None,
    hash_algorithm="auto",
    extract=False,
    archive_format="auto",
    cache_dir=None,
    cache_subdir="datasets",
):
    """Downloads a file from a URL if it not already in the cache.

    By default the file at the url `origin` is downloaded to the cache_dir
    `~/.neug, placed in the cache_subdir `datasets`, and given the
    filename `fname`. The final location of a file `example.txt` would
    therefore be `~/.neug/datsets/example.txt`

    File in tar, tar.gz, tar.bz, and zip formats can also be extracted.
    Passing a hash will verify the file after download. The command line
    programs `shasum` and `sha256sum` can compute the hash.

    Args:
        fname: `PathLike` object of the file. If an absolute path `/path/to/file`
            is specified the file will be saved at that location.
        origin (str): Original URL of the file.
        file_hash (str): The excepted hash string of the file after download.
            The sha256 and md5 hash algorithms are both supported.
        hash_algorithm (str): Select the hash algorithm to verify the file.
            Options are `"md5"`, `"sha256"`, and `"auto"`
            The default "auto" detects the hash algorithm in use.
        extract (bool): True tries extracting the file as an Archive, like zip.
        archive_format (str): Archive format to try for extracting the file.
            Options are `"auto"` `"tar"` `"zip"` and `None`.
            `"tar"` includes "tar", "tar.gz", and "tar.bz" files.
            The default `"auto"` corresponds to `["tar", "zip"]`.
            None or an empty list will return no matches found.
        cache_dir: Location of `PathLike` object to store cached files, when None,
            it defaults to the default directory `~/.neug`
        cache_subdir: Subdirectory under the cache dir where the file is saved.

    Returns:
        Path to the download file.
    """
    if cache_dir is None:
        cache_dir = os.path.join(os.path.expanduser("~"), ".neug")
    cache_dir = os.path.expanduser(cache_dir)
    if os.path.exists(cache_dir) and not os.access(cache_dir, os.W_OK):
        cache_dir = os.path.join("/", tempfile.gettempprefix(), ".neug")
    datadir = os.path.join(cache_dir, cache_subdir)
    os.makedirs(datadir, exist_ok=True)

    fname = _path_to_string(fname)
    fpath = os.path.join(datadir, fname)
    extracted_fpath = None

    download = False
    if os.path.exists(fpath):
        # file found, verify if a hash was provided
        if file_hash is not None:
            if not validate_file(fpath, file_hash, algorithm=hash_algorithm):
                logger.warning(
                    "A local file was found, but it seems to be incomplete "
                    "or outdated because the %s file hash does not match the "
                    "original value of %s, so we will re-download the data.",
                    hash_algorithm,
                    file_hash,
                )
                download = True
    else:
        download = True

    if download:
        logger.info("Downloading data from %s", origin)

        class ProgressTracker(object):
            # Maintain progbar for the lifetime of download
            progbar = None
            record_downloaded = None

        def show_progress(block_num, block_size, total_size):
            if ProgressTracker.progbar is None:
                ProgressTracker.progbar = tqdm(
                    total=total_size, unit="iB", unit_scale=True
                )
            downloaded = min(block_num * block_size, total_size)
            if ProgressTracker.record_downloaded is None:
                ProgressTracker.record_downloaded = downloaded
                update_downloaded = downloaded
            else:
                update_downloaded = downloaded - ProgressTracker.record_downloaded
                ProgressTracker.record_downloaded = downloaded
            ProgressTracker.progbar.update(update_downloaded)
            if downloaded >= total_size:
                ProgressTracker.progbar.close()
                ProgressTracker.progbar = None
                ProgressTracker.record_downloaded = None

        max_retries = MAX_RETRIES
        error_msg_tpl = "URL fetch failure on {}:{} -- {}"
        try:
            for retry in range(max_retries):
                backoff = max(2**retry, 1.0)
                try:
                    urlretrieve(origin, fpath, show_progress)
                except urllib.error.HTTPError as e:
                    error_msg = error_msg_tpl.format(origin, e.code, e.msg)
                    logger.warning("%s, retry %s times...", error_msg, retry)
                    if retry >= max_retries - 1:
                        raise Exception(error_msg)
                    time.sleep(backoff)
                except urllib.error.URLError as e:
                    # `URLError` has been made a subclass of OSError since version 3.3
                    # https://docs.python.org/3/library/urllib.error.html
                    error_msg = error_msg_tpl.format(origin, e.errno, e.reason)
                    logger.warning("%s, retry %s times...", error_msg, retry)
                    if retry >= max_retries - 1:
                        raise Exception(error_msg)
                    time.sleep(backoff)
                else:
                    break
        except (Exception, KeyboardInterrupt):
            if os.path.exists(fpath):
                os.remove(fpath)
            raise

    if extract:
        extracted_fpath = _extract_archive(fpath, datadir, archive_format)

    return fpath, extracted_fpath
