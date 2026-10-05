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
| INC-CORE-05 | Native hook consumer and literal-path completion | REQ-CORE-001-AC01/AC05 | Exact Cmd and PowerShell argument transport, expansion-sensitive paths, dependency rejection and hook ownership; full-source and installed-artifact proof |
| INC-CORE-06 | Hosted Linux evidence and native Windows compatibility lane | REQ-CORE-004-AC01–AC04 | Required tools/service and reviewed wheel admitted; workflow syntax/configuration reviewed; hosted jobs retain applicable passing results and exact revision/integrity evidence |
| INC-CORE-07 | Deterministic hosted Windows tool selection | REQ-CORE-004-AC02/AC03 | Multiple real application matches preserve the first PATH identity, required version and executable invocation; missing tools reject before collection; normal PR evidence records the corrected revision |
| INC-CORE-08 | Preserve admitted shell identity at native process launch | REQ-CORE-004-AC02/AC03 | Actual Python subprocesses execute the selected absolute Bash/sh file, preserve literal/security assertions and reject missing shells; corrected normal PR results retain exact identity and outcomes |

INC-CORE-01–05 have current native source evidence below. The hook/filesystem
corrections also have independent installed-consumer evidence. INC-CORE-02
retains its actual POSIX filesystem gap. INC-CORE-06 addresses that
gap and the missing Windows generic-contract CI selection; it changes test
infrastructure, with no Graphify extraction or Qt schema change. Existing
all-extras Ubuntu source jobs and the separate QML-wheel matrix remain the
starting point. Configuration acceptance and hosted execution are distinct.
Both workflows use the PR number for obsolete-PR cancellation and a distinct
run ID for non-PR groups. The QML-wheel correction replaces its former branch-ref
fallback, which could replace an older queued non-PR proof even when running-job
cancellation was disabled. Its triggers, matrix and test jobs are unchanged.

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

