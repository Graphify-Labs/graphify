# Graphify install sandbox

The install sandbox is a Tier 1 behavioral test harness for Graphify's
installer. It installs the current source checkout inside Docker, exercises
the installer lifecycle in isolated user and project roots, and verifies the
Graphify-owned files that lifecycle should create, repair, preserve, and
remove.

Use it when changing installer commands, packaged integration files, target
specifications, cleanup behavior, or universal uninstall. It catches problems
such as wrong paths or payloads, duplicate managed Markdown, stale sidecars,
removed user content, and undeclared filesystem changes.

> **Coverage boundary:** the sandbox verifies installer-owned filesystem
> effects. It does not prove that a target tool discovers, authenticates,
> loads, or executes the installed integration.

## Prerequisites

Run the commands from a Graphify source checkout with:

- the repository development environment installed (`uv sync --all-extras`);
- a running Docker daemon available to the current user.

The examples use the repository's locked environment. If the project
environment is already active, `python` can replace `uv run --frozen python`.

## Quick start

Start with one target and one scope while developing:

```bash
uv run --frozen python tools/install_sandbox/run.py \
  --repo . \
  --target codex \
  --scope project
```

Run the complete catalog before finalizing a catalog-wide installer change:

```bash
uv run --frozen python tools/install_sandbox/run.py \
  --repo . \
  --all \
  --scope both
```

Each invocation builds the harness image before starting the container, so a
full-catalog run takes longer than a single-target run.

## Choose what to run

Exactly one of `--target` and `--all` is required.

| Argument | Meaning |
| --- | --- |
| `--repo PATH` | Graphify source checkout to install and test. |
| `--target NAME` | Run one target. Use `--help` to list names from the current catalog. |
| `--all` | Run every target plus catalog-wide installer checks. |
| `--scope user\|project\|both` | Select install roots; defaults to `both`. |
| `--output DIR` | Use an absent or empty caller-owned directory instead of managed local output. |

Without `--output`, the runner creates a managed run beneath the ignored
`tools/install_sandbox/out/` root. For example:

```text
tools/install_sandbox/out/20260726T143012Z-codex-project/
tools/install_sandbox/out/20260726T143012Z-codex-project-02/
tools/install_sandbox/out/20260726T143012Z-all-both/
```

The numeric suffix resolves same-second collisions. For example, give an agent
or CI job an empty external artifact directory:

```bash
sandbox_output_dir="$(mktemp -d /tmp/graphify-install-sandbox-codex.XXXXXX)"
uv run --frozen python tools/install_sandbox/run.py \
  --repo . \
  --target codex \
  --scope both \
  --output "$sandbox_output_dir"
```

Set `GRAPHIFY_SANDBOX_RUNTIME` only when a different Docker-compatible runtime
executable should replace the default `docker` command.

## Output ownership and lifecycle

Managed and external output have deliberately separate ownership:

- A default run is managed by the host runner. Its run ID, metadata, and
  keep-five retention policy belong to the sandbox.
- `--output DIR` is an external leaf owned by the caller. The path must either
  be absent or be an empty real directory. Symlinks, non-empty directories, and
  explicit paths beneath `tools/install_sandbox/out/` are rejected.
- The runner never prunes external output. CI, an agent, or the person who
  supplied `--output` decides how long to keep it.

Every accepted destination is fresh: the runner allocates managed directories
atomically and never reuses files from an earlier run. It allocates the
diagnostic bundle after validating the repository but before catalog preflight,
so catalog, Docker build, and runtime failures can still leave host diagnostics.

The host writes two top-level lifecycle artifacts:

| Artifact | Use |
| --- | --- |
| `run.json` | Schema version, run ID, managed flag, timestamps, repository and output paths, selection, current phase, state, and exit code. |
| `runner.log` | Phase-labelled host preflight, Docker build, and container output, mirrored to the console. |

The runner replaces `run.json` atomically as the phase or state changes, so a
reader never observes a partially written metadata file. `run.json` moves
through these states:

| State | Meaning |
| --- | --- |
| `running` | The run has been allocated and has not reached a terminal state. An uncatchable termination can leave this state behind. |
| `passed` | Exit `0`, with a complete container `manifest.json` and `report.md`. |
| `failed` | Exit `1`, with complete behavioral results that contain a product-contract failure. |
| `incomplete` | Catalog, image-build, container-runtime, or missing-output failure prevented complete behavioral results. |
| `interrupted` | The host caught `SIGINT` or `SIGTERM` and returned the conventional signal exit code. |

Before allocating a managed run, the runner removes only surplus, valid,
terminal managed runs. After finalization it keeps the newest five, counting
`passed`, `failed`, `incomplete`, and `interrupted` equally. It does not delete
`running`, malformed, unreadable, unmarked, external, or symlinked entries.
Leftover `running` entries are preserved with a warning because the runner
cannot prove that another process is not using them.

### Optional VS Code exclusions

Repository-local managed output can still add editor file-watching and search
work. If that becomes noticeable, merge these keys into your existing
workspace settings:

```json
{
  "files.watcherExclude": {
    "**/tools/install_sandbox/out/**": true
  },
  "search.exclude": {
    "**/tools/install_sandbox/out/**": true
  }
}
```

