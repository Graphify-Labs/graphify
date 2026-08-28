"""Every document type that reaches the semantic pass must be sliceable.

`_read_files` caps each unit at `_FILE_CHAR_CAP` (20,000 characters) before
joining it into the user message. `expand_oversized_files` exists so an
oversized document is split into contiguous `FileSlice`s that together cover the
whole file — but it only splits suffixes listed in `_SPLITTABLE_TEXT_SUFFIXES`.

That list and `detect.DOC_EXTENSIONS` drifted. `.qmd`, `.skill`, `.html`,
`.yaml` and `.yml` were classified as documents, so they reached the model, and
were not splittable, so a 38,411-character one arrived as its first 20,000
characters — no warning, no `_partial_files` marker, nothing in the report
(#2900).

The contract test below is the point of this file: it fails when a new suffix is
added to `DOC_EXTENSIONS` without deciding how it gets sliced, so the two lists
cannot drift apart again silently.
"""
from pathlib import Path

import pytest

from graphify.detect import DOC_EXTENSIONS
from graphify.file_slice import (
    _SPLITTABLE_TEXT_SUFFIXES,
    expand_oversized_files,
    is_splittable_text,
    read_slice_text,
    slice_boundaries,
)
from graphify.llm import _FILE_CHAR_CAP, _read_files

# Document suffixes whose bytes are NOT what the model is shown, so a character
# range over the raw file would be meaningless. `_file_to_text` routes these
# through a converter; slicing them needs that converter threaded through
# `read_slice_text` first, which is deliberately out of scope here.
BINARY_DOC_SUFFIXES = frozenset({".pdf"})

BIG = "# Heading\n\n" + ("The parser calls the tokenizer. " * 1200)


# ---------------------------------------------------------------------------
# The contract
# ---------------------------------------------------------------------------

def test_every_text_document_type_is_splittable():
    """The guard against re-drift: a plain-text document type that reaches the
    semantic pass must be sliceable, or an oversized one loses its tail."""
    missing = sorted(
        (DOC_EXTENSIONS - BINARY_DOC_SUFFIXES) - _SPLITTABLE_TEXT_SUFFIXES
    )
    assert not missing, (
        f"these document types reach the LLM but are never sliced, so anything "
        f"over {_FILE_CHAR_CAP} characters is silently truncated: {missing}"
    )


@pytest.mark.parametrize(
    "ext", sorted(DOC_EXTENSIONS - BINARY_DOC_SUFFIXES)
)
def test_an_oversized_document_reaches_the_model_whole(tmp_path, ext):
    f = tmp_path / f"doc{ext}"
    f.write_text(BIG, encoding="utf-8")
    units = expand_oversized_files([f], _FILE_CHAR_CAP)
    assert len(units) > 1, f"{ext} was not sliced; its tail never reaches the model"
    # The slices tile the file exactly — no gap, no overlap, nothing dropped.
    assert "".join(read_slice_text(u) for u in units) == BIG


# ---------------------------------------------------------------------------
# Slicing itself is unchanged for the types that already worked
# ---------------------------------------------------------------------------

def test_a_small_document_is_still_passed_through_whole(tmp_path):
    f = tmp_path / "small.qmd"
    f.write_text("# tiny\n\nnothing to slice\n", encoding="utf-8")
    units = expand_oversized_files([f], _FILE_CHAR_CAP)
    assert units == [f], "a file under the cap must pass through as a plain Path"


def test_image_documents_are_not_sliced(tmp_path):
    """An image has no addressable text, so it can never be sliced and must pass
    through untouched. (A PDF, by contrast, is now sliced through its converter —
    #2906 — so the old assertion that PDFs are unsplittable no longer holds; the
    unreadable-PDF passthrough case is covered in test_pdf_slicing.py.)"""
    f = tmp_path / "diagram.png"
    f.write_bytes(b"\x89PNG\r\n\x1a\n" + b"x" * 40_000)
    assert not is_splittable_text(f)
    assert expand_oversized_files([f], _FILE_CHAR_CAP) == [f]


def test_code_files_are_still_not_sliced(tmp_path):
    f = tmp_path / "mod.py"
    f.write_text("def f():\n    pass\n" * 4000, encoding="utf-8")
    assert not is_splittable_text(f)
    assert expand_oversized_files([f], _FILE_CHAR_CAP) == [f]


def test_slices_stay_within_the_cap(tmp_path):
    for start, end in slice_boundaries(BIG, _FILE_CHAR_CAP):
        assert end - start <= _FILE_CHAR_CAP


# ---------------------------------------------------------------------------
# End to end through the prompt builder
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("ext", [".qmd", ".html", ".yaml", ".yml", ".skill"])
def test_the_tail_of_a_big_document_reaches_the_prompt(tmp_path, ext):
    """The symptom a user would notice: content past 20k was invisible to the
    semantic pass, so nothing in the tail could ever become a node."""
    marker = "UNIQUE_TAIL_MARKER_XYZZY"
    f = tmp_path / f"doc{ext}"
    f.write_text(BIG + "\n\n" + marker + "\n", encoding="utf-8")
    units = expand_oversized_files([f], _FILE_CHAR_CAP)
    joined = "".join(_read_files([u], tmp_path) for u in units)
    assert marker in joined
