"""QML-017 provider scope, meta-object connections and QQmlProperty production cases."""
from graphify.extractors.qt_cpp_facts import qt_metadata
from tests.qt_analysis_helpers import analysis, sites

BACKEND = '''class Backend : public QObject {
 Q_OBJECT
 Q_PROPERTY(int count READ count)
public:
 int count() { return 1; }
 Q_INVOKABLE void refresh() {}
signals:
 void changed();
private slots:
 void close() {}
};
'''
QML = '''import QtQml
QtObject { property int count: 1; function refresh() {} signal closed() }
'''


def test_qml_signals_to_cpp_private_slots_and_cpp_signals_to_qml_functions(tmp_path):
    url = (tmp_path / "Main.qml").as_uri()
    source = BACKEND + f'''void use(Backend *backend) {{ QQuickView view; view.setSource(QUrl("{url}"));
 auto root = view.rootObject();
 QObject::connect(root, SIGNAL(closed()), backend, SLOT(close()));
 QObject::connect(backend, SIGNAL(changed()), root, SLOT(refresh()));
}}'''
    result = analysis(tmp_path, {"access.cpp": source, "Main.qml": QML})
    connections = sites(result, "connect")
    assert [qt_metadata(node)["status"] for node in connections] == ["resolved", "resolved"]
    assert [qt_metadata(node)["bridge_direction"] for node in connections] == ["qml_to_cpp", "cpp_to_qml"]
    assert not [edge for edge in result["edges"] if edge.get("context", "").startswith("qt_qml_connect") and edge["relation"] == "calls"]


def test_qqmlproperty_read_write_preserves_property_handle(tmp_path):
    url = (tmp_path / "Main.qml").as_uri()
    source = f'''void use() {{ QQuickView view; view.setSource(QUrl("{url}")); auto root = view.rootObject();
 QQmlProperty handle(root, "count"); handle.read(); handle.write(2); }}'''
    result = analysis(tmp_path, {"access.cpp": source, "Main.qml": QML})
    accesses = sites(result, "qml_access")
    assert len(accesses) == 3
    assert all(qt_metadata(node)["status"] == "resolved" for node in accesses), [qt_metadata(node) for node in accesses]
    assert len({qt_metadata(node)["target_id"] for node in accesses}) == 1
    static = source.replace('QQmlProperty handle(root, "count"); handle.read(); handle.write(2);', 'QQmlProperty::read(root, "count"); QQmlProperty::write(root, "count", 2);')
    result2 = analysis(tmp_path, {"access.cpp": static, "Main.qml": QML})
    assert all(qt_metadata(node)["status"] == "resolved" for node in sites(result2, "qml_access"))


def test_context_provider_is_limited_to_loaded_component(tmp_path):
    url = (tmp_path / "Main.qml").as_uri()
    source = BACKEND + f'''void use(Backend *backend) {{ QQmlApplicationEngine engine;
 engine.rootContext()->setContextProperty("backend", backend); engine.load(QUrl("{url}")); }}'''
    qml = 'import QtQml\nQtObject { property int value: backend.count; function run() { backend.refresh() } }'
    result = analysis(tmp_path, {"access.cpp": source, "Main.qml": qml, "Other.qml": qml})
    bindings = sites(result, "context_binding")
    assert len(bindings) == 1
    accesses = sites(result, "context_access")
    assert len(accesses) == 2
    assert {node["source_file"] for node in accesses} == {"Main.qml"}


def test_duplicate_context_provider_and_local_shadow_do_not_choose(tmp_path):
    url = (tmp_path / "Main.qml").as_uri()
    source = BACKEND + f'''void use(Backend *backend, Backend *other) {{ QQmlApplicationEngine engine;
 engine.rootContext()->setContextProperty("backend", backend);
 engine.rootContext()->setContextProperty("backend", other); engine.load(QUrl("{url}")); }}'''
    qml = 'import QtQml\nQtObject { property int value: backend.count }'
    result = analysis(tmp_path, {"access.cpp": source, "Main.qml": qml})
    assert not sites(result, "context_access")
    single_provider = source.replace('engine.rootContext()->setContextProperty("backend", other);', '')
    qml2 = 'import QtQml\nQtObject { property var backend; property int value: backend.count; function run(backend) { backend.refresh() } }'
    result2 = analysis(tmp_path, {"access.cpp": single_provider, "Main.qml": qml2})
    assert not sites(result2, "context_access")


