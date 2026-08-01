from __future__ import annotations

import base64
import json
import os
import zipfile
from pathlib import Path

import pytest

from graphify import detect
from graphify.presentation import (
    PresentationError,
    PresentationLimits,
    cleanup_orphaned_presentation_bundles,
    convert_presentation_file,
)
from graphify.watch import _WATCHED_EXTENSIONS


_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


def _write_rich_pptx(path: Path) -> None:
    content_types = """<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Default Extension="png" ContentType="image/png"/>
  <Default Extension="mp3" ContentType="audio/mpeg"/>
  <Default Extension="mp4" ContentType="video/mp4"/>
  <Override PartName="/ppt/presentation.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml"/>
  <Override PartName="/ppt/slides/slide1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slide+xml"/>
  <Override PartName="/ppt/notesSlides/notesSlide1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.notesSlide+xml"/>
  <Override PartName="/ppt/charts/chart1.xml" ContentType="application/vnd.openxmlformats-officedocument.drawingml.chart+xml"/>
  <Override PartName="/ppt/diagrams/data1.xml" ContentType="application/vnd.openxmlformats-officedocument.drawingml.diagramData+xml"/>
  <Override PartName="/ppt/comments/comment1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.comments+xml"/>
  <Override PartName="/ppt/commentAuthors.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.commentAuthors+xml"/>
</Types>"""
    root_rels = """<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="ppt/presentation.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>
</Relationships>"""
    core = """<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/">
  <dc:title>Semantic Strategy</dc:title><dc:creator>Ada Researcher</dc:creator><dc:subject>Knowledge Graphs</dc:subject>
  <dcterms:created>2026-07-01T00:00:00Z</dcterms:created>
</cp:coreProperties>"""
    presentation = """<p:presentation xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <p:sldIdLst><p:sldId id="256" r:id="rId1"/></p:sldIdLst>
  <p:sldSz cx="12192000" cy="6858000"/>
  <p:extLst><p:ext><p14:sectionLst xmlns:p14="http://schemas.microsoft.com/office/powerpoint/2010/main"><p14:section name="Strategy" id="{A}"><p14:sldIdLst><p14:sldId id="256"/></p14:sldIdLst></p14:section></p14:sectionLst></p:ext></p:extLst>
</p:presentation>"""
    presentation_rels = """<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide" Target="slides/slide1.xml"/>
  <Relationship Id="rIdAuthors" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/commentAuthors" Target="commentAuthors.xml"/>
</Relationships>"""
    slide = """<p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" xmlns:c="http://schemas.openxmlformats.org/drawingml/2006/chart" xmlns:dgm="http://schemas.openxmlformats.org/drawingml/2006/diagram" xmlns:p14="http://schemas.microsoft.com/office/powerpoint/2010/main" show="0">
  <p:cSld name="Decision Slide"><p:spTree>
    <p:nvGrpSpPr/><p:grpSpPr/>
    <p:sp><p:nvSpPr><p:cNvPr id="2" name="Title 1" descr="Primary thesis"/><p:cNvSpPr/><p:nvPr><p:ph type="title"/></p:nvPr></p:nvSpPr><p:spPr><a:xfrm><a:off x="10" y="20"/><a:ext cx="100" cy="30"/></a:xfrm></p:spPr><p:txBody><a:bodyPr/><a:lstStyle/><a:p><a:r><a:t>Q4 Research Strategy</a:t></a:r></a:p></p:txBody></p:sp>
    <p:sp><p:nvSpPr><p:cNvPr id="3" name="Body 1"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr><p:spPr/><p:txBody><a:bodyPr/><a:lstStyle/><a:p><a:pPr lvl="0"/><a:r><a:rPr><a:hlinkClick r:id="rId9"/></a:rPr><a:t>Prioritize causal evidence</a:t></a:r></a:p><a:p><a:pPr lvl="1"/><a:r><a:t>Preserve uncertainty</a:t></a:r></a:p></p:txBody></p:sp>
    <p:sp><p:nvSpPr><p:cNvPr id="4" name="Alpha"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr><p:spPr/><p:txBody><a:bodyPr/><a:lstStyle/><a:p><a:r><a:t>Discover</a:t></a:r></a:p></p:txBody></p:sp>
    <p:sp><p:nvSpPr><p:cNvPr id="5" name="Beta"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr><p:spPr/><p:txBody><a:bodyPr/><a:lstStyle/><a:p><a:r><a:t>Decide</a:t></a:r></a:p></p:txBody></p:sp>
    <p:cxnSp><p:nvCxnSpPr><p:cNvPr id="6" name="Connector 5"/><p:cNvCxnSpPr><a:stCxn id="4" idx="0"/><a:endCxn id="5" idx="0"/></p:cNvCxnSpPr><p:nvPr/></p:nvCxnSpPr><p:spPr/></p:cxnSp>
    <p:graphicFrame><p:nvGraphicFramePr><p:cNvPr id="7" name="Evidence Table"/><p:cNvGraphicFramePr/><p:nvPr/></p:nvGraphicFramePr><a:graphic><a:graphicData uri="table"><a:tbl><a:tr><a:tc><a:txBody><a:p><a:r><a:t>Method</a:t></a:r></a:p></a:txBody></a:tc><a:tc><a:txBody><a:p><a:r><a:t>Confidence</a:t></a:r></a:p></a:txBody></a:tc></a:tr><a:tr><a:tc><a:txBody><a:p><a:r><a:t>Experiment</a:t></a:r></a:p></a:txBody></a:tc><a:tc><a:txBody><a:p><a:r><a:t>High</a:t></a:r></a:p></a:txBody></a:tc></a:tr></a:tbl></a:graphicData></a:graphic></p:graphicFrame>
    <p:graphicFrame><p:nvGraphicFramePr><p:cNvPr id="8" name="Revenue Chart"/><p:cNvGraphicFramePr/><p:nvPr/></p:nvGraphicFramePr><a:graphic><a:graphicData><c:chart r:id="rId2"/></a:graphicData></a:graphic></p:graphicFrame>
    <p:graphicFrame><p:nvGraphicFramePr><p:cNvPr id="9" name="Decision Diagram"/><p:cNvGraphicFramePr/><p:nvPr/></p:nvGraphicFramePr><a:graphic><a:graphicData><dgm:relIds r:dm="rId3"/></a:graphicData></a:graphic></p:graphicFrame>
    <p:pic><p:nvPicPr><p:cNvPr id="10" name="Architecture Image" descr="System architecture overview" title="Architecture"/><p:cNvPicPr/><p:nvPr/></p:nvPicPr><p:blipFill><a:blip r:embed="rId4"/></p:blipFill><p:spPr/></p:pic>
    <p:pic><p:nvPicPr><p:cNvPr id="11" name="Audio Clip"/><p:cNvPicPr/><p:nvPr/></p:nvPicPr><p:blipFill><a:blip r:embed="rId7"/></p:blipFill><p:spPr/><p:extLst><p:ext><p14:media r:embed="rId5"/></p:ext></p:extLst></p:pic>
    <p:pic><p:nvPicPr><p:cNvPr id="12" name="Video Clip"/><p:cNvPicPr/><p:nvPr/></p:nvPicPr><p:spPr/><p:extLst><p:ext><p14:media r:embed="rId6"/></p:ext></p:extLst></p:pic>
    <p:oleObj r:id="rId8" name="Research Data.xlsx" progId="Excel.Sheet.12"/>
    <p:pic><p:nvPicPr><p:cNvPr id="13" name="Linked Demo"/><p:cNvPicPr/><p:nvPr/></p:nvPicPr><p:spPr/><p:extLst><p:ext><p14:media r:link="rId12"/></p:ext></p:extLst></p:pic>
  </p:spTree></p:cSld>
  <p:transition spd="slow"><p:fade/></p:transition>
</p:sld>"""
    slide_rels = """<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/chart" Target="../charts/chart1.xml"/>
  <Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/diagramData" Target="../diagrams/data1.xml"/>
  <Relationship Id="rId4" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="../media/image1.png"/>
  <Relationship Id="rId5" Type="http://schemas.microsoft.com/office/2007/relationships/media" Target="../media/audio1.mp3"/>
  <Relationship Id="rId6" Type="http://schemas.microsoft.com/office/2007/relationships/media" Target="../media/video1.mp4"/>
  <Relationship Id="rId7" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="../media/poster.png"/>
  <Relationship Id="rId8" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/oleObject" Target="../embeddings/data1.xlsx"/>
  <Relationship Id="rId9" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink" Target="https://example.org/evidence" TargetMode="External"/>
  <Relationship Id="rId10" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/notesSlide" Target="../notesSlides/notesSlide1.xml"/>
  <Relationship Id="rId11" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/comments" Target="../comments/comment1.xml"/>
  <Relationship Id="rId12" Type="http://schemas.microsoft.com/office/2007/relationships/media" Target="https://example.org/demo.mp4" TargetMode="External"/>
</Relationships>"""
    notes = """<p:notes xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"><p:cSld><p:spTree><p:sp><p:nvSpPr><p:cNvPr id="2" name="Notes Placeholder"/><p:cNvSpPr/><p:nvPr><p:ph type="body"/></p:nvPr></p:nvSpPr><p:txBody><a:p><a:r><a:t>Confidential speaker insight</a:t></a:r></a:p></p:txBody></p:sp></p:spTree></p:cSld></p:notes>"""
    chart = """<c:chartSpace xmlns:c="http://schemas.openxmlformats.org/drawingml/2006/chart" xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"><c:chart><c:title><c:tx><c:rich><a:p><a:r><a:t>Quarterly Revenue</a:t></a:r></a:p></c:rich></c:tx></c:title><c:plotArea><c:barChart><c:ser><c:tx><c:v>Revenue</c:v></c:tx><c:cat><c:strLit><c:pt idx="0"><c:v>Q1</c:v></c:pt><c:pt idx="1"><c:v>Q2</c:v></c:pt></c:strLit></c:cat><c:val><c:numLit><c:pt idx="0"><c:v>100</c:v></c:pt><c:pt idx="1"><c:v>140</c:v></c:pt></c:numLit></c:val></c:ser></c:barChart></c:plotArea></c:chart></c:chartSpace>"""
    diagram = """<dgm:dataModel xmlns:dgm="http://schemas.openxmlformats.org/drawingml/2006/diagram" xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"><dgm:ptLst><dgm:pt modelId="n1"><dgm:t><a:p><a:r><a:t>Discover</a:t></a:r></a:p></dgm:t></dgm:pt><dgm:pt modelId="n2"><dgm:t><a:p><a:r><a:t>Decide</a:t></a:r></a:p></dgm:t></dgm:pt></dgm:ptLst><dgm:cxnLst><dgm:cxn modelId="c1" srcId="n1" destId="n2" type="parOf"/></dgm:cxnLst></dgm:dataModel>"""
    comments = """<p:cmLst xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"><p:cm authorId="0" dt="2026-07-02T12:00:00Z" idx="1"><p:pos x="1" y="2"/><p:text>Validate this claim</p:text></p:cm></p:cmLst>"""
    authors = """<p:cmAuthorLst xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"><p:cmAuthor id="0" name="Grace Reviewer" initials="GR" lastIdx="1" clrIdx="0"/></p:cmAuthorLst>"""

    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        parts = {
            "[Content_Types].xml": content_types,
            "_rels/.rels": root_rels,
            "docProps/core.xml": core,
            "ppt/presentation.xml": presentation,
            "ppt/_rels/presentation.xml.rels": presentation_rels,
            "ppt/slides/slide1.xml": slide,
            "ppt/slides/_rels/slide1.xml.rels": slide_rels,
            "ppt/notesSlides/notesSlide1.xml": notes,
            "ppt/charts/chart1.xml": chart,
            "ppt/diagrams/data1.xml": diagram,
            "ppt/comments/comment1.xml": comments,
            "ppt/commentAuthors.xml": authors,
            "ppt/media/image1.png": _PNG,
            "ppt/media/poster.png": _PNG,
            "ppt/media/audio1.mp3": b"ID3\x04\x00\x00fake-audio",
            "ppt/media/video1.mp4": b"\x00\x00\x00\x18ftypmp42fake-video",
            "ppt/embeddings/data1.xlsx": b"PK\x03\x04fake-workbook",
        }
        for name, payload in parts.items():
            zf.writestr(name, payload)


