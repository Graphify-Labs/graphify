"""Offline directed graphs, progressive disclosure, and inert untrusted text."""
from __future__ import annotations

import copy
from html.parser import HTMLParser

import pytest

from graphify import review
from graphify.review_html import _positions, render_review
from tests.test_review import model, reply_for  # noqa: F401
from tests.test_review_source import repository  # noqa: F401


class Document(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tags = []
        self.ids = set()
        self.links = []
        self.detail_depth = 0
        self.visible_text = []
    def handle_starttag(self, tag, attrs):
        if tag == "details":
            self.detail_depth += 1
        self.tags.append(tag)
        data = dict(attrs)
        assert not any(key.startswith("on") for key in data)
        if "id" in data:
            assert data["id"] not in self.ids
            self.ids.add(data["id"])
        if "href" in data:
            self.links.append(data["href"])
    def handle_endtag(self, tag):
        if tag == "details":
            self.detail_depth -= 1
    def handle_data(self, data):
        if self.detail_depth == 0:
            self.visible_text.append(data)


def test_unmapped_extraction_failures_are_visible_before_disclosure(model):
    model["coverage"]["head"]["failed_sources"] = []
    model["coverage"]["head"]["unmapped_failed_sources"] = 1
    document = render_review(model)
    assert "1 failed extractions" in document
    assert "1 failure diagnostics could not be mapped to snapshot source" in document
    parser = Document()
    parser.feed(document)
    assert any("1 failed extractions" in text for text in parser.visible_text)


def test_offline_graphs_disclosures_and_evidence_links(model):
    doc = render_review(model)
    parser = Document()
    parser.feed(doc)
    assert "script" not in parser.tags and "iframe" not in parser.tags and "img" not in parser.tags
    assert parser.tags.count("svg") >= 4
    assert parser.tags.count("details") >= 6
    assert "marker-end" in doc and "calls" in doc
    assert "Blast radius" in doc and "Behavioral pseudocode unavailable" in doc
    assert all(link[1:] in parser.ids for link in parser.links if link.startswith("#"))
    assert "default-src 'none'" in doc
    assert "@media(max-width:760px)" in doc


def test_pseudocode_is_inferred_and_inert(model, monkeypatch):
    import graphify.llm as llm
    payload = '</script><script>alert(1)</script><img src=x onerror=alert(1)>'
    monkeypatch.setattr(llm, "_call_llm", lambda *args, **kwargs: reply_for(model, summary=payload, after_pseudocode=payload))
    review.infer_behavior(model, backend="ollama")
    model["target"]["title"] = payload
    model["stories"][0]["graphs"]["head"]["nodes"][0]["label"] = payload
    doc = render_review(model)
    parser = Document()
    parser.feed(doc)
    assert "script" not in parser.tags and "img" not in parser.tags
    assert "&lt;script&gt;" in doc
    assert "INFERRED · BEHAVIOR INTERPRETATION" in doc


def test_shared_positions_and_stable_rendering(model):
    graphs = model["stories"][0]["graphs"]
    layout1 = _positions([graphs["base"], graphs["head"]])
    layout2 = _positions([graphs["head"], graphs["base"]])
    assert layout1 == layout2
    assert render_review(model) == render_review(copy.deepcopy(model))


def test_existing_artifact_survives_json_write_failure(model, tmp_path, monkeypatch):
    json_path, html_path = review.save_review(model, tmp_path)
    old_json, old_html = json_path.read_text(), html_path.read_text()
    original = review.write_text_atomic
    def failing(path, text):
        if path.name == "review.json":
            raise OSError("disk failure")
        original(path, text)
    monkeypatch.setattr(review, "write_text_atomic", failing)
    model["target"]["title"] = "New title"
    with pytest.raises(OSError, match="disk failure"):
        review.save_review(model, tmp_path)
    assert json_path.read_text() == old_json and html_path.read_text() == old_html


def test_output_override(model, tmp_path, monkeypatch):
    import graphify.paths as paths
    monkeypatch.setattr(paths, "GRAPHIFY_OUT", "custom-out")
    json_path, html_path = review.save_review(model, tmp_path)
    assert json_path.relative_to(tmp_path).parts[0] == "custom-out"
    assert html_path.exists()


@pytest.mark.parametrize("component", ["graphify-out", "reviews", "pr-42", "review.html", "review.json"])
def test_symlinked_review_paths_cannot_overwrite_victims(model, tmp_path, requires_symlinks, component):
    model["target"].update(type="pull_request", number=42)
    output = tmp_path / "graphify-out" / "reviews" / "pr-42"
    path = next(p for p in [tmp_path / "graphify-out", tmp_path / "graphify-out" / "reviews", output,
                           output / "review.html", output / "review.json"] if p.name == component)
    victim = tmp_path / "victim"
    if component.endswith((".html", ".json")):
        victim.write_text("KEEP", encoding="utf-8")
    else:
        victim.mkdir()
        (victim / "keep.txt").write_text("KEEP", encoding="utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.symlink_to(victim, target_is_directory=victim.is_dir())
    with pytest.raises(review.ReviewError, match="symlink"):
        review.save_review(model, tmp_path)
    assert (victim / "keep.txt").read_text() == "KEEP" if victim.is_dir() else victim.read_text() == "KEEP"
    assert path.is_symlink()


def test_commit_failure_restores_old_html_without_rewriting_it(model, tmp_path, monkeypatch):
    json_path, html_path = review.save_review(model, tmp_path)
    old_json, old_html = json_path.read_bytes(), html_path.read_bytes()
    replace = review.os_replace_with_fallback
    def fail_json(source, destination):
        if destination == json_path:
            raise OSError("JSON swap failure")
        replace(source, destination)
    monkeypatch.setattr(review, "os_replace_with_fallback", fail_json)
    model["target"]["title"] = "new title"
    with pytest.raises(OSError, match="JSON swap failure"):
        review.save_review(model, tmp_path)
    assert json_path.read_bytes() == old_json and html_path.read_bytes() == old_html


def test_failed_restore_preserves_recoverable_html_and_original_cause(model, tmp_path, monkeypatch):
    json_path, html_path = review.save_review(model, tmp_path)
    old_html = html_path.read_bytes()
    replace = review.os_replace_with_fallback
    def fail_twice(source, destination):
        if destination == json_path or source.name == "previous.html":
            raise OSError("original JSON failure" if destination == json_path else "restore failure")
        replace(source, destination)
    monkeypatch.setattr(review, "os_replace_with_fallback", fail_twice)
    with pytest.raises(review.ReviewError, match="recovery also failed") as failure:
        review.save_review(model, tmp_path)
    assert "original JSON failure" in str(failure.value.__cause__)
    recovery = list(html_path.parent.glob(".review-stage-*/previous.html"))
    assert len(recovery) == 1 and recovery[0].read_bytes() == old_html


@pytest.mark.parametrize("authority", ["ghe.example:8443", "[2001:db8::1]:8443"])
def test_pinned_source_url_preserves_enterprise_authority(model, authority):
    model["target"].update(repository="owner/repo", url=f"https://{authority}/owner/repo/pull/42")
    assert f"https://{authority}/owner/repo/blob/" in render_review(model)


def test_blast_diagrams_have_navigable_text_details(model):
    doc = render_review(model)
    assert doc.count("Relationships, confidence and source details") == 4
    assert "<h3>Symbols</h3>" in doc