Do not overwrite an existing `.vscode/settings.json`; merge with settings
already there and keep editor configuration local and untracked. Do not use
`files.exclude` for this purpose, because it would hide recent diagnostic
artifacts from the file explorer.

## What a run checks

For each supported target/scope pair, the harness exercises install,
reinstall, progressive-sidecar repair, and uninstall as applicable. It checks
exact packaged content and version stamps, preserves unrelated user content,
and rejects filesystem changes outside the effects declared for that target.

Every run also compares the spec catalog with the public installer target list
and checks that `graphify uninstall --purge` removes `graphify-out/` without
removing unrelated content. A full `--all` run additionally:

- runs grouped user and project universal-uninstall scenarios;
- proves user-scope installations survive `graphify uninstall --project`;
- proves uninstall without `--purge` preserves `graphify-out/`.

## Read the result

Start with `<output>/report.md`. It gives the overall scenario counts, purge
status, runtime limitations, and links to failed scenarios.

- `PASS` means the supported scenario met every declared installer contract.
- `FAIL` means at least one command or filesystem assertion failed.
- `UNSUPPORTED` is a declared coverage limitation, not a failure.
- `NOT_APPLICABLE` means that lifecycle phase is not defined for the scenario.

Use the remaining artifacts only when more detail is needed:

| Artifact | Use |
| --- | --- |
| `run.json` | Host-owned lifecycle metadata and raw exit classification. |
| `runner.log` | Complete phase-labelled host and container console output. |
| `manifest.json` | Machine-readable run selection, package data, summary, scenarios, and purge result. |
| `scenarios/<name>/result.json` | Assertions and phase status for one scenario. |
| `scenarios/<name>/*.stdout.log` and `*.stderr.log` | Installer command output. |
| `scenarios/<name>/*.json` snapshots | Filesystem state before and after lifecycle phases. |
| `scenarios/<name>/commands.log` | Commands executed for the scenario. |

An exit status of `0` means all supported scenarios and the purge check
passed. Exit status `1` means a scenario or purge check failed. Other nonzero
statuses indicate invalid input, catalog validation, image build, runtime, or
container-execution problems; read the console error before interpreting
scenario artifacts.

For agent handoff, report the exact command, output directory, exit status,
summary from `report.md`, and any failed scenario names. Do not infer a product
failure from an image-build or container-runtime error.

## Continuous integration

Normal pytest provides the fast contract: it strictly loads the checked-in
YAML catalog and compares its filename-derived targets with the current
checkout's public `graphify install --help` targets. The Docker workflow adds
the slower filesystem-effect oracle.

The advisory `.github/workflows/install-sandbox.yml` workflow runs one Ubuntu,
Python 3.12 full-catalog invocation with `--all --scope both`. It is independent
of the normal pytest matrix and runs:

- for pull requests into, and pushes to, `v8` or `main` when installer code,
  packaged skills or commands, sandbox code/tests, packaging metadata, the lock
  file, or the workflow changes;
- nightly at `05:27 UTC`;
- on manual `workflow_dispatch`.

Scheduled and manual runs always execute the full catalog. Pull-request runs
cancel an older in-progress sandbox run for the same pull request. The workflow
uses a fresh external leaf at
`$RUNNER_TEMP/graphify-install-sandbox`, uploads the complete directory after
success or failure as
`install-sandbox-<run-id>-<run-attempt>`, writes `report.md` (or `run.json`
when the report is unavailable) to the job summary, and only then evaluates
the host lifecycle metadata. A `passed` run succeeds. A complete `failed` run
also succeeds after emitting a warning because it represents behavioral
findings, not a broken diagnostic. An `incomplete` or `interrupted` run, missing
metadata, malformed metadata, or an exit-code mismatch fails the workflow. The
runner's original exit code remains recorded in `run.json` and the job summary.
This workflow is advisory for completed findings; it is not a required-check
gate.

Two commented settings near the top of the workflow are the storage-cost
controls:

- `INSTALL_SANDBOX_ARTIFACT_RETENTION_DAYS` is `14`;
- `INSTALL_SANDBOX_ARTIFACT_COMPRESSION_LEVEL` is `9`.

Artifacts are compressed during upload. GitHub Actions artifacts are immutable
after upload, so the workflow does not attempt age-based recompression;
maintainers can reduce cost by changing those retention or compression values.
A representative current bundle measured about 3.1 MB locally and roughly
80 KB at maximum compression. See
[upload-artifact compression and immutability](https://github.com/actions/upload-artifact).

## Catalog authority

The YAML specs are the authority for target membership, install effects, and
universal-uninstall eligibility. Python discovers the catalog from spec
filenames and derives aggregate scenarios from those declarations; it does not
maintain a second list of target names.

The [spec authority guide](specs/README.md) explains how to place new target
facts, deterministic derivations, cross-target policy, and product
observations without freezing the current YAML schema.

## Isolation and platform limits

The repository is mounted read-only, copied to a separate container source
directory, and installed from that copy. HOME, XDG configuration, project,
user working directory, copied source, and output are distinct isolated roots.
No real user home is mounted.

Windows and Antigravity-Windows scenarios only compare packaged payloads in the
Linux container. They do not validate Windows paths, shells, permissions,
cleanup, or runtime discovery. Hermes validates its normal Linux path only;
`%LOCALAPPDATA%` behavior is not exercised.
