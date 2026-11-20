"""Java member-level interface dispatch.

`this.worker.run()` on a field typed with the interface `Worker` resolves to
`Worker.run()`, which is what the call site names. The implementing
`EmailWorker.run()` is a separate node, and before this pass nothing joined the
two, so a directed walk from `Job.execute()` never reached the class that runs.

`resolve_java_interface_dispatch` is the `.java` gate over the shared
`graphify.interface_dispatch` mechanism the C#, Swift and Go passes use.
Confidence falls as the implementer count grows (0.85 / 0.75 / 0.65).
"""
from __future__ import annotations

from pathlib import Path

import pytest

from graphify.extract import extract

_FIXTURE = Path(__file__).parent / "fixtures" / "java_interface_dispatch"


def _extract(tmp_path: Path, files: dict[str, str]):
    for name, body in files.items():
        p = tmp_path / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body)
    r = extract(
        sorted(tmp_path / n for n in files),
        cache_root=tmp_path / "cache",
        root=tmp_path,
        parallel=False,
    )
    dispatch = {(e["source"], e["target"]) for e in r["edges"]
                if e["relation"] == "dispatches_to"}
    return dispatch, r


def _fixture_files() -> dict[str, str]:
    return {p.name: p.read_text() for p in sorted(_FIXTURE.glob("*.java"))}


def _find(r, label, id_contains):
    return next(n["id"] for n in r["nodes"]
                if n["label"] == label and id_contains in n["id"])


def _reachable(r, start: str) -> set[str]:
    adjacency: dict[str, list[str]] = {}
    for e in r["edges"]:
        adjacency.setdefault(e["source"], []).append(e["target"])
    seen = {start}
    queue = [start]
    while queue:
        for nxt in adjacency.get(queue.pop(0), []):
            if nxt not in seen:
                seen.add(nxt)
                queue.append(nxt)
    return seen


def test_call_through_an_interface_field_reaches_the_implementer(tmp_path):
    # Regression: before the Java pass, the walk from Job.execute() stopped at
    # Worker.run() and never reached EmailWorker.run() or its callees.
    dispatch, r = _extract(tmp_path, _fixture_files())
    requirement = _find(r, ".run()", "worker_worker")
    concrete = _find(r, ".run()", "emailworker")
    execute = _find(r, ".execute()", "job")
    assert dispatch == {(requirement, concrete)}
    reachable = _reachable(r, execute)
    assert concrete in reachable
    assert _find(r, ".send()", "emailworker") in reachable


def test_dispatch_edge_shape_and_the_call_is_kept(tmp_path):
    _, r = _extract(tmp_path, _fixture_files())
    edge = next(e for e in r["edges"] if e["relation"] == "dispatches_to")
    assert edge["confidence"] == "INFERRED"
    assert edge["confidence_score"] == 0.85
    assert edge["context"] == "call"
    assert edge["source_file"].endswith("EmailWorker.java")
    # Additive: the call site still names the interface method.
    calls = {(e["source"], e["target"]) for e in r["edges"] if e["relation"] == "calls"}
    assert (_find(r, ".execute()", "job"), _find(r, ".run()", "worker_worker")) in calls


def test_two_implementers_both_get_an_edge_at_lower_confidence(tmp_path):
    files = _fixture_files()
    files["SmsWorker.java"] = "public class SmsWorker implements Worker { public void run() { } }\n"
    dispatch, r = _extract(tmp_path, files)
    requirement = _find(r, ".run()", "worker_worker")
    assert dispatch == {
        (requirement, _find(r, ".run()", "emailworker")),
        (requirement, _find(r, ".run()", "smsworker")),
    }
    scores = {e["confidence_score"] for e in r["edges"] if e["relation"] == "dispatches_to"}
    assert scores == {0.75}


def test_three_implementers_floor_at_the_weak_inference_tier(tmp_path):
    files = _fixture_files()
    files["SmsWorker.java"] = "public class SmsWorker implements Worker { public void run() { } }\n"
    files["PushWorker.java"] = "public class PushWorker implements Worker { public void run() { } }\n"
    dispatch, r = _extract(tmp_path, files)
    assert len(dispatch) == 3
    scores = {e["confidence_score"] for e in r["edges"] if e["relation"] == "dispatches_to"}
    assert scores == {0.65}


def test_overload_links_only_the_matching_signature(tmp_path):
    # Each Java overload is its own node; the edge goes to the one whose
    # signature the interface declares, not to its sibling.
    dispatch, r = _extract(tmp_path, {
        "Sender.java": "public interface Sender { void send(String to); }\n",
        "MailSender.java": (
            "public class MailSender implements Sender {\n"
            "    public void send(String to) { }\n"
            "    public void send(String to, String cc) { }\n"
            "}\n"
        ),
    })
    sends = {n["source_location"]: n["id"] for n in r["nodes"]
             if n["label"].startswith(".send(") and "mailsender" in n["id"]}
    assert len(sends) == 2
    assert dispatch == {(_find(r, ".send()", "sender_sender"), sends["L2"])}
    score = next(e["confidence_score"] for e in r["edges"] if e["relation"] == "dispatches_to")
    assert score == 0.85


