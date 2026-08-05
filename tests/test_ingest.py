"""Tests for graphify.ingest.save_query_result"""
from __future__ import annotations
import re
import urllib.error
from pathlib import Path
import pytest
from graphify.ingest import ingest, save_query_result


def test_file_created(tmp_path):
    out = save_query_result("what is attention?", "Attention is...", tmp_path / "memory")
    assert out.exists()


def test_filename_format(tmp_path):
    mem = tmp_path / "memory"
    out = save_query_result("what connects A to B?", "They share...", mem)
    assert out.name.startswith("query_")
    assert out.suffix == ".md"


def test_frontmatter_question(tmp_path):
    mem = tmp_path / "memory"
    question = "what is attention?"
    out = save_query_result(question, "Attention is softmax.", mem)
    content = out.read_text()
    assert "question:" in content
    assert "attention" in content.lower()


def test_frontmatter_type(tmp_path):
    mem = tmp_path / "memory"
    out = save_query_result("q", "a", mem, query_type="path_query")
    content = out.read_text()
    assert 'type: "path_query"' in content


def test_source_nodes_included(tmp_path):
    mem = tmp_path / "memory"
    nodes = ["AttentionLayer", "SoftmaxFunc"]
    out = save_query_result("q", "a", mem, source_nodes=nodes)
    content = out.read_text()
    assert "AttentionLayer" in content
    assert "SoftmaxFunc" in content


def test_source_nodes_capped_at_10(tmp_path):
    mem = tmp_path / "memory"
    nodes = [f"Node{i}" for i in range(20)]
    out = save_query_result("q", "a", mem, source_nodes=nodes)
    content = out.read_text()
    # Only first 10 should appear in frontmatter source_nodes line
    fm_line = [l for l in content.splitlines() if l.startswith("source_nodes:")][0]
    assert fm_line.count('"Node') == 10


def test_memory_dir_created(tmp_path):
    mem = tmp_path / "deep" / "memory"
    assert not mem.exists()
    save_query_result("q", "a", mem)
    assert mem.exists()


def test_answer_in_body(tmp_path):
    mem = tmp_path / "memory"
    answer = "The answer is forty-two."
    out = save_query_result("what is the answer?", answer, mem)
    content = out.read_text()
    assert answer in content

def test_outcome_in_frontmatter_and_body(tmp_path):
    """An outcome signal is written to both frontmatter (for `reflect`) and an
    ## Outcome body section (so it round-trips into the graph on re-extraction)."""
    out = save_query_result("q", "a", tmp_path / "memory", outcome="useful")
    content = out.read_text()
    assert 'outcome: "useful"' in content
    assert "## Outcome" in content
    assert "- Signal: useful" in content


def test_correction_in_frontmatter_and_body(tmp_path):
    out = save_query_result(
        "what hashes passwords?", "MD5", tmp_path / "memory",
        outcome="corrected", correction="It's bcrypt, see PasswordHasher",
    )
    content = out.read_text()
    assert 'correction: "It\'s bcrypt, see PasswordHasher"' in content
    assert "- Correction: It's bcrypt, see PasswordHasher" in content


def test_no_outcome_means_no_outcome_section(tmp_path):
    """Backward compatible: a result without an outcome looks exactly as before."""
    out = save_query_result("q", "a", tmp_path / "memory")
    content = out.read_text()
    assert "outcome:" not in content
    assert "## Outcome" not in content


def test_invalid_outcome_rejected(tmp_path):
    with pytest.raises(ValueError):
        save_query_result("q", "a", tmp_path / "memory", outcome="great")


def test_ingest_webpage_writes_markdown(tmp_path, monkeypatch):
    target = tmp_path / "raw"
    monkeypatch.setattr("graphify.ingest.validate_url", lambda _url: None)
    monkeypatch.setattr(
        "graphify.ingest._fetch_webpage",
        lambda _url, _author, _contributor: ("# Example", "example.md"),
    )

    out = ingest("https://example.com/docs", target)

    assert out == target / "example.md"
    assert out.read_text(encoding="utf-8") == "# Example"


def test_ingest_avoids_overwrite_with_counter(tmp_path, monkeypatch):
    target = tmp_path / "raw"
    target.mkdir(parents=True)
    (target / "example.md").write_text("existing", encoding="utf-8")
    monkeypatch.setattr("graphify.ingest.validate_url", lambda _url: None)
    monkeypatch.setattr(
        "graphify.ingest._fetch_webpage",
        lambda _url, _author, _contributor: ("# New", "example.md"),
    )

    out = ingest("https://example.com/docs", target)

    assert out.name == "example_1.md"
    assert out.read_text(encoding="utf-8") == "# New"


def test_ingest_pdf_path_uses_binary_downloader(tmp_path, monkeypatch):
    target = tmp_path / "raw"
    downloaded = target / "paper.pdf"
    monkeypatch.setattr("graphify.ingest.validate_url", lambda _url: None)
    monkeypatch.setattr("graphify.ingest._download_binary", lambda *_a, **_k: downloaded)

    out = ingest("https://example.com/paper.pdf", target)

    assert out == downloaded


def test_ingest_image_without_suffix_defaults_to_jpg(tmp_path, monkeypatch):
    target = tmp_path / "raw"
    monkeypatch.setattr("graphify.ingest.validate_url", lambda _url: None)
    monkeypatch.setattr("graphify.ingest._detect_url_type", lambda _url: "image")
    captured = {}

    def _fake_download(url: str, suffix: str, _target):
        captured["url"] = url
        captured["suffix"] = suffix
        return target / "img.jpg"

    monkeypatch.setattr("graphify.ingest._download_binary", _fake_download)

    out = ingest("https://example.com/image", target)

    assert out.name == "img.jpg"
    assert captured["suffix"] == ".jpg"


def test_ingest_invalid_url_is_wrapped(tmp_path, monkeypatch):
    target = tmp_path / "raw"

    def _raise_invalid(_url: str) -> None:
        raise ValueError("blocked")

    monkeypatch.setattr("graphify.ingest.validate_url", _raise_invalid)

    with pytest.raises(ValueError, match=r"^ingest: blocked$"):
        ingest("javascript:alert(1)", target)


def test_ingest_fetch_errors_are_wrapped(tmp_path, monkeypatch):
    target = tmp_path / "raw"
    monkeypatch.setattr("graphify.ingest.validate_url", lambda _url: None)

    def _raise_fetch(_url, _author, _contributor):
        raise urllib.error.URLError("timeout")

    monkeypatch.setattr("graphify.ingest._fetch_webpage", _raise_fetch)

    with pytest.raises(RuntimeError, match=r"^ingest: failed to fetch "):
        ingest("https://example.com", target)
