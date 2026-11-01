"""INC-QML-68 peer regressions: source effects cannot imply unique runtime ordering."""
from __future__ import annotations

import pytest

from graphify.extractors.qt_cpp_facts import qt_metadata
from tests.qt_external_singleton_helpers import LOAD, SETUP, analyzed, binding_edges, setup_metadata, setup_sites


@pytest.mark.parametrize("expression", [
    "(void)typeid(CALL);", "bool checked = noexcept(CALL);", "sizeof(CALL);",
    "decltype(CALL) checked;",
])
def test_req_qml022_ac05_unevaluated_external_setup_never_authorizes_binding(tmp_path, expression):
    """Boolean-returning SDK calls in typeid/noexcept/sizeof/decltype do not execute."""
    statement = expression.replace("CALL", SETUP[:-1])
    result = analyzed(tmp_path, f"void boot() {{ Service singleton; QQmlApplicationEngine engine; {statement} {LOAD} }}")
    assert setup_metadata(result)["status"] == "unsupported"
    assert not binding_edges(result)


@pytest.mark.parametrize("effect", ["duplicate", "reset", "prior"])
def test_req_qml022_ac05_conditional_same_engine_effect_invalidates_direct_setup(tmp_path, effect):
    """Source declaration identity survives only for rejection across conditional uses."""
    action = {"duplicate": SETUP, "reset": "engine.clearSingletons();",
              "prior": 'engine.singletonInstance<Service*>("Public.Tools", "State");'}[effect]
    before = f"if(ready) {{ {action} }}" if effect == "prior" else ""
    after = f"if(ready) {{ {action} }}" if effect != "prior" else ""
    result = analyzed(tmp_path, f"void boot(bool ready) {{ Service singleton; QQmlApplicationEngine engine; {before} {SETUP} {after} {LOAD} }}")
    assert all(qt_metadata(site)["status"] != "resolved" for site in setup_sites(result))
    assert not binding_edges(result)


@pytest.mark.parametrize("argument,prefix", [("engine", ""), ("&engine", ""),
                                            ("alias", "auto &alias = engine;"),
                                            ("alias", "auto *alias = &engine;")])
def test_req_qml022_ac05_mutable_engine_helper_escape_keeps_order_unproven(tmp_path, argument, prefix):
    """An actual source declaration/alias passing into arbitrary code can alter singleton state."""
    pointer = argument.startswith("&") or "auto *" in prefix
    parameter, receiver = ("*current", "current->") if pointer else ("&current", "current.")
    result = analyzed(tmp_path, f"void reset(QQmlApplicationEngine {parameter}) {{ {receiver}clearSingletons(); }} void boot() {{ Service singleton; QQmlApplicationEngine engine; {prefix} {SETUP} reset({argument}); {LOAD} }}")
    assert setup_metadata(result)["status"] != "resolved"
    assert not binding_edges(result)


def test_req_qml022_ac05_captured_engine_callback_keeps_order_unproven(tmp_path):
    """A source closure may mutate its captured engine; it grants no ordering proof."""
    result = analyzed(tmp_path, f"void boot() {{ Service singleton; QQmlApplicationEngine engine; {SETUP} auto reset = [&engine]() {{ engine.clearSingletons(); }}; reset(); {LOAD} }}")
    assert setup_metadata(result)["status"] != "resolved"
    assert not binding_edges(result)


@pytest.mark.parametrize("action", ["alias.clearSingletons();", SETUP.replace("engine.", "alias."),
                                      'alias.singletonInstance<Service*>("Public.Tools", "State");'])
def test_req_qml022_ac05_runtime_engine_alias_cannot_hide_state_interference(tmp_path, action):
    """Source aliases are rejection evidence only, including conditional SDK effects."""
    before = f"if(ready) {{ {action} }}" if "singletonInstance" in action else ""
    after = f"if(ready) {{ {action} }}" if not before else ""
    result = analyzed(tmp_path, f"void boot(bool ready) {{ Service singleton; QQmlApplicationEngine engine; auto &alias = engine; {before} {SETUP} {after} {LOAD} }}")
    assert all(qt_metadata(site)["status"] != "resolved" for site in setup_sites(result))
    assert not binding_edges(result)


@pytest.mark.parametrize("effect", ["constructor", "store"])
def test_req_qml022_ac05_engine_constructor_or_nonlocal_storage_escape_is_unverified(tmp_path, effect):
    """A constructor or stored engine pointer can hide a later singleton mutation."""
    prefix = "struct Box { QQmlApplicationEngine *engine; };"
    action = "Box box; box.engine = &engine; reset(box);"
    if effect == "constructor":
        prefix = "struct Box { Box(QQmlApplicationEngine *engine) { engine->clearSingletons(); } };"
        action = "Box box(&engine);"
    result = analyzed(tmp_path, prefix + f"void boot() {{ Service singleton; QQmlApplicationEngine engine; {SETUP} {action} {LOAD} }}")
    assert setup_metadata(result)["status"] != "resolved"
    assert not binding_edges(result)


@pytest.mark.parametrize("effect", ["duplicate", "reset", "prior", "helper", "getter", "closure"])
def test_req_qml022_ac05_other_source_engine_and_value_uses_do_not_poison_binding(tmp_path, effect):
    """Conditional shadows and unrelated declarations stay distinct, without name matching."""
    actions = {"duplicate": SETUP, "reset": "engine.clearSingletons();",
               "prior": 'engine.singletonInstance<Service*>("Public.Tools", "State");',
               "helper": "reset(other);", "getter": "observe(engine.objectName());",
               "closure": "auto reset = [&other]() { other.clearSingletons(); };"}
    if effect in {"duplicate", "reset", "prior"}:
        action = f"if(ready) {{ QQmlApplicationEngine engine; {actions[effect]} }}"
    else:
        action = actions[effect]
    result = analyzed(tmp_path, f"void boot(bool ready) {{ Service singleton; QQmlApplicationEngine engine; QQmlApplicationEngine other; {SETUP} {action} {LOAD} }}")
    direct = [qt_metadata(site) for site in setup_sites(result) if not qt_metadata(site).get("conditional")][0]
    assert direct["status"] == "resolved"
    assert len(binding_edges(result)) == 3