def _replace_zip_parts(path: Path, replacements: dict[str, bytes | str]) -> None:
    """Rewrite selected members without creating ambiguous duplicate ZIP names."""
    replacement_bytes = {
        name: value.encode("utf-8") if isinstance(value, str) else value
        for name, value in replacements.items()
    }
    with zipfile.ZipFile(path) as source:
        members = {
            info.filename: source.read(info)
            for info in source.infolist()
            if info.filename not in replacement_bytes
        }
    members.update(replacement_bytes)
    temporary = path.with_suffix(".tmp")
    with zipfile.ZipFile(temporary, "w", zipfile.ZIP_DEFLATED) as target:
        for name, payload in members.items():
            target.writestr(name, payload)
    temporary.replace(path)


def _inject_slide_part(
    path: Path,
    *,
    shape_xml: str,
    relationship_xml: str,
    part_name: str,
    payload: bytes,
) -> None:
    with zipfile.ZipFile(path) as package:
        slide = package.read("ppt/slides/slide1.xml").decode("utf-8")
        relationships = package.read(
            "ppt/slides/_rels/slide1.xml.rels"
        ).decode("utf-8")
    _replace_zip_parts(
        path,
        {
            "ppt/slides/slide1.xml": slide.replace(
                "</p:spTree>", shape_xml + "</p:spTree>"
            ),
            "ppt/slides/_rels/slide1.xml.rels": relationships.replace(
                "</Relationships>", relationship_xml + "</Relationships>"
            ),
            part_name: payload,
        },
    )


