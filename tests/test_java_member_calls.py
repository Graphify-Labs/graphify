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


def test_inherited_field_and_chained_receiver_are_deferred(tmp_path: Path):
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
    assert not any(source in {inherited, chained} and "charge" in target
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