After the installation restart, WSL 3.0.1.0 is present but no distribution is
registered. Ubuntu download succeeds; registration fails with
`HCS_E_HYPERV_NOT_INSTALLED`. Windows reports firmware virtualization disabled,
although the processor supports virtualization and second-level address
translation. Optional-component and boot settings cannot be verified from the
non-elevated session. Linux execution remains pending until the firmware/WSL
profile is available; no Linux passes are inferred from the Windows seam tests.
[Microsoft's troubleshooting procedure](https://learn.microsoft.com/en-us/windows/wsl/troubleshooting#installation-issues)
describes the firmware and Virtual Machine Platform prerequisites.

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

### DEC-CORE-01 — Windows hook literal transport

Codex's versioned native runner accepts one command string and may select Cmd or
PowerShell. A quoted executable token needs different invocation syntax in those
shells; Cmd additionally expands percent names inside quotes. A user-scope hook
therefore wraps the selected literal Graphify path in a UTF-16LE encoded
PowerShell payload, launched through the OS-owned Windows PowerShell executable.
The payload invokes the literal path and propagates failure/exit status. Paths
never become source in the outer consumer shell. POSIX uses its existing literal
quoting; project hooks retain the existing portable bare invocation.

The serializer owns transport, installation owns JSON merging/publication, and
the native consumer owns shell execution. This uses an existing Windows OS shell;
Graphify extraction and runtime remain Python, with no corpus execution. An
unavailable shell or unsafe OS-executable token rejects publication before
reading/writing hooks. Bounded diagnostics omit private paths and exception
bodies. Status metadata supported by Codex identifies the owned hook for existing
installation/uninstall matching; the encoded payload is not decoded by that
matcher. Native shell dispatch, failure, repeated installation and retention
assertions characterize the contract.

Encoded Windows commands are limited to 8,000 characters. The current Cmd
executable, `/C` and outer quotation must also fit within its documented
[8,191-character complete-command limit](https://learn.microsoft.com/en-us/troubleshoot/windows-client/shell-experience/command-line-string-limitation).
This is conservative transport admission, not a claim that every such path exists
or can launch. An oversized command or failed OS-shell inspection rejects before
settings access, retains the existing hook file and rolling backup, and reports
an actionable reason without the private path or exception body. Shorter
installation paths and restored OS-shell access are the respective recovery steps.

Bare user-scope commands, a launcher script and per-shell path quoting were
considered. Bare commands change the accepted executable identity policy; a
script introduces another persisted artifact and working-directory authority;
per-shell quoting cannot represent one string identically for both consumers.
The encoded transport keeps the selected executable contract and fails safely
when its OS dependency is unavailable. Actual Codex event delivery remains a
system boundary separate from the versioned runner argument-transport tests.

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

Codex command verification covers actual native Cmd and Windows PowerShell 5.1
execution using the argument transports of the installed Codex 0.160.0 runner.
The fixture selects the real Graphify launcher, excludes a PATH decoy and checks
unsafe controls. Literal expansion-sensitive, bracket and Unicode paths are
included. This establishes the consumer boundary; it does not establish actual
Codex Desktop event delivery or all PowerShell versions. POSIX serialization is
retained, with actual POSIX dispatch assigned to the Linux profile. Full-source
and installed-artifact verification of INC-CORE-05 passes in the recorded native
profiles below; actual Linux dispatch remains unverified.
The inspected versioned source is the
[command executor](https://github.com/openai/codex/blob/rust-v0.160.0/codex-rs/hooks/src/engine/command_runner.rs)
and [session configuration](https://github.com/openai/codex/blob/rust-v0.160.0/codex-rs/core/src/session/mod.rs).

<a name="restart-checkpoint"></a>

## Historical restart checkpoint

This section records `9efa7e4`/`c1c0e6a` before the current consumer correction
and native run. Current results are in [traceability](../tests/TRACEABILITY.md#current-native-source-and-artifact-evidence--2026-10-05).

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

## Current native outcome

Source `463ca3226c4aec4390a1e931fb1be1582059d1ca` has a full native Windows
result of 8,818 passes, no failures and 151 skips. Exact supplemental profiles
pass all 76 Node and seven compiler/wheel cases initially excluded for setup.
All profiles retain source, dependencies and coverage. There are 68 distinct
initial skips still unexecuted locally: 63 platform/capability cases, two
other-Python-version cases, one inapplicable historical bundle branch and two
FalkorDB service cases. Full typing retains 604 baseline errors with no added
diagnostics. [Exact commands and artifacts](../tests/TRACEABILITY.md#current-native-source-and-artifact-evidence--2026-10-05)
own the evidence; separate results are not combined into a fictitious full run.

## Hosted runner proof procedure

The hosted increment preserves the existing full Ubuntu source matrix and QML
wheel matrix, adds a focused Windows 3.12 generic compatibility lane, and retains
individual JUnit/skip and source/dependency evidence. A real Ubuntu runner
supplies the POSIX kernel that the local WSL profile cannot yet provide. The
Windows lane supplies Cmd/Windows PowerShell and Git Bash behavior; it does not
substitute for a Linux kernel or physical browser/device interaction.

Each Ubuntu source job uses the official server-only image
`falkordb/falkordb-server:6.0.1@sha256:f4f60c62532b67f8651d0f4f50bbb4db7548717b502bd05abd80e668f2d974c6`.
The [tagged release](https://github.com/FalkorDB/FalkorDB/releases/tag/v6.0.1)
and [publisher's image workflow](https://github.com/FalkorDB/FalkorDB/blob/v6.0.1/.github/workflows/release-image.yml)
establish provenance; the digest fixes the selected image. This is not a
source-to-image build attestation. The
[tagged source license](https://github.com/FalkorDB/FalkorDB/blob/v6.0.1/LICENSE)
is Server Side Public License v1; Redis and base-image components retain their
own licenses. The service is an external CI oracle, with no server code or binary
added to Graphify's package.

Setup starts one run-labeled container with only loopback port 6379 and no mounted
storage. It requires real `GRAPH.LIST` and `GRAPH.QUERY` readiness within 45 seconds,
deletes the probe graph and records image/module versions. The two existing
exporter/idempotency cases and all three reviewed-wheel cases must appear exactly
once in JUnit without skips, failures or errors. The wheel is built before source
pytest and its hash must remain unchanged. Existing installer fixtures temporarily
replace packaged assistant references and restore them during teardown; the
prebuilt wheel captures source before those substitutions. Each matrix job owns
its checkout, and post-test integrity requires restored tracked inputs and
unchanged dependencies. Post-test checks require no retained
test graph, and an independent cleanup step removes only the job-owned container
and confirms absence. Failed readiness or cleanup fails the job; a new attempt
starts with a new disposable service. No deployed-service, TLS, restart or
database-version matrix acceptance is implied.

1. Validate the workflow configuration and embedded scripts locally; confirm
   unchanged application source/lock and passing affected local evidence. Review
   GitHub expression scopes with actionlint as well as YAML/native syntax: the
   first hosted run rejected `runner.temp` in job-level `env`. Resolve evidence
   directories from `RUNNER_TEMP` within the step. Review the source/configuration
   change as one versioned increment.
2. Publish the explicit feature branch and create/update its draft PR against
   the reviewed base when publication is authorized. The PR event owns full
   validation; do not dispatch a duplicate feature run. Re-read the remote source
   head and base before relying on an earlier record.
3. Read every applicable Ubuntu source, Windows compatibility and QML-wheel
   job. Bind the workflow/event/run URL, source head, base and actual checkout
   SHA: a PR checkout may be a synthetic integration commit. Inspect individual
   acceptance testcases and skip reasons as well as the job conclusion.
4. Required tool/service readiness failures, missing required testcases,
   unintended skips, changed inputs/dependencies and failed assertions retain a
   failed result. Preserve the original pytest failure when retention/audit
   steps execute. Diagnose and correct deterministic failures at the lowest
   faithful boundary, push the new reviewed SHA and let normal PR validation
   run; report infrastructure retries separately.
5. Verify the disposable testgraph/service cleanup record. Cancellation alone
   does not establish cleanup; missing evidence remains outstanding. The hosted
   runner lifecycle is an additional isolation boundary, not proof that a
   particular cleanup step succeeded.

Actual Codex event delivery, physical middle-button/browser behavior and omitted
runtime/device profiles retain their separate system procedures. Hosted pytest
does not repair the failed typing baseline or broaden generic-only Qt API support.
No merge or post-merge/protected proof is included in this validation increment.

The native Windows selection also executes the discovered-source and physical
co-owner watch regressions from INC-QML-42/44. Owned NTFS directory junctions and
hardlinks exercise source ownership without requiring file-symlink elevation.
Actual Windows short-leaf spelling remains in the QML source selection; Linux
source CI executes the original real POSIX regressions. Capability exclusions
are retained individually and never counted as passing acceptance.

## Deterministic Windows tool selection — INC-CORE-07

Status: **Implemented correction; native regression passes, corrected hosted proof pending**.
Owner: CI Windows environment admission. Acceptance: REQ-CORE-004-AC02/AC03.
Dependency: INC-CORE-06. The hosted Windows image exposes multiple Node
applications. PowerShell's `Get-Command -CommandType Application` returns all
matches, so direct `.Source` projection produces an array instead of one
executable path. The first hosted compatibility attempt at `f95366d` rejects
before pytest; it establishes no native test pass or source-integrity result.

The owning workflow selects the first application for Node and uv before
projecting its path. Node retains its exact required version check. The selected
Python, restricted process PATH, offline installation guards, test-exit retention
and evidence sequencing keep their existing owners. Multiple matches are a
successful admission case; missing tools or a wrong Node version reject before
collection. The prior partial dependency/import evidence remains retained, with
identity, JUnit and post-test integrity explicitly unavailable for that attempt.
These setup rejections do not mutate analyzed graph data. Process-local setup is
discarded with the runner; no product migration or new diagnostic code is needed.

Ordinary regressions execute the actual workflow expressions with multiple real
applications, prove first-PATH executable identity and invocation, and cover a
missing required application and real incompatible executable. The historical
selector fails both duplicate-application cases; the corrected profile passes
all five cases with no skips. Native PowerShell 5.1 runs actual Node 24.19.0 and
uv binaries. The test-only absolute uv dependency is passed through
`GRAPHIFY_TEST_UV`, keeping installer commands off the consumer PATH. The workflow
measures 450 physical lines within its existing ceiling. The normal PR run supplies corrected hosted proof.
No Graphify runtime interface, Qt analysis epoch, cache/persistence ordering or
dependency contract changes; the compatibility procedure owns this infrastructure
design. Review the plan after the corrected run and add further work only for
another reproduced gap.

## Native shell process identity — INC-CORE-08

Status: **Implemented; local consumer/configuration verification passes, corrected hosted proof pending**.
Owner: shared shell test transport and native CI admission. Acceptance:
REQ-CORE-004-AC02/AC03. Dependency: INC-CORE-07.

Hosted source `38bf8cc` reaches native pytest with 783 passes, 33 failures and
20 skips. All failures belong to Bash allowlist/payload and generated skill input
security cases. Git Bash is present and the explicit preflight passes, but Python
subprocesses launch the Windows WSL stub when given the bare `bash` name. A real
native reproduction resolves Git Bash with PATH lookup, then obtains a WSL
installation notice from bare process launch; launching that absolute Git Bash
file succeeds. Availability lookup alone does not bind process identity.

Acceptance matrix: select and execute the actual admitted absolute shell;
preserve literal paths, raw payloads, hostile-input rejection and vulnerable
positive controls; reject unavailable shell selection without collection skips;
prove a competing native/CWD executable cannot replace the selected shell.
MSYS path conversion uses that same installation's mapper. Native CI preflight
must exercise the ordinary Python consumer boundary, and retain selected shell
identity with version, revision, JUnit and integrity evidence. POSIX lookup and
production discovery defaults remain unchanged.

This is test/environment transport ownership. It changes no Graphify runtime,
extraction epoch, dependency, cache or product-persistence contract. Missing or
failed consumers reject setup; process-local admission cannot alter analyzed
data. Existing job failure preservation and cleanup own recovery. No new product
diagnostic code or infrastructure rerun is required. Exit with the unchanged
failed cases passing, executable identity/rejection regressions and corrected
normal PR evidence; review new outcomes before allocating further work.

Current shell selection resolves only qualified candidates in configured PATH
order and launches the absolute selected file. Native implicit CWD/system search
cannot replace it; an explicit CWD PATH entry remains eligible. All original
literal/hostile-input/control assertions are preserved. Eighteen helper cases
pass, including three real consumer failures before correction. The combined
shell/hook/skillgen source selection passes 161 with eight established profile
exclusions. Revised preflight proves actual Python and Node identities through
both selected shells, and retains `shell-consumers.json`. Exact commands, counts,
skip identities and limits belong to
[traceability](../tests/TRACEABILITY.md#native-shell-launch-identity--inc-core-08).

## Focused legacy ownership and size constraints

New helpers/tests remain below 300 physical lines. Existing oversized files keep
their established owners and receive only the focused correction/profile changes:

| File | Before | Checkpoint ceiling | Owner and extraction exit |
| --- | --- | --- | --- |
| `graphify/install.py` | 2559 | 2570 | Install maintainer; Codex serialization now belongs to the focused `codex_hook_command` module; other assistant serializers remain installer-owned |
| `graphify/watch.py` | 2532 | 2550 | Watch maintainer; existing documented extraction path and persistence ordering retained |
| `tests/test_hooks.py` | 1590 | 1600 | Hook test owner; new shell identity transport is already a focused helper, unrelated hook cases stay in place |
| `tests/test_install.py` | 1617 | 1640 | Install test owner; encoded-command expectations adapt two existing contract tests; new consumer and failure cases belong to the focused execution module |
| `tests/test_install_references.py` | 548 | 553 | Install-reference test owner; separate platform destination characterization before extracting responsibilities |
| `tests/test_install_roundtrip.py` | 318 | 323 | Install-roundtrip test owner; keep installed bundle identity in one roundtrip boundary |
| `tests/test_skill_auto_refresh.py` | 527 | 541 | Refresh test owner; split platform adaptation from refresh lifecycle only in a separate characterized move |
| `tests/test_watch.py` | 5100 | 5104 | Watch test owner; new portable failure cases live in the focused filesystem-profile module |
| `.github/workflows/ci.yml` | 106 | 470 | CI maintainer; full Ubuntu and focused Windows execution/evidence sequencing remain one cohesive workflow; CORE-08 adds actual Python shell/consumer admission after the earlier 450-line checkpoint; extract a shared evidence helper when another caller needs it or further meaningful growth exceeds this ceiling |

The ceilings authorize this bounded change, not routine growth. No mechanical
extractor move, broad refactor or generated artifact edit is mixed into the fixes.

The CI cohesion exception retains tool/service admission, source/dependency
identity, test exit preservation and cleanup ordering together. Splitting these
blocks solely to meet 300 lines would obscure their execution contract. The
measured workflow size and local syntax checks belong to the increment's
traceability record; 470 is a bounded ceiling, not permission for routine growth.

The current branch remains the integration checkout. Delegated owners have
disjoint installer, shell-fixture, filesystem-fixture and Terraform-test scopes;
the integration owner handles environment, shared documentation and Git. Incoming
upstream and overlapping hook/destination proposals are reviewed before choosing
the correction; publication and upstream integration are separate delivery work.
