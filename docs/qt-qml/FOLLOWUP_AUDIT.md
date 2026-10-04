# Qt/QML follow-up audit

Date: 4 October 2026. Inspected implementation:
`95adbdc165f44a96bf275a7870bb1da4d82a5bea`, on the existing feature branch.
This is a findings-only audit. Production behavior, schema, analysis policy and
installed artifacts are unchanged. Corrective increments are planned, not executed.
The [foundation audit](AUDIT.md) retains A01–A09; findings below continue that sequence.

## Graph navigation and independent evidence

`graphify update .` refreshed the repository graph without model/API extraction.
The navigation snapshot contains 20,421 nodes, 42,848 edges and 1,091 communities;
its HTML community projection contains 1,091 nodes and 2,819 edges. The report
records inspected commit `95adbdc1`. The graph JSON SHA-256 is
`5847eb480b00d170ea5ec14454be578711e266c3950dd29d3f8929635bd0d55d`.
Generated outputs remain ignored and later refreshes may change these counts.
Open `graphify-out/graph.html` and use community filters or scoped search to review
the codebase. Graph correctness is established separately from this visualization.

Scoped queries located native event, QML bridge, incremental and HTML owners.
`graphify explain QtEventIndex`, `graphify explain resolve_qt_qml` and
`graphify explain qt_analysis_state` supplied narrower navigation. Broad query
results were truncated; truncation does not establish absent code or relationships.
No wiki index was available. Embedded viewer JavaScript also needs emitted-script
checks because Python AST navigation does not describe its interaction behavior.

Independent synthetic fixtures exercise production extraction, graph assembly,
JSON publication and reload. They run offline without a Qt SDK or corpus execution.
The current source environment uses Python 3.12.14, tree-sitter 0.25.2 and
tree-sitter-language-pack 0.11.0. No private application source is retained here.

## Confirmed correctness findings

### A10 — P1: Reflective member lookup crosses QObject ownership

A QML root declares `rootOnly` and `rootAction`; a child named `left` declares
neither. C++ reads/writes `left->property("rootOnly")` / `setProperty`, and invokes
`rootAction` on `left`. The analyzer marks these accesses resolved to the root's
declarations and preserves their target edges after JSON reload.

