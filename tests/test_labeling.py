"""Tests for LLM-backed community labeling (issue #1097).

Backend calls are mocked - no network. Covers the happy path, partial replies,
malformed replies, and the no-backend fallback.
"""
import json
import re
import sys
from pathlib import Path

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

    def fake_generate(G, communities, *, backend=None, model=None, gods=None,
                      quiet=False, max_concurrency=4, batch_size=100, usage_out=None):
        captured["backend"] = backend
        captured["model"] = model
        captured["max_concurrency"] = max_concurrency
        captured["batch_size"] = batch_size
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
            "--max-concurrency",
            "8",
            "--batch-size",
            "50",
            "--no-viz",
        ],
    )

    cli.main()

    # Also verifies the space-separated forms parse (the value must not be mistaken
    # for the positional path) and reach generate_community_labels.
    assert captured == {
        "backend": "gemini", "model": "gemini-3.1-flash-lite",
        "max_concurrency": 8, "batch_size": 50,
    }


def test_label_cli_missing_only_preserves_existing_labels(tmp_path, monkeypatch):
    import graphify.__main__ as cli

    out = tmp_path / "graphify-out"
    out.mkdir()
    graph = {
        "directed": False,
        "multigraph": False,
        "nodes": [
            {"id": "orders", "label": "OrderService", "community": 0},
            {"id": "payments", "label": "PaymentService", "community": 1},
        ],
        "links": [],
    }
    (out / "graph.json").write_text(json.dumps(graph), encoding="utf-8")
    (out / ".graphify_labels.json").write_text(
        json.dumps({"0": "Order Management", "1": "Community 1"}),
        encoding="utf-8",
    )

    captured = {}

    def fake_generate(G, communities, *, backend=None, model=None, gods=None,
                      quiet=False, max_concurrency=4, batch_size=100, usage_out=None):
        captured["communities"] = dict(communities)
        return {1: "Payment Flow"}, "llm"

    monkeypatch.setattr("graphify.llm.generate_community_labels", fake_generate)
    monkeypatch.setattr("graphify.export.to_html", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        sys,
        "argv",
        ["graphify", "label", str(tmp_path), "--missing-only", "--backend", "gemini", "--no-viz"],
    )

    cli.main()

    assert set(captured["communities"]) == {1}
    labels = json.loads((out / ".graphify_labels.json").read_text(encoding="utf-8"))
    assert labels == {"0": "Order Management", "1": "Payment Flow"}


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
    # Keep hermetic: the claude-cli labelling fallback (#3475) probes PATH, so a
    # machine with `claude` installed would otherwise take the CLI path here.
    monkeypatch.setattr("graphify.llm._claude_cli_available", lambda: False)
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


def test_generate_community_labels_warns_on_partial_success(monkeypatch, capsys):
    G, communities = _graph()
    monkeypatch.setattr(
        "graphify.llm.label_communities",
        lambda *args, **kwargs: {0: "Orders", 1: "Community 1"},
    )

    labels, source = generate_community_labels(G, communities, backend="gemini")

    assert source == "llm"
    assert labels == {0: "Orders", 1: "Community 1"}
    assert "labeled 1 of 2 communities" in capsys.readouterr().err


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
        # #2534: prompt lines are now "<cid>: <names>" — the old "Community {cid}:"
        # key collided with the placeholder sentinel and echoed keys were dropped.
        cids = [int(m.group(1)) for m in
                (re.match(r"^(\d+): ", line) for line in prompt.splitlines()) if m]
        calls.append(len(cids))
        return "{" + ", ".join(f'"{c}": "Cluster {c}"' for c in cids) + "}"

    monkeypatch.setattr("graphify.llm._call_llm", fake_call)
    # max_concurrency=1 keeps the batches sequential so `calls` records them in a
    # deterministic order; the default concurrent path can complete them out of
    # order (the ordering is asserted separately in
    # test_label_communities_parallel_matches_sequential).
    labels = label_communities(G, communities, backend="gemini", batch_size=100, max_concurrency=1)

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
        # #2534: prompt lines are now "<cid>: <names>" — the old "Community {cid}:"
        # key collided with the placeholder sentinel and echoed keys were dropped.
        cids = [int(m.group(1)) for m in
                (re.match(r"^(\d+): ", line) for line in prompt.splitlines()) if m]
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
        # #2534: prompt lines are now "<cid>: <names>" — the old "Community {cid}:"
        # key collided with the placeholder sentinel and echoed keys were dropped.
        cids = [int(m.group(1)) for m in
                (re.match(r"^(\d+): ", line) for line in prompt.splitlines()) if m]
        captured_cids.extend(cids)
        return "{" + ", ".join(f'"{c}": "X{c}"' for c in cids) + "}"

    monkeypatch.setattr("graphify.llm._call_llm", fake_call)
    label_communities(G, communities, backend="gemini", max_communities=40, batch_size=100)
    # Only 40 communities should have been sent to the backend.
    assert len(captured_cids) == 40


