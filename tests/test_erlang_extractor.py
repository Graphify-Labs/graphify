"""Extraction coverage for erlang."""


from __future__ import annotations





import sys


from pathlib import Path





from graphify.extract import extract





FIXTURE = Path(__file__).parent / "fixtures" / "new_languages" / "sample.erl"





def _edge_labels(result: dict, relation: str) -> set[tuple[str, str]]:
    labels = {node["id"]: node["label"] for node in result["nodes"]}
    return {
        (labels.get(edge["source"], edge["source"]), labels.get(edge["target"], edge["target"]))
        for edge in result["edges"]
        if edge["relation"] == relation
    }


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


def test_erlang_fixture_uses_normal_extract_path(tmp_path):
    result = extract([FIXTURE], cache_root=tmp_path)

    labels = {node["label"] for node in result["nodes"]}
    assert {'run/0', 'helper/0', 'sample'} <= labels
    assert ('run/0', 'helper/0') in _edge_labels(result, "calls")


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
