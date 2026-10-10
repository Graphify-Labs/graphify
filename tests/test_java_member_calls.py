"""Java receiver-typed member-call resolution.

Java ``method_invocation`` nodes carry both the method name and its receiver,
but the generic extractor currently resolves only by the bare method name.  A
typed receiver must select the method owned by its declared type; unresolved or
ambiguous receivers must stay unlinked rather than creating a false call edge.
"""
from __future__ import annotations

from pathlib import Path

from graphify.extract import extract


def _calls(tmp_path: Path, files: dict[str, str]):
    paths = []
    for name, body in files.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
        paths.append(path)
    result = extract(paths, cache_root=tmp_path / "graphify-out")
    calls = {
        (edge["source"], edge["target"])
        for edge in result["edges"]
        if edge.get("relation") == "calls"
    }
    return calls, result


def _find(result: dict, label: str, id_contains: str) -> str:
    return next(
        node["id"]
        for node in result["nodes"]
        if node.get("label") == label and id_contains in node["id"]
    )


_AMBIGUOUS_METHODS = {
    "Services.java": (
        "class PaymentGateway { static void ping() {} void charge() {} }\n"
        "class AuditLog { static void ping() {} void charge() {} }\n"
    ),
}


def test_explicit_type_receiver_resolves_to_owned_method(tmp_path: Path):
    calls, result = _calls(tmp_path, {
        **_AMBIGUOUS_METHODS,
        "Checkout.java": (
            "class Checkout { void run() { PaymentGateway.ping(); } }\n"
        ),
    })

    run = _find(result, ".run()", "checkout")
    gateway_ping = _find(result, ".ping()", "paymentgateway")
    audit_ping = _find(result, ".ping()", "auditlog")
    assert (run, gateway_ping) in calls
    assert (run, audit_ping) not in calls


def test_field_receiver_resolves_to_declared_type(tmp_path: Path):
    calls, result = _calls(tmp_path, {
        **_AMBIGUOUS_METHODS,
        "Checkout.java": (
            "class Checkout {\n"
            "    void run() { gateway.charge(); }\n"
            "    PaymentGateway gateway;\n"
            "}\n"
        ),
    })

    run = _find(result, ".run()", "checkout")
    gateway_charge = _find(result, ".charge()", "paymentgateway")
    audit_charge = _find(result, ".charge()", "auditlog")
    assert (run, gateway_charge) in calls
    assert (run, audit_charge) not in calls


def test_this_field_receiver_resolves_to_declared_type(tmp_path: Path):
    calls, result = _calls(tmp_path, {
        **_AMBIGUOUS_METHODS,
        "Checkout.java": (
            "class Checkout {\n"
            "    PaymentGateway gateway;\n"
            "    void run() { this.gateway.charge(); }\n"
            "}\n"
        ),
    })

    run = _find(result, ".run()", "checkout")
    gateway_charge = _find(result, ".charge()", "paymentgateway")
    assert (run, gateway_charge) in calls


def test_this_field_uses_field_type_when_parameter_shadows_name(tmp_path: Path):
    calls, result = _calls(tmp_path, {
        **_AMBIGUOUS_METHODS,
        "Checkout.java": (
            "class Checkout {\n"
            "    PaymentGateway service;\n"
            "    void run(AuditLog service) {\n"
            "        service.charge();\n"
            "        this.service.charge();\n"
            "    }\n"
            "}\n"
        ),
    })

    run = _find(result, ".run()", "checkout")
    gateway_charge = _find(result, ".charge()", "paymentgateway")
    audit_charge = _find(result, ".charge()", "auditlog")
    assert (run, gateway_charge) in calls
    assert (run, audit_charge) in calls


def test_parameter_and_local_receivers_resolve_per_method(tmp_path: Path):
    calls, result = _calls(tmp_path, {
        **_AMBIGUOUS_METHODS,
        "Checkout.java": (
            "class Checkout {\n"
            "    void fromParameter(PaymentGateway service) { service.charge(); }\n"
            "    void fromLocal() { AuditLog service = new AuditLog(); service.charge(); }\n"
            "}\n"
        ),
    })

    from_parameter = _find(result, ".fromParameter()", "checkout")
    from_local = _find(result, ".fromLocal()", "checkout")
    gateway_charge = _find(result, ".charge()", "paymentgateway")
    audit_charge = _find(result, ".charge()", "auditlog")
    assert (from_parameter, gateway_charge) in calls
    assert (from_parameter, audit_charge) not in calls
    assert (from_local, audit_charge) in calls
    assert (from_local, gateway_charge) not in calls


