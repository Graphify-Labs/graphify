# Graphify Evaluation — Chilean Civil-Law Corpus (2026-09-18)

**Evaluator:** Hermes Agent (live execution, AST-only path — no LLM, no API key)
**Corpus:** 4 Python modules + 4 Markdown legal documents (a doctrine index and three Chilean
Academia Judicial training guides), 8 files · ~3,010 words · 52 KB
**Pipeline:** detect → extract (AST + Markdown structure) → build → cluster → query
**Version:** graphify 0.9.63, `graphify update .` only

This is a **legal** corpus, not a typical codebase: roughly half of it is prose doctrine in
Spanish, with the accents, legal citations and emoji-prefixed headings that come with the genre.
It is also a mixed-language corpus (English query terms against Spanish documents), which turned
out to be one of the more interesting things to test.

---

## 1. Corpus Detection

```
8 files · ~3,010 words
Verdict: corpus is large enough that graph structure adds value.
```

**Finding (skeptical):** ~3,010 words is comfortably inside any modern context window, so this
verdict reads generous. The sibling example in this folder, `worked/mixed-corpus`, covers ~4,020
words and reports the opposite — that the corpus fits in a single context window. Both cannot be
right, so the size threshold is worth a second look: a corpus this small is exactly where a graph
has to justify itself on *structure*, not on volume.

---

## 2. Extraction

```
graph: 72 nodes · 91 edges · 9 communities
extraction: 100% EXTRACTED · 0% INFERRED · 0% AMBIGUOUS
token cost: 0 input · 0 output
```

Nodes by `file_type`:

| file_type | nodes | where they come from |
|---|---|---|
| `code` | 26 | Python modules (AST) |
| `document` | 21 | Markdown guides and the doctrine index |
| `rationale` | 17 | docstrings/comments and Markdown prose blocks |
| `concept` | 8 | inferred concepts with no source file (11 nodes have no `source_file` at all) |

Edges by relation: `contains` 27 · `rationale_for` 17 · `references` 11 · `imports` 11 ·
`calls` 10 · `method` 9 · `imports_from` 6 — all `_origin: ast`, all `EXTRACTED`.

**What surprised me, positively:** the Markdown documents **do** contribute real nodes on this
path, with no LLM involved. The token cost of 0 confirms it: the document nodes are built from the
Markdown *structure* (document → section headings → sub-sections), which is enough for navigation
and for the community detection to place each guide in its own cluster.

Per-file node counts:

```
13  raw/code/grafo_vinculos.py
11  (no source_file — externals/concepts)
10  raw/code/stats_tracker.py
 9  raw/code/cold_start.py
 8  raw/code/config.py
 6  raw/doctrine/README.md
 5  raw/doctrine/aj_conciliacion_laboral.md
 5  raw/doctrine/aj_etica_judicial.md
 5  raw/doctrine/aj_juicio_oral_laboral.md
```

**What was NOT extracted — and this is the honest headline for legal corpora:** the *substance* of
the doctrine. The graph knows that "Guía para la Audiencia de Juicio Oral Laboral" exists and which
sections it has; it does not know what the guide says. Without the LLM path
(`/graphify --update` in an assistant, which `graphify update .` itself points to), a legal corpus
is navigable but not answerable.

---

## 3. Communities

| # | Nodes | Label |
|---|---|---|
| 0 | 15 | `stats_tracker.py` |
| 1 | 12 | `LegalGraphBuilder` |
| 2 | 9 | `cold_start.py` |
| 3 | 8 | `ColdStartInterviewEngine` |
| 4 | 7 | `config.py` |
| 5 | 6 | `Canon Doctrinal Jurídico Chileno — Open Legal Chile` |
| 6 | 5 | `Guía de Audiencia de Conciliación Laboral` |
| 7 | 5 | `Guía de Buenas Prácticas Judiciales en Temas Éticos` |
| 8 | 5 | `Guía para la Audiencia de Juicio Oral Laboral` |

Four communities for four code modules and three for three guides: at this size the partition is
essentially "one cluster per file", which is correct but not informative. The two labels that name
a *class* rather than a file (`LegalGraphBuilder`, `ColdStartInterviewEngine`) are the more useful
of the nine.

No import cycles detected.

---

## 4. God Nodes

