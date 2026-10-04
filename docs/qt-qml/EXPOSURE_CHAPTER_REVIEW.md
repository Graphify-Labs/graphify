# C++ attributes exposed to QML

This review maps the official [Qt 6 chapter](https://doc.qt.io/qt-6/qtqml-cppintegration-exposecppattributes.html)
and the [Qt 6.8 profile](https://doc.qt.io/qt-6.8/qtqml-cppintegration-exposecppattributes.html)
to Graphify's static analysis contracts. The chapter was explicitly reviewed on
4 October 2026. Qt API documentation describes runtime behavior; Graphify analyzes
accepted source evidence without creating objects or invoking an engine.

| Mechanism | Analysis contract and acceptance |
| --- | --- |
| Type visibility | Source registrations and accepted CMake/qmake module evidence select native providers; REQ-QML-008-AC01/AC03 and REQ-QML-009-AC01. |
| Properties and notification | `Q_PROPERTY` members retain accessor/NOTIFY evidence. INC-QML-27 maps `on<Property>Changed` to the actual accepted NOTIFY signal, whose name may differ; REQ-QML-008-AC02 and REQ-QML-007-AC03. |
| Callable attributes | Public slots and `Q_INVOKABLE` members retain their native identities; unsupported or ambiguous overloads remain unavailable; REQ-QML-008-AC02/AC03. |
| Signal subscriptions | Direct handlers and `Connections` preserve native signal direction. Explicit handler parameters own their lexical bindings; legacy block handlers have their distinct implicit parameter rule; REQ-QML-007-AC01/AC03. |
| Object and grouped attributes | Accepted declared member/provider identities govern source lookup. Runtime construction, ownership and arbitrary object selection are not inferred; REQ-QML-005-AC03/AC04 and REQ-QML-017-AC02. |
| Lists, gadgets and value behavior | `QQmlListProperty`, `Q_GADGET` value semantics, ownership transfer and coercion require separate semantic evidence. Generic C++ declarations alone do not establish those mechanisms. |
| Runtime method behavior | Dynamic overload selection, method rebinding and `NativeMethodBehavior` are outside the bounded source profile. |

The [API-family inventory](QT_API_COVERAGE.md) and [macro accountability table](QT_API_COVERAGE.md#named-macro-accountability)
are the completeness checklists. The [requirements](../REQUIREMENTS.md) define
observable behavior; [traceability](../../tests/TRACEABILITY.md) and
[validation](VALIDATION.md) distinguish executed acceptance from exclusions and
system gaps. Reviewing this chapter does not establish support for every Qt SDK
function or runtime behavior.

The concrete missing property-notification relationship is assigned to
[INC-QML-27](PLAN.md#inc-qml-27--native-property-notification-handlers).
Existing macro spelling checks remain independently applicable. No additional
runtime dependency, corpus execution or automatic exposure of unregistered classes
is introduced.
