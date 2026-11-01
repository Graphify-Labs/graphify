# Equivalent literal Qt 6 qmake module context.
TEMPLATE = lib
TARGET = tools
QT += qml quick
CONFIG += qmltypes
QML_IMPORT_NAME = Public.Tools
QML_IMPORT_VERSION = 1.0
HEADERS += backend.h
RESOURCES += resources.qrc
