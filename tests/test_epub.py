import json
"""Tests for the EPUB semantic ingestion module.

Includes synthetic EPUB fixtures to verify full semantic extraction:
- chapter order from spine
- text + titles
- media (images/audio/video) extraction and routing
- manifest structure
- safety limits
- error handling
"""

import tempfile
import zipfile
from pathlib import Path

import pytest

from graphify.epub import (
    EpubError,
    EpubLimits,
    convert_epub_file,
    cleanup_orphaned_epub_bundles,
)


def _make_minimal_epub(
    tmp: Path,
    *,
    title: str = "Test Book",
    chapters: list[tuple[str, str, list[str]]] | None = None,
) -> Path:
    """Create a minimal valid EPUB in tmp and return the .epub path."""
    if chapters is None:
        chapters = [
            ("chap1", "Chapter One", "<h1>Hello</h1><p>First chapter with <img src=\"img1.png\"/></p>"),
            ("chap2", "Chapter Two", "<h1>World</h1><p>Second with audio <audio src=\"sound.mp3\"/></p>"),
        ]

    epub_path = tmp / "test.epub"
    with zipfile.ZipFile(epub_path, "w") as z:
        # mimetype first, uncompressed
        z.writestr("mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED)

        z.writestr(
            "META-INF/container.xml",
            """<?xml version="1.0"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="content.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>""",
        )

        # Build manifest items
        manifest_items = ['<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>']
        spine_items = []
        for cid, ctitle, body in chapters:
            manifest_items.append(f'<item id="{cid}" href="{cid}.xhtml" media-type="application/xhtml+xml"/>')
            spine_items.append(f'<itemref idref="{cid}"/>')

        # content.opf with metadata
        opf = f"""<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf" unique-identifier="BookId" version="3.0">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:title>{title}</dc:title>
    <dc:creator>Test Author</dc:creator>
    <dc:language>en</dc:language>
  </metadata>
  <manifest>
    {''.join(manifest_items)}
  </manifest>
  <spine>
    {''.join(spine_items)}
  </spine>
</package>"""
        z.writestr("content.opf", opf)

        # chapters
        for cid, ctitle, body in chapters:
            xhtml = f"""<?xml version="1.0"?>
<html xmlns="http://www.w3.org/1999/xhtml">
<head><title>{ctitle}</title></head>
<body>{body}</body>
</html>"""
            z.writestr(f"{cid}.xhtml", xhtml)

        # fake media
        z.writestr("img1.png", b"\x89PNG\r\n\x1a\n" + b"\x00" * 20)
        z.writestr("end.png", b"\x89PNG\r\n\x1a\n" + b"\x00" * 20)
        z.writestr("sound.mp3", b"ID3" + b"\x00" * 100)

    return epub_path


def test_epub_limits_and_policy():
    limits = EpubLimits()
    assert limits.max_chapters >= 1
    policy = limits.as_policy()
    assert isinstance(policy, dict)
    assert "max_raw_bytes" in policy


def test_epub_convert_nonexistent_raises():
    with pytest.raises((EpubError, FileNotFoundError, OSError)):
        convert_epub_file(Path("/non/existent.epub"), Path("/tmp"))


def test_epub_basic_extraction(tmp_path):
    epub_path = _make_minimal_epub(tmp_path)
    out_dir = tmp_path / "out"
    art = convert_epub_file(epub_path, out_dir)

    assert art.markdown_path.exists()
    md = art.markdown_path.read_text()
    assert "Hello" in md
    assert "World" in md
    assert "Chapter One" in md or "Chapter Two" in md

    # Media
    assert len(art.images) >= 1
    assert any("img1" in str(p) for p in art.images)
    assert len(art.media) >= 1
    assert any("sound" in str(p) for p in art.media)

    # Manifest
    assert art.manifest_path.exists()
    manifest = json.loads(art.manifest_path.read_text())
    assert manifest["metadata"]["title"] == "Test Book"
    assert len(manifest["chapters"]) == 2
    assert manifest["chapters"][0]["title"]
    assert any(a["kind"] == "image" for a in manifest["assets"])


def test_epub_chapter_order_and_titles(tmp_path):
    chapters = [
        ("c1", "Intro", "<h1>Introduction</h1><p>intro text</p>"),
        ("c2", "Middle", "<h1>Middle Chapter</h1>"),
        ("c3", "End", "<h1>Conclusion</h1><img src=\"end.png\"/>"),
    ]
    epub_path = _make_minimal_epub(tmp_path, chapters=chapters)
    art = convert_epub_file(epub_path, tmp_path / "out2")

    manifest = json.loads(art.manifest_path.read_text())
    titles = [c["title"] for c in manifest["chapters"]]
    assert titles == ["Intro", "Middle", "End"]
    assert len(art.images) == 1


def test_epub_media_routing(tmp_path):
    epub_path = _make_minimal_epub(tmp_path)
    art = convert_epub_file(epub_path, tmp_path / "out3")

    # Images should be images, mp3 as media (video/audio bucket)
    assert all("img" in p.name or p.suffix in {".png"} for p in art.images)
    assert any(p.suffix in {".mp3"} for p in art.media)


def test_epub_error_on_bad_zip(tmp_path):
    bad = tmp_path / "bad.epub"
    bad.write_bytes(b"not a zip at all")
    with pytest.raises(EpubError):
        convert_epub_file(bad, tmp_path / "out")


def test_cleanup_function_does_not_crash(tmp_path):
    # Just ensure it runs without error on empty dir
    cleanup_orphaned_epub_bundles(tmp_path / "converted", root=tmp_path)
    assert True


def test_epub_module_symbols():
    import graphify.epub as epub_mod
    assert hasattr(epub_mod, "convert_epub_file")
    assert hasattr(epub_mod, "EpubArtifacts")
    assert hasattr(epub_mod, "EpubLimits")
    assert hasattr(epub_mod, "cleanup_orphaned_epub_bundles")
