"""Literal loader overloads must preserve source authority without Qt execution."""
from __future__ import annotations

import pytest

from graphify.extractors.qt_cpp_facts import qt_metadata
from tests.qt_analysis_helpers import analysis, sites


def corpus(tmp_path, body, declarations=""):
    """A public resource URL avoids assuming the analyzed app's working directory."""
    return analysis(tmp_path, {
        "access.cpp": declarations + "\nvoid use() { " + body + " }",
        "Main.qml": "import QtQml\nQtObject { property int value: 1 }",
        "ui.qrc": '<RCC><qresource prefix="/ui"><file>Main.qml</file></qresource></RCC>',
    })


@pytest.mark.parametrize("setup,root", [
    ('QQmlApplicationEngine engine(QUrl("qrc:/ui/Main.qml"));', 'engine.rootObjects().first()'),
    ('QQmlApplicationEngine engine(QUrl("qrc:/ui/Main.qml"), nullptr);', 'engine.rootObjects().first()'),
    ('QQmlApplicationEngine engine(nullptr); engine.load(QUrl("qrc:/ui/Main.qml"));', 'engine.rootObjects().first()'),
    ('QQmlEngine engine; QQmlComponent component(&engine, nullptr); component.loadUrl(QUrl("qrc:/ui/Main.qml"));', 'component.create()'),
    ('QQmlEngine engine; QQmlComponent component(&engine, QUrl("qrc:/ui/Main.qml"), QQmlComponent::Asynchronous);', 'component.create()'),
    ('QQmlEngine engine; QQmlComponent component(&engine); component.loadUrl(QUrl("qrc:/ui/Main.qml"), QQmlComponent::PreferSynchronous);', 'component.create()'),
    ('QQuickView view; view.setSource(QUrl("qrc:/ui/Main.qml"));', 'view.rootObject()'),
    ('QQmlApplicationEngine engine(":/ui/Main.qml");', 'engine.rootObjects().first()'),
])
def test_req_qml017_ac01_supported_loader_overloads_have_one_source(tmp_path, setup, root):
    """Parent-only construction supplies identity, never a false second load."""
    result = corpus(tmp_path, setup + ' auto root = ' + root + '; root->property("value");')
    loads = sites(result, "qml_load")
    assert len(loads) == 1 and qt_metadata(loads[0])["status"] == "resolved"
    member = sites(result, "qml_access", "property")[0]
    assert qt_metadata(member)["status"] == "resolved"
    assert any(edge["source"] == member["id"] and edge["target"] == qt_metadata(member)["target_id"]
               for edge in result["edges"])


@pytest.mark.parametrize("expression", [
    'QUrl::fromLocalFile("qrc:/ui/Main.qml")',
    'QUrl::fromLocalFile("file:///ui/Main.qml")',
    'QUrl::fromLocalFile("Main.qml")',
    'QUrl(QUrl::fromLocalFile("qrc:/ui/Main.qml"))',
    'QUrl(":/ui/Main.qml")',
    'QUrl(prefix + suffix)',
])
@pytest.mark.parametrize("route", ["engine_constructor", "component_url"])
def test_req_qml017_ac01_local_file_wrapper_cannot_become_resource_url(tmp_path, expression, route):
    """Wrapper semantics and dynamic/local-base uncertainty cannot lend qrc facts."""
    setup = (f'QQmlApplicationEngine engine({expression}); auto root = engine.rootObjects().first();'
             if route == "engine_constructor" else
             f'QQmlEngine engine; QQmlComponent component(&engine); component.loadUrl({expression}); auto root = component.create();')
    result = corpus(tmp_path, setup + ' root->property("value");')
    loads = sites(result, "qml_load")
    assert len(loads) == 1 and qt_metadata(loads[0])["status"] != "resolved"
    assert not qt_metadata(loads[0]).get("target_id")
    assert not qt_metadata(sites(result, "qml_access", "property")[0]).get("target_id")


