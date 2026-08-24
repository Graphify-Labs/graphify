"""Behavioral tests for native mixed-corpus ``graphify update``."""
from __future__ import annotations

import json

import pytest

import graphify.__main__ as mainmod


def _run_main(monkeypatch, argv: list[str]) -> None:
    monkeypatch.setattr(mainmod.sys, "argv", argv)
    try:
        mainmod.main()
    except SystemExit as exc:
        assert exc.code in (None, 0), f"unexpected exit code {exc.code}"


def test_help_distinguishes_semantic_and_code_only_updates(monkeypatch, capsys):
    monkeypatch.setattr(mainmod.sys, "argv", ["graphify", "--help"])

    mainmod.main()

    help_text = capsys.readouterr().out
    assert "update <path>" in help_text
    assert "--semantic" in help_text
    assert "documents" in help_text
    assert "LLM" in help_text


@pytest.mark.parametrize("incompatible", ["--no-cluster", "--code-only"])
def test_update_semantic_rejects_incomplete_modes(
    monkeypatch, tmp_path, capsys, incompatible
):
    (tmp_path / "app.py").write_text("value = 1\n")
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)
    monkeypatch.setattr(
        mainmod.sys,
        "argv",
        ["graphify", "update", str(tmp_path), "--semantic", incompatible],
    )

    with pytest.raises(SystemExit) as exc_info:
        mainmod.main()

    assert exc_info.value.code == 2
    assert "cannot be combined" in capsys.readouterr().err


def test_update_semantic_defaults_to_current_directory(monkeypatch, tmp_path):
    (tmp_path / "app.py").write_text("value = 1\n")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)

    _run_main(
        monkeypatch,
        ["graphify", "update", "--semantic", "--no-label", "--no-viz"],
    )

    assert (tmp_path / "graphify-out" / "GRAPH_REPORT.md").is_file()


def test_update_semantic_accepts_path_after_flags(monkeypatch, tmp_path):
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "app.py").write_text("value = 1\n")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)

    _run_main(
        monkeypatch,
        [
            "graphify",
            "update",
            "--semantic",
            "--no-label",
            "--no-viz",
            str(corpus),
        ],
    )

    assert (corpus / "graphify-out" / "GRAPH_REPORT.md").is_file()


def test_update_semantic_rejects_unknown_options(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)
    monkeypatch.setattr(
        mainmod.sys,
        "argv",
        ["graphify", "update", str(tmp_path), "--semantic", "--typo"],
    )

    with pytest.raises(SystemExit) as exc_info:
        mainmod.main()

    assert exc_info.value.code == 2
    assert "unknown semantic update option: --typo" in capsys.readouterr().err


def test_update_semantic_refreshes_changed_docs_and_final_outputs(
    monkeypatch, tmp_path, capsys
):
    """One command refreshes mixed code/docs through the report stage.

    The third unchanged run also proves that the native update path retains
    extract's incremental cache instead of paying to re-extract the document.
    """
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "app.py").write_text("def answer():\n    return 42\n")
    guide = corpus / "guide.md"
    guide.write_text("# Guide\nVersion one explains the answer.\n")

    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-fake-key")
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)
    calls: list[tuple[str, str]] = []

    def _extract_docs(paths, **kwargs):
        text = paths[0].read_text()
        version = "v2" if "Version two" in text else "v1"
        calls.append((version, kwargs["backend"]))
        chunk = {
            "nodes": [
                {
                    "id": f"guide_{version}",
                    "label": f"Guide {version}",
                    "type": "concept",
                    "source_file": "guide.md",
                    "file_type": "document",
                }
            ],
            "edges": [],
            "hyperedges": [],
        }
        on_chunk = kwargs.get("on_chunk_done")
        if on_chunk:
            on_chunk(0, 1, chunk)
        return {**chunk, "input_tokens": 10, "output_tokens": 5}

    monkeypatch.setattr("graphify.llm.extract_corpus_parallel", _extract_docs)
    command = [
        "graphify",
        "update",
        str(corpus),
        "--semantic",
        "--backend",
        "claude",
        "--no-label",
        "--no-viz",
        "--no-dedup",
        "--min-community-size=1",
    ]

    _run_main(monkeypatch, command)

    out = corpus / "graphify-out"
    graph = json.loads((out / "graph.json").read_text())
    first_nodes = graph["nodes"]
    assert "guide_v1" in {node["id"] for node in first_nodes}
    assert any(node.get("source_file") == "app.py" for node in first_nodes)
    assert (out / "GRAPH_REPORT.md").is_file()
    assert "Guide v1" in (out / "GRAPH_REPORT.md").read_text()
    assert not (out / ".graphify_labels.json").exists()
    assert not (out / "graph.html").exists()

    guide.write_text("# Guide\nVersion two explains the answer.\n")
    _run_main(monkeypatch, command)

    graph = json.loads((out / "graph.json").read_text())
    node_ids = {node["id"] for node in graph["nodes"]}
    assert "guide_v2" in node_ids
    assert "guide_v1" not in node_ids
    report = (out / "GRAPH_REPORT.md").read_text()
    assert "Guide v2" in report
    assert "Guide v1" not in report

    _run_main(monkeypatch, command)

    assert calls == [("v1", "claude"), ("v2", "claude")]
    assert not (out / "graph.html").exists()
    assert "semantic update complete" in capsys.readouterr().out.lower()
