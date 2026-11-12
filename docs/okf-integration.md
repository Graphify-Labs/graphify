# Using Graphify with OKF (Open Knowledge Format)

[OKF](https://github.com/GoogleCloudPlatform/knowledge-catalog/tree/main/okf) is a lightweight documentation standard that uses Markdown files with YAML frontmatter to describe concepts, resources, and bundles. It works by placing an `index.md` (or `index.mmd`) file inside each subdirectory to act as a bundle manifest.

Graphify and OKF complement each other naturally: OKF structures your knowledge, Graphify maps it into a queryable graph. But there is one friction point to be aware of.

---

## The friction point: documentation clutter in the code graph

Because OKF places `index.md` files directly inside your project subdirectories, Graphify's file scanner will encounter them alongside your source code. If Graphify scans your project without any filtering, it will index OKF bundle manifests and concept files as graph nodes — mixing documentation metadata into your code graph.

This is not a bug in either tool. Graphify is designed to include docs in the graph. The issue is one of **intentional separation**: you may want a pure code graph, a pure docs graph, or a combined one, and you need to tell Graphify which you want.

---

## The fix: `.graphifyignore`

### Option A — OKF files are isolated in a dedicated folder

If your OKF bundles live under a dedicated directory (e.g. `docs/`, `wiki/`, `curriculum/`), add that path to `.graphifyignore` at your project root:

```
# .graphifyignore
docs/
wiki/
curriculum/
```

Graphify will then build a pure code graph and ignore all OKF content.

To build a **separate docs graph** from the OKF bundle, run graphify scoped to that folder:

```
/graphify docs/
```

### Option B — OKF index files are scattered next to source files

If `index.md` files live directly beside `.py`, `.ts`, or other source files, use Graphify's AST-only mode so it ignores all Markdown:

```bash
graphify . --ast-only
```

In AST mode, Graphify runs only Pass 1 (deterministic tree-sitter parsing) and skips the semantic pass over docs entirely. No OKF files — scattered or not — will enter the graph.

### Option C — include OKF docs in the graph intentionally

If you *want* your OKF concepts to appear as nodes alongside your code (useful for tracing which code implements which knowledge concept), simply do nothing. Graphify will read the frontmatter and body of each OKF file and extract nodes and edges from them. OKF's `type:`, `tags:`, and `topic_keywords:` fields become graph metadata, and the `index.md` bundle manifests become hub nodes linking related concepts.

---

## Recommended layout when using both tools together

```
my-project/
├── src/               ← code (scanned by Graphify AST pass)
├── tests/
├── docs/              ← OKF bundles (add to .graphifyignore for a pure code graph)
│   ├── index.md       ← OKF bundle root
│   ├── concepts/
│   │   ├── index.md
│   │   └── my-concept.md
│   └── guides/
│       ├── index.md
│       └── setup.md
└── .graphifyignore
```

`.graphifyignore`:
```
docs/
```

To query only the code graph:
```
/graphify src/
```

To query only the knowledge graph:
```
/graphify docs/
```

To query both together (combined graph):
```
/graphify .
# and remove docs/ from .graphifyignore
```