`QtQmlAccessIndex.member` delegates to QML lexical member lookup, which can fall
back to the component root. C++ reflection must use the receiving object's member
and accepted type/inheritance evidence. QML lexical visibility does not prove a
QObject owns that property or method. Unknown dynamic properties remain uncertain;
they cannot authorize a definite link to another object's declaration.
The [Qt QObject property contract](https://doc.qt.io/qt-6.8/qobject.html#property)
defines property access on the receiving object.

Affected acceptance: REQ-QML-017-AC02/AC04. Owner: reverse-access resolver maintainer.
Correction: [INC-QML-17](PLAN.md#inc-qml-17--receiver-owned-reflection-and-child-lookup).

### A11 — P1: findChild searches outside its receiver and ignores depth

`left->findChild<QObject*>("right")` resolves a sibling of `left`.
`Qt::FindDirectChildrenOnly` can also resolve a grandchild. Persisted
`qt_cpp_qml_find_child` edges preserve both incorrect selections.
`QtQmlAccessIndex.find_child` searches the component-wide object-name index,
excluding only the receiving object. Its caller does not enforce the explicit
depth option. The [Qt findChild contract](https://doc.qt.io/qt-6.8/qobject.html#findChild)
restricts lookup to the receiver's children and the requested depth.

Source containment is not universal proof of runtime QObject parenting. The
correction must define accepted static parenting evidence and reject or retain
uncertainty for reparenting, unsupported options or insufficient tree evidence.
Affected acceptance and owner are the same as A10; INC-QML-17 covers both.

### A12 — P1: Distinct engine declarations share context exposure

An inner block constructs `engine` and supplies `backend` through its root context.
After that block, a different declaration named `engine` loads the QML component.
The analyzer joins the earlier provider to the later engine's component and
publishes a `qt_context_member` edge. A matching receiver spelling inside one
function is insufficient engine identity.

`qt_context_bindings.resolve_context_bindings` indexes loads by enclosing callable
and receiver text. Provider/load joins need declaration identity, lexical lifetime,
assignment and conditional evidence. The [Qt context contract](https://doc.qt.io/qt-6.8/qqmlcontext.html)
places contexts within their owning engine; a different engine's context is not
established by the same variable name.

Affected acceptance: REQ-QML-017-AC03/AC04. Owner: context-provider integration
maintainer. Correction: [INC-QML-18](PLAN.md#inc-qml-18--lexical-engine-and-provider-identity).

### A13 — P1: Local C++ type alias binds a global connection endpoint

Global `Sender` and `Other` declare `changed(int)`. A local
`using Sender = Other` shadows the global type before `Sender *sender` and
`QObject::connect(sender, &Sender::changed, receiver, &Receiver::accept)`.
The analyzer resolves and serializes the global `Sender::changed` endpoint.
Both `using` and `typedef` aliases also create wrong emission endpoints and export
the global class through `qmlRegisterType`, including a wrong QML handler
subscription. Direct unshadowed native/registration controls select their actual
classes correctly; block controls preserve the unshadowed outer calls.

Native collectors retain type spellings; `QtEventIndex.member` resolves those
spellings without the alias's lexical declaration authority. Unsupported aliases
must remain unresolved rather than selecting the wrong global type. The correction
must either prove the alias target and scope or conservatively reject the join.
Affected acceptance: REQ-QML-008-AC01/AC03 and REQ-QML-016-AC01–AC04.
Owners: native type/registration integration and endpoint maintainers.
Correction: [INC-QML-19](PLAN.md#inc-qml-19--native-endpoint-type-and-alias-scope).

## Existing gaps and verification limits

The [Qt API mechanism matrix](QT_API_COVERAGE.md) reviews the official combined
function/macro index as a family checklist. It distinguishes semantic support,
conservative exclusion, generic extraction and omitted/unverified mechanisms.
Complete Qt API coverage is not claimed. Literal engine URL construction and
component loadUrl are reproduced loader omissions, planned in INC-QML-20 under
REQ-QML-017-AC01/AC04; they retain unresolved targets rather than wrong-target links.

Multi-level inherited-signal lookup remains INC-QML-11. Typed factory/member
providers and child-service chains remain INC-QML-08; the factory control here
correctly remains unavailable. Exact generic constructor-overload identity remains
INC-QML-15. Same-namespace unqualified native types can remain unavailable while
fully qualified controls resolve; this conservative gap belongs to INC-QML-19.
None is closed by a readable graph, successful parsing or passing persistence checks.

The confirmed wrong edges survive reload. Cold/warm/manual/watch parity for the new
corrections, installed-wheel proof and consumer revalidation remain exit gates of
their owning increments. Existing lifecycle tests passing does not validate these
new semantic cases. Browser/device behavior remains a separate system gap under
the [navigation review procedure](VIEWER_SYSTEM_REVIEW.md).

## Reproduction and validation

The opt-in probes under `tests/audit/probe_*.py` preserve correct assertions against
the current defective implementation. Their filenames deliberately keep diagnostic
failures outside default pytest collection during this findings-only audit. They
are not passing regressions or release evidence. Move the cases into ordinary
automatically collected tests with each correction; do not xfail or weaken them.

```text
.venv/Scripts/python.exe -X utf8 -m pytest tests/audit/probe_qt_qml_object_boundaries.py tests/audit/probe_qt_native_type_shadowing.py tests/audit/probe_qt_loader_forms.py -q --tb=short
```

Exact case assignments and final outcomes are recorded in
[traceability](../../tests/TRACEABILITY.md#follow-up-audit-scope-corrections).
The final combined public probes produced **15 failed, 7 passed in 3.38 seconds**,
with the existing Hypothesis warning. Thirteen failing variants expose four wrong-
target root causes; two more expose loader omissions. Rejection assertions inspect
actual persisted edges; positive controls remain meaningful and pass. Native
and QML compatibility selection separately passed 60 existing tests in 4.85 seconds.
The targeted lifecycle command was executed in the repository environment:

```text
.venv/Scripts/python.exe -X utf8 -m pytest tests/test_qt_final_incremental_parity.py tests/test_qt_config_incremental.py tests/test_qt_analysis_state.py tests/test_qt_worker_cache_integrity.py tests/test_qt_graph_persistence.py tests/test_qt_project_membership_updates.py -q --tb=short
```

Result: **67 passed in 21.43 seconds**, one existing Hypothesis collection warning.
An earlier isolated setup under `.venv` produced discovery rejections because
corpus admission excludes that ancestor. Those setup failures are not analyzer
regressions and do not establish lifecycle acceptance.

## Contribution and collaboration compliance

| Concern | Finding and disposition |
| --- | --- |
| Canonical workspace and ownership | Compliant for this audit: existing feature branch, preserved unrelated work, disjoint probe owners and one documentation/Git integration owner. No checkout switch or remote mutation. |
| Graph-guided orientation | Compliant: refreshed graph, scoped navigation and independent correctness reproductions. No wiki was available. |
| Requirements and evidence | Partial before this audit: broader scope claims conflicted with the new cases. Existing criteria are now explicitly partial/failed for these cases; earlier bounded passes remain historical. |
| Application language and modularity | Extension remains Python; all 149 new handwritten Python files inspected before these probes were within 300 lines. New probes also require that ceiling. Existing documented oversized owners are not refactored in this audit. |
| Generated assistants | `python -m tools.skillgen --check`: 134 artifacts matched. Generator sources and generated outputs were unchanged. |
| Documentation and public data | Initial read-only review resolved 304 local links and 197 exact test references across 18 documents, with all 84 criteria assigned and no detected private-path/project/credential patterns. Final changed-document checks are recorded with this audit handoff. |
| Full repository validation | No applicable full-suite evidence for inspected `95adbdc` was available. CONTRIBUTING.md requires the complete suite for a code contribution. Earlier full-suite proof belongs to `235987b`; selected later suites do not replace it. Future correction delivery must execute current full-suite/lint/type gates. |
| Language integration convention | CONTRIBUTING.md requires new language fixtures and tests in `tests/test_languages.py`. Dedicated QML fixtures/tests exist, but that named file has no QML case. Add a production QML language-contract case before upstream delivery, without replacing dedicated coverage. |
| AI commit attribution | Seven later extension commits from `7b31d59` through `95adbdc` omit the required AI authorship metadata; earlier extension commits use truthful Codex attribution. Future commits must include it. Historical metadata remains a disclosed gap; this audit does not rewrite history. |
| Conventional commit subjects | Initial commits `6e454b7`, `47b422b`, `9fd9cd0` lack the required prefix. Future commits follow the convention; historical commits remain unchanged. |
| Native interaction procedure | Exact fixture/action/evidence/failure/cleanup/owner instructions were missing for REQ-QML-021. The linked procedure supplies the contract; actual execution remains unverified. |
| Inherited dependency-direction debt | Imported `graphify/extractors/markdown.py::_active_scan_root` imports `graphify.extract` and reads ambient `_XAML_ACTIVE_EXTRACT_ROOT`. This predates Qt work and conflicts with the general rule. The scoped exception and extraction exit are recorded in DESIGN.md; it is not permission for new ambient state. |
| PR and protected proof sequencing | No publication, merge or deployment occurred in this audit. Those obligations are inapplicable to this local findings handoff; no remote readiness is claimed. |

## Handoff and standard review

Prioritize false-positive removal in INC-QML-17/18/19 before broadening adoption.
Each increment must include production regressions, semantic diagnostics, unchanged
source-span/identity controls, stale-edge removal, failure retention, corrected
retry, consumer and installed-artifact evidence. Existing INC-QML-08/11/15 remain
open. Full-suite and language-convention gaps are upstream delivery gates rather
than invented product features.

AGENTS.md now emphasizes truthful AI attribution, receiver/declaration identity
counterexamples and promotion of opt-in audit probes into normal regression
collection. The audit strengthens evidence obligations without claiming a runtime
fix, new infrastructure or complete Qt/QML coverage.

Final local handoff checks: Ruff passes for all three audit probes (66, 139 and
221 physical lines); skillgen confirms 134 matching artifacts. Default discovery
collects none of the opt-in probes, as documented. A read-only document check
resolves 337 local links and 237 exact test references across 21 documents, with
all 84 acceptance IDs assigned. No reviewed private project, machine path or
credential patterns remain; existing public fork evidence links are retained.
Whitespace checks pass. The final graph refresh after probe additions contains
20,499 nodes, 43,081 edges and 1,045 communities; counts are navigation state,
not acceptance evidence. Missing unrelated optional grammars and the intentional
Luau partial fixture remain explicit baseline limitations. No model/API labeling
was invoked.
