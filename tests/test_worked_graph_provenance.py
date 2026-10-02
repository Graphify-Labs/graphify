"""Provenance audit of the committed reference graphs under ``worked/``.

These are real graphs from real corpora (``worked/rsl-siege-manager`` alone
carries 1,268 AST nodes and 618 LLM-produced ``rationale`` nodes), so they are
the only production-shaped semantic output in the tree — and therefore where a
fabricated-provenance regression (#2217) would first be visible.

Every ``source_file`` that claims a file must be one the same run demonstrably
knew about: the manifest where one was committed, otherwise the set of files the
deterministic AST layer attributed nodes to. A path the model invented appears in
neither.

The corpora themselves are not vendored, so this asserts internal consistency
rather than on-disk existence — which is the right test anyway, since #2217 is
precisely about existence being the wrong question.

Scope note: this does NOT guard `_claims_a_file` against over-tightening. That
function only decides which values get checked, and every attribution in the one
non-vacuous fixture is a real manifest path, so a stricter `_claims_a_file` could
never produce an offender here. Over-tightening is covered by
`test_values_that_do_not_claim_a_file` and by
`tests/test_chunking.py::test_out_of_scope_nodes_are_dropped_from_merged_result`.
The claim floor below is the only signal this file offers on that axis.
"""

import json
from pathlib import Path

import pytest

from graphify.llm import _claims_a_file

WORKED = Path(__file__).resolve().parents[1] / "worked"
GRAPHS = sorted(WORKED.glob("*/graph.json")) if WORKED.is_dir() else []

# Fixtures whose audited-claim count must not silently collapse. If a future
# change stops classifying ordinary attributions as file claims, this floor drops
# and the test fails rather than passing on an empty check.
CLAIM_FLOOR = {"rsl-siege-manager": 1800}

pytestmark = pytest.mark.skipif(not GRAPHS, reason="worked/ reference graphs not present")


def _norm(value: str) -> str:
    """Case- and separator-insensitive path key.

    Uses ``removeprefix("./")`` rather than ``lstrip("./")``: lstrip strips a
    character SET, so it eats the leading dot of ``.github/workflows/ci.yml`` and
    swallows ``../`` prefixes whole, making legitimate attributions look invented.
    """
    return str(value).replace("\\", "/").lower().removeprefix("./")


def _strip_common_prefix(paths: "set[str]") -> "set[str]":
    """Reduce absolute manifest keys to corpus-relative form.

    The manifest holds absolute paths from the machine that built the graph, while
    nodes hold repo-relative ones. Stripping the longest shared directory prefix
    lets the two be compared by exact equality — which matters, because an
    ``endswith`` fallback would also accept a bare basename, and "inferred it from
    a basename" is exactly the fabrication the extraction prompt now forbids.
    """
    if len(paths) < 2:
        return set(paths)
    split = [p.split("/") for p in paths]
    common = 0
    for parts in zip(*split):
        if len(set(parts)) != 1:
            break
        common += 1
    if not common:
        return set(paths)
    return {"/".join(p[common:]) for p in split}


def _ground_truth(graph_dir: Path, nodes: list[dict]) -> "tuple[set[str], bool]":
    """(known files, whether the truth is independent of the audited nodes).

    A committed ``manifest.json`` lists the files the run actually walked, so it
    is independent evidence and every node can be judged against it.

    Without one, the only available reference is the AST layer's own
    attributions. That is still ground truth *for the semantic layer* — the AST
    engine is deterministic and never invents a path — but it cannot judge code
    nodes, because a fabricated code node would contribute its own path to the
    reference set and validate itself. Callers must restrict the audit
    accordingly; the flag says which regime applies.
    """
    manifest = graph_dir / "manifest.json"
    if manifest.exists():
        keys = {_norm(k) for k in json.loads(manifest.read_text(encoding="utf-8"))}
        return _strip_common_prefix(keys), True
    return {
        _norm(n["source_file"])
        for n in nodes
        if n.get("file_type") == "code" and n.get("source_file")
    }, False


def test_norm_preserves_dot_directories():
    """Regression guard for the lstrip character-set bug."""
    assert _norm(".github/workflows/ci.yml") == ".github/workflows/ci.yml"
    assert _norm("./src/App.tsx") == "src/app.tsx"
    assert _norm("..\\pkg\\mod.py") == "../pkg/mod.py"


@pytest.mark.parametrize("graph_path", GRAPHS, ids=lambda p: p.parent.name)
def test_no_node_claims_a_file_the_run_never_saw(graph_path: Path):
    nodes = json.loads(graph_path.read_text(encoding="utf-8")).get("nodes", [])
    assert nodes, f"{graph_path} has no nodes — fixture is empty"
    known, independent = _ground_truth(graph_path.parent, nodes)
    assert known, f"{graph_path}: could not establish the known-file set"

    # With only the AST layer as reference, audit the semantic layer alone —
    # judging code nodes against a set they define would be circular.
    audited = [n for n in nodes if independent or n.get("file_type") != "code"]
    claims = [
        n for n in audited
        if n.get("source_file") and _claims_a_file(n["source_file"])
    ]
    # The floor is asserted BEFORE the skip, deliberately. Checking it afterwards
    # made it unreachable in the one case it exists for: if `_claims_a_file`
    # collapsed entirely, `claims` would be empty, the skip would fire first, and
    # the only signal-bearing fixture would report as skipped rather than failed.
    floor = CLAIM_FLOOR.get(graph_path.parent.name)
    if floor is not None:
        assert len(claims) >= floor, (
            f"{graph_path.parent.name}: only {len(claims)} file-claiming attribution(s) "
            f"checked, expected >= {floor}. Either the fixture changed or "
            "_claims_a_file stopped recognising ordinary corpus paths."
        )

    if not claims:
        # Nothing to check. Skip rather than report green: a fixture whose audited
        # nodes carry no file-claiming source_file (karpathy-repos) would
        # otherwise pass vacuously, which is the failure mode this file exists to
        # avoid.
        pytest.skip(
            f"{graph_path.parent.name}: {len(audited)} audited node(s), "
            "none carrying a file-claiming source_file"
        )

    offenders = [
        (n.get("id"), n.get("file_type"), n["source_file"])
        for n in claims
        if _norm(n["source_file"]) not in known
    ]
    assert not offenders, (
        f"{graph_path.parent.name}: {len(offenders)} of {len(claims)} checked node(s) "
        f"claim a file the run never saw (fabricated provenance, #2217): {offenders[:5]}"
    )
