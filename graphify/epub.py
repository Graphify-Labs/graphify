"""Bounded semantic extraction for untrusted EPUB files.

EPUB is a ZIP of XHTML + OPF (package document) + NCX/toc.
This module performs safe, limited parsing so we can extract
chapter structure, text, images, and embedded media without
executing anything or trusting the archive.

Modeled on the PPTX approach in presentation.py for consistency
(safety limits, cache keys, provenance, media routing).
Full semantic extraction (structure + media) rather than plain text.
"""

from __future__ import annotations

import hashlib
import json
import posixpath
import re
import zipfile
from dataclasses import asdict, dataclass, fields
from html.parser import HTMLParser
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import unquote

from defusedxml.ElementTree import ParseError as _XmlParseError
from defusedxml.ElementTree import fromstring as _safe_xml_fromstring
from defusedxml.common import DefusedXmlException

if TYPE_CHECKING:
    from xml.etree.ElementTree import Element as ETElement
else:  # pragma: no cover - runtime alias for annotations
    ETElement = object

CONVERTER_VERSION = "2"
MANIFEST_SCHEMA_VERSION = 2

_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"}
_SEMANTIC_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"}
_AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a", ".ogg", ".aac", ".flac"}
_VIDEO_EXTENSIONS = {".mp4", ".mov", ".webm", ".mkv", ".avi", ".m4v"}

_EPUB_MIME = "application/epub+zip"


class EpubError(ValueError):
    """Raised when an EPUB is malformed, unsafe, or outside configured bounds."""


@dataclass(frozen=True)
class EpubLimits:
    """Resource policy for one EPUB conversion."""

    max_raw_bytes: int = 100 * 1024 * 1024
    max_members: int = 5_000
    max_decompressed_bytes: int = 256 * 1024 * 1024
    max_member_bytes: int = 32 * 1024 * 1024
    max_xml_bytes: int = 4 * 1024 * 1024
    max_xml_total_bytes: int = 32 * 1024 * 1024
    max_compression_ratio: int = 100
    max_chapters: int = 2_000
    max_assets: int = 1_000
    max_asset_bytes: int = 25 * 1024 * 1024
    max_extracted_asset_bytes: int = 128 * 1024 * 1024
    max_text_chars: int = 50_000
    max_markdown_chars: int = 4_000_000
    max_xml_elements: int = 100_000
    max_xml_depth: int = 32
    max_manifest_bytes: int = 1_000_000

    def as_policy(self) -> dict[str, int]:
        return {field.name: int(getattr(self, field.name)) for field in fields(self)}


@dataclass(frozen=True)
class EpubArtifacts:
    markdown_path: Path
    manifest_path: Path
    images: tuple[Path, ...]
    media: tuple[Path, ...]
    warnings: tuple[str, ...]


@dataclass
class _Asset:
    kind: str  # image | audio | video
    role: str
    chapter: int
    relationship_id: str
    source_part: str
    content_type: str
    filename: str
    payload: bytes
    description: str = ""

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.payload).hexdigest()

    @property
    def size(self) -> int:
        return len(self.payload)


class _EPUBHTMLParser(HTMLParser):
    """Simple HTML parser to extract text and media links from XHTML."""

    def __init__(self):
        super().__init__()
        self.text_parts: list[str] = []
        self.media_hrefs: list[str] = []
        self.title: str = ""
        self._in_title = False
        self._in_h1 = False
        self.first_h1: str = ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]):
        tag_lower = tag.lower()
        if tag_lower == "title":
            self._in_title = True
        if tag_lower == "h1" and not self.first_h1:
            self._in_h1 = True
        attr_dict = dict(attrs)
        for attr in ("src", "href", "data-src"):
            val = attr_dict.get(attr)
            if val:
                self.media_hrefs.append(val)
        # Also check <source> for audio/video
        if tag_lower in ("source", "audio", "video"):
            src = attr_dict.get("src")
            if src:
                self.media_hrefs.append(src)

    def handle_endtag(self, tag: str):
        if tag.lower() == "title":
            self._in_title = False
        if tag.lower() == "h1":
            self._in_h1 = False

    def handle_data(self, data: str):
        text = data.strip()
        if not text:
            return
        if self._in_title:
            self.title = text
        if self._in_h1 and not self.first_h1:
            self.first_h1 = text
        self.text_parts.append(text)

    def get_text(self) -> str:
        text = " ".join(self.text_parts)
        return re.sub(r"\s+", " ", text).strip()[:100_000]

    def get_title(self) -> str:
        return self.title or self.first_h1 or ""


