# RFC: Swift cross-file type resolution

**Date:** 2026-10-23
**Issues:** #4574, #4575 (related open PRs: #4600, #4599, #4639); a new issue is needed for the parts not covered there
**Branch:** v8 (baseline `c588b72d`, released as 0.9.94)
**Status:** Implemented in this PR (Phases 1-4, one AST cache schema bump 25 -> 26; Phase 5 ships as its own small PR). See Implementation notes at the end for the deviations from this text.

---

## Summary

In a Swift corpus, many type references never reach the declaration of the type they name.
The usual trigger is ordinary Swift: a type declared next to its own `extension` and also
extended in another file. Each referencing file then keeps its own sourceless stub
(`<file>_swift_<name>`), so `graphify affected` and `graphify explain` undercount the users of
structs and enums.

This spec traces the failure to five separate mechanisms and proposes five small fixes. Each
fix ships as its own PR, in the dependency order given under Proposed design.

The reproductions below use the installed `graphifyy` 0.9.94. Its `graphify/` package matches
v8 `c588b72d` file for file (`diff -rq` differs only in `extractors/MIGRATION.md`), so the
results hold for the current HEAD.

---

## Problem

### Observed on a real app

The real app is a SwiftUI/TCA macOS app with 567 Swift files, built with
`graphify extract . --code-only --no-label`.

- `graphify affected "Layout"` prints `No unique node match for Layout`. Two sourced
  `Layout` nodes exist: the declaration in `Models/Layout.swift` and an unmerged
  `extension Layout` in `Logic/Migrator.swift`.
- `graphify affected <declaration id>` lists only Layout's own `.encode()` callers. None of
  the 17 references from other files reach it. Each referencing file has its own stub, for
  example `..._reducer_editor_swift_layout`, with an empty `source_file`, and
  `Editor.State` (L114 `var layout: Layout`) references that stub.
- Every `import Foundation` / `import SwiftUI` prints
  `WARNING: node 'foundation' is minted by two different files`.

Across the corpus, 1,362 `references` edges from Swift files point at a sourceless stub whose
label matches a type the corpus declares. They fall into four groups:

| Bucket | Labels | Stub edges | Cause | Phase |
|---|---|---|---|---|
| One declaration + same-file extension + extension elsewhere | 8 (`Layout`, `Session`, `Client`, …) | 601 | §RC1 | 1 |
| Extension only, the type is declared outside the corpus (`View`, `DependencyValues`, …) | 6 | 408 | #4574 | 1 (fail-closed) |
| Several declarations of one name (nested `State`, `Action`, `CodingKeys`, `Delegate`, …) | 40 | 353 | §RC3 | 3 |
| Declaration lost to a tree-sitter-swift parse error | (`LargeFeature`, 119 of the 408 above) | — | out of scope | — |

`LargeFeature.swift` (7,222 lines) parses with a top-level `ERROR` node from L100 to
L900, and that node swallows `@Reducer struct LargeFeature`. This is a grammar
limitation, a separate problem that this spec does not address (see #3542 for that class of
bug).

### Minimal reproduction (3 files + 1 consumer)

```swift
// App/Models/Layout.swift
import Foundation

struct Layout: Equatable, Codable {
  var panes: [Pane]
  struct Pane: Equatable, Codable { var id: Int }
  func encodeAll() -> Data { Data() }
}

extension Layout {            // same-file extension: shares the declaration's id
  var isEmpty: Bool { panes.isEmpty }
}
```

```swift
// App/Logic/Migrator.swift
import Foundation

extension Layout {            // cross-file extension
  static func migrated() -> Layout { Layout(panes: []) }
}

enum Migrator {
  static func run(_ input: Layout) -> Layout { input }
}
```

```swift
// App/Reducer/Editor.swift
import Foundation

struct Editor {
  struct State: Equatable {
    var layout: Layout
    var focused: Layout.Pane?
  }
  func reset(_ state: inout State) {
    state.layout = Layout(panes: [])
  }
}
```

```swift
// App/Logic/Persistence.swift
import Foundation

final class LayoutStore {
  var cached: Layout?
  func save(_ layout: Layout) {}
  func load() -> Layout { Layout(panes: []) }
}
```

**Actual** (`graphify extract . --code-only --no-label`, 0.9.94):

```
Layout nodes:
  app_models_layout_layout        App/Models/Layout.swift     <- declaration
  app_logic_migrator_layout    App/Logic/Migrator.swift <- unmerged extension
  app_logic_persistence_swift_layout  ''                              <- stub
  app_reducer_editor_swift_layout ''                           <- stub
edges into Layout:
  .run()             references parameter_type -> app_logic_migrator_layout
  .run()             references return_type    -> app_logic_migrator_layout
  LayoutStore  references field          -> app_logic_persistence_swift_layout
  .save()            references parameter_type -> app_logic_persistence_swift_layout
  .load()            references return_type    -> app_logic_persistence_swift_layout
  State              references field          -> app_reducer_editor_swift_layout
  (no edge from .reset() or .load() for the Layout(...) constructor calls)
  (no edge from State to Pane; `focused: Layout.Pane?` is recorded as a Layout reference)
stderr:
  WARNING: node 'foundation' is minted by two different files ... (x2)
```

**Expected:**

```
Layout nodes: app_models_layout_layout only
  (migrated() attached to it as a method; Migrator.swift contains it)
edges into Layout: all six references above point at app_models_layout_layout
  .reset() calls -> Layout   (constructor; INFERRED, see Phase 4)
  State references field -> app_models_layout_pane   (the nested Pane, after Phase 2;
                            app_models_layout_layout_pane after Phase 3)
stderr: no 'foundation' collision warning
```

Two controls narrow the cause down:

- *Remove the same-file `extension Layout`* (keep the cross-file one): every reference
  resolves to the declaration. So the generic rewire works for Swift, and the merge fails only
  because of the shared id.
- *Remove `Migrator.swift`* (keep the same-file extension): every reference resolves.

---

## Root cause

The Swift extractor (`graphify/extractors/engine.py`, `_extract_generic` with `_SWIFT_CONFIG`,
`graphify/extract.py:1712`) parses each file with tree-sitter-swift on its own. Swift has no
per-type imports inside a module. Every cross-file type name therefore becomes a sourceless
stub, and the corpus-level passes are expected to repair it later. There is no Swift-specific
type-reference pass like the ones for Java, Go, PHP or C#
(`extract.py:10188-10233`, `extractors/csharp.py:439`). Swift relies only on two generic
passes that match by label: `_merge_swift_extensions` (`extract.py:4147`) and
`_rewire_unique_stub_nodes` (`extract.py:3925`, called at `extract.py:10260`).

### RC1: a declaration that has a same-file extension is never canonical

- Node ids are `_make_id(stem, name)` (`engine.py:6168`; Swift leaves `namespace_stack` empty),
  so `struct Layout` and `extension Layout` in **one** file mint the **same** id.
- When the declaration node has an `extension` child, its id is appended to `swift_extensions`
  (`engine.py:6287-6290`). That includes this shared id.
- `_merge_swift_extensions` skips every id in `extension_nids` when it collects canonical
  candidates (`extract.py:4180-4181`). The real declaration is therefore not a candidate.
  The extension in `Migrator.swift` finds zero candidates and is left alone
  (`extract.py:4201-4203`).
