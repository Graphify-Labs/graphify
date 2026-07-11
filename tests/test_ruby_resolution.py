"""TDD specs for type-aware Ruby call-graph resolution.

These drive the "improved Ruby graph" work:
  * member calls capture their receiver (extraction)
  * `var = ClassName.new` local bindings give the receiver a type (extraction)
  * the cross-file resolver turns `var.method` into a precise edge BY TYPE,
    not by globally-unique name — so it survives name collisions and never
    emits a false positive when the type is unknown (resolution)
  * `require_relative` links files (resolution)

Every resolved edge must be EXTRACTED (1.0) confidence: resolve only when
certain, bail otherwise.
"""

from __future__ import annotations

from pathlib import Path

from graphify.extract import extract, extract_ruby


# ── helpers ────────────────────────────────────────────────────────────────────


def _write(tmp_path: Path, name: str, body: str) -> Path:
    p = tmp_path / name
    p.write_text(body)
    return p


def _raw_calls(result: dict) -> list[dict]:
    return result.get("raw_calls", [])


def _find_raw_call(result: dict, callee: str) -> dict | None:
    for rc in _raw_calls(result):
        if rc.get("callee") == callee:
            return rc
    return None


def _labels(nodes: list[dict]) -> dict[str, str]:
    return {n["id"]: str(n.get("label", "")) for n in nodes}


def _has_call_edge(graph: dict, src_label_sub: str, tgt_label_sub: str) -> dict | None:
    """Return the `calls` edge whose source/target labels contain the given
    substrings, or None."""
    labels = _labels(graph["nodes"])
    for e in graph["edges"]:
        if e.get("relation") != "calls":
            continue
        s = labels.get(e.get("source"), "")
        t = labels.get(e.get("target"), "")
        if src_label_sub in s and tgt_label_sub in t:
            return e
    return None


HELPER_RB = """\
def transform(data)
  data.upcase
end

class Processor
  def run(items)
    items.map { |i| transform(i) }
  end
end
"""

MAIN_RB = """\
require_relative "helper"

def handle(values)
  transform(values)
end

def process_all(items)
  p = Processor.new
  p.run(items)
end
"""

WORKER_RB = """\
class Worker
  def run(jobs)
    jobs.each { |j| j }
  end
end
"""


# ── extraction level ───────────────────────────────────────────────────────────


def test_member_call_captures_receiver(tmp_path: Path) -> None:
    main = _write(tmp_path, "main.rb", MAIN_RB)
    rc = _find_raw_call(extract_ruby(main), "run")
    assert rc is not None, "p.run should produce a raw_call with callee 'run'"
    assert rc["is_member_call"] is True
    assert rc["receiver"] == "p"


def test_local_binding_gives_receiver_a_type(tmp_path: Path) -> None:
    main = _write(tmp_path, "main.rb", MAIN_RB)
    rc = _find_raw_call(extract_ruby(main), "run")
    assert rc is not None
    # `p = Processor.new` in the same method => p has type Processor.
    assert rc.get("receiver_type") == "Processor"


def test_ambiguous_binding_yields_no_type(tmp_path: Path) -> None:
    main = _write(
        tmp_path,
        "main.rb",
        """\
def process_all(items)
  p = Processor.new
  p = Worker.new
  p.run(items)
end
""",
    )
    rc = _find_raw_call(extract_ruby(main), "run")
    assert rc is not None
    # reassigned to a different class => not certain => no type attached.
    assert rc.get("receiver_type") is None


# ── resolution level ───────────────────────────────────────────────────────────


def test_resolves_member_call_by_type(tmp_path: Path) -> None:
    _write(tmp_path, "helper.rb", HELPER_RB)
    main = _write(tmp_path, "main.rb", MAIN_RB)
    graph = extract([main, tmp_path / "helper.rb"], cache_root=tmp_path, parallel=False)
    edge = _has_call_edge(graph, "process_all", "run")
    assert edge is not None, "process_all should resolve a call to Processor#run"
    assert edge["confidence"] == "EXTRACTED"