def test_pptx_is_classified_and_watched():
    assert detect.classify_file(Path("research.pptx")) == detect.FileType.DOCUMENT
    assert ".pptx" in _WATCHED_EXTENSIONS


def test_rich_presentation_extracts_semantics_and_assets(tmp_path: Path):
    source = tmp_path / "strategy.pptx"
    _write_rich_pptx(source)

    artifacts = convert_presentation_file(source, tmp_path / "converted", root=tmp_path)
    markdown = artifacts.markdown_path.read_text(encoding="utf-8")

    assert "Semantic Strategy" in markdown
    assert "Ada Researcher" in markdown
    assert "Slide 1" in markdown and "Q4 Research Strategy" in markdown
    assert "hidden: true" in markdown
    assert "Prioritize causal evidence" in markdown
    assert "Preserve uncertainty" in markdown
    assert "Method" in markdown and "Experiment" in markdown and "Confidence" in markdown
    assert "Quarterly Revenue" in markdown and "Revenue" in markdown
    assert "Q1" in markdown and "100" in markdown and "Q2" in markdown and "140" in markdown
    assert "Discover -> Decide" in markdown
    assert "Confidential speaker insight" in markdown
    assert "Validate this claim" in markdown and "Grace Reviewer" in markdown
    assert "https://example.org/evidence" in markdown
    assert "https://example.org/demo.mp4" in markdown
    assert "System architecture overview" in markdown
    assert "Transition" in markdown and "fade" in markdown

    assert len(artifacts.images) == 2
    assert {p.suffix for p in artifacts.images} == {".png"}
    assert len(artifacts.media) == 2
    assert {p.suffix for p in artifacts.media} == {".mp3", ".mp4"}
    assert len(artifacts.attachments) == 1
    assert artifacts.attachments[0].suffix == ".xlsx"
    assert all(p.is_file() for p in (*artifacts.images, *artifacts.media, *artifacts.attachments))
    assert all(
        "slide-0001" in p.name
        for p in (*artifacts.images, *artifacts.media, *artifacts.attachments)
    )

    manifest = json.loads(artifacts.manifest_path.read_text(encoding="utf-8"))
    assert manifest["source_sha256"]
    assert manifest["slides"][0]["source_part"] == "ppt/slides/slide1.xml"
    assert manifest["slides"][0]["section"] == "Strategy"


def test_detect_registers_pptx_bundle_with_semantic_queues(tmp_path: Path):
    source = tmp_path / "strategy.pptx"
    _write_rich_pptx(source)

    result = detect.detect(tmp_path, cache_root=tmp_path / "graphify-out")

    assert len(result["files"]["document"]) >= 1
    assert any(p.endswith(".md") and "pptx" in p for p in result["files"]["document"])
    assert len(result["files"]["image"]) == 2
    assert len(result["files"]["video"]) == 2
    assert any(p.endswith(".xlsx") or p.endswith(".md") for p in result["files"]["document"])


