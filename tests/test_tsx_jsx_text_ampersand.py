"""#2922: a bare ``&`` in TSX JSX text must not break extraction.

tree-sitter-typescript requires ``&`` inside JSX text (the run between ``>``
and ``<`` inside an element) to begin an HTML entity reference
(``&amp;``, ``&#NN;``, ``&lt;``, ...). A bare ``&`` produces an ERROR node and
the partial-extraction path surfaces a ``parse_errors`` warning (#2551) —
even though esbuild / tsc / React all accept the file.

Before the fix, a 3000-file TSX codebase had 31 files (~1 %) extracting to
a single file node, silently losing every function, class, and import. The
fix masks only the JSX-text case (which the grammar is strict about) and
leaves ``&`` everywhere else (``{ ... }``, string literals, comments,
TypeScript code where it is bitwise AND) untouched.

Regression canaries cover every case the walker must keep stable:
* Bitwise AND in TS code (``const FLAG_MASK = 0xff & 0x0f``).
* ``&&`` inside a JSX expression container.
* An existing ``&amp;`` entity in JSX text — passed through unchanged.
* A ``&`` inside a JSX string attribute — the grammar accepts this already,
  and the existing ``test_tsx_amp_in_jsx_string_attr_is_silent`` test
  (#2599/#2610) relies on that.
* Generics (``function f<T>``, ``const pick = <T,>(x: T) => x``,
  ``y as number``) — ``<`` after an identifier / keyword must stay in code
  mode so a subsequent bitwise ``&`` is not masked.
* Code after a closed JSX element — the closing tag pops the element's
  ``jsx_text`` context, so a later ``a & b`` binding stays bitwise AND
  and is not corrupted into ``&amp;`` (which would reintroduce a parse
  error — the very bug class this fix removes).
* Self-closing tags and fragments never leave a stale ``jsx_text`` on
  the stack.
* Nested JSX inside a JSX expression container
  (``{ok ? <span>a & b</span> : null}``) is masked like top-level JSX.
* Single-letter uppercase components (``<A>x & y</A>``) are JSX elements,
  not generics — while ``<T>(x: T) => x`` (``(`` after ``<T>``) stays code.
* Generic arrows and function types — single-letter or multi-character
  (``<TKey>(x: TKey) => x``, ``type F = <TKey>(x: TKey) => void``, with or
  without a return-type annotation) — stay code, so a later bitwise
  ``a & b`` is never corrupted into ``a   b`` (which would reintroduce a
  parse error).
* The bytes mask is fully byte-preserving: every ``&`` in JSX text is
  replaced by a single ASCII space, so tree-sitter byte offsets and
  ``source[start_byte:end_byte]`` slices stay aligned with the original
  source (non-UTF-8 bytes round-trip unchanged).
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from graphify.extract import _mask_tsx_ampersands, _tsx_mask_source, extract


def _extract(tmp_path, files: dict[str, str]):
    for name, body in files.items():
        p = tmp_path / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body)
    old = os.getcwd()
    try:
        os.chdir(tmp_path)
        return extract([Path(n) for n in files],
                       cache_root=tmp_path / ".cache", parallel=False)
    finally:
        os.chdir(old)


def _labels(r):
    return {n["label"] for n in r["nodes"]}


def _assert_silent(err):
    assert "syntax errors" not in err
    assert "partially extracted" not in err


def test_fixture_extracts_all_symbols(tmp_path, capsys):
    """The fixture covers every JSX-text shape a real Portuguese-locale UI
    file trips the gate on — bare ``&``, ``&`` between non-ASCII letters,
    multiple bare ``&`` in one run, alongside JSX attribute ``&`` and code
    bitwise ``&`` in the same file."""
    fixture = Path("tests/fixtures/tsx_jsx_text_ampersand.tsx").resolve()
    old = os.getcwd()
    try:
        os.chdir(tmp_path)
        r = extract([fixture], cache_root=tmp_path / ".cache", parallel=False)
    finally:
        os.chdir(old)

    labels = _labels(r)
    # Top-level bindings and their members must all survive.
    assert {"Page()", "Component", "fragment"} <= labels
    _assert_silent(capsys.readouterr().err)
    # No parse_errors metadata on the file.
    assert r.get("parse_errors") in (None, [])


def test_bare_amp_in_jsx_text_is_silent(tmp_path, capsys):
    r = _extract(tmp_path, {
        "page.tsx": (
            "declare const helper: (n: number) => string;\n"
            "export function Page() {\n"
            "    return <h1>VoIP & Chamadas</h1>;\n"
            "}\n"
            "export const FLAG_MASK = 0xff & 0x0f;\n"
            "export const use = FLAG_MASK;\n"
        ),
    })
    assert "Page()" in _labels(r)
    _assert_silent(capsys.readouterr().err)


def test_bitwise_and_in_ts_code_is_preserved(tmp_path, capsys):
    """Bitwise ``&`` in TS code must NOT be masked — the walker has to keep
    code mode for ``<`` after an identifier (``FLAG_MASK``, ``helper``)
    so the ``&`` stays bitwise AND, and the file extracts cleanly."""
    r = _extract(tmp_path, {
        "bits.ts": (
            "export const FLAG_MASK = 0xff & 0x0f;\n"
            "export function bits(x: number) { return x & FLAG_MASK }\n"
        ),
    })
    assert {"FLAG_MASK", "bits()"} <= _labels(r)
    _assert_silent(capsys.readouterr().err)


def test_double_ampersand_in_jsx_expression_is_preserved(tmp_path, capsys):
    """``&&`` lives inside ``{ ... }``, not in JSX text — the walker must
    stay in code mode there."""
    r = _extract(tmp_path, {
        "view.tsx": (
            "export const view = <div>{true && <span>hi</span>}</div>;\n"
        ),
    })
    assert "view" in _labels(r)
    _assert_silent(capsys.readouterr().err)


def test_existing_entity_in_jsx_text_is_passed_through(tmp_path, capsys):
    """Already-formed ``&amp;`` is a real HTML entity and must not be
    double-masked (which would produce ``&amp;amp;``)."""
    r = _extract(tmp_path, {
        "entity.tsx": (
            "export const tag = <span>three &amp; four</span>;\n"
        ),
    })
    assert "tag" in _labels(r)
    _assert_silent(capsys.readouterr().err)


# Walker unit cases, exercised through a single parametrized call site so
# the helper keeps exactly one production caller (its ``_tsx_mask_source``
# wiring) — the afferent-coupling health gate counts direct test call sites.
_MASK_CASES = [
    # --- JSX text: bare ``&`` masked to a single ASCII space, keeping source
    # byte offsets aligned with the original file.
    # Exact-output match covers: masked exactly once, no double-mask
    # (``&amp;amp;``), surrounding text byte-identical except the one-byte
    # placeholder.
    ('<div>VoIP & Chamadas</div>',
     '<div>VoIP   Chamadas</div>'),
    # Every bare ``&`` in one JSX-text run is masked independently.
    ('<p>Welcome & hello. Mixed & multiple & ampersands.</p>',
     '<p>Welcome   hello. Mixed   multiple   ampersands.</p>'),
    # --- Non-JSX-text ``&`` locations are left intact so the TSX grammar
    # still sees the same shape it always did.
    # JSX attribute string — grammar already accepts.
    ('<a href="/search?q=a&b=c">link</a>',
     '<a href="/search?q=a&b=c">link</a>'),
    # Bitwise AND in TS code.
    ('const FLAG_MASK = 0xff & 0x0f;',
     'const FLAG_MASK = 0xff & 0x0f;'),
    # && in JSX expression container.
    ('<ul>{items.filter(it => it.flag && it.visible)}</ul>',
     '<ul>{items.filter(it => it.flag && it.visible)}</ul>'),
    # Comment line.
    ('// foo & bar\nconst x = 1;',
     '// foo & bar\nconst x = 1;'),
    # String literal.
    ('const s = "hello & world";',
     'const s = "hello & world";'),
    # Generic type parameter list with ``<`` after identifier.
    ('function foo<T>(x: T): T { return x }',
     'function foo<T>(x: T): T { return x }'),
    # Single-uppercase-letter generic ``<T>``.
    ('const x = foo<T>(1);',
     'const x = foo<T>(1);'),
    # Single-letter generic arrow: ``(`` right after ``<T>`` stays code.
    ('const id = <T>(x: T) => x;\nconst b = 1 & 2;\n',
     'const id = <T>(x: T) => x;\nconst b = 1 & 2;\n'),
    # Single-letter function-type position: also ``(`` after ``<T>``.
    ('let f: <T>(x: T) => void = null;\nconst b = 1 & 2;\n',
     'let f: <T>(x: T) => void = null;\nconst b = 1 & 2;\n'),
    # Multi-character generic arrow — ``<TKey>(x: TKey) => x`` must stay
    # code: classifying it as JSX would strand jsx_text and corrupt the
    # later bitwise ``1 & 2`` into ``1   2`` (a parse error).
    ('const pick = <TKey>(x: TKey) => x;\nconst b = 1 & 2;\n',
     'const pick = <TKey>(x: TKey) => x;\nconst b = 1 & 2;\n'),
    # Return-type annotation between parameter list and arrow.
    ('const pick = <TKey>(x: TKey): TKey => x;\nconst b = 1 & 2;\n',
     'const pick = <TKey>(x: TKey): TKey => x;\nconst b = 1 & 2;\n'),
    # Function-type position, multi-character type parameter.
    ('type F = <TKey>(x: TKey) => void;\nconst b = 1 & 2;\n',
     'type F = <TKey>(x: TKey) => void;\nconst b = 1 & 2;\n'),
    # Arrow generic with comma.
    ('const pick = <T,>(x: T) => x;',
     'const pick = <T,>(x: T) => x;'),
    # ``as`` cast — ``<`` after the keyword ``as`` is in expression
    # position; the walker must NOT enter jsx_text here.
    ('const z = y as number;',
     'const z = y as number;'),
    # ``return`` keyword — ``<Foo/>`` after ``return`` is JSX.
    ('function f() { return <Foo/> }',
     'function f() { return <Foo/> }'),
    # ``new`` keyword.
    ('const c = new <Type>(arg);',
     'const c = new <Type>(arg);'),
    # --- Tag lifecycle: closing tags pop the element's ``jsx_text``,
    # self-closing tags and fragments never leave one behind, and nested
    # elements unwind to the parent's text.
    # Closing tag pops jsx_text → later code ``&`` stays bitwise.
    ('const a = <div>x & y</div>;\nconst b = 1 & 2;\n',
     'const a = <div>x   y</div>;\nconst b = 1 & 2;\n'),
    # Self-closing (tight and spaced) never opens jsx_text.
    ('const a = <br/>;\nconst b = <br />;\nconst c = 1 & 2;\n',
     'const a = <br/>;\nconst b = <br />;\nconst c = 1 & 2;\n'),
    # Fragment open/close round-trips back to code.
    ('const a = <>x & y</>;\nconst b = 1 & 2;\n',
     'const a = <>x   y</>;\nconst b = 1 & 2;\n'),
    # Nested element: after the child closes, the parent's JSX text is
    # still masked; after the parent closes, code is not.
    ('const a = <p><b>q & r</b>t & u</p>;\nconst z = 1 & 2;\n',
     'const a = <p><b>q   r</b>t   u</p>;\nconst z = 1 & 2;\n'),
    # --- Single-letter uppercase components (``<A>``, ``<I>`` — icon/nav
    # shorthand) are JSX, not generics: text is masked, the close tag
    # pops jsx_text, and an empty element leaves no stale context.
    ('export const nav = <A>VoIP & Chamadas</A>;',
     'export const nav = <A>VoIP   Chamadas</A>;'),
    ('const a = <A>x & y</A>;\nconst b = 1 & 2;\n',
     'const a = <A>x   y</A>;\nconst b = 1 & 2;\n'),
    ('const a = <A></A>;\nconst b = 1 & 2;\n',
     'const a = <A></A>;\nconst b = 1 & 2;\n'),
    # Paren-initial JSX text has no arrow tail, so an uppercase
    # component still masks (``_generic_arrow_tail`` returns False).
    ('const el = <Panel>(note) & more</Panel>;',
     'const el = <Panel>(note)   more</Panel>;'),
    # Nested JSX inside an expression container is masked, the
    # container's own ``&&`` is not, and code after is not.
    ('const a = <div>{x && <i>i & j</i>}</div>;\nconst z = 1 & 2;\n',
     'const a = <div>{x && <i>i   j</i>}</div>;\nconst z = 1 & 2;\n'),
    # Attribute strings still untouched, element text still masked.
    ('const a = <div title="x & y">t & v</div>;',
     'const a = <div title="x & y">t   v</div>;'),
    # --- Regex literals: ``<``/``>``/``&`` inside a ``/.../`` body are not
    # JSX and must not be masked. The walker enters a regex context so the
    # ``/`` closing delimiter ends it, including unescaped ``/`` inside
    # character classes and a trailing flag run.
    ('const r = /<a>&b<\\/a>/;',
     'const r = /<a>&b<\\/a>/;'),
    ('const r = /a & b/gi;',
     'const r = /a & b/gi;'),
    ('const r = /[a&b]/;',
     'const r = /[a&b]/;'),
    ('const r = /[]]/;',
     'const r = /[]]/;'),
    ('const r = /[^]]/;',
     'const r = /[^]]/;'),
    ('const a = [<div/>, /<a>&b<\\/a>/];',
     'const a = [<div/>, /<a>&b<\\/a>/];'),
    ('const a = { r: /<a>&b<\\/a>/ };',
     'const a = { r: /<a>&b<\\/a>/ };'),
    ('return /<a>&b<\\/a>/;',
     'return /<a>&b<\\/a>/;'),
    # --- Division is not a regex (prev token is a value).
    ('const a = 1 / 2 & 3;',
     'const a = 1 / 2 & 3;'),
    ('const a = foo() / 2;',
     'const a = foo() / 2;'),
    ('const a = <div/> / 2;',
     'const a = <div/> / 2;'),
    # --- ``extends`` as a JSX attribute must not be misread as a generic
    # constraint; the element's children are still JSX text.
    ('const a = <Foo extends="a & b">t & v</Foo>;',
     'const a = <Foo extends="a & b">t   v</Foo>;'),
    ('const a = <Foo extends={a & b}>t & v</Foo>;',
     'const a = <Foo extends={a & b}>t   v</Foo>;'),
    ('const a = <Foo extends>t & v</Foo>;',
     'const a = <Foo extends>t   v</Foo>;'),
    # --- Generic arrow / function-type tails keep ``&`` in code even when
    # the return type or default parameter contains a ``;`` or ``)``.
    ('const pick = <TKey>(x: TKey): { a: number; b: string } => x;\nconst b = 1 & 2;\n',
     'const pick = <TKey>(x: TKey): { a: number; b: string } => x;\nconst b = 1 & 2;\n'),
    ('const f = <T>(x: T = ")") => x;\nconst b = 1 & 2;\n',
     'const f = <T>(x: T = ")") => x;\nconst b = 1 & 2;\n'),
    ('const f = <T>(x: T = /a\\/b/g) => x;\nconst b = 1 & 2;\n',
     'const f = <T>(x: T = /a\\/b/g) => x;\nconst b = 1 & 2;\n'),
    ('const f = <T>(x: T): "a; b" => x;\nconst b = 1 & 2;\n',
     'const f = <T>(x: T): "a; b" => x;\nconst b = 1 & 2;\n'),
    # A real generic constraint ``<T extends X>`` still stays code.
    ('function f<T extends X>() { return 1 & 2; }',
     'function f<T extends X>() { return 1 & 2; }'),
    # --- Fast-path: sources without ``&`` (or empty) are a no-op.
    ('', ''),
    ('// nothing here\nconst x = 1;\n',
     '// nothing here\nconst x = 1;\n'),
]


@pytest.mark.parametrize('src,expected', _MASK_CASES)
def test_mask_walker(src, expected):
    """Walker unit checks: bare ``&`` is masked to a single ASCII space
    only in JSX text; attributes, ``{ ... }`` containers, strings, comments,
    and TS code (bitwise AND, generics) are byte-identical."""
    got = _mask_tsx_ampersands(src)
    assert got == expected, (
        f"walker mangled {src!r}\n"
        f"  expected: {expected!r}\n"
        f"  got:      {got!r}"
    )


def test_mask_source_round_trips_non_utf8_bytes():
    """``LanguageConfig.source_transform`` byte contract: the transform
    must be fully byte-preserving. A bare ``&`` in JSX text is replaced by
    a single ASCII space, so tree-sitter offsets and ``source[start_byte:
    end_byte]`` slices stay aligned with the original file. Non-UTF-8 bytes
    (a latin-1 comment) round-trip unchanged instead of being rewritten to
    U+FFFD, which would silently alter the source the engine parses."""
    src = b"<Box>a & b</Box>  // caf\xe9 latin-1 comment\n"
    out = _tsx_mask_source(src)
    assert out.startswith(b"<Box>a   b</Box>")
    assert b"caf\xe9" in out


@pytest.mark.parametrize('src,expected', [
    (b'<Box>a & b</Box>', b'<Box>a   b</Box>'),
    ('<Box>Conexões & Integrações</Box>'.encode('utf-8'),
     '<Box>Conexões   Integrações</Box>'.encode('utf-8')),
    # Non-BMP (4-byte UTF-8) emoji in JSX text: the replacement stays one
    # byte, so offsets remain aligned with the original file.
    ('<Box>🚀 & Chamadas</Box>'.encode('utf-8'),
     '<Box>🚀   Chamadas</Box>'.encode('utf-8')),
    (b'<Box>a & b</Box>  // caf\xe9 latin-1 comment\n',
     b'<Box>a   b</Box>  // caf\xe9 latin-1 comment\n'),
    (b'<Box>a & b</Box> \xff\xfe',
     b'<Box>a   b</Box> \xff\xfe'),
    (b'const x = 1 & 2;', b'const x = 1 & 2;'),
])
def test_mask_source_preserves_byte_length(src, expected):
    """The ``_tsx_mask_source`` contract is ``bytes -> bytes`` and must be
    byte-length-preserving. Every non-ampersand byte survives the round trip,
    and a bare ``&`` in JSX text is replaced by a single ASCII space so the
    parser sees the same offsets as the original file. This covers multibyte
    UTF-8 JSX text and invalid-UTF-8 bytes that round-trip via
    ``surrogateescape``."""
    out = _tsx_mask_source(src)
    assert isinstance(out, bytes)
    assert len(out) == len(src)
    assert out == expected


def test_code_after_jsx_element_is_not_masked(tmp_path, capsys):
    """A closing tag must exit the element's ``jsx_text`` context: code
    after ``</div>`` is TS code again, so a bitwise ``&`` there must not
    be masked (masking it would turn valid code into a parse error)."""
    r = _extract(tmp_path, {
        "page.tsx": (
            "export function Page() {\n"
            "    return <div>VoIP & Chamadas</div>;\n"
            "}\n"
            "export const FLAG_MASK = 0xff & 0x0f;\n"
            "export const use = FLAG_MASK;\n"
        ),
    })
    assert {"Page()", "FLAG_MASK", "use"} <= _labels(r)
    _assert_silent(capsys.readouterr().err)


def test_nested_jsx_in_expression_container_is_masked(tmp_path, capsys):
    """JSX nested inside a JSX expression container
    (``{ok ? <span>a & b</span> : null}``) must be masked like top-level
    JSX — before, the walker stayed in expression mode and the bare ``&``
    kept producing an ERROR node."""
    r = _extract(tmp_path, {
        "view.tsx": (
            "export const view = "
            "<div>{true ? <span>VoIP & Chamadas</span> : null}</div>;\n"
        ),
    })
    assert "view" in _labels(r)
    _assert_silent(capsys.readouterr().err)
    assert r.get("parse_errors") in (None, [])


def test_non_bmp_jsx_text_ampersand_is_silent(tmp_path, capsys):
    """A non-BMP character (e.g. U+1F680 🚀, 4 UTF-8 bytes) in JSX text
    followed by a bare ``&`` must not shift parser offsets. The mask
    replaces ``&`` with a single ASCII space, so the byte length of the
    source stays identical before and after the transform."""
    r = _extract(tmp_path, {
        "page.tsx": (
            "export function Page() {\n"
            "    return <Box>🚀 & Chamadas</Box>;\n"
            "}\n"
        ),
    })
    assert "Page()" in _labels(r)
    _assert_silent(capsys.readouterr().err)
    assert r.get("parse_errors") in (None, [])