def test_resolution_is_type_based_not_name_luck(tmp_path: Path) -> None:
    """The differentiator: adding an unrelated Worker#run must NOT break the edge.

    Name-match resolvers drop this (two `run` definitions => ambiguous). A
    type-based resolver keeps resolving p.run -> Processor#run, and never points
    it at Worker#run.
    """
    _write(tmp_path, "helper.rb", HELPER_RB)
    _write(tmp_path, "worker.rb", WORKER_RB)
    main = _write(tmp_path, "main.rb", MAIN_RB)
    graph = extract(
        [main, tmp_path / "helper.rb", tmp_path / "worker.rb"],
        cache_root=tmp_path,
        parallel=False,
    )
    to_processor_run = _has_call_edge(graph, "process_all", "run")
    assert to_processor_run is not None, "edge must survive the name collision"
    assert to_processor_run["confidence"] == "EXTRACTED"
    # And it must be the RIGHT run: the target must be owned by Processor, not Worker.
    labels = _labels(graph["nodes"])
    tgt_id = to_processor_run["target"]
    # the method node id is prefixed by its owning class (helper_processor_run)
    assert "processor" in tgt_id.lower(), f"expected Processor#run, got {tgt_id}"
    assert "worker" not in tgt_id.lower()


def test_no_false_positive_when_type_unknown(tmp_path: Path) -> None:
    """A member call on a receiver with no known type must NOT be resolved."""
    _write(tmp_path, "helper.rb", HELPER_RB)
    main = _write(
        tmp_path,
        "main.rb",
        """\
require_relative "helper"

def process_all(thing)
  thing.run(1)
end
""",
    )
    graph = extract([main, tmp_path / "helper.rb"], cache_root=tmp_path, parallel=False)
    # `thing` is a parameter of unknown type => no precise target => no edge.
    assert _has_call_edge(graph, "process_all", "run") is None


def test_class_new_creates_instantiation_edge(tmp_path: Path) -> None:
    """`p = Processor.new` should link the caller to the Processor class."""
    _write(tmp_path, "helper.rb", HELPER_RB)
    main = _write(tmp_path, "main.rb", MAIN_RB)
    graph = extract([main, tmp_path / "helper.rb"], cache_root=tmp_path, parallel=False)
    edge = _has_call_edge(graph, "process_all", "Processor")
    assert edge is not None, "Processor.new should resolve a call to the Processor class"
    assert edge["confidence"] == "EXTRACTED"


# ── #1640 node extraction + #1634 constant-receiver resolution ───────────────


def _node_labels(result: dict) -> set[str]:
    return {str(n.get("label", "")) for n in result["nodes"]}


def _method_edges(result: dict) -> set[tuple[str, str]]:
    labels = _labels(result["nodes"])
    return {
        (labels.get(e["source"], ""), labels.get(e["target"], ""))
        for e in result["edges"] if e.get("relation") == "method"
    }


def test_plain_module_gets_a_node_with_methods(tmp_path: Path) -> None:
    """#1640 shape 1: `module Foo` must get a node and own its methods."""
    r = extract_ruby(_write(tmp_path, "tax.rb",
        "module TaxCalculator\n  module_function\n  def rate_for(order)\n    0.2\n  end\nend\n"))
    assert "TaxCalculator" in _node_labels(r)
    # method attaches to the module (dot label), not the file (dot-less).
    assert ("TaxCalculator", ".rate_for()") in _method_edges(r)


def test_nested_modules_each_get_a_node(tmp_path: Path) -> None:
    """#1640 shape 1, nested."""
    r = extract_ruby(_write(tmp_path, "n.rb",
        "module Billing\n  module Rounding\n    def round(x)\n      x.round(2)\n    end\n  end\nend\n"))
    labels = _node_labels(r)
    assert "Billing" in labels and "Rounding" in labels
    assert ("Rounding", ".round()") in _method_edges(r)