def test_nested_pptx_attachment_never_enters_binary_text_queue(tmp_path: Path):
    source = tmp_path / "outer.pptx"
    _write_rich_pptx(source)
    _inject_slide_part(
        source,
        shape_xml='<p:oleObj r:id="rIdNested" name="Nested.pptx"/>',
        relationship_xml=(
            '<Relationship Id="rIdNested" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/oleObject" '
            'Target="../embeddings/nested.pptx"/>'
        ),
        part_name="ppt/embeddings/nested.pptx",
        payload=b"PK\x03\x04nested presentation bytes",
    )

    result = detect.detect(tmp_path, cache_root=tmp_path / "graphify-out")

    assert not any(path.endswith(".pptx") for path in result["files"]["document"])
    assert any(
        "nested PPTX attachment retained" in warning
        for warning in result["skipped_sensitive"]
    )


def test_bmp_attachment_never_enters_vision_or_binary_text_queue(tmp_path: Path):
    source = tmp_path / "bitmap.pptx"
    _write_rich_pptx(source)
    _inject_slide_part(
        source,
        shape_xml=(
            '<p:pic><p:nvPicPr><p:cNvPr id="99" name="Bitmap"/>'
            '<p:cNvPicPr/><p:nvPr/></p:nvPicPr><p:blipFill>'
            '<a:blip r:embed="rIdBmp"/></p:blipFill><p:spPr/></p:pic>'
        ),
        relationship_xml=(
            '<Relationship Id="rIdBmp" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" '
            'Target="../media/image2.bmp"/>'
        ),
        part_name="ppt/media/image2.bmp",
        payload=b"BM" + b"\x00" * 64,
    )

    result = detect.detect(tmp_path, cache_root=tmp_path / "graphify-out")

    assert not any(path.endswith(".bmp") for path in result["files"]["image"])
    assert not any(path.endswith(".bmp") for path in result["files"]["document"])
    assert any(
        "Graphify vision cannot decode" in warning
        for warning in result["skipped_sensitive"]
    )


def test_incremental_pptx_bundle_update_and_deletion_lifecycle(tmp_path: Path):
    source = tmp_path / "strategy.pptx"
    _write_rich_pptx(source)
    manifest_path = tmp_path / "graphify-out" / "manifest.json"

    first = detect.detect_incremental(tmp_path, manifest_path=str(manifest_path))
    assert first["new_files"]["document"]
    assert len(first["new_files"]["image"]) == 2
    assert len(first["new_files"]["video"]) == 2
    first_media = set(first["new_files"]["video"])
    detect.save_manifest(
        first["files"], manifest_path=str(manifest_path), kind="both", root=tmp_path
    )

    unchanged = detect.detect_incremental(tmp_path, manifest_path=str(manifest_path))
    assert not any(unchanged["new_files"].values())
    assert first_media <= set(unchanged["unchanged_files"]["video"])

    original_times = (source.stat().st_atime, source.stat().st_mtime)
    _replace_zip_parts(source, {"ppt/media/audio1.mp3": b"ID3 changed audio payload"})
    os.utime(source, original_times)
    changed = detect.detect_incremental(tmp_path, manifest_path=str(manifest_path))
    assert changed["new_files"]["document"]
    assert changed["new_files"]["video"]
    assert first_media & set(changed["deleted_files"])
    detect.save_manifest(
        changed["files"], manifest_path=str(manifest_path), kind="both", root=tmp_path
    )

    source.unlink()
    deleted = detect.detect_incremental(tmp_path, manifest_path=str(manifest_path))
    assert deleted["deleted_files"]
    assert not any(deleted["files"].values())


def test_orphan_cleanup_rejects_tampered_source_path(tmp_path: Path):
    source = tmp_path / "strategy.pptx"
    _write_rich_pptx(source)
    output = tmp_path / "graphify-out" / "converted"
    artifacts = convert_presentation_file(source, output, root=tmp_path)
    bundle = artifacts.manifest_path.parent
    manifest = json.loads(artifacts.manifest_path.read_text(encoding="utf-8"))
    manifest["source_path"] = "../../outside.pptx"
    artifacts.manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    outside = tmp_path.parent / "outside.pptx"
    outside.write_bytes(b"must remain")
    source.unlink()

    assert cleanup_orphaned_presentation_bundles(output, root=tmp_path) == ()
    assert bundle.is_dir()
    assert outside.read_bytes() == b"must remain"
    outside.unlink()


def test_cache_uses_content_and_converter_version_not_mtime(tmp_path: Path, monkeypatch):
    import graphify.presentation as presentation

    source = tmp_path / "strategy.pptx"
    _write_rich_pptx(source)
    out = tmp_path / "converted"
    first = convert_presentation_file(source, out, root=tmp_path)
    first_text = first.markdown_path.read_text(encoding="utf-8")
    original_times = (source.stat().st_atime, source.stat().st_mtime)

    _replace_zip_parts(
        source,
        {"docProps/core.xml": "<core><title>Changed Same Mtime</title></core>"},
    )
    os.utime(source, original_times)
    second = convert_presentation_file(source, out, root=tmp_path)
    assert second.markdown_path.read_text(encoding="utf-8") != first_text
    assert "Changed Same Mtime" in second.markdown_path.read_text(encoding="utf-8")

    monkeypatch.setattr(presentation, "CONVERTER_VERSION", "test-new-version")
    third = convert_presentation_file(source, out, root=tmp_path)
    manifest = json.loads(third.manifest_path.read_text(encoding="utf-8"))
    assert manifest["converter_version"] == "test-new-version"


def test_cached_bundle_does_not_bypass_stricter_limits(tmp_path: Path):
    source = tmp_path / "strategy.pptx"
    _write_rich_pptx(source)
    output = tmp_path / "converted"
    convert_presentation_file(source, output, root=tmp_path)

    with pytest.raises(PresentationError, match="asset limit"):
        convert_presentation_file(
            source,
            output,
            root=tmp_path,
            limits=PresentationLimits(max_assets=0),
        )


