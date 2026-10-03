#pragma once
#include <QObject>
#include <QtQml/qqmlregistration.h>

class Backend : public QObject {
    Q_OBJECT
    QML_NAMED_ELEMENT(Service)
    Q_PROPERTY(int status READ status NOTIFY statusChanged)
public:
    int status() const { return 1; }
    Q_INVOKABLE void refresh() { emit statusChanged(); }
signals:
    void statusChanged();
};
