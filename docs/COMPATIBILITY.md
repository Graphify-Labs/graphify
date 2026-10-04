# Shared compatibility verification

This follow-up covers the contribution gate's installed-assistant contracts,
portable graph provenance and filesystem test profiles. It is separate from the
completed bounded Qt/QML adoption work. Runtime ownership, parser contracts and
Qt policy/cache epochs remain governed by the existing architecture.

Requirements use `REQ-CORE-NNN`, acceptance criteria `REQ-CORE-NNN-ACNN`, and
increments `INC-CORE-NN`. The independent counters begin at 001/01 and do not
renumber or reuse the Qt/QML catalog. [Requirements](REQUIREMENTS.md) own behavior;
[traceability](../tests/TRACEABILITY.md) owns results. An unavailable fixture is
not a passing assertion.

## Plan and acceptance matrix

| Increment | Outcome | Acceptance | Exit condition |
| --- | --- | --- | --- |
| INC-CORE-01 | Executable Codex hooks and portable installed-assistant fixture contracts | REQ-CORE-001-AC01–AC04 | Real dispatch from a path with spaces, exact platform destinations, refresh and uninstall regressions pass; generated skills unchanged |
| INC-CORE-02 | Explicit filesystem profiles with native failure-path protection | REQ-CORE-002-AC01–AC02 | Native classification/recovery assertions pass; actual unsupported FIFO/socket/symlink/deleted-CWD fixtures retain a separately recorded POSIX execution gap |
| INC-CORE-03 | Terraform scope and portable serialized provenance | REQ-CORE-003-AC01–AC02 | LF/CRLF source facts and directed references survive graph assembly/JSON reload without cross-directory binding |
| INC-CORE-04 | Accurate unavailable-CWD recovery diagnostics | REQ-CORE-002-AC03 | Supplied-root change-directory failure is distinguished from an unset root; prior output retained and private paths excluded |
| INC-CORE-05 | Native hook consumer and literal-path completion | REQ-CORE-001-AC01 | Exact Cmd and PowerShell consumer dispatch, including expansion-sensitive path rejection/handling; full-source and installed-artifact proof |

The environment uses Python 3.12 and `uv sync --all-extras --frozen`. This
installs the committed dependency versions without changing the lockfile.
Portable Git supplies Bash/sh for Windows shell tests. SDK tests use isolated
provider fakes; installing an SDK does not establish live-provider access.

Shell fixtures send literal input paths in the receiving Python interpreter's
format. A native Windows interpreter must not receive a fabricated WSL path.
MSYS shell output may use a different spelling for the same interpreter; the
test transport uses that shell's actual path converter before comparing complete
identities. Basenames or substring matches are insufficient.

Gemini's Windows user skill uses the shared `.agents` directory, while POSIX
uses `.gemini`. Hermes follows the existing platform-owned home/data directory.
Windows installs and refreshes use the existing adapted skill content. Shared
Gemini/agents uninstall retention is deliberate and remains covered. Corrections
to stale fixture expectations do not change these product contracts.

