"""Bounded semantic extraction for untrusted PowerPoint ``.pptx`` packages.

A presentation is converted into a content-versioned artifact bundle containing
structured Markdown plus extracted images, audio/video, and embedded files.  The
module reads OOXML directly so it can recover relationships and media that
``python-pptx`` does not expose, and it never executes or fetches package content.
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


CONVERTER_VERSION = "2"
MANIFEST_SCHEMA_VERSION = 2

_REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_PACKAGE_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
_CONTENT_TYPES_PART = "[Content_Types].xml"
_ROOT_RELS_PART = "_rels/.rels"

_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".bmp", ".tif", ".tiff"}
_SEMANTIC_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"}
_AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a", ".ogg", ".aac", ".wma", ".flac"}
_VIDEO_EXTENSIONS = {".mp4", ".mov", ".webm", ".mkv", ".avi", ".m4v", ".wmv", ".mpeg", ".mpg"}
_MIME_EXTENSIONS = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/gif": ".gif",
    "image/webp": ".webp",
    "image/svg+xml": ".svg",
    "image/bmp": ".bmp",
    "image/tiff": ".tiff",
    "audio/mpeg": ".mp3",
    "audio/mp4": ".m4a",
    "audio/wav": ".wav",
    "audio/x-wav": ".wav",
    "audio/ogg": ".ogg",
    "video/mp4": ".mp4",
    "video/quicktime": ".mov",
    "video/webm": ".webm",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
    "application/pdf": ".pdf",
}


class PresentationError(ValueError):
    """Raised when a presentation is malformed, unsafe, or outside configured bounds."""


@dataclass(frozen=True)
class PresentationLimits:
    """Resource policy for one PPTX conversion."""

    max_raw_bytes: int = 50 * 1024 * 1024
    max_members: int = 10_000
    max_decompressed_bytes: int = 512 * 1024 * 1024
    max_member_bytes: int = 64 * 1024 * 1024
    max_xml_bytes: int = 8 * 1024 * 1024
    max_xml_total_bytes: int = 64 * 1024 * 1024
    max_compression_ratio: int = 200
    max_slides: int = 1_000
    max_relationships_per_part: int = 2_000
    max_assets: int = 2_000
    max_asset_bytes: int = 50 * 1024 * 1024
    max_extracted_asset_bytes: int = 256 * 1024 * 1024
    max_text_chars: int = 20_000
    max_markdown_chars: int = 2_000_000
    max_external_target_chars: int = 4_096
    max_xml_elements: int = 250_000
    max_xml_depth: int = 64
    max_manifest_bytes: int = 2_000_000

    def as_policy(self) -> dict[str, int]:
        """Stable policy dict used for cache identity and verification."""
        return {field.name: int(getattr(self, field.name)) for field in fields(self)}


@dataclass(frozen=True)
class PresentationArtifacts:
    markdown_path: Path
    manifest_path: Path
    images: tuple[Path, ...]
    media: tuple[Path, ...]
    attachments: tuple[Path, ...]
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class _Relationship:
    relationship_id: str
    relationship_type: str
    target: str
    external: bool
    resolved_target: str | None

    @property
    def kind(self) -> str:
        return self.relationship_type.rstrip("/").rsplit("/", 1)[-1].lower()


@dataclass
class _Asset:
    kind: str
    role: str
    slide: int
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


@dataclass
class _Extraction:
    markdown: str
    assets: list[_Asset]
    slides: list[dict]
    warnings: list[str]
    presentation_part: str


class _Package:
    def __init__(self, raw: bytes, limits: PresentationLimits):
        self.raw = raw
        self.limits = limits
        self.archive = zipfile.ZipFile(io.BytesIO(raw))
        self.infos: dict[str, zipfile.ZipInfo] = {}
        self.xml_bytes_read = 0
        self.asset_bytes_read = 0
        self._validate_archive()
        self.content_types = self._load_content_types()

    def close(self) -> None:
        self.archive.close()

    def _validate_archive(self) -> None:
        infos = self.archive.infolist()
        if len(infos) > self.limits.max_members:
            raise PresentationError(
                f"PPTX has {len(infos)} archive members; limit is {self.limits.max_members} members"
            )
        declared_total = 0
        compressed_total = 0
        for info in infos:
            name = info.filename
            if not _safe_member_name(name):
                raise PresentationError(f"unsafe PPTX archive member name: {name!r}")
            if name in self.infos:
                raise PresentationError(f"duplicate PPTX archive member: {name!r}")
            if info.flag_bits & 0x1:
                raise PresentationError(f"encrypted PPTX archive member is not supported: {name!r}")
            if info.file_size > self.limits.max_member_bytes:
                raise PresentationError(
                    f"PPTX member {name!r} declares {info.file_size} bytes; "
                    f"per-member limit is {self.limits.max_member_bytes}"
                )
            declared_total += info.file_size
            compressed_total += info.compress_size
            self.infos[name] = info
        if declared_total > self.limits.max_decompressed_bytes:
            raise PresentationError(
                f"PPTX declares {declared_total} decompressed bytes; "
                f"limit is {self.limits.max_decompressed_bytes}"
            )
        if (
            declared_total
            and declared_total / max(compressed_total, 1) > self.limits.max_compression_ratio
        ):
            raise PresentationError("PPTX compression ratio exceeds the configured safety limit")
        if _CONTENT_TYPES_PART not in self.infos or _ROOT_RELS_PART not in self.infos:
            raise PresentationError("not a PPTX package: required presentation parts are missing")

    def read_member(self, name: str, *, cap: int | None = None, asset: bool = False) -> bytes:
        info = self.infos.get(name)
        if info is None:
            raise PresentationError(f"PPTX relationship target is missing: {name}")
        ceiling = min(cap or self.limits.max_member_bytes, self.limits.max_member_bytes)
        chunks: list[bytes] = []
        total = 0
        try:
            with self.archive.open(info) as member:
                while True:
                    chunk = member.read(min(1024 * 1024, ceiling + 1 - total))
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > ceiling:
                        raise PresentationError(
                            f"PPTX member {name!r} exceeds the {ceiling}-byte extraction limit"
                        )
                    chunks.append(chunk)
        except (zipfile.BadZipFile, EOFError, RuntimeError, OSError) as exc:
            raise PresentationError(f"could not read PPTX member {name!r}: {exc}") from exc
        if asset:
            self.asset_bytes_read += total
            if self.asset_bytes_read > self.limits.max_extracted_asset_bytes:
                raise PresentationError(
                    "PPTX extracted assets exceed the configured total byte limit"
                )
        return b"".join(chunks)

    def parse_xml(self, name: str) -> ETElement:
        data = self.read_member(name, cap=self.limits.max_xml_bytes)
        self.xml_bytes_read += len(data)
        if self.xml_bytes_read > self.limits.max_xml_total_bytes:
            raise PresentationError("PPTX XML parts exceed the configured total byte limit")
        # Reject DTDs/entities before parse. Byte-pattern screening alone is not
        # enough: UTF-16 / UTF-32 payloads hide ASCII markers. defusedxml forbids
        # entities and external resolution for every encoding it can decode.
        try:
            root = _safe_xml_fromstring(
                data,
                forbid_dtd=True,
                forbid_entities=True,
                forbid_external=True,
            )
        except DefusedXmlException as exc:
            raise PresentationError(
                f"DTD/entity declarations are forbidden in PPTX XML: {name}"
            ) from exc
        except _XmlParseError as exc:
            raise PresentationError(f"malformed PPTX XML in {name}: {exc}") from exc
        except (LookupError, UnicodeError, ValueError, TypeError) as exc:
            raise PresentationError(f"unreadable PPTX XML encoding in {name}: {exc}") from exc
        _enforce_xml_bounds(root, name, self.limits)
        return root

    def _load_content_types(self) -> tuple[dict[str, str], dict[str, str]]:
        root = self.parse_xml(_CONTENT_TYPES_PART)
        defaults: dict[str, str] = {}
        overrides: dict[str, str] = {}
        for element in root:
            local = _local(element.tag)
            if local == "Default":
                defaults[element.attrib.get("Extension", "").lower()] = element.attrib.get(
                    "ContentType", "application/octet-stream"
                )
            elif local == "Override":
                name = element.attrib.get("PartName", "").lstrip("/")
                if name:
                    overrides[name] = element.attrib.get("ContentType", "application/octet-stream")
        return defaults, overrides

    def content_type(self, part: str) -> str:
        defaults, overrides = self.content_types
        if part in overrides:
            return overrides[part]
        extension = PurePosixPath(part).suffix.lstrip(".").lower()
        return defaults.get(extension, "application/octet-stream")


class _Markdown:
    def __init__(self, limit: int):
        self.limit = limit
        self.parts: list[str] = []
        self.size = 0
        self.truncated = False

    def add(self, block: str) -> None:
        block = block.strip("\n")
        if not block or self.truncated:
            return
        rendered = block + "\n\n"
        if self.size + len(rendered) <= self.limit:
            self.parts.append(rendered)
            self.size += len(rendered)
            return
        notice = "\n\n> [!WARNING]\n> Presentation Markdown truncated at a safe section boundary.\n"
        room = self.limit - self.size
        if room >= len(notice):
            self.parts.append(notice)
            self.size += len(notice)
        self.truncated = True

    def render(self) -> str:
        return "".join(self.parts).rstrip() + "\n"


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _safe_member_name(name: str) -> bool:
    if not name or "\x00" in name or "\\" in name or name.startswith("/"):
        return False
    path = PurePosixPath(name)
    return not path.is_absolute() and all(part not in {"", ".", ".."} for part in path.parts)


def _read_source(path: Path, limit: int) -> bytes:
    try:
        with path.open("rb") as source:
            chunks: list[bytes] = []
            total = 0
            while True:
                chunk = source.read(min(1024 * 1024, limit + 1 - total))
                if not chunk:
                    break
                total += len(chunk)
                if total > limit:
                    raise PresentationError(
                        f"PPTX source exceeds the configured {limit}-byte raw input limit"
                    )
                chunks.append(chunk)
    except PresentationError:
        raise
    except OSError as exc:
        raise PresentationError(f"could not read PPTX source {path}: {exc}") from exc
    return b"".join(chunks)


def _rels_part(part: str) -> str:
    directory, name = posixpath.split(part)
    return posixpath.join(directory, "_rels", name + ".rels")


def _resolve_target(source_part: str, target: str) -> str | None:
    decoded = unquote(target)
    parsed = urlsplit(decoded)
    if parsed.scheme or parsed.netloc:
        return None
    decoded = parsed.path
    if not decoded or "\x00" in decoded or "\\" in decoded or decoded.startswith("/"):
        return None
    resolved = posixpath.normpath(posixpath.join(posixpath.dirname(source_part), decoded))
    if resolved == ".." or resolved.startswith("../") or not _safe_member_name(resolved):
        return None
    return resolved


def _relationships(package: _Package, part: str) -> dict[str, _Relationship]:
    rels_name = _rels_part(part)
    if rels_name not in package.infos:
        return {}
    root = package.parse_xml(rels_name)
    children = [element for element in root if _local(element.tag) == "Relationship"]
    if len(children) > package.limits.max_relationships_per_part:
        raise PresentationError(
            f"PPTX part {part!r} exceeds the relationship limit of "
            f"{package.limits.max_relationships_per_part}"
        )
    relationships: dict[str, _Relationship] = {}
    for element in children:
        relationship_id = element.attrib.get("Id", "")
        relationship_type = element.attrib.get("Type", "")
        target = element.attrib.get("Target", "")
        if not relationship_id or relationship_id in relationships:
            raise PresentationError(f"missing or duplicate relationship ID in {_rels_part(part)}")
        external = element.attrib.get("TargetMode", "").lower() == "external"
        resolved = None if external else _resolve_target(part, target)
        relationships[relationship_id] = _Relationship(
            relationship_id, relationship_type, target, external, resolved
        )
    return relationships


def _relationship_attr(element: ETElement, local_name: str) -> str | None:
    exact = f"{{{_REL_NS}}}{local_name}"
    if exact in element.attrib:
        return element.attrib[exact]
    for key, value in element.attrib.items():
        if _local(key) == local_name and key.startswith("{"):
            return value
    return None


def _first(element: ETElement, local_name: str) -> ETElement | None:
    return next((item for item in element.iter() if _local(item.tag) == local_name), None)


def _children(element: ETElement, local_name: str) -> list[ETElement]:
    return [item for item in element if _local(item.tag) == local_name]


def _clean_text(value: str | None, limit: int) -> str:
    if not value:
        return ""
    value = value.replace("\x00", "�").replace("\r\n", "\n").replace("\r", "\n")
    value = "".join(char for char in value if char in "\n\t" or ord(char) >= 32)
    value = re.sub(r"[ \t]+", " ", value).strip()
    if len(value) > limit:
        return value[: max(0, limit - 15)] + "… [truncated]"
    return value


def _all_text(element: ETElement, limit: int) -> str:
    values = [item.text or "" for item in element.iter() if _local(item.tag) in {"t", "text"}]
    return _clean_text(" ".join(value for value in values if value), limit)


def _paragraphs(element: ETElement, limit: int) -> list[tuple[int, str, list[str]]]:
    paragraphs: list[tuple[int, str, list[str]]] = []
    for paragraph in (item for item in element.iter() if _local(item.tag) == "p"):
        pieces: list[str] = []
        links: list[str] = []
        for item in paragraph.iter():
            local = _local(item.tag)
            if local == "t" and item.text:
                pieces.append(item.text)
            elif local == "br":
                pieces.append("\n")
            elif local in {"hlinkClick", "hlinkMouseOver"}:
                relationship_id = _relationship_attr(item, "id")
                if relationship_id:
                    links.append(relationship_id)
        text = _clean_text("".join(pieces), limit)
        if not text:
            continue
        properties = next(
            (item for item in paragraph if _local(item.tag) in {"pPr", "endParaRPr"}), None
        )
        try:
            level = int(properties.attrib.get("lvl", "0")) if properties is not None else 0
        except ValueError:
            level = 0
        paragraphs.append((max(0, min(level, 8)), text, links))
    return paragraphs


def _shape_metadata(shape: ETElement, limit: int) -> dict[str, str]:
    properties = _first(shape, "cNvPr")
    result = {"id": "", "name": "", "description": "", "title": "", "placeholder": ""}
    if properties is not None:
        result.update(
            {
                "id": properties.attrib.get("id", ""),
                "name": _clean_text(properties.attrib.get("name"), limit),
                "description": _clean_text(properties.attrib.get("descr"), limit),
                "title": _clean_text(properties.attrib.get("title"), limit),
            }
        )
    placeholder = _first(shape, "ph")
    if placeholder is not None:
        result["placeholder"] = placeholder.attrib.get("type", "body")
    transform = _first(shape, "xfrm")
    if transform is not None:
        offset = next((item for item in transform if _local(item.tag) == "off"), None)
        extent = next((item for item in transform if _local(item.tag) == "ext"), None)
        if offset is not None:
            result["x"] = offset.attrib.get("x", "")
            result["y"] = offset.attrib.get("y", "")
        if extent is not None:
            result["width"] = extent.attrib.get("cx", "")
            result["height"] = extent.attrib.get("cy", "")
    return result


def _walk_shapes(tree: ETElement) -> Iterable[ETElement]:
    shape_tags = {"sp", "pic", "graphicFrame", "cxnSp", "grpSp", "oleObj", "contentPart"}
    for child in tree:
        local = _local(child.tag)
        if local not in shape_tags:
            continue
        yield child
        if local == "grpSp":
            yield from _walk_shapes(child)


def _used_relationship_ids(element: ETElement, known: set[str]) -> set[str]:
    used: set[str] = set()
    for item in element.iter():
        for value in item.attrib.values():
            if value in known:
                used.add(value)
    return used


def _markdown_table(rows: list[list[str]]) -> str:
    if not rows:
        return ""
    width = max(len(row) for row in rows)
    normalized = [row + [""] * (width - len(row)) for row in rows]

    def escape(value: str) -> str:
        return value.replace("\\", "\\\\").replace("|", "\\|").replace("\n", "<br>")

    lines = ["| " + " | ".join(escape(cell) for cell in normalized[0]) + " |"]
    lines.append("| " + " | ".join("---" for _ in range(width)) + " |")
    lines.extend("| " + " | ".join(escape(cell) for cell in row) + " |" for row in normalized[1:])
    return "\n".join(lines)


def _chart_values(container: ETElement | None, limit: int) -> list[str]:
    if container is None:
        return []
    points: list[tuple[int, str]] = []
    for point in (item for item in container.iter() if _local(item.tag) == "pt"):
        value_element = next((item for item in point if _local(item.tag) in {"v", "f"}), None)
        if value_element is None:
            value_element = _first(point, "v")
        value = _clean_text(value_element.text if value_element is not None else "", limit)
        try:
            index = int(point.attrib.get("idx", len(points)))
        except ValueError:
            index = len(points)
        points.append((index, value))
    if points:
        return [value for _, value in sorted(points)]
    return [
        _clean_text(item.text, limit)
        for item in container.iter()
        if _local(item.tag) == "v" and _clean_text(item.text, limit)
    ]


def _extract_chart(
    package: _Package, part: str, limits: PresentationLimits
) -> tuple[str, list[str]]:
    root = package.parse_xml(part)
    lines: list[str] = []
    title = next((item for item in root.iter() if _local(item.tag) == "title"), None)
    title_text = _all_text(title, limits.max_text_chars) if title is not None else ""
    if title_text:
        lines.append(f"**Chart title:** {title_text}")
    series_elements = [item for item in root.iter() if _local(item.tag) in {"ser", "series"}]
    for series_index, series in enumerate(series_elements, start=1):
        tx = next((item for item in series if _local(item.tag) == "tx"), None)
        name = _all_text(tx, limits.max_text_chars) if tx is not None else ""
        if not name and tx is not None:
            name = next(
                (
                    _clean_text(item.text, limits.max_text_chars)
                    for item in tx.iter()
                    if _local(item.tag) == "v" and item.text
                ),
                "",
            )
        name = name or f"Series {series_index}"
        category = next((item for item in series if _local(item.tag) in {"cat", "xVal"}), None)
        values = next(
            (item for item in series if _local(item.tag) in {"val", "yVal", "bubbleSize"}), None
        )
        categories = _chart_values(category, limits.max_text_chars)
        numeric = _chart_values(values, limits.max_text_chars)
        rows = [["Category", name]]
        length = max(len(categories), len(numeric))
        for index in range(length):
            rows.append(
                [
                    categories[index] if index < len(categories) else str(index + 1),
                    numeric[index] if index < len(numeric) else "",
                ]
            )
        lines.append(f"**Series:** {name}")
        if length:
            lines.append(_markdown_table(rows))
    if series_elements and all(_local(item.tag) == "series" for item in series_elements):
        # Office 2016+ extended charts can keep dimensions in a shared cx:data
        # area referenced by dataId rather than nesting cat/val under each series.
        # Preserve the bounded cached evidence even when a series-to-dimension
        # join is unavailable.
        cached_values: list[str] = []
        for element in root.iter():
            if _local(element.tag) not in {"v", "t"} or not element.text:
                continue
            value = _clean_text(element.text, limits.max_text_chars)
            if value and value not in cached_values:
                cached_values.append(value)
            if len(cached_values) >= 1_000:
                break
        if cached_values:
            lines.append(
                "**Extended-chart cached values:**\n"
                + "\n".join(f"- {value}" for value in cached_values)
            )
    attachment_parts: list[str] = []
    for relationship in _relationships(package, part).values():
        if relationship.kind in {"package", "oleobject"} and relationship.resolved_target:
            attachment_parts.append(relationship.resolved_target)
    return "\n\n".join(lines), attachment_parts


def _extract_diagram(package: _Package, part: str, limits: PresentationLimits) -> str:
    root = package.parse_xml(part)
    labels: dict[str, str] = {}
    for point in (item for item in root.iter() if _local(item.tag) == "pt"):
        model_id = point.attrib.get("modelId", "")
        text = _all_text(point, limits.max_text_chars)
        if model_id and text:
            labels[model_id] = text
    lines = [f"- Node `{model_id}`: {label}" for model_id, label in labels.items()]
    for connection in (item for item in root.iter() if _local(item.tag) == "cxn"):
        source = connection.attrib.get("srcId", "")
        target = connection.attrib.get("destId", "")
        if not source or not target:
            continue
        relation = connection.attrib.get("type", "connection")
        lines.append(f"- {labels.get(source, source)} -> {labels.get(target, target)} ({relation})")
    return "\n".join(lines)


def _core_properties(
    package: _Package, limits: PresentationLimits, core_part: str | None
) -> dict[str, str]:
    if not core_part or core_part not in package.infos:
        return {}
    root = package.parse_xml(core_part)
    allowed = {
        "title",
        "subject",
        "creator",
        "keywords",
        "description",
        "lastModifiedBy",
        "created",
        "modified",
        "category",
        "contentStatus",
    }
    properties: dict[str, str] = {}
    for element in root.iter():
        local = _local(element.tag)
        if local in allowed and element.text:
            properties[local] = _clean_text(element.text, limits.max_text_chars)
    return properties


def _comment_authors(
    package: _Package,
    limits: PresentationLimits,
    presentation_relationships: dict[str, _Relationship],
) -> dict[str, str]:
    authors: dict[str, str] = {}
    relationships = [
        relationship
        for relationship in presentation_relationships.values()
        if relationship.kind in {"commentauthors", "person", "persons"}
        and not relationship.external
        and relationship.resolved_target in package.infos
    ]
    for relationship in relationships:
        assert relationship.resolved_target is not None
        root = package.parse_xml(relationship.resolved_target)
        for element in root.iter():
            if _local(element.tag) not in {"cmAuthor", "person"}:
                continue
            identifier = (
                element.attrib.get("id")
                or element.attrib.get("authorId")
                or element.attrib.get("userId")
            )
            name = (
                element.attrib.get("name")
                or element.attrib.get("displayName")
                or element.attrib.get("initials")
            )
            if identifier and name:
                authors[identifier] = _clean_text(name, limits.max_text_chars)
    return authors


def _safe_extension(part: str, content_type: str, kind: str) -> str:
    suffix = PurePosixPath(part).suffix.lower()
    if not re.fullmatch(r"\.[a-z0-9]{1,10}", suffix):
        suffix = ""
    mapped = _MIME_EXTENSIONS.get(content_type.lower(), "")
    if kind == "image" and suffix not in _IMAGE_EXTENSIONS:
        suffix = mapped if mapped in _IMAGE_EXTENSIONS else ".bin"
    elif kind == "media" and suffix not in _AUDIO_EXTENSIONS | _VIDEO_EXTENSIONS:
        suffix = mapped if mapped in _AUDIO_EXTENSIONS | _VIDEO_EXTENSIONS else ".bin"
    elif kind == "attachment" and not suffix:
        suffix = mapped or ".bin"
    return suffix or ".bin"


def _valid_semantic_image(payload: bytes, extension: str) -> bool:
    if extension == ".png":
        return payload.startswith(b"\x89PNG\r\n\x1a\n")
    if extension in {".jpg", ".jpeg"}:
        return payload.startswith(b"\xff\xd8\xff")
    if extension == ".gif":
        return payload.startswith((b"GIF87a", b"GIF89a"))
    if extension == ".webp":
        return len(payload) >= 12 and payload[:4] == b"RIFF" and payload[8:12] == b"WEBP"
    if extension == ".svg":
        prefix = payload[:4096].lstrip(b"\xef\xbb\xbf\t\r\n ").lower()
        return b"<svg" in prefix and not any(
            marker in prefix for marker in (b"<!doctype", b"<!entity")
        )
    return False


def _media_role(part: str, content_type: str) -> str:
    suffix = PurePosixPath(part).suffix.lower()
    if suffix in _AUDIO_EXTENSIONS or content_type.lower().startswith("audio/"):
        return "audio"
    if suffix in _VIDEO_EXTENSIONS or content_type.lower().startswith("video/"):
        return "video"
    return "media"


def _asset_filename(
    bundle_token: str,
    slide_number: int,
    role: str,
    index: int,
    content_digest: str,
    extension: str,
) -> str:
    # Graphify's Whisper cache is basename-keyed. Include both the stable deck
    # identity and the asset content digest so media from different decks cannot
    # collide and changed media never reuses a stale transcript.
    return f"{bundle_token}-slide-{slide_number:04d}-{role}-{index:02d}-{content_digest}{extension}"


def _extract_presentation(
    package: _Package,
    source_name: str,
    source_sha256: str,
    limits: PresentationLimits,
    bundle_reference: str,
) -> _Extraction:
    warnings: list[str] = []
    assets: list[_Asset] = []
    slides_manifest: list[dict] = []
    markdown = _Markdown(limits.max_markdown_chars)
    root_relationships = _relationships(package, "")
    main_relationship = next(
        (
            relationship
            for relationship in root_relationships.values()
            if relationship.kind == "officedocument"
            and not relationship.external
            and relationship.resolved_target
        ),
        None,
    )
    if main_relationship is None or main_relationship.resolved_target not in package.infos:
        raise PresentationError("package has no valid root officeDocument relationship")
    presentation_part = main_relationship.resolved_target
    core_relationship = next(
        (
            relationship
            for relationship in root_relationships.values()
            if relationship.kind in {"core-properties", "coreproperties"}
            and not relationship.external
            and relationship.resolved_target
        ),
        None,
    )
    properties = _core_properties(
        package,
        limits,
        core_relationship.resolved_target if core_relationship else None,
    )
    title = properties.get("title") or Path(source_name).stem
    markdown.add(f"# Presentation: {title}")
    metadata_lines = [
        f"- **Source:** `{source_name}`",
        f"- **SHA-256:** `{source_sha256}`",
        f"- **Converter version:** `{CONVERTER_VERSION}`",
        f"- **Main package part:** `{presentation_part}`",
    ]
    for key, value in properties.items():
        metadata_lines.append(f"- **{key}:** {value}")
    markdown.add("## Presentation metadata\n\n" + "\n".join(metadata_lines))

    presentation = package.parse_xml(presentation_part)
    presentation_rels = _relationships(package, presentation_part)
    section_by_slide_id: dict[str, str] = {}
    for section in (item for item in presentation.iter() if _local(item.tag) == "section"):
        section_name = _clean_text(section.attrib.get("name"), limits.max_text_chars)
        for slide_id in (item for item in section.iter() if _local(item.tag) == "sldId"):
            identifier = slide_id.attrib.get("id", "")
            if identifier and section_name:
                section_by_slide_id[identifier] = section_name

    slide_list = next((item for item in presentation if _local(item.tag) == "sldIdLst"), None)
    slide_entries = _children(slide_list, "sldId") if slide_list is not None else []
    if len(slide_entries) > limits.max_slides:
        raise PresentationError(
            f"PPTX has {len(slide_entries)} slides; limit is {limits.max_slides}"
        )
    authors = _comment_authors(package, limits, presentation_rels)
    asset_counters: dict[tuple[int, str], int] = {}
    extracted_relationships: set[tuple[int, str]] = set()
    payload_cache: dict[str, bytes] = {}
    asset_part_cache: dict[tuple[str, str], _Asset] = {}
    bundle_token = re.sub(r"[^A-Za-z0-9._-]+", "_", PurePosixPath(bundle_reference).name)
    template_cache: dict[str, dict] = {}
    template_evidence: list[str] = []
    template_evidence_emitted: set[str] = set()

    def add_asset(
        slide_number: int,
        relationship: _Relationship,
        kind: str,
        *,
        description: str = "",
        forced_part: str | None = None,
    ) -> _Asset | None:
        part = forced_part or relationship.resolved_target
        key = (slide_number, kind + ":" + (part or relationship.target))
        if key in extracted_relationships:
            return None
        extracted_relationships.add(key)
        if not part:
            return None
        if part not in package.infos:
            warnings.append(
                f"Slide {slide_number}: relationship {relationship.relationship_id} target is missing: {part}"
            )
            return None
        if len(assets) >= limits.max_assets:
            raise PresentationError(
                f"PPTX exceeds the extracted asset limit of {limits.max_assets}"
            )
        content_type = package.content_type(part)
        role = _media_role(part, content_type) if kind == "media" else kind
        counter_key = (slide_number, role)
        asset_counters[counter_key] = asset_counters.get(counter_key, 0) + 1
        extension = _safe_extension(part, content_type, kind)
        cache_key = (kind, part)
        cached = asset_part_cache.get(cache_key)
        if cached is not None and cached.kind in {kind, "attachment"}:
            # Reuse bytes/filename for the same package part when a later slide
            # inherits the same layout/master media. Still emit a per-slide
            # provenance row so each slide's association is preserved.
            asset = _Asset(
                kind=cached.kind,
                role=role,
                slide=slide_number,
                relationship_id=relationship.relationship_id,
                source_part=part,
                content_type=cached.content_type,
                filename=cached.filename,
                payload=cached.payload,
                description=description or cached.description,
            )
            assets.append(asset)
            return asset
        if part in payload_cache:
            payload = payload_cache[part]
        else:
            payload = package.read_member(part, cap=limits.max_asset_bytes, asset=True)
            payload_cache[part] = payload
        stored_kind = kind
        if kind == "image" and extension not in _SEMANTIC_IMAGE_EXTENSIONS:
            stored_kind = "attachment"
            warnings.append(
                f"Slide {slide_number}: image part {part} uses {extension}; preserved as an "
                "attachment because Graphify vision cannot decode that format"
            )
        elif kind == "image" and not _valid_semantic_image(payload, extension):
            stored_kind = "attachment"
            extension = ".bin"
            warnings.append(
                f"Slide {slide_number}: image part {part} does not match its declared format; "
                "preserved as an inert binary attachment"
            )
        content_digest = hashlib.sha256(payload).hexdigest()[:10]
        filename = _asset_filename(
            bundle_token,
            slide_number,
            role,
            asset_counters[counter_key],
            content_digest,
            extension,
        )
        asset = _Asset(
            kind=stored_kind,
            role=role,
            slide=slide_number,
            relationship_id=relationship.relationship_id,
            source_part=part,
            content_type=content_type,
            filename=filename,
            payload=payload,
            description=description,
        )
        assets.append(asset)
        asset_part_cache[cache_key] = asset
        return asset

    for slide_number, slide_entry in enumerate(slide_entries, start=1):
        slide_id = slide_entry.attrib.get("id", "")
        relationship_id = _relationship_attr(slide_entry, "id")
        relationship = presentation_rels.get(relationship_id or "")
        if relationship is None or relationship.external or not relationship.resolved_target:
            warnings.append(
                f"Slide {slide_number}: missing or unsafe slide relationship {relationship_id!r}"
            )
            continue
        slide_part = relationship.resolved_target
        if slide_part not in package.infos:
            warnings.append(f"Slide {slide_number}: slide part is missing: {slide_part}")
            continue
        slide = package.parse_xml(slide_part)
        rels = _relationships(package, slide_part)
        unsafe_used = {
            rid
            for rid in _used_relationship_ids(slide, set(rels))
            if not rels[rid].external and rels[rid].resolved_target is None
        }
        for rid in sorted(unsafe_used):
            warnings.append(
                f"Slide {slide_number}: unsafe relationship target ignored for {rid}: {rels[rid].target}"
            )
        section = section_by_slide_id.get(slide_id, "")
        hidden = slide.attrib.get("show", "1").lower() in {"0", "false", "off", "no"}
        common_slide = _first(slide, "cSld")
        slide_name = _clean_text(
            common_slide.attrib.get("name") if common_slide is not None else "",
            limits.max_text_chars,
        )
        shape_tree = _first(slide, "spTree")
        shapes = list(_walk_shapes(shape_tree)) if shape_tree is not None else []
        shape_labels: dict[str, str] = {}
        title_text = ""
        text_lines: list[str] = []
        table_blocks: list[str] = []
        chart_blocks: list[str] = []
        diagram_blocks: list[str] = []
        connector_blocks: list[str] = []
        link_lines: list[str] = []
        asset_lines: list[str] = []
        attachment_parts: list[tuple[str, str]] = []
        layout_part = ""
        master_part = ""

        for shape in shapes:
            local = _local(shape.tag)
            metadata = _shape_metadata(shape, limits.max_text_chars)
            paragraphs = (
                _paragraphs(shape, limits.max_text_chars) if local in {"sp", "cxnSp"} else []
            )
            label = (
                paragraphs[0][1] if paragraphs else metadata["name"] or f"shape {metadata['id']}"
            )
            if metadata["id"]:
                shape_labels[metadata["id"]] = label
            if metadata["placeholder"] in {"title", "ctrTitle"} and paragraphs:
                title_text = paragraphs[0][1]
            if local == "sp":
                descriptor = f"shape {metadata['id'] or '?'}"
                if metadata["name"]:
                    descriptor += f" `{metadata['name']}`"
                if metadata["placeholder"]:
                    descriptor += f" [{metadata['placeholder']}]"
                if metadata.get("x"):
                    descriptor += (
                        f" @ x={metadata.get('x')}, y={metadata.get('y')}, "
                        f"w={metadata.get('width')}, h={metadata.get('height')}"
                    )
                if metadata["description"]:
                    text_lines.append(f"- **Alt text ({descriptor}):** {metadata['description']}")
                if metadata["title"]:
                    text_lines.append(f"- **Object title ({descriptor}):** {metadata['title']}")
                for level, text, hyperlink_ids in paragraphs:
                    text_lines.append(f"{'  ' * level}- [{descriptor}] {text}")
                    for hyperlink_id in hyperlink_ids:
                        hyperlink = rels.get(hyperlink_id)
                        if hyperlink and hyperlink.external:
                            link_lines.append(f"- {text}: {hyperlink.target}")
            elif local == "graphicFrame":
                table = _first(shape, "tbl")
                if table is not None:
                    rows: list[list[str]] = []
                    for row in (item for item in table if _local(item.tag) == "tr"):
                        rows.append(
                            [
                                _all_text(cell, limits.max_text_chars)
                                for cell in row
                                if _local(cell.tag) == "tc"
                            ]
                        )
                    block = _markdown_table(rows)
                    if block:
                        table_blocks.append(f"**{metadata['name'] or 'Table'}**\n\n{block}")
                chart_element = _first(shape, "chart")
                chart_id = (
                    _relationship_attr(chart_element, "id") if chart_element is not None else None
                )
                chart_relationship = rels.get(chart_id or "")
                if chart_relationship and chart_relationship.resolved_target:
                    try:
                        chart_text, chart_attachments = _extract_chart(
                            package, chart_relationship.resolved_target, limits
                        )
                        if chart_text:
                            chart_blocks.append(
                                f"**{metadata['name'] or 'Chart'}**\n\n{chart_text}"
                            )
                        attachment_parts.extend(
                            (part, chart_id or "chart") for part in chart_attachments
                        )
                    except PresentationError as exc:
                        warnings.append(f"Slide {slide_number}: chart extraction failed: {exc}")
                rel_ids = _first(shape, "relIds")
                diagram_id = _relationship_attr(rel_ids, "dm") if rel_ids is not None else None
                diagram_relationship = rels.get(diagram_id or "")
                if diagram_relationship and diagram_relationship.resolved_target:
                    try:
                        diagram_text = _extract_diagram(
                            package, diagram_relationship.resolved_target, limits
                        )
                        if diagram_text:
                            diagram_blocks.append(
                                f"**{metadata['name'] or 'Diagram'}**\n\n{diagram_text}"
                            )
                    except PresentationError as exc:
                        warnings.append(f"Slide {slide_number}: diagram extraction failed: {exc}")

        for shape in shapes:
            if _local(shape.tag) != "cxnSp":
                continue
            metadata = _shape_metadata(shape, limits.max_text_chars)
            start = _first(shape, "stCxn")
            end = _first(shape, "endCxn")
            start_id = start.attrib.get("id", "") if start is not None else ""
            end_id = end.attrib.get("id", "") if end is not None else ""
            if start_id or end_id:
                connector_blocks.append(
                    f"- {shape_labels.get(start_id, start_id or '?')} -> "
                    f"{shape_labels.get(end_id, end_id or '?')} "
                    f"({metadata['name'] or 'connector'})"
                )

        used_ids = _used_relationship_ids(slide, set(rels))
        descriptions_by_id: dict[str, str] = {}
        for shape in shapes:
            metadata = _shape_metadata(shape, limits.max_text_chars)
            description = metadata["description"] or metadata["title"] or metadata["name"]
            for relationship_ref in _used_relationship_ids(shape, set(rels)):
                if description:
                    descriptions_by_id.setdefault(relationship_ref, description)
        for used_id in sorted(used_ids):
            used_relationship = rels[used_id]
            if used_relationship.external:
                if len(used_relationship.target) <= limits.max_external_target_chars:
                    link_lines.append(
                        f"- External {used_relationship.kind}: {used_relationship.target} "
                        f"(relationship `{used_id}`; not fetched)"
                    )
                else:
                    warnings.append(
                        f"Slide {slide_number}: external target for {used_id} exceeds the URL length limit"
                    )
                continue
            if used_relationship.resolved_target is None:
                continue
            if used_relationship.kind == "image":
                asset = add_asset(
                    slide_number,
                    used_relationship,
                    "image",
                    description=descriptions_by_id.get(used_id, ""),
                )
            elif used_relationship.kind in {"media", "audio", "video"}:
                asset = add_asset(
                    slide_number,
                    used_relationship,
                    "media",
                    description=descriptions_by_id.get(used_id, ""),
                )
            elif used_relationship.kind in {"oleobject", "package"}:
                asset = add_asset(
                    slide_number,
                    used_relationship,
                    "attachment",
                    description=descriptions_by_id.get(used_id, ""),
                )
            elif used_relationship.kind not in {
                "chart",
                "diagramdata",
                "diagramlayout",
                "diagramquickstyle",
                "diagramcolors",
                "notesslide",
                "comments",
                "comment",
                "slidelayout",
                "tags",
            }:
                content_type = package.content_type(used_relationship.resolved_target)
                if content_type.startswith("image/"):
                    unknown_kind = "image"
                elif content_type.startswith(("audio/", "video/")):
                    unknown_kind = "media"
                else:
                    unknown_kind = "attachment"
                asset = add_asset(
                    slide_number,
                    used_relationship,
                    unknown_kind,
                    description=(
                        descriptions_by_id.get(used_id, "")
                        or f"Embedded {used_relationship.kind} evidence"
                    ),
                )
            else:
                asset = None
            if asset is not None:
                reference = f"{bundle_reference}/assets/{asset.filename}"
                description = f" — {asset.description}" if asset.description else ""
                asset_lines.append(
                    f"- **{asset.role.title()}** `{reference}`{description} "
                    f"(relationship `{asset.relationship_id}`, package part `{asset.source_part}`)"
                )

        # Slide layouts and masters can contain static labels, logos, diagrams,
        # or background evidence that is visible on the rendered slide but absent
        # from slideN.xml. Cache parsed template metadata so every slide that
        # shares a layout still records its full layout/master chain and inherits
        # the same assets with per-slide provenance.
        template_queue: list[tuple[str, str]] = []
        visited_templates: set[str] = set()
        layout_relationship = next(
            (item for item in rels.values() if item.kind == "slidelayout"), None
        )
        if layout_relationship and layout_relationship.resolved_target:
            layout_part = layout_relationship.resolved_target
            template_queue.append((layout_part, "slide layout"))
        while template_queue:
            template_part, template_role = template_queue.pop(0)
            if template_part in visited_templates or template_part not in package.infos:
                continue
            visited_templates.add(template_part)
            cached_template = template_cache.get(template_part)
            if cached_template is None:
                try:
                    template_root = package.parse_xml(template_part)
                    template_rels = _relationships(package, template_part)
                except PresentationError as exc:
                    warnings.append(
                        f"Slide {slide_number}: {template_role} extraction failed for "
                        f"{template_part}: {exc}"
                    )
                    continue
                template_text_lines: list[str] = []
                template_tree = _first(template_root, "spTree")
                for template_shape in _walk_shapes(
                    template_tree if template_tree is not None else template_root
                ):
                    template_metadata = _shape_metadata(template_shape, limits.max_text_chars)
                    for level, text, _ in _paragraphs(template_shape, limits.max_text_chars):
                        placeholder = (
                            f" [{template_metadata['placeholder']}]"
                            if template_metadata["placeholder"]
                            else ""
                        )
                        template_text_lines.append(f"{'  ' * level}- {text}{placeholder}")
                master_relationship = next(
                    (item for item in template_rels.values() if item.kind == "slidemaster"),
                    None,
                )
                master_target = (
                    master_relationship.resolved_target
                    if master_relationship and master_relationship.resolved_target
                    else ""
                )
                template_assets: list[tuple[_Relationship, str]] = []
                template_used_ids = _used_relationship_ids(template_root, set(template_rels))
                for template_id in sorted(template_used_ids):
                    template_relationship = template_rels[template_id]
                    if template_relationship.external:
                        if len(template_relationship.target) <= limits.max_external_target_chars:
                            link_lines.append(
                                f"- {template_role.title()} external {template_relationship.kind}: "
                                f"{template_relationship.target} (not fetched)"
                            )
                        continue
                    if not template_relationship.resolved_target:
                        warnings.append(
                            f"Slide {slide_number} {template_role}: unsafe relationship target "
                            f"ignored for {template_id}: {template_relationship.target}"
                        )
                        continue
                    if template_relationship.kind == "image":
                        template_asset_kind = "image"
                    elif template_relationship.kind in {"media", "audio", "video"}:
                        template_asset_kind = "media"
                    elif template_relationship.kind in {"oleobject", "package"}:
                        template_asset_kind = "attachment"
                    else:
                        continue
                    template_assets.append((template_relationship, template_asset_kind))
                cached_template = {
                    "role": template_role,
                    "text_lines": template_text_lines,
                    "master_part": master_target,
                    "assets": template_assets,
                }
                template_cache[template_part] = cached_template
            if (
                cached_template["text_lines"]
                and template_part not in template_evidence_emitted
            ):
                template_evidence_emitted.add(template_part)
                template_evidence.append(
                    f"### {template_role.title()}: `{template_part}`\n\n"
                    + "\n".join(cached_template["text_lines"])
                )
            if template_role == "slide layout" and cached_template["master_part"]:
                master_part = cached_template["master_part"]
            elif template_role == "slide master":
                master_part = template_part
            for template_relationship, template_asset_kind in cached_template["assets"]:
                template_asset = add_asset(
                    slide_number,
                    template_relationship,
                    template_asset_kind,
                    description=f"Evidence inherited from {template_role}",
                )
                if template_asset is not None:
                    asset_lines.append(
                        f"- **Inherited {template_asset.role.title()}** "
                        f"`{bundle_reference}/assets/{template_asset.filename}` — "
                        f"from {template_role} `{template_part}` "
                        f"(slide {slide_number})"
                    )
            if cached_template["master_part"]:
                template_queue.append((cached_template["master_part"], "slide master"))

        for attachment_part, origin in attachment_parts:
            synthetic = _Relationship(
                f"chart-{origin}",
                "http://schemas.openxmlformats.org/officeDocument/2006/relationships/package",
                attachment_part,
                False,
                attachment_part,
            )
            asset = add_asset(
                slide_number,
                synthetic,
                "attachment",
                description="Embedded chart workbook",
                forced_part=attachment_part,
            )
            if asset is not None:
                asset_lines.append(
                    f"- **Attachment** `{bundle_reference}/assets/{asset.filename}` — "
                    f"Embedded chart workbook (package part `{asset.source_part}`)"
                )

        notes_blocks: list[str] = []
        comments_blocks: list[str] = []
        for slide_relationship in rels.values():
            if slide_relationship.external or not slide_relationship.resolved_target:
                continue
            if slide_relationship.kind == "notesslide":
                try:
                    notes = package.parse_xml(slide_relationship.resolved_target)
                    notes_tree = _first(notes, "spTree")
                    for shape in _walk_shapes(notes_tree if notes_tree is not None else notes):
                        placeholder = _shape_metadata(shape, limits.max_text_chars)["placeholder"]
                        if placeholder in {"sldImg", "sldNum", "hdr", "ftr", "dt"}:
                            continue
                        for level, text, _ in _paragraphs(shape, limits.max_text_chars):
                            notes_blocks.append(f"{'  ' * level}- {text}")
                    notes_rels = _relationships(package, slide_relationship.resolved_target)
                    notes_used_ids = _used_relationship_ids(notes, set(notes_rels))
                    for notes_id in sorted(notes_used_ids):
                        notes_relationship = notes_rels[notes_id]
                        if notes_relationship.external:
                            if len(notes_relationship.target) <= limits.max_external_target_chars:
                                link_lines.append(
                                    f"- Notes external {notes_relationship.kind}: "
                                    f"{notes_relationship.target} (relationship `{notes_id}`; not fetched)"
                                )
                            continue
                        if notes_relationship.resolved_target is None:
                            warnings.append(
                                f"Slide {slide_number} notes: unsafe relationship target ignored "
                                f"for {notes_id}: {notes_relationship.target}"
                            )
                            continue
                        if notes_relationship.kind == "image":
                            notes_asset = add_asset(
                                slide_number,
                                notes_relationship,
                                "image",
                                description="Image embedded in speaker notes",
                            )
                        elif notes_relationship.kind in {"media", "audio", "video"}:
                            notes_asset = add_asset(
                                slide_number,
                                notes_relationship,
                                "media",
                                description="Media embedded in speaker notes",
                            )
                        elif notes_relationship.kind in {"oleobject", "package"}:
                            notes_asset = add_asset(
                                slide_number,
                                notes_relationship,
                                "attachment",
                                description="Attachment embedded in speaker notes",
                            )
                        else:
                            notes_asset = None
                        if notes_asset is not None:
                            reference = f"{bundle_reference}/assets/{notes_asset.filename}"
                            asset_lines.append(
                                f"- **Notes {notes_asset.role.title()}** `{reference}` — "
                                f"{notes_asset.description} (relationship `{notes_id}`, "
                                f"package part `{notes_asset.source_part}`)"
                            )
                except PresentationError as exc:
                    warnings.append(f"Slide {slide_number}: notes extraction failed: {exc}")
            elif slide_relationship.kind in {"comments", "comment"}:
                try:
                    comments = package.parse_xml(slide_relationship.resolved_target)
                    for comment in (
                        item for item in comments.iter() if _local(item.tag) in {"cm", "comment"}
                    ):
                        text = _all_text(comment, limits.max_text_chars)
                        if not text:
                            continue
                        author_id = comment.attrib.get("authorId", "")
                        author = authors.get(
                            author_id, f"author {author_id}" if author_id else "unknown"
                        )
                        timestamp = comment.attrib.get("dt", "")
                        comments_blocks.append(
                            f"- **{author}**{f' ({timestamp})' if timestamp else ''}: {text}"
                        )
                except PresentationError as exc:
                    warnings.append(f"Slide {slide_number}: comment extraction failed: {exc}")

        transition = _first(slide, "transition")
        transition_text = ""
        if transition is not None:
            effect = next((_local(item.tag) for item in transition), "unspecified")
            attributes = ", ".join(f"{key}={value}" for key, value in transition.attrib.items())
            transition_text = f"- {effect}{f' ({attributes})' if attributes else ''}"

        heading = f"## Slide {slide_number}"
        if title_text:
            heading += f": {title_text}"
        slide_meta = [
            f"- source part: `{slide_part}`",
            f"- slide id: `{slide_id}`",
            f"- hidden: {'true' if hidden else 'false'}",
        ]
        if slide_name:
            slide_meta.append(f"- name: {slide_name}")
        if section:
            slide_meta.append(f"- section: {section}")
        markdown.add(heading + "\n\n### Slide provenance\n\n" + "\n".join(slide_meta))
        if text_lines:
            markdown.add("### Text and native shapes\n\n" + "\n".join(text_lines))
        if table_blocks:
            markdown.add("### Tables\n\n" + "\n\n".join(table_blocks))
        if chart_blocks:
            markdown.add("### Charts\n\n" + "\n\n".join(chart_blocks))
        if diagram_blocks or connector_blocks:
            blocks = diagram_blocks + (["\n".join(connector_blocks)] if connector_blocks else [])
            markdown.add("### Diagrams and connectors\n\n" + "\n\n".join(blocks))
        if asset_lines:
            markdown.add("### Extracted visual and media evidence\n\n" + "\n".join(asset_lines))
        if notes_blocks:
            markdown.add("### Speaker notes\n\n" + "\n".join(notes_blocks))
        if comments_blocks:
            markdown.add("### Comments\n\n" + "\n".join(comments_blocks))
        if link_lines:
            markdown.add(
                "### Links and externally referenced media\n\n"
                + "\n".join(dict.fromkeys(link_lines))
            )
        if transition_text:
            markdown.add("### Transition\n\n" + transition_text)

        slides_manifest.append(
            {
                "number": slide_number,
                "slide_id": slide_id,
                "source_part": slide_part,
                "title": title_text,
                "name": slide_name,
                "section": section,
                "hidden": hidden,
                "layout_part": layout_part,
                "master_part": master_part,
            }
        )

    if template_evidence:
        markdown.add("## Inherited layout and master evidence\n\n" + "\n\n".join(template_evidence))

    custom_xml_blocks: list[str] = []
    custom_parts = [
        name
        for name in sorted(package.infos)
        if name.startswith("customXml/") and name.lower().endswith(".xml")
    ]
    for custom_part in custom_parts[:100]:
        try:
            custom_root = package.parse_xml(custom_part)
        except PresentationError as exc:
            warnings.append(f"Custom XML part {custom_part} was skipped: {exc}")
            continue
        values = [
            _clean_text(value, limits.max_text_chars)
            for value in custom_root.itertext()
            if _clean_text(value, limits.max_text_chars)
        ]
        if values:
            custom_xml_blocks.append(
                f"### `{custom_part}`\n\n" + "\n".join(f"- {value}" for value in values[:1_000])
            )
    if len(custom_parts) > 100:
        warnings.append(f"Custom XML inventory truncated after 100 of {len(custom_parts)} parts")
    if custom_xml_blocks:
        markdown.add("## Custom XML evidence\n\n" + "\n\n".join(custom_xml_blocks))

    if warnings:
        markdown.add(
            "## Extraction warnings\n\n" + "\n".join(f"- {warning}" for warning in warnings)
        )
    return _Extraction(markdown.render(), assets, slides_manifest, warnings, presentation_part)


def _source_identity(path: Path, root: Path | None) -> str:
    if root is not None:
        try:
            return path.resolve().relative_to(root.resolve()).as_posix()
        except (ValueError, OSError, RuntimeError):
            pass
    try:
        return str(path.resolve())
    except (OSError, RuntimeError):
        return str(path.absolute())


def _bundle_name(path: Path, root: Path | None) -> str:
    key = _source_identity(path, root)
    normalized = unicodedata.normalize("NFC", key)
    path_hash = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:8]
    stem = re.sub(r"[^A-Za-z0-9._-]+", "_", unicodedata.normalize("NFC", path.stem)).strip("._-")
    stem = stem[:80] or "presentation"
    return f"{stem}_{path_hash}_pptx"


def _enforce_xml_bounds(root: ETElement, name: str, limits: PresentationLimits) -> None:
    """Fail closed on deeply nested or extremely large XML trees."""
    element_count = 0
    stack: list[tuple[ETElement, int]] = [(root, 1)]
    while stack:
        node, depth = stack.pop()
        element_count += 1
        if element_count > limits.max_xml_elements:
            raise PresentationError(
                f"PPTX XML {name!r} exceeds the {limits.max_xml_elements}-element safety limit"
            )
        if depth > limits.max_xml_depth:
            raise PresentationError(
                f"PPTX XML {name!r} exceeds the {limits.max_xml_depth}-level nesting limit"
            )
        for child in list(node):
            stack.append((child, depth + 1))


def _safe_bundle_relative(bundle: Path, relative: str) -> Path:
    if not isinstance(relative, str) or not _safe_member_name(relative):
        raise ValueError
    path = bundle / Path(*PurePosixPath(relative).parts)
    try:
        path.resolve().relative_to(bundle.resolve())
    except (ValueError, OSError):
        raise ValueError from None
    return path


def _file_sha256(path: Path, *, cap: int) -> tuple[str, int]:
    digest = hashlib.sha256()
    total = 0
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > cap:
                raise ValueError
            digest.update(chunk)
    return digest.hexdigest(), total


def _artifact_paths(
    bundle: Path,
    manifest: dict,
    *,
    limits: PresentationLimits | None = None,
    verify_integrity: bool = False,
) -> PresentationArtifacts | None:
    """Resolve and optionally integrity-check a cached converter bundle.

    Cached bundles are treated as untrusted input: path containment, sizes,
    hashes, kind/extension correspondence, and aggregate budgets are verified
    before any artifact is returned to detection/LLM queues.
    """
    policy = limits or PresentationLimits()

    def paths_for(kind: str) -> tuple[Path, ...]:
        values = manifest.get(kind, [])
        if not isinstance(values, list):
            raise ValueError
        paths: list[Path] = []
        for value in values:
            paths.append(_safe_bundle_relative(bundle, value))
        return tuple(paths)

    try:
        markdown = bundle / "presentation.md"
        manifest_path = bundle / "manifest.json"
        images = paths_for("images")
        media = paths_for("media")
        attachments = paths_for("attachments")
        warnings = manifest.get("warnings", [])
        if not isinstance(warnings, list) or not all(isinstance(item, str) for item in warnings):
            raise ValueError
        all_paths = (markdown, manifest_path, *images, *media, *attachments)
        if not all(path.is_file() for path in all_paths):
            return None

        if verify_integrity:
            markdown_meta = manifest.get("markdown")
            if not isinstance(markdown_meta, dict):
                raise ValueError
            expected_md_sha = markdown_meta.get("sha256")
            expected_md_size = markdown_meta.get("size")
            if not isinstance(expected_md_sha, str) or not isinstance(expected_md_size, int):
                raise ValueError
            md_sha, md_size = _file_sha256(markdown, cap=policy.max_markdown_chars * 4)
            if md_sha != expected_md_sha or md_size != expected_md_size:
                raise ValueError
            if md_size > policy.max_markdown_chars * 4:
                raise ValueError

            assets_meta = manifest.get("assets")
            if not isinstance(assets_meta, list):
                raise ValueError
            expected_by_path: dict[str, dict] = {}
            total_asset_bytes = 0
            for entry in assets_meta:
                if not isinstance(entry, dict):
                    raise ValueError
                relative = entry.get("path")
                kind = entry.get("kind")
                sha = entry.get("sha256")
                size = entry.get("size")
                filename = entry.get("filename")
                if (
                    not isinstance(relative, str)
                    or not isinstance(kind, str)
                    or not isinstance(sha, str)
                    or not isinstance(size, int)
                    or not isinstance(filename, str)
                    or size < 0
                    or size > policy.max_asset_bytes
                ):
                    raise ValueError
                if PurePosixPath(relative).name != filename:
                    raise ValueError
                if kind == "image":
                    extension = Path(filename).suffix.lower()
                    if extension not in _SEMANTIC_IMAGE_EXTENSIONS:
                        raise ValueError
                elif kind not in {"media", "attachment"}:
                    raise ValueError
                prior = expected_by_path.get(relative)
                if prior is not None:
                    if prior.get("sha256") != sha or prior.get("size") != size or prior.get("kind") != kind:
                        raise ValueError
                    continue
                expected_by_path[relative] = entry
                total_asset_bytes += size
                if total_asset_bytes > policy.max_extracted_asset_bytes:
                    raise ValueError
            if len(expected_by_path) > policy.max_assets:
                raise ValueError

            listed = {
                "image": [path.relative_to(bundle).as_posix() for path in images],
                "media": [path.relative_to(bundle).as_posix() for path in media],
                "attachment": [path.relative_to(bundle).as_posix() for path in attachments],
            }
            seen: set[str] = set()
            for kind_name, relatives in listed.items():
                for relative in relatives:
                    if relative in seen:
                        raise ValueError
                    seen.add(relative)
                    entry = expected_by_path.get(relative)
                    if entry is None or entry.get("kind") != kind_name:
                        raise ValueError
                    path = _safe_bundle_relative(bundle, relative)
                    actual_sha, actual_size = _file_sha256(path, cap=policy.max_asset_bytes)
                    if actual_sha != entry["sha256"] or actual_size != entry["size"]:
                        raise ValueError
            if set(expected_by_path) != seen:
                raise ValueError

        return PresentationArtifacts(
            markdown,
            manifest_path,
            images,
            media,
            attachments,
            tuple(warnings),
        )
    except (ValueError, OSError, RuntimeError):
        return None


def _load_cached(
    bundle: Path,
    source_sha256: str,
    source_identity: str,
    limits: PresentationLimits,
) -> PresentationArtifacts | None:
    """Return a trusted cached bundle, or None to force regeneration."""
    manifest_path = bundle / "manifest.json"
    try:
        if not manifest_path.is_file():
            return None
        manifest_size = manifest_path.stat().st_size
        if manifest_size <= 0 or manifest_size > limits.max_manifest_bytes:
            return None
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeError):
        return None
    if not isinstance(manifest, dict):
        return None
    if manifest.get("schema_version") != MANIFEST_SCHEMA_VERSION:
        return None
    if manifest.get("converter_version") != CONVERTER_VERSION:
        return None
    if manifest.get("source_sha256") != source_sha256:
        return None
    if manifest.get("source_path") != source_identity:
        return None
    if manifest.get("limits") != limits.as_policy():
        return None
    if manifest.get("locally_owned") is not True:
        return None
    return _artifact_paths(bundle, manifest, limits=limits, verify_integrity=True)


def _write_bundle(
    bundle: Path,
    extraction: _Extraction,
    source_sha256: str,
    source_name: str,
    source_identity: str,
    limits: PresentationLimits,
) -> PresentationArtifacts:
    bundle.parent.mkdir(parents=True, exist_ok=True)
    stage = bundle.parent / f".{bundle.name}.tmp-{uuid.uuid4().hex}"
    backup = bundle.parent / f".{bundle.name}.old-{uuid.uuid4().hex}"
    try:
        assets_dir = stage / "assets"
        assets_dir.mkdir(parents=True)
        markdown_bytes = extraction.markdown.encode("utf-8")
        if len(markdown_bytes) > limits.max_markdown_chars * 4:
            raise PresentationError("PPTX markdown exceeds the configured safety limit")
        (stage / "presentation.md").write_bytes(markdown_bytes)
        image_paths: list[str] = []
        media_paths: list[str] = []
        attachment_paths: list[str] = []
        asset_manifest: list[dict] = []
        total_asset_bytes = 0
        written_files: set[str] = set()
        for asset in extraction.assets:
            relative = f"assets/{asset.filename}"
            target = stage / "assets" / asset.filename
            if relative not in written_files:
                if asset.size > limits.max_asset_bytes:
                    raise PresentationError(
                        f"PPTX asset {asset.filename!r} exceeds the per-asset byte limit"
                    )
                total_asset_bytes += asset.size
                if total_asset_bytes > limits.max_extracted_asset_bytes:
                    raise PresentationError(
                        "PPTX extracted assets exceed the configured total byte limit"
                    )
                target.write_bytes(asset.payload)
                written_files.add(relative)
                if asset.kind == "image":
                    image_paths.append(relative)
                elif asset.kind == "media":
                    media_paths.append(relative)
                else:
                    attachment_paths.append(relative)
            metadata = asdict(asset)
            metadata.pop("payload")
            metadata["path"] = relative
            metadata["sha256"] = asset.sha256
            metadata["size"] = asset.size
            asset_manifest.append(metadata)
        unique_asset_paths = len(written_files)
        if unique_asset_paths > limits.max_assets:
            raise PresentationError(
                f"PPTX exceeds the extracted asset limit of {limits.max_assets}"
            )
        manifest = {
            "schema_version": MANIFEST_SCHEMA_VERSION,
            "converter_version": CONVERTER_VERSION,
            "locally_owned": True,
            "source_name": source_name,
            "source_path": source_identity,
            "source_sha256": source_sha256,
            "limits": limits.as_policy(),
            "presentation_part": extraction.presentation_part,
            "slides": extraction.slides,
            "markdown": {
                "path": "presentation.md",
                "sha256": hashlib.sha256(markdown_bytes).hexdigest(),
                "size": len(markdown_bytes),
            },
            "assets": asset_manifest,
            "images": image_paths,
            "media": media_paths,
            "attachments": attachment_paths,
            "warnings": extraction.warnings,
        }
        manifest_text = json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        if len(manifest_text.encode("utf-8")) > limits.max_manifest_bytes:
            raise PresentationError("PPTX manifest exceeds the configured safety limit")
        (stage / "manifest.json").write_text(manifest_text, encoding="utf-8")
        if bundle.exists():
            os.replace(bundle, backup)
        os.replace(stage, bundle)
        if backup.exists():
            shutil.rmtree(backup, ignore_errors=True)
    except Exception:
        shutil.rmtree(stage, ignore_errors=True)
        if backup.exists() and not bundle.exists():
            os.replace(backup, bundle)
        raise
    artifacts = _artifact_paths(bundle, manifest, limits=limits, verify_integrity=True)
    if artifacts is None:
        raise PresentationError("PPTX artifact bundle verification failed after writing")
    return artifacts


def convert_presentation_file(
    path: Path,
    out_dir: Path,
    *,
    root: Path | None = None,
    limits: PresentationLimits | None = None,
) -> PresentationArtifacts:
    """Convert ``path`` into a structured, content-versioned artifact bundle.

    External relationships are recorded but never fetched. Embedded content is
    copied as inert evidence only; no macros, OLE objects, media, or attachments
    are executed. The source is read once into a bounded immutable byte snapshot,
    preventing source-swap inconsistencies between fingerprinting and parsing.
    Cached bundles are revalidated against the active limits policy and artifact
    integrity before reuse.
    """
    limits = limits or PresentationLimits()
    raw = _read_source(path, limits.max_raw_bytes)
    source_sha256 = hashlib.sha256(raw).hexdigest()
    source_identity = _source_identity(path, root)
    bundle = out_dir / _bundle_name(path, root)
    cached = _load_cached(bundle, source_sha256, source_identity, limits)
    if cached is not None:
        return cached
    package: _Package | None = None
    try:
        try:
            package = _Package(raw, limits)
        except (zipfile.BadZipFile, zipfile.LargeZipFile, RecursionError) as exc:
            raise PresentationError(f"not a readable PPTX ZIP package: {exc}") from exc
        if root is not None:
            try:
                bundle_reference = bundle.resolve().relative_to(root.resolve()).as_posix()
            except (ValueError, OSError):
                bundle_reference = str(bundle.resolve())
        else:
            bundle_reference = str(bundle.resolve())
        extraction = _extract_presentation(
            package,
            path.name,
            source_sha256,
            limits,
            bundle_reference,
        )
    finally:
        if package is not None:
            package.close()
    return _write_bundle(
        bundle,
        extraction,
        source_sha256,
        path.name,
        source_identity,
        limits,
    )


def cleanup_orphaned_presentation_bundles(
    output_dir: Path,
    *,
    root: Path,
) -> tuple[Path, ...]:
    """Remove converter-owned bundles whose recorded source no longer exists.

    A malformed or tampered manifest fails closed and is left untouched. Only
    ``*_pptx`` directories and source paths contained by ``root`` are eligible.
    """
    if not output_dir.is_dir():
        return ()
    try:
        output_resolved = output_dir.resolve()
        root_resolved = root.resolve()
    except (OSError, RuntimeError):
        return ()

    removed: list[Path] = []
    for bundle in output_dir.iterdir():
        if not bundle.is_dir() or not bundle.name.endswith("_pptx"):
            continue
        try:
            bundle.resolve().relative_to(output_resolved)
            manifest_path = bundle / "manifest.json"
            if not manifest_path.is_file() or manifest_path.stat().st_size > 1_000_000:
                continue
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            source_identity = manifest.get("source_path")
            if not isinstance(source_identity, str) or not source_identity:
                continue
            source_relative = PurePosixPath(source_identity)
            if source_relative.is_absolute() or ".." in source_relative.parts:
                continue
            source_path = (root_resolved / Path(*source_relative.parts)).resolve()
            source_path.relative_to(root_resolved)
            if source_path.exists():
                continue
            shutil.rmtree(bundle)
            removed.append(bundle)
        except (OSError, RuntimeError, ValueError, json.JSONDecodeError):
            continue
    return tuple(removed)
