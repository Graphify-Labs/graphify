r"""URL-shaped read targets must not fool the out-of-project guard.

`_is_cwd_relative` answers "no root and no drive" to decide whether a
`file_path`/`path` value is cwd-anchored. A URL is rootless and driveless by
that exact same test: `https://example.com/source.py`,
`myscheme://x.py` and even a bare `www.example.com/source.py` all have no
`root` and no `drive`, so -- unmodified -- they short-circuit `_run_hook_guard`
straight to "in project" and the (correct, untouched) containment check below
never runs. Reproduced live against `graphify hook-guard read`, cwd at a
graphed project:

    https://example.com/source.py                  -> NUDGE  (wrong)
    www.example.com/source.py                      -> NUDGE  (wrong)
    <root>/local:/source.py                        -> NUDGE  (wrong; a naive
                                                        host-side path-join
                                                        glues a rootless
                                                        local://source.py onto
                                                        an absolute prefix,
                                                        which the containment
                                                        check can't tell apart
                                                        from a real file)
    <root>/artifact:/5.py                           -> NUDGE  (wrong, same)
    /etc/elsewhere/source.py                        -> silent (right)
    src/usr/local/pkg/pfblockerng/pfb_unbound.py    -> NUDGE  (right)

Three traps a naive "rootless value carrying `scheme://` is not cwd-relative"
rule would get wrong:

  1. `file://` is LOCAL. OMP's own pipeline strips it and resolves the
     underlying path (its `strictExternalUrlRe` deliberately omits `file`),
     so `file:///<project>/src/foo.py` must still nudge -- silencing it would
     be a false negative worse than the bug this fixes.
  2. `www.host/path` carries no `://` at all, so no scheme rule fires on it.
     Decision recorded here: it IS handled, existence-gated exactly like
     OMP's own `resolveToolSearchScope` ("an existing local path wins over
     URL") -- `_is_external_www_target` below, not `_is_cwd_relative` itself,
     which has no cwd/root context to make that call.
  3. An unrecognized scheme (`myscheme://x`) is LOCAL to OMP's own
     classifier, but this guard deliberately diverges: harness-agnostic
     silence beats a harness-specific scheme allow-list.

Input is normalized (trim + de-quote, `_normalize_hook_path`) before any
shape test, so a quoted or whitespace-padded value classifies identically to
its literal form.
"""
import io
import json
import sys
import time

import pytest

import graphify.cli as cli
from graphify.cli import (
    _has_embedded_url_scheme_segment,
    _is_cwd_relative,
    _is_external_www_target,
    _normalize_hook_path,
)


# ---------------------------------------------------------------------------
# Classification units
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("value", [
    "https://example.com/source.py",
    "myscheme://x.py",   # unrecognized scheme (trap 3): still rejected
    '  "https://example.com/source.py"  ',  # quoted + whitespace-padded
])
def test_url_prefixed_values_are_not_cwd_relative(value):
    assert _is_cwd_relative(value) is False, value


def test_file_url_is_not_naively_cwd_relative(tmp_path):
    """file:// (trap 1) strips to an absolute local path, so it is NOT the
    naive "no root, no drive -> in project" shortcut -- it goes through the
    real containment check below, exercised end-to-end further down."""
    target = tmp_path / "src" / "foo.py"
    assert _is_cwd_relative(f"file://{target.as_posix()}") is False


def test_in_project_relative_paths_are_unaffected():
    for value in ["src/mod.py", "a.py", "./rel.py", '  "src/mod.py"  ']:
        assert _is_cwd_relative(value) is True, value


def test_absolute_out_of_project_path_is_unaffected():
    """Control: an ordinary absolute path outside the project, no URL
    involved -- must keep working exactly as before."""
    assert _is_cwd_relative("/etc/elsewhere/source.py") is False


def test_embedded_scheme_segment_detects_a_mangled_absolute_url():
    """<root>/local:/source.py and <root>/artifact:/5.py: what a naive
    host-side path-join leaves behind when it glues a rootless scheme://...
    value onto an absolute prefix instead of routing it through a URL
    handler. _is_cwd_relative alone can't catch these (they DO have a root),
    so this is the companion check the call site also runs."""
    assert _has_embedded_url_scheme_segment("/root/git/pfBlockerNG/local:/source.py") is True
    assert _has_embedded_url_scheme_segment("/root/git/pfBlockerNG/artifact:/5.py") is True


def test_embedded_scheme_segment_is_silent_on_ordinary_absolute_paths():
    assert _has_embedded_url_scheme_segment("/etc/elsewhere/source.py") is False
    assert _has_embedded_url_scheme_segment("/root/git/pfBlockerNG/src/mod.py") is False


def test_www_target_is_external_only_without_a_matching_local_file(tmp_path):
    """Trap 2, decided: www. IS handled, gated on local existence (mirrors
    OMP's own "an existing local path wins over URL" precedence)."""
    assert _is_external_www_target("www.example.com/source.py", tmp_path) is True
    local = tmp_path / "www.example.com" / "source.py"
    local.parent.mkdir(parents=True)
    local.write_text("# real file", encoding="utf-8")
    assert _is_external_www_target("www.example.com/source.py", tmp_path) is False
    assert _is_external_www_target("src/mod.py", tmp_path) is False


def test_normalize_hook_path_strips_padding_quotes_and_file_scheme():
    assert _normalize_hook_path('  "src/mod.py"  ') == "src/mod.py"
    assert _normalize_hook_path("src/mod.py") == "src/mod.py"
    assert _normalize_hook_path("file:///abs/proj/foo.py") == "/abs/proj/foo.py"


