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
    """#1640 shape 1, nested — the inner module is labelled fully qualified
    (#2302), so nested and compact declarations converge on one label."""
    r = extract_ruby(_write(tmp_path, "n.rb",
        "module Billing\n  module Rounding\n    def round(x)\n      x.round(2)\n    end\n  end\nend\n"))
    labels = _node_labels(r)
    assert "Billing" in labels and "Billing::Rounding" in labels
    assert ("Billing::Rounding", ".round()") in _method_edges(r)


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


# ── #2302 compact-syntax mixins + qualified constant lookup ──────────────────


def test_compact_and_nested_module_includes_resolve(tmp_path: Path) -> None:
    """#2302: `module Billing::TotalsConcern` (compact) and a top-level module
    both resolve as mixin targets, lexically from the including class."""
    _write(tmp_path, "totals_concern.rb",
           "module Billing::TotalsConcern\n  def total; end\nend\n")
    _write(tmp_path, "archivable_concern.rb",
           "module ArchivableConcern\n  extend ActiveSupport::Concern\n  def archive; end\nend\n")
    _write(tmp_path, "models.rb",
           "module Billing\n  class Invoice\n    include TotalsConcern\n  end\nend\n"
           "\nclass Account\n  extend ArchivableConcern\nend\n")
    g = extract(sorted(tmp_path.glob("*.rb")), cache_root=tmp_path, parallel=False)
    mix = _mixes_in(g)
    assert ("Billing::Invoice", "Billing::TotalsConcern") in mix
    assert ("Account", "ArchivableConcern") in mix
    # `extend ActiveSupport::Concern` must not fabricate an edge to any local
    # module — no phantom `Concern` target of any spelling.
    assert not any(t.split("::")[-1] == "Concern" for _s, t in mix)


def test_qualified_external_mixin_does_not_bind_to_local(tmp_path: Path) -> None:
    """#2302: `extend ActiveSupport::Concern` must NOT resolve to an unrelated
    local `module Concern` just because the last segment matches."""
    _write(tmp_path, "concern.rb", "module Concern\n  def local_thing; end\nend\n")
    _write(tmp_path, "post.rb", "class Post\n  extend ActiveSupport::Concern\nend\n")
    mix = _mixes_in(extract(sorted(tmp_path.glob("*.rb")), cache_root=tmp_path, parallel=False))
    assert ("Post", "Concern") not in mix
    assert not mix


def test_in_corpus_qualified_mixin_resolves(tmp_path: Path) -> None:
    """#2302 over-suppression guard: a qualified reference whose full path IS
    defined in the corpus still resolves."""
    _write(tmp_path, "foo.rb", "module Foo\n  module Concern\n    def helper; end\n  end\nend\n")
    _write(tmp_path, "k.rb", "class K\n  include Foo::Concern\nend\n")
    mix = _mixes_in(extract(sorted(tmp_path.glob("*.rb")), cache_root=tmp_path, parallel=False))
    assert ("K", "Foo::Concern") in mix


def test_nested_declared_class_still_resolves_as_receiver(tmp_path: Path) -> None:
    """#2302 regression guard: qualifying labels must not break bare constant
    receivers — `Processor.new` / typed `p.run` still find `Billing::Processor`."""
    _write(tmp_path, "billing.rb",
           "module Billing\n  class Processor\n    def run\n      42\n    end\n  end\nend\n")
    _write(tmp_path, "caller.rb",
           "def process_all\n  p = Processor.new\n  p.run\nend\n")
    g = extract(sorted(tmp_path.glob("*.rb")), cache_root=tmp_path, parallel=False)
    assert _has_call_edge(g, "process_all", "Processor") is not None, \
        "Processor.new should still resolve to the nested-declared class"
    assert _has_call_edge(g, "process_all", "run") is not None, \
        "typed p.run should still resolve to Billing::Processor#run"


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


