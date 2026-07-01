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
