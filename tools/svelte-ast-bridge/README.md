# Svelte author-AST bridge

Graphify ships `graphify/vendor/svelte_ast_bridge.mjs` so the Python package can
parse `.svelte` files without downloading npm dependencies at runtime. The
bridge calls `parse(source, { modern: true })` from the pinned Svelte compiler
and emits compact structural facts at original source offsets. It never emits
compiled component JavaScript.

Node.js 18 or newer is required when Graphify extracts `.svelte` files. The
wheel includes the compiler bridge and all of its JavaScript dependencies, so
no runtime `npm install` is performed. If Node or the bundled compiler cannot
run, Graphify emits an explicit `svelte_ast_unavailable` diagnostic and does
not substitute regex-derived facts.

The TypeScript source is checked directly against the pinned compiler's public
`AST` discriminated unions. `src/schema-policy.ts` is the single exhaustive
fixture/intermediate policy consumed by both the bridge and corpus. `npm test`
runs that typecheck and parses the golden author-syntax corpus under
`test/fixtures/`; a Svelte upgrade must update the exhaustive classifications
and corpus before the bridge can build. Template
expressions are discovered by one `estree-walker` traversal rooted at
`ast.fragment`. `svelte2tsx` and TypeScript supply binding identity only, mapped
back to the original component offsets; generated TSX is never graphed.
`SvelteOptionsRaw` (discriminant `SvelteOptions`) is intentionally classified as
intermediate because the pinned public declaration does not emit it in the
final fragment. The corpus fails if an intermediate variant appears.

To update the compiler or bridge:

```sh
cd tools/svelte-ast-bridge
npm ci
# 1. Update the exact compiler pin and lockfile.
# 2. Let typecheck fail until every public discriminant is classified.
# 3. Add golden author syntax for every new `fixture` classification.
npm test
npm run build
```

Commit the source, lockfile, regenerated bundle, and regenerated third-party
notices together. Keep `SVELTE_COMPILER_VERSION` in
`graphify/extractors/svelte.py` synchronized with `package.json`. Run the build
twice and compare hashes before committing; the checked-in bundle is expected
to be deterministic. The pinned compiler, svelte2tsx, and TypeScript stack is
intentionally substantial (about 12.5 MB raw / 2.1 MB gzip at Svelte 5.56.6),
and the Python packaging test keeps a generous 20 MiB raw-size ceiling to catch
accidental double-bundling without turning normal upgrades into brittle diffs.