def test_ruby_suffixed_methods_extraction_and_labels(tmp_path: Path) -> None:
    """#3077: def foo, def foo!, def foo?, and def foo=(val) in the same class
    must all survive extraction with distinct IDs and raw labels."""
    f = _write(tmp_path, "thing.rb", """\
class Thing
  def foo; end
  def foo!; end
  def foo?; end
  def foo=(val); end
end
""")
    r = extract_ruby(f)
    assert "error" not in r
    method_nodes = [n for n in r["nodes"] if n["id"] != r["nodes"][0]["id"] and n.get("label") != "Thing"]
    assert len(method_nodes) == 4, f"Expected 4 distinct method nodes, got {method_nodes}"

    node_by_label = {n["label"]: n["id"] for n in r["nodes"]}
    assert ".foo()" in node_by_label
    assert ".foo!()" in node_by_label
    assert ".foo?()" in node_by_label
    assert ".foo=()" in node_by_label

    assert node_by_label[".foo()"].endswith("_foo")
    assert node_by_label[".foo!()"].endswith("_foo_bang")
    assert node_by_label[".foo?()"].endswith("_foo_pred")
    assert node_by_label[".foo=()"].endswith("_foo_eq")

    # Verify all 4 method edges exist
    method_edges = [e for e in r["edges"] if e.get("relation") == "method"]
    assert len(method_edges) == 4
    targets = {e["target"] for e in method_edges}
    assert len(targets) == 4


def test_ruby_suffixed_singleton_methods_extraction(tmp_path: Path) -> None:
    """#3077: Singleton methods (def self.foo!) must use the same sanitizer."""
    f = _write(tmp_path, "service.rb", """\
class Service
  def self.run!; end
  def self.valid?; end
end
""")
    r = extract_ruby(f)
    node_by_label = {n["label"]: n["id"] for n in r["nodes"]}
    assert ".run!()" in node_by_label
    assert ".valid?()" in node_by_label
    assert node_by_label[".run!()"].endswith("_run_bang")
    assert node_by_label[".valid?()"].endswith("_valid_pred")


def test_ruby_suffixed_toplevel_functions_extraction(tmp_path: Path) -> None:
    """#3077: Top-level functions (def parse!) must use the same sanitizer."""
    f = _write(tmp_path, "utils.rb", """\
def parse!; end
def valid?; end
""")
    r = extract_ruby(f)
    node_by_label = {n["label"]: n["id"] for n in r["nodes"]}
    assert "parse!()" in node_by_label
    assert "valid?()" in node_by_label
    assert node_by_label["parse!()"].endswith("_parse_bang")
    assert node_by_label["valid?()"].endswith("_valid_pred")


def test_ruby_suffixed_methods_call_resolution(tmp_path: Path) -> None:
    """#3077: Calls to p.save and p.save! must resolve to different target nodes."""
    acc_path = _write(tmp_path, "account.rb", """\
class Account
  def save
    1
  end
  def save!
    2
  end
  def valid?
    true
  end
end
""")
    client_path = _write(tmp_path, "client.rb", """\
def perform_save
  a = Account.new
  a.save
end

def perform_save_bang
  a = Account.new
  a.save!
end

def perform_valid_query
  a = Account.new
  a.valid?
end
""")
    g = extract([acc_path, client_path], cache_root=tmp_path / ".cache", parallel=False)
    node_by_id = {n["id"]: n for n in g["nodes"]}

    calls_by_caller = {}
    for e in g["edges"]:
        if e.get("relation") == "calls":
            caller_node = node_by_id.get(e["source"])
            target_node = node_by_id.get(e["target"])
            if caller_node and target_node:
                calls_by_caller.setdefault(caller_node["label"], []).append(target_node["label"])

    assert ".save()" in calls_by_caller.get("perform_save()", []), \
        f"perform_save should call .save(), got {calls_by_caller.get('perform_save()')}"
    assert ".save!()" in calls_by_caller.get("perform_save_bang()", []), \
        f"perform_save_bang should call .save!(), got {calls_by_caller.get('perform_save_bang()')}"
    assert ".valid?()" in calls_by_caller.get("perform_valid_query()", []), \
        f"perform_valid_query should call .valid?(), got {calls_by_caller.get('perform_valid_query()')}"


