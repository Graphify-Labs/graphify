"""Public hand-checked declared API types; no analyzed project code executes."""
from __future__ import annotations

NATIVE = '''class Service : public QObject { Q_OBJECT
 Q_PROPERTY(int count READ count)
public: int count() { return 1; }
 Q_INVOKABLE void refresh() {}
signals: void ready();
};
class Backend : public QObject { Q_OBJECT
 Q_PROPERTY(Service* service READ service)
public: Service *service() { throw 7; }
};
class Factory {
public: Backend *makeBackend() { throw 7; }
 Backend *backend;
};
'''

QML = '''import QtQml
QtObject {
 property int count: backend.service.count
 function handleReady() {}
 function run() {
  backend.service.refresh()
  backend.service.ready.connect(handleReady)
 }
 property Connections subscription: Connections {
  target: backend.service
  function onReady() { handleReady() }
 }
}
'''


def sources(root, expression="factory->makeBackend()", *, qml=QML, native=NATIVE):
    """Literal loading establishes component scope; factory bodies are irrelevant."""
    return {
        "native.h": native,
        "access.cpp": '#include "native.h"\nvoid use(Factory *factory, Backend *backend) {'
        ' QQmlApplicationEngine engine; engine.rootContext()->setContextProperty("backend", '
        + expression + '); engine.load(QUrl("' + (root / "Main.qml").as_uri() + '")); }\n',
        "Main.qml": qml,
    }
