"""Neutral source-only external-singleton fixtures; never execute Qt code."""
from graphify.extractors.qt_cpp_facts import qt_metadata
from tests.qt_analysis_helpers import analysis, sites

HEADER = '''class Service : public QObject {
 Q_OBJECT QML_NAMED_ELEMENT(State) QML_SINGLETON QML_UNCREATABLE("External instance")
public: Q_INVOKABLE int count() const;
};
class Other : public QObject { Q_OBJECT };
'''
SETUP = 'engine.setExternalSingletonInstance("Public.Tools", "State", &singleton);'
LOAD = 'engine.loadFromModule("Public.Tools", "Main");'


def sources(body=None, header=HEADER):
    return {"backend.hpp": header,
            "CMakeLists.txt": "qt_add_qml_module(app URI Public.Tools VERSION 1.0 QML_FILES Main.qml SOURCES backend.hpp)",
            "Main.qml": "import Public.Tools 1.0\nQtObject { property int count: State.count() }",
            "main.cpp": body or f"void boot() {{ Service singleton; QQmlApplicationEngine engine; {SETUP} {LOAD} }}"}


def analyzed(root, body=None, header=HEADER):
    return analysis(root, sources(body, header))


def setup_sites(result):
    return sites(result, "external_singleton_setup")


def binding_edges(result):
    return [edge for edge in result["edges"] if edge.get("context", "").startswith("qt_external_singleton_")]


def setup_metadata(result):
    found = setup_sites(result)
    assert len(found) == 1, found
    return qt_metadata(found[0])
