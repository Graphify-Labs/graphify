"""Neutral Qt6.12 generator shapes; facts do not authorize native providers."""
from graphify.extractors.qml_facts import qml_metadata


COMPONENT = '''
    name: "Backend"; prototype: "QObject"; file: "backend.hpp"; lineNumber: 12
    resolvedFile: "../outside.hpp"; lineNumberInResolvedFile: 34
    parentProperty: "owner"; isSelfExtension: true; accessSemantics: "reference"
    Property {
        name: "count"; type: "int"; isTypeConstant: true; isPropertyConstant: true
        isReadonly: true; isVirtual: true; lineNumber: 15; read: "count"
    }
    Property { name: "enabled"; type: "bool"; isOverride: true; lineNumber: 17 }
    Signal { name: "changed"; lineNumber: 19; Parameter { name: "value"; type: "int"; isTypeConstant: true } }
    Method { name: "read"; type: "int"; isMethodConstant: true; lineNumber: 21 }
    Enum { name: "State"; type: "int"; lineNumber: 22; values: ["Ready", "Busy"] }
'''


def module(component=COMPONENT):
    return 'import QtQuick.tooling 1.2\nModule { Component { ' + component + ' } }'


def records(result, kind):
    return [qml_metadata(n) for n in result["nodes"] if qml_metadata(n).get("kind") == kind]


def fields(result):
    return {(m["field_name"], m["position"], m.get("enum_key", ""), m["value"])
            for m in records(result, "qmltypes_field")}
