"""Tests for LLM-backed community labeling (issue #1097).

Backend calls are mocked - no network. Covers the happy path, partial replies,
malformed replies, and the no-backend fallback.
"""
import json
import sys

import networkx as nx
import pytest

from graphify.llm import label_communities, generate_community_labels


def _graph():
    G = nx.Graph()
    # community 0 = ordering, community 1 = payments
    G.add_node("order_place", label="place_order")
    G.add_node("order_repo", label="OrderRepository")
    G.add_node("pay_charge", label="charge_card")
    G.add_node("pay_stripe", label="StripeClient")
    communities = {0: ["order_place", "order_repo"], 1: ["pay_charge", "pay_stripe"]}
    return G, communities


def test_label_communities_happy_path(monkeypatch):
    G, communities = _graph()

    captured = {}

    def fake_call(prompt, *, backend, max_tokens=200):
        captured["prompt"] = prompt
        captured["backend"] = backend
        return '{"0": "Order Management", "1": "Payment Flow"}'

    monkeypatch.setattr("graphify.llm._call_llm", fake_call)
    labels = label_communities(G, communities, backend="gemini")

    assert labels == {0: "Order Management", 1: "Payment Flow"}
    # the prompt must carry the real node labels so the model can name them
    assert "place_order" in captured["prompt"]
    assert "StripeClient" in captured["prompt"]
    assert captured["backend"] == "gemini"


def test_label_communities_passes_model_override(monkeypatch):
    G, communities = _graph()
    captured = {}

    def fake_call(prompt, *, backend, max_tokens=200, model=None):
        captured["backend"] = backend
        captured["model"] = model
        return '{"0": "Order Management", "1": "Payment Flow"}'

    monkeypatch.setattr("graphify.llm._call_llm", fake_call)
    labels = label_communities(
        G,
        communities,
        backend="gemini",
        model="gemini-3.1-flash-lite",
    )

    assert labels == {0: "Order Management", 1: "Payment Flow"}
    assert captured == {"backend": "gemini", "model": "gemini-3.1-flash-lite"}


def test_label_cli_passes_model_override(tmp_path, monkeypatch):
    import graphify.__main__ as cli

    out = tmp_path / "graphify-out"
    out.mkdir()
    graph = {
        "directed": False,
        "multigraph": False,
        "nodes": [
            {"id": "n1", "label": "OrderService", "community": 0},
        ],
        "links": [],
    }
    (out / "graph.json").write_text(json.dumps(graph), encoding="utf-8")

    captured = {}

    def fake_generate(G, communities, *, backend=None, model=None, gods=None, quiet=False):
        captured["backend"] = backend
        captured["model"] = model
        return {0: "Orders"}, "llm"

    monkeypatch.setattr("graphify.llm.generate_community_labels", fake_generate)
    monkeypatch.setattr("graphify.export.to_html", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "graphify",
            "label",
            str(tmp_path),
            "--backend",
            "gemini",
            "--model",
            "gemini-3.1-flash-lite",
            "--no-viz",
        ],
    )

    cli.main()

    assert captured == {"backend": "gemini", "model": "gemini-3.1-flash-lite"}


def test_label_communities_partial_reply_fills_placeholder(monkeypatch):
    G, communities = _graph()
    monkeypatch.setattr("graphify.llm._call_llm",
                        lambda p, *, backend, max_tokens=200: '{"0": "Order Management"}')
    labels = label_communities(G, communities, backend="gemini")
    assert labels[0] == "Order Management"
    assert labels[1] == "Community 1"   # missing cid falls back


def test_label_communities_strips_code_fences(monkeypatch):
    G, communities = _graph()
    monkeypatch.setattr(
        "graphify.llm._call_llm",
        lambda p, *, backend, max_tokens=200: '```json\n{"0":"Orders","1":"Pay"}\n```',
    )
    labels = label_communities(G, communities, backend="gemini")
    assert labels == {0: "Orders", 1: "Pay"}


def test_label_communities_malformed_raises(monkeypatch):
    G, communities = _graph()
    monkeypatch.setattr("graphify.llm._call_llm",
                        lambda p, *, backend, max_tokens=200: "sorry, I cannot help")
    with pytest.raises(Exception):
        label_communities(G, communities, backend="gemini")


def test_generate_community_labels_degrades_on_error(monkeypatch):
    G, communities = _graph()
    monkeypatch.setattr("graphify.llm._call_llm",
                        lambda p, *, backend, max_tokens=200: "not json")
    labels, source = generate_community_labels(G, communities, backend="gemini", quiet=True)
    assert source == "placeholder"
    assert labels == {0: "Community 0", 1: "Community 1"}


def test_generate_community_labels_no_backend(monkeypatch):
    G, communities = _graph()
    monkeypatch.setattr("graphify.llm.detect_backend", lambda: None)
    labels, source = generate_community_labels(G, communities, backend=None, quiet=True)
    assert source == "placeholder"
    assert labels == {0: "Community 0", 1: "Community 1"}


def test_generate_community_labels_success(monkeypatch):
    G, communities = _graph()
    monkeypatch.setattr("graphify.llm._call_llm",
                        lambda p, *, backend, max_tokens=200: '{"0":"Orders","1":"Payments"}')
    labels, source = generate_community_labels(G, communities, backend="gemini", quiet=True)
    assert source == "llm"
    assert labels == {0: "Orders", 1: "Payments"}


