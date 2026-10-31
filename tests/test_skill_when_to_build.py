"""Every skill says when a graph is worth building (#4829)."""
from __future__ import annotations

from pathlib import Path

import pytest

SKILLS = sorted((Path(__file__).resolve().parent.parent / "graphify").glob("skill*.md"))


def test_the_skill_files_are_found():
    assert SKILLS


@pytest.mark.parametrize("skill", SKILLS, ids=lambda p: p.name)
def test_the_guidance_comes_before_the_build_steps(skill):
    text = skill.read_text(encoding="utf-8")
    guidance = text.index("**When a graph is worth building:**")
    assert guidance < text.index("## What You Must Do When Invoked")
    # An explicit request still builds, or the passage would turn /graphify into a refusal.
    assert "if the user invoked `/graphify`, follow that request as asked." in text[guidance:]
    assert "If a graph already exists, query it." in text[guidance:]
