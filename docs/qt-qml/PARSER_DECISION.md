<a name="qml-00-parser-evidence"></a>

# INC-QML-00 parser evidence

Decision D2 is accepted for an **optional** `qml` extra using
`tree-sitter-language-pack==0.11.0`, with Tree-sitter `>=0.25.2,<0.26`.
This is a parser decision, not completed production QML support.

The inspected upstream baseline is `0b60d47e6cd9338c51143f39f35b6c45c8453385`.
Proposal [#1748](https://github.com/Graphify-Labs/graphify/pull/1748) remains open
at `7b38d4c2e2226b1db826a26774c7a5f299b8d62f` as inspected on 3 October 2026.
Its flat names, import-context loss, partial-parser handling and C++ integration
require replacement or supplementation. No files or fixtures from that proposal
are copied by this increment. The probe corpus is newly written synthetic input.

## Installed dependency and grammar

The installed wheel declares `MIT OR Apache-2.0` and includes its LICENSE with
the package authors' notices. Grammar attribution remains in the dependency;
Graphify's existing LICENSE, LICENSE-MIT and NOTICE remain intact. The
[versioned grammar manifest](https://github.com/xberg-io/tree-sitter-language-pack/blob/v0.11.0/sources/language_definitions.json)
pins qmljs revision `0bec4359a7eb2f6c9220cd57372d87d236f66d59`.
Installed Windows files total 165,756,708 bytes, a reason to keep this optional.
The standalone 0.3.1 source-only binding is rejected for this slice because it
uses an older Tree-sitter interface and would require platform build maintenance.

`get_parser`, `get_binding`, `Language` and `Parser` work with the locked
Tree-sitter 0.25.2. Both installed QML grammars report ABI 14; the runtime supports
13 through 15. No Qt SDK is needed. A fresh isolated interpreter blocks Python
socket, process and shell operations before importing the parser and successfully
parses the installed grammar. This proves the tested Python-level offline path;
it is not an operating-system sandbox or an offline dependency installation.

## Executed evidence

| Host | Python | Parser probes | Status |
| --- | --- | --- | --- |
| Windows x64 | 3.10.21 | 40 passed, zero skipped | Verified |
| Windows x64 | 3.12.14 | 40 passed, zero skipped | Verified |
| Windows x64 | 3.13.15 | 40 passed, zero skipped | Verified |
| Windows x64 | 3.14.7 | 40 passed, zero skipped | Verified |
| Linux / macOS | 3.10 / 3.12 / 3.13 / 3.14 | Not run locally | Unverified |

The 12 source fixtures cover Qt 6.5/6.8 syntax profiles: imports, versions,
qualifiers, property modifiers, aliases, typed functions/signals, inline
components, enums, pragmas, bindings, handlers, JavaScript, grouped properties,
Unicode, CRLF, incomplete/malformed/empty input, qmldir and qmltypes syntax.
Source byte/point ranges are checked against literal input. This matrix is
syntax coverage; no Qt runtime was executed. Targeted Ruff and Pyright report
zero errors. Existing language/registry/identity/validation tests report
569 passed and 55 optional-dependency skips.

Baseline findings remain separate: two Windows deleted-current-directory
fixtures fail before reaching production assertions; whole-repository Pyright
reports 634 existing errors and four warnings. They are not parser successes.

## Contracts accepted for production increments

Grouped properties parse as object definitions and require semantic separation.
An empty QML file has a grammar error: production must explicitly describe its
empty-editor-file policy. Malformed source must not become an authoritative
partial graph or successful cache entry. The qmldir grammar accepts invalid
versions and missing module URIs, so INC-QML-02 requires a dedicated semantic parser.

Use explicit scan roots, case-sensitive lookup keys and normalized IDs containing
an exact-identity digest. Scope keys must be portable. Persist independent import,
export and use-site nodes; avoid lists silently truncated by metadata sanitation.
Resolver indexes are per run and borrowed context is immutable. Multiple event
sites need distinct IDs because the existing graph is a DiGraph.

INC-QML-01 must reject failed QML extraction before publishing a graph or manifest,
including forced updates and equal-node-count losses. INC-QML-02/INC-QML-03 must widen a Qt
change to the whole accepted corpus or reject it safely until INC-QML-06 adds precise
invalidation. QML C++ bridges retain declaration identity and source-owned event
sites; runtime C++ implementation remains assigned to INC-QML-04.

## Increment review

INC-QML-00 is complete for optional parser selection, with Linux/macOS evidence
explicitly unverified. Add INC-QML-01a (write/cache safety) and INC-QML-01b (declarations,
admission and installation), following the existing letter-suffix convention.
Both are required before INC-QML-01 completion. INC-QML-02 must test semantic qmldir
validation, immutable indexes, metadata transport and changes to unchanged users.
No production requirement acceptance criterion is closed by this probe alone.