def test_gods_as_dicts_do_not_crash(monkeypatch):
    """god_nodes() returns list[dict] with an 'id' key, not bare ids."""
    G, communities = _graph()
    monkeypatch.setattr("graphify.llm._call_llm",
                        lambda p, *, backend, max_tokens=200: '{"0":"Orders","1":"Pay"}')
    gods = [{"id": "order_repo", "label": "OrderRepository"}]
    labels = label_communities(G, communities, backend="gemini", gods=gods)
    assert labels == {0: "Orders", 1: "Pay"}


def test_empty_communities_returns_placeholders(monkeypatch):
    G = nx.Graph()
    called = False

    def fake_call(p, *, backend, max_tokens=200):
        nonlocal called
        called = True
        return "{}"

    monkeypatch.setattr("graphify.llm._call_llm", fake_call)
    # community with no resolvable nodes -> no prompt line -> no backend call
    labels = label_communities(G, {0: []}, backend="gemini")
    assert labels == {0: "Community 0"}
    assert called is False


# ---------------------------------------------------------------------------
# Multi-batch labeling: a single prompt with >100 communities overflows the
# 16k context window of self-hosted reasoning models (Qwen3, Llama-3.1 8B).
# label_communities now splits into batches so coverage stays complete.
# ---------------------------------------------------------------------------


def _wide_graph(n_communities: int):
    G = nx.Graph()
    communities: dict[int, list[str]] = {}
    for cid in range(n_communities):
        a, b = f"c{cid}_a", f"c{cid}_b"
        G.add_node(a, label=f"node_{cid}_a")
        G.add_node(b, label=f"node_{cid}_b")
        communities[cid] = [a, b]
    return G, communities


def test_label_communities_batches_when_over_batch_size(monkeypatch):
    G, communities = _wide_graph(250)
    calls = []

    def fake_call(prompt, *, backend, max_tokens=200):
        # The fake reads which cids the prompt asks about and answers all of them.
        cids = [int(line.split(":", 1)[0].removeprefix("Community ").strip())
                for line in prompt.splitlines() if line.startswith("Community ")]
        calls.append(len(cids))
        return "{" + ", ".join(f'"{c}": "Cluster {c}"' for c in cids) + "}"

    monkeypatch.setattr("graphify.llm._call_llm", fake_call)
    labels = label_communities(G, communities, backend="gemini", batch_size=100)

    # 250 communities / 100 per batch -> 3 batches (100, 100, 50)
    assert calls == [100, 100, 50]
    # And every community got a real name, none left as a placeholder.
    assert all(name.startswith("Cluster ") for name in labels.values()), \
        f"some communities still have placeholders: {[k for k, v in labels.items() if not v.startswith('Cluster ')][:5]}"
    assert len(labels) == 250


def test_label_communities_partial_batch_failure_keeps_successful_batches(monkeypatch):
    G, communities = _wide_graph(150)
    n_calls = [0]

    def fake_call(prompt, *, backend, max_tokens=200):
        n_calls[0] += 1
        cids = [int(line.split(":", 1)[0].removeprefix("Community ").strip())
                for line in prompt.splitlines() if line.startswith("Community ")]
        if n_calls[0] == 2:
            raise RuntimeError("simulated transient backend failure")
        return "{" + ", ".join(f'"{c}": "Named {c}"' for c in cids) + "}"

    monkeypatch.setattr("graphify.llm._call_llm", fake_call)
    labels = label_communities(G, communities, backend="gemini", batch_size=50)

    # 3 batches; second one fails. First and third produce real labels;
    # the failed batch's cids stay as placeholders.
    real = [cid for cid, name in labels.items() if name.startswith("Named ")]
    placeholder = [cid for cid, name in labels.items() if name.startswith("Community ")]
    assert len(real) == 100, f"expected 100 real labels from 2 successful batches, got {len(real)}"
    assert len(placeholder) == 50, f"expected 50 placeholders from the failed batch, got {len(placeholder)}"


def test_label_communities_all_batches_fail_raises(monkeypatch):
    G, communities = _wide_graph(150)

    def always_fail(prompt, *, backend, max_tokens=200):
        raise RuntimeError("backend down")

    monkeypatch.setattr("graphify.llm._call_llm", always_fail)
    # Every batch fails -> propagate so generate_community_labels can degrade.
    with pytest.raises(RuntimeError, match="backend down"):
        label_communities(G, communities, backend="gemini", batch_size=50)


def test_label_communities_max_communities_caps_total(monkeypatch):
    # Backwards compat: explicit max_communities still caps the total labeled,
    # so callers that pinned the legacy 200-default keep their behavior.
    G, communities = _wide_graph(150)
    captured_cids = []

    def fake_call(prompt, *, backend, max_tokens=200):
        cids = [int(line.split(":", 1)[0].removeprefix("Community ").strip())
                for line in prompt.splitlines() if line.startswith("Community ")]
        captured_cids.extend(cids)
        return "{" + ", ".join(f'"{c}": "X{c}"' for c in cids) + "}"

    monkeypatch.setattr("graphify.llm._call_llm", fake_call)
    label_communities(G, communities, backend="gemini", max_communities=40, batch_size=100)
    # Only 40 communities should have been sent to the backend.
    assert len(captured_cids) == 40
