# News

This file lists significant new capabilities contributed to graphify
upstream, in chronological order. Each entry names the method, the
contributor, the merged commit, and a one-paragraph description so a
reader can decide whether to read the full PR / commit history.

---

## Iterative sliding-window depth-graph method (0.9.43)

**Contributor:** JFWaskin
**Merged in:** `569cf56` (production polish), `dcdef67` (robustness), `feb7581` (pilot)
**Shipped as:** the `graphify depth <root>` command + the `DEPTH_REPORT.md` output

The `graphify depth` command introduces the *iterative sliding-window
depth-graph method*: a multi-pass build for the >500-file / >500K-word
case where a single-pass `graphify <root>` warns and asks the user to
narrow manually. The method auto-detects a corpus into N sub-buckets
(top-level subdirs with at least M files / W words) or accepts an
explicit `--focus <path>` set, runs the full extract pipeline per
bucket via subprocess, then merges the per-bucket graphs into a single
cross-bucket graph using the same prefix-and-compose path the existing
`graphify merge-graphs` already uses. The new output is `DEPTH_REPORT.md`,
which surfaces "cross-bucket signals" — entity LABELS (not ids) that
appear under multiple bucket prefixes in the merged graph and are
therefore the most actionable cross-system hint a reviewer can get
from a build.

The command is a thin orchestration layer over the existing
`graphify extract` and `graphify merge-graphs` code paths; no existing
command or its behaviour is changed. The 8 production scenarios
covered are: monorepo (>500 files), selective focus, resume after
interruption, CI / flaky network (transient-failure retry with
exponential backoff), CI parallel (capped at 4 workers to respect
LLM API rate limits), cross-repo integration (--global), sandbox /
read-only (--dry-run preview), and partial-failure containment
(--skip-on-error vs --no-skip-on-error).

The contribution ships with 21 tests (14 unit + 7 integration,
including a real-extract smoke test that invokes the installed
`graphify extract` subprocess on a fixture corpus with `--code-only
--no-cluster` and no LLM API key required), and was validated
end-to-end against the real graphify source itself (~70 packages,
4 000+ source files).
