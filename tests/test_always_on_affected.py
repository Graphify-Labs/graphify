"""Every always-on block names `graphify affected` (#3177).

The always-on text is what reaches the agent on every session — and none of
the six templates mentioned `affected`, so in 262 measured sessions it was
called zero times while the verbs the block does name (query/explain) were
used daily. The block now names the blast-radius verb beside them.
"""
from __future__ import annotations

from pathlib import Path

import pytest

ALWAYS_ON = Path(__file__).resolve().parent.parent / "graphify" / "always_on"
BLOCKS = sorted(p.name for p in ALWAYS_ON.glob("*.md"))


def test_all_six_blocks_exist():
    assert len(BLOCKS) == 6, BLOCKS


@pytest.mark.parametrize("name", BLOCKS)
def test_every_block_names_the_blast_radius_verb(name):
    body = (ALWAYS_ON / name).read_text(encoding="utf-8")
    assert "graphify affected" in body, f"{name} never names affected"
    assert "blast radius" in body


@pytest.mark.parametrize("name", BLOCKS)
def test_the_existing_verbs_are_still_named(name):
    body = (ALWAYS_ON / name).read_text(encoding="utf-8")
    assert "graphify query" in body