def test_nested_receiver_bindings_do_not_escape_their_scope(tmp_path: Path):
    calls, result = _calls(tmp_path, {
        **_AMBIGUOUS_METHODS,
        "Checkout.java": (
            "class Checkout {\n"
            "    PaymentGateway service;\n"
            "    void blockLocal() {\n"
            "        service.charge();\n"
            "        { AuditLog service = null; service.charge(); }\n"
            "    }\n"
            "    void anonymousClass() {\n"
            "        new Object() { void nested() { AuditLog service = null; } };\n"
            "        service.charge();\n"
            "    }\n"
            "}\n"
        ),
    })

    block_local = _find(result, ".blockLocal()", "checkout")
    anonymous_class = _find(result, ".anonymousClass()", "checkout")
    gateway_charge = _find(result, ".charge()", "paymentgateway")
    audit_charge = _find(result, ".charge()", "auditlog")
    assert not any(source == block_local and "charge" in target
                   for source, target in calls)
    assert (anonymous_class, gateway_charge) in calls
    assert (anonymous_class, audit_charge) not in calls


def test_lambda_shadowing_does_not_reuse_enclosing_receiver_type(tmp_path: Path):
    calls, result = _calls(tmp_path, {
        **_AMBIGUOUS_METHODS,
        "Checkout.java": (
            "class Checkout {\n"
            "    PaymentGateway service;\n"
            "    void captured() {\n"
            "        Runnable task = () -> service.charge();\n"
            "    }\n"
            "    void shadowed() {\n"
            "        java.util.function.Consumer<AuditLog> task =\n"
            "            service -> service.charge();\n"
            "    }\n"
            "    void parenthesized() {\n"
            "        java.util.function.Consumer<AuditLog> task =\n"
            "            (service) -> service.charge();\n"
            "    }\n"
            "    void typed() {\n"
            "        java.util.function.Consumer<AuditLog> task =\n"
            "            (AuditLog service) -> service.charge();\n"
            "    }\n"
            "    void sameType() {\n"
            "        java.util.function.Consumer<PaymentGateway> task =\n"
            "            (PaymentGateway service) -> service.charge();\n"
            "    }\n"
            "}\n"
        ),
    })

    captured = _find(result, ".captured()", "checkout")
    same_type = _find(result, ".sameType()", "checkout")
    shadowed_callers = {
        _find(result, f".{name}()", "checkout")
        for name in ("shadowed", "parenthesized", "typed")
    }
    gateway_charge = _find(result, ".charge()", "paymentgateway")
    assert (captured, gateway_charge) in calls
    assert (same_type, gateway_charge) in calls
    assert not any(source in shadowed_callers and "charge" in target
                   for source, target in calls)


def test_overloaded_callers_keep_body_scoped_receiver_types(tmp_path: Path):
    calls, result = _calls(tmp_path, {
        **_AMBIGUOUS_METHODS,
        "Checkout.java": (
            "class Checkout {\n"
            "    void run(int value) { PaymentGateway service = null; service.charge(); }\n"
            "    void run(String value) { AuditLog service = null; service.charge(); }\n"
            "}\n"
        ),
    })

    run = _find(result, ".run()", "checkout")
    gateway_charge = _find(result, ".charge()", "paymentgateway")
    audit_charge = _find(result, ".charge()", "auditlog")
    assert (run, gateway_charge) in calls
    assert (run, audit_charge) in calls


def test_ambiguous_receiver_type_emits_no_edge(tmp_path: Path):
    calls, result = _calls(tmp_path, {
        "a/Gateway.java": "package a; public class Gateway { public void send() {} }\n",
        "b/Gateway.java": "package b; public class Gateway { public void send() {} }\n",
        "Caller.java": (
            "class Caller { void run(Gateway gateway) { gateway.send(); } }\n"
        ),
    })

    run = _find(result, ".run()", "caller")
    send_targets = {
        target
        for source, target in calls
        if source == run and "send" in target
    }
    assert send_targets == set()