# --- #1390: parallel labeling (--max-concurrency) + --batch-size --------------

import threading
import time as _time


def _many_communities(n):
    G = nx.Graph()
    comms = {}
    for i in range(n):
        nid = f"n{i}"
        G.add_node(nid, label=f"sym_{i}")
        comms[i] = [nid]
    return G, comms


def test_label_communities_parallel_matches_sequential(monkeypatch):
    """Concurrency must not change the result: same cid->name map either way."""
    G, communities = _many_communities(6)

    def fake_batch(batch_cids, batch_lines, *, backend, model=None):
        return {cid: f"name-{cid}" for cid in batch_cids}

    monkeypatch.setattr("graphify.llm._label_batch_with_retry", fake_batch)
    seq = label_communities(G, communities, backend="gemini", batch_size=1, max_concurrency=1)
    par = label_communities(G, communities, backend="gemini", batch_size=1, max_concurrency=4)
    assert seq == par == {i: f"name-{i}" for i in range(6)}


def test_label_communities_batch_size_controls_batch_count(monkeypatch):
    G, communities = _many_communities(5)
    calls = []

    def fake_batch(batch_cids, batch_lines, *, backend, model=None):
        calls.append(list(batch_cids))
        return {cid: f"n-{cid}" for cid in batch_cids}

    monkeypatch.setattr("graphify.llm._label_batch_with_retry", fake_batch)
    labels = label_communities(G, communities, backend="gemini", batch_size=2, max_concurrency=1)
    assert len(calls) == 3                       # 5 communities / batch 2 -> 3 batches
    assert sum(len(c) for c in calls) == 5
    assert labels == {i: f"n-{i}" for i in range(5)}


def _peak_tracker():
    lock = threading.Lock()
    state = {"now": 0, "peak": 0}

    def fake_batch(batch_cids, batch_lines, *, backend, model=None):
        with lock:
            state["now"] += 1
            state["peak"] = max(state["peak"], state["now"])
        _time.sleep(0.03)
        with lock:
            state["now"] -= 1
        return {cid: f"n-{cid}" for cid in batch_cids}

    return fake_batch, state


def test_label_communities_runs_batches_concurrently(monkeypatch):
    G, communities = _many_communities(8)
    fake_batch, state = _peak_tracker()
    monkeypatch.setattr("graphify.llm._label_batch_with_retry", fake_batch)
    label_communities(G, communities, backend="gemini", batch_size=1, max_concurrency=4)
    assert state["peak"] > 1, "batches should run in parallel with max_concurrency>1"


def test_label_communities_forces_serial_for_ollama(monkeypatch):
    """ollama/claude-cli must stay serial regardless of --max-concurrency."""
    G, communities = _many_communities(8)
    fake_batch, state = _peak_tracker()
    monkeypatch.setattr("graphify.llm._label_batch_with_retry", fake_batch)
    monkeypatch.delenv("GRAPHIFY_OLLAMA_PARALLEL", raising=False)
    label_communities(G, communities, backend="ollama", batch_size=1, max_concurrency=8)
    assert state["peak"] == 1, "ollama must be forced serial"


def test_label_communities_salvages_truncated_reply(monkeypatch):
    # #1690: a reply truncated mid-object (a stingy token budget or model
    # preamble) used to hard-fail the whole batch with `Expecting value: line 1
    # column 6`. The complete pairs that arrived are now salvaged.
    G, communities = _graph()
    monkeypatch.setattr(
        "graphify.llm._call_llm",
        lambda p, *, backend, max_tokens=200: '{"0": "Order Management", "1":',
    )
    labels = label_communities(G, communities, backend="gemini")
    assert labels[0] == "Order Management"   # salvaged
    assert labels[1] == "Community 1"         # truncated cid falls back to placeholder