- `_rewire_unique_stub_nodes` then sees two sourced, type-like `Layout` nodes
  (`extract.py:3936-3941`), treats the label as ambiguous and keeps every stub
  (`extract.py:3993-4009`). The fail-closed guard is correct here, but its input is wrong.
- `_disambiguate_colliding_node_ids` (`extractors/resolution.py:1060`, called at
  `extract.py:10185`) salts the bare `layout` stubs apart by referencing file. That
  produces the `<file>_swift_layout` ids seen above. The ids are a symptom, not a cause.

The #4574 author describes the same mechanism (the "Money" case) in a comment on that issue.

### RC2: an extension of an outside type acts as a declaration (#4574)

An extension of a type declared nowhere in the corpus (`extension View`,
`private extension String`) survives the merge with a `source_file` and the label of the
extended type. If one such node exists, it becomes the unique "real" definition for the rewire
(`extract.py:3936-3941`). If several files extend the same type, the label becomes ambiguous
(408 edges on the app above). Either way the result is wrong.

### RC3: Swift type names are reduced to their first segment

- `_swift_collect_type_refs` keeps only the first `type_identifier` of a `user_type`
  (`engine.py:1478-1484`). tree-sitter-swift parses `Layout.Pane` as `user_type` with
  children `type_identifier(Layout) type_identifier(Pane)`, so the reference becomes
  `Layout`. `_swift_user_type_name` behaves the same way for inheritance clauses
  (`engine.py:1424-1432`).
- The same head-only name goes into `swift_type_table` (`engine.py:7332-7333`, `7371`), so
  `focused` is typed as `Layout` and a later `focused.id` would be resolved against the
  wrong type.
