"""Sourceless stubs must not shadow a real declaration, nor collapse into one
rival group (#49, RC3 of #46).

`find_node_ambiguity` grouped the winning tier by `source_file`. Every sourceless
stub carries `source_file == ""`, so N stubs counted as a single file: no
ambiguity was reported and `explain` answered with `matches[0]` — the graph's
iteration order. The 18 exact-tier stubs shadowing `BalanceitemRepository` on the
pinned api corpus are the field case; the shapes below are the synthetic
equivalents (Q4 = sourced + N stubs, Q2 = sourced + 1 stub).
"""
from __future__ import annotations

import json

import pytest
from networkx.readwrite import json_graph

import graphify.__main__ as mainmod
from graphify.affected import resolve_seed
from graphify.serve import _find_node, find_node_ambiguity


LABEL = "FooRepository"
SOURCED_ID = "app_repo_foorepository_foorepository"
SOURCE_FILE = "app/Repo/FooRepository.php"


def _stub(index: int, *, omit_source_key: bool = False) -> dict:
    """A sourceless stub: `_php_emit_base`'s bare shadow, or a per-file salted one.

    `omit_source_key` reproduces the attributeless node serve materializes for a
    dangling edge endpoint (no `source_file` key at all, not an empty one).
    """
    node = {"id": f"app_uses_consumer{index}_php_foorepository", "label": LABEL,
            "community": 0}
    if not omit_source_key:
        node["source_file"] = ""
    return node


def _sourced() -> dict:
    return {"id": SOURCED_ID, "label": LABEL, "source_file": SOURCE_FILE,
            "source_location": "L22", "community": 0}


def _graph_dict(nodes: list[dict]) -> dict:
    return {"directed": False, "multigraph": False, "graph": {},
            "nodes": nodes, "links": []}


def _load(nodes: list[dict]):
    return json_graph.node_link_graph(
        {**_graph_dict(nodes), "directed": True}, edges="links")


def _write(tmp_path, nodes: list[dict], name: str = "graph.json"):
    p = tmp_path / name
    p.write_text(json.dumps(_graph_dict(nodes)))
    return p


def _run_explain(monkeypatch, graph_path, label, capsys):
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)
    monkeypatch.setattr(mainmod.sys, "argv",
        ["graphify", "explain", label, "--graph", str(graph_path)])
    code = None
    try:
        mainmod.main()
    except SystemExit as exc:
        code = exc.code
    return capsys.readouterr().out, code


# --- Q4: one sourced declaration + N sourceless stubs ------------------------


@pytest.mark.parametrize("stub_count", [2, 3, 18])
def test_sourced_node_wins_over_n_sourceless_stubs(stub_count):
    """Criterion 1/4: never a silent arbitrary stub, at any stub count.

    The guard must not depend on stub counts staying high — post-#47/#48 graphs
    have fewer stubs, and the residual ones must still be handled.
    """
    stubs = [_stub(i) for i in range(stub_count)]
    # Stubs first: matches[0] was a stub under graph-iteration order.
    G = _load(stubs + [_sourced()])
    assert _find_node(G, LABEL)[0] == SOURCED_ID
    assert find_node_ambiguity(G, LABEL) == []


def test_q4_answer_does_not_depend_on_node_order():
    stubs = [_stub(i) for i in range(3)]
    forward = _load(stubs + [_sourced()])
    reverse = _load([_sourced()] + list(reversed(stubs)))
    assert _find_node(forward, LABEL)[0] == _find_node(reverse, LABEL)[0] == SOURCED_ID


def test_q4_explain_reports_the_sourced_node(monkeypatch, tmp_path, capsys):
    p = _write(tmp_path, [_stub(i) for i in range(18)] + [_sourced()])
    out, code = _run_explain(monkeypatch, p, LABEL, capsys)
    assert f"  ID:        {SOURCED_ID}" in out
    assert SOURCE_FILE in out
    assert "Ambiguous" not in out
    assert code != 1


def test_attributeless_dangling_endpoints_are_also_stubs():
    """A dangling edge endpoint has no `source_file` key at all — same rule."""
    stubs = [_stub(i, omit_source_key=True) for i in range(3)]
    G = _load(stubs + [_sourced()])
    assert _find_node(G, LABEL)[0] == SOURCED_ID
    assert find_node_ambiguity(G, LABEL) == []


# --- all-sourceless tier: no real node to prefer, so refuse ------------------


@pytest.mark.parametrize("stub_count", [2, 18])
def test_sourceless_rivals_alone_are_ambiguous_not_an_arbitrary_pick(stub_count):
    """The bug proper: N stubs shared the `""` bucket and looked unambiguous."""
    G = _load([_stub(i) for i in range(stub_count)])
    assert len(find_node_ambiguity(G, LABEL)) == stub_count


def test_explain_refuses_when_only_sourceless_stubs_match(monkeypatch, tmp_path, capsys):
    p = _write(tmp_path, [_stub(i) for i in range(3)])
    out, code = _run_explain(monkeypatch, p, LABEL, capsys)
    assert "Ambiguous" in out
    assert code == 1
    assert "Node: FooRepository\n  ID:" not in out


