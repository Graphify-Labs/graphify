"""Java receiver-typed member-call resolution.

Java ``method_invocation`` nodes carry both the method name and its receiver,
but the generic extractor currently resolves only by the bare method name.  A
typed receiver must select the method owned by its declared type; unresolved or
ambiguous receivers must stay unlinked rather than creating a false call edge.
"""
from __future__ import annotations

import json
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


def test_inherited_field_resolves_and_chained_receiver_follows_return_type(tmp_path: Path):
    """#3151: a field declared on the superclass now types `this.<field>` in
    the subclass, so `this.gateway.charge()` resolves. A chained receiver
    (`factory.create().charge()`) is typed by `create()`'s declared return."""
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
    assert any(source == chained and "charge" in target
               for source, target in calls), "create() declares Gateway"


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


# Builder steps named like methods of an unrelated class, so only the declared
# return types can pick the right ones.
_BUILDER = {
    "Product.java": "class Product { void ship() {} }\n",
    "Builder.java": (
        "class Builder {\n"
        "    Builder size(int n) { return this; }\n"
        "    Product build() { return new Product(); }\n"
        "}\n"
    ),
    "Factory.java": "class Factory { static Builder builder() { return new Builder(); } }\n",
    "Decoy.java": "class Decoy { Decoy size(int n) { return this; } void build() {} void ship() {} }\n",
}


def _owner_of(result: dict, method_nid: str) -> str:
    nodes = {n["id"]: n for n in result["nodes"]}
    return next(nodes[e["source"]]["label"] for e in result["edges"]
                if e["relation"] == "method" and e["target"] == method_nid)


def _call_owners(calls, result: dict, caller: str) -> set[tuple[str, str]]:
    nodes = {n["id"]: n for n in result["nodes"]}
    return {(_owner_of(result, t), nodes[t]["label"]) for s, t in calls if s == caller}


def test_call_chain_is_typed_from_declared_return_types(tmp_path: Path):
    calls, result = _calls(tmp_path, {
        **_BUILDER,
        "Client.java": "class Client { void run() { Factory.builder().size(3).build().ship(); } }\n",
    })

    owners = _call_owners(calls, result, _find(result, ".run()", "client_run"))
    assert {("Builder", ".size()"), ("Builder", ".build()"), ("Product", ".ship()")} <= owners
    assert not any(owner == "Decoy" for owner, _ in owners)


def test_new_cast_and_bare_call_receivers_are_typed(tmp_path: Path):
    calls, result = _calls(tmp_path, {
        **_BUILDER,
        "Client.java": (
            "class Client {\n"
            "    Builder mine() { return new Builder(); }\n"
            "    void viaNew() { new Builder().size(1); }\n"
            "    void viaCast(Object o) { ((Builder) o).build(); }\n"
            "    void viaBare() { mine().build(); }\n"
            "    void viaField() { this.factory().size(2); }\n"
            "    Builder factory() { return Factory.builder(); }\n"
            "}\n"
        ),
    })

    assert ("Builder", ".size()") in _call_owners(calls, result, _find(result, ".viaNew()", "vianew"))
    assert ("Builder", ".build()") in _call_owners(calls, result, _find(result, ".viaCast()", "viacast"))
    assert ("Builder", ".build()") in _call_owners(calls, result, _find(result, ".viaBare()", "viabare"))
    assert ("Builder", ".size()") in _call_owners(calls, result, _find(result, ".viaField()", "viafield"))


def test_return_type_named_in_several_files_is_the_returning_files_own(tmp_path: Path):
    calls, result = _calls(tmp_path, {
        "Alpha.java": (
            "class Alpha {\n"
            "    static Builder builder() { return new Builder(); }\n"
            "    static class Builder { Alpha get() { return null; } }\n"
            "}\n"
        ),
        "Beta.java": (
            "class Beta {\n"
            "    static class Builder { Beta get() { return null; } }\n"
            "}\n"
        ),
        "Client.java": "class Client { void run() { Alpha.builder().get(); } }\n",
    })

    run = _find(result, ".run()", "client_run")
    alpha_get = _find(result, ".get()", "alpha")
    beta_get = _find(result, ".get()", "beta")
    assert (run, alpha_get) in calls
    assert (run, beta_get) not in calls