def test_tampered_cached_markdown_is_regenerated(tmp_path: Path):
    source = tmp_path / "strategy.pptx"
    _write_rich_pptx(source)
    output = tmp_path / "converted"
    first = convert_presentation_file(source, output, root=tmp_path)
    first.markdown_path.write_text("FORGED CACHE CONTENT", encoding="utf-8")

    second = convert_presentation_file(source, output, root=tmp_path)

    assert "FORGED CACHE CONTENT" not in second.markdown_path.read_text(encoding="utf-8")
    assert "Q4 Research Strategy" in second.markdown_path.read_text(encoding="utf-8")


def test_utf16_dtd_and_entity_are_rejected(tmp_path: Path):
    source = tmp_path / "entity.pptx"
    _write_rich_pptx(source)
    payload = (
        '<?xml version="1.0" encoding="UTF-16"?>'
        '<!DOCTYPE core [<!ENTITY x "expanded">]>'
        '<core><title>&x;</title></core>'
    ).encode("utf-16")
    _replace_zip_parts(source, {"docProps/core.xml": payload})

    with pytest.raises(PresentationError, match="DTD|entity"):
        convert_presentation_file(source, tmp_path / "converted", root=tmp_path)


def test_shared_layout_populates_master_for_every_slide(tmp_path: Path):
    source = tmp_path / "shared-layout.pptx"
    _write_rich_pptx(source)
    presentation = """<p:presentation xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <p:sldIdLst>
    <p:sldId id="256" r:id="rId1"/>
    <p:sldId id="257" r:id="rId2"/>
  </p:sldIdLst>
</p:presentation>"""
    presentation_rels = """<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide" Target="slides/slide1.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide" Target="slides/slide2.xml"/>
</Relationships>"""
    with zipfile.ZipFile(source) as package:
        slide1 = package.read("ppt/slides/slide1.xml")
        slide1_rels = package.read("ppt/slides/_rels/slide1.xml.rels").decode("utf-8")
    # Ensure slide1 has an explicit layout relationship.
    if "slidelayout" not in slide1_rels.lower() and "slideLayout" not in slide1_rels:
        slide1_rels = slide1_rels.replace(
            "</Relationships>",
            '<Relationship Id="rIdLayout" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideLayout" Target="../slideLayouts/slideLayout1.xml"/>'
            "</Relationships>",
        )
    layout = """<p:sldLayout xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
  <p:cSld><p:spTree><p:nvGrpSpPr/><p:grpSpPr/>
    <p:sp><p:nvSpPr><p:cNvPr id="2" name="Layout Label"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr><p:spPr/><p:txBody><a:p><a:r><a:t>Shared Layout</a:t></a:r></a:p></p:txBody></p:sp>
  </p:spTree></p:cSld>
</p:sldLayout>"""
    layout_rels = """<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rIdMaster" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideMaster" Target="../slideMasters/slideMaster1.xml"/>
</Relationships>"""
    master = """<p:sldMaster xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
  <p:cSld><p:spTree><p:nvGrpSpPr/><p:grpSpPr/>
    <p:sp><p:nvSpPr><p:cNvPr id="2" name="Master Label"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr><p:spPr/><p:txBody><a:p><a:r><a:t>Shared Master</a:t></a:r></a:p></p:txBody></p:sp>
  </p:spTree></p:cSld>
</p:sldMaster>"""
    slide2 = slide1.decode("utf-8").replace("Q4 Research Strategy", "Second Slide Title")
    slide2_rels = slide1_rels
    content_types = """<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Default Extension="png" ContentType="image/png"/>
  <Default Extension="mp3" ContentType="audio/mpeg"/>
  <Default Extension="mp4" ContentType="video/mp4"/>
  <Override PartName="/ppt/presentation.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml"/>
  <Override PartName="/ppt/slides/slide1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slide+xml"/>
  <Override PartName="/ppt/slides/slide2.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slide+xml"/>
  <Override PartName="/ppt/slideLayouts/slideLayout1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slideLayout+xml"/>
  <Override PartName="/ppt/slideMasters/slideMaster1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slideMaster+xml"/>
  <Override PartName="/ppt/notesSlides/notesSlide1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.notesSlide+xml"/>
  <Override PartName="/ppt/charts/chart1.xml" ContentType="application/vnd.openxmlformats-officedocument.drawingml.chart+xml"/>
  <Override PartName="/ppt/diagrams/data1.xml" ContentType="application/vnd.openxmlformats-officedocument.drawingml.diagramData+xml"/>
  <Override PartName="/ppt/comments/comment1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.comments+xml"/>
  <Override PartName="/ppt/commentAuthors.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.commentAuthors+xml"/>
</Types>"""
    _replace_zip_parts(
        source,
        {
            "[Content_Types].xml": content_types,
            "ppt/presentation.xml": presentation,
            "ppt/_rels/presentation.xml.rels": presentation_rels,
            "ppt/slides/slide1.xml": slide1,
            "ppt/slides/_rels/slide1.xml.rels": slide1_rels,
            "ppt/slides/slide2.xml": slide2,
            "ppt/slides/_rels/slide2.xml.rels": slide2_rels,
            "ppt/slideLayouts/slideLayout1.xml": layout,
            "ppt/slideLayouts/_rels/slideLayout1.xml.rels": layout_rels,
            "ppt/slideMasters/slideMaster1.xml": master,
        },
    )

    artifacts = convert_presentation_file(source, tmp_path / "converted", root=tmp_path)
    manifest = json.loads(artifacts.manifest_path.read_text(encoding="utf-8"))
    slides = {(item["number"], item["layout_part"], item["master_part"]) for item in manifest["slides"]}
    assert (1, "ppt/slideLayouts/slideLayout1.xml", "ppt/slideMasters/slideMaster1.xml") in slides
    assert (2, "ppt/slideLayouts/slideLayout1.xml", "ppt/slideMasters/slideMaster1.xml") in slides