# --- a stub with no sourced rival is still an answer ------------------------


@pytest.mark.parametrize("omit_source_key", [False, True])
def test_lone_stub_with_no_sourced_rival_still_resolves(omit_source_key):
    """The rule demotes stubs against a real declaration — it does not delete them.

    `resolve_seed`'s exact-label pass no longer returns a lone *sourceless* match
    outright (a decorated "name()" declaration is invisible to that pass but
    visible to the bare-name pass below it, and serve's exact tier — matching both
    forms — would prefer it). A stub with nothing to lose to must therefore still
    come back from a later pass rather than fall through to None.

    This asserts that outcome, not the mechanism: for an undecorated label both
    the bare-name pass and the `contains` pass below it return the stub, so either
    alone would satisfy this. `test_bare_name_pass_is_what_recovers_a_lone_stub`
    isolates the pass the fall-through actually leans on.
    """
    stub = _stub(0, omit_source_key=omit_source_key)
    G = _load([stub])
    assert _find_node(G, LABEL) == [stub["id"]]
    assert find_node_ambiguity(G, LABEL) == []
    assert resolve_seed(G, LABEL) == stub["id"]


def test_bare_name_pass_is_what_recovers_a_lone_stub():
    """A decorated sourceless stub that the `contains` pass cannot rescue.

    `handle()` never enters the exact-label pass (its stored label keeps the
    decoration, the query does not), and the `contains` pass ties it with the
    `handleRequest()` sibling. Only the bare-name pass sees it alone — so this is
    the assertion that goes red if that pass stops returning lone matches, which
    is the fall-through the exact-label change depends on.
    """
    G = _load([
        {"id": "stub_handle", "label": "handle()", "source_file": "", "community": 0},
        {"id": "app_svc_php_handlerequest", "label": "handleRequest()",
         "source_file": "app/Svc.php", "source_location": "L14", "community": 0},
    ])
    assert resolve_seed(G, "handle") == "stub_handle"


def test_lone_stub_explains_rather_than_reporting_a_phantom_ambiguity(
    monkeypatch, tmp_path, capsys
):
    p = _write(tmp_path, [_stub(0)])
    out, code = _run_explain(monkeypatch, p, LABEL, capsys)
    assert f"  ID:        {_stub(0)['id']}" in out
    assert "Ambiguous" not in out
    assert code != 1


# --- Q2: one sourced + one sourceless ---------------------------------------


def test_q2_shape_does_not_regress():
    """Criterion 2: resolve to the sourced node (never the stub, never silent)."""
    G = _load([_stub(0), _sourced()])
    assert _find_node(G, LABEL)[0] == SOURCED_ID
    assert find_node_ambiguity(G, LABEL) == []


def test_q2_explain_reports_the_sourced_node(monkeypatch, tmp_path, capsys):
    p = _write(tmp_path, [_stub(0), _sourced()])
    out, code = _run_explain(monkeypatch, p, LABEL, capsys)
    assert f"  ID:        {SOURCED_ID}" in out
    assert code != 1


# --- explain / affected consistency (criterion 3) ---------------------------


@pytest.mark.parametrize("stub_count", [1, 2, 18])
def test_explain_and_affected_agree_when_a_sourced_node_exists(stub_count):
    """`resolve_seed` refused with "No unique node match" while `explain`
    answered — that divergence is #46's symptom."""
    G = _load([_stub(i) for i in range(stub_count)] + [_sourced()])
    assert resolve_seed(G, LABEL) == _find_node(G, LABEL)[0] == SOURCED_ID


@pytest.mark.parametrize("stub_count", [2, 18])
def test_explain_and_affected_both_refuse_when_every_rival_is_sourceless(stub_count):
    G = _load([_stub(i) for i in range(stub_count)])
    assert resolve_seed(G, LABEL) is None
    assert find_node_ambiguity(G, LABEL)  # explain refuses too


def test_affected_prefers_sourced_node_for_a_callable_label():
    """`resolve_seed`'s bare-name pass (decorated "name()" labels) needs the
    same rule as its exact-label pass."""
    nodes = [
        {"id": "stub_handle", "label": "handle", "source_file": "", "community": 0},
        {"id": "app_svc_php_handle", "label": "handle()",
         "source_file": "app/Svc.php", "source_location": "L9", "community": 0},
    ]
    G = _load(nodes)
    assert resolve_seed(G, "handle") == "app_svc_php_handle"


# --- the pre-existing monorepo tie must still be reported -------------------


def test_two_sourced_rivals_are_still_ambiguous():
    """Sourced-vs-sourced (#2032's symbol case) is untouched by the stub rule."""
    G = _load([
        {"id": "chat_port", "label": "MetricsPort",
         "source_file": "services/chat/ports/metrics.port.ts", "community": 0},
        {"id": "scrape_port", "label": "MetricsPort",
         "source_file": "services/scraping/ports/metrics.port.ts", "community": 0},
    ])
    assert len(find_node_ambiguity(G, "MetricsPort")) == 2
