# Qt/QML acceptance traceability

QML-00 evidence: `test_qml_parser_probe.py` has 40 passing probes without skips
on Windows x64 Python 3.10, 3.12, 3.13 and 3.14. See
[PARSER_DECISION.md](../docs/qt-qml/PARSER_DECISION.md). Production criteria below
remain open; baseline generic-language tests prove existing behavior only.

The requirement definitions are authoritative in
[REQUIREMENTS.md](../docs/REQUIREMENTS.md). The
[increment plan](../docs/qt-qml/PLAN.md) supplies acceptance scenarios and exit gates.
Test filenames below are proposed; revise them to the actual production boundaries
when implementing each increment, and replace gaps with exact test node IDs/results.

| Requirement | Planned evidence owner | Coverage status |
| --- | --- | --- |
| QML-001 | Parser compatibility/install matrix, `test_qml_parser_probe.py`, and `test_qml_extract.py` | Gap: backend not selected |
| QML-002 | `test_detect.py`, `test_qml_extract.py`, named metadata and update/watch cases | Gap: QML/metadata not admitted |
| QML-003 | `test_qml_extract.py` and hand-checked declaration fixtures | Gap: no QML extractor |
| QML-004 | `test_qml_resolution.py` module/alias/version and ambiguity fixtures | Gap: no QML resolver |
| QML-005 | `test_qml_resolution.py` component/id/inline/singleton visibility fixtures | Gap: no QML scope model |
| QML-006 | `test_qml_resolution.py` alias/binding direction and dynamic cases | Gap: no binding analysis |
| QML-007 | QML/JS/Connections fixtures and existing JS regression tests | Gap: QML/JS integration absent |
| QML-008 | `test_qt_cpp_bridge.py` and mixed QML/C++ registration fixtures | Gap: Qt exposure metadata absent |
| QML-009 | `test_qt_project_metadata.py` and accepted corpus-boundary metadata fixtures | Gap: Qt project adapters absent |
| QML-010 | Extract/build/export round-trip and same-endpoint relation cases | Gap: Qt relationship projection undecided |
| QML-011 | `test_cache.py`, `test_watch.py`, cold/warm/full/incremental equality | Gap: dependency-aware Qt invalidation absent |
| QML-012 | Malformed/missing-parser/failure fixtures and persistence-guard cases | Gap: Qt failure contract unimplemented |
| QML-013 | Query/path/explain/affected/export and optional MCP Qt smoke fixtures | Gap: no Qt graph to verify |
| QML-014 | Python/OS install CI, Unicode/path cases and mixed-language regressions | Partial baseline only; Qt matrix unverified |
| QML-015 | Support matrix review, skillgen checks and upstream PR check evidence | Planning only; language support unimplemented |
| QML-016 | `test_qt_signals_slots.py`, C++/graph/consumer/incremental regressions | Gap: Qt connection/emission semantics absent |
| QML-017 | `test_qml_cpp_access.py`, project metadata and bidirectional bridge regressions | Gap: C++ access to QML object APIs absent |

See [VALIDATION.md](../docs/qt-qml/VALIDATION.md) for the commands actually run.
Do not mark proposed fixtures as executed or reinterpret skipped optional-language
tests as coverage of unavailable capabilities.

## Individual acceptance assignments

Each ID below is defined in the requirements document and inherits the planned
verification owner in the table above. Every status is **Gap: implementation and
execution pending**. The planned completion increment owns the complete criterion,
not just its earliest source-fact implementation. Later changes reverify affected
criteria; cross-cutting safety is required immediately in every relevant PR.
Replace each gap with exact production test/check evidence
when its increment delivers that criterion; a requirement-level aggregate result
does not replace these individual assignments.

