"""PHP `use`-import-aware receiver typing: the decisive refusal (#21, closes #16).

`_resolve_php_member_calls` used to bind a receiver's short type name through a
corpus-wide index whose only refusal rule was "more than one candidate". A file
that writes `use Vendor\\Sdk\\Client;` has CLAIMED the name `Client` for a class
that is not in the corpus at all — but the resolver never saw `use` statements,
so the lone unrelated `App\\Local\\Client` satisfied the single-definition guard
and minted a wrong `INFERRED 0.8` edge.

`PhpNameResolver` (mirroring `CsharpNameResolver`) answers with a
`(node_id, decisive)` verdict and is consulted IN FRONT of that fallback: a
claimed name that does not land on an in-corpus class refuses instead of falling
back. The refusal is strictly subtractive; its additive counterpart — binding
the claimed FQN to the class whose file declares exactly that name (#22) — is
covered by `test_php_alias_binding.py`, and
`test_alias_renaming_to_an_unclaimed_short_name_binds_since_22` below pins the
boundary from this side.

Every test goes through the public `extract()` seam, and every positive case
carries a decoy class with an identically named method that must get no edge.
"""
from __future__ import annotations

from pathlib import Path

from graphify.extract import extract


def _calls(tmp_path: Path, files: dict[str, str]):
    paths = []
    for name, body in files.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
        paths.append(path)
    result = extract(paths, cache_root=tmp_path / "graphify-out")
    calls = {
        (edge["source"], edge["target"]): edge
        for edge in result["edges"]
        if edge.get("relation") == "calls"
    }
    return calls, result


def _find(result: dict, label: str, id_contains: str) -> str:
    return next(
        node["id"]
        for node in result["nodes"]
        if node.get("label") == label and id_contains in node["id"]
    )


# The canonical #16 fixture (spec #18 carries the same copy) plus a decoy that
# declares an identically named method: only the receiver's type tells them
# apart, so a bare-name match would light the decoy up.
_CLIENT = (
    "<?php\nnamespace App\\Local;\n"
    "class Client {\n    public function send(): int { return 1; }\n}\n"
)
_DECOY = (
    "<?php\nnamespace App\\Audit;\n"
    "class Recorder {\n    public function send(): int { return 0; }\n}\n"
)
_CORPUS = {
    "app/Local/Client.php": _CLIENT,
    "app/Audit/Recorder.php": _DECOY,
}


def _caller(uses: str = "", annotation: str = "Client",
            namespace: str = "App\\Http") -> str:
    return (
        "<?php\n"
        f"namespace {namespace};\n"
        f"{uses}"
        "class I {\n"
        f"    private {annotation} $c;\n"
        "    public function go(): int { return $this->c->send(); }\n"
        "}\n"
    )


def _sends(calls, caller: str) -> list[str]:
    return [tgt for src, tgt in calls if src == caller]


# ── the refusal: a claimed name that names no in-corpus class ─────────────────


def test_use_alias_outside_corpus_emits_no_edge(tmp_path: Path):
    """#16, cross-file: `use Vendor\\Sdk\\Client;` claims `Client` for a class
    this corpus does not contain. The lone `App\\Local\\Client` is a stranger."""
    calls, r = _calls(tmp_path, {
        **_CORPUS,
        "app/Http/I.php": _caller("use Vendor\\Sdk\\Client;\n"),
    })

    go = _find(r, ".go()", "_go")
    assert _sends(calls, go) == [], "an out-of-corpus `use` target must refuse"


def test_use_alias_outside_corpus_emits_no_edge_same_file(tmp_path: Path):
    """#16, same file: the stranger is declared in another namespace block of
    the calling file, so the same-file matcher could mint the edge too."""
    calls, r = _calls(tmp_path, {
        "app/Mixed/Both.php": (
            "<?php\n"
            "namespace App\\Local {\n"
            "    class Client { public function send(): int { return 1; } }\n"
            "}\n"
            "namespace App\\Http {\n"
            "    use Vendor\\Sdk\\Client;\n"
            "    class I {\n"
            "        private Client $c;\n"
            "        public function go(): int { return $this->c->send(); }\n"
            "    }\n"
            "}\n"
        ),
    })

    go = _find(r, ".go()", "_go")
    assert _sends(calls, go) == [], \
        "a same-file stranger must be refused like a cross-file one"


