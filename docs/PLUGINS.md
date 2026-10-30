# Extractor plugins

Add a language to graphify by installing a package. graphify discovers plugins at startup; nothing in
graphify names them.

```
graphify plugins          # what is installed, how each matches, where it came from
graphify plugins --json
```

## Writing one

Declare an entry point in the plugin package's `pyproject.toml`:

```toml
[project.entry-points."graphify.extractors"]
mylang = "mypkg.graphify_plugin:PLUGIN"
```

`PLUGIN` can be a plain `dict` (so the package does not have to import graphify), a
`graphify.plugins.ExtractorPlugin`, any object with the same attributes, a zero-argument function returning
one of those, or a list of them.

```python
def extract(path):                      # called once per file, may run in a worker process
    return {"nodes": [...], "edges": [...]}

PLUGIN = {"name": "mylang", "suffixes": [".ml2"], "extract": extract}
```

### Per-file or batch

| | `extract(path[, ctx])` | `extract_batch(paths, ctx) -> {path: result}` |
|---|---|---|
| called | once per file, possibly in a worker process | once per extraction, in the main process |
| cached per file | yes (key: file content + plugin name + `cache_key`) | no |
| use for | self-contained parsers | tools that resolve names across files, or are costly to start |

Give exactly one. `ctx` (`PluginContext`) has `root`, `paths` and `log(msg)`; it is passed only if the function
takes the extra argument.

### Result shape

`{"nodes": [...], "edges": [...]}` in graphify's extraction schema. Required: node `id`, `label`; edge
`source`, `target`, `relation`. graphify fills `file_type` (`code`), `source_file` (the file),
`confidence` (`EXTRACTED`) and `confidence_score` when missing. Malformed output, an exception, or a batch that
fails is turned into a per-file error: the file is listed in `failed_sources` and the reason is printed to
stderr. A failed plugin never falls back to another extractor and never writes a half-valid graph.

### Fields

| field | meaning |
|---|---|
| `name` | unique; shown by `graphify plugins`, used by `GRAPHIFY_DISABLE_PLUGINS` |
| `suffixes`, `filenames`, `globs`, `shebangs` | what it matches (at least one) |
| `file_type` | `code` (default), `document`, `paper`, `image`, `video` |
| `priority` | higher wins when two plugins match (default 0) |
| `override_builtin` | take files graphify's own extractors already handle (default: built-ins win) |
| `cross_file` | skip the per-file cache (always true for batch plugins) |
| `cache_key` | change it to invalidate cached results when the plugin's output changes |
| `available()` | return `None` when usable, else a reason string; an unavailable plugin matches nothing and the reason is printed |
| `post_process(result, path[, ctx])` | adjust each result after extraction |
| `api` | plugin API version this was written for (current: 1); newer than graphify's is rejected |

## Environment

| variable | effect |
|---|---|
| `GRAPHIFY_PLUGINS=off` | no plugins at all |
| `GRAPHIFY_PLUGINS=mod:attr,mod2:attr2` | also load these, for plugins not installed as a package |
| `GRAPHIFY_DISABLE_PLUGINS=name,name2` | skip these plugins |

Plugins are deliberately **not** loadable from a project's `.graphifyrc`: that file belongs to the repo being
scanned, and loading code it names would let a scanned repo run code.

## Notes

- `detect` classifies a plugin's files using its `file_type`; `graphify watch` rebuilds when they change.
- Programmatic `graphify.plugins.register(...)` is process-local; parallel workers do not see it. Use an entry
  point or `GRAPHIFY_PLUGINS` for anything that must run in workers.
- Example: the separate `qlens` package provides `.q` support this way, as a batch plugin.
