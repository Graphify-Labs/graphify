# Literal Qt 6 module fixture; analysis must never configure this project.
cmake_minimum_required(VERSION 3.21)
project(PublicTools LANGUAGES CXX)
find_package(Qt6 REQUIRED COMPONENTS Qml Quick)
qt_add_qml_module(tools
    URI Public.Tools
    VERSION 1.0
    RESOURCE_PREFIX /ui
    QML_FILES Main.qml
    SOURCES backend.h
    IMPORTS QtQuick/2.15
)