def test_label_communities_accumulates_token_usage(monkeypatch):
    # #1694: cluster-only mode reported zero labeling cost because token usage
    # from the naming LLM calls was never accumulated. label_communities now
    # fills a caller-supplied usage_out accumulator, summed across all batches.
    G, communities = _many_communities(6)

    def fake_call(prompt, *, backend, max_tokens=200, usage_out=None):
        if usage_out is not None:
            usage_out["input"] = usage_out.get("input", 0) + 100
            usage_out["output"] = usage_out.get("output", 0) + 10
        # one name per community id present in this batch
        cids = []
        for line in prompt.splitlines():
            if line.startswith("Community "):
                cids.append(int(line.split()[1].rstrip(":")))
            elif re.match(r"^\d+: ", line):
                cids.append(int(line.split(":", 1)[0]))
        return json.dumps({str(c): f"Name {c}" for c in cids})

    monkeypatch.setattr("graphify.llm._call_llm", fake_call)
    usage = {"input": 0, "output": 0}
    # batch_size=2 -> 3 batches, run serially so the count is deterministic
    labels = label_communities(
        G, communities, backend="gemini", batch_size=2, max_concurrency=1,
        usage_out=usage,
    )
    assert len(labels) == 6
    assert usage == {"input": 300, "output": 30}  # 3 batches * (100, 10)


def test_label_communities_counts_tokens_for_failed_batch(monkeypatch):
    # A batch whose reply can't be parsed was still billed by the provider, so
    # its tokens must be counted even though it contributes no label (#1694).
    G, communities = _graph()

    def fake_call(prompt, *, backend, max_tokens=200, usage_out=None):
        if usage_out is not None:
            usage_out["input"] = usage_out.get("input", 0) + 50
            usage_out["output"] = usage_out.get("output", 0) + 5
        return "not json at all"

    monkeypatch.setattr("graphify.llm._call_llm", fake_call)
    usage = {"input": 0, "output": 0}
    # single community -> no split retry; the only batch fails to parse, so
    # label_communities re-raises (every batch failed) after counting tokens.
    G2 = nx.Graph()
    G2.add_node("a", label="alpha")
    with pytest.raises((ValueError, json.JSONDecodeError)):
        label_communities(
            G2, {0: ["a"]}, backend="gemini", usage_out=usage,
        )
    assert usage == {"input": 50, "output": 5}


def _two_community_graph(out):
    """Two disconnected components -> two stable communities, each hub-labelled
    by its own node."""
    graph = {
        "directed": False, "multigraph": False,
        "nodes": [
            {"id": "orders", "label": "OrderService", "community": 0},
            {"id": "order_db", "label": "OrderDB", "community": 0},
            {"id": "payments", "label": "PaymentService", "community": 1},
            {"id": "pay_db", "label": "PayDB", "community": 1},
        ],
        "links": [
            {"source": "orders", "target": "order_db", "relation": "calls"},
            {"source": "payments", "target": "pay_db", "relation": "calls"},
        ],
    }
    (out / "graph.json").write_text(json.dumps(graph), encoding="utf-8")


@pytest.mark.parametrize("command", ["cluster-only", "label"])
def test_cluster_commands_render_aggregated_html_above_viz_limit(
    tmp_path, monkeypatch, capsys, command,
):
    """#2853: relabeling a large graph must keep a current aggregated HTML."""
    import graphify.__main__ as cli

    out = tmp_path / "graphify-out"
    out.mkdir()
    _two_community_graph(out)
    html = out / "graph.html"
    html.write_text("stale visualization", encoding="utf-8")

    monkeypatch.setenv("GRAPHIFY_VIZ_NODE_LIMIT", "3")
    monkeypatch.setattr(cli, "_check_skill_version", lambda _: None)
    monkeypatch.setattr(
        "graphify.llm.generate_community_labels",
        lambda G, comms, **kwargs: (
            {cid: f"Fresh community {cid}" for cid in comms},
            "test",
        ),
    )

    argv = ["graphify", command, str(tmp_path)]
    if command == "cluster-only":
        argv.append("--no-label")
    monkeypatch.setattr(sys, "argv", argv)

    cli.main()

    output = capsys.readouterr().out
    assert html.exists()
    assert not (out / ".graph.html.stale").exists()
    rendered = html.read_text(encoding="utf-8")
    assert "stale visualization" not in rendered
    if command == "label":
        assert "Fresh community" in rendered
    assert "aggregated" in output
    assert "graph.html updated" in output


def test_cluster_only_preserves_but_does_not_claim_unusable_aggregate(
    tmp_path, monkeypatch, capsys,
):
    """A skipped aggregate must not race with or falsely claim an HTML write."""
    import importlib
    import graphify.__main__ as cli

    out = tmp_path / "graphify-out"
    out.mkdir()
    _two_community_graph(out)
    html = out / "graph.html"
    html.write_text("stale visualization", encoding="utf-8")

    monkeypatch.setenv("GRAPHIFY_VIZ_NODE_LIMIT", "3")
    monkeypatch.setattr(cli, "_check_skill_version", lambda _: None)
    monkeypatch.setattr(
        importlib.import_module("graphify.cluster"),
        "cluster",
        lambda G, **kwargs: {0: list(G.nodes())},
    )
    monkeypatch.setattr(
        sys,
        "argv",
        ["graphify", "cluster-only", str(tmp_path), "--no-label"],
    )

    cli.main()

    output = capsys.readouterr().out
    assert html.read_text(encoding="utf-8") == "stale visualization"
    assert (out / ".graph.html.stale").exists()
    assert "Skipped graph.html" in output
    assert "existing graph.html left unchanged" in output
    assert "graph.html updated" not in output