def test_group_use_alias_outside_corpus_emits_no_edge(tmp_path: Path):
    """The group form carries its FQN on the declaration's prefix (#19); the
    claim it makes is the same one."""
    calls, r = _calls(tmp_path, {
        **_CORPUS,
        "app/Http/I.php": _caller("use Vendor\\Sdk\\{Client};\n"),
    })

    go = _find(r, ".go()", "_go")
    assert _sends(calls, go) == []


def test_renaming_alias_over_an_out_of_corpus_target_emits_no_edge(tmp_path: Path):
    """`use X as Client;` claims the short name `Client` just as firmly."""
    calls, r = _calls(tmp_path, {
        **_CORPUS,
        "app/Http/I.php": _caller("use Vendor\\Sdk\\Handler as Client;\n"),
    })

    go = _find(r, ".go()", "_go")
    assert _sends(calls, go) == []


def test_written_fqn_outside_corpus_emits_no_edge(tmp_path: Path):
    """The compounding half of #16: an annotation that names the out-of-corpus
    class outright, with no `use` statement at all (#20 kept the written form)."""
    calls, r = _calls(tmp_path, {
        **_CORPUS,
        "app/Http/I.php": _caller(annotation="\\Vendor\\Sdk\\Client"),
    })

    go = _find(r, ".go()", "_go")
    assert _sends(calls, go) == []


def test_namespace_relative_annotation_outside_corpus_emits_no_edge(tmp_path: Path):
    """A written qualified name with no leading backslash is RELATIVE: inside
    `App\\Http`, `Local\\Client` means `App\\Http\\Local\\Client`, which exists
    nowhere — not `App\\Local\\Client`."""
    calls, r = _calls(tmp_path, {
        **_CORPUS,
        "app/Http/I.php": _caller(annotation="Local\\Client"),
    })

    go = _find(r, ".go()", "_go")
    assert _sends(calls, go) == []


# ── the guards: everything the refusal must NOT touch ─────────────────────────


def test_in_corpus_use_alias_keeps_its_edge(tmp_path: Path):
    """The positive guard: a `use` that names the real in-corpus class binds
    exactly as it does today (through the unique-short-name fallback), and the
    decoy that merely shares the method name still gets nothing."""
    calls, r = _calls(tmp_path, {
        **_CORPUS,
        "app/Http/I.php": _caller("use App\\Local\\Client;\n"),
    })

    go = _find(r, ".go()", "_go")
    send = _find(r, ".send()", "client")
    assert (go, send) in calls
    assert calls[(go, send)]["confidence"] == "INFERRED"
    assert (go, _find(r, ".send()", "recorder")) not in calls


def test_written_fqn_naming_the_in_corpus_class_keeps_its_edge(tmp_path: Path):
    calls, r = _calls(tmp_path, {
        **_CORPUS,
        "app/Http/I.php": _caller(annotation="\\App\\Local\\Client"),
    })

    go = _find(r, ".go()", "_go")
    assert (go, _find(r, ".send()", "client")) in calls
    assert (go, _find(r, ".send()", "recorder")) not in calls


def test_namespace_relative_annotation_in_corpus_keeps_its_edge(tmp_path: Path):
    """Inside namespace `App`, `Local\\Client` IS `App\\Local\\Client`."""
    calls, r = _calls(tmp_path, {
        **_CORPUS,
        "app/I.php": _caller(annotation="Local\\Client", namespace="App"),
    })

    go = _find(r, ".go()", "_go")
    assert (go, _find(r, ".send()", "client")) in calls
    assert (go, _find(r, ".send()", "recorder")) not in calls