def test_custom_out_places_pptx_bundle_under_output_root(tmp_path: Path):
    source_root = tmp_path / "src"
    source_root.mkdir()
    source = source_root / "strategy.pptx"
    _write_rich_pptx(source)
    out_root = tmp_path / "dest"

    result = detect.detect(source_root, cache_root=out_root)

    docs = result["files"]["document"]
    assert docs
    assert all(str(out_root) in path for path in docs)
    assert not (source_root / "graphify-out").exists()
    assert (out_root / "graphify-out" / "converted").is_dir()


def test_embedded_office_attachment_sidecar_keeps_parent_provenance(tmp_path: Path, monkeypatch):
    attachment = tmp_path / "strategy_abcd_pptx-slide-0001-attachment-01-deadbeef.xlsx"
    attachment.write_bytes(b"PK\x03\x04placeholder")
    parent = tmp_path / "strategy.pptx"
    parent.write_bytes(b"fake")
    markdown = tmp_path / "out" / "graphify-out" / "converted" / "strategy_abcd_pptx" / "presentation.md"
    markdown.parent.mkdir(parents=True)
    markdown.write_text("# parent", encoding="utf-8")

    def _fake_xlsx(_path: Path) -> str:
        return "## Sheet: Evidence\n\n| ParentProvenanceMarker |\n| --- |"

    monkeypatch.setattr(detect, "xlsx_to_markdown", _fake_xlsx)
    sidecar = detect.convert_office_file(
        attachment,
        tmp_path / "out" / "graphify-out" / "converted",
        root=tmp_path,
        provenance={
            "parent_presentation": str(parent),
            "parent_slide": "1",
            "embedded_attachment": attachment.name,
            "presentation_markdown": str(markdown),
        },
    )
    assert sidecar is not None
    text = sidecar.read_text(encoding="utf-8")
    assert "<!-- converted from" in text
    assert "parent_presentation:" in text
    assert "parent_slide: 1" in text
    assert "strategy.pptx" in text
    assert "ParentProvenanceMarker" in text

    # Detect path: slide number is recovered from the PPTX asset filename.
    slide_match = __import__("re").search(r"-slide-(\d{4})-", attachment.name)
    assert slide_match is not None
    assert int(slide_match.group(1)) == 1


def test_archive_member_limit_fails_closed(tmp_path: Path):
    source = tmp_path / "too-many.pptx"
    _write_rich_pptx(source)
    with zipfile.ZipFile(source, "a") as zf:
        for index in range(5):
            zf.writestr(f"customXml/item{index}.xml", "<x/>")

    limits = PresentationLimits(max_members=5)
    with pytest.raises(PresentationError, match="members"):
        convert_presentation_file(source, tmp_path / "converted", root=tmp_path, limits=limits)


def test_unsafe_internal_relationship_is_not_extracted(tmp_path: Path):
    source = tmp_path / "unsafe.pptx"
    _write_rich_pptx(source)
    with zipfile.ZipFile(source) as zf:
        rels = zf.read("ppt/slides/_rels/slide1.xml.rels").decode("utf-8")
        slide = zf.read("ppt/slides/slide1.xml").decode("utf-8")
    rels = rels.replace(
        "</Relationships>",
        '<Relationship Id="rIdBad" Type="http://schemas.microsoft.com/office/2007/relationships/media" Target="..%2F..%2F..%2Foutside.mp4"/></Relationships>',
    )
    slide = slide.replace(
        "</p:spTree>",
        '<p:pic><p:extLst><p:ext><p14:media r:embed="rIdBad"/></p:ext></p:extLst></p:pic></p:spTree>',
    )
    _replace_zip_parts(
        source,
        {
            "ppt/slides/_rels/slide1.xml.rels": rels,
            "ppt/slides/slide1.xml": slide,
        },
    )

    artifacts = convert_presentation_file(source, tmp_path / "converted", root=tmp_path)
    assert len(artifacts.media) == 2
    markdown = artifacts.markdown_path.read_text(encoding="utf-8")
    assert "unsafe relationship target" in markdown.lower()


def test_doctype_xml_is_rejected(tmp_path: Path):
    source = tmp_path / "entity.pptx"
    _write_rich_pptx(source)
    _replace_zip_parts(
        source,
        {
            "ppt/presentation.xml": '<!DOCTYPE x [<!ENTITY boom "boom">]><p:presentation xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">&boom;</p:presentation>'
        },
    )

    with pytest.raises(PresentationError, match="DTD|entity|XML"):
        convert_presentation_file(source, tmp_path / "converted", root=tmp_path)


def test_main_presentation_part_is_resolved_from_root_relationships(tmp_path: Path):
    source = tmp_path / "relocated-main.pptx"
    _write_rich_pptx(source)
    with zipfile.ZipFile(source) as zf:
        root_rels = zf.read("_rels/.rels").decode("utf-8")
        presentation = zf.read("ppt/presentation.xml")
        presentation_rels = zf.read("ppt/_rels/presentation.xml.rels").decode("utf-8")
        content_types = zf.read("[Content_Types].xml").decode("utf-8")
    root_rels = root_rels.replace("ppt/presentation.xml", "custom/pres.xml")
    presentation_rels = presentation_rels.replace(
        "slides/slide1.xml", "../ppt/slides/slide1.xml"
    ).replace("commentAuthors.xml", "../ppt/commentAuthors.xml")
    content_types = content_types.replace(
        "</Types>",
        '<Override PartName="/custom/pres.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml"/></Types>',
    )
    _replace_zip_parts(
        source,
        {
            "_rels/.rels": root_rels,
            "[Content_Types].xml": content_types,
            "custom/pres.xml": presentation,
            "custom/_rels/pres.xml.rels": presentation_rels,
        },
    )

    artifacts = convert_presentation_file(source, tmp_path / "converted", root=tmp_path)
    manifest = json.loads(artifacts.manifest_path.read_text(encoding="utf-8"))

    assert manifest["presentation_part"] == "custom/pres.xml"
    assert "Q4 Research Strategy" in artifacts.markdown_path.read_text(encoding="utf-8")


