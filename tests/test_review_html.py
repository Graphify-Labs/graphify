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
    def handle_starttag(self, tag, attrs):
        self.tags.append(tag)
        data = dict(attrs)
        assert not any(key.startswith("on") for key in data)
        if "id" in data:
            assert data["id"] not in self.ids
            self.ids.add(data["id"])
        if "href" in data:
            self.links.append(data["href"])


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