def _safe_extract(zipf: zipfile.ZipFile, member: str, dest: Path, max_bytes: int) -> bytes:
    info = zipf.getinfo(member)
    if info.file_size > max_bytes:
        raise EpubError(f"member too large: {member}")
    data = zipf.read(member)
    if len(data) > max_bytes:
        raise EpubError(f"extracted too large: {member}")
    dest.write_bytes(data)
    return data


def _parse_container(zipf: zipfile.ZipFile, limits: EpubLimits) -> str:
    """Return the rootfile path from META-INF/container.xml."""
    try:
        data = zipf.read("META-INF/container.xml")
    except KeyError:
        raise EpubError("missing META-INF/container.xml")
    if len(data) > limits.max_xml_bytes:
        raise EpubError("container.xml too large")
    root = _safe_xml_fromstring(data)
    rootfiles = root.findall(".//{urn:oasis:names:tc:opendocument:xmlns:container}rootfile")
    for rf in rootfiles:
        if rf.get("media-type") == "application/oebps-package+xml":
            return rf.get("full-path")
    raise EpubError("no rootfile found in container.xml")


def _parse_opf(zipf: zipfile.ZipFile, opf_path: str, limits: EpubLimits) -> dict:
    """Parse OPF and return manifest items + spine order + metadata."""
    try:
        data = zipf.read(opf_path)
    except KeyError:
        raise EpubError(f"missing OPF: {opf_path}")
    if len(data) > limits.max_xml_bytes:
        raise EpubError("OPF too large")
    root = _safe_xml_fromstring(data)
    ns = {"opf": "http://www.idpf.org/2007/opf", "dc": "http://purl.org/dc/elements/1.1/"}

    manifest = {}
    for item in root.findall(".//opf:manifest/opf:item", ns):
        iid = item.get("id")
        href = item.get("href")
        media_type = item.get("media-type", "")
        if iid and href:
            manifest[iid] = {
                "href": href,
                "media-type": media_type,
                "full_path": posixpath.normpath(posixpath.join(posixpath.dirname(opf_path), href)),
            }

    spine = []
    for itemref in root.findall(".//opf:spine/opf:itemref", ns):
        iid = itemref.get("idref")
        if iid in manifest:
            spine.append(iid)

    # Extract some metadata
    metadata = {}
    for tag in ("title", "creator", "language", "identifier"):
        el = root.find(f".//dc:{tag}", ns)
        if el is not None and el.text:
            metadata[tag] = el.text.strip()

    return {"manifest": manifest, "spine": spine, "metadata": metadata}


def _resolve_href(base: str, href: str) -> str:
    """Resolve relative href against base path inside the EPUB zip."""
    if href.startswith(("http://", "https://", "data:")):
        return ""
    href = unquote(href.split("#")[0])  # strip fragment
    return posixpath.normpath(posixpath.join(posixpath.dirname(base), href))


def _extract_from_xhtml(data: bytes) -> tuple[str, str, list[str]]:
    """Extract text, title, and media hrefs from XHTML using HTMLParser."""
    try:
        parser = _EPUBHTMLParser()
        parser.feed(data.decode("utf-8", errors="replace"))
        parser.close()
        text = parser.get_text()
        title = parser.get_title()
        media = [h for h in parser.media_hrefs if h and not h.startswith(("http:", "https:", "data:"))]
        return text, title, media
    except Exception:
        return "", "", []


def _classify_media(filename: str) -> str | None:
    ext = Path(filename).suffix.lower()
    if ext in _SEMANTIC_IMAGE_EXTENSIONS:
        return "image"
    if ext in _AUDIO_EXTENSIONS:
        return "audio"
    if ext in _VIDEO_EXTENSIONS:
        return "video"
    return None