def test_untyped_chain_link_stays_unlinked(tmp_path: Path):
    # A type-parameter return, a library return and an untyped `var` receiver
    # carry no type to follow.
    calls, result = _calls(tmp_path, {
        **_BUILDER,
        "Client.java": (
            "class Client<T> {\n"
            "    T self() { return null; }\n"
            "    String text() { return \"\"; }\n"
            "    void viaTypeParam() { self().build(); }\n"
            "    void viaLibrary() { text().length(); }\n"
            "    void viaVar() { var b = Factory.builder(); b.size(1).build(); }\n"
            "}\n"
        ),
    })

    for caller in ("viaTypeParam", "viaLibrary", "viaVar"):
        owners = _call_owners(calls, result, _find(result, f".{caller}()", caller.lower()))
        assert not any(label in (".build()", ".length()") for _, label in owners), (caller, owners)


def test_chain_through_an_unchanged_file_survives_a_changed_files_rebuild(tmp_path: Path):
    from graphify.watch import _rebuild_code

    files = {**_BUILDER, "Client.java": "class Client { void run() { Factory.builder().size(3).build(); } }\n"}
    roots = []
    for name in ("inc", "full"):
        root = tmp_path / name
        root.mkdir()
        for fname, body in files.items():
            (root / fname).write_text(body, encoding="utf-8")
        roots.append(root)
    inc, full = roots
    assert _rebuild_code(inc, no_cluster=True, acquire_lock=False, force=True)
    for root in roots:
        p = root / "Client.java"
        p.write_text(p.read_text(encoding="utf-8") + "// touched\n", encoding="utf-8")
    assert _rebuild_code(inc, changed_paths=[inc / "Client.java"], no_cluster=True, acquire_lock=False)
    assert _rebuild_code(full, no_cluster=True, acquire_lock=False, force=True)

    def calls_of(root):
        g = json.loads((root / "graphify-out" / "graph.json").read_text(encoding="utf-8"))
        return {(e["source"], e["target"]) for e in g.get("links", g.get("edges", [])) if e["relation"] == "calls"}

    assert calls_of(inc) == calls_of(full)
    assert any(s.endswith("client_run") and t.endswith("builder_build") for s, t in calls_of(full))


def test_schema_bump_retires_java_entries_cached_without_receiver_chains(tmp_path: Path, monkeypatch):
    """An entry from schema 7 has no `java_receiver_chain` / `_java_ret`; replaying
    it would leave `Factory.builder().size(3)` unlinked."""
    import graphify.cache as cache_mod
    from graphify.cache import save_cached
    from graphify.extract import extract_java

    files = {**_BUILDER, "Client.java": "class Client { void run() { Factory.builder().size(3); } }\n"}
    paths = []
    for name, body in files.items():
        (tmp_path / name).write_text(body, encoding="utf-8")
        paths.append(tmp_path / name)
    current_schema = cache_mod._AST_CACHE_SCHEMA
    monkeypatch.setattr(cache_mod, "_EXTRACTOR_VERSION", "same-version")
    monkeypatch.setattr(cache_mod, "_AST_CACHE_SCHEMA", 7)  # last schema without them
    monkeypatch.setattr(cache_mod, "_cleaned_ast_dirs", set())
    for p in paths:
        stale = extract_java(p)
        for raw_call in stale.get("raw_calls", []):
            raw_call.pop("java_receiver_chain", None)
        for node in stale["nodes"]:
            node.pop("_java_ret", None)
        save_cached(p, stale, root=tmp_path, cache_root=tmp_path, kind="ast")

    monkeypatch.setattr(cache_mod, "_AST_CACHE_SCHEMA", current_schema)
    monkeypatch.setattr(cache_mod, "_cleaned_ast_dirs", set())
    r = extract(paths, root=tmp_path, cache_root=tmp_path, parallel=False)
    calls = {(e["source"], e["target"]) for e in r["edges"] if e["relation"] == "calls"}
    assert ("Builder", ".size()") in _call_owners(calls, r, _find(r, ".run()", "client_run"))