def test_normalize_hook_path_file_url_authority_rows():
    """RFC 8089 / Node's ``url.fileURLToPath`` (throws
    ``ERR_INVALID_FILE_URL_HOST`` for anything else): a ``file://`` URL is
    local only when its authority is empty or ``localhost``. Only those two
    forms may be reduced to their bare path component; any other authority
    names a remote host and must be left intact for `_is_foreign_url_scheme`
    to classify."""
    assert _normalize_hook_path("file:///abs/proj/foo.py") == "/abs/proj/foo.py"
    assert _normalize_hook_path("file://localhost/abs/proj/foo.py") == "/abs/proj/foo.py"
    assert _normalize_hook_path("file://evil.com/abs/proj/foo.py") == "file://evil.com/abs/proj/foo.py"


# ---------------------------------------------------------------------------
# End-to-end through the guard (real stdin JSON, cwd at a graphed project)
# ---------------------------------------------------------------------------

def _project(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    f = src / "mod.py"
    f.write_text("def x():\n    return 1\n", encoding="utf-8")
    out = tmp_path / "graphify-out"
    out.mkdir()
    (out / "manifest.json").write_text(
        json.dumps({"src/mod.py": {"mtime": 1}}), encoding="utf-8")
    time.sleep(0.02)
    (out / "graph.json").write_text('{"nodes":[],"links":[]}', encoding="utf-8")
    return f


def _invoke(tmp_path, monkeypatch, file_path):
    monkeypatch.chdir(tmp_path)
    payload = {"session_id": "s1", "tool_name": "Read",
               "tool_input": {"file_path": str(file_path)}}

    class _Stdin:
        buffer = io.BytesIO(json.dumps(payload).encode())
    monkeypatch.setattr(sys, "stdin", _Stdin())
    buf = io.StringIO()
    monkeypatch.setattr(sys, "stdout", buf)
    cli._run_hook_guard("read")
    return buf.getvalue()


def test_https_url_is_silent(tmp_path, monkeypatch):
    _project(tmp_path)
    assert _invoke(tmp_path, monkeypatch, "https://example.com/source.py").strip() == ""


def test_www_host_with_no_local_match_is_silent(tmp_path, monkeypatch):
    _project(tmp_path)
    assert _invoke(tmp_path, monkeypatch, "www.example.com/source.py").strip() == ""


def test_mangled_absolute_local_scheme_url_is_silent(tmp_path, monkeypatch):
    _project(tmp_path)
    target = f"{tmp_path}/local:/source.py"
    assert _invoke(tmp_path, monkeypatch, target).strip() == ""


def test_mangled_absolute_artifact_scheme_url_is_silent(tmp_path, monkeypatch):
    _project(tmp_path)
    target = f"{tmp_path}/artifact:/5.py"
    assert _invoke(tmp_path, monkeypatch, target).strip() == ""


def test_unrecognized_scheme_is_silent(tmp_path, monkeypatch):
    _project(tmp_path)
    assert _invoke(tmp_path, monkeypatch, "myscheme://x.py").strip() == ""


def test_absolute_out_of_project_path_stays_silent(tmp_path, monkeypatch):
    """Control (right today, must stay right): containment already works."""
    _project(tmp_path)
    assert _invoke(tmp_path, monkeypatch, "/etc/elsewhere/source.py").strip() == ""


def test_in_project_relative_path_still_nudges(tmp_path, monkeypatch):
    """Control (right today, must stay right)."""
    _project(tmp_path)
    assert "MANDATORY" in _invoke(tmp_path, monkeypatch, "src/mod.py")


def test_file_url_to_an_indexed_in_project_file_still_nudges(tmp_path, monkeypatch):
    """Trap 1: file:// must NOT regress to silent."""
    f = _project(tmp_path)
    assert "MANDATORY" in _invoke(tmp_path, monkeypatch, f"file://{f.as_posix()}")


def test_file_url_with_remote_authority_is_silent(tmp_path, monkeypatch):
    """VALID #4: a non-local authority (RFC 8089) names a remote host, not
    the in-project file it happens to share a path with -- must NOT nudge."""
    f = _project(tmp_path)
    assert _invoke(tmp_path, monkeypatch, f"file://evil.com{f.as_posix()}").strip() == ""


def test_file_url_with_localhost_authority_still_nudges(tmp_path, monkeypatch):
    """localhost is local per RFC 8089 / Node's url.fileURLToPath."""
    f = _project(tmp_path)
    assert "MANDATORY" in _invoke(tmp_path, monkeypatch, f"file://localhost{f.as_posix()}")


def test_quoted_and_padded_https_url_is_silent(tmp_path, monkeypatch):
    _project(tmp_path)
    assert _invoke(tmp_path, monkeypatch, '  "https://example.com/source.py"  ').strip() == ""


def test_padded_in_project_path_still_nudges(tmp_path, monkeypatch):
    """Leading whitespace only (not quotes, not trailing padding): the
    extension allow-list this guard must not touch splits on the final "/"
    and matches the tail verbatim, so trailing junk after ".py" fails IT
    regardless of classification -- that is pre-existing, out-of-scope
    behaviour, not the URL-classification bug this file covers. Quoted and
    doubly-padded input is proven at the classification layer directly in
    test_in_project_relative_paths_are_unaffected above.
    """
    _project(tmp_path)
    assert "MANDATORY" in _invoke(tmp_path, monkeypatch, "  src/mod.py")