def test_struct_new_constant_creates_class_with_methods(tmp_path: Path) -> None:
    """#1640 shape 2: `Foo = Struct.new(...) do ... end`."""
    r = extract_ruby(_write(tmp_path, "invoice.rb",
        "Invoice = Struct.new(:total, :tax) do\n  def grand_total\n    total + tax\n  end\nend\n"))
    assert "Invoice" in _node_labels(r)
    assert ("Invoice", ".grand_total()") in _method_edges(r)


def test_class_new_constant_creates_class_and_inherits(tmp_path: Path) -> None:
    """#1640 shape 3: `Foo = Class.new(Super)` — node + inherits edge."""
    r = extract_ruby(_write(tmp_path, "err.rb", "ApiError = Class.new(StandardError)\n"))
    assert "ApiError" in _node_labels(r)
    labels = _labels(r["nodes"])
    inh = {(labels.get(e["source"], ""), labels.get(e["target"], ""))
           for e in r["edges"] if e.get("relation") == "inherits"}
    assert ("ApiError", "StandardError") in inh


def test_data_define_constant_creates_class(tmp_path: Path) -> None:
    r = extract_ruby(_write(tmp_path, "res.rb", "Result = Data.define(:ok, :value)\n"))
    assert "Result" in _node_labels(r)


def test_constant_receiver_singleton_call_resolves(tmp_path: Path) -> None:
    """#1634: `Processor.call` (def self.call) resolves to the singleton method."""
    _write(tmp_path, "processor.rb", "class Processor\n  def self.call; end\nend\n")
    runner = _write(tmp_path, "runner.rb",
        "class Runner\n  def run\n    Processor.call\n  end\nend\n")
    graph = extract([runner, tmp_path / "processor.rb"], cache_root=tmp_path, parallel=False)
    assert _has_call_edge(graph, "run", "call") is not None


def test_constant_receiver_module_function_call_resolves(tmp_path: Path) -> None:
    """#1634 + #1640: `TaxCalculator.rate_for` resolves across files to a
    module_function — needs both the module node (#1640) and the resolver (#1634)."""
    _write(tmp_path, "tax.rb",
        "module TaxCalculator\n  module_function\n  def rate_for(o)\n    0.2\n  end\nend\n")
    pp = _write(tmp_path, "pp.rb",
        "class PaymentProcessor\n  def process(order)\n    TaxCalculator.rate_for(order)\n  end\nend\n")
    graph = extract([pp, tmp_path / "tax.rb"], cache_root=tmp_path, parallel=False)
    assert _has_call_edge(graph, "process", "rate_for") is not None


def test_constant_receiver_unknown_class_method_falls_back_to_class(tmp_path: Path) -> None:
    """#1634: `Model.where` (no `where` def, e.g. ActiveRecord) still links to the
    class node for blast-radius, rather than dropping the edge."""
    _write(tmp_path, "model.rb", "class Model\n  def self.create; end\nend\n")
    caller = _write(tmp_path, "svc.rb",
        "class Svc\n  def run\n    Model.where(id: 1)\n  end\nend\n")
    graph = extract([caller, tmp_path / "model.rb"], cache_root=tmp_path, parallel=False)
    # No `where` method node exists, so the edge lands on the class node itself.
    assert _has_call_edge(graph, "run", "Model") is not None


def test_ambiguous_constant_receiver_emits_no_edge(tmp_path: Path) -> None:
    """Two classes named `Processor` => ambiguous receiver => bail (no wrong edge)."""
    _write(tmp_path, "a.rb", "module A\n  class Processor\n    def self.call; end\n  end\nend\n")
    _write(tmp_path, "b.rb", "module B\n  class Processor\n    def self.call; end\n  end\nend\n")
    caller = _write(tmp_path, "c.rb",
        "class Runner\n  def run\n    Processor.call\n  end\nend\n")
    graph = extract([caller, tmp_path / "a.rb", tmp_path / "b.rb"], cache_root=tmp_path, parallel=False)
    assert _has_call_edge(graph, "run", "call") is None


# ── #1668 include/extend/prepend -> mixes_in ─────────────────────────────────


