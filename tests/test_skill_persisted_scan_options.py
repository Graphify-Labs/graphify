"""Skill scans must preserve the CLI's persisted corpus boundaries (#4240).

Two delivery paths carry the scan:

* Split hosts call ``graphify pipeline detect`` / ``detect-incremental``, whose
  bodies live in ``graphify.pipeline``. With #197 the persisted-options read moved
  from an inline ``python -c`` block into those steps, so the guard now exercises
  the step functions directly.
* The aider/devin monoliths still inline ``detect(Path('INPUT_PATH'))`` and are
  checked by executing the extracted block, as before.
"""
from __future__ import annotations
import json
import re
import subprocess
import sys
from pathlib import Path
import pytest
from graphify import paths
from tools.skillgen import gen
from graphify.detect import detect, save_manifest
from graphify.pipeline import step_detect, step_detect_incremental
from graphify.watch import _write_build_config, _read_build_excludes, _read_build_gitignore


def _monolith_scan_blocks():
    """The inline detect/detect_incremental blocks that remain (aider/devin only)."""
    found = []
    for art in gen.render_all(gen.load_platforms()):
        for block in re.findall(r'```bash\n(.*?)```', art.content, re.S):
            if "result = detect(Path('INPUT_PATH')" not in block and "result = detect_incremental(Path('INPUT_PATH')" not in block:
                continue
            m = re.search(r' -c "\n(.*)\n"', block, re.S)
            if m:
                found.append((art.path, m.group(1).replace('\\"', '"')))
    # Only the two monoliths keep the inline form; the split hosts call the
    # pipeline steps (covered below).
    assert len(found) == 4, f"expected the 4 monolith scan blocks, found {len(found)}"
    return found


def _make_corpus(tmp_path):
    corpus = tmp_path / 'corpus'
    corpus.mkdir()
    subprocess.run(['git', 'init', '-q', str(corpus)], check=True)
    (corpus / '.gitignore').write_text('notes/\n', encoding='utf-8')
    (corpus / 'notes').mkdir()
    (corpus / 'docs').mkdir()
    for name in ('notes/a.md', 'docs/b.md', 'docs/skip.md'):
        (corpus / name).write_text('# sample\n', encoding='utf-8')
    out = tmp_path / 'graphify-out'
    _write_build_config(out, excludes=['docs/skip.md'], gitignore=False)
    return corpus, out


@pytest.mark.parametrize('art,source', _monolith_scan_blocks(), ids=lambda value: value.split('\n', 1)[0])
def test_monolith_scan_honors_persisted_options(tmp_path, monkeypatch, art, source):
    monkeypatch.delenv('GRAPHIFY_OUT', raising=False)
    monkeypatch.setattr(paths, 'GRAPHIFY_OUT', 'graphify-out')
    corpus, out = _make_corpus(tmp_path)
    # Match the skill's documented CWD-relative output/manifest layout, with
    # INPUT_PATH pointing to a distinct corpus rather than the output parent.
    if 'detect_incremental' in source:
        files = detect(corpus, gitignore=False, extra_excludes=['docs/skip.md'])['files']
        save_manifest(files, str(out / 'manifest.json'), root=corpus)
    # Only exercise the scan contract, not subsequent sidecar/report steps.
    src = source.split('result = ', 1)[0] + 'result = ' + source.split('result = ', 1)[1].split('\n', 1)[0]
    src += '\nprint(json.dumps(result))\n'
    src = src.replace('INPUT_PATH', corpus.as_posix())
    result = subprocess.run([sys.executable, '-c', src], cwd=tmp_path, check=True, capture_output=True, text=True)
    data = json.loads(result.stdout)
    actual = {Path(f).relative_to(corpus).as_posix() for files in data['files'].values() for f in files}
    assert actual == {'notes/a.md', 'docs/b.md'}, art
    if 'detect_incremental' in source:
        assert data['excluded_files'] == [], art


def test_pipeline_step_detect_honors_persisted_options(tmp_path, monkeypatch):
    """`graphify pipeline detect` reuses the persisted excludes/gitignore (#4240)."""
    monkeypatch.delenv('GRAPHIFY_OUT', raising=False)
    monkeypatch.setattr(paths, 'GRAPHIFY_OUT', 'graphify-out')
    corpus, _ = _make_corpus(tmp_path)
    result = step_detect(corpus, out=tmp_path)
    actual = {Path(f).relative_to(corpus).as_posix() for files in result['files'].values() for f in files}
    assert actual == {'notes/a.md', 'docs/b.md'}


def test_pipeline_step_detect_incremental_honors_persisted_options(tmp_path, monkeypatch):
    """`graphify pipeline detect-incremental` reuses the same boundaries (#4240)."""
    monkeypatch.delenv('GRAPHIFY_OUT', raising=False)
    monkeypatch.setattr(paths, 'GRAPHIFY_OUT', 'graphify-out')
    corpus, _ = _make_corpus(tmp_path)
    result = step_detect_incremental(corpus, out=tmp_path)
    actual = {Path(f).relative_to(corpus).as_posix()
              for files in result.get('new_files', {}).values() for f in files}
    assert 'docs/skip.md' not in actual
    assert {'notes/a.md', 'docs/b.md'} <= actual


@pytest.mark.parametrize('contents', [None, '{', '[]', '{"gitignore": "false", "excludes": 12}'])
def test_absent_or_malformed_build_options_use_defaults(tmp_path, contents):
    if contents is not None:
        (tmp_path / '.graphify_build.json').write_text(contents, encoding='utf-8')
    assert _read_build_gitignore(tmp_path) is True
    assert _read_build_excludes(tmp_path) == []


def test_detection_api_explicit_options_are_not_overridden(tmp_path):
    subprocess.run(['git', 'init', '-q', str(tmp_path)], check=True)
    (tmp_path / '.gitignore').write_text('notes/\n', encoding='utf-8')
    (tmp_path / 'notes').mkdir()
    for name in ('notes/a.md', 'keep.md'):
        (tmp_path / name).write_text('# sample\n', encoding='utf-8')
    _write_build_config(tmp_path / 'graphify-out', excludes=['keep.md'], gitignore=False)
    data = detect(tmp_path, gitignore=True, extra_excludes=[])
    actual = {Path(f).name for files in data['files'].values() for f in files}
    assert actual == {'keep.md'}
