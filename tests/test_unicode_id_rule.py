"""#4432: the node-id rule in the prompts must match ``graphify.ids`` for non-ASCII paths.

``ids.make_id`` keeps Unicode letters and digits (``docs/tz/ЛЗ4.md`` ->
``docs_tz_лз4``), but the prompts said ids are "only [a-z0-9_]". A model cannot
follow both, so it invented a different stem per chunk and per run. The prompts now
state the real rule and hand the model each file's canonical stem; these tests pin
the wording, the stem helper, the stem in the chunk prompt, and the skill's code
step that writes the stems for the subagents.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from graphify.extract import extract  # noqa: E402
from graphify.llm import _EXTRACTION_SYSTEM, _read_files, _wrap_untrusted  # noqa: E402
from tools.skillgen import gen  # noqa: E402

# Paths from the issue, with the stems `make_id(_file_stem(...))` gives for them.
CYRILLIC = "docs/tz/ЛЗ4_обоснование_с_листом_Расчет_Кдог.md"
CYRILLIC_STEM = "docs_tz_лз4_обоснование_с_листом_расчет_кдог"
SPACED = "docs/tz/СРЗ КП18-С301   ЛЗ2 (105) - 12.10.2026.md"
SPACED_STEM = "docs_tz_срз_кп18_с301_лз2_105_12_10_2026"


def _file_id_stem(*args, **kwargs) -> str:
    from graphify.extractors import base
    return base.file_id_stem(*args, **kwargs)


# --- the rule text, in every prompt ------------------------------------------


def _spec_artifacts() -> list[tuple[str, str]]:
    return [(a.path, a.content) for a in gen.render_all(gen.load_platforms())
            if a.path.endswith("references/extraction-spec.md")]


def test_the_spec_scan_sees_every_host():
    """The parametrized guard below must not pass vacuously."""
    assert len(_spec_artifacts()) == 14, [p for p, _ in _spec_artifacts()]


def test_llm_prompt_states_the_unicode_rule():
    assert "only [a-z0-9_]" not in _EXTRACTION_SYSTEM
    assert "letters and digits of any script are kept" in _EXTRACTION_SYSTEM.lower()
    assert _EXTRACTION_SYSTEM.count("never transliterated") == 1
    assert "Cyrillic" not in _EXTRACTION_SYSTEM
    assert 'stem="..."' in _EXTRACTION_SYSTEM


@pytest.mark.parametrize("path,content", _spec_artifacts(), ids=[p for p, _ in _spec_artifacts()])
def test_spec_states_the_unicode_rule(path: str, content: str):
    assert "only `[a-z0-9_]`" not in content, path
    assert "Letters and digits of any script are kept as written" in content, path
    assert "never transliterated" in content, path
    assert "<TAB>stem" in content, path


def test_no_generated_skill_still_says_only_ascii_ids():
    offenders = [a.path for a in gen.render_all(gen.load_platforms())
                 if re.search(r"only \[?`?\[a-z0-9_\]", a.content)]
    assert not offenders, offenders


# --- file_id_stem ------------------------------------------------------------


@pytest.mark.parametrize("path,stem", [(CYRILLIC, CYRILLIC_STEM), (SPACED, SPACED_STEM),
                                       ("docs/guide.md", "docs_guide"), ("setup.py", "setup")])
def test_file_id_stem_of_a_relative_path(path: str, stem: str):
    assert _file_id_stem(path) == stem


def test_file_id_stem_resolves_an_absolute_path_against_root_dot(tmp_path: Path, monkeypatch):
    """detect gives absolute paths and the scan root is often `.`; both must resolve
    to the same root-relative stem, not to ''."""
    (tmp_path / "docs" / "tz").mkdir(parents=True)
    doc = tmp_path / CYRILLIC
    doc.write_text("# x\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    assert _file_id_stem(str(doc), ".") == CYRILLIC_STEM
    assert _file_id_stem(str(doc), str(tmp_path)) == CYRILLIC_STEM
    assert _file_id_stem(CYRILLIC, ".") == CYRILLIC_STEM


def test_file_id_stem_is_empty_outside_the_root(tmp_path: Path):
    """No root-relative form: never bake the checkout location into an id."""
    root = tmp_path / "proj"
    root.mkdir()
    other = tmp_path / "elsewhere" / "a.md"
    other.parent.mkdir()
    other.write_text("x", encoding="utf-8")
    assert _file_id_stem(str(other), str(root)) == ""


def test_file_id_stem_of_quotes_and_angle_brackets_is_word_characters_only():
    """`"`, `<` and `>` in a file name must not survive into the id: the stem is
    written into a prompt attribute and a tab-separated file."""
    stem = _file_id_stem('docs/a"b<c>d.md')
    assert stem == "docs_a_b_c_d"
    assert stem and all(ch.isalnum() or ch == "_" for ch in stem)


# --- the stem in the chunk prompt --------------------------------------------


def test_chunk_prompt_carries_each_files_stem(tmp_path: Path):
    for rel in (CYRILLIC, SPACED):
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text("# заголовок\n", encoding="utf-8")
    prompt = _read_files([tmp_path / CYRILLIC], tmp_path)
    assert f'stem="{CYRILLIC_STEM}"' in prompt
    assert f'stem="{SPACED_STEM}"' in _read_files([tmp_path / SPACED], tmp_path)


def test_chunk_prompt_for_an_ascii_path_differs_only_by_the_stem(tmp_path: Path):
    doc = tmp_path / "docs" / "guide.md"
    doc.parent.mkdir()
    doc.write_text("# Intro\n", encoding="utf-8")
    prompt = _read_files([doc], tmp_path)
    assert 'stem="docs_guide"' in prompt
    assert re.sub(r' stem="[^"]*"', "", prompt) == _wrap_untrusted("docs/guide.md", "# Intro\n")


def test_chunk_prompt_stem_attribute_cannot_carry_a_quote(tmp_path: Path):
    doc = tmp_path / 'a"b.md'
    doc.write_text("x", encoding="utf-8")
    (stem,) = re.findall(r' stem="([^"]*)"', _read_files([doc], tmp_path))
    assert stem == "a_b"


# --- the stem equals what the real pipeline mints -----------------------------


@pytest.mark.parametrize("rel", [CYRILLIC, "docs/guide.md"])
def test_file_id_stem_is_the_prefix_the_pipeline_mints(tmp_path: Path, rel: str):
    """The document pass mints the file's own node under the canonical stem; the stem
    handed to the model is that same string, and a semantic node carrying it is left
    alone by the build-time remap."""
    from graphify.build import _semantic_id_remap

    doc = tmp_path / rel
    doc.parent.mkdir(parents=True, exist_ok=True)
    doc.write_text("# Раздел\n\nТекст.\n", encoding="utf-8")

    stem = _file_id_stem(str(doc), str(tmp_path))
    nodes = extract([doc], cache_root=tmp_path, root=tmp_path)["nodes"]
    (page,) = [n for n in nodes if n.get("node_kind") == "page"]
    assert page["id"] == stem
    assert all(n["id"] == stem or n["id"].startswith(stem + "_") for n in nodes)

    assert f'stem="{stem}"' in _read_files([doc], tmp_path)
    semantic = [{"id": f"{stem}_понятие", "label": "понятие", "file_type": "concept",
                 "source_file": rel}]
    assert _semantic_id_remap(semantic, str(tmp_path)) == {}


# --- the skill's code step ----------------------------------------------------


def _cache_step_body(text: str) -> str:
    """The python body of the Part B cache step, un-escaped from its bash quoting."""
    for block in re.findall(r'-c "\n(.*?)\n"\n', text, re.S):
        if "check_semantic_cache" in block and "_uncached_stems" in block:
            return block.replace('\\"', '"')
    raise AssertionError("cache step not found")


@pytest.mark.skipif(sys.platform == "win32", reason="runs the bash-quoted python body")
def test_skill_cache_step_writes_a_stem_for_every_uncached_file(tmp_path: Path):
    skill = (REPO_ROOT / "graphify" / "skill.md").read_text(encoding="utf-8")
    body = _cache_step_body(skill)
    assert body.count("INPUT_PATH") == 1, "the scan root is set once and reused"

    for rel in (CYRILLIC, "docs/guide.md"):
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text("# x\n", encoding="utf-8")
    spec = tmp_path / "spec.md"
    spec.write_text("prompt", encoding="utf-8")
    out = tmp_path / "graphify-out"
    out.mkdir()
    import json
    (out / ".graphify_detect.json").write_text(json.dumps(
        {"files": {"document": [str(tmp_path / CYRILLIC), str(tmp_path / "docs/guide.md")]}},
        ensure_ascii=False), encoding="utf-8")

    script = body.replace("INPUT_PATH", ".").replace("SPEC_PATH", str(spec))
    done = subprocess.run([sys.executable, "-c", script], cwd=tmp_path, capture_output=True,
                          text=True, env={**os.environ, "PYTHONPATH": str(REPO_ROOT)})
    assert done.returncode == 0, done.stderr

    lines = (out / ".graphify_uncached_stems.txt").read_text(encoding="utf-8").splitlines()
    assert lines == [f"{tmp_path / CYRILLIC}\t{CYRILLIC_STEM}", f"{tmp_path / 'docs/guide.md'}\tdocs_guide"]
    bare = (out / ".graphify_uncached.txt").read_text(encoding="utf-8").splitlines()
    assert bare == [line.split("\t")[0] for line in lines]


# Hosts whose own monolith body has its own Part B; they never carried the rule and
# are not covered here.
_MONOLITHS = {"graphify/skill-aider.md", "graphify/skill-devin.md"}


def _skill_artifacts() -> list[tuple[str, str]]:
    return [(a.path, a.content) for a in gen.render_all(gen.load_platforms())
            if re.fullmatch(r"graphify/skill[-a-z]*\.md", a.path)
            and "check_semantic_cache" in a.content and a.path not in _MONOLITHS]


@pytest.mark.parametrize("path,content", _skill_artifacts(), ids=[p for p, _ in _skill_artifacts()])
def test_skill_hands_the_stems_to_the_subagents(path: str, content: str):
    assert "file_id_stem(f, root)" in content, path
    assert "`path<TAB>stem`" in content, path
    assert "fall back to `.graphify_uncached.txt`" in content, path
    assert ".graphify_uncached_stems.txt" in content.split("Clean up temp files:")[-1].splitlines()[0], path


def test_the_skill_scan_sees_the_hosts():
    assert len(_skill_artifacts()) == 14, [p for p, _ in _skill_artifacts()]