| Acceptance ID | Assigned verification case | Planned completion increment |
| --- | --- | --- |
| QML-001-AC01 | Built-wheel install, parser entry point, versions and license matrix | QML-01 |
| QML-001-AC02 | Offline/no-Qt supported-syntax corpus and repeatability | QML-03 |
| QML-001-AC03 | Missing/incompatible parser diagnostic and unsuccessful-cache behavior | QML-01 |
| QML-001-AC04 | Empty, malformed and unsupported input distinction | QML-01 |
| QML-002-AC01 | QML admission across scan, code-only, direct, update and watch | QML-06 |
| QML-002-AC02 | Exact metadata filename admission and unrelated-file rejection | QML-05 |
| QML-002-AC03 | Ignore, root, symlink and size-boundary rejection | QML-05 |
| QML-002-AC04 | Paths, spaces, Unicode and existing classification parity | QML-06 |
| QML-003-AC01 | Hand-checked declaration ownership, labels and spans | QML-01 |
| QML-003-AC02 | Duplicate scope/basename/member identity separation | QML-01 |
| QML-003-AC03 | Comment, string and grouped-property false-positive rejection | QML-01 |
| QML-003-AC04 | Cache/process/relocation identity and named-declaration line insertion | QML-01 |
| QML-004-AC01 | Directory/URI/alias/version import provider selection | QML-02 |
| QML-004-AC02 | Same-name exports with alias/version/qmldir visibility | QML-02 |
| QML-004-AC03 | Missing, incompatible and ambiguous provider rejection | QML-02 |
| QML-004-AC04 | Declared-root containment and remote-import nonfetch | QML-02 |
| QML-005-AC01 | Component/inline-component ID visibility | QML-02 |
| QML-005-AC02 | Shadowing, singleton and inherited-member boundaries | QML-02 |
| QML-005-AC03 | Internal, external and dynamic-member visibility rejection | QML-02 |
| QML-005-AC04 | Separate type/instance/member lookup identities | QML-02 |
| QML-006-AC01 | Binding/alias source targets, direction and evidence | QML-03 |
| QML-006-AC02 | Qualified alias scope and ambiguous/missing targets | QML-03 |
| QML-006-AC03 | Side-effect expression nonexecution | QML-03 |
| QML-006-AC04 | Same-endpoint binding facts survive build and serialization | QML-03 |
| QML-007-AC01 | Embedded JS/handler calls, source mapping and shadowing | QML-03 |
| QML-007-AC02 | Imported JS aliases/library directives and JS regression parity | QML-03 |
| QML-007-AC03 | Connections/handler signal targets, subscription identity and direction | QML-03 |
| QML-007-AC04 | Dynamic calls and shared-JS cross-language false-positive rejection | QML-03 |
| QML-008-AC01 | Valid declarative and literal procedural C++ registrations | QML-05 |
| QML-008-AC02 | Property/invokable/signal/notify provenance and declaration merging | QML-05 |
| QML-008-AC03 | Duplicate, macro-wrapper, overload and name-only bridge rejection | QML-05 |
| QML-008-AC04 | Comment/literal nonmatching, parser offsets and C++ regressions | QML-05 |
| QML-009-AC01 | Qt 6 CMake and qmake literal module/exposure mapping | QML-05 |
| QML-009-AC02 | qmldir/qmltypes exports, provenance and conflicts | QML-05 |
| QML-009-AC03 | Resource alias mapping, path containment and XML entity rejection | QML-05 |
| QML-009-AC04 | Unsupported build expressions and build/plugin/runtime nonexecution | QML-05 |
| QML-010-AC01 | Ordering/cache/process determinism and normalized-name collisions | QML-07 |
| QML-010-AC02 | Endpoint, source-span and canonical-path JSON remapping | QML-07 |
| QML-010-AC03 | Multiple promised facts survive simple-graph projection | QML-07 |
| QML-010-AC04 | Confidence/evidence distinctions and source-backed provenance priority | QML-07 |
| QML-011-AC01 | Cold/warm/manual/watch graph equality after QML edits | QML-06 |
| QML-011-AC02 | Provider-only changes re-resolve unchanged consumers and evict stale links | QML-06 |
| QML-011-AC03 | Parser/config/root/ignore compatibility invalidation | QML-06 |
| QML-011-AC04 | No-change idempotency and clean-build parity for all mutations | QML-06 |
| QML-012-AC01 | Bounded parser/extractor/resolver failure diagnostics | QML-06 |
| QML-012-AC02 | Existing valid graph/cache preservation on failed extraction | QML-06 |
| QML-012-AC03 | Intentional deletion versus failure and persistence guards | QML-06 |
| QML-012-AC04 | Hostile input resource bounds, redaction and nonexecution | QML-06 |
| QML-013-AC01 | Query/explain/path scopes, routes and source evidence | QML-07 |
| QML-013-AC02 | Affected traversal dependency direction and included consumers | QML-07 |
| QML-013-AC03 | Advertised export/reload preservation and explicit omissions | QML-07 |
| QML-013-AC04 | MCP/CLI parity and deliberate metadata search indexing | QML-07 |
| QML-014-AC01 | Every advertised host/Python lane install and extraction evidence | QML-07 |
| QML-014-AC02 | Windows/POSIX path/Unicode/relocation and optional-parser parity | QML-07 |
| QML-014-AC03 | Relevant existing-language and shared-boundary regression comparison | QML-07 |
| QML-014-AC04 | Honest skipped/unrun/baseline/type-check accounting | QML-07 |
| QML-015-AC01 | PR requirement/acceptance/support documentation consistency | QML-07 |
| QML-015-AC02 | Authoritative skillgen changes and artifact/schema checks | QML-07 |
| QML-015-AC03 | Reviewed base/head, dependency attribution and PR reuse evidence | QML-07 |
| QML-015-AC04 | Every release promise traced to evidence or explicit deferral; privacy scan | QML-07 |
| QML-016-AC01 | Signal/slot forms, signatures, spans and emission semantics | QML-04b |
| QML-016-AC02 | Typed/overloaded/lambda/legacy signal connections and scoped endpoints | QML-04b |
| QML-016-AC03 | Connection type/context/conditional evidence and dynamic uncertainty | QML-04b |
| QML-016-AC04 | Call/emission/connect/disconnect distinction, consumer and update preservation | QML-07 |
| QML-017-AC01 | Literal loader/module/resource-to-QML component provenance | QML-05 |
| QML-017-AC02 | QML root/objectName/member access from C++, distinct from QML id | QML-05 |
| QML-017-AC03 | Two-way signal bridge and literal context/initial-property exposure | QML-05 |
| QML-017-AC04 | Dynamic/duplicate lookup rejection and bidirectional incremental parity | QML-07 |
