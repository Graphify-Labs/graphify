# Executed increments

## QML-00

Complete for optional parser selection; see [parser evidence](PARSER_DECISION.md).
No production criterion closes from probes alone.

## QML-01

QML-01a implements publication guards and conservative refresh. QML-01b adds lazy
offline grammar loading, QML admission, declarations/imports, explicit roots,
scoped portable IDs, spans, safe failures and a pinned optional qml extra.
Bounded base64 companions preserve semantic values through HTML sanitation.
Empty editor files have file facts and an explicit informational diagnostic.
The subset includes objects, grouped properties, properties/modifiers, signals,
functions, inline components, enums, pragmas and imports. Module joins are QML-02;
bindings/calls/signals QML-03. C++/CMake/qmake/resources remain later increments.

Windows focused checks: 90 passed, zero skipped. Real spawn workers, portable
identity, build/JSON reload, forced/equal-count/edge-loss retention, read races
and successful retries are exercised. New modules pass Ruff/Pyright. Clean wheel
installation and remaining parser-failure cases are being verified.

| Criterion | Status | Evidence / remaining gate |
| --- | --- | --- |
| QML-001-AC01 | In progress | Clean wheel installations pending |
| QML-001-AC02 | In progress | Offline probes pass; production syntax closes QML-03 |
| QML-001-AC03 | Verified | Actual optional import rejection, incompatible binding/native parse failures, safe cache bypass |
| QML-001-AC04 | Verified | Empty, malformed and grammar-recognized unsupported fixtures have distinct diagnostics |
| QML-003-AC01 | Verified | Exact declarations/ownership/types in test_qml_declarations.py |
| QML-003-AC02 | Verified | Duplicate scopes/paths/stems/case in identity and graph tests |
| QML-003-AC03 | Verified | Comment/string/grouped-property negatives |
| QML-003-AC04 | Verified | Relocation, inserted comments, reordered/warm batches and actual spawn |

QML-003 is Verified for this subset. QML-001/002/010/011/012/013/014/015 are Partially
implemented, with later metadata/update/platform/consumer gates still open.
Other requirements remain Planned.

## Increment review and module debt

QML-00 added QML-01a/01b. QML-01 review requires semantic qmldir validation,
immutable indexes, provider-only refresh and independent reference/event sites
in QML-02/03. No new top-level increment is needed. Cache optimization is QML-06.

Root owns narrow integration hooks in oversized legacy extract.py, detect.py,
build.py, cli.py and watch.py. New responsibilities remain in modules below 300
lines. Exception: integration hooks only in these existing files. Exit: upstream
coordinated facade/writer splitting, outside this increment. Final validation
records measured sizes/deltas before handoff.