def _mixes_in(graph: dict) -> set[tuple[str, str]]:
    labels = _labels(graph["nodes"])
    return {
        (labels.get(e["source"], ""), labels.get(e["target"], ""))
        for e in graph["edges"] if e.get("relation") == "mixes_in"
    }


def test_include_emits_mixes_in_edge(tmp_path: Path) -> None:
    _write(tmp_path, "concern.rb", "module SealedProtection\n  def sealed?; true; end\nend\n")
    _write(tmp_path, "model.rb",
           "class Roster < ApplicationRecord\n  include SealedProtection\nend\n")
    g = extract([tmp_path / "model.rb", tmp_path / "concern.rb"], cache_root=tmp_path, parallel=False)
    assert ("Roster", "SealedProtection") in _mixes_in(g)


def test_extend_and_prepend_emit_mixes_in(tmp_path: Path) -> None:
    _write(tmp_path, "helpers.rb", "module Helpers\n  def h; end\nend\n")
    _write(tmp_path, "audit.rb", "module Audit\n  def a; end\nend\n")
    _write(tmp_path, "svc.rb",
           "class Svc\n  extend Helpers\n  prepend Audit\nend\n")
    mix = _mixes_in(extract(sorted(tmp_path.glob("*.rb")), cache_root=tmp_path, parallel=False))
    assert ("Svc", "Helpers") in mix
    assert ("Svc", "Audit") in mix


def test_extend_self_and_nonconstant_args_emit_no_mixin(tmp_path: Path) -> None:
    # `extend self` and `include some_var` are not constant module references.
    _write(tmp_path, "m.rb",
           "module M\n  extend self\n  def go; end\nend\n")
    mix = _mixes_in(extract([tmp_path / "m.rb"], cache_root=tmp_path, parallel=False))
    assert not any(t == "self" for _s, t in mix)
    assert not mix


def test_include_of_undefined_or_ambiguous_module_emits_no_edge(tmp_path: Path) -> None:
    # Undefined module (no node) -> no edge, under the single-owner guard.
    _write(tmp_path, "x.rb", "class X\n  include NotDefinedAnywhere\nend\n")
    mix = _mixes_in(extract([tmp_path / "x.rb"], cache_root=tmp_path, parallel=False))
    assert not any(t == "NotDefinedAnywhere" for _s, t in mix)


def test_mixin_is_not_emitted_as_calls_edge(tmp_path: Path) -> None:
    # Regression: the shared cross-file call pass must not turn a mixin into a
    # `calls` edge (which would mislabel it and block the mixes_in emit).
    _write(tmp_path, "concern.rb", "module C\n  def m; end\nend\n")
    _write(tmp_path, "k.rb", "class K\n  include C\nend\n")
    g = extract([tmp_path / "k.rb", tmp_path / "concern.rb"], cache_root=tmp_path, parallel=False)
    labels = _labels(g["nodes"])
    calls = {(labels.get(e["source"], ""), labels.get(e["target"], ""))
             for e in g["edges"] if e.get("relation") == "calls"}
    assert ("K", "C") not in calls
    assert ("K", "C") in _mixes_in(g)


def test_rake_files_extract_and_resolve_like_rb(tmp_path):
    """#1784: `.rake` files are plain Ruby and must route to the Ruby extractor
    and participate in Ruby cross-file resolution exactly like `.rb`."""
    rake = _write(tmp_path, "ops.rake",
                  "class RakeHelper\n  def self.run\n    Widget.tally\n  end\nend\n")
    rb = _write(tmp_path, "widget.rb",
                "class Widget\n  def self.tally\n    42\n  end\nend\n")
    result = extract([rake, rb], cache_root=tmp_path / ".cache")
    label = {n["id"]: n.get("label") for n in result["nodes"]}
    labels = set(label.values())
    # the .rake file's symbols are extracted
    assert "RakeHelper" in labels and ".run()" in labels
    # and the cross-file member call resolves .rake -> .rb
    calls = {(label.get(e["source"]), label.get(e["target"]))
             for e in result["edges"] if e["relation"] == "calls"}
    assert (".run()", ".tally()") in calls
