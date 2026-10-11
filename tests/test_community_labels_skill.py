"""Curated community labels must reach the persisted graph.json (#2490).

Two guards:

1. The ``to_json`` export gate: nodes get ``community_name`` only when the
   ``community_labels`` kwarg is passed, so any Step-5 flow that curates labels
   but omits the kwarg ships a graph.json without community names.

2. A lint over the generated ``graphify/skill*.md`` bodies (and the fragment they
   render from) plus the pipeline step they call: Step 5 must invoke
   ``graphify pipeline label``, and that step (``graphify.pipeline.step_label``)
   must re-export ``graphify-out/graph.json`` with ``community_labels``. Together
   these lock the #2490 fix end to end — a future edit cannot drop the kwarg or
   the step without failing here.

Before #197 the label flow was an inline ``python -c`` block carrying
``labels = LABELS_DICT``; it is now the ``label`` subcommand, so the lint follows
the flow to where it lives.
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import networkx as nx
import pytest

from graphify.export import to_json

REPO_ROOT = Path(__file__).resolve().parent.parent
FRAGMENTS_DIR = REPO_ROOT / "tools" / "skillgen" / "fragments" / "core"


def _two_community_graph() -> tuple[nx.Graph, dict[int, list[str]]]:
    G = nx.Graph()
    G.add_node("n1", label="Database", community=0, source_file="app/db.py", type="code")
    G.add_node("n2", label="Server", community=0, source_file="app/srv.py", type="code")
    G.add_node("n3", label="Cache", community=1, source_file="infra/cache.py", type="code")
    G.add_edge("n1", "n2", relation="calls")
    communities = {0: ["n1", "n2"], 1: ["n3"]}
    return G, communities


def test_to_json_community_labels_kwarg_writes_community_name():
    """Passing community_labels stamps community_name on that community's nodes."""
    G, communities = _two_community_graph()
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "graph.json"
        assert to_json(G, communities, str(out), community_labels={0: "X"})
        data = json.loads(out.read_text())
        by_id = {n["id"]: n for n in data["nodes"]}
        assert by_id["n1"]["community_name"] == "X"
        assert by_id["n2"]["community_name"] == "X"
        # A community missing from a non-empty labels dict gets the placeholder.
        assert by_id["n3"]["community_name"] == "Community 1"


def test_to_json_without_labels_kwarg_writes_no_community_name():
    """Omitting the kwarg is the #2490 bug shape: no node carries community_name."""
    G, communities = _two_community_graph()
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "graph.json"
        assert to_json(G, communities, str(out))
        data = json.loads(out.read_text())
        assert all("community_name" not in n for n in data["nodes"])


# --- template lint -----------------------------------------------------------

#: Web-UI / CLI hosts rendered from core.md. The aider and devin monoliths are
#: hand-authored per-platform skills with their own inline-Python pipelines; they
#: are tracked separately and not converted to the pipeline subcommands yet (#197).
_MONOLITH_SKILLS = {"skill-aider.md", "skill-devin.md"}


def _skill_bodies() -> list[Path]:
    paths = sorted(
        p for p in REPO_ROOT.glob("graphify/skill*.md")
        if p.name not in _MONOLITH_SKILLS
    )
    assert paths, "no generated graphify/skill*.md found"
    return paths


#: The Step-5 subcommand the skill hands its curated labels to.
_LABEL_STEP = "graphify pipeline label"

#: The one call that must carry the curated labels into graph.json. Checked in
#: graphify/pipeline.py where the step body now lives. The call may wrap across
#: lines, so assert both halves rather than one literal.
_REEXPORT_TARGET = 'to_json(G, communities, str(out_dir / "graph.json")'
_REEXPORT_LABELS = "community_labels=int_labels"


@pytest.mark.parametrize("path", _skill_bodies(), ids=lambda p: p.name)
def test_skill_step5_invokes_the_label_subcommand(path: Path):
    """Every generated skill routes Step 5 through `graphify pipeline label`.

    That subcommand is the only place the curated labels reach ``to_json`` with
    the ``community_labels`` kwarg, so a body that curates labels some other way
    would ship graph.json nodes with no ``community_name`` (#2490).
    """
    text = path.read_text(encoding="utf-8")
    assert _LABEL_STEP in text, (
        f"{path.name}: Step 5 must call `{_LABEL_STEP}` so curated labels reach "
        f"graph.json's community_name (#2490)"
    )


def test_step_label_reexports_graph_json_with_curated_labels():
    """`step_label` must pass community_labels to to_json — the #2490 guard.

    This is the call the old Step-5 inline block made. It moved into
    ``graphify/pipeline.py`` with #197; pin it there so the kwarg cannot be
    dropped silently.
    """
    pipeline_src = (REPO_ROOT / "graphify" / "pipeline.py").read_text(encoding="utf-8")
    assert _REEXPORT_TARGET in pipeline_src, (
        "graphify/pipeline.py: the label step must re-export graphify-out/graph.json (#2490)"
    )
    assert _REEXPORT_LABELS in pipeline_src, (
        "graphify/pipeline.py: that re-export must pass community_labels so nodes "
        "carry community_name (#2490)"
    )
    # And the labels must actually come from the caller's curated dict.
    assert "labels: dict[int | str, str]" in pipeline_src
    assert "int_labels = {int(k): v for k, v in labels.items()}" in pipeline_src


@pytest.mark.parametrize(
    "fragment",
    sorted(p for p in FRAGMENTS_DIR.glob("*.md") if p.name not in ("aider.md", "devin.md")),
    ids=lambda p: p.name,
)
def test_core_fragments_step5_reexport_with_curated_labels(fragment: Path):
    """Same lint at the source of truth: the core fragments skillgen renders from."""
    text = fragment.read_text(encoding="utf-8")
    assert _LABEL_STEP in text, (
        f"{fragment.name}: the core fragment must route Step 5 through "
        f"`{_LABEL_STEP}` (#2490, #197)"
    )
    assert "LABELS_DICT" not in text, (
        f"{fragment.name}: the old LABELS_DICT code-substitution placeholder must be "
        f"gone; labels are passed as --labels JSON to `{_LABEL_STEP}` (#197)"
    )


@pytest.mark.parametrize(
    "fragment",
    sorted(p for p in FRAGMENTS_DIR.glob("*.md") if p.name in ("aider.md", "devin.md")),
    ids=lambda p: p.name,
)
def test_monolith_fragments_still_reexport_curated_labels(fragment: Path):
    """The unconverted aider/devin monoliths keep their own #2490 re-export.

    They still carry the inline Step-5 block, so this checks the original shape
    still holds until they are migrated to `graphify pipeline label` (#197).
    """
    text = fragment.read_text(encoding="utf-8")
    assert "to_json(G, communities, 'graphify-out/graph.json', community_labels=labels)" in text, (
        f"{fragment.name}: the monolith Step-5 block must still re-export graph.json "
        f"with community_labels=labels (#2490)"
    )
