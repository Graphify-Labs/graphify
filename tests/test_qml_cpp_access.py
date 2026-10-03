"""QML-017 literal loaders, scoped handles and objectName rejection boundaries."""
from graphify.extractors.qt_cpp_facts import qt_metadata
from tests.qt_analysis_helpers import analysis, sites

QML = '''import QtQml
QtObject {
 id: root
 property string title: "hello"
 function refresh() {}
 signal closed()
 property QtObject child: QtObject { id: childId; objectName: "details"; property int count: 1 }
}
'''


def test_view_root_and_literal_object_name_property_access(tmp_path):
    url = (tmp_path / "Main.qml").as_uri()
    source = f'''void use() {{
 QQuickView view;
 view.setSource(QUrl("{url}"));
 auto root = view.rootObject();
 root->property("title");
 auto child = root->findChild<QObject*>("details");
 child->setProperty("count", 2);
 QMetaObject::invokeMethod(root, "refresh");
}}'''
    result = analysis(tmp_path, {"access.cpp": source, "Main.qml": QML})
    assert qt_metadata(sites(result, "qml_load")[0])["status"] == "resolved"
    assert qt_metadata(sites(result, "qml_root")[0])["status"] == "resolved"
    accesses = sites(result, "qml_access")
    assert len(accesses) == 4
    assert all(qt_metadata(node)["status"] == "resolved" for node in accesses), [qt_metadata(node) for node in accesses]


def test_qml_id_is_not_object_name_and_computed_lookup_not_guessed(tmp_path):
    url = (tmp_path / "Main.qml").as_uri()
    source = f'''void use(QString name) {{ QQuickView view; view.setSource(QUrl("{url}"));
 auto root = view.rootObject(); root->findChild<QObject*>("childId"); root->findChild<QObject*>(name); }}'''
    result = analysis(tmp_path, {"access.cpp": source, "Main.qml": QML})
    first, second = sites(result, "qml_access")
    assert qt_metadata(first)["reason"] == "object_name_unavailable"
    assert qt_metadata(second)["status"] == "dynamic"


def test_relative_runtime_url_and_reassigned_handle_remain_unresolved(tmp_path):
    source = '''void use() { QQuickView view; view.setSource(QUrl("Main.qml"));
 auto root = view.rootObject(); root = other(); root->property("title"); }'''
    result = analysis(tmp_path, {"access.cpp": source, "Main.qml": QML})
    assert qt_metadata(sites(result, "qml_load")[0])["status"] != "resolved"
    assert qt_metadata(sites(result, "qml_access")[0])["status"] != "resolved"


def test_duplicate_object_names_do_not_select_first_child(tmp_path):
    url = (tmp_path / "Main.qml").as_uri()
    qml = QML.replace('property int count: 1 }', 'property int count: 1 }\n property QtObject other: QtObject { objectName: "details" }')
    source = f'''void use() {{ QQuickView view; view.setSource(QUrl("{url}")); auto root = view.rootObject(); root->findChild<QObject*>("details"); }}'''
    result = analysis(tmp_path, {"access.cpp": source, "Main.qml": qml})
    assert qt_metadata(sites(result, "qml_access")[0])["status"] == "ambiguous"


def test_engine_module_loader_root_selection_and_plain_component_create(tmp_path):
    source = '''void use() { QQmlApplicationEngine engine; engine.loadFromModule("App", "Main");
 auto root = engine.rootObjects().first(); root->property("title"); }'''
    result = analysis(tmp_path, {"access.cpp": source, "App/Main.qml": QML, "App/qmldir": "module App\nMain 1.0 Main.qml\n"})
    assert qt_metadata(sites(result, "qml_load")[0])["status"] == "resolved"
    assert qt_metadata(sites(result, "qml_root")[0])["status"] == "resolved"
    assert qt_metadata(sites(result, "qml_access")[0])["status"] == "resolved"
    opaque = analysis(tmp_path, {"access.cpp": source.replace('.first()', '.last()'), "App/Main.qml": QML, "App/qmldir": "module App\nMain 1.0 Main.qml\n"})
    assert qt_metadata(sites(opaque, "qml_root")[0])["status"] == "unsupported"
    url = (tmp_path / "Main.qml").as_uri()
    component = f'''void use() {{ QQmlEngine engine; QQmlComponent component(&engine, QUrl("{url}"));
 auto root = component.create(); root->property("title"); }}'''
    created = analysis(tmp_path, {"access.cpp": component, "Main.qml": QML})
    assert qt_metadata(sites(created, "qml_root")[0])["status"] == "resolved"
    assert qt_metadata(sites(created, "qml_access")[0])["status"] == "resolved"


def test_literal_names_are_unicode_and_comments_templates_are_not_evidence(tmp_path):
    url = (tmp_path / "Main.qml").as_uri()
    qml = QML.replace('"details"', '"détail"')
    source = f'''// view.setSource(QUrl("{url}"));
void use() {{ QQuickView view; view.setSource(QUrl("{url}")); auto root = view.rootObject();
 root->findChild<QObject*>("détail"); const char *text = R"(root->property("title"))"; }}'''
    result = analysis(tmp_path, {"access.cpp": source, "Main.qml": qml})
    assert len(sites(result, "qml_load")) == 1
    assert len(sites(result, "qml_access")) == 1
    assert qt_metadata(sites(result, "qml_access")[0])["status"] == "resolved"
