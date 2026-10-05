"""Public Qt 6 adoption corpus: metadata, typed providers and inherited overload sites."""
from __future__ import annotations

from tests.qt_adoption_fixture import NATIVE, QML, sources


CMAKE = "qt_add_qml_module(app URI Public.Adoption VERSION 1.0 QML_FILES Main.qml SOURCES native.h access.cpp)\n"
QMAKE = """QT += qml quick
CONFIG += c++17
QML_IMPORT_NAME = Public.Adoption
QML_IMPORT_VERSION = 1.0
HEADERS += $$PWD/native.h
SOURCES += $$PWD/access.cpp
QML_FILES += $$PWD/Main.qml
QML_IMPORT_PATH += $$PWD/imports
QMLPATHS += $$PWD/imports
"""


def corpus(root, build_system):
    """Bodies throw if executed; source analysis consumes declared API types only."""
    app = root / "app"
    native = NATIVE.replace("class Backend : public QObject", "class\nBackend : public Middle")
    native = "class Grand : public QObject { Q_OBJECT signals: void changed(); };\n" + \
             "class Middle : public Grand { Q_OBJECT };\n" + native
    native = native.replace("public: Service *service()", "public: Backend(); Backend(int value); Service *service()")
    data = sources(app, native=native)
    data["access.cpp"] += "Backend::Backend() : Backend(0) { emit changed(); }\nBackend::Backend(int value) {}\n"
    data["CMakeLists.txt" if build_system == "cmake" else "application.pro"] = CMAKE if build_system == "cmake" else QMAKE
    # Explicit analysis configuration grants this module visibility. A qmake
    # tooling/build hint alone cannot enlarge the accepted corpus or lookup roots.
    data["imports/Public/Extra/qmldir"] = "module Public.Extra\nExtra 1.0 Extra.qml\n"
    data["imports/Public/Extra/Extra.qml"] = "import QtQml\nQtObject { property int value: 3 }\n"
    data["Consumer.qml"] = "import Public.Extra 1.0\nExtra {}\n"
    for name, source in data.items():
        path = app / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(source.encode("utf-8"))
    (root / "keep.py").write_text("def retained(): return 7\n", encoding="utf-8")
    return app