def test_req_qml017_ac01_absolute_fromlocalfile_retains_file_component(tmp_path):
    """An absolute accepted path is converted to a file URI, with exact QML target."""
    path = str(tmp_path / "Main.qml").replace("\\", "/")
    result = corpus(tmp_path, f'QQmlApplicationEngine engine(QUrl::fromLocalFile("{path}")); '
                    'auto root = engine.rootObjects().first(); root->property("value");')
    assert qt_metadata(sites(result, "qml_load")[0])["literal_url"] == (tmp_path / "Main.qml").as_uri()
    assert qt_metadata(sites(result, "qml_access", "property")[0])["status"] == "resolved"


@pytest.mark.parametrize("declaration,local", [
    ('namespace App { class QUrl { public: QUrl(const char*); };', ''),
    ('namespace App { ::QUrl QUrl(const char*) { return ::QUrl("qrc:/ui/Other.qml"); }', ''),
    ('namespace App {', 'auto QUrl = [](const char*) { return ::QUrl("qrc:/ui/Other.qml"); };'),
])
def test_req_qml017_ac01_url_wrapper_shadow_cannot_lend_literal_argument(tmp_path, declaration, local):
    """A custom type/callable can construct a different value than its argument."""
    result = analysis(tmp_path, {
        "access.cpp": declaration + ' void use() { ' + local + ' QQmlApplicationEngine engine(QUrl("qrc:/ui/Main.qml")); '
                      'auto root = engine.rootObjects().first(); root->property("value"); } }',
        "Main.qml": "import QtQml\nQtObject { property int value: 1 }",
        "ui.qrc": '<RCC><qresource prefix="/ui"><file>Main.qml</file></qresource></RCC>',
    })
    assert not any(qt_metadata(node).get("target_id") for node in sites(result, "qml_load"))
    assert not qt_metadata(sites(result, "qml_access", "property")[0]).get("target_id")


def test_req_qml017_ac01_custom_component_engine_cannot_authorize_constructor(tmp_path):
    """A known local declaration named QQmlEngine does not prove SDK ownership."""
    result = corpus(tmp_path, 'QQmlEngine engine; QQmlComponent component(&engine, QUrl("qrc:/ui/Main.qml")); '
                    'auto root = component.create(); root->property("value");', 'class QQmlEngine {};')
    assert not any(qt_metadata(node).get("target_id") for node in sites(result, "qml_load"))
    assert not qt_metadata(sites(result, "qml_access", "property")[0]).get("target_id")


def test_req_qml017_ac01_global_sdk_constructor_bypasses_namespace_shadow(tmp_path):
    """An explicit global SDK type retains authority beneath an unrelated name."""
    result = analysis(tmp_path, {
        "access.cpp": 'namespace App { class QQmlApplicationEngine {}; void use() { '
                      '::QQmlApplicationEngine engine(::QUrl("qrc:/ui/Main.qml")); '
                      'auto root = engine.rootObjects().first(); root->property("value"); } }',
        "Main.qml": "import QtQml\nQtObject { property int value: 1 }",
        "ui.qrc": '<RCC><qresource prefix="/ui"><file>Main.qml</file></qresource></RCC>',
    })
    assert qt_metadata(sites(result, "qml_load")[0])["status"] == "resolved"
    assert qt_metadata(sites(result, "qml_access", "property")[0])["status"] == "resolved"


@pytest.mark.parametrize("declarations,kind", [
    ("namespace Other { class QQmlApplicationEngine {}; }", "Other::QQmlApplicationEngine"),
    ("class QQmlApplicationEngine {};", "QQmlApplicationEngine"),
    ("class Fake {}; using QQmlApplicationEngine = Fake;", "QQmlApplicationEngine"),
    ("namespace Other { class QQmlComponent {}; }", "Other::QQmlComponent"),
])
def test_req_qml017_ac01_sdk_name_shadow_cannot_authorize_loader(tmp_path, declarations, kind):
    """A qualified custom type or a local SDK-name declaration is not a Qt loader."""
    component = "Component" in kind
    setup = (f'QQmlEngine engine; {kind} component(&engine); component.loadUrl(QUrl("qrc:/ui/Main.qml")); auto root = component.create();'
             if component else
             f'{kind} engine(QUrl("qrc:/ui/Main.qml")); engine.load(QUrl("qrc:/ui/Main.qml")); auto root = engine.rootObjects().first();')
    result = corpus(tmp_path, setup + ' root->property("value");', declarations)
    assert not any(qt_metadata(node).get("target_id") for node in sites(result, "qml_load"))
    assert not qt_metadata(sites(result, "qml_access", "property")[0]).get("target_id")