def test_extended_chart_cached_values_are_preserved(tmp_path: Path):
    source = tmp_path / "extended-chart.pptx"
    _write_rich_pptx(source)
    extended_chart = """<cx:chartSpace xmlns:cx="http://schemas.microsoft.com/office/drawing/2014/chartex"><cx:chart><cx:title><cx:tx><cx:v>Portfolio Evidence</cx:v></cx:tx></cx:title><cx:plotArea><cx:series><cx:tx><cx:v>Risk Score</cx:v></cx:tx><cx:dataId val="0"/></cx:series></cx:plotArea><cx:data><cx:strDim><cx:pt idx="0"><cx:v>Alpha</cx:v></cx:pt><cx:pt idx="1"><cx:v>Beta</cx:v></cx:pt></cx:strDim><cx:numDim><cx:pt idx="0"><cx:v>0.2</cx:v></cx:pt><cx:pt idx="1"><cx:v>0.7</cx:v></cx:pt></cx:numDim></cx:data></cx:chart></cx:chartSpace>"""
    _replace_zip_parts(source, {"ppt/charts/chart1.xml": extended_chart})

    artifacts = convert_presentation_file(source, tmp_path / "converted", root=tmp_path)
    markdown = artifacts.markdown_path.read_text(encoding="utf-8")

    assert "Portfolio Evidence" in markdown
    assert "Risk Score" in markdown
    assert "Alpha" in markdown and "Beta" in markdown
    assert "0.2" in markdown and "0.7" in markdown


def test_notes_images_and_media_are_extracted(tmp_path: Path):
    source = tmp_path / "notes-media.pptx"
    _write_rich_pptx(source)
    with zipfile.ZipFile(source) as zf:
        notes = zf.read("ppt/notesSlides/notesSlide1.xml").decode("utf-8")
    notes = notes.replace(
        "</p:spTree>",
        """<p:pic xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" xmlns:p14="http://schemas.microsoft.com/office/powerpoint/2010/main"><p:nvPicPr><p:cNvPr id="9" name="Notes Evidence"/><p:cNvPicPr/><p:nvPr/></p:nvPicPr><p:blipFill><a:blip r:embed="rIdNoteImage"/></p:blipFill><p:extLst><p:ext><p14:media r:embed="rIdNoteAudio"/></p:ext></p:extLst></p:pic></p:spTree>""",
    )
    notes_rels = """<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
      <Relationship Id="rIdNoteImage" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="../media/note-image.png"/>
      <Relationship Id="rIdNoteAudio" Type="http://schemas.microsoft.com/office/2007/relationships/media" Target="../media/note-audio.mp3"/>
    </Relationships>"""
    _replace_zip_parts(
        source,
        {
            "ppt/notesSlides/notesSlide1.xml": notes,
            "ppt/notesSlides/_rels/notesSlide1.xml.rels": notes_rels,
            "ppt/media/note-image.png": _PNG + b"note",
            "ppt/media/note-audio.mp3": b"ID3-note-audio",
        },
    )

    artifacts = convert_presentation_file(source, tmp_path / "converted", root=tmp_path)
    markdown = artifacts.markdown_path.read_text(encoding="utf-8")

    assert len(artifacts.images) == 3
    assert len(artifacts.media) == 3
    assert "Image embedded in speaker notes" in markdown
    assert "Media embedded in speaker notes" in markdown


def test_media_basenames_are_deck_and_content_unique_for_transcript_cache(tmp_path: Path):
    first_source = tmp_path / "one" / "deck.pptx"
    second_source = tmp_path / "two" / "deck.pptx"
    first_source.parent.mkdir()
    second_source.parent.mkdir()
    _write_rich_pptx(first_source)
    _write_rich_pptx(second_source)
    out = tmp_path / "converted"

    first = convert_presentation_file(first_source, out, root=tmp_path)
    second = convert_presentation_file(second_source, out, root=tmp_path)
    first_names = {path.name for path in first.media}
    second_names = {path.name for path in second.media}
    assert first_names.isdisjoint(second_names)

    old_audio = next(path.name for path in first.media if path.suffix == ".mp3")
    _replace_zip_parts(first_source, {"ppt/media/audio1.mp3": b"ID3-changed-content"})
    changed = convert_presentation_file(first_source, out, root=tmp_path)
    new_audio = next(path.name for path in changed.media if path.suffix == ".mp3")
    assert new_audio != old_audio