def test_cluster_only_restores_html_after_unexpected_render_failure(
    tmp_path, monkeypatch,
):
    """A failed render must not destroy the previous HTML file."""
    import importlib
    import graphify.__main__ as cli

    out = tmp_path / "graphify-out"
    out.mkdir()
    _two_community_graph(out)
    html = out / "graph.html"
    html.write_text("previous visualization", encoding="utf-8")

    def fail_render(*args, **kwargs):
        raise OSError("simulated render failure")

    monkeypatch.setenv("GRAPHIFY_VIZ_NODE_LIMIT", "3")
    monkeypatch.setattr(cli, "_check_skill_version", lambda _: None)
    monkeypatch.setattr(
        importlib.import_module("graphify.export"),
        "to_html",
        fail_render,
    )
    monkeypatch.setattr(
        sys,
        "argv",
        ["graphify", "cluster-only", str(tmp_path), "--no-label"],
    )

    with pytest.raises(OSError, match="simulated render failure"):
        cli.main()

    assert html.read_text(encoding="utf-8") == "previous visualization"
    assert (out / ".graph.html.stale").exists()
    assert not list(out.glob(".graph.html.*.previous"))


def test_cluster_only_marks_html_stale_before_report_generation(
    tmp_path, monkeypatch,
):
    """An interruption after graph.json advances must remain repairable."""
    import graphify.__main__ as cli
    from graphify.watch import _reconcile_graph_html

    out = tmp_path / "graphify-out"
    out.mkdir()
    _two_community_graph(out)
    html = out / "graph.html"
    html.write_text("previous visualization", encoding="utf-8")

    def interrupt_report(*args, **kwargs):
        raise KeyboardInterrupt

    monkeypatch.setenv("GRAPHIFY_VIZ_NODE_LIMIT", "3")
    monkeypatch.setattr(cli, "_check_skill_version", lambda _: None)
    monkeypatch.setattr("graphify.report.generate", interrupt_report)
    monkeypatch.setattr(
        sys,
        "argv",
        ["graphify", "cluster-only", str(tmp_path), "--no-label"],
    )

    with pytest.raises(KeyboardInterrupt):
        cli.main()

    marker = out / ".graph.html.stale"
    assert html.read_text(encoding="utf-8") == "previous visualization"
    assert marker.exists()

    persisted = json.loads((out / "graph.json").read_text(encoding="utf-8"))
    assert _reconcile_graph_html(out, persisted) == "rendered"
    assert html.read_text(encoding="utf-8") != "previous visualization"
    assert not marker.exists()


def test_cluster_only_refused_graph_write_preserves_existing_stale_marker(
    tmp_path, monkeypatch,
):
    """A refused write must not erase retry state owned by an earlier run."""
    import graphify.__main__ as cli

    out = tmp_path / "graphify-out"
    out.mkdir()
    _two_community_graph(out)
    html = out / "graph.html"
    html.write_text("known stale visualization", encoding="utf-8")
    marker = out / ".graph.html.stale"
    marker.touch()

    monkeypatch.setattr(cli, "_check_skill_version", lambda _: None)
    monkeypatch.setattr("graphify.export.to_json", lambda *args, **kwargs: False)
    monkeypatch.setattr(
        sys,
        "argv",
        ["graphify", "cluster-only", str(tmp_path), "--no-label"],
    )

    with pytest.raises(SystemExit) as stopped:
        cli.main()

    assert stopped.value.code == 1
    assert html.read_text(encoding="utf-8") == "known stale visualization"
    assert marker.exists()


def test_cluster_only_succeeds_when_stale_marker_cleanup_fails(
    tmp_path, monkeypatch, capsys,
):
    """A completed HTML replacement must remain a successful command."""
    import graphify.__main__ as cli

    out = tmp_path / "graphify-out"
    out.mkdir()
    _two_community_graph(out)
    html = out / "graph.html"
    html.write_text("stale visualization", encoding="utf-8")
    marker = out / ".graph.html.stale"
    marker.touch()
    original_unlink = Path.unlink

    def reject_marker_unlink(path, *args, **kwargs):
        if path == marker:
            raise PermissionError("simulated marker cleanup failure")
        return original_unlink(path, *args, **kwargs)

    monkeypatch.setenv("GRAPHIFY_VIZ_NODE_LIMIT", "3")
    monkeypatch.setattr(cli, "_check_skill_version", lambda _: None)
    monkeypatch.setattr(Path, "unlink", reject_marker_unlink)
    monkeypatch.setattr(
        sys,
        "argv",
        ["graphify", "cluster-only", str(tmp_path), "--no-label"],
    )

    cli.main()

    captured = capsys.readouterr()
    assert html.read_text(encoding="utf-8") != "stale visualization"
    assert marker.exists()
    assert "graph.html updated" in captured.out
    assert "stale marker could not be cleared" in captured.err