def _sends(r, owner):
    """`(signature, node id)` for each `.send` overload declared on `owner`."""
    return {(n.get("metadata") or {}).get("signature"): n["id"] for n in r["nodes"]
            if n["label"].startswith(".send(") and n["id"].startswith(owner + "_")}


def test_overloads_on_both_sides_pair_one_to_one(tmp_path):
    dispatch, r = _extract(tmp_path, {
        "Sender.java": "public interface Sender { void send(String to); void send(String to, String cc); }\n",
        "MailSender.java": (
            "public class MailSender implements Sender {\n"
            "    public void send(String to) { }\n"
            "    public void send(String to, String cc) { }\n"
            "}\n"
        ),
    })
    iface, impl = _sends(r, "sender_sender"), _sends(r, "mailsender_mailsender")
    assert dispatch == {
        (iface["String"], impl["String"]),
        (iface["String,String"], impl["String,String"]),
    }


def test_same_arity_overloads_pair_by_parameter_type(tmp_path):
    # Arity cannot split send(String) from send(int); the erased signature does.
    dispatch, r = _extract(tmp_path, {
        "Sender.java": "public interface Sender { void send(String to); void send(int n); }\n",
        "MailSender.java": (
            "public class MailSender implements Sender {\n"
            "    public void send(String to) { }\n"
            "    public void send(int n) { }\n"
            "}\n"
        ),
    })
    iface, impl = _sends(r, "sender_sender"), _sends(r, "mailsender_mailsender")
    assert dispatch == {(iface["String"], impl["String"]), (iface["int"], impl["int"])}


def test_an_interface_overload_with_no_implementation_gets_no_edge(tmp_path):
    dispatch, r = _extract(tmp_path, {
        "Sender.java": "public interface Sender { void send(String to); void send(String to, String cc); }\n",
        "MailSender.java": (
            "public abstract class MailSender implements Sender {\n"
            "    public void send(String to) { }\n"
            "}\n"
        ),
    })
    iface, impl = _sends(r, "sender_sender"), _sends(r, "mailsender_mailsender")
    assert dispatch == {(iface["String"], impl["String"])}


def test_two_candidates_neither_matching_get_no_edge(tmp_path):
    dispatch, _ = _extract(tmp_path, {
        "Sender.java": "public interface Sender { void send(String to); }\n",
        "MailSender.java": (
            "public class MailSender implements Sender {\n"
            "    public void send(Integer n) { }\n"
            "    public void send(Long n) { }\n"
            "}\n"
        ),
    })
    assert not dispatch


def test_a_lone_same_named_method_is_linked_whatever_its_signature(tmp_path):
    # Known limit: one interface method and one implementer method of a name
    # pair up without comparing signatures (the shared one-to-one rule), so a
    # send(int, int) beside an inherited send(String) still gets the edge.
    dispatch, r = _extract(tmp_path, {
        "Sender.java": "public interface Sender { void send(String to); }\n",
        "Base.java": "public class Base { public void send(String to) { } }\n",
        "MailSender.java": (
            "public class MailSender extends Base implements Sender {\n"
            "    public void send(int a, int b) { }\n"
            "}\n"
        ),
    })
    iface, impl = _sends(r, "sender_sender"), _sends(r, "mailsender_mailsender")
    assert dispatch == {(iface["String"], impl["int,int"])}


def test_constructor_is_not_a_dispatch_target(tmp_path):
    # The constructor is labelled after the class, so only the run() method can
    # match the interface; this pins that a constructor never adds a candidate.
    dispatch, r = _extract(tmp_path, {
        "Worker.java": "public interface Worker { void run(); }\n",
        "EmailWorker.java": (
            "public class EmailWorker implements Worker {\n"
            "    public EmailWorker() { }\n"
            "    public void run() { }\n"
            "}\n"
        ),
    })
    assert dispatch == {(_find(r, ".run()", "worker_worker"), _find(r, ".run()", "emailworker"))}


def test_no_matching_member_produces_no_edge(tmp_path):
    dispatch, _ = _extract(tmp_path, {
        "Worker.java": "public interface Worker { void run(); }\n",
        "EmailWorker.java": "public class EmailWorker implements Worker { public void stop() { } }\n",
    })
    assert not dispatch


def test_abstract_base_class_is_out_of_scope(tmp_path):
    # `extends` is an `inherits` edge, and a base method may well be the real
    # target, so walking inheritance is a different bet from dispatch.
    dispatch, _ = _extract(tmp_path, {
        "Base.java": "public abstract class Base { public abstract void run(); }\n",
        "Impl.java": "public class Impl extends Base { public void run() { } }\n",
    })
    assert not dispatch


def test_interface_hierarchy_is_not_walked_transitively(tmp_path):
    # Known limit: Worker's only implementer is the interface Task, which
    # declares nothing, so Worker.run never reaches Impl.run.
    dispatch, _ = _extract(tmp_path, {
        "Worker.java": "public interface Worker { void run(); }\n",
        "Task.java": "public interface Task extends Worker { }\n",
        "Impl.java": "public class Impl implements Task { public void run() { } }\n",
    })
    assert not dispatch