def test_inherited_field_resolves_and_chained_receiver_stays_deferred(tmp_path: Path):
    """#3151: a field declared on the superclass now types `this.<field>` in
    the subclass, so `this.gateway.charge()` resolves. A chained receiver
    (`factory.create().charge()`) still carries no declared type and stays
    deferred rather than guessed."""
    calls, result = _calls(tmp_path, {
        "Services.java": (
            "class Gateway { void charge() {} Gateway create() { return this; } }\n"
            "class Base { Gateway gateway; }\n"
            "class Checkout extends Base {\n"
            "    Gateway factory;\n"
            "    void inherited() { this.gateway.charge(); }\n"
            "    void chained() { factory.create().charge(); }\n"
            "}\n"
        ),
    })

    inherited = _find(result, ".inherited()", "checkout")
    chained = _find(result, ".chained()", "checkout")
    assert any(source == inherited and "charge" in target
               for source, target in calls), "superclass field must type the receiver"
    assert not any(source == chained and "charge" in target
                   for source, target in calls)


def test_unqualified_call_still_resolves(tmp_path: Path):
    calls, result = _calls(tmp_path, {
        "Checkout.java": (
            "class Checkout {\n"
            "    void run() { helper(); this.other(); }\n"
            "    void helper() {}\n"
            "    void other() {}\n"
            "}\n"
        ),
    })

    run = _find(result, ".run()", "checkout")
    helper = _find(result, ".helper()", "checkout")
    other = _find(result, ".other()", "checkout")
    assert (run, helper) in calls
    assert (run, other) in calls


def test_inherited_method_resolves_for_this_field_and_parameter_receivers(tmp_path: Path):
    calls, result = _calls(tmp_path, {
        "Base.java": "class Base { void start() {} }\n",
        "Worker.java": (
            "class Worker extends Base {\n"
            "    void viaThis() { this.start(); }\n"
            "}\n"
        ),
        "Service.java": (
            "class Service {\n"
            "    Worker worker;\n"
            "    void viaField() { worker.start(); }\n"
            "    void viaParam(Worker w) { w.start(); }\n"
            "}\n"
        ),
    })

    start = _find(result, ".start()", "base_start")
    assert (_find(result, ".viaThis()", "worker_viathis"), start) in calls
    assert (_find(result, ".viaField()", "service_viafield"), start) in calls
    assert (_find(result, ".viaParam()", "service_viaparam"), start) in calls


def test_nearest_declaration_on_the_superclass_chain_wins(tmp_path: Path):
    calls, result = _calls(tmp_path, {
        "Chain.java": (
            "class Root { void start() {} void stop() {} }\n"
            "class Middle extends Root { void stop() {} }\n"
            "class Leaf extends Middle {}\n"
            "class Client { void run(Leaf leaf) { leaf.start(); leaf.stop(); } }\n"
        ),
    })

    run = _find(result, ".run()", "client_run")
    assert (run, _find(result, ".start()", "root_start")) in calls
    assert (run, _find(result, ".stop()", "middle_stop")) in calls
    assert (run, _find(result, ".stop()", "root_stop")) not in calls


def test_super_call_resolves_to_the_superclass_declaration(tmp_path: Path):
    calls, result = _calls(tmp_path, {
        "Base.java": "class Base { void close() {} }\n",
        "Worker.java": (
            "class Worker extends Base {\n"
            "    void close() { super.close(); }\n"
            "}\n"
        ),
    })

    worker_close = _find(result, ".close()", "worker_close")
    base_close = _find(result, ".close()", "base_close")
    assert (worker_close, base_close) in calls
    assert any(
        edge.get("relation") == "calls"
        and (edge["source"], edge["target"]) == (worker_close, base_close)
        and edge.get("confidence") == "EXTRACTED"
        for edge in result["edges"]
    )