def test_cluster_only_does_not_erase_concurrent_html_after_failure(
    tmp_path, monkeypatch,
):
    """A failing renderer must not roll back a concurrent successful writer."""
    import importlib
    import graphify.__main__ as cli

    out = tmp_path / "graphify-out"
    out.mkdir()
    _two_community_graph(out)
    html = out / "graph.html"
    html.write_text("previous visualization", encoding="utf-8")

    def concurrent_then_fail(*args, **kwargs):
        html.write_text("newer concurrent visualization", encoding="utf-8")
        raise OSError("simulated render failure")

    monkeypatch.setenv("GRAPHIFY_VIZ_NODE_LIMIT", "3")
    monkeypatch.setattr(cli, "_check_skill_version", lambda _: None)
    monkeypatch.setattr(
        importlib.import_module("graphify.export"),
        "to_html",
        concurrent_then_fail,
    )
    monkeypatch.setattr(
        sys,
        "argv",
        ["graphify", "cluster-only", str(tmp_path), "--no-label"],
    )

    with pytest.raises(OSError, match="simulated render failure"):
        cli.main()

    assert html.read_text(encoding="utf-8") == "newer concurrent visualization"


def test_cluster_only_no_label_does_not_persist_placeholders(tmp_path, monkeypatch):
    """#2073: --no-label must not write .graphify_labels.json with 'Community N'
    placeholders (which the reuse path would then treat as fresh forever). A
    later normal run must produce real (non-placeholder) labels."""
    import graphify.__main__ as cli
    out = tmp_path / "graphify-out"
    out.mkdir()
    _two_community_graph(out)
    labels_path = out / ".graphify_labels.json"

    monkeypatch.setattr(cli, "_check_skill_version", lambda _: None)
    monkeypatch.setattr("graphify.export.to_html", lambda *a, **k: None)
    # No-backend fallback shape: returns placeholders, which must not clobber hubs.
    monkeypatch.setattr("graphify.llm.generate_community_labels",
                        lambda G, comms, **k: ({cid: f"Community {cid}" for cid in comms}, "none"))

    monkeypatch.setattr(sys, "argv", ["graphify", "cluster-only", str(tmp_path), "--no-label", "--no-viz"])
    cli.main()
    assert not labels_path.exists(), "--no-label persisted a placeholder labels file (#2073)"
    assert not (out / ".graphify_labels.json.sig").exists()

    # A later normal run generates real labels (no sticky placeholders blocking it).
    monkeypatch.setattr(sys, "argv", ["graphify", "cluster-only", str(tmp_path), "--no-viz"])
    cli.main()
    assert labels_path.exists()
    saved = json.loads(labels_path.read_text(encoding="utf-8"))
    assert saved, "no labels written on the normal run"
    assert not any(v == f"Community {k}" for k, v in saved.items()), (
        f"real labels expected, got placeholders: {saved} (#2073)"
    )


def test_cluster_only_heals_persisted_placeholder_but_reuses_genuine(tmp_path, monkeypatch):
    """#2073: an already-polluted sidecar (a placeholder for one community, a
    genuine label for another) self-heals — the placeholder is replaced by the
    hub name while the genuine label is reused, with no LLM call."""
    import graphify.__main__ as cli
    out = tmp_path / "graphify-out"
    out.mkdir()
    _two_community_graph(out)
    labels_path = out / ".graphify_labels.json"
    # Polluted state: community 0 is a stuck placeholder, community 1 is genuine.
    labels_path.write_text(json.dumps({"0": "Community 0", "1": "Payment Flow"}), encoding="utf-8")

    monkeypatch.setattr(cli, "_check_skill_version", lambda _: None)
    monkeypatch.setattr("graphify.export.to_html", lambda *a, **k: None)
    def _fail_generate(*a, **k):
        raise AssertionError("generate_community_labels must not be called on the reuse path")
    monkeypatch.setattr("graphify.llm.generate_community_labels", _fail_generate)

    monkeypatch.setattr(sys, "argv", ["graphify", "cluster-only", str(tmp_path), "--no-viz"])
    cli.main()
    saved = json.loads(labels_path.read_text(encoding="utf-8"))
    assert saved["0"] != "Community 0", "stuck placeholder was not healed (#2073)"
    assert saved["1"] == "Payment Flow", "genuine label was not reused"


