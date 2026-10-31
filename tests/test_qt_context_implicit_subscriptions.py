"""REQ-QML-018-AC04: native legacy parameters precede nested subscription lookup."""
from __future__ import annotations

import pytest

from graphify.extractors.qml_facts import qml_metadata
from graphify.extractors.qt_cpp_facts import qt_metadata
from tests.qt_adoption_fixture import NATIVE, sources
from tests.qt_analysis_helpers import analysis, sites


@pytest.mark.parametrize("parameter", ["backend", "handleReady"])
@pytest.mark.parametrize("style", ["legacy", "function", "arrow"])
def test_req_qml018_ac04_native_parameters_own_nested_provider_and_callback_lookup(tmp_path, parameter, style):
    """Legacy native binders shadow providers/callbacks; explicit handlers retain their own formals."""
    body = "{ backend.service.ready.connect(handleReady) }"
    handler = {"legacy": "onReady: " + body, "function": "function onReady(other) " + body,
               "arrow": "onReady: (other) => " + body}[style]
    qml = "import QtQml\nQtObject { function handleReady() {} property Connections sub: Connections { target: backend.service; " + handler + " } }"
    native = NATIVE.replace("void ready();", "void ready(int " + parameter + ");")
    result = analysis(tmp_path, sources(tmp_path, qml=qml, native=native))
    assert len(sites(result, "context_subscription")) == (1 if style == "legacy" else 2)
    assert len(sites(result, "context_handler_endpoint")) == (1 if style == "legacy" else 2)
    if style == "legacy":
        assert {qt_metadata(node)["subscription_form"] for node in sites(result, "context_subscription")} == {"Connections"}


def test_req_qml018_ac04_nearer_local_callback_keeps_explicit_authority(tmp_path):
    """A local JS function inside a legacy handler precedes its same-name native parameter."""
    qml = "import QtQml\nQtObject { property Connections sub: Connections { target: backend.service; onReady: { function handleReady() {} backend.service.ready.connect(handleReady) } } }"
    native = NATIVE.replace("void ready();", "void ready(int handleReady);")
    result = analysis(tmp_path, sources(tmp_path, qml=qml, native=native))
    assert len(sites(result, "context_subscription")) == 2
    nested = next(node for node in sites(result, "context_subscription") if qt_metadata(node)["subscription_form"] == "signal.connect")
    by_id = {node["id"]: node for node in result["nodes"]}
    assert qml_metadata(by_id[qt_metadata(nested)["handler_target_id"]])["kind"] == "js_function"