- Nested types get no qualified identity. Their id omits the enclosing type (#4575), and their
  label is the bare name, so `real_by_label["State"]` holds 23 candidates on the app.
  `extension Editor.State` is labelled `Editor.State`. That dotted label is never
  type-like (`resolution.py:1209-1212`) and never matches the bare-labelled declaration in
  `_merge_swift_extensions`, so extensions of nested types never merge.

### RC4: cross-file constructor calls are dropped

`Layout(panes: [])` is recorded as a raw call with `via_stub: True` whenever the same file
also names `Layout` in a type position (`engine.py:9614-9618`, #3888). The shared call pass
accepts such a call only with import evidence or a C# namespace hit (`extract.py:10798`). A
Swift file never imports a type from its own module, so the call is always dropped. Even
without `via_stub`, the `(caller, target)` pair dedup at `extract.py:10800` suppresses the call
when a `references` edge for the same pair already exists, as in `.load()`. That dedup is
intended and is not changed here.

### RC5: duplicate import-node warnings

`_import_swift` (`extract.py:1683`) returns `(id, label)` pairs. The extractor turns each pair
into a `type=module` anchor whose `source_file` is the **importing** file
(`engine.py:6103-6115`). `_disambiguate_colliding_node_ids` exempts `type=module`
(`resolution.py:1076`), but `deduplicate_entities` → `_report_id_collision`
(`dedup.py:1041-1042`, `dedup.py:612-650`) does not. The id `foundation` carries no path
prefix, so `_defines_id` (`dedup.py:319`) is false for every copy, and the warning fires once
per extra importing file. No data is lost, since these are the same module. The warning is
noise, but it trains users to ignore a real data-loss warning.

### How other languages avoid this

- **Go** has package-wide visibility like Swift and folds per-file copies of one type by
  package directory (`_merge_go_package_types`, `resolution.py:3361`). It resolves
  `pkg.Type` through import paths (`_resolve_go_type_references`, `resolution.py:3612`).
- **Java, C# and PHP** resolve type references with package, namespace or `using` evidence
  before the generic rewire runs (`extract.py:10204-10218`, `extract.py:10274-10285`).
- **Python** resolves imports and repoints type references in
  `_resolve_cross_file_imports` (`resolution.py:2913`).
- **Rust** marks the true declaration (`_rust_declaration_count`) so the rewire can tell a
  declaration from an `impl` block (`extract.py:3979-3992`). This is the closest precedent
  for Phase 1.

Swift has none of these. It needs the Rust-style "which node is the declaration" marker. For
nested types it needs the Go/Java-style "resolve with scope evidence before the bare-label
rewire" pass.

---

## Relationship to open PRs

| | RC1 (repro above) | RC1 control: same-file extension only | RC2 `extension String` | Nested `Outer.Inner` from another file |
|---|---|---|---|---|
| v8 `c588b72d` | stubs (fail) | resolves | absorbs refs (fail) | refs `Outer` (fail) |
| v8 + #4600 | stubs (fail) | **stubs (regression)** | fixed | — |
| v8 + #4599 | — | — | — | refs `Outer` (fail); in-file bare `Inner` still resolves |

The author checked these by applying each PR's diff to a scratch worktree of `c588b72d`. The
review of this spec could not read the upstream PRs, so the rows for #4600 and #4599 are not
re-checked.

**#4600 regresses the common case.** It sets `metadata.swift_extension = True` on
`class_nid` whenever a declaration has an `extension` child. In the same-file case that id is
the real declaration, so the rewire skips the only definition. The 5 references in the
control fixture move from `app_models_layout_layout` back onto stubs. In the
`struct X` + `extension X` in `X.swift` layout this affects every such type, even when no
other file extends it. Phase 1 below is the variant that the #4574 author proposed in the
issue thread: mark only **extension-only** ids. Phase 1 is its own implementation and is not
based on #4600, since #4600 does not fix the `Layout` case and regresses the common case.

**#4599** gives nested types a parent-qualified id. Phase 3 is implemented here on its own,
with the same kind of id, and does not wait for #4599 (D8). #4599 alone does not resolve
`Outer.Inner` written in another file (RC3).

**#4639** (file-scope `typealias` nodes) is complementary. Phase 2 resolves references to those
alias nodes the same way as references to any other declaration.

---

## Proposed design

Five phases, one PR each. All of them are deterministic, fail closed on ambiguity, and never
bind across language families (the existing `_lang_family` guards stay).

The phases depend on each other, so they land in this order:

- Phase 1 -> Phase 2 -> Phase 3 -> Phase 4. Phase 2 indexes only the declarations that Phase 1
  marks. Phase 3 needs Phase 2's lexical lookup for bare in-body references: once nested ids
  carry the parent, `ensure_named_node` (`engine.py:6015-6022`) no longer finds `State` in the
  file and mints a stub. Phase 4 uses Phase 2's index.
- Phase 5 is independent and can land at any time.
- Upstream, Phase 3 ships in the same PR as Phase 4 (or after it). With parent-based ids,
  `struct Outer { struct Inner {}; func use(_ x: Inner) {}; func run() { Inner() } }` mints a
  sourceless `Inner` stub for the parameter (`engine.py:6016-6022`); the same-file label map
  then sends `Inner()` to raw calls with `via_stub` (`engine.py:9567`, `engine.py:9617-9618`),
  which only Phase 4 binds (`extract.py:10798`). This PR lands Phases 1-4 together.
- Each PR is correct on its own once the PRs before it have landed. Phase 2 without Phase 3
  fails closed on folded same-file nested types (see Phase 2, rule 5).

### Fixed contracts (decisions D1-D22, D24, D25)

Parallel implementers build against these names. A phase may not rename them.

| Kind | Name | Phase | Meaning |
|---|---|---|---|
| node key | `_swift_extension_only: True` | 1 | sourced Swift class node made only of `extension` blocks in its file |
| per-file record | `swift_extensions[]` = `{"nid", "label", "declared": bool}` | 1 | `declared` = the id is also in `swift_declared_nids` |
| node key | `_swift_qualified: list[str]` | 2 | qualified paths of the declaration(s) on this node, e.g. `["Editor.State"]`; an extension node holds the path it extends |
| edge attr | `_swift_scope: str` | 2 | on Swift `references`, `inherits` and `implements` edges: qualified path of the enclosing type or extended type; omitted at file scope (D14) |
| edge attr | `_swift_lookup: "ambiguous" \| "unresolved"` | 2 | the Swift pass declined this edge; the generic rewire must leave it on its stub |
| per-file record | `swift_type_table = {"path", "table", "scopes", "factory"?}` | 2 | `table[name]` is the written type path (`"Layout.Pane"`) for properties, parameters and locals alike; new `scopes[name]` is the innermost enclosing Swift type (D12) |
| function | `_swift_type_index(nodes: list[dict]) -> SwiftTypeIndex` | 2 | `extractors/resolution.py`; `SwiftTypeIndex` is a `NamedTuple(by_path: dict[str, list[str]], by_label: dict[str, list[str]])` |
| function | `_swift_lookup(index: SwiftTypeIndex, name: str, scope: str) -> tuple[str, str \| None]` | 2 | status `"resolved"` (with nid), `"ambiguous"`, `"unresolved"` or `"external"` (with `None`) |
| function | `_resolve_swift_type_references(per_file, paths, all_nodes, all_edges, root, resolution_context_nodes=None, resolution_context_edges=None) -> None` | 2 | `extractors/resolution.py`, same signature as `_resolve_go_type_references` (`resolution.py:3612-3620`) |
| function | `_merge_swift_extensions(per_file, all_nodes, all_edges, context_nodes=None, context_edges=None) -> None` | 1 | `extract.py:4147`; context arguments are read-only candidates |
| function | `_swift_caller_scope(caller_nid: str, method_owner: dict[str, str], node_by_id: dict[str, dict]) -> str \| None` | 4 | `extract.py`; a caller that is itself a Swift type uses its own path, else the `method`/`contains` owner's path; `""` for a file-scope function, `None` when the type has 0 or 2+ qualified paths (D20) |
| cache | `_AST_CACHE_SCHEMA` (`cache.py:40`) | 1, 2, 3 | one bump per PR that changes per-file output (D5) |

Decisions, each with its reason and the rejected alternative:

- **D1 Phase 2 index -> Phase 4 call pass.** The index is not handed from pass to pass. Each
  consumer (type pass, call pass, member-call resolver) calls `_swift_type_index` on the nodes
  it already has, and `_swift_lookup` with the caller's scope. *Reason:* the registry resolvers
  have the fixed signature `(per_file, all_nodes, all_edges)` (`extract.py:4562-4566`,
  `extract.py:7457`). An index rebuilt from node keys needs no signature change, no new
  raw-call field and no extra cache bump. *Rejected:* returning the table from
  `_resolve_swift_type_references` and threading it through `extract()` and `LanguageResolver`;
  stamping a scope on every raw call.
- **D2 Marker location.** `_swift_extension_only` and `_swift_qualified` are top-level node
  keys, added to the context-node marker tuples in `cli.py:4341-4347` and `watch.py:2035-2041`.
  They are not in `metadata`. *Reason:* those tuples copy top-level keys only (`if
  _node.get(_marker)`), and the merge and rewire read top-level markers the same way they read
  `_rust_declaration_count` (`extract.py:3990`). *Rejected:* `metadata.swift_extension_only`
  plus the separate metadata allowlist (`cli.py:4350-4373`, `watch.py:2044-2066`), which keeps
  two lists in sync.
- **D3 `swift_type_table` consumer.** `_resolve_swift_member_calls` resolves a table value with
  `_swift_lookup(index, table[prop], scopes.get(prop, ""))`. A value without a dot and with no
  index hit keeps today's `_key(label)` path. A dotted value with no `"resolved"` hit binds
  nothing. *Reason:* `_key` strips non-alphanumerics (`extract.py:4590-4591`), so `Outer.Inner`
  would match neither `Inner` nor anything but a type labelled `OuterInner`. The
  `{"path", "table"}` wrapper stays, like the existing `"factory"` sibling (`engine.py:10249`).
  *Rejected:* head-only values (today's wrong binding); last segment only (binds the wrong
  same-named nested type).
- **D4 Where declaration identity lives.** On the node (`_swift_qualified`), not in a per-file
  bucket. There is no `swift_type_decls` record. *Reason:* node ids are already rewritten by the
  prefix remap (`extract.py:9963-9972`), the symbol remap (`extract.py:10044-10049`),
  `_disambiguate_colliding_node_ids` (which takes no `per_file`, `resolution.py:1060-1063`, and
  runs after the merge) and the cache relativizer. A node key needs no new remap site and
  reaches incremental context through D2. *Rejected:* a per-file `swift_type_decls[].nid`
  bucket plus three new remap sites plus a separate context channel.
- **D5 Cache schema.** Every upstream PR that changes per-file extractor output bumps
  `_AST_CACHE_SCHEMA` once: Phase 1, Phase 2 and Phase 3 each take the next number when they
  land, with one clause in the comment. Phases 4 and 5 change corpus passes only and do not
  bump. This PR lands Phases 1-4 together and bumps once (25 -> 26). *Reason:* within one
  package version the counter is the only change to the cache key (`cache.py:39-40`), so a
  shared bump leaves stale per-file output between PRs. *Rejected:* one bump for Phase 1+2;
  bumps in Phase 4/5.
- **D6 Phase order.** Phase 1 -> 2 -> 3 -> 4, Phase 5 independent (see above). *Reason:* each
  PR stays correct alone. *Rejected:* Phase 2+3 as one PR (largest diff); Phase 3 before
  Phase 2 (bare in-body `State` regresses to an ambiguous stub).
- **D7 Swift pass outcome vs the generic rewire.** The Swift pass stamps `_swift_lookup` on
  each Swift reference edge it declines, and only when the bare label is declared somewhere in
  the Swift index (`by_label`). `_rewire_unique_stub_nodes` leaves a stamped edge on its stub,
  in the per-edge guard next to `_names_own_builtin_base` (`extract.py:4038-4050`). Other
  referrers of the same stub, such as a TypeScript file, still rewire. *Reason:* the rewire
  picks one target per stub (`extract.py:4010-4012`) by bare label. Without the stamp it
  binds a bare `Config` to the only `Outer.Config`, which Swift lookup rules out. Swift
  references to Objective-C or other non-Swift types are never stamped, so they keep today's
  rewire. *Rejected:* a per-stub "Swift-owned" flag (blocks non-Swift referrers of a shared
  stub); re-parking on an FQN-labelled stub as Java does for #2504 (changes stub ids again).
- **D8 Phase 3 and upstream #4599.** Phase 3 is implemented here on its own. It does not
  build on #4599 and does not wait for it. It uses `_make_id(parent_class_nid, name)`, the
  formula Python nested classes already use (`engine.py:6172-6173`), plus a collision pre-scan.
  If #4599 lands first with the same formula, Phase 3 shrinks to the pre-scan and the tests.
  *Reason:* #4599 is outside this repository and was not re-checked in review. The formula has
  a local precedent. *Rejected:* blocking Phase 3 on #4599; adopting its diff unseen.

Decisions D9-D22 close the remaining gaps between the phases:

- **D9** The presence of `_swift_qualified` on a node stands for "declared and contained";
  only the Swift class walk stamps it, and every class-walk node gets a `contains` edge
  (`engine.py:6278-6281`). `_swift_type_index(nodes)` takes no edges.
- **D10** Candidates are counted by distinct nid. A node whose `_swift_qualified` has 2+
  distinct paths gives `"ambiguous"` whenever a lookup hits it.
- **D11** `_swift_qualified` is deduplicated and keeps its order: a same-file `struct X` +
  `extension X` gives `["X"]`, not `["X", "X"]`.
- **D12** Every `swift_type_table["table"]` value is the written path (dotted when written
  dotted), whatever helper produced it: `_swift_collect_type_refs`, `_swift_constructor_type`,
  attribute type, navigation head, parameters (`engine.py:7898-7899`) or `_swift_local_var_types`
  (`engine.py:2984`). `scopes[name]` is the qualified path of the innermost enclosing Swift
  type (for a parameter or a function local: the enclosing type of the function); omitted at
  file scope.
- **D13** `_swift_classify_base` classifies a dotted base on its last segment.
- **D14** `_swift_scope` is also stamped on Swift `inherits` / `implements` edges
  (`engine.py:6333-6339`); the Phase 2 pass processes `references`, `inherits` and
  `implements`.
- **D15** Unit tests for `_swift_type_index` / `_swift_lookup` go to the new file
  `tests/test_swift_type_index.py`.
- **D16** `_swift_scope` and `_swift_lookup` are run-local: popped from every edge at the end
  of `extract()`, next to the existing `_rust_use_name` pop (`extract.py:10896`), after every
  resolver and the rewire.
- **D17** The Phase 2 pass considers only Swift edges (source node from a `.swift` file) of
  those relations whose target is a sourceless stub, and reads the written name from the stub
  `label`. Edges onto a sourced node are left alone.
- **D18** In `_merge_swift_extensions`, from Phase 2 on, **every** extension label, dotted or
  bare, resolves through `_swift_lookup(index, label, "")` (absolute path, no scope):
  `"resolved"` merges into that nid; `"ambiguous"` / `"unresolved"` do not merge (the
  extension node stays, with its marker); only `"external"` falls back to the existing
  family-gated bare-label path (Objective-C ↔ Swift). *Reason:* a bare `extension Config` of an
  outside type must not merge into a unique nested `Outer.Config`, whose label is also
  `Config` (`extract.py:4178-4211`). Phase 1 keeps the bare-label path; Phase 2 replaces it.
- **D19** In `_resolve_swift_member_calls`, only status `"external"` falls back to today's
  `_key(label)` path. `"resolved"` binds to that nid; `"ambiguous"` / `"unresolved"` bind
  nothing. Only `"unresolved"` is parked as today's unresolved member call (the name is not
  visible from the scope and may live in another repository). `"ambiguous"` is not parked:
  the local repository declares the name, as in today's "ambiguous -> bail"
  (`extract.py:4706-4711` at `c588b72d`), so the cross-repo pass
  (`cross_repo_calls.py`, `link_cross_repo_member_calls`) cannot bind it to a foreign type.
- **D20** `_swift_caller_scope`: a caller that is itself a Swift type node with exactly one
  `_swift_qualified` path uses that path (a property initializer is walked with the type as
  its caller, `engine.py:7341`); a caller found through `method` / `contains` uses its owner's
  single path; 2+ paths -> `None` (no binding); a file-scope function -> `""`.
- **D21** Resolved type edges keep `EXTRACTED` (Phase 2, rule 2).
- **D22** Each phase adds its own import line in `extract.py` next to the existing resolution
  imports; no placeholder stubs.
- **D24** Same-file constructor calls to nested types are deferred to Phase 4. In the Swift extractor's call walk (`engine.py:9543`, `engine.py:9567-9581`), a bare
  non-member call whose callee label names a nested Swift type (a type node with a parent
  type), or a label shared by 2+ Swift type nodes in the file, is not bound through the
  bare-label map `label_to_nid` (`engine.py:8458-8463`). The call goes to `raw_calls`, and the
  Phase 4 branch binds it through `_swift_lookup` + `_swift_caller_scope` (D20) as an INFERRED
  `calls` edge (`context="constructor"`, `confidence_score=0.85`). A label that names a single
  top-level Swift type keeps today's same-file EXTRACTED binding. Phase 3 and Phase 4 ship
  together upstream. *Reason:* after Phase 3 the bare-label map binds `State()` in both
  `A.runA()` and `B.runB()` to one `State`. *Rejected:* an owner-chain lookup of nested types
  in the extractor (a second copy of the lookup rule and a new map); accepting the wrong
  binding for v1.
- **D25** The per-file `swift_type_table` stays flat (fail-closed). When
  two writes for the same name in one file disagree on type or scope, the extractor stores
  `scopes[name] = None` (the `table` value stays); `_resolve_swift_member_calls` binds nothing
  for a name whose scope is `None` (no edge, and not parked, so the cross-repo pass cannot bind
  it to a foreign type, as for `"ambiguous"` in D19). The record
  format stays. *Reason:* the table keeps the last write (`engine.py:7892-7899`), so one shared
  scope would send `x.go()` in both `A.runA(_ x: State)` and `B.runB(_ x: State)` to
  `B.State.go()`. *Rejected:* keying the table by owner (changes the settled D3/D12 format);
  accepting the wrong binding for v1.

### Phase 1: mark real declarations (RC1, RC2)

Extractor (`engine.py`, class walk around `6257-6290`):

- Keep a per-file set `swift_declared_nids`. An id goes into it when the file has a
  `class_declaration` whose keyword (`_swift_declaration_keyword`) is
  `class/struct/enum/actor`, or a node with `t == "protocol_declaration"`.
- Emit `swift_extensions` records as `{"nid", "label", "declared": nid in swift_declared_nids}`.
- Stamp sourced Swift class nodes that are **extension-only** with the top-level key
  `_swift_extension_only = True` (D2). Stamp after the walk, because Swift allows the
  extension to come before the declaration.
- Bump `_AST_CACHE_SCHEMA` (D5).

Same-file references to an extension-only node: `ensure_named_node` returns the file's own id
when the name is in `seen_ids` (`engine.py:6015-6022`). So in a file with `extension Foo {}`
and `struct Holder { var v: Foo }`, the reference targets the file's extension node, not a stub. This is
today's behaviour and Phase 1 keeps it: the edge stays file-local. If the merge folds the
extension into a declaration, the edge follows it (`extract.py:4219-4240`). The node never
attracts references from other files (rewire rule below).

Corpus (`_merge_swift_extensions`, `extract.py:4147`):

- Candidates are nodes without `_swift_extension_only`, including declared ids that also
  appear in `swift_extensions`; the existing family, builtin, `contained` and type-like
  filters (`extract.py:4178-4196`) stay. Never remap a declared id.
- On an incremental build the call at `extract.py:10176` passes `resolution_context_nodes` and
  `resolution_context_edges` as `context_nodes` / `context_edges`. Unchanged declarations are
  read-only candidates. Their `contains` edges are in the context (`cli.py:4382-4384`), so the
  same `contained` test applies. An extension in a changed file then folds onto an unchanged
  declaration, as in a full build.
- Remap only extension-only ids. A survivor (no candidate, or several) keeps
  `_swift_extension_only`.
- The remap also rewrites `raw_calls[].caller_nid` in `per_file` (the same dicts as
  `all_raw_calls`, `extract.py:9656-9660`), as the prefix remap (`extract.py:9959-9962`) and
  the symbol remap (`extract.py:10040-10043`) do. A property initializer in an extension is
  walked with the extension node as its caller (`engine.py:7341`); without the rewrite its
  raw calls, including the ones deferred to Phase 4 (D24), keep a deleted caller id.

Rewire (`_rewire_unique_stub_nodes`, `extract.py:3936`):

- A node with `_swift_extension_only` is not added to `real_by_label`. References from other
  files stay on stubs, as for `Int` or `Bool`. This is fail-closed and matches #4574's
  expected behaviour.

Incremental builds: add `"_swift_extension_only"` to the marker tuples in `cli.py:4341-4347`
and `watch.py:2035-2041` (D2), so `graphify update` keeps it on unchanged context nodes. A
graph built before Phase 1 has no marker; its extension-only nodes act as declarations (today's
behaviour) until the next full `graphify extract`.

Expected effect on the app: the 601-edge bucket resolves. The extension-only nodes for `View`,
`DependencyValues` and similar stop attracting references.

### Phase 2: Swift module symbol table and type-reference pass (RC3, qualified names)

A new pass, `_resolve_swift_type_references(per_file, paths, all_nodes, all_edges, root,
resolution_context_nodes=None, resolution_context_edges=None)` in `extractors/resolution.py`,
modelled on `_resolve_go_type_references`. `extract()` calls it gated on `.swift`, right after
the Go pass (`extract.py:10221-10232`): after `_merge_swift_extensions` and
`_disambiguate_colliding_node_ids`, and **before** `_rewire_unique_stub_nodes`
(`extract.py:10260`).

Extractor outputs. They change per-file records, so `_AST_CACHE_SCHEMA` gets a bump (D5):

- Each Swift class node gets `_swift_qualified: list[str]`, built from a nesting stack during
  the walk (`["Editor.State"]`). An extension node records the path it extends
  (`extension Editor.State` -> `["Editor.State"]`). A second declaration whose id
  folds onto an existing node appends its path instead of being lost, so before Phase 3
  `struct A { struct State {} }; struct B { struct State {} }` in one file gives one node with
  `["A.State", "B.State"]`. Add `"_swift_qualified"` to the marker tuples (D2).
- `_swift_collect_type_refs` keeps its signature (`engine.py:1462`, appends `(name, role)` to
  `out`). For a `user_type` chain it appends **one** entry, the joined path with generic
  arguments stripped per segment (`Outer<Arg>.Inner<Other>` -> `"Outer.Inner"`), and the
  generic arguments as separate `generic_arg` entries, as today. The `Self` and in-scope
  generic-parameter exclusions apply to the head segment, so `T.Element` and `Self.Element`
  emit nothing. `_swift_user_type_name` (`engine.py:1424-1432`) returns the same joined path
  for inheritance clauses.
- The stub for `Layout.Pane` is labelled `Layout.Pane`, not `Layout`. Every Swift
  `references`, `inherits` and `implements` edge carries `_swift_scope`, the qualified path of
  the enclosing type or extended type (`"Editor.State"`), omitted at file scope (D14).
- `swift_type_table["table"][name]` holds the joined path for every producer: properties
  (`prop_type` at `engine.py:7333`), parameters (`engine.py:7898-7899`) and locals
  (`_swift_local_var_types`, `engine.py:2984`). A new `swift_type_table["scopes"][name]` holds
  the innermost enclosing Swift type; for a parameter or a local, the enclosing type of the
  function (D12). The table stays flat per file, and a later write with the same name wins
  (`engine.py:7892-7899`). When two writes for the same name in one file disagree on type or
  scope, the extractor stores `scopes[name] = None`; the `table` value stays (D25).

Symbol table (`_swift_type_index`, D1):

```
by_path:  qualified name ("Layout", "Layout.Pane", "Editor.State") -> [nid, ...]
by_label: last segment ("Pane", "State") -> [nid, ...]
```

It holds nodes whose `source_file` is `.swift`, that carry `_swift_qualified` (which stands
for declared and contained, D9) and are not `_swift_extension_only`, from
`all_nodes` plus the context nodes. In the first version the table covers the **whole corpus**:
the corpus is treated as one module. This is the same boundary the generic rewire uses today.
A unique declaration in another SwiftPM or Xcode target can therefore bind; per-target scoping
is open question Q1.

Resolution of a reference `A.B.C` written in scope `S1.S2` (`_swift_lookup`), applied the same
way to annotations, parameter and return types, inheritance/conformance clauses, generic
arguments and extension targets:

1. Lexical lookup, innermost first: try `S1.S2.A.B.C`, then `S1.A.B.C`, then `A.B.C`. This
   mirrors Swift name lookup, where a bare `State` inside `Editor` or inside
   `extension Editor` means `Editor.State`.
2. The first level that has exactly one candidate wins (`"resolved"`). The edge is repointed
   and keeps `EXTRACTED`, since the binding follows from the text and the language rules.
3. A level that has two or more candidates stops the search without binding (`"ambiguous"`).
4. No level matches, but the last segment is declared in the corpus (`by_label`):
   `"unresolved"`. A bare `Config` outside `Outer` never means `Outer.Config`.
5. A node with two or more `_swift_qualified` paths is a candidate for each path, and a lookup
   that lands on it is `"ambiguous"`. Phase 3 removes this case.
6. No level matches and the last segment is not declared in Swift: `"external"` (SwiftUI,
   Foundation, a package outside the corpus, or an Objective-C class). The edge is left
   untouched, and the generic rewire handles it as today.

The pass handles only Swift `references`, `inherits` and `implements` edges whose target is a
sourceless stub; the written name is the stub `label` (D14, D17). For `"ambiguous"` and
`"unresolved"` the edge stays on its stub and gets `_swift_lookup` set to the status.
`_rewire_unique_stub_nodes` leaves such an edge on its stub (D7).

Extension targets resolve with the same lookup at file scope (D18): every extension label,
dotted or bare, goes through `_swift_lookup(index, label, "")` in `_merge_swift_extensions`.
`extension Editor.State` merges into the nested declaration; a bare `extension Config` of
an outside type does not merge into a nested `Outer.Config` (`"unresolved"`). Only
`"external"` falls back to the existing family-gated bare-label match, which keeps Swift↔ObjC
folding.

Member calls (D3, D19): `_resolve_swift_member_calls` resolves `table[name]` through
`_swift_lookup` with `scopes[name]`. A name whose scope is `None` (D25) and an `"ambiguous"`
lookup (D19) bind nothing and are not parked, so `graphify merge-graphs` cannot bind them to a
same-named type in another repository; only `"unresolved"` and `"external"` park.

Edges that the pass repoints leave their stubs unreferenced. Those stubs are dropped in the
same way as in `_resolve_go_type_references` (`resolution.py:3705-3712`). Stubs that are still
referenced stay as they are today.

### Phase 3: nested type identity (D8; related: #4599)

- A nested Swift type gets the id `_make_id(parent_class_nid, name)`, the formula Python nested
  classes use (`engine.py:6172-6173`).
- Collision pre-scan: methods of a type use `_make_id(parent_class_nid, name)` too
  (`engine.py:7623`), and ids are caseless (`ids.py:57`). So `struct Outer { struct State {};
  func state() {} }` would mint one id twice, and `add_node` would drop the second node
  (`engine.py:5975-5977`). A new `_swift_nested_collision_groups(body_node, source: bytes,
  parent_nid: str) -> dict[str, set[str]]` collects, per parent, the nested type and member
  names that slug to one id. Both the type id and the member id go through
  `_underscore_salted_nid(plain_nid, name, groups)` (`engine.py:1311`), which salts the
  colliding names by a hash of the name, independent of declaration order; a single public
  name (no leading `_`) in the group keeps the plain id (`engine.py:1331-1333`), as for Python
  #2810. Ids without a collision are unchanged.
- A bare in-body reference (`func f(_ s: State)`) now misses the same-file shortcut and resolves
  through Phase 2's lexical lookup.
- A same-file constructor call to a nested type (`State()` inside `A.runA()`), or to a label
  shared by 2+ Swift types in the file, is no longer bound by the extractor's bare-label map;
  it stays a raw call for Phase 4 (D24). This is why Phase 3 ships with Phase 4.
- Bump `_AST_CACHE_SCHEMA` (D5).

### Phase 4: constructor calls with module-scope evidence (RC4)

In the shared call pass in `extract()`, for every Swift raw call that is not `is_member_call`
(member calls are skipped earlier, at `extract.py:10517`), run the Swift lookup **before** the
generic candidate filtering:

- scope = `_swift_caller_scope(caller_nid, method_owner, node_by_id)` (D20): a caller that is
  itself a Swift type with one `_swift_qualified` path uses that path (property initializers
  are walked with the type as caller, `engine.py:7341`); otherwise the single path of the type
  that owns the caller through a `method` / `contains` edge (the `_csharp_method_owner`
  pattern, `extract.py:10573-10577`); `""` for a file-scope function. `None` (0 or 2+ paths)
  means no Swift binding for this call.
- `_swift_lookup(_swift_type_index(resolution_nodes), callee, scope)`:
  - `"resolved"`: emit `calls` with `context="constructor"`, `confidence="INFERRED"`,
    `confidence_score=0.85`, then `continue`. The call is inferred and not extracted, because
    `Foo(...)` could also be a free function or a static `callAsFunction`.
  - `"ambiguous"` or `"unresolved"`: `continue`, with no fallback to the generic tie-breakers.
  - `"external"`: fall through to the existing logic (free functions, Objective-C).

This covers `via_stub` calls, bare `Foo(...)` calls without an annotation, and the same-file
calls to nested types that the extractor defers (D24) alike. Those same-file calls change
from EXTRACTED to INFERRED. For Swift
calls it takes the place of the `via_stub` evidence gate at `extract.py:10798`: a
`"resolved"` hit is the evidence, the Swift counterpart of the C# `stub_scope_hit`
(`extract.py:10586-10598`). The JS/TS no-import skip at `extract.py:10785-10797` is not a
precedent here.

The `(caller, target)` pair dedup at `extract.py:10800` stays (RC4). A caller that already
references the type, such as `func load() -> Layout { Layout(...) }`, keeps only the
`references` edge. The Phase 4 test therefore uses a caller without a type reference to the
callee (`.reset()` in the repro).

Out of scope for Phase 4: the member form `Outer.Inner(...)`, which reaches the shared pass as
`is_member_call`.

### Phase 5: no collision warning for module anchors (RC5)

In `deduplicate_entities`, skip `_report_id_collision` for a node group whose members are all
`type == "module"` (or `"namespace"`), mirroring `resolution.py:1076`. As an alternative,
`_import_swift` anchors could be emitted sourceless with an `origin_file`. That would change
`build.py` validation and the `--no-cluster` output, so we prefer the one-line skip. No cache
bump (D5).

---

## Impact

### Node ids and graph shape

- Phase 1 changes no ids. It removes duplicate sourced nodes (extension nodes folded into
  their declaration) and sourceless stubs that become unreferenced.
- Phase 2 changes stub labels from `Layout` to `Layout.Pane` for qualified references
  that still do not resolve. Their ids follow from the label through `_make_id`.
- Phase 3 changes nested-type ids, and salts the ids of a nested type and a member that
  collide. Saved queries and `--seed` ids that name a nested Swift type stop matching. This
  belongs in the CHANGELOG.
- `graphify affected` / `explain` for a declared Swift type report more dependants. This is
  the purpose of the change, and `GRAPH_REPORT.md` god-node rankings will move on Swift
  corpora.

### Cache and incremental builds

- `_AST_CACHE_SCHEMA` (`cache.py:40`): one bump in each of Phase 1, 2 and 3; none in Phase 4
  and 5. This PR lands Phases 1-4 together and bumps once (25 -> 26). See D5.
- The new pass reads `resolution_context_nodes` / `resolution_context_edges`, the way the Go
  pass does, and the merge reads them as candidates (Phase 1). So on `graphify update`,
  references written in the **changed** files resolve against unchanged declarations as in a
  full build. This belongs in the regression test list ("Cross-file edges must be preserved
  during incremental updates").
- Known limitation, unchanged by this RFC: the context carries no `references` or `calls`
  edges (`cli.py:4382-4384`). References in **unchanged** files are not re-resolved when a
  declaration is added, moved or deleted elsewhere, or becomes ambiguous; they keep their old
  binding until the next full `graphify extract`. This is the same for every language pass.
- A graph built before the upgrade has no `_swift_extension_only` or `_swift_qualified` keys.
  The CHANGELOG entry should ask for one full `graphify extract` after the upgrade.
- The shrink guard is unaffected in practice: the node count drops only by duplicates and
  unreferenced stubs. A large Swift corpus may still trip it on the first rebuild after the
  upgrade. The CHANGELOG entry should mention `--force` / `GRAPHIFY_FORCE=1`.

### Backwards compatibility

- No CLI or flag changes.
- Non-Swift corpora: every new code path is gated on `.swift` / `tree_sitter_swift` or on the
  new markers. Phase 5 only removes a warning.
- Swift↔ObjC folding (#1556) stays: Phase 1 keeps the `native` family gate in
  `_merge_swift_extensions`. The new symbol table contains Swift declarations only, and ObjC
  classes still reach Swift extensions through the existing merge. A Swift reference to an
  ObjC class is `"external"` for the Swift pass and keeps today's rewire (D7).

### Performance

- Phase 1: O(nodes) set membership, no extra parse.
- Phase 2: one dict build over declared Swift nodes, plus at most `depth(scope)` lookups per
  Swift reference edge, which in practice means at most 3-4. It needs no reparse, because
  scope and full path are recorded at extraction time. On the app above, with 39,656 edges and
  13,962 nodes, this costs less than the existing rewire pass. The call pass and the
  member-call resolver each rebuild the index once (D1).
- No change to the per-file extraction cost beyond keeping a scope stack.

---

## Test plan

The tests follow `tests/test_swift_cross_file_calls.py`: `_write(...)` the files into
`tmp_path` and call `extract(files, cache_root=tmp_path / "cache", root=tmp_path / "src",
parallel=False)`. Assertions name the **target node id**, its `source_file` and its parent
`contains` edge, not only `_edge_labels`: several nodes share a label such as `State`, so a
label assertion passes on a wrong binding.

Each phase lists **regression** tests, which must be shown to fail on `c588b72d` without the
fix, and **controls**, which pass on `c588b72d` and must keep passing.

Phase 1 (`tests/test_swift_cross_file_calls.py`):

- Regression `test_declaration_with_same_file_extension_absorbs_cross_file_extension`: the 3+1
  file repro. It asserts one `Layout` node, `.migrated()` as its method, and every
  `references` edge onto it.
- Regression `test_extension_of_outside_type_does_not_absorb_references`: the #4574 repro.
- Regression `test_extension_only_node_does_not_absorb_other_file_reference`: `extension Foo {}`
  in one file, no declaration, `struct Consumer { var w: Foo }` in another file. The other
  file's reference stays
  on its stub; on baseline the rewire binds it to the single extension node.
- Regression `test_extension_only_marker_survives_incremental_update`: `_rebuild_code` with the
  extension file only in the resolution context; no edge from the changed file onto it.
- Regression `test_incremental_extension_merges_into_unchanged_declaration`: full build, then
  change only the `extension Foo` file. The result equals a full build: one `Foo` node, the
  extension's methods on it.
- Control `test_same_file_extension_alone_still_resolves_references`: the RC1 control. It
  guards against the #4600 regression.
- Control `test_same_file_reference_to_extension_only_node_stays_file_local`: `extension Foo {}`
  and `struct Holder { var v: Foo }` in one file, no declaration, no other consumer. The edge
  targets that file's node.
- Control `test_extension_only_type_extended_in_two_files_stays_unresolved`: `extension View`
  in two files, `struct Screen { var body: some View }` elsewhere. Asserts no edge onto either extension node;
  on baseline the two extension nodes already make the label ambiguous
  (`extract.py:3933-3946`, `extract.py:3993-4012`).

Phase 2 (new `tests/test_swift_type_resolution.py`):

- Regression `test_qualified_nested_reference_resolves_to_nested_type`:
  `var focused: Layout.Pane?` from another file reaches the `Pane` node.
- Regression `test_bare_nested_name_resolves_lexically_in_extension`:
  `extension Editor { func f(_ s: State) }` in another file reaches
  `Editor.State` and not another reducer's `State`.
- Regression `test_bare_name_not_visible_lexically_stays_on_stub`: the only `Config` is
  `Outer.Config`; a bare `Config` in another file stays on its stub, and no edge reaches
  `Outer.Config`. The `_swift_lookup` marker is popped at the end of `extract()` (D16), so
  `_swift_lookup == "unresolved"` is asserted in a direct test of
  `_resolve_swift_type_references` in `tests/test_swift_type_index.py` (D15),
  `test_type_pass_marks_bare_name_not_visible_lexically_unresolved`.
- Regression `test_extension_of_nested_type_merges`: `extension Editor.State { ... }` in
  another file. Its methods attach to the nested declaration.
- Regression `test_qualified_conformance_and_generic_args_resolve`: `struct A: Outer.Proto` and
  `var x: [String: Layout.Pane]` across files.
- Regression `test_type_table_records_full_path`: on the per-file extractor result,
  `result["swift_type_table"]["table"]["focused"] == "Layout.Pane"` and
  `result["swift_type_table"]["scopes"]["focused"] == "Editor.State"`.
- Regression `test_member_call_through_nested_type_annotation`: `x: Outer.Inner` and `x.go()`
  bind to `Inner.go()`.
- Regression `test_member_call_through_nested_parameter_type`: `A.State` and `B.State`;
  inside `A`, `func f(_ x: State) { x.go() }`, with `go()` in `extension A.State` in another
  file; `scopes["x"] == "A"` and the call binds to `A.State.go()`.
- Regression `test_member_call_same_param_name_in_two_types_binds_nothing`
  (`tests/test_swift_member_call_scopes.py`): one file with `A.State`, `B.State`,
  `A.runA(_ x: State) { x.go() }` and `B.runB(_ x: State) { x.go() }`, `go()` added by
  separate extensions; `scopes["x"] is None` and neither call binds, in particular not both
  to `B.State.go()` (D25). The `scopes` assertion fails on baseline, which has no `scopes`
  key; the no-binding part already holds there.
- Regression `test_conflicting_scope_member_call_not_parked_for_cross_repo`
  (`tests/test_swift_member_call_scopes.py`): the same file, plus a second repository with a
  single `struct State { func go() {} }`. Neither call is parked, and
  `link_cross_repo_member_calls` after `graphify merge-graphs` adds no edge to the other
  repository's `State.go()` (D19, D25).
- Regression `test_nested_base_class_resolves_lexically_in_extension`: `Outer.Base`, a
  top-level `Base`, and `extension Outer { class Derived: Base {} }` in another file; the
  `inherits` edge reaches `Outer.Base`.
- Regression `test_extension_of_external_type_does_not_merge_into_nested_namesake`: the only
  `Config` is `Outer.Config`; `extension Config { func extra() {} }` in another file stays its
  own node, and `extra()` is not a method of `Outer.Config`.
- Regression `test_qualified_identity_survives_incremental_update`: change only a consumer of
  `Outer.Inner`; it still reaches `Inner` from the context.
- Regression `test_type_declarations_resolve_with_absolute_paths`: the same fixture extracted
  with absolute and relative paths, and with colliding path slugs (`Cfg/Helpers.swift`,
  `Cfg_Helpers.swift`), gives the same target ids.
- Control `test_ambiguous_bare_name_stays_on_stub`: two top-level `Config` in different files.
  No edge, the stub is kept.
- Control `test_member_call_dotted_type_does_not_bind_concatenated_label`: `x: Outer.Inner`
  with a separate `OuterInner` type; `x.go()` does not bind to `OuterInner.go()`.
- Control `test_same_file_duplicate_nested_names_stay_ambiguous`: `A.State` and `B.State` in
  one file, referenced from another file; no binding before Phase 3.
- Control `test_no_cross_language_binding`: a Swift `Store` reference with a TS `class Store`
  in the corpus. This complements `test_extension_does_not_merge_into_same_named_foreign_type`.
- Control `test_swift_reference_to_non_swift_type_keeps_generic_rewire`: a Swift reference to
  an Objective-C class still resolves.

Phase 3 (`tests/test_swift_type_resolution.py`):

- Regression `test_same_file_nested_types_get_distinct_ids`: `A.State` and `B.State` in one
  file get the ids `_make_id(a_nid, "State")` and `_make_id(b_nid, "State")`, and
  `test_same_file_duplicate_nested_names_stay_ambiguous` now binds each reference.
- Regression `test_nested_type_and_same_slug_method_both_kept`: `struct Outer { struct State {};
  func state() {} }` keeps both nodes and their `contains` / `method` edges.
- Regression `test_bare_in_body_reference_binds_own_nested_type`: two features with their own
  `State` in one file; each `func f(_ s: State)` binds to its own `State`.
- Control `test_nested_constructor_call_kept_after_nested_ids` (needs Phase 4 in the same PR):
  `struct Outer { struct Inner {}; func use(_ x: Inner) {}; func run() { Inner() } }` keeps a
  `calls` edge from `run()` to `Inner`, as on baseline.

Phase 4 (`tests/test_swift_cross_file_calls.py`):

- Regression `test_cross_file_constructor_call_emits_inferred_call`: `.reset()` calls
  `Layout(panes: [])`; one `calls` edge, `context == "constructor"`, `INFERRED`.
- Regression `test_constructor_call_not_visible_lexically_stays_unresolved`: the only `Config`
  is `Outer.Config`; `Config()` elsewhere gets no edge.
- Control `test_ambiguous_constructor_callee_stays_unresolved`: two top-level `Config`; no edge.
- Regression `test_same_file_nested_constructor_binds_own_type` (with Phase 3):
  `struct A { struct State {}; func runA() { State() } }; struct B { struct State {};
  func runB() { State() } }` in one file; `runA()` calls `A.State` and `runB()` calls
  `B.State`, each an INFERRED `calls` edge with `context == "constructor"` (D24).
- Control `test_same_file_top_level_constructor_stays_extracted`: a single top-level
  `struct Foo` and `func make() { Foo() }` in one file keep today's EXTRACTED `calls` edge.
- Control `test_extension_initializer_constructor_call_survives_merge`: `Model.swift` with
  `struct Outer {}`, `Extras.swift` with `extension Outer { struct Inner {}; static let value =
  Inner() }`. After the merge a `calls` edge from `Outer` to `Inner` exists and no raw call or
  edge keeps the deleted extension id (baseline has `Outer -> Inner`).

Phase 5 (`tests/test_swift_import_resolution.py`). `extract()` never calls
`deduplicate_entities` (its only caller is `build.py:1921`), so these tests call
`deduplicate_entities(...)` directly on the extraction of the files:

- Regression `test_shared_module_import_prints_no_collision_warning`: two files that both
  `import Foundation`; `capsys` shows no collision warning.
- Control `test_mixed_module_and_code_collision_still_warns`: a `module` node and a code node
  with one id still warn.

Full gate, per CONTRIBUTING: `uv run pytest tests -q`, `uv run ruff check .`, `uv run pyright`.

---

## Out of scope

- tree-sitter-swift parse errors that swallow declarations (the `@Reducer` struct above, #3542).
- Member-call resolution through nested receivers (`state.layout.encodeAll()`, depth > 1).
- Constructor calls in member form (`Outer.Inner(...)`), see Phase 4.
- Member calls through a factory that returns a nested type whose bare name is not unique
  (`let x = Factory.make(); x.go()` with `make() -> Outer.Inner` and a top-level `Inner`). The
  factory path checks bare-label uniqueness (`extract.py:4661-4666`), so it binds nothing
  (fail-closed).
- Re-resolving references in unchanged files on an incremental build (see Impact).
- Cross-module resolution with `@testable import` evidence (see Q1).
- Protocol-extension default implementations and conditional conformances
  (`extension Array: P where Element == X`). These are left as they are today.

---

## Open questions for the maintainer

1. **Module boundary.** Decided for the first version: the corpus is one module (Phase 2).
   Open for a follow-up: scope the table per Swift module (a SwiftPM target from
   `Package.swift`, `Sources/<Target>/` and `Tests/<Target>/`, or an Xcode target). Per-module
   scoping would avoid false bindings and false ambiguity between an app and its test target,
   which declare many same-named helpers.
2. **#4600 vs Phase 1.** Resolved: Phase 1 is its own implementation and is not based on #4600,
   which does not fix the `Layout` case and regresses the common case.
3. **Confidence for lexical resolution.** Is `EXTRACTED` right for a binding derived from Swift
   lookup rules, or should cross-file Swift type bindings be `INFERRED` like Phase 4?
4. **Stub labels.** Resolved: a qualified unresolved reference (`Foo.Bar`) keeps the full
   dotted label, as Go's external stubs do (Phase 2).
5. **Ordering with #4599/#4639.** Phase 3 does not wait for #4599 (D8). Open: if #4599 lands
   first, does it use the same id formula, so that Phase 3 shrinks to the collision pre-scan
   and the tests?

---

## Implementation notes

Phases 1-4 are implemented in this PR; Phase 5 (the module collision warning) and the Python
member-call language gate ship as separate small PRs. The decisions below
were taken during the implementation. The fixed contracts above follow them; where a phase
section still differs (the Phase 3 salting rule), these notes take precedence.

- **D24, same-file constructor calls.** The extractor does not bind a
  same-file constructor call whose label names a nested Swift type or a label shared by 2+
  Swift type nodes in the file. The call stays a raw call and Phase 4 binds it through
  `_swift_lookup` + `_swift_caller_scope` as an INFERRED `calls` edge
  (`context="constructor"`). A label that names a single top-level type keeps the same-file
  EXTRACTED binding.
- **D25, flat per-file receiver table (fail-closed).** `swift_type_table`
  stays flat per file. When two writes for one name in a file disagree on type or scope
  (shadowed locals included), the extractor stores `scopes[name] = None`; the `table` value
  stays. `_resolve_swift_member_calls` binds nothing for such a name and does not park it, so
  the cross-repo pass cannot bind a locally declared name to a foreign type. The same holds
  for an `"ambiguous"` lookup; only `"unresolved"` and `"external"` park. The rule is
  fail-closed for any differing write: two writes of the same type in two enclosing types, or
  spelled `Outer.T` and `T`, also give `None`. A refinement that keeps one scope for writes
  proven to name the same type is left for follow-up work.
  The check sees the writes that go into `table`: properties, parameters and the locals that
  `_swift_local_var_types` types. Factory bindings (`let x = Maker.make()`) and annotated
  locals bound from a call (`let x: B = obtain()`) do not take part yet, so two such writes
  of one name in different functions can still both bind to the first one, as on v8
  (follow-up).
- **Sugar extensions.** `extension [T]`, `extension [K: V]` and `extension T?` extend
  `Swift.Array`, `Swift.Dictionary` and `Swift.Optional` (label, id and `_swift_qualified`).
  Reading the written text would slug to `T`'s own id, give `T` a second qualified path and
  make it ambiguous; the `Swift.` prefix keeps a project's own `struct Array` from absorbing
  the extension. The node stays `_swift_extension_only`. A written `extension Array<T>` takes
  the path `Array`.
- **Dotted labels resolve only through `_swift_lookup`.** A dotted Swift name such as
  `MenuItem.ID` never falls back to the label key, which drops the dot and would
  bind an unrelated `MenuItemID`. This holds for the member-call receiver fallback
  and for the stub rewire (`_rewire_unique_stub_nodes`); the rewire guard tests the raw `.swift`
  suffix, so a file remapped to Swift with `.graphifyrc` is not covered yet
  (follow-up). Undotted names keep the fallback.
- **No type-only edge to an extension-only node.** When a member call's receiver type is an
  extension-only node and the method is not defined in the extension, no `references` edge is
  emitted.
- **Language gates on the member-call passes.** `_resolve_swift_member_calls` handles only
  Swift callers, decided by `effective_suffix` so a `.graphifyrc` language override counts, and
  binds only targets whose effective suffix is `.swift`, `.m`, `.mm` or `.h` (Objective-C
  interop). The gate is by suffix, so a C or C++ namesake in a `.h` or `.mm` file
  still passes (follow-up).
  The matching gate for `_resolve_python_member_calls` (Python callers and Python targets
  only) ships as a separate PR. Edges between other languages come from their own passes.
- **Nested id salting.** Phase 3 above says a single public name in a collision group keeps
  the plain id. The code differs in two cases: an enum case or computed property always keeps
  its plain id, so with one of them in the group every nested type and method is salted, even
  the only public name; and a nested type and a method of the very same name (`struct State`,
  `func State()`) get distinct ids, the type salting a kind-tagged name
  (`_swift_salted_member_nid`, `engine.py:1503-1523`).
- **Cache schema.** This PR bumps `_AST_CACHE_SCHEMA` once, 25 -> 26 (D5), instead of once
  per phase.

Known limits left for follow-up work are listed in the PR description.
