# EPUB Semantic Ingestion Scoping (STL 3.14+)

## Goals (parallel to PPTX)
- Full semantic extraction, **not** plain text.
- Preserve chapter/spine order, structure, relationships, provenance.
- Extract: text (XHTML/OPS), notes/annotations if present, tables, images (→ vision), embedded audio/video (→ transcription with content-aware cache), hyperlinks.
- Emit: Markdown sidecars + structured manifest (similar to PPTX).
- Bounded/safe parsing of untrusted EPUBs (ZIP + XML).
- Support custom --out, watch, CLI, agent workflows.
- Incremental + clustered liveness for generated transcripts.
- Tests: adversarial (malformed, large, nested zips, bad XML), end-to-end with real EPUB fixtures.

## Architecture Approach (like PPTX)
- New `graphify/epub.py` (or `graphify/ebook.py`) — dedicated bounded parser.
  - Use `zipfile` with strict limits (max members, sizes, compression ratio).
  - Use `defusedxml` for OPF, NCX, XHTML (DTD/entity rejection, depth limits).
  - Parse OPF for manifest/spine (reading order).
  - Walk spine for chapter content.
- Keep `detect.py` as dispatcher (add EPUB detection + routing).
- Reuse `transcribe.py` for media (unconditional on 3.14+).
- Reuse vision routing for images.
- No heavy "ebooklib" runtime dep at core (optional for probes only, like python-pptx was for PPTX).

## Key Differences from PPTX
- EPUB structure: OPF (package doc), spine (linear reading order), manifest, NCX/toc.
- XHTML content (not OOXML slides).
- Often has embedded fonts, CSS — treat as unsupported/inert unless we decide to extract styles.
- Media can be in the EPUB zip itself.
- Chapters are the "slides" analog.

## Safety Requirements (copy/adapt from PPTX)
- Max source size, ZIP members, per-member uncompressed, aggregate, compression ratio.
- Max XML depth/elements.
- Reject traversal, DTD, entities, encrypted/duplicate members, active content (scripts in XHTML?).
- Treat cache as untrusted.

## Integration Points
- `detect.py`: `convert_office_file` generalization or new `convert_epub`.
- `cli.py`: support for EPUB in extract/watch.
- `watch.py`: add .epub to watched extensions.
- `tools/skillgen/...`: update references for agent EPUB workflows.
- Tests: `tests/test_epub.py` (mirroring test_presentation.py).

## Deliverables for separate PR
- Core parser in new module.
- Full provenance (chapter IDs, reading order, parent EPUB).
- Media → transcript/vision nodes preserved in graphs.
- Adversarial + real EPUB fixtures (public domain books + crafted bad ones).
- Docs update + example.
- No mixing with PPTX work.

## Open Questions to Resolve in Scoping
- Exact library choice for XHTML parsing (lxml with defused? html5lib?).
- Do we extract CSS/embedded fonts as assets or inert?
- TOC/NCX vs spine order (prefer spine).
- Annotations/highlights in EPUB (some formats have them).
- Performance for large novels (many chapters).

## Next Immediate Steps (if approved)
1. Inventory real EPUB test fixtures.
2. Prototype minimal safe OPF + spine parser.
3. Mirror PPTX test patterns.
4. Coordinate with upstream if any existing thin EPUB PRs.

Status: Ready to start dedicated branch after this STL 3.14 work lands.