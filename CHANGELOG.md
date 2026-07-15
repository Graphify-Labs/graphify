# Changelog

Full release notes with details on each version: [GitHub Releases](https://github.com/safishamsi/graphify/releases)

## 0.9.17 (unreleased)

- Security/privacy follow-up: nodes whose `source_file` was never dispatched are now dropped from the graph, not just skipped from the cache (#1895). The #1757 guard stopped a mis-attributed node from clobbering another file's cache entry, but the node itself still flowed into `graph.json`; it is now filtered out of the merged result (real-file, non-dispatched attributions only), consistent with the cache rejection.
- Fix: `manifest.json` now records every successfully-extracted file, not just the zero-node ones (#1897). The #933 stamping filter compared root-relative node `source_file`s against absolute `detect()` paths, so it dropped every freshly-extracted semantic document from the manifest and broke the incremental-update baseline. Both sides are now resolved before comparison; genuinely omitted/zero-node docs stay unstamped so they retry.
- Fix: `graphify hook install` now registers the `graph.json` union merge driver that the README and CHANGELOG have long documented (#1902). It writes the `merge.graphify` config via `git config` and an idempotent, append-only `graphify-out/graph.json merge=graphify` line in `.gitattributes`; `uninstall` removes them.
- Fix: `hook install`/`status` no longer print a spurious "could not read core.hooksPath" warning on repos whose `.git/config` contains git-legal duplicate keys (VS Code writes these) (#1907). Config is now resolved via `git rev-parse --git-path hooks` instead of a strict `configparser`, which rejected duplicate keys.
- Fix: `graphify export obsidian` prunes notes for nodes that left the graph instead of merging old and new on re-export (#1896). Only notes graphify itself wrote (tracked in its ownership manifest) are removed, with a vault-containment guard, so user-authored notes are never touched.
- Fix: non-English query sentences no longer pick wrong BFS seeds because their filler words were unfiltered (#1900). The query stopword set now covers German and the major Romance languages (curated to avoid clobbering English content words), so `Wie funktioniert die Authentifizierung?` seeds the keyword, not the stopwords.
- Fix: Python calls to an imported module now resolve (already shipped in 0.9.16); `.skill` files (Markdown-with-frontmatter agent files) are now classified as documents instead of being silently dropped as an unsupported extension (#1901).
- Fix: the `--postgres` missing-driver error now points at the correct PyPI package, `graphifyy[postgres]` (was the nonexistent `graphify[postgres]`) (#1906).

## 0.9.16 (2026-07-14)

- Fix: semantic extraction now reconciles dispatched files against returned results, so a document the model silently omits is no longer lost without a trace (#1890). A chunk can return a clean, non-empty response that simply leaves out some of the documents it was given; those docs previously produced no node, no warning, and no cache/manifest stamp, so they were re-dispatched and re-omitted on every run. `extract_corpus_parallel` now diffs the dispatched file set against the `source_file`s that came back, records the gap in `uncovered_files`, and prints a loud warning listing the omitted files. (This is the visibility guard; routing documents through the deterministic extractor so they always get at least a file node is tracked separately.)

- Fix: close two residual paths where an absolute scan path (including the OS username) still leaked into a committed `graph.json`, completing #1789 (#1899). (a) A reference target outside the scan root (an out-of-root `.csproj` ProjectReference, `.sln` project, or bash `source`) kept its absolute `source_file` and an absolute-derived id, because the relativization post-passes silently skipped anything `relative_to(root)` could not handle; such targets now get a portable walk-up relative path and an `ext_`-namespaced id (bare basename when the target is far outside the corpus or on another drive). (b) A symbol whose name normalizes to nothing (a minified `$` function, a JSONC `"//"` comment key) collapsed `_make_id(stem, name)` down to the bare absolute file stem; those no-signal symbols are now skipped at mint time.

- Fix: uppercase TypeScript extensions (`.TS`/`.TSX`/`.MTS`/`.CTS`) are now parsed with the TypeScript grammar instead of falling through to the JavaScript grammar, which silently dropped interfaces and type aliases (#1881, thanks @xkam7ar). Detection and dispatch already lowercased, but the grammar selection inside `extract_js` compared the suffix case-sensitively.

- Fix: Kotlin builtin/stdlib types (`String`, `Int`, `List`, ...) are no longer emitted as `references` edges, matching the existing Java/Python/Go builtin filtering (#1876, thanks @kebwlmbhee). They created false coupling and split clusters on real projects. User types that legitimately share a name (`Result`, framework types) are deliberately not filtered, consistent with the other languages.

- Fix: the stale/missing-skill version warning now prints to stderr, not stdout, so it no longer pollutes the machine-readable output of `graphify query`/`path` (#1805 / #1893, thanks @Mzt00). Every sibling warning in that check already used stderr.

- Fix: Python qualified calls to an imported module (`module.function()`) now produce a `calls` edge, matching bare-name calls (#1883). The call was captured correctly but fell through a gap: the shared cross-file pass skips every member call (to avoid god-node blowups from bare method names), and the Python member-call resolver only handled capitalized class receivers (`ClassName.method()`), so a lowercase module receiver was dropped. The resolver now also resolves a lowercase receiver that names a module imported into the caller's file, linking to the single callable that module contains (guarded so `self`/`obj`/local instances and ambiguous names never create a false edge).

- Fix: `--exclude` patterns now survive into `update`/`watch`/git-hook rebuilds instead of applying only to the initial scan (#1886). The patterns were never persisted, so the first rebuild re-ran `detect()` without them and silently re-indexed the excluded paths. `extract` now records them in a `graphify-out/.graphify_build.json` sidecar and `_rebuild_code` re-applies them on every rebuild (they still layer after `.gitignore`/`.graphifyignore`/`.git/info/exclude`, so they keep winning). Graphs built before this release simply have no sidecar and behave as before.

- Fix: the dedup ID-collision warning now reports in proportion to what is actually lost, and an ID collision resolves to a deterministic survivor (#1851 / #1852, thanks @bchan84x). Two nodes can mint the same `<path>_<entity>` ID when a document merely references an entity defined elsewhere; the old code kept whichever arrived first and always printed a scary "two files with the same name" warning that overstated the loss (edges rewire to the survivor, so a reference collapse loses nothing). Now the node whose `source_file` actually defines the ID wins, a harmless reference collapse is silent, a same-file relabel is a quiet note, and only a genuine cross-file collision warns. The survivor is chosen by a total order (definer first, then the shorter/canonical label, then lexically) so it no longer depends on chunk arrival order, including when several same-file nodes co-define one ID.

- Fix (regression from 0.9.15): a nested `.gitignore`/`.graphifyignore` no longer applies its patterns outside its own directory (#1873 / #1887 / #1885, thanks @Alwyn93). When 0.9.15 started reading nested ignore files, a non-anchored pattern was still matched against the path relative to the scan root, so a nested bare `*` (a common "ignore this scratch dir" idiom, e.g. what the hypothesis library writes into `.hypothesis/`) matched every file and `detect()` returned zero files, silently producing an empty graph. Patterns are now matched relative to the directory whose ignore file defined them and only apply within that subtree; the anchor directory itself is exempt.

- Fix (regression from 0.9.15): `graphify update` no longer emits 0 nodes and refuses to overwrite an existing `graph.json` when the source tree contains a nested broad `.gitignore` (#1880). This was the update-layer symptom of the scoping bug above: the zeroed re-scan produced an empty rebuild, which the shrink-guard then correctly refused. With subtree scoping fixed the rebuild sees the real files again; the shrink-guard is unchanged.

- Fix: a full `graphify update` no longer evicts the LLM semantic edges of a re-extracted document (#1865 / #1868, thanks @xor-xe). Node reconciliation was already provenance-aware (semantic nodes lack the AST `_origin` marker and are preserved), but edge reconciliation evicted by `source_file` alone, so a Markdown/doc file that also has an AST extractor had its `semantically_similar_to`/`conceptually_related_to` edges dropped on an AST-only rebuild that cannot regenerate them, leaving orphaned concept nodes. Edges now carry the same `_origin` marker, and re-extraction replaces only a source's AST-tier edges while its semantic edges survive until a semantic re-extraction supersedes them. Deletion still evicts every tier.

- Fix: `--cargo` no longer drops a workspace-internal dependency edge that uses Cargo's `package = "..."` rename (#1858 / #1861, thanks @thejesh23). The dependency loop looked up crates by the `[dependencies]` table key, but a renamed entry (`db = { path = "../storage", package = "internal-storage" }`) keys on `db` while the target crate is published as `internal-storage`, so `crate_depends_on` silently never appeared. The lookup now honors the `package` override.

- Fix: `detect_incremental` re-extracts a legacy-manifest file when its mtime moves backwards, not just forwards (#1859 / #1862, thanks @thejesh23). The legacy float-schema branch used a strict `current_mtime > stored`, so a file restored to an older timestamp (a `git checkout` of an older commit, a tarball restore, `rsync --times`) was treated as unchanged and never re-extracted, leaving the graph reflecting newer content than the corpus on disk. It now compares with `!=`, matching the dict-schema branch; with no stored hash to verify, any mtime delta forces a re-extract, and the next save promotes the entry to the hash-verified dict schema.

- Fix: the dedup summary line reports the fuzzy-merge count even when there were no exact merges (#1857 / #1860, thanks @thejesh23). The fuzzy branch was nested inside `if exact_merges`, so a doc- or semantic-heavy run that merged only via the cross-file fuzzy pass printed a bare `Deduplicated N node(s).` with no breakdown. Both counts are now reported whenever non-zero.

- Fix: the incremental semantic-cache checkpoint no longer fails on oversized (sliced) documents (#1870). The 0.9.14 batch-scoping fix built its per-chunk allowlist by reading `FileSlice.rel`, an attribute that does not exist (a `FileSlice` carries its parent file in `.path`), so every chunk containing a sliced document leaked the `FileSlice` object into the allowlist, `save_semantic_cache` raised `TypeError`, and the best-effort handler swallowed it: extraction still finished but those chunks were never checkpointed, so a re-run or a run resumed after a crash/rate-limit re-billed them. The allowlist now resolves each unit through `unit_path`, so a slice maps to its parent file and the checkpoint writes as intended.

## 0.9.15 (2026-07-13)

- Fix: detection now honors nested `.gitignore`/`.graphifyignore` files below the scan root, not just those at the scan root and above (#1847, thanks @Mohak-Agrawal). git applies a `.gitignore` to everything under its own directory, but graphify only loaded ignore files from the VCS-root-down-to-scan-root chain — so a `vendor/sub/.gitignore` deeper in the tree was never read and its exclusions leaked into the graph. Each directory's own ignore files are now read during the walk and anchored to that directory, preserving last-match-wins precedence (nearer files win, including over `.git/info/exclude`) and the parent-exclusion rule.

- Fix: `graphify update` now writes human-readable `community_name` labels, not just numeric community ids (#1808 / #1855, thanks @latreon). The incremental rebuild in `_rebuild_code` called `to_json` without `community_labels`, so every `update`/hook rebuild stripped the labels a `cluster-only` pass had written; a follow-up `cluster-only` restored them and the next rebuild stripped them again. The rebuild now forwards the labels it already computes (hub-derived for a code-only pass) and strips `community_name` from the topology fast-path comparison so the new field doesn't force a needless re-cluster.

- Security: fix a stored XSS and broken neighbor links in the exported `graph.html` (#1838, thanks @edgestack-ai). The report's neighbor "focus" links dropped an unescaped `JSON.stringify(nid)` into a double-quoted inline `onclick`. Because the stringified value carries its own quotes, the attribute was truncated on every node — so the links never worked — and a node `id`/`label` containing a double-quote broke out of the attribute and injected live handlers. AST node ids are `[a-z0-9_]`-safe, but ids/labels from documents or from titles scraped via `graphify add <url>` are not, so a hostile source could plant an executable handler into a report opened locally. The id is now carried in an HTML-escaped `data-nid` attribute and dispatched through a single delegated listener, closing the injection and repairing the links.

## 0.9.14 (2026-07-12)

- Fix: Visual Studio *solution folder* nodes no longer embed the absolute scan path (including the local username) in their `id` and `source_file` (#1789, thanks @fremat79). A solution folder is a virtual grouping, not a file — VS writes its name as both the display name and the "path" — but `extract_sln` resolved it to an absolute filesystem path anyway and keyed the node id off that. The CLI's id-relativization pass only remaps ids of real files in the scan set, so a virtual folder never matched and its absolute id survived into a committed `graph.json` (e.g. `id=/Users/<name>/proj/Plugins` instead of `id=plugins`). Solution folders are now detected (name == path) and keyed off the folder name only; real project files still resolve as before. (The earlier fix covered `.csproj`/`.sln` file nodes but missed the virtual folders — this completes it.)

- Fix: the CLI no longer crashes with exit code 255 when a downstream reader closes the pipe early (#1807 / #1811, thanks @varuntej07). Truncating output with `head`, PowerShell's `Select-Object -First N`, or `sed q` disconnected the reader mid-write, graphify hit an unhandled `BrokenPipeError` (or `OSError(EINVAL)` on Windows) and exited 255 — so CI wrappers and agent harnesses that both trim output and check the exit code read a successful query as a command failure. An early-closing reader is now treated as success: stdout is flushed inside the guard (piped stdout is block-buffered, so a small output would otherwise only flush at interpreter shutdown, where the error escapes as a noisy "Exception ignored" and a nonzero exit), then redirected to devnull so the shutdown flush can't raise again, and the process exits 0.

- Fix: `extract()` no longer writes its AST cache into the analyzed source tree (#1774 / #1802, thanks @SimiSips). With no explicit `cache_root`, the cache defaulted to the inferred common parent of the input files — the source tree — so analyzing a read-only or foreign corpus silently created `graphify-out/cache/` inside it. The cache is an output, so it now defaults to the current working directory. Crucially, the cache *location* is decoupled from the key/id *anchor*: the inferred common parent still anchors the content-hash keys, node ids, symbol resolution, and the XAML/C# project-scan boundary, so keys stay relative and portable (shared/CI cache reuse keeps working) and out-of-CWD corpora aren't mis-scanned. An explicit `cache_root` (as the CLI and watcher pass) is unchanged.

- Fix: `graphify query` no longer floods results with homonymous generic symbols (#1766 / #1832, thanks @devcool20). When dozens of nodes share one generic label — framework route handlers all labelled `GET`/`POST`, a repeated `handler` — they used to consume every BFS seed slot, so the traversal explored many near-identical neighborhoods and drowned out the query's actual target. Seed selection now deduplicates by normalized label (`GET`/`Get`/`get` collapse together), keeping at most one representative per label while still guaranteeing a seed for each distinct query term. The per-label cap is scoping-only — the shared node scorer (also used by `shortest_path`/`explain` endpoint resolution) is left untouched, so those are unaffected.

- Fix: semantic cache writes are now scoped to the files actually dispatched in each extraction batch (#1757 / #1835, thanks @TPAteeq). A model can attribute a node's `source_file` to another corpus file; `save_semantic_cache` would then replace (or, mid-run, pollute) that other file's complete cache entry with a stray fragment — silently, with no shrink guard. Writes now honor an `allowed_source_files` allowlist: the final CLI write is scoped to the uncached file set, and the per-chunk incremental checkpoint (`extract_corpus_parallel`, the default path for `extract`/`update`) is scoped to that chunk's own files, so an out-of-scope attribution is skipped with a warning instead of clobbering a legitimate entry.

- Fix: `graphify export graphml` no longer crashes on dict- or list-valued attributes (#1831 / #1830, thanks @hofmockel). `nx.write_graphml` only accepts scalar values, so a per-node `metadata` dict or the graph-level `hyperedges` list raised `GraphML does not support type <class 'dict'/'list'>` and failed the entire export — on a real ~2,300-node graph, every attempt. `to_graphml` now coerces `None -> ""` and JSON-serializes non-scalars across graph/node/edge scopes (GraphML-native int/float/bool/str pass through unchanged), and writes atomically via a temp file so a failed export no longer leaves a 0-byte `.graphml` that downstream tooling mistakes for a completed one.

- Fix: `.nox/` (nox virtualenvs) is now skipped during detection alongside `.tox/` (#1804, thanks @igorregoir-lgtm). nox is tox's successor and creates a `.nox/` tree of the same shape, but only `.tox` was in the skip set — so a repo with a nox env got its site-packages fully indexed (one real repo came out 91% venv noise: 6,720 of 7,365 nodes from `.nox/`) and semantic extraction burned tokens reading venv docs.

- Fix: detection now honors `.git/info/exclude`, not just `.gitignore`/`.graphifyignore` (#1810, thanks @cdahl86-cyber). `info/exclude` is where git records local-only excludes and where `git worktree add` writes nested worktree paths, so a repo can exclude a directory without any `.gitignore` entry. graphify walked straight into those worktree copies and the graph exploded (one repo with 5 worktrees went from ~9,400 nodes / 10 MB to ~210,000 nodes / 311 MB, ~77% duplicate worktree nodes, near the 512 MB cap — regenerated on every commit by the auto-rebuild hooks). The exclude file is loaded at lowest precedence (below every per-directory `.gitignore`/`.graphifyignore`), matching git, so a nearer `!` re-include still wins; the linked-worktree/submodule case (where `.git` is a file) is resolved to the shared common git dir.

- Fix: the git hooks no longer misbehave inside linked worktrees, and `GRAPHIFY_SKIP_HOOK` now suppresses both hooks (#1809, thanks @cdahl86-cyber; worktree guard co-developed with @Claude-Madera's #1806). Two gaps: (1) `post-checkout` never checked `GRAPHIFY_SKIP_HOOK`, so the var stopped commit-triggered rebuilds but not branch-switch ones; it now honors it like `post-commit`. (2) With `core.hooksPath` shared across worktrees, a commit in any linked worktree fired `post-commit`, which wrote a rogue delta-only `graph.json` into that worktree and raced deploy/CI `git clean` against the detached rebuild (`failed to remove graphify-out/: Directory not empty`). Both hooks now short-circuit in a linked worktree (git-dir != git-common-dir), comparing absolute paths so the primary checkout — where `--git-common-dir` is the relative `.git` — is never false-positived and wrongly skipped.

## 0.9.13 (2026-07-12)

- Fix: the query log is now opt-in (off by default) (#1797, thanks @adam-pond-agent). `querylog` wrote every `query`/`path`/`explain` question and corpus path (and full responses if `GRAPHIFY_QUERY_LOG_RESPONSES`) to a default-on, unbounded, fail-silent plaintext file at `~/.cache/graphify-queries.log` — outside any repo's .gitignore/retention, and undocumented, which contradicts graphify's on-device / no-telemetry posture. Logging is now OFF unless you opt in with `GRAPHIFY_QUERY_LOG_ENABLE=1` (default path) or `GRAPHIFY_QUERY_LOG=<path>`; `GRAPHIFY_QUERY_LOG_DISABLE=1` still forces it off. All the query-log env vars are now documented in the README.

- Fix: a markdown file that went through semantic extraction is no longer duplicated into two disconnected nodes on later `graphify update` (#1799, thanks @jerp86). The semantic pass mints `<slug>_doc` while the markdown quick-scan mints the bare `<slug>`, so the file's edges split across two twins (a docs->code path query would dead-end on the bare half; centrality and communities split too). `build_from_json` now merges the bare quick-scan node into the semantic `_doc` node when both share the same `source_file` and are `file_type: document`, consolidating their edges/hyperedges onto one node. Gated so an unrelated code symbol `foo` and `foo_doc` never merge.

- Fix: incremental `graphify update` no longer silently evicts nodes for a file that left the scan corpus but still exists on disk (#1795, thanks @CJNA). `_reconcile_existing_graph` read "source absent from the collected corpus" as "deleted", but that's also what an ignore-rule/filter change looks like (e.g. an upgrade that starts honoring `.gitignore`) — in one 27k-node graph the first rebuild after such an upgrade mass-evicted 655 nodes whose files were present the whole time. Eviction now fails closed: a corpus-absent source is only evicted when `Path(identity).exists()` is False (true deletion), otherwise its nodes/edges/hyperedges are preserved and a loud line reports how many were kept and why. True deletions and renames evict as before; a full `extract --force` still purges deliberate exclusions.

- Fix: `build_merge` no longer silently deletes a re-extracted file's fresh nodes when that file is also passed in `prune_sources` (#1796, thanks @erichkusuki). A file present in `new_chunks` is being replaced, not deleted, so it's now excluded from the prune set — "replace" wins over a contradictory "delete" of the same source. Previously, following the old edit-workflow (pass the changed file in `prune_sources`) deleted the just-built concept whenever an edit kept a node's label. Genuine deletions (a file in `prune_sources` but not `new_chunks`) still prune.

- Fix: `graphify path` resolves each endpoint to the first candidate whose label contains every query token, instead of blindly taking the top-scored node (#1785, thanks @CJNA). `_score_nodes`' full-query bonus only fires when the query equals/prefixes a label, so a query that is a token *subset* of the intended label (`"Reject-everything judge"` vs `"Degenerate Reject-Everything Judge"`) got no bonus and a node prefix-matching one rare token could outscore it — anchoring the path on an unrelated, often disconnected node and yielding a false "No path found". When the top candidate already full-matches (the common case) the pick is unchanged. Applied to both the `path` CLI and the MCP shortest-path tool; the close-runner-up ambiguity warning now fires only when the score head is what was actually picked.

- Fix: the report's "Suggested Questions" weakly-connected-node count now matches its "Knowledge Gaps" count (#1768, thanks @balloon72). `suggest_questions()` omitted the `file_type != "rationale"` filter that `report.py`'s Knowledge Gaps section applies, so the same `GRAPH_REPORT.md` showed two different numbers for the same concept (e.g. 757 vs 245), making a healthy graph look like it had a major documentation gap. Both computations now use the same filter.

- Fix: Bash scripts that run each other by execution now get a cross-file edge (#1756, thanks @balloon72). `extract_bash` only linked `source x.sh` / `. x.sh`; the two most common forms — `bash x.sh` and `./x.sh` — produced no edge, so execution topology was missing. They now emit a `calls` edge (context `script_invocation`) to the invoked script's entry node when the target resolves to a real file on disk (script runners `bash`/`sh`/`zsh`/`ksh`/`dash` and bare `./x.sh`), skipping missing or shadowed targets.

- Fix: Ruby `.rake` files are now extracted and participate in Ruby cross-file resolution like `.rb` (#1784, thanks @krishnateja7). `.rake` is plain Ruby but the extension was gated out of seven places (classification, extractor dispatch, the language-name/family maps, the `ruby_member_calls` resolver's suffix set, both `.rb`-suffix filters in `ruby_resolution.py`, and the build repo-tag map), so every rake task was skipped and its calls were invisible. All seven now include `.rake`; `Widget.tally` from a `.rake` task resolves to its `.rb` definition.

- Fix: cross-module references to a function now resolve to its definition instead of dangling on a name-only stub (#1781, thanks @EmilNyg). `_rewire_unique_stub_nodes` gated merge targets through `_is_type_like_definition`, which rejects any label ending in `)` — so function/method defs could never absorb their reference stubs, and "who references this function" returned nothing on the definition node while a sourceless stub held all the edges. Top-level function defs are now eligible rewire targets when the label match is globally unique, gated by a language-family match with the referrers (a Python `get_db` reference can't bind to a unique Go `get_db()`) and excluding stubs used as a supertype (`inherits`/`implements`/`extends` — you don't inherit from a function). Types are unchanged.

## 0.9.12 (2026-07-10)

- Fix: live PostgreSQL introspection (`--postgres`) now emits foreign-key `references` edges under a read-only role (#1746, thanks @rithyKabir). The FK query read `information_schema.referential_constraints`, which is privilege-filtered — a role with only SELECT sees zero FK rows while tables/views/routines still appear, so every `references` edge silently vanished. It now reads the world-readable `pg_catalog.pg_constraint` (keyed by oid, which also fixes same-named constraints on sibling tables cross-matching in the old name-based joins), preserving composite-FK column order via `UNNEST ... WITH ORDINALITY`.

- Fix: `json_config` no longer emits `imports`/`extends` edges to node IDs it never creates (#1764, thanks @oleksii-tumanov). `package.json` dependencies and `tsconfig.json` `extends`/`$ref` targets produced edges whose endpoint node was absent, so `build_from_json` silently dropped them (the "no matching node id" case is filtered out of real errors) — losing dependency/extends structure on two of the most common files in any JS/TS repo. The extractor now creates the referenced target as a `concept` node before adding the edge.

- Fix: `graphify update` no longer deletes semantic hyperedges on every run (#1755, thanks @oleksii-tumanov). The AST-only rebuild treated every rebuilt corpus file as grounds to evict hyperedges anchored to it, but the AST pass never re-emits hyperedges, so doc-sourced hyperedges (exactly what semantic extraction produces) were permanently lost on the first `update` after a full build — even a no-op run. Hyperedge eviction is now scoped to genuinely deleted (or symlink-outside) sources, mirroring node/edge handling; replacement-by-id and dangling-member cleanup are unchanged.

- Fix: Java member calls resolve against the receiver's declared type instead of a bare method-name match (#1696/#1697, thanks @oleksii-tumanov). `gw.charge()` where `gw: PaymentGateway` now binds to `PaymentGateway.charge`, not a same-named `AuditLog.charge` in another file. Explicit-type receivers and `this` are exact; current-class fields, method parameters, and explicitly-typed locals resolve via a method-scoped type table; a missing, ambiguous, inherited, or chained receiver is skipped rather than guessed (same god-node guard as the C#/Swift/Ruby resolvers). Fully-qualified and nested-type receivers are deferred (they need package/nesting-aware type identity).

- Fix: output/cache artifacts no longer land in the scanned corpus or CWD when `--out`/`--graph` point elsewhere (#1747, thanks @bbqboogiedwonsen). `extract <corpus> --out <dir>` correctly wrote the graph to `<dir>` but `detect()`'s word-count/stat-index cache still created a stray `graphify-out/cache/` inside the corpus (it uses the scan root); it now honors the `--out` dir via a threaded `cache_root`. And `cluster-only --graph <elsewhere>/graphify-out/graph.json` wrote `GRAPH_REPORT.md`/labels/analysis/re-clustered graph to the CWD instead of beside the input; it now writes beside `--graph` when that graph lives in a `graphify-out/` dir, while still restoring into the CWD for an archived `backup/graph.json` (#934).

- Fix: `imports`/`references` edges no longer bind across a language boundary (#1749, thanks @philberndt). The spec already forbids cross-language `calls`, but an unresolved Python `import time` could still resolve by bare stem onto a `src/time.ts` file node — welding a polyglot repo's halves together at a phantom edge (in the reporter's repo, 3 such edges were the *only* thing bridging 2409 Python nodes to 1403 TS nodes, inflating `time.ts` betweenness ~90x and making it the #1 "god node"). The build-time cross-language guard now covers `imports`/`imports_from`/`references` in addition to `calls`, dropping an edge only when both endpoints are known code languages of different interop families (so a config/manifest → code reference is untouched).

- Fix: files whose extractor bailed out for a missing optional dependency no longer vanish without a trace (#1745, thanks @rithyKabir). `.sql` files (and other extra-gated languages) have a dispatch entry, so the #1689 no-extractor warning can't fire, and `extract_sql` returns an error result when `tree-sitter-sql` is absent, so the #1666 zero-node warning skips it too — the graph built "successfully" while an entire SQL corpus contributed nothing. `extract()` now surfaces these grouped by extension, naming the extra that restores the language (e.g. `pip install "graphifyy[sql]"`).

- Fix: `build_from_json` is deterministic across process runs again (#1753, thanks @erasmust-dotcom). The ghost-node merge iterated `set(G.nodes())`, so which node survived a `(basename, label)` collision depended on CPython's per-process string-hash seed — rebuilding the same extraction JSON in a fresh process could silently pick a different canonical id (breaking the cluster→relabel workflow with a `KeyError` on an id that vanished). The Pass 1/Pass 2 loops now iterate in sorted order. Additionally, two non-AST (semantic) nodes sharing a key but from *different* files are now treated as distinct concepts and both survive (mirroring the AST/AST ambiguity guard #1257) instead of one arbitrarily merging away; a genuine same-file duplicate still collapses.

- Fix: a Java field/parameter/return-type reference to a class whose simple name is shared by two modules no longer dangles on a sourceless phantom node (#1744, thanks @aviciot). Both same-named classes already survive as distinct path-scoped nodes, but the cross-module `references` edge was left pointing at a bare no-source stub because `_resolve_java_type_references` re-pointed `implements`/`inherits`/`imports` but not `references` — so a query about the referenced class could miss it. The Java resolver now disambiguates `references` by the importing file's `import` statement (falling back to same-package), mirroring the C# resolver, and drops the orphaned phantom.

## 0.9.11 (2026-07-08)

- Fix: file enumeration no longer silently drops a directory subtree. `detect()`'s `os.walk` had no `onerror` handler, so an `os.scandir` failure (a permission error, or a directory created/deleted mid-walk by concurrent writes) was swallowed and that whole subtree vanished from the scan with no log, yielding a silently partial `graph.json`. The walk now records every skipped directory (surfaced in the result's `walk_errors`) and warns to stderr, while still enumerating the rest. Relatedly, `to_json`'s anti-shrink guard (#479) now fails safe: a non-empty but unreadable existing `graph.json` refuses the overwrite (pass `force=True` to override) instead of silently clobbering a good graph; an empty file still proceeds.
- Fix: Pascal/Delphi extractors no longer emit duplicate `method`/`contains`/`inherits` edges. A class method declared in the interface section and defined in the implementation section each emitted an edge to the same node, so ~half of a Pascal graph's method edges were doubled (skewing degree/centrality and tripping the new cross-file resolver's god-node guard). Both extractors now dedup edges on (source, target, relation), mirroring the existing node dedup.
- Fix: Pascal/Delphi call resolution is scoped to the caller's class + inherits chain, and calls to methods inherited across file boundaries now resolve (#1739, thanks @richtext). Both extractors previously resolved every call via a single file-wide `{name: node_id}` dict, so two unrelated classes with a same-named method (property accessors, generated COM/TLB wrappers) collapsed onto whichever was inserted last, producing wrong cross-class `calls` edges. Resolution now walks own-class then ancestor chain then file-level free functions, emitting no edge when ambiguous (same god-node guard as the Ruby resolver). A new corpus-wide resolver (`graphify/pascal_resolution.py`) resolves calls from a descendant to a base-class method declared in a different file (the common generated-base/manual-descendant split). Also stops emitting a duplicate cross-file base-class stub carrying the wrong `source_file`.
- Fix: query ranking no longer lets a lone generic term that exact-matches a short leaf label hijack seed selection in multi-term queries (#1602/#1724, thanks @fkhawajagh). `_score_nodes` scales the per-term exact/prefix tiers by squared term coverage; single-term and full-coverage queries are unchanged.
- Fix: Kotlin enum entries are extracted as nodes with `case_of` edges to their enum (#1700, thanks @ivanzhilovich). Closes the Kotlin half of #1700 (the Java half shipped in 0.9.10 via #1719); `enum class ChatType { NORMAL, GROUP, SYSTEM }` now yields NORMAL/GROUP/SYSTEM nodes and "where is ChatType.X used" works for Kotlin.
- Fix: SKILL.md's POSIX interpreter probe no longer silently falls back to a graphify-less system python (#1735, thanks @mohammedMsgm). Step 1 ran `uv tool run graphifyy python -c ...`, but the `graphifyy` package's executable is `graphify`, so uv treated `python` as a missing `graphifyy` command; `2>/dev/null` hid uv's own `--from` hint, leaving `PYTHON` on an interpreter without graphify. The probe now runs `uv tool run --from graphifyy python -c ...`. The PowerShell path was already correct.

- Refactor: decomposed the two largest modules into focused, single-responsibility modules — verbatim moves only, every original import path preserved via re-exports, no behavior change (#1737, thanks @TPAteeq). `extract.py` 17,054 → 4,740 LOC (the tree-sitter engine, cross-file resolution, shared models, and 23 language extractors moved under `graphify/extractors/`), `__main__.py` 5,368 → 673 (install/uninstall + CLI dispatch split into `graphify/install.py` and `graphify/cli.py`), `export.py` 1,671 → 962 (HTML + graph-DB exporters under `graphify/exporters/`). Full suite unchanged.
- Fix: `merge-graphs` gives each input a distinct repo tag so same-stem nodes from different source graphs don't collapse (#1729). Two graphs under a same-named repo dir (`src/graphify-out` and `frontend/src/graphify-out`, both → `src`) shared the `src::` prefix, so a backend `src/app.js` and a frontend `App.jsx` (both bare `app`) merged into one node with edges from both — false cross-runtime `path` results. Colliding tags are now widened (`frontend_src`) with an index-suffix backstop, and the command prints a note when it disambiguates.
- Fix: `uninstall` removes the graphify hook/section from Claude's local-only files too (#1731, thanks @TPAteeq). It now cleans `.claude/settings.local.json` and both `CLAUDE.local.md` locations in addition to the standard files, via both `graphify uninstall` and `graphify claude uninstall`.
- Feat: `graphify extract --code-only` indexes code (local AST, no API key) and skips the doc/paper/image semantic pass, so a mixed repo no longer hard-fails when no LLM backend is configured (#1734). Reports what it skipped; the no-key error now points users at the flag.

## 0.9.10 (2026-07-08)

- Fix: TS/JS member calls on a builtin-typed receiver no longer collapse onto a same-named user symbol (#1726). `_resolve_typescript_member_calls` matched a receiver's type to a definition by casefolded label, so `x: Date; x.getTime()` bound the caller to a user `class DATE`/`const DATE` in another file — inventing hundreds of phantom `references` edges and a false god node. Builtin-global receiver types (`Date`, `Promise`, `Map`, ...) are now skipped, mirroring the cross-file call guard; genuine user types are unaffected.
- Fix: never bind a cross-file `calls` edge to a definition in a different language family (#1718, thanks @edinaldoof). Name-only matching resolved a TSX callback passed by name to a same-named Kotlin method (and a Python call to a Kotlin fun) — phantom edges the spec forbids. Candidates are now filtered by interop family (JVM, native C-family, JS/TS module graph, ...); unknown families stay permissive.
- Fix: an ambiguous legacy-stem alias in `build_merge` no longer silently merges two unrelated files (#1713, thanks @mallyskies). The `#1504` old-stem alias (`ping.h`/`ping.php` → bare `ping`) resolved by hash-order, riding a dangling edge onto an arbitrary same-named file. Aliases are now committed only when exactly one file claims them; a salted `.h`/`.cpp` file node is recognized as its own claimant so a genuine collision stays ambiguous (and dropped) instead of picking a wrong winner.
- Fix: inline base-class stubs are tagged with `origin_file` (#1707, thanks @mallyskies). Five inheritance handlers built cross-file base-class stubs without `origin_file`, so same-named bases across files collapsed onto one shared stub that could then merge with an unrelated real class (218 wrong `inherits` edges observed). They now route through `ensure_named_node`, which sets the tag.
- Fix: Java enum constants are extracted as nodes with `case_of` edges to their enum (#1719, thanks @ivanzhl). Closes the Java half of #1700; `affected ErrorCode` / "where is ErrorCode.X used" now works for Java.
- Fix: `graphify` rebuilds recover from a deleted hook working directory instead of crashing (#1703, thanks @FranciscoJSBarragan). A detached git hook can inherit a CWD that no longer exists; the rebuild now recovers via `GRAPHIFY_REPO_ROOT` or fails cleanly instead of raising `FileNotFoundError`.
- Feat: the semantic cache is checkpointed per chunk so an interrupted extraction resumes instead of restarting (#1715, thanks @A-Levin). Each completed chunk is unioned into the cache immediately (opt out with `GRAPHIFY_NO_INCREMENTAL_CACHE`); the final write still overwrites authoritatively.
- Docs: `SECURITY.md` no longer claims stdio-only now that an opt-in `--transport http` (binds `127.0.0.1` by default) exists (#1714, thanks @Thizeidler); added tests for `GRAPHIFY_MAX_GRAPH_BYTES` parsing and corrected its unit docstring to binary MiB/GiB (#1722, thanks @Cekaru).

## 0.9.9 (2026-07-07)

- Fix: `graphify explain` resolves an exactly-typed punctuated label symmetrically against `norm_label` (#1704). The search term tokenized on `\w+` ("blockStream.ts" -> "blockstream ts", space where the '.' was) while a node's stored `norm_label` keeps punctuation ("blockstream.ts"). The verbatim case was already rescued by the tokenized-label tier, but that broke if a node's `label` and `norm_label` diverged; a punctuation-preserving `norm_query` is now matched against `norm_label` across the exact/prefix/substring tiers (and fed to the trigram prefilter), so it is robust by construction.
- Fix: code files with no AST extractor are surfaced instead of silently dropped (#1689, thanks for the precise root-cause). `.r`/`.R` (also `.ejs`, `.ets`) are in `CODE_EXTENSIONS` so they are counted as code, but there is no extractor for them, so they produced zero nodes with no warning. `extract` now prints a grouped warning ("N file(s) are classified as code but graphify has no AST extractor ...: .r (17)"). Adding a real `tree-sitter-r` extractor remains a follow-up.
- Fix: the AST-extraction progress line keeps a consistent denominator to the end (#1693). Intermediate lines counted against `len(uncached_work)` but the final line switched to `total_files` (which includes cached hits and no-extractor files), so on a large corpus the count appeared to jump upward right after 99%. Both the parallel and sequential final lines now use the `uncached_work` denominator.
- Fix: `GRAPH_REPORT.md` no longer emits dangling `[[_COMMUNITY_*]]` Obsidian wikilinks by default (#1712). The `_COMMUNITY_*.md` notes those links target are only created by the opt-in `--obsidian` export, and the report is written at build time before any export, so on a default run every link dangled (spawning phantom nodes in a vault's graph view, literal brackets elsewhere). The Community Hubs section now renders as plain text by default; the wikilink form is behind an `obsidian=True` opt-in.
- Fix: `.m` files are no longer force-parsed by the Objective-C grammar when they are MATLAB (#1702, thanks @catalystdream for the diagnosis). `.m` is shared by Objective-C and MATLAB, but the dispatch routed every `.m` to `extract_objc`, which turned real MATLAB into garbage nodes/edges. `.m` is now content-sniffed like `.h`: a genuine Objective-C `.m` (with `@implementation`/`@interface`/`@import`/`#import`) still routes to `extract_objc`; a MATLAB `.m` gets no extractor and is surfaced by the #1689 warning rather than mis-parsed. `.mm` is unchanged (unambiguously Objective-C++). A real `tree-sitter-matlab` extractor remains a follow-up.
- Fix: the `/graphify` usage comment in the skill files no longer claims a bare `/graphify` produces an Obsidian vault by default (#1681, thanks for the audit). It now reads "full pipeline on current directory (HTML viz; add `--obsidian` for a vault)", matching Step 6. Fixed at the skillgen source so every generated `skill-*.md` variant carries the corrected comment.
- Feat: files graphify sees but cannot classify are surfaced instead of vanishing (#1692). Extensionless, non-shebang project files (Dockerfile, Gemfile, Makefile, Rakefile, LICENSE, ...) and unsupported extensions previously left no trace at all. `detect` now collects them into an `unclassified` list, and `graphify extract` reports "N file(s) not classified (no supported extension or shebang), skipped: ...". Actually extracting Dockerfile/Makefile-style content remains a follow-up.

## 0.9.8 (2026-07-06)

- Fix: the Claude Code / Codebuddy `PreToolUse` and Gemini CLI `BeforeTool` graph-nudge hooks now work on Windows (#522). The hooks were inline POSIX bash (`case/esac`, `[ -f ]`, single-quoted `echo`), which Windows cmd.exe/PowerShell cannot parse — so on Windows the hook failed silently, no "run `graphify query` before grepping/reading raw files" context was injected, and users had to invoke `/graphify` by hand. The detection logic (grep-command match, source-file extension match, skip-if-under-output-dir, graph-exists check) moved into a shell-agnostic `graphify hook-guard <search|read>` subcommand invoked via the absolute exe path (the same pattern the codex hook already uses), so the hook parses and runs identically on Windows, macOS, and Linux. Behavior on macOS/Linux is unchanged (byte-identical nudge payload); the graph path now also honors `GRAPHIFY_OUT`. The Gemini `BeforeTool` hook got the same treatment (`graphify hook-guard gemini`), which also removes its dependency on a bare `python` being on PATH. Codex stays a no-op there because Codex Desktop rejects `additionalContext`.
- Fix: `--update`-style section writes to `CLAUDE.md`/`AGENTS.md` no longer corrupt or drop content (#1688, thanks @bdfinst). `_replace_or_append_section` located its managed block by substring (`marker in content`) and `next(... if marker in line)`, so a heading that appeared as a substring of another line (or duplicate headings) matched the wrong offset and the rewrite could truncate the file. It now matches the section heading exactly (`line.strip() == marker`), appends when absent, and prefers the last exact match when several exist, so unrelated content is preserved.
- Fix: token estimation no longer crashes on files containing tiktoken special-token text like `<|endoftext|>` (#1685, thanks @Kyzcreig). `_TOKENIZER.encode(content)` raises `ValueError` by default when the text contains a special token, which aborted packing on docs/corpora that merely mention these strings. Both `encode` sites now pass `disallowed_special=()` so such text is tokenized as ordinary bytes.
- Fix: the Ollama backend no longer multiplies a hang by the retry count (#1686, thanks @Kyzcreig). A stalled local model would wedge for `timeout * (max_retries + 1)`, which with the default 6 retries turned one long stall into a very long one. Ollama now defaults to zero client-side retries (a local model that stalls will not un-stall on retry); set `GRAPHIFY_MAX_RETRIES` to opt back in. Other backends are unchanged. Note: the underlying stall is non-deterministic and driven by the model server, so this bounds the wait rather than eliminating the hang.
- Fix: a truncated or slightly malformed community-labeling reply no longer discards the whole batch (#1690, thanks @vdgbcrypto). `_parse_label_response` now salvages the complete `"id": "name"` pairs from a reply that failed a strict `json.loads` (e.g. a reply truncated mid-object), raising only when no pairs can be recovered. The per-batch token budget was also raised (`256 + 48*n`, was `64 + 24*n`) to give models that prepend a short preamble enough headroom to finish the JSON. The exact provider truncation in the report could not be reproduced without a live key; the parser and budget fixes address the mechanism.
- Fix: cluster-only mode now reports the real token cost of community labeling instead of a hardcoded zero (#1694, thanks @sub4biz). The labeling LLM calls were never accounted for, so `GRAPH_REPORT.md`'s "Token cost" line always read `0 input · 0 output` in cluster-only runs. `_call_llm` now accumulates per-response usage into an optional accumulator that is threaded through the labeling path and surfaced in the report. Backends that do not return usage (the Claude Code CLI) still contribute nothing, which is honest rather than estimated.
- Docs/Feat: `deepseek-v4-flash` (and `v4-pro`) have thinking ENABLED by default; graphify no longer implies otherwise and adds an opt-in `GRAPHIFY_DISABLE_THINKING=1` toggle (#1621, thanks @sub4biz for the empirical testing). Disabling thinking removes a rare reasoning-leak failure mode (which the adaptive extraction/labeling retry already recovers from) but, measured on real corpora, trades it for more frequent benign truncation and measurably lower extraction quality and file coverage — so it stays a documented user choice rather than a forced default. The stale "non-thinking" comment on the built-in deepseek config is corrected. The moonshot (kimi) branch is unchanged (it must disable thinking or content comes back empty).
- Fix: source files are no longer silently dropped during discovery by two over-broad filters (#1666, thanks @krishnateja7 for the precise root-cause). (a) A bare `snapshots/` directory was pruned as a Jest/Vitest artifact, which killed legitimate code namespaces like a Rails `app/services/snapshots/`; it is now pruned only when it actually contains `.snap` files or sits directly under a JS test root (`__snapshots__` stays unconditionally pruned). (b) `_is_sensitive` dropped files on a bare name-keyword hit (`device_token.rb`, `passwords_controller.rb`) even when `classify_file` had already resolved them to source code; a genuine programming-language source file is now exempt from the weak keyword heuristic, while real secret stores in data/config formats (`credentials.json`, `secrets.yaml`, `.env`, `.pem`, ...) are still caught. This is the discovery-layer fix; the 0.9.7 no-cache-on-empty change could not surface these because the files never reached extraction.

## 0.9.7 (2026-07-06)

- Fix: Java standard-library types are no longer emitted as `references` noise (#1603, thanks @NydiaChung). A `_JAVA_BUILTIN_TYPES` skip list now suppresses ubiquitous `java.lang`/`java.util`/`java.io`/`java.time`/`java.math`/`java.nio.file` type names (`String`, `List`, `Map`, `Optional`, `Integer`, `Exception`, ...) at the type-ref walker; they never resolve to a project node, so edges to them were pure noise (mirrors `_GO_PREDECLARED_TYPES`/`_PYTHON_ANNOTATION_NOISE`). Nested user-type generic arguments still resolve: `List<Item>` drops the `List` edge but keeps `Item`.
- Feat: added a `pascal` optional extra for AST-quality Pascal/Delphi extraction (#1616, thanks @vinicius-l-machado). `extract_pascal` already used tree-sitter-pascal when present (with a regex fallback), but the grammar was never declared in the package metadata, so the AST path never ran out of the box. `uv tool install "graphifyy[pascal]"` now opts into it (also included in `[all]`); tree-sitter-pascal ships prebuilt wheels for every platform, so no C toolchain is needed. On a mid-size Delphi codebase the AST path yields notably more accurate `calls`/`inherits` edges than the regex fallback.
- Feat: JS/TS rationale comments and ADR/RFC citations are now extracted (#1599, thanks @niltonmourafilho-arch). Python already turned `# NOTE:`/`# WHY:`/`# HACK:` comments and docstrings into `rationale` nodes, but JS/TS comments were discarded. `extract_js` now runs the same post-pass: `// NOTE:`-style and block-comment rationale become `rationale` nodes with `rationale_for` edges, and `ADR-NNNN` / `RFC NNNN` citations become `doc_ref` nodes with `cites` edges from the file, closing the code-to-design-doc gap in mixed corpora at zero LLM cost (pure line scan). Files with no such comments are unaffected.
- Fix: extensionless executables with a shebang (CLI entry points like `devctl`, `manage`) are now extracted (#1683, thanks @Stashub). `detect` already classified a `#!/usr/bin/env bash`/`python`/`node`/... file as code, but `_get_extractor` dispatched on the suffix alone and returned nothing, so the file was silently dropped from the graph and its doc-referenced symbols stayed dangling stubs. Extensionless files now resolve their extractor from the shebang interpreter (`_SHEBANG_DISPATCH`), mirroring detection. Only interpreters with a real extractor are mapped (python, bash-family, node, ruby, lua, php, julia); others (perl, fish, Rscript) stay skipped rather than mis-parsed by a wrong grammar.
- Feat: Ruby `include`/`extend`/`prepend <Module>` now emits a `mixes_in` edge to the module (#1668, thanks @krishnateja7). Concerns/mixins are the composition mechanism in Rails, but they produced no edges, so the blast radius of editing a shared concern was invisible to `affected`. A constant-argument mixin inside a class or module body now resolves to the module node (reusing the #1634 candidate logic and the #1640 module nodes, under the single-owner guard) and emits `Class --mixes_in--> Module`, which `affected` already traverses. `extend self` and non-constant arguments are skipped; an ambiguous or undefined module produces no edge.
- Feat: `affected <Class>` now reaches callers that bind to the class's method nodes (#1669, thanks @krishnateja7). Since #1634 binds `Service.call` precisely to the `def self.call` method node, a class-level `affected` query missed those callers because `method`/`contains` are (correctly) not general-traversal relations. The reverse walk now seeds from the root's own member nodes (one `method`/`contains` hop outward) so method-bound callers are reachable from the class, with no change to the general traversal (no forward noise) and the member nodes themselves are not reported as hits.
- Fix: capitalized/mixed-case file extensions are no longer silently skipped (#1671, thanks @raman118). `collect_files` and `_get_extractor` matched suffixes case-sensitively, so `App.PY`, `script.JS`, `Lib.Ts`, etc. fell through and were never extracted. Suffix matching now falls back to the lowercased form for both file discovery and extractor dispatch (including `.blade.php`); an unsupported extension like `.xyz` is still skipped.
- Fix: the virtual PostgreSQL `source_file` URI no longer gets backslash-mangled on Windows (#1672, thanks @raman118). `introspect_postgres` built the synthetic `postgresql://host/db` path with `Path`, which rewrites `/` to `\` on Windows; it now uses `PurePosixPath` so the URI stays forward-slashed on every platform.
- Fix: a deferred `import(...)` no longer manufactures a phantom file cycle (#1241, thanks @Synvoya). Dynamic imports are real dependencies but not static ones, so two files that reference each other via one static import plus one dynamic import were reported as a circular dependency. The dynamic-import edge stays in the graph (marked `deferred`) but is excluded from `find_import_cycles`.
- Fix: an extractable source file that produces zero nodes is no longer cached, and is surfaced with a warning (#1666, thanks @krishnateja7). Every supported file yields at least a file node, so a zero-node result is anomalous (a transient batch/parallel hiccup). Caching it made the empty byte-stable across runs and silently blinded `affected`/`explain` to and through the file. The cache write is now skipped for a zero-node result so a rerun self-heals, and `extract` warns when an accepted source file lands in the graph with no nodes. This addresses the persistence and the silent blindness; if the underlying zero-node extraction still reproduces on a specific corpus, the warning now makes it visible to report.
- Fix: the Windows skill variant now declares `name: graphify` instead of `name: graphify-windows` (#1635, thanks @ray8875). `graphify install --platform windows` writes the variant to `~/.claude/skills/graphify/SKILL.md`, but Claude Code requires the skill folder name to equal the frontmatter `name`, so the `-windows` suffix broke discovery/validation. The variant suffix is a packaging detail, not part of the skill's identity.
- Fix: the OpenCode plugin joins its reminder to the user's command with `;` instead of `&&` (#1646, thanks @gonaik). Windows PowerShell 5.1 rejects `&&` as a statement separator (`not a valid statement separator`), so the first bash command of every OpenCode session on Windows failed. `;` works in PowerShell 5.1, Bash, and POSIX shells. (Both the OpenCode and Kilo plugin templates are fixed.)
- Fix: the `GRAPH_REPORT.md` "Import Cycles" section is now emitted only when the graph contains code (#1657, thanks @Ns2384-star). On a documents-only corpus there are no imports, so the section was pure noise ("None detected") on every run; it is now conditioned on code nodes or import edges being present. (The same report also confirms the mojibake and stdout-encoding items in that issue are already addressed on the current branch: manifest.json and `GRAPH_REPORT.md` are written UTF-8, and the CLI reconfigures stdout/stderr to UTF-8 with `errors="replace"`.)
- Fix: a modified `.docx`/`.xlsx` now re-enters `--update` (#1649, thanks @Ns2384-star). `detect_incremental` tracks the converted markdown sidecar, and `convert_office_file` early-returned whenever the sidecar already existed — so an Office source edited after its first conversion never updated its sidecar and was reported "unchanged" forever, freezing the graph on a living docs corpus. The sidecar is now re-converted when the source is newer than it (which bumps the sidecar's mtime/content so the incremental hash check picks it up); an unchanged source still skips the rewrite so it never churns (#1226).
- Fix: files whose absolute path exceeds Windows' 260-char limit are now hashed (#1655, thanks @Ns2384-star). `_md5_file`/`save_manifest`/`count_words` used plain `open()`/`stat()`, which the Windows file APIs reject for long paths unless prefixed with the extended-length marker `\\?\` — so deeply-nested files (accented, deep folders) never hashed, their manifest entry never stabilized, and `detect_incremental` re-flagged them as changed on every run. Change-detection I/O now prefixes long absolute paths on win32 (mirroring the normalization `cache.py` already applied to cache keys). No-op on other platforms.
- Perf: word counts are cached against each file's stat signature (#1656, thanks @Ns2384-star). `detect()` counted words in every PDF/docx/text file to size the corpus, re-opening and re-parsing every binary on each run — minutes on a large docs corpus even when only a few files changed. Counts are now memoized in the existing content-hash stat index (keyed by size + mtime), so an unchanged file is parsed once and read from the index thereafter; incremental detection drops from O(corpus) parsing to O(changed).
- Fix: a JS/TS call with no local definition and no import no longer binds to a same-named export in an unrelated package (#1659, thanks @leonaburime-ucla). When a callee had exactly one same-named definition repo-wide, the cross-file resolver emitted a `calls` edge at INFERRED/0.8 even with no import path between the two files. On a monorepo this fabricated dependencies: a 14-package repo showed `platform` and `sidecar` depending on `registry-protocol` purely because it exported generically-named symbols (`*Schema`, etc.) that unresolved calls collapsed onto. JS/TS modules have no implicit cross-module scope, so a cross-file call is real only if the caller imported it — direct JS/TS cross-file `calls` attribution is now gated on import evidence and left unresolved otherwise. Other languages keep the single-candidate resolution (C/C++ headers, Ruby autoload, same-package implicit scope legitimately call across files without an explicit import), and the `indirect_call` path (already INFERRED and callable-gated) is unchanged. As part of the fix, caller→file mapping for import-evidence now uses the raw call's `source_file` string, so a path-resolution/symlink mismatch can no longer spuriously fail evidence and mislabel a real cross-file call.

## 0.9.6 (2026-07-04)

- Fix: Ruby plain modules and `Struct.new` / `Class.new` / `Data.define` constant assignments now get container nodes (#1640, thanks @krishnateja7). The extractor only created nodes for `class Foo`, so `module Foo` (utility/`module_function` modules), `Foo = Struct.new(...) do ... end`, `Foo = Class.new(StandardError)`, and `Result = Data.define(...)` produced no node at all — their methods hung off the file via `contains` with dot-less labels, and no edge could ever target them. `module` is now a container type (methods attach via `method` like a class, nested modules included), and a constant assignment whose RHS is one of those factories synthesizes a class node named after the constant, attaches block-defined methods to it, and emits an `inherits` edge for `Class.new(Super)`. Plain constant assignments (`MAX = 100`, `X = Foo.new`) are untouched.
- Fix: Ruby constant-receiver singleton calls now resolve cross-file (#1634, thanks @krishnateja7). `Service.call`, `Model.where`, `SomeJob.perform_async` — the dominant Rails idiom — emitted no `calls` edge, so with Zeitwerk autoloading (no `require`s) a Rails app had essentially no cross-file edges and `affected`/`path` came up empty. `resolve_ruby_member_calls` now handles a capitalized (constant) receiver with any callee: it binds to the class's singleton/instance method when one is owned (`def self.call`, which the extractor indexes), else to the class node itself so inherited/dynamic class methods (ActiveRecord `where`/`find_by`) still give correct blast-radius. Namespaced receivers (`Billing::Processor.call`) resolve by the bare class name. The single-owning-class god-node guard is kept throughout — an ambiguous receiver resolves to nothing rather than a wrong edge.
- Fix: Apex `interface X extends A, B` now emits an `extends` edge per parent (#1645, thanks @Synvoya). The interface regex captured the parent list in group 2, but the handler only read the interface name (group 1), so multiple-inheritance parents were dropped and only the `contains` edge survived. The interface branch now iterates the parent list and resolves each the same way the class branch already does.
- Fix: Kotlin interface delegation (`class Foo : Bar by baz`) now emits the `implements` edge (#1644, thanks @Synvoya). The `by` form wraps the delegated interface in an `explicit_delegation` node, so neither the `constructor_invocation` nor the bare `user_type` branch fired and the edge was silently dropped. The delegation-specifier loop now unwraps `explicit_delegation` to its `user_type` (generic-argument recovery still runs), so idiomatic Kotlin delegation shows up in the graph.
- Fix: a malformed semantic chunk no longer crashes `extract` and discards every successful chunk (#1631, thanks @ssazy). When an LLM returned a well-formed object whose `edges` (or `nodes`/`hyperedges`) array carried a stray non-dict entry — a nested list where an edge object belongs — the AST+semantic merge and the semantic-cache write both called `.get()` per entry and raised `AttributeError: 'list' object has no attribute 'get'`. On a 34-chunk run where 33 succeeded, that meant no `graph.json` was written and the cache write failed too, so a re-run re-extracted everything. `_parse_llm_json` now sanitizes each fragment at the single parse chokepoint (keeping only dict entries and coercing a non-list value to `[]`), so the cache writer, the adaptive-retry merge, and the CLI merge are all protected in one place.
- Fix: an unresolved bare npm import no longer aliases onto an unrelated same-named local file (#1638, thanks @EveX1). `import colors from "tailwindcss/colors"` in a `.tsx` file emitted an `imports_from` edge to the bare id `colors`, and build.py's pre-migration alias index (which registers every local file's bare stem) then remapped it onto an unrelated `backend/utils/colors.py` — a confident (`EXTRACTED`) cross-language phantom edge, and one per `.tsx` file sharing the import. In a real monorepo eight unrelated `.tsx` files all landed on a single Python module. Common package subpaths (`colors`, `utils`, `types`, `config`, `client`) collide this way constantly. The external-import fallback now namespaces its target with the `ref` prefix (the same J-4 convention used for tsconfig `extends`/`$ref` externals), so it can never collapse to a local file/symbol id; the ref-namespaced target has no node, so build drops it as an external reference — the correct outcome for a third-party import.
- Fix: `graph.json` node/edge ordering is now stable run-to-run for document/semantic corpora (#1632, thanks @umeshpsatwe). With a parallel LLM backend, `extract_corpus_parallel` merged chunk results in completion order, so which network call happened to return first reordered the nodes and edges even when the model returned identical content — churning `graph.json` between otherwise-identical runs. Chunks are now merged in deterministic submission order after the pool drains (matching the serial path); the progress callback still fires in completion order so long local runs aren't silent. Note: the semantic content the LLM extracts is itself nondeterministic run-to-run — this fix removes the pipeline's own ordering churn, not the model's variance.

- Fix: `graphify export obsidian` no longer crashes in `to_canvas` on a dangling community member (#1236 follow-up, thanks @swells808). The original #1236 fix guarded `to_obsidian` but not `to_canvas`, so a community member id with no backing node in the graph still raised `KeyError` while writing `graph.canvas` — after the notes had exported, leaving a partial mirror. `to_canvas` now applies the same dangling-member filter (`m in G and m in node_filenames`) in both the box-sizing and card-layout loops.

- Feat: TS/JS member calls on a local `new` binding or a type-annotated parameter now resolve (#1630, thanks @DanielC000). `const s = new Svc(); s.doThing()` and a call on a typed param — including inside a returned closure (`(svc: Svc) => () => svc.doThing()`) — now emit `calls` edges to the receiver type's method, so `affected` no longer silently under-reports. Extends the #1316 `this.field` resolver: the per-file type table now also learns local `new` bindings and bare-typed parameters, and `walk_calls` descends into inline/returned closures (attributing their calls to the enclosing function) instead of stopping at the arrow boundary. Resolution keeps the single-definition guard; an untyped or non-bare-typed (array/union/generic) receiver produces no edge.

- Fix: the `query` reference doc's inline vocab/fallback snippets now read and write files with `encoding="utf-8"` (#1619 A2, thanks @edtrackai). On Windows (default cp1252) the bare `read_text()`/`write_text()` calls crashed on exactly the cross-language corpora the doc demonstrates (e.g. Cyrillic labels like `обработчик`). Fixed across all generated skill variants.

- Fix: `graphify update`/`watch` no longer leaves stale sources after a deletion or a destination-only rename (#1623 / #1622, thanks @oleksii-tumanov). When the last supported file was deleted, or a rename reported only its destination in `changed_paths`, the removed source's nodes lingered in `graph.json`. The rebuild now reconciles extractor-backed sources against the files still present (code and document sources, subdirectory roots, legacy markers, symlinks, hyperedges) while preserving semantic and out-of-scope records.
- Fix: `graphify query` guarantees per-term BFS seed diversity (#1596 / #1445, thanks @nokternol). A multi-term natural-language query could collapse to one seed when a single term hit an exact label match on an otherwise-unrelated node (`_EXACT_MATCH_BONUS` outscores substring matches ~1000×), and the 20%-gap seed cutoff then discarded every other term's seeds — so BFS explored only the incidental match's neighborhood. `_pick_seeds` now also seeds the best match for each distinct query term (ties broken by graph degree), so one term's incidental collision can't starve out the others. Partially addresses the seed-hijack in #1602.
- Fix: `extract` no longer crashes during final graph assembly when a node's `source_file` equals the scan root (#1618, thanks @sub4biz). Such a node (e.g. a project-level semantic concept the LLM attributed to the whole repo) relativized to `Path('.')`, and `_file_stem`'s `path.with_suffix("")` raised `ValueError: '.' has an empty name` — crashing *after* all LLM extraction cost was spent and writing no `graph.json` at all. `_file_stem` now returns `""` for a name-less path, and `_semantic_id_remap` skips the root-equal node (it has no per-file identity to remap, so its id is left untouched). Not a 0.9.5 regression — the latent code was hit only when dedup happened to produce a root-`source_file` node.
- Feat: C# receiver-typed member-call resolution (#1609, thanks @JensD-git). `recv.Method()` where `recv` is a typed field, property, parameter, or local now resolves to the receiver *type's* method. C# previously had no member-call resolver, so the bare method name matched any same-named method in the corpus — `_server.Save()` silently mis-bound to an unrelated `Cache.Save()` (a wrong edge, not just a missing one), leaving delegation-heavy call graphs blind across typed boundaries. The receiver is now typed from a per-file field/property/param/local table (incl. `var v = new T()`) and resolved with the single-definition god-node guard; `this.M()` binds to the enclosing class and `Type.M()` to the named type. An untypable receiver (e.g. `dynamic`) or a method absent on the type produces no edge — precision over recall, matching the Swift/C++/Python resolvers.
- Fix: `graphify cluster-only` now writes `.graphify_analysis.json` alongside `graph.json` (#1617 / #1610, thanks @sanmaxdev). Without it, a re-cluster left a stale/absent sidecar and a later `export html` silently reported "Single community". The sidecar now carries communities/cohesion/gods/surprises/questions, matching the full extract path.
- Fix: `.mts` / `.cts` (TypeScript module extensions) are now treated as TypeScript (#1607, thanks @ashmitg). They were missing from the code-extension set and the JS/TS language maps, so `.mts`/`.cts` sources were detected as non-code and silently skipped.
- Fix: four TS/JS extractor gaps (#1615, thanks @papinto). Generator functions (`function*`) now register as callables; `namespace`/`module`/`declare module` containers become queryable nodes; and the TS import-equals form (`import x = require("./m")`) now emits an import edge (its module string nests in an `import_require_clause` the direct-child scan missed).
- Fix: symlinked extraction inputs are contained to the scan root (#1613, thanks @Tok6Flow0). Symlink-directory following is now explicit opt-in, and resolved corpus paths must stay under the scan root before detection, AST collection, and LLM/image reads — an in-corpus symlink pointing outside the selected root is skipped rather than silently indexed. In-root symlinked sub-trees still work.
- Fix: the `claude-cli` backend no longer stalls on an infinite chunk bisection under newer Claude Code CLIs. The extraction schema was delivered via `--system-prompt` with only the raw file dump in the user turn, on the assumption that a replacement system prompt is the model's sole authority. Claude Code >= ~2.1 (verified on 2.1.197) does not honour that: it still layers in the local coding-agent context (CLAUDE.md/AGENTS.md in cwd, skills, MCP) and, given a user turn that is just a file with no request, replies conversationally ("I see the file, but there's no actual request attached — what would you like me to do with it?"). That prose parses to zero nodes/edges, so `_response_is_hollow` flagged it as truncation and the adaptive-retry path bisected the chunk indefinitely (`94 → 47 → 23 → …`), never converging and never writing `graph.json`. The full extraction schema plus an explicit imperative now ride in the user turn and `--system-prompt` is dropped, so the CLI emits the JSON object directly; the `<untrusted_source>` prompt-injection guardrails are carried verbatim and unchanged. Other `_call_claude_cli` behaviour (model override, `--add-dir` image handling, timeout, token accounting) is untouched.

## 0.9.5 (2026-07-02)

- Feat: the MCP server can serve many projects from one process via an optional `project_path` on every tool (#1594, thanks @joanfgarcia). Omit it and nothing changes — the server answers against the graph it was started with. Pass an absolute `project_path` and that call is routed to `<project_path>/<GRAPHIFY_OUT>/graph.json` instead, with its own mtime+size hot-reload, so one stdio/HTTP server backs a whole workspace of repos. Graphs load lazily and cache per resolved path; a missing/corrupt project graph is a tool error, not a process exit, and the server starts even when its default graph is absent. Backward-compatible and additive.
- Fix: Swift singleton cached into a local var now resolves later calls (#1604, thanks @jerryliurui). `let x = NetworkManager.shared` followed by `x.fetchData()` on a subsequent line produced zero call edges — local `let`/`var` bindings inside method bodies weren't typed (only class-level properties and params were), and a static-member init (`Type.shared`, a navigation expression) wasn't recognized even where locals were typed. Method-body locals are now typed from both constructor (`Type()`) and static-member (`Type.shared`) initializers, so `x.method()` resolves to the receiver type via the existing single-definition guard. This singleton-into-local idiom is one of the most common Swift call patterns.
- Fix: the skill's Python-interpreter detection now accepts Homebrew `python@3.x` paths (#1586, thanks @SUDARSHANCHAUDHARI). The shebang allowlist rejected any path with a character outside `[a-zA-Z0-9/_.-]`, but Homebrew installs versioned Python under `python@3.13`, so a valid interpreter containing `@` was skipped and detection fell through to a bare `python3` that lacked graphify (every step then failed with `ModuleNotFoundError`). `@` is now allowed across all skill variants (matching the #473 hooks.py fix); injection characters are still rejected.
- Fix: `graphify merge-graphs` no longer crashes on inputs that disagree on graph type (#1606, thanks @AdrianRusan). Per-repo `graph.json` files don't always share the same `directed` / `multigraph` flags, and `compose` requires one uniform type, so a mixed set raised an unhandled `NetworkXError`. All inputs are now normalized to a plain undirected graph (which the cross-repo merged view already is) before composing.
- Fix: type-reference / inheritance edge gaps closed across seven languages (all thanks @Synvoya):
  - Scala: `var` field declarations now emit type `references` like `val` (#1587).
  - PowerShell: class base types after `:` now emit `inherits` (first) / `implements` (rest), matching the C# convention (#1588).
  - Objective-C: protocol-to-protocol adoption (`@protocol Derived <Base>`) now emits an `implements` edge (#1589).
  - PHP: promoted constructor properties (`__construct(private Repo $r)`) now emit type `references` (method + class field) (#1590).
  - C#: auto-properties (`public Widget Main { get; set; }`) now emit type `references` like fields, including generic args (#1591).
  - C++: base-class template arguments (`class Car : Base<Dep>`) now emit `generic_arg` references, matching the Java behavior (#1592).
  - Swift: enum associated-value types (`case started(Session)`) now emit `references` (#1593).
- Fix: cross-file name resolution now respects case in case-sensitive languages (#1581, thanks @sheik-hiiobd). Resolution matched identifiers case-insensitively for every language, so in Python/Rust/Go/Java/etc. `from pathlib import Path` resolved to an unrelated shell-script `export PATH=...` node — a single variable becoming the corpus's #1 god-node (266 false incoming edges on one real repo), inflating god-node rankings, `affected` blast-radius, and community assignment. Both the cross-file call resolver and the type-reference stub-rewire now match by exact case; only genuinely case-insensitive languages (PHP functions/classes, SQL, Nim) still fold. For case-sensitive languages this only ever removes false edges.
- Fix: Julia qualified / relative / scoped-selected imports now emit edges (#1580, thanks @Synvoya). Only bare `using Foo` was handled; `using Base.Threads` (scoped), `using ..Parent` (relative import_path), and the scoped package of `import Base.Threads: nthreads` were dropped.
- Fix: Rust tuple-struct field types now emit `references` edges (#1582, thanks @Synvoya). `struct Wrapper(Logger, Vec<Config>);` referenced nothing — positional fields nest under `ordered_field_declaration_list` with no `field_declaration` wrapper, the same shape as tuple enum variants (#1579); that path wasn't traversed for structs.
- Fix: SystemVerilog class properties with leading qualifiers now emit field `references` (#1583, thanks @Synvoya). The field regex only matched unqualified `<type> <name>;`, so `rand Config x;` / `protected Base b;` (qualifier + type + name) failed to match and their type references were dropped.
- Fix: Elixir multi-alias brace form now emits imports edges (#1577, thanks @Synvoya). `alias Foo.{Bar, Baz}` produced no imports (the handler only matched a bare single alias); it now expands to one edge per member module. Single `alias`/`import`/`require`/`use` unchanged.
- Fix: Fortran function invocations now emit `calls` edges (#1578, thanks @Synvoya). Only `call sub(...)` (subroutine) calls were captured; `y = f(x)` function calls (a `call_expression`) were dropped. Resolved against procedures defined in the file so array indexing (`arr(i)`, same `name(...)` syntax) can't fabricate a spurious call.
- Fix: Rust enum variant payload types now emit `references` edges (#1579, thanks @Synvoya). `Click(Logger)` / `Resize { size: Dim }` referenced nothing — `enum_item` had no type-reference handler (struct/trait did). Both tuple and struct variant field types now resolve.
- Fix: `graphify cluster-only` no longer reuses stale community labels after the graph changed. When a repo was re-scoped/re-clustered, the saved `.graphify_labels.json` was applied wholesale to the new community set — so a community id that now covered a different community wore the old (LLM) name, silently. cluster-only now writes a per-community membership signature beside the labels and, on reuse, keeps a saved label only for communities whose membership is unchanged; any community that changed (or, for pre-signature label files, when the community count no longer matches) is renamed by its deterministic hub, with a warning to run `graphify label` for fresh LLM names.
- Fix: cross-file `indirect_call` edges were dropped by `graphify extract` on the CLI (a 0.9.4 regression). The callable-target guard for cross-file indirect dispatch was keyed on node ids collected before the id-relativization/disambiguation passes; when the scan root relativizes ids (the CLI's default, `cache_root == project root`), those ids went stale and every cross-file indirect edge was silently dropped — only same-file ones survived. Callable-ness is now read from a node marker that rides through the remaps, so `submit(imported_fn)`, imported dispatch tables, assignment/getattr aliases across files resolve on the CLI as they already did via the `extract()` API.

## 0.9.4 (2026-07-01)

- Fix: Ruby class inheritance now emits an `inherits` edge (#1535, thanks @Synvoya). `class Dog < Animal` produced `contains`/method/call edges but no `inherits` edge — the inheritance handler had branches for Java/Kotlin/C#/Scala/C++/PHP/Swift/Python but none for Ruby, so the `superclass` field was never read. Handles both bare (`< Animal`) and qualified (`< M::Base`) superclasses.
- Fix: Groovy `extends`/`implements` now emit `inherits`/`implements` edges (#1534, thanks @Synvoya). tree-sitter-groovy exposes inheritance through the same grammar shape as tree-sitter-java, but the handler was gated to Java only, so every Groovy inheritance relationship was dropped.
- Fix: corrupt `graph.json` now raises a clear, actionable error instead of a raw traceback (#1537 / #1536, thanks @guyoron1). The three graph-loading paths — `build_merge` (`--update`), `load_graph` (`graphify prs`), and diagnostics (`graphify diagnose`) — wrap `json.loads` and raise a `RuntimeError` with recovery guidance on a truncated/invalid file (incomplete write, power loss, manual edit).
- Fix: cross-chunk node-ID collisions now warn instead of silently dropping a node (#1508 / #1504, thanks @nuthalapativarun). When two nodes share an ID but come from different source files (two same-named files in different directories), dedup keeps the first and now prints a warning naming both files and how to avoid the loss (`graphify extract` per subfolder + `merge-graphs`).
- Fix: git hooks on Windows/MSYS default to sequential rebuilds (#1554, thanks @matiasduartee). Hook-triggered rebuilds now export `GRAPHIFY_MAX_WORKERS=1` on Windows/MSYS (explicit user value still wins), avoiding fragile inherited pipe handles; and the Windows-path hooks guard is a no-op on native Windows, where such paths are legitimate.
- Docs: correct the `deduplicate_by_label` docstring — it is dormant, not auto-called by `build()` (#1514, thanks @TPAteeq). The active dedup path is `deduplicate_entities`; the note that `deduplicate_by_label` runs automatically was never true, and it must not be enabled for code nodes (it merges by label with no file_type guard, conflating same-named symbols across files).
- Feat: deterministic hub community labels, readable without an LLM (#1576, thanks @sheik-hiiobd). When no LLM backend is configured, community labels used to fall back to `Community 70`, making the report and its Suggested Questions unreadable. Each community is now named after its highest-degree member (the structural hub, ties broken by node id for run-to-run stability) — so a plain `graphify` run reads `auth` / `log_action` at zero token cost. A configured LLM naming pass still overrides these with richer names; `--no-label` still yields bare `Community N`.
- Feat: extend `indirect_call` to `getattr(obj, "name")` reflective dispatch (#1575, #1566 slice 3, thanks @sheik-hiiobd). A callable looked up by a string literal — `fn = getattr(obj, "handler")` — now emits an `indirect_call` edge (context `getattr`, INFERRED) so `affected` reaches it. Only a plain string literal resolves; a variable, f-string, or concatenation is dynamic and emits nothing. Unlike the identifier paths, a getattr string names an attribute, not a binding, so it is never shadowed by a param/local — `def via(handler): getattr(x, "handler")` still resolves to the module `handler`. Function and module scope; cross-file handled by the shared resolver. Python only for now.
- Fix: `graphify --update` no longer drops hyperedges from unchanged files (#1574, thanks @socar-tender). `build_merge` read only nodes and edges from the existing `graph.json`, never hyperedges — so every incremental update collapsed the graph's hyperedge set (the semantic domain-flow groupings) down to just the re-extracted files'. Existing hyperedges are now carried forward: re-extracted files' prior hyperedges are replaced by their new version (by `source_file`), deleted files' are pruned, and the rest are preserved with id-dedup — mirroring how `watch` already handled it.
- Fix: `graphify --update` no longer leaves ghost nodes for deleted files when `build_merge` is called without `root` (#1571, thanks @goodjira). Absolute `prune_sources` paths (from `detect_incremental`) never relativized to match the stored relative `source_file` keys, so deleted files' nodes survived the prune. `build_merge` now infers a fallback root when none is passed — the committed `graphify-out/.graphify_root` marker, else the output dir's parent — so pruning (and re-extract replacement) work regardless of the caller. The shipped `--update` runbooks already pass `root`; this hardens the library for any caller that doesn't.
- Feat: extend `indirect_call` to assignment and return references (#1569, #1566 slice 2, thanks @sheik-hiiobd). A function bound to a name (`cb = handler`), returned from a factory (`def make(): return handler`), or aliased at module level (`CALLBACK = handler`) now emits an `indirect_call` edge, so `affected` reaches it. Captures the value side only (a bare name or a bare unpack `a, b = f, g`); a collection literal on the RHS stays with the dispatch-table scan. Reuses the shared guard, so the inverted-shadow trap is handled by construction — a param/local named on the RHS still hits the shadow guard and emits nothing (no return of #1565's false edges). Function and module scope; Python only for now.
- Fix: the skill-version mismatch warning is now direction-aware (#1568, thanks @TPAteeq). It used to advise `Run 'graphify install' to update` on ANY version difference, but `install` writes the package's own bundled skill and re-stamps the version — so when the skill on disk was NEWER than the package (a stale `uv tool` CLI, or a contributor's dev checkout), following that advice silently DOWNGRADED the skill to make the warning go away. Now when the skill is newer, the warning recommends upgrading the package (`uv tool upgrade graphifyy` / `pip install -U graphifyy`) instead; the older-skill case still recommends `install`. Versions compare numerically (so `0.10` > `0.9`).
- Feat: extend `indirect_call` capture to JS/TS (#1566). The same model now applies to JavaScript and TypeScript: a callback passed by name (`arr.map(fn)`, `setTimeout(fn)`, Express-style `app.get("/", handler)`, event wiring `emitter.on("e", handler)`) and functions listed in object/array dispatch tables (`const ROUTES = { create: handler }`, `const HOOKS = [onStart, onStop]`). Arrow-const functions (`const cb = () => {}`) count as callable targets; object shorthand (`{ handler }`) is a reference; inline arrows/function expressions are direct definitions and are not captured; object KEYS and non-callable values are excluded. Same guards as Python: callable-target-only, not shadowed by a param/local/module reassignment, single-definition god-node guard cross-file. Cross-file resolution is import-aware — a `import { onEvent }` edge to the symbol no longer suppresses the `indirect_call` to it. Module-level call-argument registration (idiomatic in JS) is captured in addition to the function-scoped capture Python has.
- Feat: extend `indirect_call` to dispatch tables (#1566). A function listed as a VALUE in a dict/list/set/tuple literal — a route/handler registry like `ROUTES = {"create": create_user, "delete": delete_user}` or `HOOKS = [on_start, on_stop]` — now emits an `indirect_call` edge so `affected` reaches those handlers too. Works at module level (attributed to the file) and inside a function (attributed to the function), same-file and cross-file. Same guards as the call-argument case: callable-target-only, not shadowed by a param/local/module-level reassignment, dict KEYS excluded (only values are references).
- Feat: capture indirect dispatch as `indirect_call` edges so `graphify affected` (blast radius) catches callers that pass a function by name as a call argument — `executor.submit(fn)`, `Thread(target=fn)`, `map(fn, xs)`, callbacks (#1565, thanks @sheik-hiiobd). Kept as a distinct INFERRED relation separate from `calls` (strict call-graph queries stay precise) and added to the affected relation set. Hardened against false edges: the argument name must resolve to a callable definition and must NOT be shadowed by a parameter or local binding in the enclosing function — so the idiomatic `def via(pool, handler): pool.submit(handler)` (handler is the param) and a data variable sharing a function's name produce no edge. Now also resolves cross-file: a callback imported from another module (`from .handlers import on_event; pool.submit(on_event)`) routes through the same cross-file resolver as direct calls — single-definition god-node guard, callable-target-only, staying INFERRED — closing the gap where #1565 saw only same-file callbacks (the common real-world shape is cross-module). Python only for now.

## 0.9.3 (2026-06-30)

- Feat: cross-file member-call resolution for C++ and Objective-C (#1547, #1556). A class declared in a header and defined in its `.cpp`/`.m` no longer fragments into two nodes (a decl/def merge pass collapses the sibling header/impl pair, gated to same-directory same-name so unrelated classes never merge), and a member call now resolves across files by the receiver's inferred type: C++ `Foo f; f.bar()` / `Foo::bar()` / `this->bar()` and ObjC `Foo *f = [[Foo alloc] init]; [f doThing]` / `[self render]` link to the owning class's method. Resolution is by receiver type, never bare name, with the single-definition god-node guard — an uninferable or ambiguous receiver produces no edge (high precision over recall, grounded in how compiler-free indexers like ctags/Doxygen mis-resolve by name). Also routes C++ headers to the C++ extractor and ObjC `#import` bridging headers to the ObjC extractor. Reported by @c0dezer019 and @JabberYQ. (Residual cross-file `#include` edge resolution under symlinked roots and ObjC dynamic-dispatch receivers remain follow-ups.)
- Feat: namespace-aware C# cross-file type resolution (#1562, thanks @TheFedaikin). The namespace is folded into the C# node id (so same-named types in different namespaces stay distinct), `using` directives are honored with lexical per-block scope, and qualified references (`Namespace.Type`, `using` aliases) resolve — disambiguating a bare reference to the one in-scope namespace that provides it, and refusing (no edge) when ambiguous. Advances the #1318 shadow-node umbrella for C#.
- Fix: test mocks no longer erase the real cross-file call graph (#1553, thanks @Schweinehund). When a bare callee name had 2+ definitions without unique import evidence, the god-node guard dropped the edge entirely — so a single same-named test mock wiped the real call graph (a 76-stub Pester suite erased everything). The guard now applies tie-breakers — non-test preference (a shared, segment-aware path classifier) then path proximity — and resolves only when exactly one candidate survives, else still bails. A real def plus a test mock resolves to the real def; two genuine non-test defs still bail (no fan-out).
- Fix: hyperedge member lists keyed `members` or `node_ids` are now accepted, not silently dropped (#1561, thanks @askalot-io). Normalized to the canonical `nodes` at ingest (in build_from_json and semantic_cleanup), deduped, with a warning — mirroring the existing from/to edge-endpoint aliasing.
- Feat: work-memory overlay — `graphify reflect` now projects the verdicts it distills (preferred / tentative / contested, recency-weighted) into a `.graphify_learning.json` sidecar next to graph.json, and `graphify explain` / `query` / `GRAPH_REPORT.md` / the HTML viewer surface them where you look (a `Lesson:` hint, a colored node ring). Builds on the idea in #1441/#1542 (thanks @TPAteeq), implemented as a sidecar rather than stamping graph.json: structural truth stays separate (no `learning_*` in graph.json or GraphML exports, no rebuild churn). Each verdict carries the source questions that produced it (provenance) and a content fingerprint of the cited code, so a verdict on a file that has changed since is flagged "code changed — re-verify" instead of shown as still-authoritative. Dead-ends stay query-scoped (a report section, never a node attribute). Letting verdicts influence query traversal is deliberately deferred (it needs propensity correction + exploration to avoid a self-reinforcing feedback loop).
- Feat: type-aware `this.field.method()` resolution for TypeScript/JS (#1316, thanks @guyoron1). A member call through a constructor-injected dependency (`constructor(private db: Database)` then `this.db.query()`) now produces a `calls` edge to the field type's method, resolved by the field's declared type and gated by the single-definition god-node guard (an ambiguous or untyped field produces no edge — no global name-match fan-out). EXTRACTED confidence; constructor parameter-property injection scope.
- Feat: resolve TypeScript wildcard path aliases (#1544, thanks @oleksii-tumanov). A `compilerOptions.paths` pattern like `@app/*` or `@*/interfaces` now captures the matched segment and substitutes it into each target in order, honoring tsc's longest-prefix / exact-wins specificity, baseUrl, and the first-existing-target fallback. Extends the #1531 resolver.
- Feat: resolve JS namespace re-export bindings (#1552, thanks @oleksii-tumanov). `export * as ns from './mod'` now creates a real symbol node for `ns`, registers it as a named export (so a downstream `import { ns }` resolves to it), and emits a file-level `re_exports` edge — treated as a single opaque binding, so `ns.member` accesses don't fan out into false per-symbol edges. Includes cycle and deep-chain guards.
- Feat: Objective-C dot-syntax property accesses and `@selector()` call edges (#1475, #1543, thanks @guyoron1). `self.product.name` now emits an `accesses` edge and `@selector(method)` a `calls` edge, each resolved only to an unambiguous in-scope definition by exact method-id match (a sibling of the same class for dot-syntax; exactly one method by exact selector name for `@selector`) — so `self.name` can't mis-resolve to a `-surname` sibling and same-named methods across classes don't fan out. Completes the #1475 ObjC follow-ups.

## 0.9.2 (2026-06-29)

- Feat: type-aware Ruby member-call resolution (#1499, thanks @vamsipavanmahesh). `p.run` is now resolved by the inferred type of the receiver (`p = Processor.new` ⇒ `Processor#run`) instead of by globally-unique method name, so the edge survives name collisions (an unrelated `Worker#run` no longer makes it ambiguous) and never points at the wrong method. Introduces a small resolver-registry framework that the existing Swift (#1356) and Python (#1446) cross-file passes register into. Receiver types are inferred only from unambiguous local `var = ClassName.new` bindings; a call whose receiver type can't be proven resolves to nothing rather than to a guess — a deliberate precision-over-recall change for Ruby member calls.
- Feat: resolve workspace imports through the package's `exports` map (#1308, thanks @guyoron1). A subpath import like `import { x } from "@scope/pkg/browser"` now resolves through the package.json `exports` map (string values, condition objects, nested conditions, and `./*` wildcard patterns) instead of falling back to a bare path string, falling back to the existing bare-path/index resolution when there's no exports map or no match. `default` is consulted last (Node's catch-all), and an export target that escapes the package directory is rejected.
- Fix: import edges silently dropped on codebases using tsconfig path aliases or workspace packages (#1529), a regression from the 0.9.0 full-repo-relative node-ID change. Relative imports resolve to repo-relative paths and matched fine, but alias (`@/lib/utils`) and workspace imports resolve to absolute paths, so the import-target ID baked in the on-disk prefix and no longer matched the repo-relative definition node — the edge was dropped at build (common on Next.js/SvelteKit). The id-remap post-pass now also registers the absolute-resolved form, so alias/workspace import targets land on the real node again.
- Fix: tsconfig `compilerOptions.paths` fallback targets are now honored (#1531, thanks @oleksii-tumanov). A `paths` value is an ordered list (`"@app/*": ["src/app/*", "lib/app/*"]`) that `tsc` tries in turn; graphify kept only the first entry, so an import whose file lived at a later target was dropped or misresolved. Each target is now tried in order and the first that resolves to a real file wins (no false edge when none exist).
- Fix: the semantic (LLM) extraction cache is now pruned (#1527, thanks @mwolter805). The AST cache was version-swept but the content-hash-keyed semantic cache had no cleanup, so every content change or file deletion left an orphan entry and `graphify-out/cache/semantic/` grew unbounded. Orphan entries are now removed at the end of `extract`, computed against the full live document set (not the incremental changed subset, which would have evicted still-valid entries) and only touching `cache/semantic/`; the cache stays unversioned so releases never re-bill LLM extraction.
- Fix: three Objective-C extractor bugs (#1475, thanks @JabberYQ for the detailed report and test repo). (1) `.h` headers using `NS_ASSUME_NONNULL_BEGIN` before `@interface` produced no class node — tree-sitter-objc can't expand the argument-less macro and fails to emit a `class_interface` node at all, so the macro is now blanked (offset-preserving) before parsing. (2) Quoted `#import "X.h"` edges dangled once a `.h`/`.m` pair existed (the bare-stem target was salted away during id-disambiguation); imports now resolve to the real header file node, fixing the equivalent latent C `#include` bug too. (3) `[[Foo alloc] init]` now emits a `references` edge to the allocated class, resolved only to an unambiguous class (no false edges). Dot-syntax property accesses and `@selector(...)` target-action edges remain follow-ups.
- Fix: Swift type-qualified static calls now resolve as EXTRACTED rather than INFERRED (#1533, thanks @JabberYQ). `SessionType.staticMethod()` / `Singleton.shared.method()` name the receiver type explicitly in source, so the resolved edge is an exact reference, matching the Python qualified-class-method pass; instance calls typed via local inference (`obj.method()`) stay INFERRED.
- Fix: enforce the API timeout in the secondary LLM dispatch path (#1442, thanks @DhruvTilva). `_call_llm` (used by the dedup LLM tiebreaker) built its Anthropic/OpenAI clients without `timeout`, so requests there ignored `GRAPHIFY_API_TIMEOUT` and could hang — it now passes the timeout like the primary extraction paths.
- Fix: `to_graphml` no longer raises `ValueError` on a node/edge with a `None` attribute value — null fields are coerced to `""` before writing (#1502, thanks @antonioscarinci).
- Feat: `graphify save-result` accepts `--answer-file` as an alternative to `--answer`, so a long or multi-line answer can be read from a file instead of an inline shell argument (#1502, thanks @antonioscarinci).
- Fix: generated install/skill guidance is now host-generic (#1530, thanks @ari-mitophane). The wording no longer tells agents to invoke a literal `skill` tool with `skill: "graphify"` (host-specific and invalid in many environments); it now points to the installed graphify skill or instructions.
- Security: bump `msgpack` to 1.2.1 (GHSA-6v7p-g79w-8964) and `pydantic-settings` to 2.14.2 (GHSA-4xgf-cpjx-pc3j), and drop the unused `safety` dev dependency, which only pulled in `nltk` (an unpatched HIGH advisory). All transitive; the two HIGH-severity ones were dev-tooling only and never in the published wheel. `pip-audit` (already run in CI) continues to provide dependency-CVE scanning.

## 0.9.1 (2026-06-28)

- Fix: rate-limited (HTTP 429) extraction chunks are now retried instead of dropped (#1523, thanks @bercedev). The provider SDKs back off and honor `Retry-After`, but the SDK default of 2 retries was too low for strict per-org concurrency/RPM caps (e.g. Moonshot/kimi), so a parallel `extract` 429'd, each chunk logged `chunk N failed`, and was silently lost (incomplete graph + console spam). The OpenAI-compatible, Azure, and Anthropic clients are now built with a higher `max_retries` (default 6, override via `GRAPHIFY_MAX_RETRIES`). For very tight accounts, `--max-concurrency 1` further reduces the concurrency that triggers org-level limits.

- Fix: `graphify update` now prunes the edges a re-extracted file no longer produces (#1521, thanks @UltronOfSpace). Old edges were preserved by endpoint-node membership alone, so a deleted import's edge survived forever as long as both endpoints still existed — driving phantom circular-dependency findings (and `--force` didn't help). Edges owned by a re-extracted file (`source_file`) are dropped before merging the fresh extraction; cross-file edges that merely point at the file are untouched.
- Fix: residual node-ID collisions after the 0.9.0 full-path change (#1522, thanks @sub4biz). `normalize_id` collapses every separator to `_`, so distinct paths that differ only by a separator-vs-punctuation swap (`foo/bar_baz.py` vs `foo_bar/baz.py`) still merged. Colliders are now salted with a short stable path hash so they stay distinct; non-colliding IDs are byte-identical to 0.9.0 (no re-migration).
- Fix: Java record component types now emit `references` edges (#1519, thanks @oleksii-tumanov) — a record's data dependencies (`record Order(Payload p, List<Item> items, …)`) were invisible; primitives and the record's own type parameters are skipped.
- Fix: same-label cross-file imported-type stubs now stay distinct in the six dedicated extractors too — Julia, Fortran, Go, Rust, PowerShell, ObjC (#1515, thanks @TPAteeq). The #1462 disambiguation previously only covered the generic extractor, so e.g. two Go files importing the same `ext.Widget` collapsed into one conflated node; they're now kept distinct (while `source_file` stays empty so the #1402 rewire onto a real definition is unchanged).
- Fix: Java type parameters no longer emit spurious `references` edges (#1518, thanks @oleksii-tumanov). The generic-parent support (#1511) created a stray edge/stub for the bare `T` in `class Box<T> extends Container<T>`; the extractor now collects in-scope type-parameter names (class/interface/record/method/constructor, incl. bounded/multiple) and skips them, while keeping every real type and the `inherits`/`implements` edge to the base.
- Fix: the internal `origin_file` disambiguation field (#1462) is no longer serialized into graph.json, where it had shipped (in 0.9.0) as an absolute, machine-specific path — it is dropped once the colliding-id pass consumes it, keeping output portable (#1516, thanks @TPAteeq; cf. #555, #932). `_origin` stays (the incremental watcher needs it, #1116).

## 0.9.0 (2026-06-28)

- **Breaking — node IDs now include the full repo-relative path** (#1504, #1509). The node-ID stem was the immediate parent dir + filename, so same-named files in different directories collided into one last-writer-wins node and silently dropped graph content (`docs/v1/api/README.md` and `docs/v2/api/README.md` both → `api_readme`). The stem is now the full repo-relative path (`docs_v1_api_readme` vs `docs_v2_api_readme`); top-level files are unchanged (`setup.py` → `setup`). The AST extractor, the LLM system prompt, the extraction-spec, and the two hand-copied stem helpers are all aligned to this one rule (fixing the #1509 AST↔LLM divergence that produced ghost duplicates), and `build_from_json` deterministically re-keys any cached/older semantic fragment onto the new IDs from its `source_file` so the unversioned semantic cache survives without ghosts or a re-bill. **Existing graphs migrate to the new ID format automatically on the next `build`/`update`** (no re-bill). Note: same-named files in different directories that previously collided into one node are only *recovered as distinct nodes* by a fresh extraction — run `graphify extract --force` to rebuild and gain them (migrating an already-collided graph/cache can't resurrect the nodes that were already dropped). If you push to a persisted **Neo4j** store, re-import after upgrading (re-exported IDs change); saved Gephi/yEd (GraphML) layouts go stale; MCP/cypher consumers should query by label rather than persisting node IDs across rebuilds.
- Feat: `--timing` flag on `graphify extract` and `graphify cluster-only` prints per-stage wall-clock timings to stderr (#1490). Shows how long each pipeline stage takes — `extract`: detect → AST → semantic → build → cluster → analyze → export; `cluster-only`: load → cluster → analyze → label → report → export — plus a final total, so slow stages are visible on large corpora. Off by default (monotonic `perf_counter`, stderr-only); machine-read stdout / `graph.json` are unchanged.

## 0.8.51 (2026-06-28)

- Fix: the Obsidian export (`--obsidian` / `to_obsidian`) no longer overwrites a user's own notes or `.obsidian/` config when pointed at an existing vault (#1506). It wrote one note per node straight into the target dir and unconditionally replaced `.obsidian/graph.json`, so `--obsidian-dir ~/my-vault` could clobber a same-named note (`Database.md`) and the user's graph-view settings — silently, no backup. graphify now records the files it owns in a `.graphify_obsidian_manifest.json` and refuses to overwrite any pre-existing file it didn't create (skipping it with one aggregated warning); a re-run still updates graphify's own notes. The default `graphify-out/obsidian` output is unchanged.
- Fix: Java enum and annotation (`@interface`) declarations are now emitted as type nodes (#1512, thanks @oleksii-tumanov), so a field typed as an enum or a class annotated with a project annotation resolves to a real node instead of a dangling reference.
- Fix: Java generic parent relationships are no longer dropped (#1510, thanks @oleksii-tumanov) — `class Foo extends Bar<T>` / `implements List<T>` now emit the `inherits`/`implements` edge to the base type, with the type arguments as `generic_arg` references.
- Fix: the `claude-cli` backend no longer crashes with `UnicodeDecodeError` on Windows systems where `claude.cmd` emits GBK/cp936 bytes (#1505, thanks @nuthalapativarun) — both subprocess calls decode with `errors="replace"`.
- Fix: `graphify explain` and `graphify affected` now resolve a query given as a source-file path even when the graph has multiple nodes from that file (#1503, thanks @behavio1). A path like `app/api/route.ts` tokenized to terms that matched no node, so explain returned "No node matching"; source-file paths are now indexed and matched exactly, and when several nodes share the file the lookup prefers the file-level node (the `L1` node whose name matches the file). Trailing-separator handling is aligned between the two commands.
- Docs: clearer install/PATH guidance for `uv tool install graphifyy` on macOS (#1471, thanks @Patsch36). Two expected uv behaviors read as bugs: (1) after `uv tool install`, the `graphify` command lands in uv's tool bin dir (`~/.local/bin`), which a fresh macOS/zsh shell often doesn't have on `PATH` — the README now points to `uv tool update-shell` instead of implying uv always wires `PATH`; (2) `uvx graphify …` / `uv tool run graphify …` resolve the first word as a *package* and fail, because the package is `graphifyy` and `graphify` is only its console script — the docs now show `uvx --from graphifyy graphify install`. README install note + Troubleshooting only; no code change.
- Fix: imported type stubs with the same label no longer falsely merge across files when there is no project definition to rewire onto (#1462, thanks @jiangyq9). Two files that both `from pathlib import Path` and use `Path` as a type previously collapsed into one node; the referencing file is now kept as an internal disambiguator (`origin_file`) used only when splitting colliding ids, while `source_file` stays empty so a real project definition can still be rewired onto (the #1402 path is unaffected).
- Feat: resolve C# cross-file type references and extract `enum`/`struct`/`record` declarations (#1466, thanks @TheFedaikin). A new `_resolve_csharp_type_references` (the C# counterpart to the Java resolver) re-points dangling `inherits`/`implements`/`references` edges from no-source "shadow" stubs to their real definitions, disambiguating same-named types in different namespaces via the referencing file's `using` directives and enclosing namespace; ambiguous matches are refused rather than guessed. `enum`/`struct`/`record` types are now extracted as definitions so those references resolve too. Advances #1318 for C#.
- Fix: the Go AST extractor no longer creates phantom duplicate nodes for cross-file type references — the Go copy of `ensure_named_node` still used the older sourced-stub fallback; it now emits a sourceless stub like the other extractors, extending the #1402 fix to Go (#1500, thanks @TPAteeq).
- Fix: cross-file references to a same-named type now stay distinct across the six dedicated AST extractors (Go, Rust, Julia, Fortran, PowerShell, ObjC) instead of conflating into one shared node — #1462's `origin_file` stub-disambiguation had only been applied to the generic extractor; it now covers all seven.

## 0.8.50 (2026-06-27)

- Feat: `graphify label --missing-only` relabels only communities that are unnamed or still hold a `Community N` placeholder, preserving existing non-placeholder labels from `.graphify_labels.json` (#1481, thanks @jiangyq9; supersedes #1421 by @matiasduartee, who proposed the same flag). Lets a large graph be relabeled incrementally without re-naming (and paying for) communities that already have good names.
- Feat: index Metal (`.metal`) shader files — Metal Shading Language is C++14, so `.metal` is classified as code and routed through the existing C++ extractor, mirroring the CUDA `.cu`/`.cuh` reuse (#1480, thanks @jiangyq9; supersedes #1450 by @GoodOlClint). Also adds `.cu`/`.cuh`/`.metal` to the cross-language edge-filter family map (they were missing), so phantom cross-language `calls` edges between these and C++ are correctly suppressed.
- Fix: pass `stream: False` explicitly on OpenAI-compatible chat-completion calls (#1223, thanks @jiangyq9). Some gateways default to SSE streaming when `stream` is omitted, but graphify always reads the result as a single response, so the call failed against those gateways. Applied to both the extraction dispatch path and the `--dedup-llm` tiebreaker path.
- Fix: emit `references` edges for Java field types (#1485) and for type-level annotations on Java classes/interfaces/records (#1487, both thanks @oleksii-tumanov). Field types (including the `generic_arg` element of `List<Handler>`) and class annotations (`@Service`, `@Entity`) were missing from the graph even though parameter/return types and method annotations were already captured; primitives are still skipped.
- Fix: the Objective-C extractor was silently dropping most code-level relationships (#1475, thanks @JabberYQ for the detailed report). Five fixes: (1) ObjC `.h` headers were parsed by the C extractor (1 node, 0 edges, losing every `@interface`/`@protocol`/`@property`/method) — a `.h` is now routed to the ObjC extractor when it contains an ObjC-only directive (`@interface`/`@protocol`/`@implementation`/`@import`), which never hijacks a real C/C++ header; (2) `[receiver selector]` calls produced no `calls` edges at all because the method-body pass looked for `selector`/`keyword_argument_list` nodes, but the grammar tags selector parts with the field name `method` (type `identifier`) — the selector is now read from the `method` fields, skipping the receiver, which also makes compound sends like `[self a:x b:y]` resolve; (3) generic property types (`NSArray<Product *> *`) were invisible because the type was wrapped in a `generic_specifier` — the element and container types are now both referenced; (4) class methods (`+foo`) were mislabeled `-foo`; (5) `@import Foundation;` now produces an `imports` edge. Property/dot-syntax `accesses` and `@selector(...)` target-action edges remain follow-ups.
- Feat: link WPF/XAML views to their ViewModels and extract richer binding references (#1473, thanks @MikeKatsoulakis). Builds on the initial XAML support (#1460). Resolves a view to its ViewModel from an explicit `<Window.DataContext><vm:MainViewModel/>`, a design-time `d:DataContext="{d:DesignInstance Type=…}"`, the `View`→`ViewModel` naming convention, or Prism `ViewModelLocator.AutoWireViewModel="True"` — always against an actually-extracted C# class, so a name with no matching class (or an ambiguous one) emits no edge (explicit DataContext is EXTRACTED, conventions are INFERRED). Also extracts binding paths (`{Binding User.Name}`, `Path=Order.Total`), commands (`Command="{Binding SaveCommand}"`), converters, and CommunityToolkit `[ObservableProperty]`/`[RelayCommand]` generated members. The event-handler resolution stays gated on the .NET handler signature (no spurious event edges), and ViewModel discovery is bounded to the extraction root.
- Fix: `.vue` Single File Components now extract their `<script>` with the right grammar (#1468, thanks @papinto). `.vue` was dispatched to `extract_js`, which selects a tree-sitter grammar by suffix; `.vue` is neither `.ts` nor `.tsx`, so the whole SFC — `<template>` markup, `<script>`, and `<style>` — was parsed as JavaScript, producing a top-level ERROR node and recovering no imports, symbols, or type references. A dedicated `extract_vue` now masks everything outside `<script>` (replacing it with spaces so line numbers stay accurate) and parses just the script with the grammar named by `lang` (`ts` default, `tsx`/`js`/`jsx` honored). The open-tag scan tolerates `>` inside quoted attributes, so Vue 3.3+ generic components (`generic="T extends Record<string, unknown>"`) parse correctly.
- Fix: `graphify reflect --if-stale` now also checks the `.graphify_analysis.json` and `.graphify_labels.json` sidecars (and any custom `--analysis`/`--labels` paths) when deciding whether `LESSONS.md` is up to date (#1470, thanks @oleksii-tumanov). It previously only stat'd the memory docs and `graph.json`, so lessons could stay stale after community analysis or labels changed without the graph changing. A missing sidecar is treated as not-an-input, so no-cluster builds are unaffected.
- Fix: the `Read|Glob` PreToolUse hook (the "run graphify first" nudge installed for Claude Code and CodeBuddy) now matches the file's real trailing extension instead of substring-scanning the path (#1463, thanks @marketechniks). The old check asked `any(ext in path)`, which had two opposite failures: `.json` files (`package.json`, `tsconfig.json`) spuriously fired because `.js` is a substring of `.json`, and `.astro`/`.vue`/`.svelte` never fired because they weren't in the set — so on Astro/Vue/Svelte projects, where those are the primary source type, reads and globs never surfaced the graph. The hook now compares the segment after the last `/` then after the last `.` against the extension set (with `.astro`/`.vue`/`.svelte` added), so `package.json` stays silent, `data.geojson` stays silent, `**/*.astro` fires, and an extension sitting on a directory component (`my.ts/file`) correctly doesn't. The `graphify-out/` suppression and fail-open behavior are unchanged.
- Fix: make it unambiguous in the skill that graphify needs no API key, so terminal-style hosts stop looping on a missing one (#1461). Hermes (and the other AGENTS.md hosts: Codex, Aider, OpenClaw, Droid, Trae, …) run the `graphify` CLI directly and don't dispatch subagents, but the Step 3 extraction guidance framed the no-key path only as "fall through to subagent dispatch" — so on `/graphify .` those agents would spin for minutes insisting they needed an API key before eventually proceeding. Step 3 now opens with an explicit, hoisted "graphify needs no API key — never ask the user for one, never block on one" statement (code is AST-only; a code-only corpus skips semantic extraction entirely), and the fallback now spells out a non-subagent path for terminal hosts instead of assuming subagent dispatch. Applied across every generated skill body, including the aider/devin monoliths, with a regression test that pins the wording in place.
- Feat: extract WPF/XAML structure from `.xaml` files (#1460, thanks @MikeKatsoulakis). No new parser dependency (stdlib XML, with the same DOCTYPE/ENTITY and size guards as the `.csproj` extractor). Captures the root element, named controls (`x:Name`/`Name`) and their control types, `{Binding ...}` references, and `x:Class`, and bridges the view to its `.xaml.cs` code-behind by resolving event-handler attributes to the matching methods on the partial class. Event resolution is gated on the .NET handler signature `(object sender, …EventArgs e)` and skips free-form attributes (`Content`, `Text`, `Tag`, …), so a property value that merely matches a method name (e.g. `Content="Save"` next to a business method `Save()`) can't fabricate a spurious event edge.
- Fix: `to_canvas` (Obsidian Canvas export) now lays out each community's node cards in the same `ceil(sqrt(n))`-column grid the group box is sized for. The box width assumed a roughly-square `sqrt(n)`-column layout, but the placement loop hardcoded 3 columns, so any community larger than ~9 members rendered as a cramped 3-wide strip in an over-wide, mostly-empty box. The column count is now computed once per community and reused for the box width, box height, and card placement, so the cards fill the box. Cosmetic, no data change (#1452, thanks @TPAteeq).
- Fix: `to_obsidian` / `to_canvas` / `to_wiki` no longer silently overwrite notes whose labels differ only by case (e.g. a class `References` and a prose heading `references`). The filename dedup was keyed on the exact-case name, so two such labels counted as non-colliding and the second write clobbered the first on case-insensitive filesystems (macOS/APFS, Windows/NTFS) — no suffix, no warning. Dedup now folds case (keyed on the lowercased name) while still emitting the original-case filename, so any pair that would collide on disk gets a numeric suffix. The obsidian/canvas dedup is shared in one helper so they can't drift, `wiki`'s slug dedup gets the matching fix, the `_COMMUNITY_*.md` overview notes (which had no dedup) are covered, and a generated `base_1` is itself re-checked so it can't overwrite a node literally labelled `base_1` (#1453, thanks @TPAteeq).
- Feat: the `kimi`, `gemini`, and `deepseek` semantic-extraction backends now honor `KIMI_BASE_URL`, `GEMINI_BASE_URL`, and `DEEPSEEK_BASE_URL` to point at any OpenAI-compatible endpoint (a proxy, gateway, or self-hosted relay), matching the existing `OLLAMA_BASE_URL` / `OPENAI_BASE_URL` overrides. Each falls back to its hardcoded official default when the variable is unset, so behavior is unchanged for everyone who doesn't set it (#1458, thanks @jc2shile).
- Fix: `to_wiki` (Wikipedia-style wiki export) now emits portable relative markdown links instead of Obsidian `[[wikilinks]]`, so navigation works in every renderer — VS Code preview, GitHub, GitLab, a plain browser — not just Obsidian. Two defects: (1) `[[Title]]` resolves by note title only inside Obsidian; everywhere else `[[Domain Data Models]]` points at a literal `Domain Data Models.md`, but the article file is `Domain_Data_Models.md` (the slug substitutes spaces and reserved characters), so nearly every community/god-node navigation link opened an empty page. (2) God-node articles linked every neighbor (`[[AwsHelper.py]]`, `[[.read_object_key()]]`), but only communities and god nodes get article files, so those node-level links were dead even inside Obsidian. Links are now standard `[display](slug.md)` with the target URL-encoded, so spaces, `&`, parentheses, and `#` survive intact in CommonMark renderers and Obsidian alike; any link whose target has no article is downgraded to plain text instead of left dangling. Each article's slug is computed up front (a `label -> slug` resolver built before any body is rendered) so a link to a community or god-node article points at the real on-disk filename, including the case-fold collision suffix (`parser_2.md`). Cosmetic, no graph/data change (#1444, thanks @restagner).

## 0.8.49 (2026-06-24)

- Fix: the `get_community` MCP tool now shows the community name in its header (`Community 12 — Auth & Sessions (8 nodes)`), matching `get_node` and the query-traversal output, which already read the `community_name` attribute `to_json` writes onto every node. `get_community` was the only graph tool still returning a bare numeric id. The name is read from the community's member nodes (they share it), sanitised like every other LLM-derived field, and skipped when it is just the `Community N` placeholder so the header never doubles to `Community 12 — Community 12` (#1448, thanks @rmart1308).
- Security: floor `starlette` at `>=1.3.1` to pick up the fixes for CVE-2026-48818 and CVE-2026-54283 (both resolved by 1.3.1). starlette underpins the HTTP MCP transport (`graphify-mcp` over HTTP / `serve_http`); the stdio transport and CLI are unaffected. It was an undeclared transitive dependency (via `mcp`) that `graphify/serve.py` imports directly, so it is now declared in the `mcp` (and `all`) extras and floored, which protects end users installing `graphifyy[mcp]`, not just the locked dev/CI environment. Lockfile bumped 1.0.0 -> 1.3.1; serve/MCP/HTTP tests pass on the new version (#1391, #1396, thanks @orbisai0security).
- Refactor: begin splitting the monolithic `extract.py` into per-language modules under `graphify/extractors/` (#1212). The `blade`, `elixir`, `razor`, and `zig` extractors plus the shared primitives (`_make_id`, `_file_stem`, `_read_text`, `_LANGUAGE_BUILTIN_GLOBALS`) move into their own files, with `graphify/extractors/base.py` holding the shared pieces and a strict one-way import direction (`extract.py` -> `extractors/`, never the reverse). `extract.py` re-exports the moved names, so every `from graphify.extract import ...` caller and the dispatch table are unchanged. Behavior-neutral lift-and-shift (verified byte-identical), groundwork for moving the remaining languages out. See `graphify/extractors/MIGRATION.md`.
- Feat: community labeling can now run in parallel (#1390). `graphify cluster-only` and `graphify label` accept `--max-concurrency N` (default 4) to fan labeling batches out across a thread pool, and `--batch-size N` (default 100) to tune communities per LLM call. A large graph that previously needed hundreds of sequential calls now runs them in rounds. Mirrors the existing `extract` parallelism, including the safety guards: `ollama` and `claude-cli` are forced serial (set `GRAPHIFY_OLLAMA_PARALLEL=1` / `GRAPHIFY_CLAUDE_CLI_PARALLEL=1` to override). Output is unchanged and deterministic regardless of concurrency, since results are keyed by community id and merged on the main thread.
- Fix: `graphify reflect` no longer duplicates lines in the "known dead ends" and "corrections" sections when the same Q&A is saved more than once. Those lists were appended per memory doc with no key (node scoring already dedups by node, but these two did not); they now collapse by question, keeping the most recent entry — so a re-corrected question shows its latest correction. Output stays deterministic (ordered by date then question).
- Fix: the work-memory loop no longer depends on the git hook. The skill now tells the agent to run `graphify reflect --if-stale` itself at the start of graph work (cheap, deterministic, a no-op when no outcomes have been saved), then read `LESSONS.md`. Previously a skill-only install (without `graphify hook install`) would keep recording outcomes via `save-result` but never regenerate `LESSONS.md`, so the lessons never surfaced. The post-commit hook is now an optimization for between-session freshness rather than a requirement. The new `--if-stale` flag skips the run when `LESSONS.md` is already newer than every input (the memory docs and the graph), so when the hook just refreshed it the agent's session-start run costs almost nothing.

## 0.8.47 (2026-06-24)

- Feat: the work-memory loop is now zero-config for agents (#1441). The skill's query reference instructs the agent to read `graphify-out/reflections/LESSONS.md` at the start of graph work (start from preferred sources, skip known dead ends) and to record an `--outcome useful|dead_end|corrected` on `save-result`; the git post-commit/post-checkout hooks now auto-run `reflect` after each rebuild — best-effort and only when saved outcomes exist — so `LESSONS.md` stays current without a manual `graphify reflect`.
- Feat: a first deterministic slice of self-improving "work memory" (#1441). `graphify save-result` gains optional `--outcome useful|dead_end|corrected` and `--correction TEXT` flags that record how a saved Q&A turned out — written to the memory doc's frontmatter and an `## Outcome` body section so the signal both stays machine-readable and round-trips into the graph on the next semantic re-extraction. A new `graphify reflect` command then scans `graphify-out/memory/` and writes a deterministic `graphify-out/reflections/LESSONS.md` an agent can load at the start of the next session — grouped by community when a `graph.json` is present, flat otherwise. Source nodes are scored, not counted: each citation is a signed, time-decayed value (`useful` positive, `dead_end`/`corrected` negative, configurable half-life via `--half-life-days`, default 30), so a fresh dead end outweighs a months-old useful. A node is only promoted to "preferred" once corroborated by ≥`--min-corroboration` distinct results (default 2) — one save can't mint a trusted lesson; the rest render as "tentative", and nodes with both positive and negative signals render once as "contested" with a recency-wins verdict. Source nodes are matched to the graph by label or id, and citations whose node no longer exists are dropped so stale lessons don't linger. Deterministic, no LLM; bare `graphify save-result` and all existing behavior are unchanged.
- Fix: `graphify update` now prunes a function/symbol removed from a still-present file without needing `--force`. The build already dropped the stale node (#1116), but the shrink-guard then refused to write the smaller graph ("new graph has N nodes but existing has M … Refusing to overwrite"), so the deletion silently never persisted unless you passed `--force` — leaving stale nodes (and the work-memory node-existence gate) lagging until a forced rebuild. The guard is now file-aware: a net shrink is allowed when every lost node belongs to a file re-extracted this run (or deleted), and still refused when a node disappears from a file that was *not* touched (the failed/partial-extraction case it exists to catch).
- Fix: `validate_extraction` and `build_from_json` no longer crash on a non-hashable node `id` or edge `source`/`target` (e.g. a list emitted by a malformed LLM extraction) — previously a single bad node raised `TypeError: unhashable type` and aborted the entire build of an otherwise-complete corpus. The validator now reports the bad id/endpoint as an error string (its documented contract), and the build skips the malformed entry with a stderr warning while keeping every well-formed node/edge; non-dict nodes are still left to raise so shape diagnostics are unchanged (#1447, thanks @dschwartzi).
- Fix: Python qualified class-method calls (`ClassName.method(...)`) now produce an EXTRACTED `calls` edge to the class-qualified method node (#1446). Previously these cross-class static/qualified calls were dropped: the shared cross-file pass skips all member calls (the #543/#1219 god-node guard against bare `obj.method()` collisions), and when the called method shared its name with an in-file node — e.g. a viewset action `approve()` delegating to a service `Service.approve()` — the bare-name lookup matched the caller's own node and silently dropped it. The Python extractor now captures a simple-identifier receiver, defers capitalized-receiver member calls to a new receiver-based resolver (`_resolve_python_member_calls`, mirroring the Swift pass), and emits the edge only when the receiver resolves to exactly one class that owns the method (single-definition god-node guard); instance/module calls (`self.x()`, `obj.x()`, lowercase receivers) are unaffected.
- Feat: new first-class `agents` platform installs the skill to the generic cross-framework Agent-Skills locations. `graphify install --platform agents` (alias `--platform skills`) writes the spec's user-global `~/.agents/skills/graphify/SKILL.md` — the directory `npx skills` and spec-compliant frameworks read — and `--project` writes `./.agents/skills/graphify/SKILL.md`; `graphify uninstall` removes them. Previously that user-global location was only reachable as an accidental side effect of the gemini-on-Windows branch. The skill bundle re-homes amp's agents-md body (registered in `tools/skillgen/platforms.toml`, rendered through the skillgen drift/coverage guards); the body is identical to amp's, and only the on-demand hooks reference differs — it points at `graphify agents install`, which (as the amp-twin subcommand) wires the skill plus an AGENTS.md always-on section. Bare `graphify install` is unchanged — still single-platform (claude/windows) (#1432, closes #1405).

## 0.8.46 (2026-06-23)

- Perf: graph queries on large graphs are faster via a trigram candidate prefilter in the MCP/CLI query path. A trigram→node index (built once per graph and rebuilt on hot-reload) narrows the candidate set before the IDF-weighted scorer runs, cutting the previous O(N) scan. The prefilter is a strict superset of the exhaustive scorer (it indexes `norm_label`, `label_tokens`, `nid`, and `source_file`), so results and ranking are unchanged; short/CJK queries and low-selectivity terms fall back to the full scan (#1431; thanks @papinto).
- Feat: the skill runbook adds a Step 4.5 graph-health gate that runs `diagnose_extraction` and surfaces dangling/self-loop/collapsed-edge warnings before labeling, and anchors the semantic cache on the scan root (`root='INPUT_PATH'`) so cache hits survive a non-cwd scan. Read-only — never aborts the build (#1437; thanks @bahcgscateringsa-design).
- Fix: `graphify install --platform hermes` now installs to the right directory on Windows. Hermes scans `%LOCALAPPDATA%\hermes\skills`, but the installer always used the POSIX `~/.hermes/skills` (so on Windows the skill was never discovered). `_platform_skill_destination` gained a hermes branch that targets `%LOCALAPPDATA%\hermes\skills` on Windows and keeps `~/.hermes/skills` elsewhere (#1403).
- Fix: cross-file type-annotation references no longer create phantom duplicate nodes. A class defined once but referenced via type annotations in N other files (`def f(x: Thing) -> Thing`) produced 1+N nodes — the extra ones with the referencing file's path baked into the id (`pkg_a_py_thing`). `ensure_named_node` minted a *sourced* stub for these cross-file refs, which `_disambiguate_colliding_node_ids` then collided into per-file ids and `_rewire_unique_stub_nodes` refused to collapse. The fallback now emits a *sourceless* stub (like the inheritance-base path), so the references resolve to the single canonical definition. Fixed uniformly across all six language extractors that share the helper (#1402).
- Feat: CUDA (`.cu`/`.cuh`) source files are now extracted. CUDA is a C++ superset, so these files route through the existing C++ (`tree-sitter-cpp`) extractor — no new grammar dependency. `__global__`/`__device__` kernels, host functions, structs and `#include`s are captured, host call edges are inferred, and `<<<grid, block>>>` kernel-launch syntax parses without error. Detection and file-watching follow automatically since both derive their extension sets from the dispatch table / `CODE_EXTENSIONS` (#1411).
- Fix: `to_obsidian` / `to_canvas` no longer emit punctuation-only filenames (e.g. `@.md` from a `@/*` tsconfig `paths` key). Such a file is valid on disk but empty once a downstream tool re-slugs on word characters (it crashes `qmd update`), so an all-punctuation label now falls back to `unnamed` (#1409; thanks @Mylock51).
- Fix: the opencode plugin's search reminder no longer contains backticks. The hook prepends the reminder inside a double-quoted `echo`, where bash performed command substitution on the backticks — silently running `graphify query "<question>"` on every search. The reminder is now plain text (#1413; thanks @WSHAPER).
- Fix: `graphify extract --cargo` exits with a clear error instead of a traceback when `Cargo.toml` is missing or unreadable (the introspection now also catches `OSError`) (#1428; thanks @DhruvTilva).
- Chore: resolve an `F821` (undefined `nx`) flagged in `prs.py` by importing `networkx` under `TYPE_CHECKING` for the quoted type annotation (#1429; thanks @DhruvTilva).

## 0.8.45 (2026-06-22)

- Fix: native-backend semantic extraction now produces hyperedges. The `graphify extract --backend <gemini|claude|claude-cli|openai|kimi|…>` prompt (`llm._EXTRACTION_SYSTEM`) only ever showed `"hyperedges":[]` in its output schema and never explained what a hyperedge is, so every native backend silently emitted zero — while the agent/skill path (whose `extraction-spec.md` fully documents hyperedges) produced them. The two prompts had drifted. The native prompt now carries the same "3 or more nodes participate together" instruction and a populated schema example, so both extraction paths yield the same hyperedge behaviour for a given corpus. Verified end-to-end: a doc that previously produced 0 hyperedges now produces one (correctly relativized, per #1418). Guard tests assert the two prompts can't drift apart again.
- Fix: `GRAPHIFY_OUT` is now honoured end-to-end. The override (a custom output-dir name or absolute path, for worktrees/shared setups — #686) was only respected by some readers; `graphify extract` and several commands hardcoded `graphify-out/`, so a `GRAPHIFY_OUT=custom-out graphify extract` still wrote to `graphify-out/`, and downstream `query`/`serve`/`update` looked in the wrong place. The output-dir name is now resolved through `graphify.paths` everywhere it matters: the `extract` write dir, `cluster-only`/`label`, `query`/`affected`/`benchmark` defaults, `save-result --memory-dir`, `uninstall --purge`, `cache-check`, the `manifest.json`/`transcripts`/`memory`/`converted` paths in `detect`/`transcribe`, the `build_merge`/`serve`/`benchmark`/`prs` graph-path defaults, and the `detect` scan-exclude (so a renamed output dir is never re-ingested as source). Default behaviour is unchanged — without the env var everything still uses `graphify-out/` (#1423).
- Fix: the `GRAPH_REPORT.md` header now shows the actual scan root instead of a literal `.`. The split-skill runbook passed `'.'` as the `root` argument to `report.generate` in Steps 4 and 5, so a `/graphify /some/path` run produced a report titled `# Graph Report - .`. It now passes `'INPUT_PATH'` (matching the monoliths, which were already correct). Display-only — no path written to `graph.json`/`manifest.json` was affected (#1419).
- Fix: the skill runbooks now write a portable `manifest.json`. Step 9 (full build) and the `--update` reference called `save_manifest(...)` without `root=`, so manifest keys were stored as absolute paths; cloning or moving the repo then broke `graphify --update` — every cached file missed and the whole corpus re-extracted. All four runbook call sites (the lean-core `skill.md`, the Aider/Devin monoliths, and the shared `--update` reference) now pass `root='INPUT_PATH'`, relativizing keys to the scan root to match the native `graphify update` path. The monolith change is registered as a new sanctioned change-class in the round-trip guard (#1417).
- Fix: hyperedge `source_file` is now relativized to the scan root like nodes and edges. `build_from_json(root=...)` relativized `source_file` on `nodes[]` and `links[]`, but stored `graph.hyperedges[]` verbatim, so a semantic subagent's absolute path (e.g. `/Users/.../CLAUDE.md`) leaked into `graph.json`. The fix lives in `build_from_json` (not `to_json`, which has no `root` to relativize against) and mirrors the existing node/edge handling (#1418).
- Fix: the `GRAPHIFY_OUT` override is now honoured everywhere instead of a hardcoded `"graphify-out"` literal. The name is consolidated into a single `graphify.paths` module (was duplicated across `__main__`, `cache`, and `watch`); `security.validate_graph_path`'s `base=None` discovery + fallback, `callflow_html`'s project-root resolution, and the post-commit/post-checkout hook bodies (which now read the env var at hook-run time) all use it. Previously a renamed output dir validated against the wrong base or made the hook miss `.graphify_root` (#1423).
- Fix: the Aider and Devin monolith skills now carry the #1392 runbook fixes that the split skill got in 0.8.44. These single-file skills are hand-maintained and frozen against a pinned pristine-v8 blob by a round-trip guard, so they had been excluded. The guard is now a multiset diff that classifies every added/removed line against documented sanctioned change-classes (rather than a positional zip that forbade any line-count change), which lets the multi-line fixes land while still failing on any unsanctioned drift. Both monoliths now propagate `directed=IS_DIRECTED` into every `build_from_json` call (a `--directed` run no longer collapses reciprocal edges), scope semantic extraction to document/paper/image (code is covered by the AST pass), delete `.graphify_cached.json` on a cache miss, and run Step 4's zero-node guard before any write with the report/analysis gated on `to_json` actually persisting the graph (#1392).

## 0.8.44 (2026-06-19)

- Fix: generated Claude/agent skill, crash & data-loss bugs in the runbooks (#1392). (1) Semantic chunk files were written under the **scanned dir** (`.graphify_root`) but the merge globs **cwd** `graphify-out/`, so a non-cwd scan produced "no nodes"; chunk paths are now derived from cwd. (2) Code-only corpora skipped Part B but Part C reads `.graphify_semantic.json` unconditionally, raising `FileNotFoundError`; the fast path now writes an empty semantic file first. (3) `--cluster-only` told the agent to re-run Steps 5-9, which read intermediate files a prior cleanup deleted (`FileNotFoundError`); it now relies on the self-contained `graphify cluster-only` CLI. (4) Step 4's zero-node guard ran *after* `GRAPH_REPORT.md`/`graph.json`/analysis were written, and `GRAPH_REPORT.md` was written before `to_json`'s #479 shrink-guard; the guard now runs before any write and the report/analysis are written only when `to_json` actually persisted the graph.
- Fix: generated Claude/agent skill, remaining correctness bugs in the runbooks (#1392). `--directed` is now propagated as `directed=IS_DIRECTED` into `build_from_json` (Step 4 + Step 5 rebuild) and `build_merge` (the `--update` merge + diff), so a `--directed` (and `--directed --update`) run no longer silently rebuilds undirected and collapses reciprocal A<->B edges. Semantic extraction flattens only `document`/`paper`/`image` (code is already covered structurally by the AST pass) so subagents stop re-reading every source file. `.graphify_cached.json` is deleted on a cache miss so Part C never merges a stale cache from a prior run. `--update` now transcribes changed video files and moves the transcripts into documents before the semantic pipeline. Transcription writes via `write_text` (no shell redirect), honours `GRAPHIFY_WHISPER_MODEL`/`GRAPHIFY_WHISPER_PROMPT`, and prints status to stderr. `add-watch` and `exports` use the resolved interpreter explicitly, and the MCP Desktop config documents the absolute interpreter path. Extraction-spec example id is namespaced; query term split keeps tokens of 3+ chars.
- Fix: the semantic extract entry points no longer crash on `FileSlice` units. The 0.8.43 `#1386` fix coerced every item with `[Path(f) for f in files]`, which raised `TypeError` on the `FileSlice` objects produced by the oversized-text slicing path (#1369), so a corpus containing a document large enough to be sliced crashed on extract. Items are now coerced only when they are not already a `Path` or `FileSlice` (#1397, #1399).

## 0.8.43 (2026-06-19)

- Feat: package manifests are now parsed deterministically into a dependency graph. `apm.yml`, `pyproject.toml`, `go.mod`, and `pom.xml` each yield ONE canonical package node per package (keyed by name) plus `depends_on` edges, routed to the AST path so the LLM never sees them. Previously `apm.yml` was an LLM-handled document, so the same package got a different file-anchored id from its own manifest than from each dependent's dependency reference and split into duplicate nodes; a package referenced from N manifests is now a single hub node (#1377).
- Feat: markdown links now become graph edges. `extract_markdown` only emitted heading nodes + `contains` edges and never parsed link syntax, so a doc full of `[text](./other.md)` links (e.g. `index.md`, `table-of-contents.md`) had no edges to what it links and never became a hub. Inline links, reference-style links, and `[[wikilinks]]` are resolved relative to the source file (external URLs / in-page anchors / images skipped) and emitted as `references` edges, with targets resolved via the same node-id recipe so they merge onto the real doc node (#1376).
- Security: bumped vulnerable dependencies to patched versions — `pypdf` 6.11.0→6.13.3 (CVE-2026-48155/48156), `yt-dlp` 2026.3.17→2026.6.9, `pyjwt` 2.12.1→2.13.0, `cryptography` 48.0.0→49.0.0, `python-multipart` 0.0.28→0.0.32 — with lower-bound floors for the direct deps (`pypdf`, `yt-dlp`) so installs get the patched versions (#1375; thanks @hypnwtykvmpr).
- Fix: the semantic extract entry points (`extract_corpus_parallel`, `extract_files_direct`) crashed with `AttributeError` when passed `str` paths instead of `pathlib.Path`. Both now coerce `files = [Path(f) for f in files]` at entry (#1386).
- Fix: community labeling now recovers from a malformed-JSON batch by splitting it at the midpoint and retrying each half (mirroring the extract path), instead of logging-and-skipping it — which silently lost ~100 community names per failed batch on large graphs (#1280, #1278; thanks @CJdev232).
- Fix: `graphify hook install` no longer creates a literal backslash-named junk directory and reports false success when `core.hooksPath` (or `git rev-parse --git-path hooks`) is a Windows-style path under WSL. Drive-letter / embedded-backslash hooks paths are now rejected with a clear error (#1385).
- Refactor: node-ID normalization is unified into a single `graphify.ids` module. `extract._make_id`, `build._normalize_id`, `mcp_ingest._make_id`, and `symbol_resolution._bash_make_id` were four hand-synced copies of the same NFKC/casefold recipe — the root of the recurring ghost-node bug class (#811/#550/#1033/#1104). All four now delegate to one implementation guarded by contract + hypothesis property tests (#1378; thanks @danielnguyenfinhub).

## 0.8.42 (2026-06-18)

- Fix: large text documents are no longer silently truncated during semantic extraction. `_read_files` capped every file at 20,000 characters, so a Markdown/text/rST document longer than that had everything past the cap dropped — the model never saw it, and the packer/adaptive-retry path couldn't recover ("packing can't shrink one big file"). Oversized splittable-text files are now sliced at heading/paragraph boundaries into units that each fit the cap and together cover the whole file; every slice reports its parent file as `source_file`, so the graph is not fragmented per-slice. A single slice that still overflows the model's output is bisected and retried. Code files and PDFs are never sliced (they keep whole-symbol / page handling). (#1369)
- Fix: `/graphify --update` no longer deletes a changed file's freshly re-extracted nodes. The `0.8.41` `root=` fix (#1361) made `build_merge`'s prune actually match relative `source_file` values — which then matched the just-re-extracted nodes of *changed* files (still listed in `prune_sources`) and removed them, so an `--update` on a changed file could wipe its nodes. The update runbook now prunes only genuinely **deleted** files; changed files are reconciled by `build_merge`'s replace-on-re-extract (#1344). The full build also now passes `root=` to `build_from_json`, and the extraction-spec `source_file` is pinned to the verbatim path, so the full build and incremental updates never drift on node-key base. (#1366; thanks @RelywOo)
- Fix: Java `record` declarations are now modeled as first-class type nodes (they share `class_declaration`'s name/body/interfaces fields), and `new Foo(...)` constructor calls now produce a `calls` edge to the constructed type. Previously a record appeared only as its file node (degree 0) with no incoming edges, and body-level `new` usages were dropped because `object_creation_expression` wasn't a recognized call type and its callee lives in the `type` field rather than `name`. (#1373)
- Security fix: `.graphifyignore` and `.gitignore` are now **merged** per directory instead of `.graphifyignore` silently replacing that directory's `.gitignore`. Previously, adding a `.graphifyignore` (e.g. to exclude media) disabled the dir's `.gitignore` entirely, so a file excluded only by `.gitignore` — including neutrally-named secrets like `prod-dump.sql` or `customer-data.json` that the sensitive-file heuristic doesn't catch — got indexed into the graph, whose artifacts embed file contents and are routinely committed. `.gitignore` is read first and `.graphifyignore` last, so `.graphifyignore` patterns (including `!` negations) still win on conflict; adding one can only ever exclude more, never re-include a `.gitignore`-excluded file. (#1363)

## 0.8.41 (2026-06-17)

- Fix: OpenAI-compatible backends (`ollama`, `openai`, `deepseek`, `kimi`) now honour their configured `16384` output-token cap instead of silently falling back to `8192`. The dispatch read a `max_completion_tokens` config key that only `gemini` defines; the others set `max_tokens`, so their advertised cap was dead and deep-mode JSON truncated mid-string (recovered by the adaptive bisect, but noisy and slower). The dispatch now reads either key, and the `openai` config gained an explicit cap. `GRAPHIFY_MAX_OUTPUT_TOKENS` still overrides. (#1365)
- Fix: fuzzy dedup no longer over-merges distinct nodes in three cases. (1) Numbered/versioned siblings whose embedded digit runs differ as zero-padding-insensitive multisets (`ADR 0011` vs `ADR 0013`, `3.1 Product Goals` vs `1.1 Product Goals`, `40%+ …` vs `<20% …`) never merge. (2) `rationale`/`document` nodes are file-anchored like code (#1205's reasoning): near-identical docstring/heading boilerplate in parallel files no longer collapses across files, while same-file duplicates still merge. (3) Cross-file labels that share a long prefix but diverge in a distinguishing token (`testing-library jest-native` vs `react-native`) are scored on plain Jaro instead of Jaro-Winkler, so the leading-prefix bonus can no longer fabricate a merge; genuine cross-file duplicates still clear the bar on Jaro alone, and same-file near-duplicates keep Jaro-Winkler. Guards are mirrored into the `--dedup-llm` ambiguous-pair collection. (#1284 thanks @van4oza, #1243)
- Fix: Swift cross-file class relationships expressed through member calls and constructors now resolve to the receiver's real definition. A per-file type table (built from property/parameter declarations and constructor inference) types the receiver of `recv.method()` / `Type.staticMethod()` / `Singleton.shared.method()` / `self.prop.method()`, and property/field initializers (`let vm = VM()`) are now walked for constructor calls. Edges are emitted only when the receiver's type resolves to exactly one definition (preserving the #543/#1219 god-node guards) and are tagged `INFERRED`; the blanket member-call skip in the shared call pass is untouched (#1356).
- Fix: `/graphify <path> --update` now prunes stale nodes correctly. The update runbook called `build_merge(prune_sources=...)` without `root=`, so the absolute prune paths were never relativized to match the graph's relative `source_file` values — nothing was pruned and changed/deleted files left ghost nodes that compounded on every incremental run. The shared skill fragment now passes `root` (the native `graphify update` CLI was already correct) (#1361).
- Fix: `export obsidian` no longer writes an empty 32-byte `graph.canvas` on a populated graph. `to_canvas` built cards solely by iterating communities, so a graph with no community data (`--no-cluster` builds, or a missing analysis sidecar) produced the empty `{"nodes": [], "edges": []}` shell while the markdown notes rendered fine. It now falls back to one synthetic community covering every node (#1324).
- Fix: edges missing a `source_file` field (occasionally emitted by the semantic/LLM extractor, which `build` only normalized when the field was already present) are now backfilled from the edge's endpoint nodes in `build_from_json` and the `--no-cluster` raw-write path, so they no longer reach `graph.json` without a file reference or trip validation (#1279).
- Fix: every platform's query skill now ships **both** the vocab/IDF query-expansion step and the inline NetworkX fallback. Previously the two capabilities were split across `cli.md` / `cli-inline.md` so no platform got both — Claude had the superior expansion but no CLI-down fallback, while all other platforms had the fallback but the weaker raw-question matcher. The two fragments are merged into one unified `query` reference (and stub) shipped to all hosts; the `query_variant` enum and its coverage-audit exemption are removed (#1325; thanks @LeanderBlume).
- Fix: cross-file Java `implements`/`inherits`/`imports` edges no longer orphan onto bare "shadow" nodes when two packages define a same-named type. The referencing file's `import` statement now disambiguates by exact package (FQN) and re-points the edge to the real definition, dropping the orphan stub. Previously `_rewire_unique_stub_nodes` could only repair the globally-unique case, so same-named interfaces (common in large Java codebases — `Handler`, `Service`, interface+impl pairs) left the real definition isolated in its own community (#1318).
- Fix: Swift imports of the same module from multiple files now collapse to a single shared `type=module` node instead of N path-qualified duplicates. The import target is tagged `type=module` and exempted from id-disambiguation, so reverse traversal ("what imports CoreKit?") works; the `--no-cluster` writer also now dedupes nodes by id (and edges) to match the clustered `build_from_json` path. Builds on the v0.8.40 Swift-import fix (#1327, #1330; thanks @duncan-daydream).

## 0.8.40 (2026-06-16)

- Feat: custom OpenAI- and Anthropic-compatible endpoints via `OPENAI_BASE_URL`/`OPENAI_MODEL` and `ANTHROPIC_BASE_URL`/`ANTHROPIC_MODEL`. Point either backend at a self-hosted or proxy server (vLLM, llama.cpp, LM Studio, LiteLLM, gateways); defaults still resolve to `api.openai.com` / `api.anthropic.com`, and `GRAPHIFY_OPENAI_MODEL` keeps precedence over `OPENAI_MODEL`. Wired through both the extraction path (`_call_claude`) and community labeling (#1273).
- Feat: PowerShell `.psm1` modules are now indexed. `.psm1` was absent from `CODE_EXTENSIONS` and the extractor dispatch table, so modules — and their dependents — were silently missing from the graph; they parse cleanly with the existing PowerShell grammar (#1315). (`.psd1` manifests and `Import-Module` / dot-source import edges remain a follow-up.)
- Fix: Swift `import` edges are no longer silently dropped. `_import_swift` emitted an edge to a bare module id with no backing node, so `build.py` pruned 100% of Swift imports. The target module node is now synthesized (new opt-in `LanguageConfig.synthesize_import_module_nodes`) so the edge survives the build (#1327).
- Fix: `--no-cluster` and incremental `graphify update` no longer accumulate duplicate edges. These paths bypass the NetworkX `DiGraph` that collapses parallel edges, so repeated `update` grew the edge count every run and counts diverged across build modes. Edges are now deduped by `(source, target, relation)` before writing — deterministic and idempotent; the no-cluster rebuild log now reports the written (deduped) edge count instead of the raw pre-merge count (#1317).
- Perf: `save_manifest` file hashing parallelized with a `ThreadPoolExecutor` (#1295).
- Perf: `_walk_js_tree` converted from a recursive generator to an iterative walk, reducing overhead on large JS/TS trees (#1294).

- Feat: JS/TS AST now extracts function symbols defined via `this.X = () => {}` / `this.X = function(){}` (constructor-assigned methods), `exports.X = fn` / `module.exports.X = fn`, `Foo.prototype.X = fn`, class arrow/function fields (`class C { onClick = (e) => {} }`), and `const f = function(){}` function expressions. Previously only top-level `function` declarations, top-level `const x = () =>` arrows, classes, and method shorthand were captured, so the majority of callable symbols in constructor-style and CommonJS codebases (DAOs, route handlers, services) never became nodes and could not be call-edge endpoints. Arbitrary `obj.x = fn` is deliberately not captured, preserving the #1077 phantom-god-node guard (#1322).
- Fix: `graphify query`, `graphify explain`, and MCP `query_graph`/`get_node` now show the human-readable community name (e.g. "FlashAttention Paper") instead of a blank or numeric ID after running `cluster-only`. `to_json` now accepts `community_labels` and embeds `community_name` on each node; read paths fall back to the numeric `community` field for backward compatibility with old graphs (#1305).
- Fix: `graphify-mcp` and `python -m graphify.serve` now accept `--graph <path>` as an alias for the positional argument, consistent with every other graphify subcommand. Previously `--graph` raised "unrecognized arguments" (#1304).

- CI: bandit (MEDIUM+ severity) and pip-audit security scans added as a non-blocking `security-scan` job. Both run with `continue-on-error: true` so they never break CI — advisory signal only, with the intent to remove the gate once pre-existing findings are triaged.
- Docs: RFC for file-level node summaries added (`docs/node-summaries-rfc.md`). Proposes inline `graph.json` attribute vs sidecar storage options with pros/cons, phased implementation plan, and open questions for maintainer decision.

- Fix: AST extraction no longer crashes on Windows machines with >61 logical cores. `ProcessPoolExecutor` on Windows is hard-capped at 61 workers via `WaitForMultipleObjects`; the clamp now applies to all three input paths (auto-compute, `GRAPHIFY_MAX_WORKERS`, `--max-workers`) (#1298).
- Fix: ghost-merge skips ambiguous `(basename, label)` collisions where two AST nodes share the same key. When same-named symbols appear in same-named files across different directories (e.g. two `render()` in two `index.ts`), the previous last-writer-wins produced an arbitrary canonical node and mis-pointed all edges. Ambiguous keys are now tracked and skipped (#1257).
- Fix: startup no longer crashes on unreadable `.graphify_version` files. On restricted-permission installs or network mounts, `.exists()` / `.read_text()` raised `PermissionError` and crashed every `graphify query/explain/path` call. All three FS probes now wrapped in `try/except OSError: return` (#1299).
- Fix: `prs.py` claude-cli backend resolves `claude.cmd` on Windows. The `_call_llm` and `_call_claude_cli` extraction paths were already fixed; `prs.py` had the same bare `["claude", ...]` subprocess call that fails on Windows npm installs with WinError 2 (#1288).

## 0.8.39 (2026-06-12)

- Perf: O(n²)→O(n) LSH neighbor lookup in `deduplicate_entities`. The inner scan `next(n for n in candidates if n["id"]==neighbor_id)` was O(n) per neighbor; replaced with a `candidates_by_id` dict built once per pass. Also adds a `norm_cache` to avoid re-normalising labels on every comparison.
- Fix: `graphify merge-chunks` summary now prints the node count instead of the raw list object. `global_graph.py` printed `merged['nodes']` (the list) instead of `len(merged['nodes'])`.
- Fix: manifest data-loss on corrupt `~/.graphify/manifest.json`. A parse error previously triggered `except Exception: pass`, silently returning an empty manifest and overwriting the file — wiping all tracked repos. The corrupt file is now renamed to a timestamped `.corrupt.<ts>` backup with a stderr warning before starting fresh.
- Fix: tree-sitter grammar packages now have pinned upper-bound version ranges in `pyproject.toml`. Grammar packages routinely break node-type and field APIs across minor bumps; ceilings prevent silent breakage on future upgrades.
- Feat: FalkorDB export backend. `graphify export falkordb --push redis://localhost:6379` pushes the graph to a FalkorDB instance. Optional dep (`uv tool install "graphifyy[falkordb]"`); lazy import; idempotent (MERGE semantics); Cypher injection guarded.

- Fix: `affected` and `graphify query` now handle graph files that use `"edges"` as the top-level key instead of `"links"`. Graphs produced by native `graphify extract` on some corpus layouts used `"edges"`; loading them in `affected.py` raised `KeyError: 'links'`. Normalised using the same established pattern already in `__main__.py` and `serve.py`.
- Fix: a single `!` negation rule in `.graphifyignore` no longer disables all directory pruning. Previously any negation pattern caused `collect_files` to descend every ignored directory to look for re-included files. Since gitignore semantics cannot rescue files beneath an excluded parent, this descent was always wasted — the per-file filter still excluded them. Pruning now proceeds unconditionally; only the final per-file `_is_ignored` check is consulted for negation.
- Feat: `--model` flag added to `graphify label-communities` and `graphify cluster-only`. Routes through `generate_community_labels` → `label_communities` → `_call_llm`; defaults to `None` (keeps existing backend default). Also fixes a latent arg-parsing bug where `--backend gemini` (space-separated) was mis-parsed as the positional path argument.
- Docs: Persian (فارسی) README translation added (`docs/translations/README.fa-IR.md`).

## 0.8.38 (2026-06-11)

- Fix: LLM-generated `calls` edges now have correct direction. The extraction prompt previously never stated that `source` = caller and `target` = callee; the LLM systematically emitted callee→caller edges. An explicit direction rule was added to the prompt. Separately, ghost-node merge was extended to collapse LLM duplicate nodes (bare-stem IDs) onto AST canonical nodes (parent-qualified IDs) even when the LLM node carries a `source_location` — the old check only caught `source_location=None` ghosts. Post-fix annotation: `calls` precision 100% (n=6), overall INFERRED precision 94% (n=16).
- Fix: default imports/exports now produce symbol-level edges. JS/TS symbol resolution only handled named imports, so a `export default class Foo` imported as `import Foo from './foo'` got just a file→file `imports_from` edge — the class node received no incoming symbol edge. On codebases that default-export most classes (NestJS services/helpers/models, etc.) this left those symbols looking like isolated leaf nodes and made `graphify affected "<Class>"` / `explain` report no callers. Default imports are now recorded with `imported_name="default"`, `export default <class|function|identifier>` registers a `"default"` export, and the existing resolver wires the `imports` edge (and resolves calls through the local binding, even when renamed). Anonymous defaults (`export default class {}`) remain file-level only.
- Fix: tsconfig `paths` aliases now resolved relative to `baseUrl`. Previously all `@/*` → `src/*` aliases were resolved from the config file's directory regardless of `baseUrl`, breaking path alias import resolution for NestJS, monorepo, and similar layouts that set `baseUrl: "./src"`.
- Fix: ghost-merge skips ambiguous `(basename, label)` keys where multiple AST nodes share the same pair. Previously the last-writer-wins pass silently mis-merged one of two same-named symbols in different files (e.g. two `render` functions across separate modules), re-pointing edges to the wrong canonical node.
- Fix: `resolve_seed` now matches bare query terms against callable-decorated node labels. A query for `"render"` failed to seed nodes whose label was stored as `".render()"` because the string comparison was exact. Bare names are now tried against stripped labels as a fallback after exact and prefix matches.
- Fix: AST cache is now namespaced by graphify version. Stale AST cache entries from a previous release no longer silently produce wrong extraction output after an upgrade — each version writes to its own subdirectory under `graphify-out/cache/ast/<version>/`. Semantic cache is deliberately unversioned (LLM calls are expensive to re-run).
- Fix: global-graph edges are now rewired to deduplicated external nodes. When two repos shared an external dependency node (e.g. both reference `requests`), one copy was pruned but edges still pointed to the removed node ID, creating dangling references. Edges are now remapped through the dedup remap table before insertion.
- Fix: dedup pass 2 now picks the winner only from the verified `(node, neighbor)` pair. The previous code unioned both normalised-label groups before calling `_pick_winner`, allowing an unrelated same-named node from a different file to be dragged into the merge and supplant the correct winner.
- Fix: extraction cache is anchored at the `--out` directory root instead of leaking a `graphify-out/` into the scanned project. Using `graphify extract ./src --out /tmp/out` previously wrote cache files into `./src/graphify-out/cache/` alongside source files. Cache now writes exclusively under the `--out` path.
- Fix: `collect_files` rewritten as a single pruned `os.walk` instead of one `rglob` per extension. On large repos this eliminated ~85 redundant filesystem traversals; noise directories (`node_modules`, `.git`, `__pycache__`, etc.) are now pruned before descent, preventing those subtrees from being scanned at all.
- Fix: frontmatter delimiter detection now requires a whole `---` line (regex `^---[ \t]*\r?$`). Thematic break lines (`----`) and YAML documents that open with `--- title: foo` were incorrectly parsed as frontmatter delimiters, causing cache hash instability on Markdown files with those constructs.
- Fix: `claude-cli` backend now spawns `claude.cmd` on Windows headless installs. `npm`-installed Claude Code ships a `.cmd` shim on Windows; `CreateProcess` cannot run it without the explicit extension. `shutil.which("claude.cmd")` is now tried first on win32, mirroring the fix already applied to the extraction path. `CREATE_NO_WINDOW` flag added to both subprocess spawn sites to prevent console windows flashing during headless runs.
- Fix: `claude-cli` backend handles JSON-array envelope from Claude Code CLI ≥ 2.1. Older CLI versions returned a single JSON object; 2.1+ wraps the response in a streaming array of events. The envelope parser now accepts both shapes, preferring the last `{"type":"result"}` event from an array.
- Feat: Cargo workspace dependency extraction. `graphify extract ./my-workspace --cargo` introspects `Cargo.toml` files across a Rust workspace and emits `crate:<name>` nodes with `crate_depends_on` edges for workspace-internal dependencies. Registry dependencies are excluded. Handles virtual workspaces, root-package workspaces, glob members, and `{workspace = true}` inherited deps.
- Fix: SystemVerilog class-level extraction improved. Classes, interfaces, enums, parameters, and their inheritance/implementation relationships are now extracted correctly from `.sv`/`.svh` files. Dart `with MyMixin` clauses now emit `mixes_in` edges (was incorrectly `implements`), consistent with PHP and Scala.
- Docs: README grammar count updated from 28 to 36, reflecting all currently supported tree-sitter language grammars.

## 0.8.37 (2026-06-10)

- Security: SSRF guard rewritten to eliminate thread-safety race. The global `socket.getaddrinfo` monkey-patch is replaced with per-connection `_SSRFGuardedHTTPConnection`/`_SSRFGuardedHTTPSConnection` subclasses that resolve DNS once, validate the IP, and connect to that exact address — closing both the concurrent-thread race window and the underlying TOCTOU gap. No global state is mutated, so sibling threads (MCP server, PR triage pool) are unaffected.
- Security: Prompt injection mitigation for LLM semantic extraction. Untrusted source file content is now wrapped in `<untrusted_source path="..." sha256="...">` XML delimiters; jailbreak sentinel tokens (`<|im_start|>`, `[INST]`, `<<SYS>>`, forged closing tags) are neutralised with a zero-width space; the extraction system prompt includes an explicit SECURITY block stating that content inside the wrapper is inert data.
- Fix: `export obsidian` and `export canvas` no longer crash with `KeyError` when a community contains a node ID absent from the graph (stale community index, merge artifacts). Dangling members are silently skipped.
- Fix: `--update` on macOS no longer re-extracts all Office files on every run. `convert_office_file()` now NFC-normalises the source path before hashing the sidecar filename, so NFD paths returned by `os.walk` (HFS+/APFS) produce the same sidecar as NFC-constructed paths. An early-return when the sidecar exists prevents mtime bumps causing spurious re-detection.
- Fix: Data `.json` files no longer explode into hundreds of orphan key-nodes. The JSON extractor now only processes config/manifest JSON (detected by filename — `package.json`, `tsconfig.json`, `.eslintrc.json`, `deno.json`, etc. — or by top-level keys such as `dependencies`, `extends`, `$ref`, `compilerOptions`). Data JSON (top-level arrays, generic key/value files) is skipped by the AST pass and left for the LLM semantic pass.
- Fix: OpenAI-compatible backends no longer send `temperature=0` to reasoning models. `_resolve_temperature()` auto-detects o1/o3/o4 and gpt-5 series and omits temperature from the request. Override with `GRAPHIFY_LLM_TEMPERATURE=<value>` (or `none` to omit explicitly for any model).
- Fix: EDR / corporate Windows hang eliminated. `datasketch` (which transitively imports `scipy` → `numpy.testing` → `platform.machine()` subprocess at import time) is replaced by a self-contained pure-numpy MinHash/MinHashLSH implementation with byte-identical hash math. Removes `datasketch` and `scipy` from the dependency tree.
- Perf: `detect()` ignore-pattern checks memoized per scan. Each ancestor directory is now evaluated once across all sibling files, eliminating ~42M redundant `fnmatch` calls on large repos (~34% whole-run speedup on 2k-file corpora).
- Fix: `dedup.py` label-based merge passes now skip code nodes entirely. Distinct same-named symbols in different files (e.g. two `Config` classes) were being merged by the exact-label and MinHash/LSH passes. Code nodes are now deduplicated by ID only, which is correct.
- Feat: `GRAPHIFY_MAX_GRAPH_BYTES` env var to override the 512 MiB `graph.json` size cap. Accepts plain bytes, `<N>MB`, or `<N>GB`. The cap error message now cites this env var. `graphify export html` auto-falls back to the community-aggregation view when over cap instead of hard-failing.
- Feat: `CLAUDE.md` template now uses mandatory language for the graphify-first rule — "MANDATORY: Before using Read/Grep/Glob/Bash to explore the codebase, you MUST run graphify first" — and explicitly requires forwarding the rule to subagent prompts. PreToolUse hook message hardened to match.
- CI: Release workflow added. Every GitHub release now ships `graphify-self-graph.tar.gz` as a downloadable asset — `graph.json` + `graph.html` + `GRAPH_REPORT.md` from running Graphify on its own source. Open `graph.html` locally with no install required to see what Graphify produces.

## 0.8.36 (2026-06-08)

- Feat: `extra_body` field in `providers.json` forwarded to OpenAI-compat calls at extraction and labeling. Lets vLLM/Qwen3/Llama endpoints pass model-specific request shapes (e.g. `{"chat_template_kwargs": {"enable_thinking": false}}`). Explicit `extra_body` also bypasses Ollama `num_ctx` auto-derive. Thanks to @EirikWolf (#1197).
- Feat: `label_communities` multi-batch for 16k-context models. Chunks of 100 communities per call (configurable `batch_size=`); `max_communities` defaults to `None` (label all); partial batch failures no longer drop the whole pass. Thanks to @EirikWolf (#1197).
- Feat: `.slnx` Visual Studio solution file support. Extracts `contains` (project references) and `imports` (build dependencies) edges from the modern XML solution format (VS 2022 17.13+). Thanks to @bakgaard (#1189).
- Feat: `graphify-mcp` console script. MCP stdio server now directly invocable as `graphify-mcp` from `uv tool install` / `pipx`. Thanks to @jr2804 (#1190).
- Fix: `label_communities` token budget raised and `GRAPHIFY_MAX_OUTPUT_TOKENS` now honoured. Hardcoded `min(40+16n, 4096)` undershooted (~16 tok/community); raised to `min(64+24n, 8192)` and wrapped in `_resolve_max_tokens()` (#1200).
- Fix: `find_import_cycles` no longer hangs on large graphs. `nx.simple_cycles()` now receives `length_bound=max_cycle_length`, pruning during enumeration rather than post-filtering — drops from never-returns to ~0.1s on dense graphs (#1196).
- Fix: fuzzy dedup no longer merges prefix-extension symbol pairs. `getActiveSession`/`getActiveSessions`, `parseConfig`/`parseConfigFile` etc. scored ~98-99 JW and were auto-merged. A prefix-extension guard now prevents merge when one normalised label is a strict prefix of the other, in both Pass 2 and the LLM tiebreaker (#1201).
- Fix: `_norm`, `_norm_label`, `_strip_diacritics` guard against `None` node labels, preventing `TypeError` crash on corpora with explicit `null` label fields (#1194). Thanks to @freiit (#1195).
- Fix: skill frontmatter `trigger:` field removed from all 14 skill variants — not part of Agent Skills spec, flagged by `agentskills validate` CI (#1180).

## 0.8.35 (2026-06-07)

- Feat: CodeBuddy platform support. `graphify codebuddy install` installs the graphify skill to `~/.codebuddy/skills/graphify/SKILL.md`, writes a `CODEBUDDY.md` always-on section, and registers Bash + Read|Glob PreToolUse hooks in `.codebuddy/settings.json` that nudge the agent toward `graphify query` instead of grepping raw files when a graph exists. `graphify install --platform codebuddy` and `graphify codebuddy uninstall` also supported. Thanks to @studyzy (#1136).
- Fix: `graphify --update` no longer destructively collapses distinct same-named symbols across files. The skill's `--update` merge now passes re-extracted (changed) files to `prune_sources` alongside deleted files, so old nodes for changed files are pruned before fresh AST is inserted — no fuzzy reconciliation needed. Separately, `dedup.py` Pass 1 now skips nodes with an empty `source_file` so label-only merging across no-source-file nodes is prevented. The anti-shrink guard message now names fuzzy dedup as a possible cause rather than only blaming missing chunk files (#1178).

## 0.8.34 (2026-06-07)

- Feat: Streamable HTTP transport for the MCP server. `python -m graphify.serve graph.json --transport http --port 8080 --api-key $SECRET` serves the graph over the MCP Streamable HTTP transport (spec 2025-03-26) so a single shared process can serve the whole team. Flags: `--host`, `--port`, `--api-key` (env `GRAPHIFY_API_KEY`), `--path`, `--json-response`, `--stateless`, `--session-timeout`. Docker image included. stdio remains the default (#1143).
- Feat: Salesforce Apex extractor. `.cls` and `.trigger` files are now AST-extracted via regex (no tree-sitter grammar exists for Apex). Extracts classes, interfaces, enums, methods, triggers, and SOQL/DML edges (#1159).
- Feat: Azure OpenAI Service backend. `--backend azure` reads `AZURE_OPENAI_API_KEY` + `AZURE_OPENAI_ENDPOINT` and auto-detects both. Uses the existing `openai` package — no new dependency (#1107).
- Feat: live PostgreSQL introspection. `graphify extract --postgres "postgresql://..."` connects directly to a running database and maps tables, views, routines, and FK relations via `information_schema` in a `SERIALIZABLE READ ONLY` transaction. New `graphify[postgres]` extra (psycopg3). Credentials are sanitized from error messages (#1103).
- Feat: vision and PDF support in headless extract. Images now route through per-backend vision payloads (base64/data-URI for claude/openai, file path for claude-cli, bytes for bedrock) instead of producing garbage binary data. Non-vision backends get a text reference via `_strip_pixels`. PDFs reuse pypdf. 5MB cap, 20-image chunk limit (#1110).
- Fix: `graphify update` now prunes symbols removed from files that still exist on disk. Previously, deleting a function left a ghost node in the graph until the source file itself was deleted. Every AST node is now stamped with `_origin="ast"`; on a full rebuild any stamped node absent from the fresh output is dropped (#1118).
- Fix: `graphify path` and `shortest_path` now fire the exact-match bonus for multi-word queries. The per-token comparison never equalled a full multi-word label, so the exact bonus was silently skipped for queries like `"AuthService"` when the label contained punctuation or spaces. The full normalized query is now compared alongside each token (#1165).
- Fix: `_is_sensitive` no longer flags topic-mentioning filenames as secrets. `token-economics-of-recall.md` and `password-policy-discussion.md` were silently dropped. Generic keywords (token/secret/password) now only fire when the keyword ends the filename stem or the stem is ≤2 words; specific patterns (`.env`, `.pem`, `id_rsa`, etc.) remain unconditional (#1169).
- Fix: git hooks no longer use `nohup` to background the rebuild. Git for Windows' MSYS shell has no `nohup`, causing the post-commit/post-checkout hook to fail silently and the graph to go stale. Replaced with a cross-platform Python launcher using `DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP` on Windows and `start_new_session=True` on POSIX (#1161 / #1170).
- Fix: post-commit and post-checkout hooks now respect an existing `.graphify_root`. A scoped build (`graphify src/`) was silently expanded to the full repo on the next commit because the hook hardcoded `Path('.')`. The hook body now reads `graphify-out/.graphify_root` first (#1173).
- Fix: `graphify affected` now forces a directed graph on load, matching the identical fix already applied in `serve.py` and `__main__.py`. On undirected graphs (`"directed": false` in graph.json) the traversal was direction-blind — missing true callers and reporting callees as affected (#1174).
- Fix: Step 9 skill cleanup no longer aborts under fish/zsh on pure-code corpora. The `rm -f ... .graphify_chunk_*.json` glob errored with "no matches found" when no chunk files existed, leaving other temp files on disk. Split into `rm -f` for fixed filenames and `find -maxdepth 1 -delete` for the chunk glob (#1172).
- Fix: `detect_incremental` no longer crashes on schema-drifted manifest files. A dict-valued `mtime` entry (from an older richer schema) is now coerced to `None` and the file is treated as new rather than raising a comparison error (#1163).
- Fix: numpy pinned to `>=2.0` only on Python 3.13+ in the `svg` and `all` extras. numpy 1.26.4 ships no `cp313` wheel so `uv sync` fell back to a source build requiring a C compiler (#1153 / #1154).
- Fix: Codex platform skill now installs to `.codex/skills/graphify/` (was `.agents/skills/graphify/`), aligning with where the hook already lives (#1160).

## 0.8.33 (2026-06-06)

- Feat: FalkorDB export backend — sibling to Neo4j, selected via `graphify export falkordb [--push falkordb://localhost:6379]`. FalkorDB is OpenCypher-compatible, so the MERGE/SET upsert queries match the Neo4j path; auth is optional and the target graph defaults to `graphify`. Install with `uv tool install "graphifyy[falkordb]"` (#1175).
- Feat: install banner — `graphify install` now prints an amber knowledge-graph brain in the terminal (TTY-only, silent in CI/pipes, never raises).
- Fix: Python `from pkg import submod` package-form imports now resolve to a file-level `imports_from` edge to the submodule file when it exists on disk. Previously these imports produced zero edges, leaving test files as disconnected islands in the graph (up to 66% of test nodes in some corpora). The fix lives in the symbol-resolution post-pass which has filesystem access (#1146).
- Fix: builtin type-annotation nodes (`str`, `int`, `bool`, `float`, `bytes`, `MagicMock`, `Mock`, `AsyncMock`, etc.) no longer appear as graph nodes or accumulate edges. They were being created via the annotation walker whenever used as parameter or return types, inflating degree counts ~25% and displacing real abstractions from god-node rankings. A new `_PYTHON_ANNOTATION_NOISE` filter suppresses them at extraction time; `god_nodes` also filters them as a defense for pre-existing graphs (#1147).
- Fix: AST/semantic ghost-duplicate nodes are now auto-merged at build time. When AST and semantic extraction produce different IDs for the same symbol (one with `source_location=L<n>`, one without), `build_from_json` detects the pair by `(source_file basename, label)` and collapses the semantic ghost into the AST node, re-pointing all edges. Graphs built before this release can be cleaned up with `graphify extract . --force` (#1145).

## 0.8.32 (2026-06-05)

- Feat: Terraform/HCL support. `.tf`, `.tfvars`, and `.hcl` files are now AST-extracted via `tree-sitter-hcl` into a structured infrastructure dependency graph. Nodes: resources, data sources, modules, variables, outputs, providers, and locals. Edges: `contains`, `references` (interpolation), and `depends_on`. Node IDs are directory-scoped for cross-file resolution. Requires `uv tool install "graphifyy[terraform]"` (#1129).
- Fix: `graphify extract` no longer requires an LLM API key for code-only corpora. Backend resolution is now deferred until after file detection — a corpus with only code files (pure tree-sitter AST, zero LLM calls) runs fully offline. The key is only enforced when docs, PDFs, or images are present, or when `--dedup-llm` is passed (#1122).
- Fix: `graphify kiro install` now correctly installs the `references/` sidecar and `.graphify_version` stamp. The install was using a bare `write_text` that bypassed the shared helper, shipping `SKILL.md` with 8 dead `references/*.md` pointers. Re-run `graphify kiro install` to pick up the fix (#1142).
- Fix: `GRAPHIFY_API_TIMEOUT` now applies to `claude-cli` subprocess and Anthropic SDK backend, not just the HTTP client. Both subprocess paths previously hardcoded `timeout=600` and ignored the env var and `--api-timeout` flag (#1112).
- Build: version floors added for `networkx>=3.4`, `datasketch>=1.6`, and `rapidfuzz>=3.0` to prevent silent breakage from old installs resolving incompatible versions.

## 0.8.31 (2026-06-03)

- Fix: `graphify hook install` now embeds the current interpreter (`sys.executable`) directly into the generated hook scripts. Previously, uv tool and pipx installs silently no-oped on git commit in GUI clients and CI runners where `~/.local/bin` is not on PATH — the hook could not find the graphify launcher, fell through all detection probes, and exited 0 without rebuilding. The embedded path is sanitized through a filesystem-safe allowlist before substitution. If you already have hooks installed, re-run `graphify hook install` to pick up the fix (#1127).
- Fix: hook scripts now also probe `graphify-out/.graphify_python` as a fallback interpreter source, covering Windows/Git Bash installs where the launcher is a binary with no parseable shebang, and the case where the pinned path goes stale after a reinstall.
- Security: hook script hardening — the `_PINNED=` assignment uses single quotes to prevent shell injection from a path containing metacharacters; `nohup "$GRAPHIFY_PYTHON" -c` is properly quoted to handle spaces; the fallback emits a loud stderr diagnostic instead of a bare silent `exit 0`.
- Feat: query logging. Every `graphify query`, `graphify path`, `graphify explain`, and MCP `query_graph` call is now appended to `~/.cache/graphify-queries.log` in JSON Lines format (timestamp, kind, question, corpus path, nodes returned, result size, duration). Full subgraph responses are not stored by default. Control with `GRAPHIFY_QUERY_LOG` (path override), `GRAPHIFY_QUERY_LOG_DISABLE=1` (opt out), `GRAPHIFY_QUERY_LOG_RESPONSES=1` (store full response text) (#1128).

## 0.8.30 (2026-06-03)

- Fix: `graphify install --project --platform antigravity` now writes Antigravity's always-on layer (`.agents/rules/graphify.md` + `.agents/workflows/graphify.md`), not just the skill. The project-scoped path went through the skill-only branch and skipped them, even though the project uninstall removes them.
- Feat: close the Read-tool graph bypass. The `PreToolUse` nudge previously only fired on Bash search (`grep`/`rg`/`find`); an agent answering a question by reading many source files through the native `Read` tool (or `Glob`) slipped past it. A new `Read|Glob` hook nudges toward `graphify query` when `graphify-out/graph.json` exists, only for a source/doc file outside `graphify-out/`, and never blocks (#1114).
- Feat: add an `anthropic` optional extra (and include it in `[all]`) so the `claude` backend is installable like every other one: `uv tool install "graphifyy[anthropic]"`. Previously it was the only backend with no extra, so a user with `ANTHROPIC_API_KEY` set could not satisfy it without `--with anthropic`. The backend package-missing errors now point at `uv tool install "graphifyy[<extra>]"` (the isolated-venv path) rather than only `pip install`.

## 0.8.29 (2026-06-02)

- Feat: progressive-disclosure skill files. The per-host `SKILL.md` is now a lean core (~615 lines, down from the ~1156-line monolith, about 47% less always-loaded context) that carries the full default code-build pipeline inline and links to an on-demand `references/` sidecar (extraction-spec, query, update, exports, transcribe, github-and-merge, add-watch, hooks); an agent reads a reference only when that path is actually taken, so a normal build needs none. 18 hosts go progressive (claude, codex, opencode, kilo, copilot, claw, droid, trae, trae-cn, hermes, kiro, pi, antigravity, antigravity-windows, windows, kimi, amp, gemini); aider and devin stay monolithic by design. All 15 skill bodies + sidecars are generated from one source under `tools/skillgen/`, with CI guards (`--check`, `--audit-coverage`, `--monolith-roundtrip`, `--always-on-roundtrip`) proving the references are byte-identical slices of the old monolith so nothing is lost (#1121).
- Fix: `graphify install --platform gemini` shipped a `SKILL.md` with 8 dead `references/` pointers. gemini installs claude's lean progressive core but the installer never copied claude's references sidecar; it now does, so every on-demand reference resolves (regression from the progressive-disclosure split).
- Security (F1): a project-local `./.graphify/providers.json` (which travels with a cloned or shared repo) is no longer loaded automatically, since a custom provider's `base_url` is where your corpus and API key are sent. Set `GRAPHIFY_ALLOW_LOCAL_PROVIDERS=1` to opt in; the user's own `~/.graphify/providers.json` is still trusted. Non-http(s) `base_url`s are rejected on load and on `provider add`, and plaintext-http egress warns. **Behavior change:** if you relied on an auto-loaded project-local providers file, set the opt-in env var.
- Security (F2): untrusted office/PDF files are screened before parsing (on-disk size cap, plus a bounded streaming-decompression ceiling for `.docx`/`.xlsx` zip containers) so a zip-bomb in a scanned corpus can no longer exhaust memory.
- Security (F3): `OLLAMA_BASE_URL` pointing at a link-local or cloud-metadata address (`169.254.x`, `metadata.google.*`, or any host that resolves to one) now fails closed with a clean error instead of sending the corpus there. Trusted LAN hosts still warn-and-allow.
- Security (F5): the Fortran C-preprocessor step passes an absolute path so an attacker-named corpus file cannot be interpreted as a `cpp` option.

## 0.8.28 (2026-06-01)

- Feat: Kilo Code support — `graphify install --platform kilo` installs a native skill (`~/.config/kilo/skills/graphify/SKILL.md`) and `/graphify` command, plus a `.kilo` `tool.execute.before` plugin (mirroring the OpenCode integration). Existing `.kilo/kilo.jsonc` config is read but never rewritten — plugin registration goes to `kilo.json` so user comments are preserved (#512)
- Feat: modernized Dart extractor — comment stripping, `part of` redirection, nested-generic-aware `extends`/`with`/`implements` parsing, generic type-argument mapping, and generic call detection (#1098)
- Fix: `uv tool install graphifyy` / `pip install graphifyy` no longer fails to build on Linux/macOS — `tree-sitter-dm` (BYOND DreamMaker) ships only a Windows wheel, so on other platforms it compiled from source and aborted the entire install when a C toolchain or `python3-dev` headers were missing. It is now an optional extra (`graphifyy[dm]`, also in `[all]`) instead of a core dependency, so the default install needs no compiler (#1104).
  - **Upgrade note:** DreamMaker `.dm`/`.dme` users must reinstall with `graphifyy[dm]` (or `[all]`) to keep AST extraction — on `uv tool upgrade` the now-optional grammar is removed. `.dmi`/`.dmm`/`.dmf` parsing is unaffected (no tree-sitter dependency).
- Fix: community IDs are now assigned by a total order (`(-size, sorted node IDs)`) so an identical grouping always gets identical IDs across runs — previously the equal-sized small communities that dominate a sparse graph were numbered by the partitioner's (not seed-stable) enumeration order, making a per-node community diff report large spurious "churn" even though the actual grouping was reproducible (#1090 follow-up)
- Fix: `graphify amp install` now writes the skill where Amp actually looks for it. It was landing in `.amp/skills/graphify` (project) and `~/.amp/skills/graphify` (user), neither of which Amp searches, so the skill never loaded. User-scope installs now go to `~/.config/agents/skills/graphify` and project installs to `.agents/skills/graphify`, and a stale `~/.amp/skills/graphify` from an older install is cleaned up on the next run.

## 0.8.27 (2026-05-31)

- Feat: standalone CLI now auto-names communities with the configured backend instead of leaving `Community N` placeholders — community labeling was previously an agent-only step (skill.md Step 5), so bare-CLI runs never got semantic names; `cluster-only` now auto-labels when no `.graphify_labels.json` exists, new `graphify label <path>` subcommand (re)generates names on demand, `--no-label` opts out, `--backend=<name>` overrides auto-detection; one batched LLM call with per-community placeholder fallback and graceful degradation on missing backend/API error; works with all built-in and custom OpenAI-compatible backends (#1097)
- Fix: AST file-level node IDs now match the skill.md `{parent_dir}_{stem}` spec — they were derived from the full relative path plus extension (`match_script_pipeline_step_py`) while semantic subagents use `script_pipeline_step`, splitting every file into two disconnected ghost nodes; fixed at the single relative-path remap chokepoint so file nodes and all import/dependency edge endpoints (Python, TS, Lua, C, bash) convert together (#1033)
- Fix: symbol-level node IDs for root-level files now match the spec too — the #1033 remap relativized file nodes but symbols still embedded the absolute parent-dir name (`<rootdir>_main_run` vs spec `main_run`), splitting every top-level file's symbols into AST/semantic ghost pairs; the remap now canonicalizes symbol stems and `raw_calls` caller IDs, gated by `source_file` (#1096)
- Fix: TypeScript `interface A extends B` and same-file `class X extends Y` now produce `inherits`/`implements` edges — the walker only inspected `class_heritage` (missing the interface `extends_type_clause` node) and the resolver only consulted the import table (missing same-file bases); both gaps closed (#1095)
- Fix: `graphify export obsidian` no longer crashes with `OSError ENAMETOOLONG` on long node labels — `to_obsidian`/`to_canvas` now cap filenames on UTF-8 bytes (not chars, so multibyte/CJK labels are handled) with an 8-char hash suffix on truncation to keep distinct long-prefix labels from colliding; also fixes the previously-uncapped `_COMMUNITY_` notes (#1094)
- Fix: `graph.json` is now deterministic across runs — `detect()` sorts file traversal lexicographically (`os.walk` order is filesystem-dependent), which had made first-writer-wins node-ID decisions and Leiden community counts vary between identical runs (#1090)
- Fix: Windows consoles no longer crash with `UnicodeEncodeError` on non-UTF-8 code pages — `main()` reconfigures stdout/stderr to UTF-8 at startup and `→`/`—` in print statements replaced with ASCII (#992)

## 0.8.26 (2026-05-30)

- Feat: `find_import_cycles(G)` in `analyze.py` detects file-level circular import dependencies — collapses symbol graph to file-level directed import graph, finds simple cycles via Johnson's algorithm, deduplicates rotations, renders `## Import Cycles` section in `GRAPH_REPORT.md` (#961)
- Feat: custom LLM provider registry — `graphify provider add/list/show/remove` registers any OpenAI-compatible endpoint (NVIDIA NIM, vLLM, OpenRouter, Together, LiteLLM) via `~/.graphify/providers.json`; custom providers auto-detected after built-ins in `detect_backend()` priority (#1084)
- Fix: `extract_files_direct()` no longer silently defaults to kimi (Moonshot AI) — `backend=None` now calls `detect_backend()` and raises a clear `ValueError` if no key is configured, matching CLI behavior; README Privacy section updated with data-residency notes (#1086)
- Fix: `pnpm-workspace.yaml` with `packages: - '.'` no longer crashes with `IndexError: tuple index out of range` on Python 3.10 — `Path.glob('.')` replaced with `[root]` guard in `_load_workspace_packages`; `GRAPHIFY_DEBUG=1` env var added to `_safe_extract` for full traceback on extraction errors (#1083)
- Fix: anchored `.graphifyignore` patterns (leading `/`) no longer match the same directory name anywhere in the tree — `_matches()` in both `_is_ignored` and `_is_included` now gates basename/segment shortcuts on `not anchored`; anchored patterns do exact anchor-relative path match only (#1087)
- Docs: Filipino (fil-PH) README translation added (#1080)

## 0.8.25 (2026-05-29)

- Fix: JS/TS `const`/`let` inside arrow-function callbacks no longer emit phantom god-nodes — scope guard restricts `_js_extra_walk` node emission to program-level declarations only; applies uniformly to JS, TS, and TSX (#1077)
- Fix: fenced code blocks in Markdown no longer emit orphan `codeblock_N` nodes — they had only `contains` edges and no semantic meaning; fence-toggle still prevents inner content from being mis-parsed as headings (#1077)
- Fix: Lua `require("pkg.sub")` now resolves to the correct file node ID — dots converted to path separators, probes filesystem for `.lua`/`.luau`/`init.lua` variants up the directory tree (#1075)
- Fix: Windows `claude-cli` backend no longer raises `WinError 2` — prefers `claude.cmd` over bare `claude` to avoid PATHEXT `.ps1` resolution failure (#1072)
- Fix: post-commit hook no longer silently drops `changed_paths` when another rebuild holds the lock — lock-losers queue paths to a pending file; the lock-holder drains and merges on acquire (#1059)
- Fix: `graphify install antigravity` global install now writes to `~/.gemini/config/skills/` (per Antigravity docs) instead of the wrong `~/.agents/`; uninstall, version-stamp refresh, and project-scope install all updated to match (#1079)
- Docs: README warns against `pip install` on Mac/Windows due to Python env mismatch causing `ModuleNotFoundError`; `uv tool install` recommended as primary method (#1074)

## 0.8.24 (2026-05-29)

- Feat: type-reference edges for ObjC, Julia, C, C++, Scala, Fortran, and PowerShell — extends cross-language semantic context work from #1015 to a second wave of languages; CI matrix now covers Python 3.10 with `faster-whisper` version guard (#1071)
- Fix: claude-cli backend no longer loops on hollow streamed responses — handles all four documented failure modes (empty stream, no JSON, missing `result`, empty `result`) with tests (#1063)
- Fix: `calls` edges no longer flip caller/callee when the same node pair appears in both directions in an undirected build — first-seen direction preserved on bidirectional collision (#1061)
- Fix: `graphify-out/.graphify_python` path prefix was missing in 8 skill files (256 instances) causing `cat: .graphify_python: No such file or directory` on every non-Claude-Code platform
- Chore: all skill files now use uv-aware interpreter detection — `uv tool run graphifyy python` preferred over shebang parsing when uv is available

## 0.8.23 (2026-05-28)

- Feat: type-reference edges for Swift, Kotlin, PHP, Rust, and Go — `references` edges with `parameter_type`, `return_type`, `generic_arg`, `field`, and `attribute` contexts; inheritance split into `inherits` (superclass) vs `implements` (protocol/interface/trait) for all five languages (#1015)
- Chore: CI switched from pip to uv (`astral-sh/setup-uv`, `uv sync`, `uv run pytest`); `uv.lock` committed for reproducible installs; dev setup docs updated (#885)

## 0.8.22 (2026-05-28)

- Feat: BYOND DreamMaker support — `.dm`/`.dme` files extracted via tree-sitter-dm (type definitions, proc declarations, `#include` edges, in-file call resolution, `new /type()` instantiation edges); `.dmi` PNG icon files parsed for icon-state nodes; `.dmm` map files parsed for type-path `uses` edges from the tile dictionary section; `.dmf` interface files parsed for window/elem/control-type hierarchy (#884)
- Feat: `graphify extract --mode deep` flag enables richer semantic extraction using an extended system prompt; flag propagated through all four LLM backends (#1030)

## 0.8.21 (2026-05-27)

- Fix: `graphify update` (no `--changed` flag) no longer leaves ghost nodes from files deleted between runs — full re-extraction path now reconciles the existing graph against current disk state and evicts any node whose `source_file` no longer exists; `_norm_source_file` used on both sides to guarantee path format consistency (#1007)
- Fix: `graphify install --platform opencode --project` now writes `SKILL.md` to `.opencode/skills/graphify/SKILL.md` (discoverable by OpenCode) instead of the incorrect `.config/opencode/skills/` path; git-add hint updated accordingly (#1040)
- Fix: post-commit hook no longer triggers rebuild when only `graphify-out/` files were committed (avoids infinite dirty-tree loop when graph outputs are tracked in git); `GRAPHIFY_SKIP_HOOK=1` env var added for one-off skip; hook rebuild log now appends (`>>`) instead of overwriting (`>`) (#1018, #1037)
- Fix: graph output is now byte-for-byte deterministic across runs — edges sorted by `(source, target, relation)` in `build_from_json`; `PYTHONHASHSEED=0` exported in hook scripts to stabilize Louvain community ordering (#1010)
- Feat: Amp (ampcode.com) platform support — `graphify amp install/uninstall` installs the skill into `.amp/skills/graphify/SKILL.md` (#948)
- Fix: query punctuation no longer breaks node matching — `"what calls extract?"` correctly finds the `extract` node; `_search_tokens` helper strips punctuation from search terms in `_query_terms`, `_score_nodes`, and `_find_node` (#994, #978)
- Fix: language built-in globals (`String`, `Number`, `Boolean`, `Object`, `Array`, etc.) no longer accumulate spurious call edges — filtered at same-file and cross-file resolution in the AST extractor, eliminating god-node pollution from constructor-style calls (#916, #726)
- Feat: SystemVerilog header files (`.svh`) now extracted using the Verilog parser alongside `.v` and `.sv` (#1042)
- Fix: `@property`, `@staticmethod`, `@classmethod` methods no longer produce orphaned nodes without a class-qualified ID — `decorated_definition` is now treated as a transparent wrapper in the Python AST walker, preserving `parent_class_nid` through the decorator layer (#1050)
- Fix: Pass 2 dedup no longer merges nodes with identical labels that live in different files — same-file partition enforced for the identical-label subcase so `foo()` in `a.py` and `foo()` in `b.py` are not collapsed into one node (#1046)
- Fix: `graphify-out/memory/` files are no longer silently excluded by `.gitignore` pattern matching — memory dir files now bypass the gitignore filter in `detect.py`, ensuring knowledge accumulated via `graphify remember` is always scanned (#1047)

## 0.8.20 (2026-05-26)

- Fix: stale nodes persist after `graphify update` when files are deleted on Windows — `deleted_paths` and `evict_sources` in `_rebuild_code` now use `.as_posix()` for consistent forward-slash paths; `_relativize_source_files` called on the existing graph before eviction (not after); `_relativize_source_files` itself now produces forward slashes (#1007)
- Fix: `graphify extract` stale-node pruning now also handles symlinked scan roots — `prune_set` expansion uses `Path(root).resolve()` before `relative_to()` so symlinked roots produce correct relative paths (#1007)
- Feat: MCP config extractor — `.mcp.json`, `mcp.json`, `mcp_servers.json`, `claude_desktop_config.json` now extracted into the knowledge graph; captures server nodes, npm/pip package refs, env var requirements; env values discarded to prevent secret leakage (#1034)
- Fix: `cluster-only` no longer drops community label alignment after re-clustering — `remap_communities_to_previous` now applied in the `cluster-only` path, matching the behaviour of `graphify update` (#1028)
- Fix: Dart child node IDs no longer embed absolute paths — switched from `_make_id(str(path), name)` to `_make_id(_file_stem(path), name)`, consistent with all other extractors; existing Dart graphs should be rebuilt with `--force` (#999)
- Security: XML parsing in `extract_csproj` and `extract_lazarus_package` now pre-screens for `<!DOCTYPE` / `<!ENTITY` declarations before calling `ET.fromstring`, blocking billion-laughs DoS on malicious project files; `extract_lpk` also gains the missing 2 MiB size cap

## 0.8.19 (2026-05-26)

- Feat: .NET project file support — `.sln`, `.csproj`, `.fsproj`, `.vbproj`, `.razor`, `.cshtml` now extracted; captures NuGet package refs, project-to-project dependencies, target frameworks, SDK attributes, Blazor/Razor directives (`@using`, `@inject`, `@inherits`, `@model`, `@page`), component refs, and `@code` block methods (#1025)
- Feat: Chinese query segmentation — compound Chinese tokens (e.g. `页面路由`) are split into meaningful words using jieba when installed, with character bigram fallback; original compound preserved alongside segments for exact-match; new `pip install "graphifyy[chinese]"` extra (#1026)
- Fix: Wiki TypeError when `source_file` is `None` — `G.nodes[n].get("source_file") or ""` replaces `.get("source_file", "")`, which did not handle explicit `None` values (#1016)
- Fix: Nested `.claude/worktrees/` no longer indexed — `_is_noise_dir` now accepts an optional `parent` param and skips `worktrees/` directories nested inside dotted dirs like `.claude/` (#1023)
- Fix: `backup_if_protected` no longer accumulates one folder per run — uses content-hash comparison to skip identical backups and overwrite in-place when content changes; one folder per day maximum
- Feat: Devin CLI support — `graphify devin install/uninstall` installs the skill into Devin's `.devin/rules/` directory (#1020)
- Fix: TypeScript 5.0 array-form `extends` in `tsconfig.json` now handled — `_read_tsconfig_aliases` normalizes `extends` to a list before iteration (#1017)

## 0.8.18 (2026-05-24)

- Fix: post-commit hook now updates graph after delete-only commits — shrink-guard is bypassed when `changed_paths` contains explicit deletions, preventing stale nodes from accumulating indefinitely (#1000)
- Fix: `graphify export` (html/obsidian/wiki/svg/graphml/neo4j) no longer collapses to "Single community" when `.graphify_analysis.json` is absent — falls back to per-node `community` attribute already present in `graph.json` (#1001)
- Fix: Ukrainian README translation updated to v8 — all new sections, correct badges, 31 languages (#995)
- Feat: semantic context tags on `references` edges for Python/JS/TS/C#/Java — `parameter_type`, `return_type`, `generic_arg`, `attribute`, `field`; C#/Java split `inherits`/`implements`; dedup key now includes context (#996)
  - **Breaking:** Java `extends` edges are now emitted as `inherits` — queries filtering on `relation="extends"` for Java nodes must be updated to `relation="inherits"`
- Feat: constrained query expansion in skill — Step 0 extracts actual graph vocab and forces LLM to pick expansion tokens only from that set, preventing hallucinated expansions; Unicode regex fix captures Cyrillic/CJK labels (#998)
- Docs: Ukrainian README updated to v8 with all new sections, correct badges, YC badge, 31 language count (#995)

## 0.8.17 (2026-05-23)

- Fix: Case-sensitive call resolution for Go, Rust, and Elixir — resolvers previously lowercased both the label index and the callee name, causing `Authorize` to match `authorize` and produce phantom edges; Ruby/C#/Java/Kotlin/Scala/PHP use the same generic resolver which now splits into case-sensitive (all languages) and case-insensitive (PHP only, where function/class names are genuinely case-insensitive) dicts (#993)
- Fix: Cross-language phantom `calls` edges from semantic extraction dropped at graph-build time — INFERRED `calls` edges whose source and target nodes belong to different language families (py/js/go/rs/jvm/c/cpp/rb/php/cs/swift/lua) are now discarded; skill.md prompt updated with an explicit anti-rule (#991)

## 0.8.16 (2026-05-22)

- Fix: CJK/Unicode labels no longer silently stripped during dedup — `_norm()` and `_norm_label()` now use Unicode-aware `[\W_]+` regex with `casefold()` and NFKC normalization; previously `道具処理クラス` and any non-ASCII label collapsed to empty string and got falsely merged (#937)
- Fix: `.ets` (ArkTS/HarmonyOS) files now recognized as code and extracted via the TypeScript parser (#926)
- Fix: `graphify` now exits non-zero when all semantic-extraction chunks fail — previously a silent empty graph was written with exit code 0, masking backend failures (#889)
- Feat: `graphify install --project` installs the skill into the current repository (`.claude/skills/`, `.agents/skills/`, etc.) instead of the user home directory; per-platform subcommands support the same flag (#931)
- Docs: Uzbek (uz-UZ) README translation (#982)

## 0.8.15 (2026-05-22)

- Fix: `cluster-only` subcommand crashed with `FileNotFoundError` when `graphify-out/` did not yet exist — output directory is now created before any write (#934)
- Fix: `GRAPHIFY_MAX_OUTPUT_TOKENS` env var now respected for all OpenAI-compatible backends — previously the token limit was hardcoded, causing truncated responses on high-context queries (#973)
- Fix: Swift extension nodes no longer duplicated across files — `_merge_swift_extensions` deduplicates by canonical name before graph insertion (#969)
- Fix: Non-Latin query terms (CJK, Arabic, Cyrillic, etc.) now preserved through query preprocessing — previous normalization stripped non-ASCII chars, making multi-lingual codebases unsearchable (#964)
- Feat: Multigraph runtime compatibility probe — emits a warning if a `MultiDiGraph` is passed where a `Graph` is expected by any downstream consumer (analyze, cluster, wiki, export, report) (#956)
- Feat: JS/TS barrel re-exports tracked as explicit `re_exports` graph edges — `export { X } from './mod'` emits typed edges with `context="re-export"` and `confidence=EXTRACTED`; file-level `imports_from` edges also emitted (#960)
- Feat: `--affected` and `--import-resolution` flags for the `v8` subcommand — impact analysis and cross-file import resolution exposed as first-class CLI options

## 0.8.14 (2026-05-20)

- Fix: `--wiki` crash when community node IDs are stale after dedup or re-extract — stale IDs are now silently dropped with a stderr warning; raises a clear error only if every ID is stale (#936)
- Fix: `.gitignore` patterns now respected when no `.graphifyignore` exists — previous behaviour silently ignored the project's gitignore, causing expected exclusions to be skipped (#945)
- Feat: `--exclude <pattern>` CLI flag to pass extra gitignore-style exclusion patterns at runtime without modifying `.graphifyignore` (#947)
- Fix: `.worktrees/` directory now skipped during scan — git worktree sibling checkouts inside `.worktrees/` were previously indexed as duplicate source (#947)
- Security: NAT64 IPv6 addresses (`64:ff9b::/96`) no longer false-positive as blocked reserved IPs — affects hosts like `arxiv.org` on IPv6-only networks where the ISP uses RFC 6052 NAT64

## 0.8.13 (2026-05-18)

- Fix: node ID collisions across same-named files in different directories — SQL extractor and Python import resolver now use directory-qualified stems (`dir_file_entity`) instead of bare filename stems, preventing silent node merging on repos with duplicate filenames (#1A, #1B)
- Perf: stat-based mtime fastpath for `file_hash` — skips full SHA256 read when file size+mtime_ns unchanged, same trade-off as make; index flushed atomically via atexit
- Fix: absolute `source_file` paths from semantic subagents no longer stored in graph — `build_from_json`, `build`, and `build_merge` accept a `root` param and relativize paths at build time (#932)
- Fix: failed semantic chunks no longer permanently freeze their files in the manifest — only files that appear in extraction output get `semantic_hash` stamped; failed-chunk files keep empty `semantic_hash` and are re-queued on next run (#933)
- Feat: `graphify cache-check`, `graphify merge-chunks`, `graphify merge-semantic` CLI subcommands expose cache and merge logic as library-callable commands for skill pipelines

## 0.8.12 (2026-05-18)

- Security: `_is_sensitive` now correctly flags underscore-prefixed secret filenames (`api_token.txt`, `oauth_token.json`) — `\b` word boundary was treating `_` as a word char, so names like `api_token` never matched (#920)
- Security: `_is_sensitive` now checks parent directories against a `_SENSITIVE_DIRS` blocklist (`.ssh`, `.aws`, `.gcloud`, `secrets`, etc.) so any file inside those dirs is skipped regardless of name; root-level files named `credentials` or `secrets` are no longer falsely flagged (#920)
- Fix: `--wiki` Relationships section was always empty — `_cross_community_links` read `community` from node attributes (always None) instead of the `communities` dict; `_god_node_article` had the same bug and never linked to the owning community (#925)
- Fix: `--watch` now respects `.graphifyignore` — the event handler was checking extensions before the ignore filter, so paths inside `node_modules/`, `.venv/`, etc. triggered rebuilds (#928)
- Fix: `graphify <path>` now correctly dispatches to `graphify extract <path>` — previously a bare path argument returned "unknown command" instead of starting extraction
- Fix: skill fast path — if `graphify-out/graph.json` already exists and the request is a natural-language question, extraction steps are skipped entirely and `graphify query` runs immediately; previously the skill re-ran detect and hit the corpus-size gate on every question
- Fix: large-corpus gate raised from 200 to 500 files; `detect()` now returns `scan_root` so the skill correctly computes relative subdirectory breakdowns instead of showing absolute paths; flat repos with no subdirectories no longer ask the user to pick a subfolder that doesn't exist
- Docs: clarify that code-only corpora skip the LLM semantic extraction pass entirely — AST handles code, Pass 3 is reserved for docs, papers, images, and transcripts (#836)

## 0.8.11 (2026-05-18)

- Fix: LLM empty choices / None message guard — Gemini and other providers return `choices=[]` on content-filtered HTTP 200 responses; now raises a clean error instead of crashing with IndexError (#924)
- Fix: OpenCode skill removed invalid `general-purpose` agent reference and headless-incompatible interactive halt (#911, closes #825)
- Fix: Codex skill now uses graphify query/explain/path even when graph artifacts are dirty in worktree (#913, closes #860)
- Perf: precompute degrees once in surprise scoring — ~11x speedup per lookup on large graphs (#914)

## 0.8.10 (2026-05-17)

- Fix: git hooks phantom directory on git < 2.31 — drop `--path-format=absolute`, validate path contains no newlines, anchor relative paths on repo root (#907)
- Fix: `save_manifest` incremental data loss — seed from existing manifest before loop so untouched files aren't erased on partial runs (#917)
- Fix: C++ class/struct inheritance edges missing — extract `base_class_clause` for `class_specifier` and `struct_specifier` (#915)
- Fix: cohesion split threshold unreachable due to rounding — `cohesion_score` now returns raw float, display rounds to 2dp (#919)
- Fix: Rust cross-crate spurious INFERRED edges — skip `Type::method()` scoped calls and common trait-method names from cross-file resolver (#908)
- Feat: `--resolution N` for `extract` and `cluster-only` — control Leiden/Louvain community granularity (>1 = more smaller, <1 = fewer larger) (#919)
- Feat: `--exclude-hubs P` for `extract` and `cluster-only` — exclude degree-percentile super-hubs from partitioning, reattach by majority-vote neighbour community (#919)

## 0.8.9 (2026-05-17)

- Feat: DeepSeek backend support — set `DEEPSEEK_API_KEY` and use `--backend deepseek`; default model `deepseek-v4-flash`

## 0.8.8 (2026-05-16)

- Feat: `graphify prs` — graph-aware PR dashboard: CI state, review decision, worktree mapping, and graph blast radius per PR; `--triage` ranks your queue via any configured LLM backend (claude, kimi, openai, gemini, claude-cli, ollama — auto-detected); `--conflicts` shows PRs sharing graph communities with node labels; `--worktrees` maps worktree paths to branches to open PRs; MCP tools `list_prs`, `get_pr_impact`, `triage_prs` for agent access

## 0.8.7 (2026-05-16)

- Fix: query seed selection now uses IDF weighting — common terms like `error` or `handle` that match dozens of nodes are down-weighted so a rare identifier like `FooBarService` ranks first and BFS expands from the right node (#897)
- Fix: seed count is now dynamic — a dominant match (score gap >80% vs next candidate) gets one seed rather than always picking three, preventing noise nodes from consuming BFS slots alongside the target (#897)
- Fix: truncation message in `query_graph` now tells Claude what to do (call `get_node` or add a `context_filter`) rather than just saying "truncated" (#897)
- Fix: C++ class data members (`int x;`, `static const int MAX = 100;`) now extracted as nodes with `defines` edges from the parent class — previously the field_declaration branch was a no-op due to a wrong child type guard (#898)
- Fix: dedup Pass 1 now partitions same-label groups by source_file before merging — nodes with generic labels (`handle`, `init`, `run`) from different files no longer collapse into artificial god nodes; cross-file matches are routed to Pass 2 fuzzy (#895)
- Fix: C/C++ `#include "path/to/file.h"` edges now resolve the include path relative to the including file and use the full resolved path as the target node ID, matching what extraction creates for the included file — previously all include edges dangled with a basename-only ID (#899)
- Fix: `exact_merges` counter in dedup now reports only merges actually performed rather than counting all same-label nodes across files (#895)

## 0.8.6 (2026-05-16)

- Fix: cross-language INFERRED `calls`/`uses` edges (e.g. Python → TypeScript) are suppressed in Surprising Connections — label-matching across language boundaries in monorepos is resolver pollution, not structural insight; all structural bonuses zeroed for these edges
- Fix: code-to-doc INFERRED `calls`/`uses` edges suppressed in Surprising Connections — the LLM seeing a symbol name in a README and emitting a `calls` edge is documentation cross-reference noise, not a real architectural connection (#890)
- Fix: generic JSON key nodes (`name`, `id`, `type`, `start`, `end`, `key`, `value`, `data`, `items`, `title`, `description`, `version`, `properties`) filtered from god_nodes — their degree is positional (every sibling record in the same JSON file references them), not architectural (#890)
- Fix: Alembic migrations, Django migrations, and protobuf-generated files now have their module-level docstrings suppressed from rationale extraction — these are boilerplate headers, not design intent; function docstrings inside migration files are still captured
- Feat: `--follow-symlinks` is now auto-detected — if symlinked children are present in the target directory, follow-symlinks is enabled automatically without requiring an explicit flag (#887)
- Fix: install guidance now directs users to run `/graphify query` interactively rather than reading `GRAPH_REPORT.md` first; the report is a summary, not a starting point (#891)

## 0.8.5 (2026-05-15)

- Fix: `.graphifyignore` parent-exclusion rule now correctly blocks files under an excluded directory even when a `!` negation exists elsewhere in the file — previously any negation pattern disabled directory pruning entirely (#882)
- Fix: dedup no longer false-merges chip/model SKU variants like `ASR1603`/`ASR1605` or `M1`/`M1 Pro` — Jaro-Winkler prefix bonus is now gated by `_is_variant_pair` and `_short_label_blocked` guards; real typos on short labels still merge (#878)
- Docs: added `worked/rsl-siege-manager/` — case study on a real-world Python + TypeScript monorepo (FastAPI backend, React/Vite frontend, Discord bot); covers god node behaviour with tests included, cross-language INFERRED edges, community cohesion, and Alembic migration noise (#881)

## 0.8.4 (2026-05-15)

- Feat: Firebird SQL — trigger and stored procedure extraction via `CREATE TRIGGER` and regex fallback; FK detection via global regex covering `REFERENCES` and `FOREIGN KEY` clauses (#875)
- Fix: SQL extraction regex fallback now decodes source as UTF-8 instead of latin-1, preventing non-ASCII identifier hash mismatches (#875)
- Fix: `--update` deletion pruning now matches on full source file paths instead of basenames, preventing false node removal when different directories contain files with the same name (#876)
- Fix: `--update` now also prunes edges whose `source_file` attr points to deleted files, not just nodes (#876)
- Fix: community label keys from `graph.json` (stored as strings) are now coerced to int before lookup, fixing blank community names in GRAPH_REPORT.md and graph.html (#877)

## 0.8.3 (2026-05-15)

- Fix: Windows skill temp files (chunk JSONs, `.graphify_python`, `.graphify_root`) no longer pollute the project root — all written under `graphify-out/` (#831)
- Fix: `--update` with deletions-only no longer errors when `.graphify_extract.json` does not yet exist — creates an empty extraction file before merging (#876)

## 0.8.2 (2026-05-15)

- Fix: Python interpreter detection for `uv tool` and `pipx` installs on Windows — `graphify install` and all skill steps now find the correct executable (#831)
- Fix: antigravity Windows skill path resolution (#831)
- Fix: dot directories (e.g. `.github/`, `.vscode/`) are now indexed when explicitly included via `.graphifyignore` (#873)
- Fix: MCP server hot-reloads the graph when `graph.json` changes on disk (#874)

## 0.8.1 (2026-05-15)

- Feat: Bash extractor — `.sh` and `.bash` files now indexed via tree-sitter; extracts functions, cross-function calls, `source`/`.` imports resolved to real file paths, and `export`/`declare` variable declarations (#866)
- Feat: JSON extractor — `.json` files now indexed via tree-sitter; extracts key/value `contains` tree, `dependencies`/`devDependencies` blocks as `imports` edges, `extends` edges (tsconfig, eslintrc), and `$ref` references (#866)
- Feat: `.sh`, `.bash`, `.json` added to `CODE_EXTENSIONS` in `detect.py` so files are picked up during corpus scan (#866)
- Feat: Mermaid callflow HTML auto-regenerates on every graph rebuild when `*-callflow.html` exists in `graphify-out/` — works with `--watch` and `graphify hook install`
- Fix: `coverage/`, `lcov-report/`, `visual-tests/`, `visual-test/`, `__snapshots__/`, `snapshots/`, `storybook-static/`, `dist-protected/` added to `_SKIP_DIRS` — generated artefact dirs no longer appear in the corpus (#869, #870)
- Fix: `graphify hook install` now works in git linked worktrees — uses `git rev-parse --git-path hooks` instead of constructing `.git/hooks/` directly (#865)
- Fix: office sidecar files in `graphify-out/converted/` are now checked against `.graphifyignore` before being added to the file list (#861)
- Fix: `save_manifest()` accepts a `kind` parameter (`ast`, `semantic`, `both`) — incremental AST-only `graphify update` no longer overwrites `semantic_hash` entries, preventing spurious full re-extracts on the next run (#857)
- Fix: five paths in `skill-windows.md` Step B3 were missing the `graphify-out/` prefix, causing chunk files to be written to the wrong directory (#862)

## 0.7.19 (2026-05-14)

- Feat: `.astro` files now extracted as code — frontmatter static imports, dynamic imports, and `<script>` block imports all produce edges; tsconfig path aliases resolved (#850, PR #852)
- Fix: `.rebuild.lock` no longer accumulates PIDs across rebuilds — now contains a single owning PID while running and is unlinked on release so downstream tooling polling for its absence unblocks promptly (#858, PR #859)
- Docs: skill.md now clarifies that graphify does not read `ANTHROPIC_API_KEY` or other provider keys during `/graphify` skill runs — the host IDE session provides the LLM (PR #864)

## 0.7.18 (2026-05-14)

- Fix: `graphify update` is now idempotent — graph.json and GRAPH_REPORT.md are only rewritten when content actually changes; topology comparison short-circuits clustering entirely on unchanged graphs, eliminating residual community-count drift (#824)
- Fix: community IDs are now stable across rebuilds — Leiden/Louvain receive deterministically sorted input and a fixed random seed; greedy overlap remapper preserves existing IDs so hand-edited `.graphify_labels.json` labels don't drift onto wrong communities (#824)
- Fix: `--no-cluster` flag added to `graphify update` — writes raw AST graph without clustering, consistent with `graphify extract --no-cluster` (#824)
- Fix: `graphify update --no-cluster` now writes `"links"` key matching the schema of the full clustered path; previously wrote `"edges"`, causing schema toggle on every mode switch
- Fix: `.graphify_labels.json` was rewritten on every rebuild even when nothing changed; now only written when outputs actually change
- Fix: shrink-check (refuse overwrite when new graph has fewer nodes) was duplicated across two code paths; unified into a single `_check_shrink()` helper
- Fix: node ID format in skill.md corrected to `{parent_dir}_{filename_stem}_{entity}` — the old filename-only format caused ghost-duplicate nodes when AST and semantic extractors disagreed on the stem; top-level files use just the filename stem; existing graphs with ghost duplicates can be cleaned up with `graphify extract --force`
- Fix: safer JSON serialization in clustering sort keys (`default=str`) prevents crashes when edge attributes contain non-serializable values
- Docs: added Prerequisites, optional extras table, environment variables reference, troubleshooting, and dev setup to README (#833)

## 0.7.17 (2026-05-13)

- Fix: `graphify path` and `graphify explain` now render arrow direction correctly — `-->` for caller→callee, `<--` for callee←caller; previously the graph was loaded undirected so every hop printed `-->` regardless of stored direction (#849, #853)
- Fix: MCP `shortest_path` and `get_neighbors` tools had the same reversed-arrow bug; now fixed in `serve.py` alongside the CLI commands (#849, #853)
- Fix: `graphify extract --backend bedrock` was rejected by the CLI guard even when `AWS_PROFILE`/`AWS_REGION`/`AWS_DEFAULT_REGION`/`AWS_ACCESS_KEY_ID` were set — boto3 session auth was never reached (#846)
- Fix: BFS/DFS query traversal now skips expanding high-degree hub nodes (threshold: `max(50, p99_degree)`) as transit — hubs can still be destinations but no longer produce semantically meaningless 2-hop paths like `ClassA → View → ClassB` in Android/Spring corpora (#830)
- Fix: `--update` manifest shrink — after an incremental run, `manifest.json` was overwritten with only the changed-file subset, causing the next `--update` to re-flag the entire unchanged corpus as new; Step 9 now persists the full corpus via `all_files` fallback (#837)
- Fix: `file_type` enum aligned across `skill.md` and `llm.py` (both now enumerate all six values: `code`, `document`, `paper`, `image`, `rationale`, `concept`); synonym mapper in `build.py` silently coerces known LLM-emitted synonyms (`pattern→concept`, `markdown→document`, `tool→code`, etc.) before validation (#840)
- Fix: Fortran test fixture renamed `sample.F90` → `sample_preprocessed.F90` to avoid case-collision with `sample.f90` on macOS case-insensitive filesystems (credit: @FatahChan, #823)

## 0.7.16 (2026-05-12)

- Fix: all `read_text()`/`write_text()` calls in `skill.md` and `skill-windows.md` now specify `encoding="utf-8"` — bare calls defaulted to the system codepage on Chinese-locale Windows, silently mojibaking node labels and Markdown content on `--update` (#832)
- Fix: `json.dumps` in skill pipeline now uses `ensure_ascii=False` so Chinese/CJK characters are stored as-is rather than `\uXXXX` escaped (#832)
- Fix: Step 1 install fallback in skill now prefers `uv tool install --upgrade graphifyy` over `pip` when uv is on PATH — pip was installing to the wrong environment when graphify was originally installed via `uv tool` (#831)
- Fix: `_score_nodes` in `serve.py` now uses three-tier precedence (exact 1000 / prefix 100 / substring 1) instead of flat substring scoring — `graphify path "Foo" "FooBar"` no longer returns 0 hops when both labels substring-match the same node (#828)
- Fix: `graphify path` and MCP `_tool_shortest_path` now emit a clear error when source and target resolve to the same node, instead of silently returning 0 hops (#828)
- Fix: `file_hash` in `cache.py` now normalises path keys via `.as_posix().lower()` — Windows junction/case variants of the same file now hash identically, fixing `save_semantic_cache` always reporting "Cached 0 files" on subsequent `--update` runs (#826)
- Fix: `check_semantic_cache` now applies the same absolute-path normalization as `save_semantic_cache` so relative `source_file` paths resolve consistently on both sides (#826)
- Fix: `_AGENTS_MD_SECTION` now includes the `/graphify` skill trigger instruction — all 7 AGENTS.md platforms (OpenCode, Codex, Aider, Trae, Hermes, OpenClaw, Factory Droid) now correctly invoke the skill tool when the user types `/graphify` (#827)

## 0.7.15 (2026-05-11)

- Fix: `-h`/`--help`/`-?` in any position now stops execution — previously `graphify cursor install --help` silently installed into Cursor; `graphify benchmark --help` crashed with FileNotFoundError (#821)
- Fix: `--version`, `-v`, and `graphify version` now print the installed version and exit (#818)
- Fix: `GRAPHIFY_OLLAMA_NUM_CTX=<invalid>` no longer falls back to hardcoded 131072 (which exhausted VRAM) — it now falls through to the auto-derived value and prints a warning (#820)
- Fix: when `GRAPHIFY_OLLAMA_NUM_CTX` is set smaller than the estimated chunk size, graphify now warns explicitly that Ollama will silently truncate the prompt and suggests a corrected `--token-budget` (#820)

## 0.7.14 (2026-05-11)

- Fix: `_make_id` and `_normalize_id` now apply NFKC Unicode normalization before ID generation -- composed/decomposed forms of the same character (e.g. `é` typed vs pasted from a PDF) now produce the same node ID; switched from `.lower()` to `.casefold()` for correct Turkish/German/Greek case folding; both functions are now byte-for-byte equivalent (#811)
- Fix: non-ASCII identifiers (CJK, Cyrillic, Arabic, accented Latin) are no longer collapsed to a bare file stem -- `[^\w]+` with `re.UNICODE` replaces the old `[^a-zA-Z0-9]+` so Unicode word chars are preserved as part of the ID (#811)
- Fix: dedup edge remap uses explicit key-presence check instead of `or` so empty-string `source` is not silently swapped for `from`; stale `from`/`to` keys are now popped before the edge is emitted so they can't leak into `graph.json` edge attributes (#803)
- Fix: `--update` merge now calls `build_merge()` directly instead of an inline NetworkX round-trip that re-introduced the direction-flip bug from #760; dict merge ordering fixed so explicit `source`/`target` always win over stale attrs; hyperedges pulled from `G.graph` (merged) rather than just the new extraction (#801)
- Fix: subagent chunk files are now written to an absolute path (`CHUNK_PATH` injected at dispatch time from `graphify-out/.graphify_root`) so the Write tool doesn't lose chunks to an undefined working directory (#808)
- Fix: skill version mismatch warning is now suppressed during `hook-check` (runs on every editor tool use and must be silent) and routed to stderr for all other commands

## 0.7.13 (2026-05-09)

- Fix: Ollama `num_ctx` now derived from actual chunk size instead of hardcoded 131072 -- over-allocating 128k KV-cache slots for small chunks exhausted VRAM by chunk 4 on large models; formula is `min(input_tokens + output_cap + 2000, 131072)` so `--token-budget 8192` gets ~26k instead of 131072 (#798)
- Fix: hollow-response warning now mentions VRAM pressure and `GRAPHIFY_OLLAMA_NUM_CTX` / `GRAPHIFY_OLLAMA_KEEP_ALIVE` env vars as tuning knobs (#798)
- Feat: `graphify export callflow-html` -- generates a self-contained Mermaid architecture/call-flow HTML page from `graphify-out/graph.json`, grouped by community with interactive zoom/pan diagrams, call detail tables, and graph report highlights (#797)
- Feat: callflow HTML auto-regenerates on every `--watch` rebuild and post-commit hook if the file already exists -- opt-in by existence, zero config (#800)

## 0.7.12 (2026-05-09)

- Fix: `graphify explain` and `graphify path` no longer crash on `MultiGraph` inputs -- new `edge_data()`/`edge_datas()` helpers in `build.py` handle both simple and multi-graphs; all 8 production call sites and 30 skill-file inline heredocs updated (#796)
- Fix: hollow Ollama responses (0 tokens / empty string) now trigger adaptive retry bisection instead of silently dropping the chunk -- `_response_is_hollow()` detects empty/null/whitespace content and parsed results with no nodes/edges, then rewrites `finish_reason="length"` to route into the existing bisection path (#792)
- Fix: post-commit hook no longer spawns unbounded parallel rebuilds -- per-repo `fcntl.flock` non-blocking lock in `_rebuild_code`; `changed_paths` wired from hook through to AST extractor; stale nodes evicted on deletion; `GRAPHIFY_REBUILD_TIMEOUT` watchdog; Darwin-aware memory cap (#791)
- Fix: Antigravity install now writes to `.agents/` (plural) -- corrected in platform config, paths, workflow body, and help text (#453)
- Fix: Antigravity rules file now includes `trigger: always_on` YAML frontmatter so Antigravity recognises it (#785)
- Feat: `graphify extract` gains `--max-workers`, `--token-budget`, `--max-concurrency`, `--api-timeout` flags; hard 8-worker AST cap removed; explicit HTTP timeout on OpenAI client (default 600s, `GRAPHIFY_API_TIMEOUT`); ollama API key gate skipped for loopback URLs (#792)
- Feat: Pascal/Delphi extraction now works without `tree-sitter-pascal` -- regex fallback covers unit/program/library headers, uses clauses, class/interface inheritance, method declarations, and intra-file calls (#781)
- Feat: `/graphify --help` now prints the Usage block and stops without running pipeline steps (all 12 skill files) (#795)

## 0.7.11 (2026-05-09)

- Fix: context-window-exceeded API errors now trigger automatic retry with bisected file chunks -- exponential bisection up to 6 levels deep; covers `"context_length_exceeded"`, `"maximum context length"`, and `"too_large"` across OpenAI-compat backends (#789)
- Fix: Windows pipeline unblocked -- `print_benchmark()` falls back to ASCII box-drawing on cp1252 consoles; `ProcessPoolExecutor` `BrokenProcessPool` caught and falls back to sequential extraction when caller lacks `if __name__ == "__main__":` guard; Windows skill file (`skill-windows.md`) rewrites all `python -c "..."` blocks as PowerShell heredocs to fix quote-escaping failures (#788)
- Fix: reversed `calls` edges after `--update` -- `build_merge()` now reads the saved JSON directly instead of round-tripping through NetworkX `node_link_graph()`, which was silently reversing edge direction on reload (#760)
- Fix: atomic SKILL.md install -- temp-file + `os.replace()` pattern prevents half-installed empty skill directories that looked valid but contained no file; version-stamp guard and warning added for missing installs (#725)
- Feat: `graphify uninstall` top-level command -- removes graphify skill files from all platforms in one shot; `--purge` flag also deletes `graphify-out/`
- Feat: SQL `ALTER TABLE` FK extraction -- `ADD CONSTRAINT ... FOREIGN KEY` and `ADD FOREIGN KEY` DDL statements now emit `references` edges; schema-qualified table names (`schema.table`) correctly resolved (#779)

## 0.7.10 (2026-05-07)

- Fix: `.tsx` files now use `language_tsx` grammar for JSX-aware parsing -- previously `language_typescript` was used, silently dropping all JSX-specific nodes (#766)
- Fix: `edges` key in saved graph JSON now normalised to `links` before loading -- prevents `KeyError: 'links'` on graphs written by older NetworkX versions in `query`, `path`, `explain`, and serve (#768)
- Fix: Google Workspace `gws export` drops unsupported `resourceKey` query param -- Drive API requires it as an HTTP header; sending it as a query param was a silent no-op (#772)
- Security: eleven hardening fixes -- Cypher escape strips C0 control chars and `\n`/`\r`; YAML frontmatter escapes U+2028, U+2029, tabs, and C0; MCP `sanitize_label` applied to all LLM-derived fields; C preprocessor blocked from `#include` exfiltration via `-nostdinc -I /dev/null`; merge-driver 50 MB file size cap and 100k node cap; `detect_backend()` places Ollama last so paid API keys take precedence over ambient `OLLAMA_BASE_URL`; Neo4j `--password` reads from `NEO4J_PASSWORD` env var by default; hooks exception handling narrowed to `(configparser.Error, OSError)`
- Refactor: skill YAML descriptions rewritten to be trigger-oriented (#774)
- Refactor: generated `CLAUDE.md` / `AGENTS.md` / `GEMINI.md` templates strengthened with `ALWAYS`/`NEVER`/`IF ... EXISTS` graph-first directives (#775)

## 0.7.9 (2026-05-07)

- Feat: TypeScript extraction parity -- interface, enum, type alias, and module-level const nodes extracted; new_expression emits calls edges; parity with Java/C# class_types (#708)
- Feat: Quarto (`.qmd`) file support -- routed through existing Markdown extractor; Quarto executable code blocks (` ```{python} `) extracted as code nodes (#761)
- Feat: optional Google Workspace shortcut export for headless extraction -- `graphify extract ./docs --google-workspace` converts `.gdoc`, `.gsheet`, and `.gslides` files into Markdown sidecars with the `gws` CLI before semantic extraction; account email pseudonymized via SHA256 hash; `[google]` extra adds Sheets table rendering support (#752)
- Fix: Google Workspace exports now run `gws` from the sidecar output directory with a relative `-o` path, matching `gws` path validation and avoiding failures when extracting a corpus outside the current working directory.
- Feat: AWS Bedrock backend -- `graphify extract ./docs --backend bedrock`; credentials via standard AWS provider chain (AWS_PROFILE, AWS_REGION, IAM roles, SSO); model via GRAPHIFY_BEDROCK_MODEL (default anthropic.claude-3-5-sonnet-20241022-v2:0); `[bedrock]` extra adds boto3 (#757)

## 0.7.8 (2026-05-06)

- Fix: CommonJS `require()` imports now extracted from JS/TS -- `const { foo } = require('./mod')`, `const m = require('./mod')`, and `const x = require('./mod').y` all emit EXTRACTED `imports_from` (and per-symbol `imports`) edges. Previously CJS-only Node.js codebases produced AST graphs missing every import edge, which downgraded all cross-file calls to INFERRED.
- Fix: cross-file `calls` edges are now promoted from INFERRED to EXTRACTED when the caller's file has an explicit `imports` or `imports_from` edge to the callee. Previously every cross-file call was unconditionally INFERRED, even when a top-of-file `import` / `require` proved the binding. On a 92-file CJS Node.js corpus this promoted 88% of cross-file calls (104 of 118) to EXTRACTED.
- Feat: Gemini and OpenAI backends -- `graphify extract ./docs --backend gemini` (GEMINI_API_KEY / GOOGLE_API_KEY) or `--backend openai` (OPENAI_API_KEY); `[gemini]` and `[openai]` extras added (#735)
- Feat: Groovy and Spock support -- `.groovy` and `.gradle` extracted via tree-sitter-groovy; Spock spec files (`def "feature"()` syntax) handled via regex fallback (#732)
- Feat: Luau support -- `.luau` (Roblox Luau) added to code extraction using the Lua tree-sitter parser (#745)
- Feat: Markdown structural extraction -- headings, fenced code blocks, and nesting hierarchy extracted as graph nodes from `.md` and `.mdx` files with zero new dependencies (#711)
- Fix: `collect_files()` extension set now auto-syncs with `_DISPATCH` -- previously 18 extensions (`.sql`, `.vue`, `.svelte`, `.jsx`, `.ex`, `.jl`, etc.) were silently skipped in skill-mode extraction (#711)
- Fix: `detect_incremental` now forwards `follow_symlinks` to `detect()` -- symlinked subtrees no longer vanish on `--update` runs (#736)
- Fix: TS bare-path / `.svelte.ts` / `.svelte.js` / `index.ts` directory / multi-dot imports now resolve correctly -- previously these produced phantom edges dropped at merge time (#717, #716)
- Fix: `cluster-only` now loads and saves `.graphify_labels.json` -- human-readable community labels survive re-clustering instead of resetting to "Community N" (#744)
- Fix: `graphify export wiki` now fails fast with exit 1 if `.graphify_analysis.json` is missing -- prevents silent deletion of existing wiki articles (#746)
- Fix: `to_wiki()` now raises before the cleanup loop when `communities` is empty -- second safety layer against wiki data loss (#746)
- Fix: Ollama import error message now says "Ollama" not "Kimi" and points to `pip install openai`; `[ollama]` extras group added (#750)
- Security: hooks.py path execution now validates scripts are within the repo root -- closes supply-chain attack vector where a malicious commit could redirect hook execution (#747)

## 0.7.7 (2026-05-05)

- Feat: Ollama backend for headless extraction -- `graphify extract ./docs --backend ollama`; auto-detected when `OLLAMA_BASE_URL` is set; defaults to `qwen2.5-coder:7b`; zero cost ($0.00); sentinel API key handles OpenAI client auth requirement (#729)
- Feat: Cross-project global graph at `~/.graphify/global.json` -- `graphify global add/remove/list/path` to register multiple project graphs with `<repo>::<id>` prefixed node IDs, preventing silent collisions; hash-based skip avoids re-ingesting unchanged graphs (#729)
- Feat: `graphify extract --global --as <tag>` flag -- after building a project graph, auto-registers it into the global graph in one step (#729)
- Feat: `merge-graphs` now prefix-relabels each input graph before composing, preventing silent node ID collisions when two projects share entity names (#729)
- Fix: `deduplicate_entities` raises `ValueError` if called with nodes spanning multiple repos (cross-project dedup disabled by design -- per-project graphs are deduplicated in isolation) (#729)
- Fix: `detect_incremental()` now accepts and forwards `follow_symlinks` to `detect()`. Without this, `--update` runs silently miss any files reached through a symlinked sub-tree (e.g. `state_of_truth/` symlinking to a directory outside the corpus root), even when the original full run had detected them. Previously the flag was on `detect()` and `collect_files()` only. (#736)

## 0.7.6 (2026-05-05)

- Fix: `cluster-only` now accepts `--graph <path>` to specify a non-default graph.json location; positional path and flags can appear in any order (#724)
- Fix: `_is_sensitive()` no longer drops legitimate source files — word boundaries on the keyword pattern prevent false positives like `tokenizer.py`, `password_verification.py`, `SecretManager.java` (#718)
- Fix: `graphify extract --backend claude/kimi` raises default `max_tokens` from 8192 → 16384, eliminating the truncation-then-recursive-split cascade on dense doc corpora; respects `GRAPHIFY_MAX_OUTPUT_TOKENS` env var (#730)
- Fix: `--update` prune message now clearly distinguishes "N nodes pruned from M deleted files" from "M deletions detected but graph already clean — no drift" (#539)
- Fix: `extract_svelte()` stub nodes now carry the resolved import path as `source_file` instead of the importer's path, preventing metadata corruption after merge (#712)
- Fix: `extract_svelte()` now catches static `import X from './foo.svelte'` via a dedicated regex pass over `<script>` block content — previously tree-sitter's JS parser silently dropped all static imports in `.svelte` files (#713)
- Fix: `graphify extract` (full rebuild path) now saves `manifest.json` on every successful run, not only on `--update`; prevents stale-manifest drift on subsequent incremental runs (#538)
- Fix: `graphify antigravity install` now writes to `.agent/` (no trailing s) matching Antigravity's actual config paths (#704)
- Fix: Pi skill YAML frontmatter description simplified to avoid "nested mappings" parse error on Pi startup (#737)
- Fix: `--dedup-llm` flag now correctly threads LLM backend through to `deduplicate_entities` in both fresh and incremental extract paths; fresh extract path now also runs dedup (previously called `build_from_json` directly, bypassing dedup entirely)

## 0.7.5 (2026-05-04)

- Feat: `graphify extract` now runs incrementally - auto-detects prior `manifest.json` and re-extracts only changed/new files; semantic results cached by content hash so unchanged docs cost zero LLM tokens on repeat runs (#698)
- Feat: Entity deduplication pipeline runs on every build - entropy gate + MinHash/LSH blocking + Jaro-Winkler verification + same-community boost collapses near-duplicate entities (typos, spacing, plurals) before clustering
- Feat: `--dedup-llm` flag for `graphify extract` - optional LLM tiebreaker for ambiguous entity pairs (~$0.01 for 10k-node graphs), off by default
- Fix: `graphify hook install` rebuild now preserves human-readable community labels from `.graphify_labels.json` instead of resetting to generic "Community N" names on every commit (#705)
- Fix: `graphify install --platform gemini` now works correctly (#706)
- Deps: `datasketch` and `rapidfuzz` added as base dependencies

## 0.7.4 (2026-05-04)

- Fix: `_read_tsconfig_aliases()` now parses JSONC — handles `//` line comments, `/* */` block comments, and trailing commas that every TypeScript framework starter generates; warns to stderr on parse failure instead of silently returning `{}` (#700)
- Fix: `extract_svelte()` regex fallback now captures aliased dynamic imports (`$lib/...`, `$partials/...`, `@/...`) and uses correct `_make_id(str(path))` scheme so edges survive into `graph.json` instead of being dropped as phantom nodes (#701)

## 0.7.3 (2026-05-04)

- Feat: `graphify extract <path>` — headless full-pipeline extraction for CI; runs AST extraction on code files and semantic LLM extraction on docs/papers/images without Claude Code in the loop; supports `--backend kimi|claude`, `--out DIR`, `--no-cluster`; auto-detects backend from `MOONSHOT_API_KEY` / `ANTHROPIC_API_KEY`; docs-only corpora (issue #698) work cleanly
- Fix: export/query/path/explain CLI subcommands added in 0.7.2 now ship with integration tests
- Fix: skill.md reduced from 63KB to 47KB by replacing Python heredocs with CLI calls (#696)

## 0.7.2 (2026-05-04)

- Feat: Fortran support - extracts modules, subroutines, functions, programs, `use` imports, and `call` edges from `.f`, `.F`, `.f90`, `.F90`, `.f95`, `.F95`, `.f03`, `.F03`, `.f08`, `.F08` files; names are lowercased for case-insensitive matching (#694)

## 0.7.1 (2026-05-04)

- Fix: Obsidian export - community labels with `.`, `&`, `(`, `)` now produce valid Obsidian tags; only `[a-zA-Z0-9_\-/]` characters survive, preventing broken Dataview queries (#690)
- Fix: `_load_tsconfig_aliases()` now follows tsconfig `extends` chains - SvelteKit, Nuxt, and NestJS path aliases defined in extended configs are no longer silently dropped (#691)
- Fix: `.svelte` files now get a regex pass over the template layer after JS AST extraction - `{#await import('./X.svelte')}` markup-level dynamic imports are captured as edges (#692)
- Fix: recursion limit raised to 10,000 at extract entry points (main process + each worker) with a `_safe_extract` wrapper that skips pathological files with a clear warning instead of crashing the whole run (#695)

## 0.7.0 (2026-05-03)

Multi-dev busy-repo support: four gaps that caused merge conflicts, stale graphs, and silent cache misses in team workflows.

- Feat: `graphify hook install` now also configures a git merge driver for `graphify-out/graph.json` — union-merges two graph.json files so git never produces conflict markers in the knowledge graph; writes `.gitattributes` and registers `graphify merge-driver` in `.git/config`
- Feat: `graphify merge-driver <base> <current> <other>` subcommand — takes two graph.json variants and writes their node/edge union back to `<current>`; always exits 0 so merge never blocks
- Feat: Leiden community detection now seeded (`seed=42` when supported) for deterministic community IDs across parallel rebuilds — reduces JSON diff churn in multi-dev repos
- Feat: `graph.json` now embeds `built_at_commit` (git HEAD) at write time; `GRAPH_REPORT.md` surfaces the commit hash and a freshness check hint
- Fix: `file_hash` is now content-only (path removed from hash) — renamed files reuse their cache entry instead of re-extracting; cached `source_file` fields are updated to the new path on load
- Fix: watch mode mixed-batch handling — commits with both code and non-code files now rebuild code immediately AND write `needs_update` flag; previously code changes were silently dropped in mixed batches

## 0.6.9 (2026-05-03)

- Fix: `source_file` path separators normalized to forward slashes at graph ingestion — same physical file emitted with backslashes (Windows AST extractor) and forward slashes (semantic subagents) now merges into one node instead of splitting into two disconnected components (#683)
- Fix: two-phase cohesion re-clustering — communities with cohesion < 0.05 and ≥ 50 nodes are re-split, preventing doc-hub nodes (e.g. `CLAUDE.md`) from merging unrelated subsystems into one giant community (#683)
- Fix: VS Code Copilot instructions rewritten to be prescriptive — agent's first tool call must read `GRAPH_REPORT.md`, explicit trigger list, narrow allowlist for raw source reads (#688)
- Feat: `GRAPHIFY_OUT` env var overrides the output directory — accepts a relative name or absolute path, wires through `cache.py`, `watch.py`, and the CLI; useful for sharing one graph across multiple git worktrees (#686)
- Fix: `graphify antigravity install` now auto-updates stale rules and workflow files on re-run instead of silently skipping them (#652)
- Docs: README simplified — less dense, plain language; technical pipeline details moved to `docs/how-it-works.md`

## 0.6.8 (2026-05-03)

- Fix: `.graphifyignore` negation patterns (`!src/**`) now work correctly — when any `!` pattern is present, directory pruning is deferred to per-file checks so negated files inside ignored directories are reached (#676)
- Fix: Antigravity slash command `/graphify` now appears in the command dropdown — workflow file now includes YAML frontmatter with `name: graphify` required for Antigravity discovery (#678)
- Fix: Gemini CLI BeforeTool hook replaced `[ -f ... ] && echo` (bash-only) with cross-platform `python -c` using `json.dumps` — fixes hook failure on Windows CMD and Git Bash (#681)
- Fix: Codex hook-check exits silently — resolves `additionalContext` rejection on Codex Desktop PreToolUse (#651)
- Fix: `graphify install --platform codex` now writes absolute path to `graphify` executable — fixes PATH resolution in VS Code extension on Windows (#651)
- Fix: thin communities (fewer than 3 concept nodes) are now omitted from the Communities section in `GRAPH_REPORT.md` by default; report header shows `(N total, M thin omitted)` and Knowledge Gaps collapses thin communities to one summary line (#664)

## 0.6.7 (2026-05-02)

- Feat: `graphify tree` — self-contained D3 v7 collapsible-tree HTML view of `graph.json`; expand/collapse controls, depth-based colours, hover inspector; XSS-safe (#557)
- Feat: token-aware chunking with split-and-retry on truncation (#625)
- Feat: cross-language edge context filters in MCP `query_graph` tool (#573)
- Feat: dynamic `import()` extraction for JS/TS (#579)
- Fix: `save_semantic_cache` crashed with `IsADirectoryError` when a node's `source_file` was a directory path — `p.exists()` → `p.is_file()` (#655)
- Fix: `sanitize_label(None)` raised `TypeError` crashing `to_html` on graphs with null `source_file` rationale nodes — return `""` early (#656)
- Fix: chunk-extraction prompt omitted `rationale` from valid `file_type` values — model hallucinated `concept` on every doc/paper run; explicit merge step added to all skill variants (#657)
- Fix: `cost.json` always reported 0 tokens — chunk JSONs have placeholder zeros; orchestrator now globs and sums real token counts before merging (#658)
## 0.6.6 (2026-05-02)

- Fix: `skill-windows.md` rewritten from PowerShell to bash — Claude Code on Windows uses git-bash so PowerShell syntax (`$null`, `$LASTEXITCODE`, `Select-Object`, `& (Get-Content ...)`, `Remove-Item`) caused exit code 49 failures; now mirrors `skill.md` structure with `python` added as fallback after `python3` for Windows Conda (#39)
- Fix: wiki `to_wiki()` now clears stale articles before regenerating, preventing orphan .md accumulation (#558)
- Fix: `_safe_filename()` in wiki.py now strips Windows-reserved characters (`< > : " / \ | ? *`) and caps length at 200 chars (#594)
- Fix: rationale-node leakage in cross-file INFERRED call resolution — rationale nodes now excluded from name lookup; edge direction (`calls`, `rationale_for`) preserved correctly at JSON export (#576)
- Feat: `.graphifyinclude` hidden path allowlist — opt specific hidden dirs into traversal (e.g. `.hermes/plans/**/*.md`) (#583)
- Feat: `--no-viz` flag wired in `cluster-only`; `GRAPHIFY_VIZ_NODE_LIMIT` env var overrides 5000-node HTML threshold (#565)
- Fix: stray colon SyntaxError in `skill-trae.md` `--cluster-only` block (#603)
- Docs: skill INFERRED confidence score guidance changed to discrete rubric (0.55/0.65/0.75/0.85/0.95) backed by calibration data (#546)
- Docs: skill `--update` prune output clarified — splits no-drift vs drift cases (#544)
- Docs: skill `--update` merge step now calls `save_manifest` to prevent deleted files reappearing (#545)
- Feat: `graphify tree` — self-contained D3 v7 collapsible-tree HTML view of `graph.json`; expand/collapse controls, depth-based colours, hover inspector; XSS-safe via `html.escape()` and `_js_safe()` (#557)

## 0.6.5 (2026-05-02)

- Fix: Kotlin call-walker now accepts both `simple_identifier` and `identifier` node types — PyPI's `tree_sitter_kotlin` grammar uses `identifier` while older forks use `simple_identifier`, causing zero `calls` edges to be emitted (#659)
- Feat: community sidebar now uses checkbox-based multi-select instead of show/hide buttons — supports indeterminate "select all" state (#647)
- Feat: `graphify update --force` and `GRAPHIFY_FORCE=1` env var — bypass the node-count safety check after refactors that legitimately shrink the graph (#639)
- Fix: Codex PreToolUse hook on Windows — replaced `python3 -c "..."` inline command (fails on Conda where only `python` exists, and breaks PowerShell JSON parsing) with `graphify hook-check`, a new shell-agnostic subcommand. Re-run `graphify codex install` to regenerate the hook (#651, #522)

## 0.6.4 (2026-05-02)

- Fix: Codex PreToolUse hook failed on Windows — `[ -f ]` is bash-only and crashes on `cmd.exe`; replaced with a cross-platform Python one-liner (`pathlib.Path.exists()`) (#651)

## 0.6.3 (2026-05-02)

- Fix: incremental rebuild (`graphify update`, post-commit hook) dropped INFERRED/AMBIGUOUS semantic nodes extracted from code files — node preservation now filters by ID membership in the new AST output instead of `file_type`, so LLM-extracted call/data-flow edges survive code-only rebuilds (#653)
- Fix: post-commit and post-checkout hooks blocked `git commit` for the full rebuild duration (hours on large repos) — rebuilds now detach via `nohup & disown`, git returns in ~100ms, log written to `~/.cache/graphify-rebuild.log` (#650)
- Fix: cross-file INFERRED `calls` resolution used a last-write-wins name map, causing common short names (`log`, `execute`, `find`) to accumulate hundreds of spurious edges and dominate god_nodes ranking — resolution now skips any callee name that matches 2+ candidates (ambiguous, no import evidence to pick the right target) (#543)
- Fix: `cluster-only` command crashed on graphs with >5000 nodes due to unguarded `to_html` call — now wrapped in try/except ValueError matching the watch/hook path (#541)

## 0.6.2 (2026-05-01)

- Fix: Kimi K2.6 reasoning mode consumed entire token budget leaving `content` empty — thinking now disabled on Moonshot calls so graphs actually populate (#623)
- Fix: `graphify update` / `graphify watch` never persisted the manifest, so every subsequent `--update` re-extracted all files — manifest now saved after each rebuild (#621)
- Fix: inline comments in `.graphifyignore` (e.g. `vendor/ # legacy`) now stripped correctly — whitespace + `#` suffix is treated as a comment, `path#hash.py` preserved (#605)
- Fix: `graphify query "FunctionName"` now returns the exact matching node first instead of high-degree hub modules hijacking the output — 100-point exact-match bonus + seeds render before BFS expansion (#638)
- Fix: concurrent AST extractors raced on a shared `.tmp` cache file — each writer now gets a unique tempfile via `mkstemp`, eliminating cache corruption under parallel extraction (#589)
- Fix: `_clone_repo` branch names starting with `-` could be interpreted as git flags — validation added, `--` separator inserted before positional args (#589)
- Fix: replaced `html2text` (GPL-3.0) with `markdownify` (MIT) — removes the only copyleft dependency from a MIT project (#586)
- Fix: `--update` re-extracted files whose mtime was bumped by sync tools (Obsidian, Nextcloud) without content changes — manifest now stores content hash alongside mtime; mtime bump triggers an MD5 check before re-extraction (#593)
- Feat: R language support — `.r` files classified as code and processed via LLM semantic extraction (#617)
- Feat: extensionless shell scripts now detected via shebang (`#!/bin/bash`, `#!/usr/bin/env python3`, etc.) and included as code (#619)
- Fix: cross-language INFERRED `calls` edges (e.g. Python→TypeScript name collision) no longer appear as top surprising connections in GRAPH_REPORT.md (#630)
- Fix: `cluster-only` CLI silently flipped directed graphs to undirected — `directed` flag now read from graph.json and preserved through re-clustering (#590)
- Fix: Windows UNC / extended-length paths (`\\?\C:\...`) now normalize to consistent cache keys (#629)
- Fix: `.graphifyignore` negation patterns (`!src/lib/secrets.ts`) now work — full last-match-wins evaluation with `!` un-ignore support (#628)

## 0.6.1 (2026-05-01)

- Fix: `.graphifyignore` discovery now uses correct gitignore semantics — outer rules are loaded first so inner (closer) rules always win via last-match-wins, matching standard gitignore behavior (#643)
- Fix: without a VCS root, `.graphifyignore` discovery is now hermetic to the scan folder — no leakage across sibling projects in a shared workspace (#643)
- Fix: anchored patterns (leading `/`) in a parent `.graphifyignore` now correctly apply only relative to their own directory, not the scan root (#643)
- Fix: trailing spaces in patterns are now handled per gitignore spec — unescaped trailing spaces are stripped, `vendor\ ` (escaped) is preserved (#643)

## 0.6.0 (2026-05-01)

- Feat: SQL AST extractor — `.sql` files now processed deterministically via tree-sitter. Extracts tables, views, functions/procedures, foreign key references, and FROM/JOIN reads_from edges. No LLM needed. Requires `pip install 'graphifyy[sql]'` (#349)
- Feat: `xlsx_extract_structure()` utility — extracts sheet names, named tables, and column headers from .xlsx files as structural nodes

## 0.5.7 (2026-04-30)

- Feat: YAML/YML files now indexed for semantic extraction — Kubernetes, Kustomize, Helm, and any YAML corpus now picked up automatically (#633)

## 0.5.6 (2026-04-30)

- Fix: `NameError: name '_os' is not defined` crash after `graphify update` — this was fixed in v5 branch but not released to PyPI (#618, #612)

## 0.5.5 (2026-04-29)

- Feat: Kimi K2.6 backend — `pip install 'graphifyy[kimi]'` + `MOONSHOT_API_KEY` routes semantic extraction through Kimi K2.6. 3-6x richer relation extraction at ~3x lower cost. Claude remains default; Kimi is opt-in.
- Fix: phantom god nodes (#598) — member-call callees (`this.logger.log()` → `log`) no longer cross-file resolved. Go package-qualified calls (`pkg.Func()`) correctly preserved. Affects JS/TS, Go, Rust, Swift, Kotlin, Scala, PHP, C++, C#, Zig, Elixir.
- Fix: `concept` file_type no longer triggers validation warnings (#601)
- Fix: `graphify update` remembers scan root via `graphify-out/.graphify_root` — no path argument needed on subsequent runs
- Fix: Kimi K2.6 temperature 400 error — temperature param is now skipped for Kimi backends (model enforces its own fixed value) (#610)
- Fix: community labels deleted in Step 9 cleanup — `.graphify_labels.json` is now preserved so wiki/obsidian/HTML retain human-readable names after re-cluster (#608)
- Fix: `NameError: name '_os' is not defined` in `graphify update` Kimi tip (#612)
- Fix: `SyntaxWarning` in `__main__.py` for shell glob pattern with backslash escapes
- Fix: Python upper bound removed — `requires-python = ">=3.10"` now supports Python 3.14+ (#607)

## 0.5.4 (2026-04-28)

- Fix: SSRF DNS rebinding — `safe_fetch` now patches `socket.getaddrinfo` for the full request duration (#591)
- Fix: yt-dlp SSRF bypass — `download_audio` now calls `validate_url` before handing URL to yt-dlp (#592)

## 0.5.3 (2026-04-27)

- Fix: cache namespace — AST and semantic entries now live in `cache/ast/` and `cache/semantic/` subdirectories; flat entries read as migration fallback

## 0.5.2 (2026-04-26)

- Fix: PreToolUse hook now matches on `Bash` instead of `Glob|Grep` for Claude Code v2.1.117+

## 0.5.1 (2026-04-25)

- Fix: node ID collision for same-named files in different directories
- Fix: `source_file` paths relativized before return so `graph.json` is portable
- Fix: desync guard — `to_json()` returns bool; report only written on successful JSON write
- Feat: TypeScript `@/` path aliases resolved via `tsconfig.json`
- Feat: Show All / Hide All buttons in HTML community panel

## 0.5.0 (2026-04-24)

- Feat: `graphify clone <github-url>` — clone and graph any public repo
- Feat: `graphify merge-graphs` — combine multiple `graph.json` outputs into one cross-repo graph
- Feat: `CLAUDE_CONFIG_DIR` support in `graphify install`
- Feat: shrink guard — `to_json()` refuses to overwrite with a smaller graph
- Feat: `build_merge()` for safe incremental updates
- Feat: duplicate node deduplication via `deduplicate_by_label()`
- Fix: `graphify-out/` excluded from source scanning

## 0.4.23 (2026-04-18)

- Fix: stale skill version warning persists after running `graphify install` when multiple platforms were previously installed — `graphify install` now refreshes `.graphify_version` in all other known skill directories so the warning clears across the board (#178)
- Fix: `.html` files silently skipped during detection — added `.html` to `DOC_EXTENSIONS`; HTML pages, docs, and web project content now indexed correctly (#260)
- Fix: `_rebuild_code` (watch/update/hook) fails entirely on graphs > 5000 nodes because `to_html` raises `ValueError` — wrapped in its own try/except so `graph.json` and `GRAPH_REPORT.md` always land; stale `graph.html` from a previous smaller run is removed (#432)
- Fix: Go stdlib imports (e.g. `"context"`) produced `imports_from` edges pointing at local files of the same basename — Go import node IDs now prefixed `go_pkg_` using the full import path, eliminating false cycle-dependency pairs (#431)

## 0.4.22 (2026-04-18)

- Fix: AST cache written to `src/graphify-out/cache/` instead of project root when all code files share a common prefix like `src/` — `extract()` now called with explicit `cache_root=watch_path` in `_rebuild_code` and `cache_root=Path('.')` in the Codex skill AST step (#429)
- Fix: `.mdx` files silently skipped during detection — added `.mdx` to `DOC_EXTENSIONS` in `detect.py`; MDX-based corpora (Next.js, Docusaurus, Astro) now indexed correctly (#428)

## 0.4.21 (2026-04-17)

- Fix: `graphify cluster-only` crashed with `KeyError: 'total_files'` in `report.py` — cluster-only skips detection so the stats dict was empty; now passes a `warning` key so the report skips the file-stats section (#422)
- Fix: `/graphify --update` dropped all existing graph nodes — the merge block built a correct in-memory `G_existing` but never wrote it back to `.graphify_extract.json`, so Step 4 rebuilt from the new-extraction-only file; merged result is now serialized back before Step 4 runs (#423)

## 0.4.20 (2026-04-17)

- Fix: JS/MJS `imports_from` edges were silently dropped for files that use `../subdir/file.mjs` style imports — `Path.parent / raw` left `..` segments unnormalized, so the generated target ID didn't match the actual file node ID. Fixed with `os.path.normpath` (#414)
- Fix: `graphify update .` and `graphify cluster-only` now generate `graph.html` alongside `graph.json` and `GRAPH_REPORT.md` — previously only the skill generated the interactive HTML (#418)

## 0.4.19 (2026-04-17)

- Fix: AST and semantic extraction no longer produce mismatched node IDs — `build_from_json` now normalises IDs before dropping edges, so edges survive when the LLM generates slightly different casing or punctuation than the AST extractor (#390)
- Fix: cross-file call resolution extended to Go, Rust, Zig, PowerShell, and Elixir — unresolved callees are now saved as `raw_calls` and resolved globally in a post-pass, matching existing behaviour for Python, Swift, Java, C#, Kotlin, Scala, Ruby, and PHP (#298)
- Fix: Windows `graphify-out/graphify-out` nesting bug — `cache_dir` and `_rebuild_code` in watch.py now call `.resolve()` on the root path, preventing a nested output directory when graphify is run from a subdirectory (#410)
- Fix: `graphify hook install` now respects `core.hooksPath` git config (used by Husky and similar tools) — hooks are written to the configured path instead of always `.git/hooks` (#401)
- Fix: Kiro skill YAML frontmatter — `description` value is now quoted and colons replaced with dashes, preventing a parse error in Kiro's YAML loader (#385)
- Docs: added Windows PATH tip (`%APPDATA%\Python\PythonXY\Scripts`) and macOS pipx tip (`pipx ensurepath`) to the install section (#413)
- Docs: added team workflow section — committing `graphify-out/`, `.graphifyignore` usage, and recommended `.gitignore` additions (#369)

## 0.4.16 (2026-04-16)

- Fix: graphify watch crashed on all platforms with NameError because import sys was missing from watch.py (#386, #394)
- Fix: .mjs files were detected but produced 0 nodes — added .mjs to the AST extractor dispatch table (#387)
- Fix: llm.py excluded from the published wheel (local benchmarking file, not part of the public API) (#391)

## 0.4.15 (2026-04-15)

- Feat: VS Code Copilot Chat support — `graphify vscode install` installs a Python-only skill (works on Windows PowerShell) and writes `.github/copilot-instructions.md` for always-on graph context (#206)
- Fix: OpenCode plugin path used backslashes on Windows causing duplicate entries in `opencode.json` — now uses forward slashes via `.as_posix()` (#378)
- Fix: Gemini CLI on Windows now installs skill to `~/.agents/skills/` (higher priority) instead of `~/.gemini/skills/` (#368)
- Fix: `.mjs` and `.ejs` files now recognised by the AST extractor as JavaScript (#365, #372)
- Fix: `god_nodes()` field renamed from `edges` to `degree` for clarity — updated in report, wiki, serve, and all tests (#375)
- Fix: macOS `graphify watch` now uses `PollingObserver` by default to avoid missed events with FSEvents (#373)

## 0.4.14 (2026-04-15)

- Fix: cross-file call edges now emitted for all languages (Swift, Go, Rust, Java, C#, Kotlin, Scala, Ruby, PHP, and others) — previously only Python had cross-file resolution; unresolved call sites are now saved per file and resolved against a global label map in a post-pass (#348)
- Fix: PHP extractor now handles `scoped_call_expression` (static method calls like `Helper::format()`) and `class_constant_access_expression` (enum/constant references like `Status::ACTIVE`) — both were silently dropped before (#230, #232)
- Fix: `--wiki` flag now runs `to_wiki()` as Step 6b in the skill pipeline before the cleanup step — community labels are available and the wiki is written to `graphify-out/wiki/` (#229, #354)
- Fix: `graphify install --platform opencode` now also installs the `.opencode/plugins/graphify.js` plugin, matching what `graphify opencode install` does (#356)
- Fix: `extract()` accepts explicit `cache_root` parameter so subdirectory runs no longer write cache to `<subdir>/graphify-out/cache/` (#350)
- Fix: `os.replace` in cache writer falls back to `shutil.copy2` on `PermissionError` (Windows WinError 5) (#287)
- Fix: `graphify update` exits with code 1 on rebuild failure instead of silently returning (#287)
- Fix: `CLAUDE.md`, Cursor, and Antigravity templates now use `graphify update .` instead of hardcoded `python3 -c` invocation (#287)
- Fix: `skill-kiro.md` added to `pyproject.toml` package-data — `graphify kiro install` was failing on fresh pip installs (#352)
- Fix: `betweenness_centrality` in `suggest_questions` uses `k=100` approximate sampling for graphs over 1000 nodes; `edge_betweenness_centrality` returns early for graphs over 5000 nodes (#341)

## 0.4.13 (2026-04-14)

- Add: Verilog/SystemVerilog support — `.v` and `.sv` files extracted via tree-sitter-verilog (modules, functions, tasks, package imports, module instantiations with `instantiates` edges) (#325)
- Fix: hyperedge polygons render correctly on HiDPI/Retina displays — `afterDrawing` callback ctx is now used directly (already in network coordinate space), removing the double-applied transform and incorrect `canvas.width/2` DPR anchor (#334)
- Fix: AGENTS.md and GEMINI.md rebuild rule now uses `graphify update .` instead of hardcoded `python3 -c "..."` — correct Python is resolved through the graphify binary, no more interpreter mismatches in Nix/pipx/uv environments (#324)
- Fix: `graphify query` and `graphify explain` no longer crash with `AttributeError` when a node has `label: null` — all `.get("label", "")` calls guarded with `or ""` to handle explicit null values (#323)

## 0.4.12 (2026-04-13)

- Add: Kiro IDE/CLI support — `graphify kiro install` writes `.kiro/skills/graphify/SKILL.md` (invoked via `/graphify`) and `.kiro/steering/graphify.md` (`inclusion: always` — always-on context before every conversation) (#319, #321)
- Fix: cache `file_hash()` now uses the path relative to project root instead of the resolved absolute path — cache entries are now portable across machines, CI runners, and different checkout directories (#311)

## 0.4.11 (2026-04-13)

- Fix: `graphify query` no longer crashes with `ValueError` on MultiGraph graphs — `G.edges[u, v]` replaced with `G[u][v]` + MultiGraph guard (#305)
- Fix: `graphify query` no longer crashes with `AttributeError: 'NoneType' has no attribute 'lower'` when a node has a null `source_file` (#307)
- Fix: MCP server launched from a different directory now correctly derives the `graphify-out` base from the absolute path provided, instead of CWD (#309)
- Fix: `.graphifyignore` patterns from a parent directory now fire correctly when graphify is run on a subfolder — patterns are matched against paths relative to both the scan root and the `.graphifyignore`'s anchor directory (#303)

## 0.4.10 (2026-04-13)

- Fix: `graphify install --platform cursor` no longer crashes — passes `Path(".")` to `_cursor_install` (#281)
- Fix: `_agents_uninstall` now only removes the OpenCode plugin when uninstalling the `opencode` platform — other platforms were incorrectly having their OpenCode plugin stripped (#276)
- Fix: misleading comment in query `--graph` path handler removed (#278)
- Fix: `skill-codex.md` — `wait` → `wait_agent` (correct Codex tool name) (#273)
- Add: `svg = ["matplotlib"]` optional extra in pyproject.toml; `matplotlib` added to `[all]` extra (#288)
- Fix: `graspologic` dependency now has `python_version < '3.13'` env marker in `leiden` and `all` extras — prevents install failures on Python 3.13+ (#290)
- Add: Dart/Flutter support — `.dart` files extracted via regex (classes, mixins, functions, imports); added to `CODE_EXTENSIONS` (#292)
- Add: `norm_label` field written at build time in `to_json()` for diacritic-insensitive search; `_score_nodes` and `_find_node` in `serve.py` use `norm_label` with Unicode NFKD normalization fallback (#293)
- Add: Hermes Agent platform support — `graphify hermes install` writes skill to `~/.hermes/skills/graphify/SKILL.md` and AGENTS.md (#251)
- Add: PHP extractor now captures static property access (`Foo::$bar`) as `uses_static_prop` edges (#234)
- Add: PHP extractor now captures `config()` helper calls as `uses_config` edges pointing to the first config key segment (#236)
- Add: PHP extractor now captures service container bindings (`bind`, `singleton`, `scoped`, `instance`) as `bound_to` edges (#238)
- Add: PHP extractor now captures `$listen` / `$subscribe` event listener arrays as `listened_by` edges (#240)
- Add: `prune_dangling_edges()` utility in `export.py` — removes edges whose source/target is not in the node set (#294)
- Fix: Antigravity install injects YAML frontmatter into skill file for native tool discovery; rules now include MCP navigation hint; prints MCP config snippet (#268)
- Fix: Windows hook tests now use platform-aware assertions instead of POSIX executable bit checks (#279)
- Add: CLI commands `path`, `explain`, `add`, `watch`, `update`, `cluster-only` now work as bare terminal commands (not just AI skill invocations) — documented in `--help` output (#277)

## 0.4.8 (2026-04-12)

- Fix: platform skill files (aider, codex, opencode, claw, droid, copilot, windows) no longer contain Claude-specific language — references to "Claude" as the AI model replaced with platform-agnostic wording (#272)

## 0.4.7 (2026-04-12)

- Fix: `watch` semantic edge preservation was always empty — `graph.json` uses `links` key but code read `edges` (#269)
- Fix: `graphify claw install` now writes to `.openclaw/` (correct OpenClaw directory) instead of `.claw/` (#208)
- Add: Blade template support — `@include`, `<livewire:>` components, and `wire:click` bindings extracted from `.blade.php` files (#242)
- Docs: WSL/Linux MCP setup note — package name is `graphifyy`, use `.venv/bin/python3` in `.mcp.json` (#250)

## 0.4.6 (2026-04-12)

- Add: Google Antigravity support — `graphify antigravity install` writes `.agent/rules/graphify.md` (always-on rules) and `.agent/workflows/graphify.md` (`/graphify` slash command) (#203, #199, #53)

## 0.4.5 (2026-04-12)

- Fix: MCP server no longer crashes with `ValidationError` on blank lines sent between JSON messages by some clients (#201)

## 0.4.4 (2026-04-12)

- Fix: `watch` now preserves INFERRED/AMBIGUOUS edges (code↔doc rationale links) across rebuilds — previously all cross-type edges were dropped (#261)
- Fix: Codex hook no longer emits `permissionDecision:allow` which codex-cli 0.120.0 rejects (#249)
- Fix: Common lockfiles (`package-lock.json`, `yarn.lock`, `Cargo.lock`, etc.) are now skipped during detection, preventing token drain on large JS/Rust/Python projects (#266)

## 0.4.3 (2026-04-12)

- Fix: JS/TS relative imports now resolve to full-path node IDs — previously all `imports_from` edges were silently dropped on large TypeScript codebases (#256)
- Fix: Python relative imports (`from .foo import bar`) now resolve correctly to full-path node IDs (#256)
- Fix: `watch --rebuild_code` now merges fresh AST with existing semantic nodes from docs/papers instead of overwriting them (#253)
- Fix: Windows hooks now fall back to `python` if `python3` is not found; exits cleanly if neither has graphify installed (#244)
- Fix: `surprising_connections` / `suggest_questions` no longer crash with `KeyError` on stale `_src`/`_tgt` edge hints after node merges (#226)
- Add: `.vue` and `.svelte` files now recognized as code and included in extraction (#254)

## 0.4.2 (2026-04-11)

- Fix: same-basename files in different directories produced colliding node IDs — now uses full path (#211)
- Fix: edges using `from`/`to` keys instead of `source`/`target` were silently dropped (#216)
- Fix: empty graphs (no edges) crashed `to_html` with `ZeroDivisionError` (#217)
- Fix: post-commit hook skipped `.tsx`, `.jsx`, and other valid code extensions due to stale allowlist (#222)
- Fix: NetworkX ≤3.1 serialises edges as `links` — now accepted alongside `edges` (#212)
- Fix: version warning fired during `install`/`uninstall` and duplicated on shared paths (#220)
- Fix: all file IO now uses `encoding="utf-8"` — prevents crashes on Windows with CJK or emoji labels; hook writes use `newline="\n"` to prevent CRLF shebang breakage (#204)
- Fix: Obsidian export — node labels ending in `.md` produced `.md.md` filenames; `GRAPH_REPORT.md` now links to community hub files so vault stays in one connected component (#221)

## 0.4.1 (2026-04-10)

- Fix: `collect_files()` in `extract.py` now respects `.graphifyignore` — previously ignored patterns, causing thousands of unwanted files (e.g. `node_modules/`) to be scanned (#188)
- Fix: skill.md Step B2 now explicitly requires `subagent_type="general-purpose"` — using `Explore` type silently dropped extraction results since it is read-only and cannot write chunk files (#195)
- Fix: Step B3 now warns when chunk files are missing from disk instead of silently skipping them

## 0.4.0 (2026-04-10)

- Branch: v4 — video and audio corpus support
- Add: drop `.mp4`, `.mp3`, `.wav`, `.mov`, `.webm`, `.m4a`, `.ogg`, `.mkv`, `.avi`, `.m4v` files into any corpus and graphify transcribes them locally with faster-whisper before extraction
- Add: YouTube and URL download via yt-dlp — `/graphify add https://youtube.com/...` downloads audio-only and feeds it through the same Whisper pipeline
- Add: domain-aware Whisper prompts — the coding agent reads god nodes from the corpus and writes a one-sentence domain hint for Whisper itself, no separate API call
- Add: `graphify-out/transcripts/` cache — transcripts cached by filename; YouTube URLs cached by hash so re-runs skip already-transcribed files
- Requires: `pip install 'graphifyy[video]'` for faster-whisper and yt-dlp

## 0.3.29 (2026-04-10)

- Add: video and audio corpus support — drop `.mp4`, `.mp3`, `.wav`, `.mov`, `.webm`, `.m4a`, `.ogg`, `.mkv`, `.avi`, `.m4v` files into any corpus and graphify transcribes them with faster-whisper before extraction
- Add: YouTube and URL video download — pass a YouTube link (or any video URL) to `/graphify add <url>` and yt-dlp downloads audio-only, which is then transcribed and added to the corpus automatically
- Add: domain-aware Whisper prompts — god nodes from non-video files are used to build a one-sentence domain hint for Whisper via a cheap Haiku call, improving transcript accuracy on technical content
- Add: `graphify-out/transcripts/` cache — transcripts are cached by filename so re-runs skip already-transcribed files; URLs cached by hash
- Requires: `pip install 'graphifyy[video]'` for faster-whisper + yt-dlp

## 0.3.28 (2026-04-10)

- Fix: hook installers (Claude Code, Codex, Gemini CLI) now always remove and reinstall the hook on re-run — users upgrading from old versions no longer get stuck with a broken hook format (#182)
- Fix: rationale node labels no longer contain bare `\r` characters on Windows/WSL CRLF files — breaks Obsidian export was silently producing invalid filenames (#176)
- Fix: `skill-windows.md` now includes `--wiki`, `--obsidian-dir`, and `--directed` which were missing vs the main skill (#177)

## 0.3.27 (2026-04-10)

- Fix: graphify install --platform gemini now also copies the skill file to ~/.gemini/skills/graphify/SKILL.md so the /graphify trigger works in Gemini CLI (#174)

## 0.3.26 (2026-04-10)

- Fix: MCP server no longer uses a circular path validation when loading a graph outside cwd — now validates the path exists and ends in `.json` instead of checking containment within its own parent directory (security fix)

## 0.3.25 (2026-04-09)

- Fix: `graphify install --platform gemini` now routes to `gemini_install()` instead of erroring — `gemini` was missing from `_PLATFORM_CONFIG` (#171)
- Fix: `graphify install --platform cursor` now routes to `_cursor_install()` the same way (#171)
- Fix: `serve.py` `validate_graph_path` now passes `base=Path(graph_path).resolve().parent` so MCP server works when graph is outside cwd (#170)
- Fix: MCP `call_tool()` handler now wraps dispatch in try/except — exceptions in tool handlers return graceful error strings instead of crashing the stdio loop (#163)
- Fix: `_load_graphifyignore` now walks parent directories up to the `.git` boundary, matching `.gitignore` discovery behavior — subdirectory scans now inherit root ignore patterns (#168)
- Add: Aider platform support — `graphify install --platform aider` copies skill to `~/.aider/graphify/SKILL.md`; `graphify aider install/uninstall` writes AGENTS.md rules (#74)
- Add: GitHub Copilot CLI platform support — `graphify install --platform copilot` copies skill to `~/.copilot/skills/graphify/SKILL.md`; `graphify copilot install/uninstall` for skill management (#134)
- Add: `--directed` flag — `build_from_json()` and `build()` now accept `directed=True` to produce a `DiGraph` preserving edge direction (source→target); `cluster()` converts to undirected internally for Leiden; `graph_diff` edge key handles directed graphs correctly (#125)
- Add: Frontmatter-aware cache for Markdown files — `.md` files hash only the body below YAML frontmatter, so metadata-only changes (reviewed, status, tags) no longer invalidate the cache (#131)

## 0.3.24 (2026-04-09)

- Fix: `graphify codex install` (and opencode) no longer exits early when `AGENTS.md` already has the graphify section — partial installs with a missing `.codex/hooks.json` can now recover on re-run (#153)

## 0.3.23 (2026-04-09)

- Add: Gemini CLI support — `graphify gemini install` writes a `GEMINI.md` section and a `BeforeTool` hook in `.gemini/settings.json` that fires before file-read tool calls (#105)
- Add: sponsor nudge at pipeline completion — all skill files now print a one-line sponsor link after a fresh build, not on `--update` runs

## 0.3.22 (2026-04-09)

- Add: Cursor support — `graphify cursor install` writes `.cursor/rules/graphify.mdc` with `alwaysApply: true` so the graph context is always included; `graphify cursor uninstall` removes it (#137)
- Fix: `_rebuild_code()` KeyError — `detected[FileType.CODE]` corrected to `detected['files']['code']` matching `detect()`'s actual return shape; was silently breaking git hooks on every commit (#148)
- Fix: `to_json()` crash on NetworkX 3.2.x — `node_link_data(G, edges="links")` now falls back to `node_link_data(G)` on older NetworkX, same shim already used for `node_link_graph` (#149)
- Fix: README clarifies `graphifyy` is the only official PyPI package — other `graphify*` packages are not affiliated (#129)

## 0.3.21 (2026-04-09)

- Fix: Codex PreToolUse hook now places `systemMessage` at the top level of the output JSON instead of inside `hookSpecificOutput` — matches the strict schema enforced by codex-cli 0.118.0+ which uses `additionalProperties: false` (#138)
- Fix: git hooks now use `#!/bin/sh` instead of `#!/bin/bash` — Git for Windows ships `sh.exe` not `bash`, so hooks were silently skipped on Windows (#140)

## 0.3.20 (2026-04-09)

- Fix: XSS in interactive HTML graph — node labels, file types, community names, source files, and edge relations now HTML-escaped before `innerHTML` injection; neighbor link `onclick` uses `JSON.stringify` instead of raw string interpolation
- Add: OpenCode `tool.execute.before` plugin — `graphify opencode install` now writes `.opencode/plugins/graphify.js` and registers it in `opencode.json`, firing the graph reminder before bash calls (equivalent to Claude Code's PreToolUse hook) (#71)
- Fix: AST-resolved call edges now carry `confidence=EXTRACTED, weight=1.0` instead of INFERRED/0.8 — tree-sitter call resolution is deterministic, not probabilistic (#127)
- Fix: `tree-sitter>=0.23.0` now pinned in dependencies and `_check_tree_sitter_version()` guard added — stale environments now get a clear `RuntimeError` with upgrade instructions instead of a cryptic `TypeError` deep in the AST pipeline (#89)

## 0.3.19 (2026-04-09)

- Fix: install step now tries plain `pip install` before falling back to `--break-system-packages` — Homebrew and PEP 668 managed environments no longer risk environment corruption (#126)

## 0.3.18 (2026-04-09)

- Fix: `--watch` mode now respects `.graphifyignore` — `_rebuild_code` was calling `collect_files()` directly instead of `detect()`, bypassing ignore patterns (#120)
- Fix: Codex PreToolUse hook now uses `systemMessage` instead of `additionalContext` — Codex does not support `additionalContext` and was returning an error (#121)
- Fix: Trae link corrected from `trae.com` to `trae.ai` in README, README.zh-CN.md, README.ja-JP.md, README.ko-KR.md (#122)
- Docs: Korean README added (README.ko-KR.md) (#112)
- Refactor: `save_query_result` inline Python blocks in all 6 skill files replaced with `graphify save-result` CLI command — shorter, maintainable, less tokens for LLM (#114)
- Add: `graphify save-result` CLI subcommand — saves Q&A results to memory dir without inline Python
- Fix: HTML graph click detection now uses hover-tracking (`hoveredNodeId`) — more reliable than vis.js click params on small/dense nodes (#82)
- Fix: `mkdir -p graphify-out` now runs before writing `.graphify_python` in `skill.md` — prevents write failure on first run; `.graphify_python` no longer deleted in Step 9 cleanup across all skill files so follow-up commands keep their interpreter (#93)
- Fix: `skill-trae.md` added to `pyproject.toml` package-data — Trae users no longer hit `ModuleNotFoundError` after `pip install` (#102)
- Fix: `analyze.py` and `watch.py` now import extension sets from `detect.py` instead of local copies — Swift, Lua, Zig, PowerShell, Elixir, JSX, Julia, Objective-C files no longer misclassified as documents (#109)
- Refactor: dead `build_graph()` function removed from `cluster.py` (#109)

## 0.3.17 (2026-04-08)

- Add: Julia (.jl) support — modules, structs, abstract types, functions, short functions, using/import, call edges, inherits edges via tree-sitter-julia (#98)
- Fix: Semantic extraction chunks now group files by directory so related artifacts land in the same chunk, reducing missed cross-chunk relationships (#65)
- Fix: `tree-sitter>=0.21` now pinned in dependencies — prevents silent empty AST output when older tree-sitter is installed with newer language bindings (#52)
- Add: Progress output every 100 files during AST extraction so large projects don't appear to hang (#52)

## 0.3.16 (2026-04-08)

- Fix: `graphify query`, `serve`, and `benchmark` now work on NetworkX < 3.4 — version-safe shim for `node_link_graph()` at all call sites (#95)
- Fix: `.jsx` files now detected and extracted via the JS extractor — added to `CODE_EXTENSIONS` and `_DISPATCH` (#94)
- Fix: `.graphify_python` no longer deleted in Step 9 cleanup across all 6 skill files — pipx users no longer hit `ModuleNotFoundError` on follow-up commands (#92)

## 0.3.15 (2026-04-08)

- Feat: Trae and Trae CN platform support (`graphify install --platform trae` / `trae-cn`)
- Fix: `skill-droid.md` was missing from PyPI package data — Factory Droid users couldn't install the skill
- Fix: XSS in HTML legend — community labels now HTML-escaped before `innerHTML` injection
- Fix: Shebang allowlist validation in `hooks.py` and all 6 skill files — prevents metacharacter injection from malicious binaries
- Fix: `louvain_communities()` kwargs now inspected at runtime for cross-version NetworkX compatibility
- Fix: pipx installs now detected correctly in git hooks (reads shebang from graphify binary)
- Fix: graspologic ANSI escape codes no longer corrupt PowerShell 5.1 scroll buffer
- Docs: Japanese README added
- Docs: `graph.json` + LLM workflow example added to README
- Docs: Codex PreToolUse hook now documented in platform table

## 0.3.14 (2026-04-08)

- Fix: `graphify codex install` now also writes a PreToolUse hook to `.codex/hooks.json` so the graph reminder fires before every Bash tool call (#86)
- Fix: `--update` now prunes ghost nodes from deleted files before merging new extraction (#51)

## 0.3.13 (2026-04-08)

- Fix: PreToolUse hook now outputs `additionalContext` JSON so Claude actually sees the graph reminder before Glob/Grep calls (#83)
- Fix: Go AST method receivers and type declarations now use package directory scope, eliminating disconnected duplicate type nodes across files in the same package (#85)
- Fix: PDFs inside Xcode asset catalogs (`.imageset`, `.xcassets`) are no longer misclassified as academic papers (#52)
- Fix: `_resolve_cross_file_imports` is now guarded with `if py_paths` and wrapped in try/except so a Python parser crash can't abort extraction for non-Python files (#52)
- Fix: Skill intermediate files (`.graphify_*.json`) now live in `graphify-out/` instead of project root, preventing git pollution (#81)

## 0.3.12 (2026-04-07)

- Fix: `sanitize_label` was double-encoding HTML entities in the interactive graph (`&amp;lt;` instead of `&lt;`) — removed `html.escape()` from `sanitize_label`; callers that inject directly into HTML now call `html.escape()` themselves (#66)
- Fix: `--wiki` flag missing from `skill.md` usage table (#55)

## 0.3.11 (2026-04-07)

- Fix: Louvain fallback hangs indefinitely on large sparse graphs — added `max_level=10, threshold=1e-4` to prevent infinite loops while preserving community quality (#48)

## 0.3.10 (2026-04-07)

- Fix: Windows UnicodeEncodeError during `graphify install` — replaced arrow character with `->` in all print statements (#47)
- Add: skill version staleness check — warns when installed skill is older than the current package, across all platforms (#46)

## 0.3.9 (2026-04-07)

- Add: `follow_symlinks` parameter to `detect()` and `collect_files()` — opt-in symlink following with circular symlink cycle detection (#33)
- Fix: `watch.py` now uses `collect_files()` instead of manual rglob loop for consistency
- Docs: Codex uses `$graphify .` not `/graphify .` (#36)
- Test: 5 new symlink tests (367 total)

## 0.3.8 (2026-04-07)

- Add: C# inheritance and interface implementation extraction — `base_list` now emits `inherits` edges for both simple (`identifier`) and generic (`generic_name`) base types (#45)
- Add: `graphify query "<question>"` CLI command — BFS/DFS traversal of `graph.json` without needing Claude Code skill (`--dfs`, `--budget N`, `--graph <path>` flags)
- Test: 2 new C# inheritance tests (362 total)

## 0.3.7 (2026-04-07)

- Add: Objective-C support (`.m`, `.mm`) — `@interface`, `@implementation`, `@protocol`, method declarations, `#import` directives, message-expression call edges
- Add: `--obsidian-dir <path>` flag — write Obsidian vault to a custom directory instead of `graphify-out/obsidian`
- Fix: semantic cache was only saving 4/17 files — relative paths from subagents now resolved against corpus root before existence check
- Fix: 75 validation warnings per run for `file_type: "rationale"` — added `"rationale"` to `VALID_FILE_TYPES`
- Test: 6 Objective-C tests; `.m`/`.mm` added to `test_collect_files_from_dir` supported set (360 total)

## 0.3.0 (2026-04-06)

- Add: multi-platform support — Codex (`skill-codex.md`), OpenCode (`skill-opencode.md`), OpenClaw (`skill-claw.md`)
- Add: `graphify install --platform <codex|opencode|claw>` routes skill to correct config directory
- Add: `graphify codex install` / `opencode install` / `claw install` — writes AGENTS.md for always-on graph-first behaviour
- Add: `graphify claude uninstall` / `codex uninstall` / `opencode uninstall` / `claw uninstall`
- Add: MIT license
- Fix: `build()` was silently dropping hyperedges when merging multiple extractions
- Refactor: `extract.py` 2527 → 1588 lines — replaced 12 copy-pasted language extractors with `LanguageConfig` dataclass + `_extract_generic()`
- Docs: clustering is graph-topology-based (no embeddings) — explained in README
- Docs: all missing flags documented (`--cluster-only`, `--no-viz`, `--neo4j-push`, `query --dfs`, `query --budget`, `add --author`, `add --contributor`)

## 0.2.2 (2026-04-06)

- Add: `graphify claude install` — writes graphify section to local CLAUDE.md + PreToolUse hook in `.claude/settings.json`
- Add: `graphify claude uninstall` — removes section and hook
- Add: `graphify hook install` — installs post-commit and post-checkout git hooks (platform-agnostic)
- Add: `graphify hook uninstall` / `hook status`
- Add: `graphify benchmark` CLI command
- Fix: node deduplication documented at all three layers

## 0.1.8 (2026-04-05)

- Fix: follow-up questions now check for wiki first (graphify-out/wiki/index.md) before falling back to graph.json
- Fix: --update now auto-regenerates wiki if graphify-out/wiki/ exists
- Fix: community articles show truncation notice ("... and N more nodes") when > 25 nodes
- UX: pipeline completion message now lists all available flags and commands so users know what graphify can do

## 0.1.7 (2026-04-05)

- Add: `--wiki` flag — generates Wikipedia-style agent-crawlable wiki from the graph (index.md + community articles + god node articles)
- Add: `graphify/wiki.py` module with `to_wiki()` — cross-community wikilinks, cohesion scores, audit trail, navigation footer
- Add: 14 wiki tests (245 total)
- Fix: follow-up question example code now correctly splits node labels by `_` to extract verb prefixes (previous version used `def`/`fn` prefix matching which always returned zero results)

## 0.1.6 (2026-04-05)

- Fix: follow-up questions after pipeline now answered from graph.json, not by re-exploring the directory (was 25 tool calls / 1m30s; now instant)
- Skill: added "Answering Follow-up Questions" section with graph query patterns

## 0.1.5 (2026-04-05)

- Perf: semantic extraction chunks 12-15 → 20-25 files (fewer subagent round trips)
- Perf: code-only corpora skip semantic dispatch entirely (AST handles it)
- Perf: print timing estimate before extraction so the wait feels intentional
- Fix: 5 skill gaps - --graphml in Usage table, --update manifest timing, query/path/explain graph existence check, --no-viz clarity
- Refactor: dead imports removed (shutil, sys, inline os); _node_community_map() helper replaces 8 copy-pasted dict comprehensions; to_html() split into _html_styles() + _html_script(); serve.py call_tool() if/elif chain replaced with dispatch table
- Test: end-to-end pipeline integration test (detect → extract → build → cluster → analyze → report → export)

## 0.1.4 (2026-04-05)

- Replace pyvis with custom vis.js HTML renderer - node size by degree, click-to-inspect panel with clickable neighbors, search box, community filter, physics clustering
- HTML graph generated by default on every run (no flag needed)
- Token reduction benchmark auto-runs after every pipeline on corpora over 5,000 words
- Fix: 292 edge warnings per run eliminated - stdlib/external edges now silently skipped
- Fix: `build()` cross-extraction edges were silently dropped - now merged before assembly
- Fix: `pip install graphify` → `pip install graphifyy` in skill Step 1 (critical install bug)
- Add: `--graphml` flag implemented in skill pipeline (was documented but not wired up)
- Remove: pyvis dependency, dead lib/ folder, misplaced eval reports from tests/
- Add: 5 HTML renderer tests (223 total)

## 0.1.3 (2026-04-04)

- Fix: `pyproject.toml` structure - `requires-python` and `dependencies` were incorrectly placed under `[project.urls]`
- Add: GitHub repository and issues URLs to PyPI page
- Add: `keywords` for PyPI search discoverability
- Docs: README clarifies Claude Code requirement, temporary PyPI name, worked examples footnote

## 0.1.1 (2026-04-04)

- Add: CI badge to README (GitHub Actions, Python 3.10 + 3.12)
- Add: ARCHITECTURE.md - pipeline overview, module table, extraction schema, how to add a language
- Add: SECURITY.md - threat model, mitigations, vulnerability reporting
- Add: `worked/` directory with eval reports (karpathy-repos 71.5x benchmark, httpx, mixed-corpus)
- Fix: pytest not found in CI - added explicit `pip install pytest` step
- Fix: README test count (163 → 212), language table, worked examples links
- Docs: README reframed as Claude Code skill; Karpathy problem → graphify answer framing

## 0.1.0 (2026-04-03)

Initial release.

- 13-language AST extraction via tree-sitter (Python, JS, TS, Go, Rust, Java, C, C++, Ruby, C#, Kotlin, Scala, PHP)
- Leiden community detection via graspologic with oversized community splitting
- SHA256 semantic cache - warm re-runs skip unchanged files
- MCP stdio server - `query_graph`, `get_node`, `get_neighbors`, `shortest_path`, `god_nodes`
- Memory feedback loop - Q&A results saved to `graphify-out/memory/`, extracted on `--update`
- Obsidian vault export with wikilinks, community tags, Canvas layout
- Security module - URL validation, safe fetch with size cap, path guards, label sanitisation
- `graphify install` CLI - copies skill to `~/.claude/skills/` and registers in `CLAUDE.md`
- Parallel subagent extraction for docs, papers, and images