@pytest.mark.parametrize("load,create", [
    ('component.loadUrl(QUrl("qrc:/ui/Main.qml"), computedMode)', 'component.create()'),
    ('component.loadUrl(QUrl("qrc:/ui/Main.qml"), QQmlComponent::Asynchronous, nullptr)', 'component.create()'),
    ('component.loadUrl(QUrl("qrc:/ui/Main.qml"))', 'component.create(otherContext)'),
    ('component.loadUrl(QUrl("qrc:/ui/Main.qml")); component.loadUrl(QUrl("qrc:/ui/Main.qml"))', 'component.create()'),
    ('if (enabled) component.loadUrl(QUrl("qrc:/ui/Main.qml"))', 'component.create()'),
    ('component.loadUrl(QUrl("qrc:/ui/Missing.qml"))', 'component.create()'),
])
def test_req_qml017_ac04_unknown_overload_or_creation_cannot_prove_root(tmp_path, load, create):
    """Mode, context, conditional, repeated and unavailable loads keep no root target."""
    result = corpus(tmp_path, 'QQmlEngine engine; QQmlComponent component(&engine); '
                    + load + '; auto root = ' + create + '; root->property("value");')
    access = sites(result, "qml_access", "property")[0]
    assert qt_metadata(access)["status"] != "resolved" and not qt_metadata(access).get("target_id")


@pytest.mark.parametrize("mode", ["Asynchronous", "PreferSynchronous"])
@pytest.mark.parametrize("parent", ["", ", nullptr"])
def test_req_qml017_ac01_constructor_mode_needs_sdk_type_authority(tmp_path, mode, parent):
    """A global SDK receiver cannot lend authority to a shadowed enum owner."""
    result = corpus(tmp_path, 'QQmlEngine engine; using QQmlComponent = Fake; '
                    f'::QQmlComponent component(&engine, QUrl("qrc:/ui/Main.qml"), QQmlComponent::{mode}{parent}); '
                    'auto root = component.create(); root->property("value");',
                    'struct Fake { enum CompilationMode { Asynchronous, PreferSynchronous }; };')
    assert qt_metadata(sites(result, "qml_load")[0])["loader_supported"] is False
    assert not qt_metadata(sites(result, "qml_access", "property")[0]).get("target_id")


@pytest.mark.parametrize("wrapper", ["QString", "QLatin1String", "QByteArray"])
@pytest.mark.parametrize("shadow", ["alias", "callable", "global_sdk"])
def test_req_qml017_ac01_string_wrapper_requires_source_authority(tmp_path, wrapper, shadow):
    """Written wrapper arguments cannot prove a value returned by custom code."""
    declaration = (f'using {wrapper} = Fake;' if shadow == "alias" else
                   f'::{wrapper} {wrapper}(const char*) {{ return ::{wrapper}("qrc:/ui/Other.qml"); }}'
                   if shadow == "callable" else f'class {wrapper} {{}};')
    spelling = "::" + wrapper if shadow == "global_sdk" else wrapper
    result = analysis(tmp_path, {
        "access.cpp": 'class Fake {}; namespace Public { ' + declaration + ' void use() { '
                      f'QQmlApplicationEngine engine({spelling}("qrc:/ui/Main.qml")); '
                      'auto root = engine.rootObjects().first(); root->property("value"); } }',
        "Main.qml": "import QtQml\nQtObject { property int value: 1 }",
        "Other.qml": "import QtQml\nQtObject { property int value: 2 }",
        "ui.qrc": '<RCC><qresource prefix="/ui"><file>Main.qml</file><file>Other.qml</file></qresource></RCC>',
    })
    load = qt_metadata(sites(result, "qml_load")[0])
    access = qt_metadata(sites(result, "qml_access", "property")[0])
    if shadow == "global_sdk":
        assert load["status"] == access["status"] == "resolved"
    else:
        assert not load.get("target_id") and not access.get("target_id")