# ── #2534 case 2: prompt key must not collide with the placeholder sentinel ──


def test_label_prompt_lines_use_bare_cid_keys():
    """The prompt line used to read "Community {cid}: ..." — the exact string of
    the no-backend placeholder sentinel. A model that echoed the key back as the
    name produced a reply indistinguishable from the fallback, so the caller's
    sentinel filter silently dropped it (#2534). The key must be the bare id."""
    from graphify.llm import _community_label_lines

    G, communities = _graph()
    lines, labeled_cids = _community_label_lines(G, communities, None, 10, 12)
    assert sorted(labeled_cids) == [0, 1]
    for line in lines:
        assert re.match(r"^\d+: ", line), f"prompt line key is not a bare id: {line!r}"
        assert not line.startswith("Community "), f"sentinel-colliding key: {line!r}"


def test_label_cli_drops_sentinel_and_bare_key_echoes(tmp_path, monkeypatch):
    """#2534 case 2, cli side: an LLM reply that echoes the sentinel
    ("Community 5") or the bare prompt key ("7") must not survive the filter —
    the deterministic hub labels win — while a real name still overrides."""
    import graphify.__main__ as cli

    out = tmp_path / "graphify-out"
    out.mkdir()
    graph = {
        "directed": False,
        "multigraph": False,
        "nodes": [
            {"id": "orders", "label": "OrderService", "community": 0},
            {"id": "pay", "label": "PaymentService", "community": 5},
            {"id": "ship", "label": "ShippingService", "community": 7},
        ],
        "links": [],
    }
    (out / "graph.json").write_text(json.dumps(graph), encoding="utf-8")

    def fake_generate(G, communities, *, backend=None, model=None, gods=None,
                      quiet=False, max_concurrency=4, batch_size=100, usage_out=None):
        return {0: "Order Management", 5: "Community 5", 7: "7"}, "llm"

    monkeypatch.setattr("graphify.llm.generate_community_labels", fake_generate)
    monkeypatch.setattr("graphify.export.to_html", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        sys, "argv",
        ["graphify", "label", str(tmp_path), "--backend", "gemini", "--no-viz"],
    )

    cli.main()

    labels = json.loads((out / ".graphify_labels.json").read_text(encoding="utf-8"))
    assert labels["0"] == "Order Management"            # real name survives
    assert labels["5"] == "PaymentService"              # sentinel echo dropped -> hub label
    assert labels["7"] == "ShippingService"             # bare-key echo dropped -> hub label


# ── #3586: Size-aware community labels and token-bounded batching ─────────────


def test_adaptive_sample_size_boundaries():
    """Verify exact boundary transitions for size-aware adaptive sampling."""
    from graphify.llm import _adaptive_sample_size

    boundaries = {
        5: 5,
        12: 12,
        13: 15,
        50: 15,
        51: 20,
        200: 20,
        201: 26,
        1000: 26,
        1001: 32,
        2000: 32,
    }
    for n, expected in boundaries.items():
        assert _adaptive_sample_size(n) == expected, (
            f"Expected _adaptive_sample_size({n}) == {expected}, got {_adaptive_sample_size(n)}"
        )

    # Monotonicity and never sampling more nodes than available for small communities
    for n in range(1, 13):
        assert _adaptive_sample_size(n) == n
    # Upper bound cap
    assert _adaptive_sample_size(10_000) == 32


def test_explicit_top_k_override_and_positional():
    """Explicit top_k caps representative sample, and positional signature is preserved."""
    from graphify.llm import _community_label_lines

    G = nx.Graph()
    # Large community with 100 nodes
    members = [f"node_{i:03d}" for i in range(100)]
    for m in members:
        G.add_node(m, label=f"Label_{m}")
    communities = {0: members}

    # Adaptive default (top_k=None) for N=100 produces 20 representatives
    lines_adaptive, cids_adaptive = _community_label_lines(G, communities)
    assert cids_adaptive == [0]
    names_adaptive = lines_adaptive[0].split(": ", 1)[1].split(", ")
    assert len(names_adaptive) == 20

    # Explicit top_k=7 caps representatives at 7
    lines_explicit, _ = _community_label_lines(G, communities, top_k=7)
    names_explicit = lines_explicit[0].split(": ", 1)[1].split(", ")
    assert len(names_explicit) == 7

    # Preserves positional call: _community_label_lines(G, communities, gods, max_communities, 12)
    lines_pos, _ = _community_label_lines(G, communities, None, 10, 12)
    names_pos = lines_pos[0].split(": ", 1)[1].split(", ")
    assert len(names_pos) == 12