def test_ruby_suffixed_methods_id_stability(tmp_path: Path) -> None:
    """#3077: ID of foo! must remain stable when foo is added later."""
    f1 = _write(tmp_path, "model.rb", """\
class Model
  def foo!; end
end
""")
    r1 = extract_ruby(f1)
    node1 = next(n for n in r1["nodes"] if n.get("label") == ".foo!()")
    id1 = node1["id"]
    assert id1.endswith("_foo_bang")

    # Add def foo
    f2 = _write(tmp_path, "model.rb", """\
class Model
  def foo; end
  def foo!; end
end
""")
    r2 = extract_ruby(f2)
    node2_bang = next(n for n in r2["nodes"] if n.get("label") == ".foo!()")
    node2_plain = next(n for n in r2["nodes"] if n.get("label") == ".foo()")

    assert node2_bang["id"] == id1, "foo!'s ID must remain unchanged when foo is added"
    assert node2_plain["id"] != node2_bang["id"], "foo and foo! must have distinct IDs"
# ── #3078: a qualified receiver must respect its namespace ────────────────────


_LOCAL_BASE_RB = """\
class Thing
  class Base
    def self.call(x) = x
  end
end
"""

_BILLING_RB = """\
module Billing
  class Processor
    def self.run(x) = x
  end
end
"""

_SOLO_RB = """\
class Solo
  def self.go = 1
end
"""


def test_framework_qualified_receiver_does_not_bind_same_named_local_class(tmp_path: Path) -> None:
    """`ActiveRecord::Base.transaction` must not bind to an unrelated local `Base`.

    The receiver used to be truncated to its last constant, so any corpus with a
    single class named `Base` collected every framework call as an EXTRACTED 1.0
    edge — a false hub, not a missing edge. The namespace has to be part of the
    match (#3078). `ActiveJob::Base` is here too because both namespaces used to
    collapse onto the very same node.
    """
    _write(tmp_path, "thing.rb", _LOCAL_BASE_RB)
    caller = _write(tmp_path, "other.rb", """\
class Other
  def framework_ar
    ActiveRecord::Base.transaction { save! }
  end

  def framework_aj
    ActiveJob::Base.default_queue_name
  end
end
""")
    graph = extract([caller, tmp_path / "thing.rb"], cache_root=tmp_path, parallel=False)
    assert _has_call_edge(graph, "framework_ar", "Thing::Base") is None, \
        "ActiveRecord::Base must not bind to an unrelated local Thing::Base"
    assert _has_call_edge(graph, "framework_aj", "Thing::Base") is None, \
        "ActiveJob::Base must not bind to an unrelated local Thing::Base"


def test_qualified_receiver_still_resolves_inside_its_own_namespace(tmp_path: Path) -> None:
    """The namespace check must not cost a genuine `Billing::Processor.run` edge."""
    _write(tmp_path, "billing.rb", _BILLING_RB)
    caller = _write(tmp_path, "other.rb", """\
class Other
  def qualified
    Billing::Processor.run(1)
  end
end
""")
    graph = extract([caller, tmp_path / "billing.rb"], cache_root=tmp_path, parallel=False)
    edge = _has_call_edge(graph, "qualified", ".run()")
    assert edge is not None, "a correctly-namespaced receiver must still resolve"
    assert edge["confidence"] == "EXTRACTED"


def test_top_level_pinned_constant_receiver_still_resolves(tmp_path: Path) -> None:
    """`::Solo.go` pins the constant to top level and must keep resolving.

    Worth its own case: capturing the whole path means the receiver text now starts
    with `::`, so the constant-receiver check has to look past the leading colons.
    """
    _write(tmp_path, "solo.rb", _SOLO_RB)
    caller = _write(tmp_path, "other.rb", """\
class Other
  def pinned
    ::Solo.go
  end
end
""")
    graph = extract([caller, tmp_path / "solo.rb"], cache_root=tmp_path, parallel=False)
    assert _has_call_edge(graph, "pinned", ".go()") is not None, \
        "a top-level-pinned constant receiver must still resolve"