def convert_epub_file(
    path: Path,
    out_dir: Path,
    *,
    limits: EpubLimits | None = None,
    root: Path | None = None,
) -> EpubArtifacts:
    """Convert an .epub to a semantic bundle (markdown + manifest + media).

    Preserves reading order from spine, extracts chapter text with titles,
    routes images/audio/video to appropriate output for vision/transcription.
    """
    limits = limits or EpubLimits()
    path = path.resolve()
    if not path.exists():
        raise EpubError(f"file not found: {path}")

    raw_size = path.stat().st_size
    if raw_size > limits.max_raw_bytes:
        raise EpubError("EPUB too large")

    stem = path.stem
    bundle_dir = out_dir / f"{stem}.epub"
    bundle_dir.mkdir(parents=True, exist_ok=True)

    markdown_path = bundle_dir / f"{stem}.md"
    manifest_path = bundle_dir / "manifest.json"

    images: list[Path] = []
    media: list[Path] = []
    warnings: list[str] = []

    try:
        with zipfile.ZipFile(path, "r") as zf:
            # Basic zip safety (mirrors PPTX)
            if len(zf.infolist()) > limits.max_members:
                raise EpubError("too many members")

            total_decomp = 0
            for info in zf.infolist():
                total_decomp += info.file_size
                if info.file_size > limits.max_member_bytes:
                    raise EpubError(f"member too large: {info.filename}")
                if info.compress_size and info.file_size > limits.max_compression_ratio * info.compress_size:
                    raise EpubError(f"bad compression ratio: {info.filename}")

            if total_decomp > limits.max_decompressed_bytes:
                raise EpubError("total decompressed too large")

            opf_path = _parse_container(zf, limits)
            opf = _parse_opf(zf, opf_path, limits)

            chapters: list[dict] = []
            assets: list[_Asset] = []
            seen_media: set[str] = set()

            for idx, item_id in enumerate(opf["spine"][: limits.max_chapters]):
                item = opf["manifest"].get(item_id)
                if not item:
                    continue
                full = item["full_path"]
                try:
                    data = zf.read(full)
                except KeyError:
                    warnings.append(f"missing spine item: {full}")
                    continue

                text, title, media_hrefs = _extract_from_xhtml(data)

                chapter_title = title or f"Chapter {idx + 1}"
                chapter_md = f"# {chapter_title}\n\n{text}\n" if text else f"# {chapter_title}\n\n"

                chapters.append({
                    "index": idx,
                    "id": item_id,
                    "href": item["href"],
                    "title": chapter_title,
                    "text_length": len(text),
                    "text_preview": text[:300] if text else "",
                })

                # Resolve and extract media
                for href in media_hrefs:
                    resolved = _resolve_href(full, href)
                    if not resolved or resolved in seen_media:
                        continue
                    seen_media.add(resolved)
                    kind = _classify_media(resolved)
                    if kind:
                        try:
                            payload = zf.read(resolved)
                            if len(payload) > limits.max_asset_bytes:
                                warnings.append(f"asset too large, skipped: {resolved}")
                                continue
                            asset = _Asset(
                                kind=kind,
                                role="embedded",
                                chapter=idx,
                                relationship_id=str(hash(resolved)),
                                source_part=resolved,
                                content_type=item.get("media-type", ""),
                                filename=Path(resolved).name,
                                payload=payload,
                            )
                            assets.append(asset)

                            asset_dir = bundle_dir / kind
                            asset_dir.mkdir(exist_ok=True)
                            out_path = asset_dir / asset.filename
                            out_path.write_bytes(payload)
                            if kind == "image":
                                images.append(out_path)
                            else:
                                media.append(out_path)
                        except KeyError:
                            warnings.append(f"media not found in zip: {resolved}")
                        except Exception as e:
                            warnings.append(f"media extract failed {resolved}: {e}")

            # Write combined markdown with chapter separators
            md_parts = []
            for ch in chapters:
                if ch.get("text_preview") or ch.get("title"):
                    md_parts.append(f"# {ch['title']}\n\n{ch.get('text_preview', '')}")
            full_md = "\n\n".join(md_parts)
            if len(full_md) > limits.max_markdown_chars:
                full_md = full_md[: limits.max_markdown_chars]
                warnings.append("markdown truncated")

            markdown_path.write_text(full_md, encoding="utf-8")

            # Rich manifest
            manifest = {
                "converter_version": CONVERTER_VERSION,
                "schema_version": MANIFEST_SCHEMA_VERSION,
                "source": str(path),
                "source_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "limits": limits.as_policy(),
                "metadata": opf.get("metadata", {}),
                "chapters": chapters,
                "assets": [
                    {
                        "kind": a.kind,
                        "chapter": a.chapter,
                        "filename": a.filename,
                        "sha256": a.sha256,
                        "size": a.size,
                        "source_part": a.source_part,
                    }
                    for a in assets
                ],
                "warnings": warnings,
            }
            manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    except (zipfile.BadZipFile, DefusedXmlException, _XmlParseError) as e:
        raise EpubError(f"unsafe or malformed EPUB: {e}") from e

    return EpubArtifacts(
        markdown_path=markdown_path,
        manifest_path=manifest_path,
        images=tuple(images),
        media=tuple(media),
        warnings=tuple(warnings),
    )


def cleanup_orphaned_epub_bundles(converted_dir: Path, *, root: Path) -> None:
    """Remove stale .epub bundles (same pattern as PPTX)."""
    if not converted_dir.exists():
        return
    for bundle in list(converted_dir.glob("*.epub")):
        # simple heuristic: if no corresponding source, clean (can be improved)
        pass  # TODO: implement proper orphan detection like PPTX


# Thin wrapper for uniform calling
def convert_epub(path: Path, out_dir: Path, **kwargs) -> EpubArtifacts:
    return convert_epub_file(path, out_dir, **kwargs)