def test_label_communities_and_generate_forward_explicit_top_k(monkeypatch):
    """label_communities and generate_community_labels forward explicit top_k."""
    G = nx.Graph()
    members = [f"node_{i:03d}" for i in range(100)]
    for m in members:
        G.add_node(m, label=f"Label_{m}")
    communities = {0: members}

    captured_prompts = []

    def fake_call(prompt, *, backend, max_tokens=200, **kwargs):
        captured_prompts.append(prompt)
        return '{"0": "Custom Subsystem"}'

    monkeypatch.setattr("graphify.llm._call_llm", fake_call)

    # Explicit top_k=5 via label_communities
    labels = label_communities(G, communities, backend="gemini", top_k=5)
    assert labels == {0: "Custom Subsystem"}
    line = captured_prompts[-1].strip().splitlines()[-1]
    prompt_labels = line.split(": ", 1)[1].split(", ")
    assert len(prompt_labels) == 5

    # Forwarding via generate_community_labels
    gen_labels, src = generate_community_labels(G, communities, backend="gemini", top_k=8)
    assert src == "llm"
    assert gen_labels == {0: "Custom Subsystem"}
    line_gen = captured_prompts[-1].strip().splitlines()[-1]
    prompt_labels_gen = line_gen.split(": ", 1)[1].split(", ")
    assert len(prompt_labels_gen) == 8


def test_representative_diversity_per_file_cap():
    """Representatives are not all taken from alphabetically first source file,
    per-file cap is enforced, and internal hub & god nodes are prioritized."""
    from graphify.llm import _community_label_lines

    G = nx.Graph()
    # 30 nodes in a_file.py, 10 nodes in b_file.py, 10 nodes in c_file.py
    # N = 50 -> adaptive sample = 15.
    # Per-file cap = max(2, (15 + 2) // 3) = 5.
    members = []
    for i in range(30):
        nid = f"a_node_{i:02d}"
        G.add_node(nid, label=f"ALabel_{i:02d}", source_file="a_file.py")
        members.append(nid)
    for i in range(10):
        nid = f"b_node_{i:02d}"
        G.add_node(nid, label=f"BLabel_{i:02d}", source_file="b_file.py")
        members.append(nid)
    for i in range(10):
        nid = f"c_node_{i:02d}"
        G.add_node(nid, label=f"CLabel_{i:02d}", source_file="c_file.py")
        members.append(nid)

    # Add community-internal edges to make b_node_05 a strong internal hub
    for i in range(10):
        if i != 5:
            G.add_edge("b_node_05", f"b_node_{i:02d}")

    # Declare c_node_09 as a global god node
    gods = [{"id": "c_node_09", "label": "CLabel_09"}]

    lines, _ = _community_label_lines(G, {0: members}, gods=gods)
    labels = lines[0].split(": ", 1)[1].split(", ")
    assert len(labels) == 15

    # 1. God node is prioritized first
    assert labels[0] == "CLabel_09"

    # 2. Internal hub b_node_05 is prioritized high (second, before low-degree nodes)
    assert labels[1] == "BLabel_05"

    # 3. Alphabetically first file a_file.py does NOT dominate the sample:
    a_labels = [l for l in labels if l.startswith("ALabel_")]
    b_labels = [l for l in labels if l.startswith("BLabel_")]
    c_labels = [l for l in labels if l.startswith("CLabel_")]

    assert len(a_labels) == 5, f"a_file.py exceeded per-file cap of 5: {a_labels}"
    assert len(b_labels) == 5, f"b_file.py did not receive 5 representatives: {b_labels}"
    assert len(c_labels) == 5, f"c_file.py did not receive 5 representatives: {c_labels}"


def test_single_file_community_receives_full_sample():
    """Single-file community receives its full adaptive sample via backfill."""
    from graphify.llm import _community_label_lines

    G = nx.Graph()
    # 50 nodes all in one source file
    members = [f"single_{i:02d}" for i in range(50)]
    for m in members:
        G.add_node(m, label=f"SingleLabel_{m}", source_file="only_one.py")

    # N = 50 -> adaptive sample = 15. File cap = 5, but backfill fills all 15.
    lines, _ = _community_label_lines(G, {0: members})
    labels = lines[0].split(": ", 1)[1].split(", ")
    assert len(labels) == 15