Upstream PR [#3268](https://github.com/Graphify-Labs/graphify/pull/3268) proposes
bare Codex commands for default installs. This correction instead retains the
existing explicit executable contract and fixes literal invocation. PR
[#2802](https://github.com/Graphify-Labs/graphify/pull/2802) independently addresses
Windows destination fixtures. Upstream issue
[#2800](https://github.com/Graphify-Labs/graphify/issues/2800) tracks Gemini/agents
shared-directory collision; current tests do not establish ownership isolation
or resolve that upgrade limitation. Incoming upstream `v8` was inspected at
`35adf43`; no incoming commits are integrated in this follow-up.
The requirement review corrected the draft refresh criterion to describe only
uniquely owned destinations: the production refresh deliberately leaves ambiguous
shared copies unchanged. That retained behavior has exact regression assertions;
it does not establish a fix for upstream issue #2800.

Terraform source files use portable POSIX separators. Same-name declarations
in distinct directories retain distinct identities and only same-directory
references. The former Windows failure occurred before assessing any target:
the test searched for a backslash path while the extractor emitted the correct
portable path. No Terraform production change is needed for that defect.

## Verification profiles and remaining system work

Native Windows cannot create Unix FIFOs through `os.mkfifo` or remove its current
working directory. Symlink creation also depends on actual account capability.
Capability/profile exclusions leave the real POSIX assertions intact and do not
substitute simulated evidence for a real filesystem result. Windows production
failure seams supplement those assertions.

WSL is absent on the inspected host, and the agent session is not elevated.
[Microsoft's installation procedure](https://learn.microsoft.com/en-us/windows/wsl/install)
requires an administrator terminal and may require a restart. A Linux run remains
outstanding until that environment is available; package installation or Bash
alone cannot establish POSIX kernel behavior. No operating-system security policy
is changed to manufacture a passing fixture.

Prepare the native environment from the repository root:

```powershell
uv sync --all-extras --frozen
uv pip check --python .venv/Scripts/python.exe
```

Expose the portable Git installation's `usr/bin` directory in the test process
PATH to make both `bash` and `sh` available. Keep the test provider environment
isolated and use `uv run --no-sync` or the environment's Python to preserve all
installed extras while verifying. A missing Bash tool is a setup gap, not a
reason to classify shell security cases as successful.

For the remaining real Linux profile, run this in an administrator PowerShell
terminal, then restart if Windows requests it:

```powershell
wsl --install -d Ubuntu --no-launch
```

After Ubuntu initialization, enter the mounted repository root from its Bash
shell and create an independent ignored environment, preserving `.venv` for
Windows. Install uv using its official instructions before these commands:

```bash
UV_PROJECT_ENVIRONMENT=.venv-posix uv sync --all-extras --frozen
UV_PROJECT_ENVIRONMENT=.venv-posix uv run --no-sync pytest tests/ -q --tb=short -rs
```

Test temporary filesystem fixtures on Ubuntu's `/tmp` so they exercise Linux
capabilities. The mounted source checkout remains the canonical repository;
no development checkout is moved. Keep Linux results, source revision, exact
dependency versions and remaining skips separate from native Windows evidence.

## Architecture and diagnostic impact

Production corrections cover the Codex command's literal executable invocation
and the unavailable-CWD failure reason. Installation still owns hook JSON publication and its existing
diagnostics; fixtures own shell/path transport. There is no new parser, logger,
cache owner, persistence mechanism or Qt diagnostic. Successful commands reach
the existing CLI; rejected arguments and filesystem failures retain existing
behavior. Test-only scope/provenance corrections need no cache invalidation.

Unavailable-CWD recovery diagnostics distinguish `GRAPHIFY_REPO_ROOT` being
absent from an unsuccessful change to a supplied root. The failure remains
terminal before persistence; retry is safe after restoring an accessible root.
Messages name the failed stage and omit private path/exception bodies. This uses
the existing console error owner and introduces no Qt diagnostic code or logger.

Codex command verification currently covers the native Cmd shell dispatch boundary
and the POSIX serialization branch. Installed Codex 0.160.0's versioned executor
defaults to Cmd on Windows but can inherit PowerShell from the session. Actual
PowerShell hook dispatch and Windows percent-expansion paths remain unverified;
quoted spaces alone do not establish literal identity for every Windows shell.
INC-CORE-05 retains those adjacent findings for correction after the environment
restart. Its acceptance is pending; the partial Cmd fix is a checkpoint.
The inspected versioned source is the
[command executor](https://github.com/openai/codex/blob/rust-v0.160.0/codex-rs/hooks/src/engine/command_runner.rs)
and [session configuration](https://github.com/openai/codex/blob/rust-v0.160.0/codex-rs/core/src/session/mod.rs).

## Restart checkpoint

All dependency installation and focused test processes have finished. The full
source rerun is deferred until the WSL installation restart and initialization.
The native all-extras environment is compatible; the lock and original coverage
file remain unchanged. The final AST-only repository update completed with 22,274 nodes
and 50,115 edges using `graphify update . --no-cluster`, with no LLM invocation.
These raw graph counts are navigation output, not extraction correctness proof.

Full Pyright with the explicit native environment reports 604 errors and zero
warnings. None belongs to the new focused test/helper files or corrected Terraform
test. The gate still fails; dependency installation and focused pytest/Ruff results
do not make it pass. The earlier implicit-interpreter run failed to resolve the
environment and is discarded as an invalid profile. Compare the explicit full
typing result against a matching baseline before claiming no regression.

Resume in this order: verify WSL/Ubuntu availability, complete INC-CORE-05 literal
consumer handling, run focused cases in native and Linux profiles, run both full
source suites, review every skip, rebuild the installed artifact where production
changed, and update graph/evidence. Retain source and dependency fingerprints,
exact commands and failure identities. No full-source success is claimed at this
checkpoint.

## Focused legacy ownership and size constraints

New helpers/tests remain below 300 physical lines. Existing oversized files keep
their established owners and receive only the focused correction/profile changes:

| File | Before | Checkpoint ceiling | Owner and extraction exit |
| --- | --- | --- | --- |
| `graphify/install.py` | 2559 | 2570 | Install maintainer; extract hook serialization in a separate characterized increment |
| `graphify/watch.py` | 2532 | 2550 | Watch maintainer; existing documented extraction path and persistence ordering retained |
| `tests/test_hooks.py` | 1590 | 1600 | Hook test owner; new shell identity transport is already a focused helper, unrelated hook cases stay in place |
| `tests/test_install.py` | 1617 | 1621 | Install test owner; future hook cases belong to the new focused execution module |
| `tests/test_install_references.py` | 548 | 553 | Install-reference test owner; separate platform destination characterization before extracting responsibilities |
| `tests/test_install_roundtrip.py` | 318 | 323 | Install-roundtrip test owner; keep installed bundle identity in one roundtrip boundary |
| `tests/test_skill_auto_refresh.py` | 527 | 541 | Refresh test owner; split platform adaptation from refresh lifecycle only in a separate characterized move |
| `tests/test_watch.py` | 5100 | 5104 | Watch test owner; new portable failure cases live in the focused filesystem-profile module |

The ceilings authorize this bounded change, not routine growth. No mechanical
extractor move, broad refactor or generated artifact edit is mixed into the fixes.

The current branch remains the integration checkout. Delegated owners have
disjoint installer, shell-fixture, filesystem-fixture and Terraform-test scopes;
the integration owner handles environment, shared documentation and Git. Incoming
upstream and overlapping hook/destination proposals are reviewed before choosing
the correction; publication and upstream integration are separate delivery work.