def test_ancestor_outside_the_corpus_leaves_inherited_call_unresolved(tmp_path: Path):
    calls, result = _calls(tmp_path, {
        "Named.java": "interface Named { String name(); }\n",
        "Entity.java": (
            "import org.example.Identified;\n"
            "interface Entity extends Identified, Named {}\n"
        ),
        "Client.java": "class Client { void run(Entity e) { e.name(); } }\n",
    })

    run = _find(result, ".run()", "client_run")
    assert not any(source == run for source, _ in calls)


def test_super_call_is_not_bound_back_to_the_calling_class(tmp_path: Path):
    calls, result = _calls(tmp_path, {
        "lib/Handler.java": "package lib;\npublic class Handler { public void handle() {} }\n",
        "app/Handler.java": (
            "package app;\n"
            "public class Handler extends lib.Handler {\n"
            "    public void handle() {}\n"
            "    public void retry() { super.handle(); }\n"
            "}\n"
        ),
    })

    retry = _find(result, ".retry()", "handler_retry")
    assert not any(source == retry for source, _ in calls)


def test_inherited_call_is_not_bound_to_another_language(tmp_path: Path):
    calls, result = _calls(tmp_path, {
        "Worker.java": (
            "import org.lib.*;\n"
            "class Worker extends Base { void run() { this.start(); super.start(); } }\n"
        ),
        "tools/base.py": "class Base:\n    def start(self):\n        pass\n",
    })

    run = _find(result, ".run()", "worker_run")
    assert not any(source == run for source, _ in calls)


# A name declared by two unrelated classes, so no corpus-wide unique-name match
# can stand in for the supertype lookup.
_TWO_GATEWAYS = {
    "Gateway.java": "class Gateway { void charge() {} }\n",
    "Audit.java": "class Audit { void charge() {} boolean isRegistered() { return false; } }\n",
}


def test_bare_call_reaches_a_method_inherited_from_another_file(tmp_path: Path):
    calls, result = _calls(tmp_path, {
        **_TWO_GATEWAYS,
        "Base.java": "abstract class Base { boolean isRegistered() { return true; } }\n",
        "Child.java": "class Child extends Base { boolean check() { return isRegistered(); } }\n",
    })

    check = _find(result, ".check()", "child_check")
    assert (check, _find(result, ".isRegistered()", "base_isregistered")) in calls
    assert (check, _find(result, ".isRegistered()", "audit_isregistered")) not in calls


def test_bare_call_reaches_an_interface_default_method(tmp_path: Path):
    calls, result = _calls(tmp_path, {
        **_TWO_GATEWAYS,
        "Registry.java": "interface Registry { default boolean isRegistered() { return true; } }\n",
        "Child.java": "class Child implements Registry { boolean check() { return isRegistered(); } }\n",
    })

    check = _find(result, ".check()", "child_check")
    assert (check, _find(result, ".isRegistered()", "registry_isregistered")) in calls


def test_bare_call_takes_the_nearest_supertype_declaring_it(tmp_path: Path):
    calls, result = _calls(tmp_path, {
        "Root.java": "class Root { void stop() {} }\n",
        "Middle.java": "class Middle extends Root { void stop() {} }\n",
        "Leaf.java": "class Leaf extends Middle { void run() { stop(); } }\n",
    })

    run = _find(result, ".run()", "leaf_run")
    assert (run, _find(result, ".stop()", "middle_stop")) in calls
    assert (run, _find(result, ".stop()", "root_stop")) not in calls


def test_superclass_method_wins_over_an_interface_default(tmp_path: Path):
    # Java's "class wins": Root.log() beats Loud's default, even from a deeper level.
    calls, result = _calls(tmp_path, {
        "Root.java": "class Root { void log() {} }\n",
        "Base.java": "class Base extends Root {}\n",
        "Loud.java": "interface Loud { default void log() {} }\n",
        "Child.java": "class Child extends Base implements Loud { void run() { log(); } }\n",
    })

    run = _find(result, ".run()", "child_run")
    assert (run, _find(result, ".log()", "root_log")) in calls
    assert (run, _find(result, ".log()", "loud_log")) not in calls


def test_bare_call_declared_by_two_interfaces_binds_nothing(tmp_path: Path):
    calls, result = _calls(tmp_path, {
        "Loud.java": "interface Loud { void log(); }\n",
        "Quiet.java": "interface Quiet { void log(); }\n",
        "Child.java": "abstract class Child implements Loud, Quiet { void run() { log(); } }\n",
    })

    run = _find(result, ".run()", "child_run")
    assert not any(source == run and "log" in target for source, target in calls)


