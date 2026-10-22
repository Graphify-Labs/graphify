# Qt 6 and QML contribution

This contribution integrates bounded Qt 6/QML static analysis with Graphify's
Python pipeline on upstream 0.9.94. The reviewed upstream base is
`c588b72d936927790a87ad009955078ed40562a3`. The preceding fork delivery is
`f7430ac9c112bddfc5f5bdb25e9b2fcfb866825a`; its successful hosted checks describe
that older source/base combination, not this integration.

## Scope

QML declarations, lexical scopes, imports, bindings, handlers and JavaScript
produce source-owned facts. Literal CMake, qmake, QRC, `qmldir` and `.qmltypes`
metadata establish accepted module, component and resource context. Qt C++
declarations, properties, invokables, signals, slots, emissions, connections and
supported bidirectional QML/C++ access retain their distinct mechanisms and
uncertainty. Dynamic or unsupported inputs cannot become guessed providers.

Analysis does not execute corpus scripts, builds, `moc`, resource compilation or
QML components and does not require a Qt SDK. The optional QML extra pins
`tree-sitter-language-pack==0.11.0`. The existing Python packaging architecture,
upstream license and original attribution remain intact.

The current proposal includes the complete tested Qt/QML graph-consumer and
native-adoption integration, including community projection/navigation, Windows
recorded-interpreter transport, and the shared source/cache/publication/CI
prerequisites described in the code reference. This scope is broader than the
earlier focused proposal #4111, which excluded several fork consumer/installer
changes. Those differences are part of the review and are not presented as
unchanged upstream behavior. Maintainers can request separately reviewed slices;
no proposal is merged or retired automatically.

## Existing proposals

[PR #4111](https://github.com/Graphify-Labs/graphify/pull/4111) retains the earlier
Qt/QML contribution and its review history. Its source remains separate from the
new integration. [PR #1748](https://github.com/Graphify-Labs/graphify/pull/1748)
also proposes QML support; shared extractor, facade and packaging files overlap.
The alternative parser and resolution decisions remain documented in the audit
and architecture. This contribution does not claim the other proposal's tests
or silently replace its ownership and attribution.

## Review order

1. Read requirements, the supported-profile catalog and D36's integration
   decision. Distinguish implemented static support from runtime guarantees.
2. Review QML/C++ fact producers, source ranges and lexical identity before
   project/module and native endpoint resolution.
3. Review accepted-corpus ownership, cache invalidation and guarded publication.
   AST schema 23 retires both predecessor schemas; Qt policy 26 remains separate.
4. Review graph assembly, multirelation transport, source-backed community
   projection, exporters and query/assistant consumers.
5. Review native hook/installer boundaries, packaging, generated guidance and
   source/native workflow evidence.
6. Follow acceptance IDs to exact tests and recorded platform gaps in
   [traceability](../../tests/TRACEABILITY.md).

## Validation boundaries

Current evidence belongs to INC-QML-59. Exact commands and outcomes are recorded
in traceability and the pull request as they complete. A green earlier fork run,
local source run, isolated wheel smoke and upstream synthetic checkout are
different evidence boundaries. The normal upstream pull-request event owns new
hosted validation; no duplicate full workflow is dispatched before submission.
First-contributor execution approval may require an upstream maintainer.

Skips, inherited type diagnostics and advisory scanner outcomes remain explicit.
Neither successful parsing nor a green advisory security job establishes complete
Qt API coverage, runtime application correctness or security clearance. A failed
or unsupported extraction must preserve prior accepted products through the
existing integrity boundary.

## Repository identity

The public fork is
[graphify-with-qt-and-qml-support](https://github.com/SlinkyRamey/graphify-with-qt-and-qml-support).
Renaming preserves its GitHub repository identity and history. The feature
contribution branch is separate from the fork's original default branch;
renaming does not publish a new upstream release or imply upstream acceptance.
