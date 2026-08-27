"""Offline CLI pipeline coverage for ``--backend copilot-sdk``."""
from __future__ import annotations

import json
import sys
import types

import graphify.__main__ as mainmod


def _run(monkeypatch, corpus, out_dir):
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _path: None)
    monkeypatch.setattr(
        mainmod.sys,
        "argv",
        [
            "graphify", "extract", str(corpus), "--backend", "copilot-sdk",
            "--no-cluster", "--out", str(out_dir),
        ],
    )
    try:
        mainmod.main()
    except SystemExit as exc:
        assert exc.code in (None, 0)


def test_extract_copilot_sdk_mocked_pipeline_and_incremental_cache(monkeypatch, tmp_path):
    # Python 3.10 intentionally does not install the 3.11+ SDK extra. The CLI
    # contract is otherwise version-independent, so provide only the import
    # marker that its preflight check needs.
    monkeypatch.setitem(sys.modules, "copilot", types.ModuleType("copilot"))
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "README.md").write_text("# Alpha\nAlpha calls Beta.\n")
    out_dir = tmp_path / "out"
    calls = {"count": 0}
    payload = {
        "nodes": [
            {"id": "alpha", "label": "Alpha", "file_type": "document", "source_file": "README.md"},
            {"id": "beta", "label": "Beta", "file_type": "document", "source_file": "README.md"},
        ],
        "edges": [{"source": "alpha", "target": "beta", "relation": "references", "source_file": "README.md"}],
        "hyperedges": [],
    }

    def fake_call(prompt, **kwargs):
        calls["count"] += 1
        assert "untrusted_source" in prompt
        assert kwargs["model"] is None
        return {"content": json.dumps(payload), "input_tokens": 10, "output_tokens": 6, "model": "test-model"}

    monkeypatch.setattr("graphify.copilot_sdk_backend.call_copilot_sdk", fake_call)
    for key in ("GEMINI_API_KEY", "GOOGLE_API_KEY", "MOONSHOT_API_KEY", "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "DEEPSEEK_API_KEY"):
        monkeypatch.delenv(key, raising=False)

    _run(monkeypatch, corpus, out_dir)
    graph_path = out_dir / "graphify-out" / "graph.json"
    cache_path = out_dir / "graphify-out" / "cache"
    assert graph_path.exists()
    graph = json.loads(graph_path.read_text())
    assert {node["id"] for node in graph["nodes"]} == {"alpha", "beta"}
    assert graph["edges"][0]["source_file"] == "README.md"
    assert calls["count"] == 1
    assert cache_path.exists()

    # Existing manifest + semantic cache means the second run does not call
    # Copilot again, while the normal graph output remains available.
    _run(monkeypatch, corpus, out_dir)
    assert calls["count"] == 1
    assert graph_path.exists()
