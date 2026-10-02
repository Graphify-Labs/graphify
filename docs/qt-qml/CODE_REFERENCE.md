# Qt/QML extension code reference

The files below exist in the audited baseline. Symbol names and ownership are
starting points for implementation; consult [AUDIT.md](AUDIT.md) for line evidence.

| Existing owner | Role and extension considerations |
| --- | --- |
| `graphify/detect.py` | `classify_file`, `detect`, `detect_incremental`, code extensions and corpus boundaries; add exact metadata names consistently |
| `graphify/extract.py` | Dispatch, language-family handling, `extract_cpp`, aggregate `extract`, ID/path normalization and resolution passes |
| `graphify/extractors/` | Focused language extractors; preferred home for source-local QML and Qt metadata responsibilities |
| `graphify/extractors/engine.py` | Shared AST traversal and generic C++ configuration; preserve normal C++ signatures, calls and macro normalization while a separate Qt overlay refers to these declaration IDs |
| `graphify/resolver_registry.py` | Post-extraction cross-file resolver activation; Qt context and exact metadata filenames must activate resolution after QML-only, C++-only or metadata-only changes |
| `graphify/cache.py` | Persistent per-file extraction cache and compatibility/invalidation rules |
| `graphify/watch.py` | Manual update/watch rebuild, watched-file admission, incremental extraction and persistence guards |
| `graphify/build.py` | Graph merge/provenance and simple graph construction; relation loss must be addressed before rich Qt projection |
| `graphify/__main__.py`, `graphify/cli.py` | CLI dispatch/facade and query/explain/path/affected implementation entry points |
| `graphify/serve.py` | Optional MCP query and graph consumer contracts |
| `graphify/export.py`, `graphify/exporters/` | Serialization and presentation consumers |
| `tools/skillgen/fragments/` | Authoritative assistant instruction source; generated outputs require skillgen checks |
| `pyproject.toml`, `uv.lock` | Python support, parser dependencies/extras, explicit packaged modules and frozen environment |
| `.github/workflows/ci.yml` | Upstream test/skillgen matrix; add Windows evidence without weakening existing gates |
| `tests/test_detect.py`, `tests/test_languages.py`, `tests/test_extract.py` | Detection, language and aggregate extraction regression coverage |
| `tests/test_build.py`, `tests/test_cache.py`, `tests/test_watch.py` | Graph integrity, cache and incremental persistence regression coverage |

Proposed modules such as `extractors/qml.py`, Qt metadata adapters, a Qt project
index, and a Qt/QML resolver do **not** exist yet. Choose final names at the relevant
increment, update the explicit packaging list if adding packages, and update this
table when ownership becomes real. Avoid listing planned APIs as public interfaces.

The proposed Qt C++ overlay owns source-local meta-object declarations, emissions,
connect/disconnect syntax, loader/access sites and literal context/initial-property
facts. The proposed resolver owns scoped module/resource joins and
engine/component/view-to-QML-object provenance. It must support native C++ events
without requiring QML parsing. QML-008, QML-016 and QML-017 in
[REQUIREMENTS.md](REQUIREMENTS.md) define the separate exposure, event and reverse
object-access acceptance contracts; none is implemented by the imported generic
C++ extractor alone. [DESIGN.md](DESIGN.md) records proposed relation contexts and
source ownership, including private-slot meta-object endpoints and compatible
ordinary member-pointer receivers.