def test_use_function_import_makes_no_class_claim(tmp_path: Path):
    """`use function` / `use const` import no class name (#26), in either
    spelling — so they claim nothing and the fallback runs untouched."""
    for index, uses in enumerate((
        "use function Vendor\\Sdk\\Client;\n",
        "use function Vendor\\Sdk\\{Client};\n",
        "use const Vendor\\Sdk\\Client;\n",
    )):
        calls, r = _calls(tmp_path / f"case{index}", {
            **_CORPUS, "app/Http/I.php": _caller(uses),
        })
        go = _find(r, ".go()", "_go")
        assert (go, _find(r, ".send()", "client")) in calls, uses
        assert (go, _find(r, ".send()", "recorder")) not in calls, uses


def test_unclaimed_short_name_still_falls_back(tmp_path: Path):
    """No `use`, no qualified form: the resolver knows nothing about the name
    and the corpus-wide fallback decides, exactly as before."""
    calls, r = _calls(tmp_path, {
        **_CORPUS,
        "app/Http/I.php": _caller(),
    })

    go = _find(r, ".go()", "_go")
    assert (go, _find(r, ".send()", "client")) in calls
    assert (go, _find(r, ".send()", "recorder")) not in calls


def test_alias_renaming_to_an_unclaimed_short_name_binds_since_22(tmp_path: Path):
    """The #21/#22 boundary, from the #21 side. `use App\\Local\\Client as Api;`
    names an in-corpus class under a WRITTEN short name (`Api`) nothing in the
    corpus is called, so #21's fallback found nothing and refused. The declared-
    FQN index (#22) follows the alias to its target — the recall win this test
    used to pin as out of scope."""
    calls, r = _calls(tmp_path, {
        **_CORPUS,
        "app/Http/I.php": _caller("use App\\Local\\Client as Api;\n", annotation="Api"),
    })

    go = _find(r, ".go()", "_go")
    send = _find(r, ".send()", "client")
    assert (go, send) in calls
    assert (go, _find(r, ".send()", "recorder")) not in calls


# ── the same verdicts across an incremental rebuild ───────────────────────────
#
# The `use` map belongs to the CALLING file, which `graphify update`/watch always
# re-dispatch, so the refusal needs no persisted marker (spec #18, decision 3).
# The context below is assembled exactly as `test_php_member_calls.py` mirrors
# watch.py: a field subset of the persisted nodes plus contains/method edges,
# both scoped to the files that are NOT re-extracted.

_CTX_NODE_FIELDS = ("label", "source_file", "file_type", "type")
_CTX_MARKERS = ("_callable", "_callable_class", "_php_non_class_types",
                "_php_interfaces", "_php_class_fqns")


def _watch_resolution_context(result: dict, unchanged: set[str]):
    nodes = []
    for node in result["nodes"]:
        if not node.get("id") or node.get("source_file") not in unchanged:
            continue
        ctx = {"id": node["id"]}
        ctx.update({field: node.get(field) for field in _CTX_NODE_FIELDS})
        ctx.update({m: node[m] for m in _CTX_MARKERS if node.get(m)})
        nodes.append(ctx)
    edges = [
        {
            "source": edge.get("source"),
            "target": edge.get("target"),
            "relation": edge.get("relation"),
            "source_file": edge.get("source_file"),
        }
        for edge in result["edges"]
        if edge.get("relation") in ("contains", "method")
        and edge.get("source_file") in unchanged
    ]
    return nodes, edges


