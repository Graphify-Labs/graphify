"""Extraction coverage for erlang."""


from __future__ import annotations





import importlib.util as _ilu
import sys


from pathlib import Path





import pytest

from graphify.extract import extract

# tree-sitter-language-pack is an optional extra, not installed by a default
# `uv sync`. Skip the grammar tests when it is absent; the missing-parser
# test below still runs because it simulates the absent grammar itself.
_needs_erlang = pytest.mark.skipif(
    _ilu.find_spec("tree_sitter_language_pack") is None,
    reason="tree-sitter-language-pack not installed (optional [erlang] extra)",
)





FIXTURE = Path(__file__).parent / "fixtures" / "new_languages" / "sample.erl"





def _edge_labels(result: dict, relation: str) -> set[tuple[str, str]]:
    labels = {node["id"]: node["label"] for node in result["nodes"]}
    return {
        (labels.get(edge["source"], edge["source"]), labels.get(edge["target"], edge["target"]))
        for edge in result["edges"]
        if edge["relation"] == relation
    }


@_needs_erlang
def test_erlang_functions_resolve_by_name_and_arity(tmp_path):
    source = tmp_path / "worker.erl"
    source.write_text(
        "-module(worker).\n"
        "-export([run/1]).\n"
        "run(X) -> helper(X).\n"
        "helper(X) -> X.\n"
        "helper(X, Y) -> X + Y.\n",
        encoding="utf-8",
    )

    result = extract([source], cache_root=tmp_path)

    labels = {node["label"] for node in result["nodes"]}
    assert {"worker", "run/1", "helper/1", "helper/2"} <= labels
    assert ("run/1", "helper/1") in _edge_labels(result, "calls")
    assert ("run/1", "helper/2") not in _edge_labels(result, "calls")


@_needs_erlang
def test_erlang_attributes_includes_and_remote_calls(tmp_path):
    header = tmp_path / "worker.hrl"
    header.write_text("-define(HEADER_VALUE, 2).\n", encoding="utf-8")
    other = tmp_path / "other.erl"
    other.write_text(
        "-module(other).\n-export([go/1]).\ngo(X) -> X.\n", encoding="utf-8"
    )
    source = tmp_path / "worker.escript"
    source.write_text(
        "#!/usr/bin/env escript\n"
        "-module('worker').\n"
        "-behaviour(gen_server).\n"
        '-include("worker.hrl").\n'
        '-include_lib("stdlib/include/assert.hrl").\n'
        "-export([run/1, 'quoted'/0]).\n"
        "-record(state, {value}).\n"
        "-type result() :: ok | error.\n"
        "-define(DEFAULT, 1).\n"
        "run(X) -> helper(X), other:go(X), io:format(\"x\").\n"
        "helper(X) -> X.\n"
        "'quoted'() -> ok.\n",
        encoding="utf-8",
    )

    result = extract([source, other, header], cache_root=tmp_path)

    labels = {node["label"] for node in result["nodes"]}
    assert {
        "worker", "other", "run/1", "helper/1", "quoted/0", "go/1",
        "state", "result/0", "DEFAULT", "HEADER_VALUE", "gen_server",
    } <= labels
    assert ("run/1", "helper/1") in _edge_labels(result, "calls")
    assert ("run/1", "go/1") in _edge_labels(result, "calls")
    assert ("worker", "run/1") in _edge_labels(result, "exports")
    assert ("worker", "gen_server") in _edge_labels(result, "implements")
    assert any(edge["relation"] == "imports_from" for edge in result["edges"])


@_needs_erlang
def test_erlang_fixture_uses_normal_extract_path(tmp_path):
    result = extract([FIXTURE], cache_root=tmp_path)

    labels = {node["label"] for node in result["nodes"]}
    assert {'run/0', 'helper/0', 'sample'} <= labels
    assert ('run/0', 'helper/0') in _edge_labels(result, "calls")


@_needs_erlang
def test_erlang_local_fun_reference_links_to_the_function(tmp_path):
    """`fun helper/1` is a reference to a local function — the idiomatic way to
    pass a callback to `lists:map`, `spawn`, etc. It names exactly one function
    (name + arity), so it must link the caller to it. Only direct calls were
    walked before, so every `fun Name/Arity` reference was dropped from the call
    graph (#3993)."""
    source = tmp_path / "worker.erl"
    source.write_text(
        "-module(worker).\n"
        "-export([run/0]).\n"
        "run() -> lists:map(fun helper/1, [1, 2, 3]).\n"
        "helper(X) -> X + 1.\n",
        encoding="utf-8",
    )

    result = extract([source], cache_root=tmp_path)

    assert ("run/0", "helper/1") in _edge_labels(result, "indirect_call")


@_needs_erlang
def test_erlang_local_fun_reference_respects_arity(tmp_path):
    """Fail-closed: `fun helper/1` must bind only to the arity-1 clause, never to
    a same-named function of a different arity (#3993)."""
    source = tmp_path / "worker.erl"
    source.write_text(
        "-module(worker).\n"
        "run() -> spawn(fun helper/0).\n"
        "helper(X) -> X.\n",  # only helper/1 exists, not helper/0
        encoding="utf-8",
    )

    result = extract([source], cache_root=tmp_path)

    assert not any(
        src == "run/0" for src, _tgt in _edge_labels(result, "indirect_call")
    )


@_needs_erlang
def test_erlang_direct_call_stays_a_call_not_indirect(tmp_path):
    """Positive control: a direct call keeps emitting a `calls` edge (not
    `indirect_call`), unchanged by the fun-reference handling (#3993)."""
    source = tmp_path / "worker.erl"
    source.write_text(
        "-module(worker).\n"
        "run() -> helper(5).\n"
        "helper(X) -> X.\n",
        encoding="utf-8",
    )

    result = extract([source], cache_root=tmp_path)

    assert ("run/0", "helper/1") in _edge_labels(result, "calls")
    assert ("run/0", "helper/1") not in _edge_labels(result, "indirect_call")


@_needs_erlang
def test_erlang_call_inside_anonymous_fun_still_captured(tmp_path):
    """Positive control: a direct call made inside an anonymous `fun ... end`
    body must still be walked and resolved (#3993)."""
    source = tmp_path / "worker.erl"
    source.write_text(
        "-module(worker).\n"
        "run() -> lists:foreach(fun(X) -> helper(X) end, [1, 2, 3]).\n"
        "helper(X) -> X.\n",
        encoding="utf-8",
    )

    result = extract([source], cache_root=tmp_path)

    assert ("run/0", "helper/1") in _edge_labels(result, "calls")


@_needs_erlang
def test_erlang_malformed_tail_comments_and_strings_do_not_create_phantoms(tmp_path):
    source = tmp_path / 'broken.erl'
    source.write_text('-module(broken).\nvalid() -> ok.\n% ghost() -> ok.\ninvalid(\n', encoding="utf-8")

    result = extract([source], cache_root=tmp_path)

    labels = {node["label"].casefold() for node in result["nodes"]}
    assert 'valid/0' in labels
    assert labels.isdisjoint({'ghost/0'})


def test_erlang_missing_parser_reports_install_hint(tmp_path, monkeypatch, capsys):
    source = tmp_path / "missing.erl"
    source.write_text('-module(missing).\n', encoding="utf-8")
    monkeypatch.setitem(sys.modules, 'tree_sitter_language_pack', None)

    result = extract([source], cache_root=tmp_path)

    assert result["nodes"] == []
    assert 'pip install "graphifyy[erlang]"' in capsys.readouterr().err