def test_initial_property_provider_requires_declared_qml_property(tmp_path):
    url = (tmp_path / "Main.qml").as_uri()
    source = BACKEND + f'''void use(Backend *backend) {{ QQuickView view;
 view.setInitialProperties({{{{"backend", backend}}}}); view.setSource(QUrl("{url}")); }}'''
    qml = 'import QtQml\nQtObject { property var backend; property int value: backend.count }'
    result = analysis(tmp_path, {"access.cpp": source, "Main.qml": qml})
    assert len(sites(result, "context_binding")) == 1
    assert len(sites(result, "context_access")) == 1
    result2 = analysis(tmp_path, {"access.cpp": source, "Main.qml": qml.replace('property var backend;', '')})
    assert not sites(result2, "context_binding")


def test_component_create_and_initial_properties_bind_accepted_component(tmp_path):
    url = (tmp_path / "Main.qml").as_uri()
    source = BACKEND + f'''void use(Backend *backend) {{ QQmlEngine engine;
 QQmlComponent component(&engine, QUrl("{url}"));
 QObject *object = component.createWithInitialProperties({{{{"backend", backend}}}});
 object->setProperty("value", 2); }}'''
    qml = 'import QtQml\nQtObject { property var backend; property int value: backend.count }'
    result = analysis(tmp_path, {"access.cpp": source, "Main.qml": qml})
    assert qt_metadata(sites(result, "qml_load")[0])["status"] == "resolved"
    assert qt_metadata(sites(result, "qml_root")[0])["status"] == "resolved"
    assert qt_metadata(sites(result, "qml_access")[0])["status"] == "resolved"
    assert len(sites(result, "context_access")) == 1


def test_context_object_and_conditional_or_dynamic_providers(tmp_path):
    url = (tmp_path / "Main.qml").as_uri()
    source = BACKEND + f'''void use(Backend *backend, bool enabled) {{ QQmlApplicationEngine engine;
 engine.rootContext()->setContextObject(backend); engine.load(QUrl("{url}")); }}'''
    qml = 'import QtQml\nQtObject { property int value: count }'
    result = analysis(tmp_path, {"access.cpp": source, "Main.qml": qml})
    assert len(sites(result, "context_access")) == 1
    conditional = source.replace('engine.rootContext()->setContextObject(backend);', 'if (enabled) engine.rootContext()->setContextObject(backend);')
    result2 = analysis(tmp_path, {"access.cpp": conditional, "Main.qml": qml})
    assert not sites(result2, "context_binding")
    assert qt_metadata(sites(result2, "context_exposure")[0])["status"] == "dynamic"
    dynamic = BACKEND + f'''void use(QVariantMap properties) {{ QQuickView view;
 view.setInitialProperties(properties); view.setSource(QUrl("{url}")); }}'''
    result3 = analysis(tmp_path, {"access.cpp": dynamic, "Main.qml": qml})
    assert not sites(result3, "context_binding")
    assert qt_metadata(sites(result3, "initial_properties")[0])["reason"] == "computed_initial_properties"


def test_typed_qml_signal_and_untyped_function_use_explicit_meta_signatures(tmp_path):
    url = (tmp_path / "Main.qml").as_uri()
    source = BACKEND.replace('void changed();', 'void changed(QVariant value);').replace('void close() {}', 'void close(const QString &message) {}') + f'''void use(Backend *backend) {{ QQuickView view;
 view.setSource(QUrl("{url}")); auto root = view.rootObject();
 QObject::connect(root, SIGNAL(message(QString)), backend, SLOT(close(QString)));
 QObject::connect(backend, SIGNAL(changed(QVariant)), root, SLOT(receive(QVariant))); }}'''
    qml = 'import QtQml\nQtObject { signal message(msg: string); function receive(value) {} }'
    result = analysis(tmp_path, {"access.cpp": source, "Main.qml": qml})
    assert all(qt_metadata(node)["status"] == "resolved" for node in sites(result, "connect")), [qt_metadata(node) for node in sites(result, "connect")]