def test_base_constructor_call_is_not_an_inherited_method(tmp_path: Path):
    calls, result = _calls(tmp_path, {
        "Base.java": "class Base { Base() {} Base copy() { return new Base(); } }\n",
        "Child.java": "class Child extends Base { Base make() { return new Base(); } }\n",
    })

    make = _find(result, ".make()", "child_make")
    assert (make, _find(result, ".Base()", "base_base_base")) not in calls


def test_bare_field_receiver_inherited_from_another_file(tmp_path: Path):
    calls, result = _calls(tmp_path, {
        **_TWO_GATEWAYS,
        "Base.java": "abstract class Base { protected Gateway gateway; }\n",
        "Child.java": "class Child extends Base { void pay() { gateway.charge(); } }\n",
    })

    pay = _find(result, ".pay()", "child_pay")
    assert (pay, _find(result, ".charge()", "gateway_charge")) in calls
    assert (pay, _find(result, ".charge()", "audit_charge")) not in calls


def test_local_names_shadow_an_inherited_field(tmp_path: Path):
    # A parameter, a `var` local and a lambda parameter named like the inherited
    # field are not the field: none of these calls may reach Gateway.charge().
    calls, result = _calls(tmp_path, {
        **_TWO_GATEWAYS,
        "Base.java": "abstract class Base { protected Gateway gateway; }\n",
        "Child.java": (
            "import java.util.List;\n"
            "class Child extends Base {\n"
            "    void viaParam(Audit gateway) { gateway.charge(); }\n"
            "    void viaVar() { var gateway = new Audit(); gateway.charge(); }\n"
            "    void viaLambda(List<Audit> xs) { xs.forEach(gateway -> gateway.charge()); }\n"
            "}\n"
        ),
    })

    gateway_charge = _find(result, ".charge()", "gateway_charge")
    for caller in ("viaParam", "viaVar", "viaLambda"):
        assert (_find(result, f".{caller}()", caller.lower()), gateway_charge) not in calls, caller
    assert (_find(result, ".viaParam()", "viaparam"), _find(result, ".charge()", "audit_charge")) in calls


def test_schema_bump_retires_java_entries_cached_without_the_unbound_marker(tmp_path: Path, monkeypatch):
    """An entry from schema 7 has no `receiver_unbound` marker; replaying it would
    leave `gateway.charge()` on an inherited field unlinked."""
    import graphify.cache as cache_mod
    from graphify.cache import save_cached
    from graphify.extract import extract_java

    files = {
        **_TWO_GATEWAYS,
        "Base.java": "abstract class Base { protected Gateway gateway; }\n",
        "Child.java": "class Child extends Base { void pay() { gateway.charge(); } }\n",
    }
    paths = []
    for name, body in files.items():
        (tmp_path / name).write_text(body, encoding="utf-8")
        paths.append(tmp_path / name)
    current_schema = cache_mod._AST_CACHE_SCHEMA
    monkeypatch.setattr(cache_mod, "_EXTRACTOR_VERSION", "same-version")
    monkeypatch.setattr(cache_mod, "_AST_CACHE_SCHEMA", 7)  # last schema without the marker
    monkeypatch.setattr(cache_mod, "_cleaned_ast_dirs", set())
    for p in paths:
        stale = extract_java(p)
        for raw_call in stale.get("raw_calls", []):
            raw_call.pop("receiver_unbound", None)
        save_cached(p, stale, root=tmp_path, cache_root=tmp_path, kind="ast")

    monkeypatch.setattr(cache_mod, "_AST_CACHE_SCHEMA", current_schema)
    monkeypatch.setattr(cache_mod, "_cleaned_ast_dirs", set())
    r = extract(paths, root=tmp_path, cache_root=tmp_path, parallel=False)
    calls = {(e["source"], e["target"]) for e in r["edges"] if e["relation"] == "calls"}
    assert (_find(r, ".pay()", "child_pay"), _find(r, ".charge()", "gateway_charge")) in calls
