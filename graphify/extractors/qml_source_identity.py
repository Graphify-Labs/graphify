"""Relative Qt fact ownership after physical admission, without target authority.

Readers retain source bytes, limits and publication ownership. This stateless
boundary reuses native spelling admission and walked-name selection; it reads
identity metadata only and stores no root, index or cache between calls.
"""
from __future__ import annotations

import os
from pathlib import Path

from graphify.source_identity import normalize_input_source, walked_relative_source


class SourceInputIdentityError(ValueError):
    """Preserve the native admission category without carrying backend bodies."""
    code = "SOURCE_INPUT_IDENTITY_FAILED"
    reason = "native_source_spelling_unavailable"

    def __init__(self):
        super().__init__("SOURCE_INPUT_IDENTITY_FAILED: native source spelling unavailable; "
                         "repair filesystem access and retry")


def relative_qml_source(path: Path, root: Path | None) -> str:
    """Keep discovered lexical owners while rejecting foreign physical targets."""
    try:
        admitted = normalize_input_source(Path(path), root)
    except ValueError:
        raise SourceInputIdentityError() from None
    # POSIX link/.. traversal follows the physical parent. Capture that input
    # before lexical abspath normalization can describe a different file.
    physical = admitted.resolve()
    written = physical if ".." in admitted.parts else Path(os.path.abspath(admitted))
    anchor = Path(root).resolve() if root is not None else physical.parent

    def realpath(value: str, _cwd: str) -> Path:
        # Explicit inputs are absolute; the shared naming boundary owns neither
        # this reader's filesystem calls nor a second memoization lifetime.
        return Path(value).resolve()

    return walked_relative_source(written, anchor, physical,
                                  realpath=realpath, cwd=os.getcwd()).as_posix()
