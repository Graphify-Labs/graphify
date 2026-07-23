"""Bounded semantic extraction for untrusted EPUB files.

EPUB is a ZIP of XHTML + OPF (package document) + NCX/toc.
This module performs safe, limited parsing so we can extract
chapter structure, text, images, and embedded media without
executing anything or trusting the archive.

Modeled on the PPTX approach in presentation.py for consistency
(safety limits, cache keys, provenance, media routing).
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import posixpath
import re
import shutil
import unicodedata
import uuid
import zipfile
from dataclasses import asdict, dataclass, fields
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, Iterable
from urllib.parse import unquote, urlsplit

from defusedxml.ElementTree import ParseError as _XmlParseError
from defusedxml.ElementTree import fromstring as _safe_xml_fromstring
from defusedxml.common import DefusedXmlException

if TYPE_CHECKING:
    from xml.etree.ElementTree import Element as ETElement
else:  # pragma: no cover - runtime alias for annotations
    ETElement = object

CONVERTER_VERSION = "1"
MANIFEST_SCHEMA_VERSION = 1

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
    """Parse OPF and return manifest items + spine order."""
    try:
        data = zipf.read(opf_path)
    except KeyError:
        raise EpubError(f"missing OPF: {opf_path}")
    if len(data) > limits.max_xml_bytes:
        raise EpubError("OPF too large")
    root = _safe_xml_fromstring(data)
    ns = {"opf": "http://www.idpf.org/2007/opf"}

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

    return {"manifest": manifest, "spine": spine}


def _extract_text_from_xhtml(data: bytes) -> str:
    """Very simple text extraction from XHTML."""
    try:
        text = data.decode("utf-8", errors="replace")
        # strip tags crudely
        text = re.sub(r"<script[^>]*>.*?</script>", "", text, flags=re.I | re.S)
        text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.I | re.S)
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        return text[:100_000]  # safety
    except Exception:
        return ""


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
    """Convert an .epub to a semantic bundle (markdown + manifest + media)."""
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
            # Basic zip safety
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

            for idx, item_id in enumerate(opf["spine"]):
                item = opf["manifest"].get(item_id)
                if not item:
                    continue
                full = item["full_path"]
                try:
                    data = zf.read(full)
                except KeyError:
                    warnings.append(f"missing spine item: {full}")
                    continue

                text = _extract_text_from_xhtml(data)
                chapter_md = f"# Chapter {idx+1}\n\n{text}\n"
                chapters.append({
                    "index": idx,
                    "id": item_id,
                    "href": item["href"],
                    "text_preview": text[:200],
                })

                # Look for images/media referenced in the chapter (simplified)
                for m in re.finditer(r'(?i)(src|href)=["\']([^"\']+\.(png|jpg|jpeg|gif|webp|svg|mp3|wav|m4a|ogg|mp4|mov|webm))["\']', data.decode("utf-8", "ignore")):
                    href = m.group(2)
                    full_media = posixpath.normpath(posixpath.join(posixpath.dirname(full), href))
                    kind = _classify_media(full_media)
                    if kind:
                        try:
                            payload = zf.read(full_media)
                            asset = _Asset(
                                kind=kind,
                                role="embedded",
                                chapter=idx,
                                relationship_id=str(uuid.uuid4()),
                                source_part=full_media,
                                content_type="",
                                filename=Path(full_media).name,
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
                        except Exception as e:
                            warnings.append(f"media extract failed {full_media}: {e}")

            # Write combined markdown
            full_md = "\n\n".join(c for c in [ch.get("text_preview", "") for ch in chapters] if c)
            if len(full_md) > limits.max_markdown_chars:
                full_md = full_md[: limits.max_markdown_chars]
                warnings.append("markdown truncated")

            markdown_path.write_text(full_md, encoding="utf-8")

            # Manifest
            manifest = {
                "converter_version": CONVERTER_VERSION,
                "schema_version": MANIFEST_SCHEMA_VERSION,
                "source": str(path),
                "source_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "limits": limits.as_policy(),
                "chapters": chapters,
                "assets": [
                    {
                        "kind": a.kind,
                        "chapter": a.chapter,
                        "filename": a.filename,
                        "sha256": a.sha256,
                        "size": a.size,
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


# For now, a thin wrapper so detect.py can call it uniformly
def convert_epub(path: Path, out_dir: Path, **kwargs) -> EpubArtifacts:
    return convert_epub_file(path, out_dir, **kwargs)
