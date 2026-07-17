# graphify reference: add a URL and watch a folder

## For /graphify add

```bash
graphify add URL --dir raw
graphify update .
```

Use `--author` and `--contributor` when supplied. The fetched source is ordinary corpus input; the update commits it to a new native generation.

## For --watch

```bash
graphify watch INPUT_PATH
```

Watch mode keeps long-lived native readers, debounces file events, excludes concurrent writers, and atomically activates successful updates. An obsolete-format file is ignored with a rebuild warning.
