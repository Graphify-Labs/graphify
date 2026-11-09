"""A paren-less Ruby method call is a self-send and must keep its `calls` edge.

In Ruby the most common call form has no receiver and no parentheses::

    def run
      build      # a method call on self, not a variable read
    end

Tree-sitter parses that `build` as a bare `identifier`, structurally identical
to a local-variable read `x`. The call-walk only looked at `call` nodes, so the
edge was silently dropped — `run` → `build` never appeared, even though
`run(1)`, `self.run` and `run arg` all resolved. The Ruby resolver already had
a dedicated bare-call promotion path, but it had nothing to promote because the
extraction step never produced the call.

The fix mirrors Ruby's own rule: a bare identifier is a send on `self` unless a
local or parameter of that name is in scope. These specs pin both halves — the
send is captured, and a genuine local read is NOT turned into a call.
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

from graphify.extract import extract


def _extract(tmp_path, files: dict[str, str]) -> dict:
    for name, body in files.items():
        p = tmp_path / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body)
    old = os.getcwd()
    try:
        os.chdir(tmp_path)
        return extract([Path(n) for n in files], cache_root=Path(tempfile.mkdtemp()))
    finally:
        os.chdir(old)


def _labels(r: dict) -> dict[str, str]:
    return {n["id"]: str(n.get("label", "")) for n in r["nodes"]}


def _calls(r: dict, src: str, tgt: str) -> list[dict]:
    labels = _labels(r)
    return [
        e
        for e in r["edges"]
        if e.get("relation") == "calls"
        and labels.get(e.get("source")) == src
        and labels.get(e.get("target")) == tgt
    ]


def test_bare_self_send_in_a_class_is_a_call(tmp_path):
    r = _extract(tmp_path, {"w.rb": (
        "class Widget\n"
        "  def run\n"
        "    build\n"
        "  end\n"
        "  def build\n"
        "    1\n"
        "  end\n"
        "end\n"
    )})
    assert _calls(r, ".run()", ".build()")


def test_bare_call_between_module_methods_is_a_call(tmp_path):
    # The whole module layer used to be a set of leaves with no internal edges.
    r = _extract(tmp_path, {"g.rb": (
        "module Greetable\n"
        "  def greet\n"
        "    build_message\n"
        "  end\n"
        "  def build_message\n"
        "    \"hi\"\n"
        "  end\n"
        "end\n"
    )})
    assert _calls(r, ".greet()", ".build_message()")


def test_bare_call_to_a_mixed_in_method_resolves(tmp_path):
    r = _extract(tmp_path, {"m.rb": (
        "module Greetable\n"
        "  def greet\n"
        "    \"hi\"\n"
        "  end\n"
        "end\n"
        "class Person\n"
        "  include Greetable\n"
        "  def initialize\n"
        "    greet\n"
        "  end\n"
        "end\n"
    )})
    assert _calls(r, ".initialize()", ".greet()")


def test_bare_call_as_an_argument_is_a_call(tmp_path):
    # `log hello` — `hello` is itself a paren-less send passed as the argument.
    r = _extract(tmp_path, {"a.rb": (
        "class W\n"
        "  def run\n"
        "    log hello\n"
        "  end\n"
        "  def hello\n"
        "  end\n"
        "  def log(x)\n"
        "  end\n"
        "end\n"
    )})
    assert _calls(r, ".run()", ".hello()")


def test_a_local_variable_read_is_not_a_call(tmp_path):
    # `build` is assigned first, so the later bare `build` is a variable read,
    # not a send — even though a method named `build` exists. No edge.
    r = _extract(tmp_path, {"v.rb": (
        "class W\n"
        "  def run\n"
        "    build = 1\n"
        "    build\n"
        "  end\n"
        "  def build\n"
        "    2\n"
        "  end\n"
        "end\n"
    )})
    assert not _calls(r, ".run()", ".build()")


def test_a_parameter_read_is_not_a_call(tmp_path):
    # A parameter named like a method shadows it; the bare read is the parameter.
    r = _extract(tmp_path, {"p.rb": (
        "class W\n"
        "  def run(build)\n"
        "    build\n"
        "  end\n"
        "  def build\n"
        "    1\n"
        "  end\n"
        "end\n"
    )})
    assert not _calls(r, ".run()", ".build()")


def test_a_block_parameter_read_is_not_a_call(tmp_path):
    # `item` is a block parameter inside the method, not a send.
    r = _extract(tmp_path, {"b.rb": (
        "class W\n"
        "  def run\n"
        "    [1].each do |item|\n"
        "      item\n"
        "    end\n"
        "  end\n"
        "  def item\n"
        "  end\n"
        "end\n"
    )})
    assert not _calls(r, ".run()", ".item()")


def test_self_send_and_bare_send_do_not_duplicate_an_edge(tmp_path):
    r = _extract(tmp_path, {"s.rb": (
        "class W\n"
        "  def run\n"
        "    build\n"
        "    self.build\n"
        "  end\n"
        "  def build\n"
        "  end\n"
        "end\n"
    )})
    assert len(_calls(r, ".run()", ".build()")) == 1