def test_missing_or_empty_source_file_does_not_crash():
    """Missing or empty source_file attributes are handled gracefully."""
    from graphify.llm import _community_label_lines

    G = nx.Graph()
    members = [f"n_{i:02d}" for i in range(40)]
    for i, m in enumerate(members):
        if i % 3 == 0:
            G.add_node(m, label=f"Lbl_{m}")  # no source_file
        elif i % 3 == 1:
            G.add_node(m, label=f"Lbl_{m}", source_file=None)
        else:
            G.add_node(m, label=f"Lbl_{m}", source_file="")

    # N = 40 -> adaptive sample = 15
    lines, _ = _community_label_lines(G, {0: members})
    labels = lines[0].split(": ", 1)[1].split(", ")
    assert len(labels) == 15


def test_community_smaller_than_target_uses_all_members():
    """Communities with fewer members than target sample use all available nodes."""
    from graphify.llm import _community_label_lines

    G = nx.Graph()
    members = ["node_a", "node_b", "node_c"]
    for m in members:
        G.add_node(m, label=f"Label_{m}")

    lines, _ = _community_label_lines(G, {0: members})
    labels = lines[0].split(": ", 1)[1].split(", ")
    assert len(labels) == 3
    assert set(labels) == {"Label_node_a", "Label_node_b", "Label_node_c"}


def test_token_aware_batching_splits_oversized_batches(monkeypatch):
    """Batches respect both batch_size and prompt token ceilings."""
    from graphify.llm import _pack_label_batches, _estimate_text_tokens, _LABEL_PROMPT_PREAMBLE

    # Create 30 community lines of ~400 characters (~100 tokens) each
    labeled_cids = list(range(30))
    lines = [f"{cid}: " + ", ".join(f"ComponentServiceHandler_{cid}_{i}" for i in range(15)) for cid in labeled_cids]

    # If max_prompt_tokens is small, e.g. 500 tokens:
    batches = _pack_label_batches(labeled_cids, lines, batch_size=100, max_prompt_tokens=500)
    assert len(batches) > 1, "Should split across multiple batches when tokens exceed limit"

    # Verify each batch respects constraints and all cids are preserved
    seen_cids = []
    for b_cids, b_lines in batches:
        assert len(b_cids) <= 100
        assert len(b_cids) == len(b_lines)
        prompt = _LABEL_PROMPT_PREAMBLE + "\n".join(b_lines)
        tokens = _estimate_text_tokens(prompt)
        # Each batch must be within token budget unless it's a single oversized community line
        if len(b_cids) > 1:
            assert tokens <= 500
        seen_cids.extend(b_cids)

    assert seen_cids == labeled_cids


def test_token_aware_batching_accepts_single_oversized_line():
    """A community line exceeding max_prompt_tokens alone is accepted in its own batch."""
    from graphify.llm import _pack_label_batches

    labeled_cids = [0, 1, 2]
    # Very long line
    huge_line = "0: " + ", ".join(["LongRepresentativeNameHere"] * 100)
    normal_line_1 = "1: ShortNameA, ShortNameB"
    normal_line_2 = "2: ShortNameC, ShortNameD"

    lines = [huge_line, normal_line_1, normal_line_2]
    # Set max_prompt_tokens smaller than huge_line + preamble
    batches = _pack_label_batches(labeled_cids, lines, batch_size=10, max_prompt_tokens=50)

    # huge_line should be in its own batch, and normal lines in subsequent batch(es)
    assert len(batches) >= 2
    assert batches[0][0] == [0]
    all_packed = [cid for b_cids, _ in batches for cid in b_cids]
    assert all_packed == [0, 1, 2]


def test_label_communities_end_to_end_with_token_batching(monkeypatch):
    """label_communities processes all communities across token-split batches."""
    G = nx.Graph()
    # 20 communities with long member names
    communities = {}
    for cid in range(20):
        c_members = [f"c{cid}_node_{i:02d}" for i in range(30)]
        for m in c_members:
            G.add_node(m, label=f"VeryLongDescriptiveComponentName_{cid}_{m}")
        communities[cid] = c_members

    batches_seen = []

    def fake_call(prompt, *, backend, max_tokens=200, **kwargs):
        batches_seen.append(prompt)
        # Parse cids from prompt lines
        results = {}
        for line in prompt.splitlines():
            m = re.match(r"^(\d+):", line)
            if m:
                results[m.group(1)] = f"Community Name {m.group(1)}"
        return json.dumps(results)

    monkeypatch.setattr("graphify.llm._call_llm", fake_call)

    # Force a tight token limit by monkeypatching _LABEL_MAX_PROMPT_TOKENS
    monkeypatch.setattr("graphify.llm._LABEL_MAX_PROMPT_TOKENS", 400)

    labels = label_communities(G, communities, backend="gemini", batch_size=100)
    assert len(labels) == 20
    for cid in range(20):
        assert labels[cid] == f"Community Name {cid}"

    # Verify that splitting actually occurred because of the token limit
    assert len(batches_seen) > 1