```
 1. LegalGraphBuilder                                    8 edges
 2. safe_urlopen()                                       6
 3. ColdStartInterviewEngine                             5
 4. get_pypi_download_stats()                            5
 5. get_github_community_stats()                         5
 6. get_suite_adoption_metrics()                         5
 7. Canon Doctrinal Jurídico Chileno — Open Legal Chile   5
 8. build_quick_graph()                                  4
 9. Guía de Audiencia de Conciliación Laboral            4
10. Guía de Buenas Prácticas Judiciales en Temas Éticos  4
```

Three of the ten "core abstractions" are **legal documents**, not code. That is the right answer
for this corpus and it is genuinely useful: it tells a newcomer that the doctrine guides are
first-class structure, and it fell out of the structural parse without any model.

---

## 5. Queries (offline, BFS depth 2)

| Query | Start node(s) | Nodes | Verdict |
|---|---|---|---|
| `how does the telemetry count adoptions` | `send_anonymous_telemetry_ping()` | 16 | ✅ precise — the right function, from a paraphrase in another language |
| `legal graph builder` | `LegalGraphBuilder` | 16 | ✅ precise |
| `token savings` | `⚡ 3. Estándar de Optimización de Tokens` | 6 | ✅ excellent — an **English** query landed on a **Spanish** heading |
| `plazo para contestar la demanda en el juicio oral laboral` | the right guide + its neighbours | 10 | ⚠️ reaches the correct document, not the rule |
| `requisitos de la conciliación laboral` | `aj_conciliacion_laboral.md` | 5 | ⚠️ same: document-level answer |
| `¿qué dice el artículo 446 sobre la audiencia?` | two guides | 10 | ⚠️ same, and no article-level node exists to hit |

The cross-language label matching is the standout: Spanish headings with accents and emoji were
reachable from English queries, including one that starts with an emoji. For a Chilean legal
corpus (where every real query will be in Spanish but the agent's working language may not be),
this matters.

The last three rows are the limit, and it is the correct limit for a 0-token path — but a lawyer
reading this graph would not know it. "Which document" is not "what the rule says".

---

## 6. What it got right

- **The code graph is precise.** `send_anonymous_telemetry_ping() → safe_urlopen()` and the other
  call edges are exactly the real call sites, with `source_location` line numbers.
- **Markdown structure is enough for navigation, at zero cost.** 21 document nodes and 3 legal
  guides among the god nodes, without a single token spent.
- **Cross-language retrieval works**, including accented Spanish labels from English queries.
- **Community labels** are good enough to navigate by, and two of them named the actual classes.
- **Nothing was mislabelled as inferred.** 91/91 edges `EXTRACTED`, which for a corpus that is half
  prose is a deliberate and honest choice.

## 7. What it got wrong or missed

1. **Substance is out of reach on the AST-only path.** The corpus check counts the prose, but the
   extraction leaves it at heading level. Anyone running `graphify update .` on a legal corpus and
   reading the summary ("100% EXTRACTED") could reasonably overestimate what is in the graph. The
   tip about `/graphify --update` is printed, but it is one line among several.
2. **The corpus-size verdict contradicts a sibling example** (3,010 words "adds value" vs 4,020
   words "fits in one window").
3. **Heading labels are taken verbatim, emoji included** (`⚡ 3. Estándar de Optimización de
   Tokens`, `🏛️ 1. Obras y Tratados Canónicos Digitalizados por Capítulos`). For documents-heavy
   corpora, stripping decorative prefixes would make the node labels usable as navigation.
4. **Node ids keep accents and the full heading text**
   (`raw_doctrine_readme_1_obras_y_tratados_canónicos_digitalizados_por_capítulos`). It works, but
   ids are long and non-ASCII, which is worth knowing before using them as keys elsewhere.
5. **"Surprising Connections" surfaced nothing surprising here** — all three were the same
   `stats_tracker.py → config.py` call through `safe_urlopen()`. On a small corpus that is probably
   expected; on a legal one it means the feature needs more files before it earns its name.

---

## 8. Where this corpus comes from

The files are a slice of [Open Legal Chile](https://github.com/elpabloultron/open-legal-chile)
(Apache-2.0): a legal-tech suite that builds its own node-link graph over 58 Chilean doctrine
works and merges it with Graphify's code graph through a single idempotent call. The nine graph
questions that matter for the merge — schema keys, id conventions, whether edges survive a
round-trip — were answered by this run, which is why the evaluation is written down here instead of
being kept privately. The slice is trimmed to keep the example small; the full corpus is 58
documents.