def _full_then_incremental(tmp_path: Path, files: dict[str, str], changed: str):
    corpus = tmp_path / "corpus"
    paths = {}
    for name, body in files.items():
        path = corpus / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
        paths[name] = path

    def _calls_of(result):
        return {
            (edge["source"], edge["target"]): edge
            for edge in result["edges"]
            if edge.get("relation") == "calls"
        }

    full = extract(list(paths.values()), cache_root=corpus)
    paths[changed].write_text(
        files[changed].replace("class ", "// touched\nclass ", 1), encoding="utf-8"
    )
    ctx_nodes, ctx_edges = _watch_resolution_context(
        full, unchanged=set(files) - {changed}
    )
    inc = extract(
        [paths[changed]],
        cache_root=corpus,
        resolution_context_nodes=ctx_nodes,
        resolution_context_edges=ctx_edges,
    )
    return (_calls_of(full), full), (_calls_of(inc), inc)


_INCR_CALLER = "app/Http/I.php"


def test_alias_refusal_survives_incremental_rebuild(tmp_path: Path):
    """`App\\Local\\Client` is unchanged and therefore not dispatched; the claim
    lives in the caller, which is, so the refusal must fire either way."""
    (full_calls, _), (inc_calls, inc) = _full_then_incremental(tmp_path, {
        **_CORPUS,
        _INCR_CALLER: _caller("use Vendor\\Sdk\\Client;\n"),
    }, changed=_INCR_CALLER)

    go = _find(inc, ".go()", "_go")
    assert _sends(full_calls, go) == [], "full-build baseline must refuse"
    assert _sends(inc_calls, go) == [], \
        "an undispatched defining file must not resurrect the false edge"


def test_in_corpus_alias_still_resolves_incrementally(tmp_path: Path):
    """Positive control for the test above: the defining file's declared FQN
    now rides the persisted `_php_class_fqns` marker (#23), so the binding holds
    across the rebuild — decoy still empty. The pre-#23 path, where the marker
    is absent and the class is corroborated against its PSR-4 path instead, is
    pinned in `test_php_alias_binding.py`."""
    (full_calls, full), (inc_calls, inc) = _full_then_incremental(tmp_path, {
        **_CORPUS,
        _INCR_CALLER: _caller("use App\\Local\\Client;\n"),
    }, changed=_INCR_CALLER)

    go = _find(inc, ".go()", "_go")
    # The target lives in an unchanged file, so its id comes from the full run.
    send = _find(full, ".send()", "client")
    assert (go, send) in full_calls
    assert (go, send) in inc_calls, \
        "a rebuild must keep an edge whose `use` names the in-corpus class"
    assert (go, _find(full, ".send()", "recorder")) not in inc_calls


def test_non_psr4_layout_keeps_its_edge_incrementally(tmp_path: Path):
    """Composer maps a namespace PREFIX onto a directory (`App\\Weird\\` ->
    `src/`), so `App\\Weird\\Odd` legitimately lives at `src/Odd.php`. The full
    run corroborates the `use` against the namespace that file DECLARES, and
    since #23 the incremental run reads the same declaration off the persisted
    marker. `test_php_alias_binding.py` pins the pre-marker variant, where the
    shorter path must not read as a contradiction — a stripped prefix looks
    exactly like one."""
    caller = (
        "<?php\nnamespace App\\Http;\n"
        "use App\\Weird\\Odd;\n"
        "class I {\n"
        "    private Odd $o;\n"
        "    public function go(): int { return $this->o->ping(); }\n"
        "}\n"
    )
    (full_calls, full), (inc_calls, inc) = _full_then_incremental(tmp_path, {
        "src/Odd.php": (
            "<?php\nnamespace App\\Weird;\n"
            "class Odd {\n    public function ping(): int { return 1; }\n}\n"
        ),
        "app/Audit/Pinger.php": (
            "<?php\nnamespace App\\Audit;\n"
            "class Pinger {\n    public function ping(): int { return 0; }\n}\n"
        ),
        _INCR_CALLER: caller,
    }, changed=_INCR_CALLER)

    go = _find(inc, ".go()", "_go")
    odd = _find(full, ".ping()", "odd")
    assert (go, odd) in full_calls
    assert (go, odd) in inc_calls, \
        "an unchanged defining file off the PSR-4 path must keep its edge"
    assert (go, _find(full, ".ping()", "pinger")) not in inc_calls