def test_duplicate_archive_member_is_rejected(tmp_path: Path):
    source = tmp_path / "duplicate.pptx"
    _write_rich_pptx(source)
    with zipfile.ZipFile(source, "a", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("ppt/media/image1.png", _PNG)

    with pytest.raises(PresentationError, match="duplicate"):
        convert_presentation_file(source, tmp_path / "converted", root=tmp_path)


def test_asset_stream_limit_is_enforced_before_materialization(tmp_path: Path):
    source = tmp_path / "asset-limit.pptx"
    _write_rich_pptx(source)

    with pytest.raises(PresentationError, match="extraction limit"):
        convert_presentation_file(
            source,
            tmp_path / "converted",
            root=tmp_path,
            limits=PresentationLimits(max_asset_bytes=8),
        )


def test_unsupported_binary_image_format_is_retained_but_not_sent_as_text(tmp_path: Path):
    source = tmp_path / "legacy-image.pptx"
    _write_rich_pptx(source)
    with zipfile.ZipFile(source) as zf:
        rels = zf.read("ppt/slides/_rels/slide1.xml.rels").decode("utf-8")
    rels = rels.replace("../media/image1.png", "../media/legacy.bmp")
    _replace_zip_parts(
        source,
        {
            "ppt/slides/_rels/slide1.xml.rels": rels,
            "ppt/media/legacy.bmp": b"BM unsupported bitmap evidence",
        },
    )

    artifacts = convert_presentation_file(source, tmp_path / "converted", root=tmp_path)

    assert len(artifacts.images) == 1  # the PNG video poster remains vision-compatible
    assert any(path.suffix == ".bmp" for path in artifacts.attachments)
    assert any("vision cannot decode" in warning for warning in artifacts.warnings)


def test_disguised_image_payload_is_demoted_to_binary_attachment(tmp_path: Path):
    source = tmp_path / "disguised-image.pptx"
    _write_rich_pptx(source)
    _replace_zip_parts(
        source,
        {"ppt/media/image1.png": b"<html><script>not an image</script></html>"},
    )

    artifacts = convert_presentation_file(source, tmp_path / "converted", root=tmp_path)

    assert len(artifacts.images) == 1
    assert any(path.suffix == ".bin" for path in artifacts.attachments)
    assert any("does not match its declared format" in warning for warning in artifacts.warnings)


def test_layout_master_custom_xml_and_unknown_embedded_parts_are_preserved(tmp_path: Path):
    source = tmp_path / "package-evidence.pptx"
    _write_rich_pptx(source)
    with zipfile.ZipFile(source) as zf:
        slide = zf.read("ppt/slides/slide1.xml").decode("utf-8")
        rels = zf.read("ppt/slides/_rels/slide1.xml.rels").decode("utf-8")
    slide = slide.replace(
        "</p:spTree>",
        '<p:contentPart r:id="rIdModel"/></p:spTree>',
    )
    rels = rels.replace(
        "</Relationships>",
        """<Relationship Id="rIdLayout" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideLayout" Target="../slideLayouts/slideLayout1.xml"/>
        <Relationship Id="rIdModel" Type="http://schemas.microsoft.com/office/2017/10/relationships/model3d" Target="../media/model.glb"/>
        </Relationships>""",
    )
    layout = """<p:sldLayout xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><p:cSld><p:spTree>
      <p:sp><p:nvSpPr><p:cNvPr id="2" name="Layout Label"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr><p:txBody><a:p><a:r><a:t>Corporate knowledge standard</a:t></a:r></a:p></p:txBody></p:sp>
      <p:pic><p:nvPicPr><p:cNvPr id="3" name="Layout Logo"/><p:cNvPicPr/><p:nvPr/></p:nvPicPr><p:blipFill><a:blip r:embed="rIdLogo"/></p:blipFill></p:pic>
    </p:spTree></p:cSld></p:sldLayout>"""
    layout_rels = """<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
      <Relationship Id="rIdLogo" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="../media/layout-logo.png"/>
      <Relationship Id="rIdMaster" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideMaster" Target="../slideMasters/slideMaster1.xml"/>
    </Relationships>"""
    master = """<p:sldMaster xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"><p:cSld><p:spTree><p:sp><p:nvSpPr><p:cNvPr id="2" name="Master Label"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr><p:txBody><a:p><a:r><a:t>Research Division</a:t></a:r></a:p></p:txBody></p:sp></p:spTree></p:cSld></p:sldMaster>"""
    _replace_zip_parts(
        source,
        {
            "ppt/slides/slide1.xml": slide,
            "ppt/slides/_rels/slide1.xml.rels": rels,
            "ppt/slideLayouts/slideLayout1.xml": layout,
            "ppt/slideLayouts/_rels/slideLayout1.xml.rels": layout_rels,
            "ppt/slideMasters/slideMaster1.xml": master,
            "ppt/media/layout-logo.png": _PNG + b"layout",
            "ppt/media/model.glb": b"glTF-model-evidence",
            "customXml/item1.xml": "<research><claim>Causal mechanism registry</claim></research>",
        },
    )

    artifacts = convert_presentation_file(source, tmp_path / "converted", root=tmp_path)
    markdown = artifacts.markdown_path.read_text(encoding="utf-8")

    assert "Corporate knowledge standard" in markdown
    assert "Research Division" in markdown
    assert "Causal mechanism registry" in markdown
    assert "Embedded model3d evidence" in markdown
    assert len(artifacts.images) == 3
    assert any(path.suffix == ".glb" for path in artifacts.attachments)
    manifest = json.loads(artifacts.manifest_path.read_text(encoding="utf-8"))
    assert manifest["slides"][0]["layout_part"] == "ppt/slideLayouts/slideLayout1.xml"
    assert manifest["slides"][0]["master_part"] == "ppt/slideMasters/slideMaster1.xml"


def test_markdown_output_limit_stops_at_section_boundary(tmp_path: Path):
    source = tmp_path / "bounded-output.pptx"
    _write_rich_pptx(source)

    artifacts = convert_presentation_file(
        source,
        tmp_path / "converted",
        root=tmp_path,
        limits=PresentationLimits(max_markdown_chars=700),
    )
    markdown = artifacts.markdown_path.read_text(encoding="utf-8")

    assert len(markdown) <= 700
    assert "truncated at a safe section boundary" in markdown
    assert len(artifacts.images) == 2
    assert len(artifacts.media) == 2