def test_an_unoverridden_default_method_is_not_dispatched(tmp_path):
    # The call really does land on the default body, so only `stop` links.
    dispatch, r = _extract(tmp_path, {
        "Worker.java": "public interface Worker { default void run() { } void stop(); }\n",
        "EmailWorker.java": "public class EmailWorker implements Worker { public void stop() { } }\n",
    })
    assert dispatch == {(_find(r, ".stop()", "worker_worker"), _find(r, ".stop()", "emailworker"))}


def test_enum_record_and_generic_implementers_link(tmp_path):
    dispatch, r = _extract(tmp_path, {
        "Worker.java": "public interface Worker<T> { void run(T job); }\n",
        "Mode.java": "public enum Mode implements Worker<String> { A; public void run(String job) { } }\n",
        "Once.java": "public record Once(int n) implements Worker<String> { public void run(String job) { } }\n",
    })
    requirement = _find(r, ".run()", "worker_worker")
    assert dispatch == {
        (requirement, _find(r, ".run()", "mode_mode")),
        (requirement, _find(r, ".run()", "once_once")),
    }


def test_a_same_named_interface_in_another_language_is_not_linked(tmp_path):
    # `implements` resolves by name, so a Java class naming `Worker` can bind to
    # a C# `Worker` when that is the only node with the name. Neither the C# nor
    # the Java pass may link the pair: it is a collision, not an implementation.
    dispatch, _ = _extract(tmp_path, {
        "Worker.cs": "public interface Worker { void run(); }\n",
        "EmailWorker.java": "public class EmailWorker implements Worker { public void run() { } }\n",
    })
    assert not dispatch


def test_a_same_named_kotlin_interface_is_not_linked(tmp_path):
    pytest.importorskip("tree_sitter_kotlin")
    dispatch, _ = _extract(tmp_path, {
        "Worker.kt": "interface Worker { fun run() }\n",
        "EmailWorker.java": "public class EmailWorker implements Worker { public void run() { } }\n",
    })
    assert not dispatch


def test_a_csharp_implementer_of_a_java_interface_is_not_linked(tmp_path):
    dispatch, _ = _extract(tmp_path, {
        "Worker.java": "public interface Worker { void run(); }\n",
        "EmailWorker.cs": "public class EmailWorker : Worker { public void run() { } }\n",
    })
    assert not dispatch


_TWO_WORKERS = {
    "a/Worker.java": "package a;\n\npublic interface Worker { void run(); }\n",
    "b/Worker.java": "package b;\n\npublic interface Worker { void run(); }\n",
}


def test_same_simple_name_in_two_packages_links_only_the_imported_one(tmp_path):
    dispatch, r = _extract(tmp_path, {**_TWO_WORKERS, "c/EmailWorker.java": (
        "package c;\n\nimport a.Worker;\n\n"
        "public class EmailWorker implements Worker { public void run() { } }\n"
    )})
    assert dispatch == {(_find(r, ".run()", "a_worker_worker"), _find(r, ".run()", "c_emailworker"))}


def test_a_qualified_implements_clause_is_a_known_limit(tmp_path):
    # Known limit: `implements a.Worker` with no import binds to a sourceless
    # `Worker` stub rather than a.Worker, so no edge is drawn. It fails closed:
    # b.Worker, the other same-named interface, never gets one either.
    dispatch, _ = _extract(tmp_path, {**_TWO_WORKERS, "c/EmailWorker.java": (
        "package c;\n\n"
        "public class EmailWorker implements a.Worker { public void run() { } }\n"
    )})
    assert not dispatch


def test_a_csharp_pair_is_untouched_by_the_java_pass():
    from graphify.java_dispatch import resolve_java_interface_dispatch

    nodes = [
        {"id": "iface", "label": "IR", "source_file": "a.cs", "_callable_class": True},
        {"id": "impl", "label": "A", "source_file": "a.cs", "_callable_class": True},
        {"id": "iface_m", "label": ".M()", "source_file": "a.cs", "_callable": True},
        {"id": "impl_m", "label": ".M()", "source_file": "a.cs", "_callable": True},
    ]
    edges = [
        {"source": "impl", "target": "iface", "relation": "implements"},
        {"source": "iface", "target": "iface_m", "relation": "method"},
        {"source": "impl", "target": "impl_m", "relation": "method"},
    ]
    resolve_java_interface_dispatch([], nodes, edges)
    assert not any(e["relation"] == "dispatches_to" for e in edges)


def test_java_pass_is_registered_with_the_other_dispatch_passes():
    import graphify.extract  # noqa: F401  (registers resolvers on import)
    from graphify.resolver_registry import registered_resolvers

    names = [r.name for r in registered_resolvers()]
    assert "java_interface_dispatch" in names
    assert names.index("java_member_calls") < names.index("java_interface_dispatch")
