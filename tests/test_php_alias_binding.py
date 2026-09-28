"""PHP positive alias binding via the declared-FQN index (#22, #23).

#21's `PhpNameResolver` made a claimed name DECISIVE — a `use` import whose
target is not in the corpus refuses instead of binding a same-short-named
stranger — but it could only delete edges. This is the additive counterpart:
when the claimed FQN matches the name some in-corpus file DECLARES for a class
(#14's `php_class_fqns` payload), that match binds, selecting the imported one
of several namesakes and following a renaming alias (`use App\\A\\X as Y;`) to
a class the written short name would never census.

The index only knows classes whose declared FQNs are available. On a full run
that is every dispatched file; on an incremental rebuild the defining file is
NOT re-dispatched, so the declared map rides the persisted `_php_class_fqns`
marker on the file node (#23) — the same channel as `_php_non_class_types`.
A graph written before the marker fails closed: the #22 binding is simply
absent (never guessed), while #21's verdicts still stand on the path evidence.

Every test goes through the public `extract()` seam, and every positive case
carries same-short-named decoys in other namespaces asserted to get NO edge.
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


def _sends(calls, caller: str) -> list[str]:
    return [tgt for src, tgt in calls if src == caller]


# Two in-corpus namesakes: only the caller's `use` import can tell them apart,
# so the pre-#22 single-definition guard refused both.
_X_A = (
    "<?php\nnamespace App\\Alpha;\n"
    "class X {\n    public function send(): int { return 1; }\n}\n"
)
_X_B = (
    "<?php\nnamespace App\\Beta;\n"
    "class X {\n    public function send(): int { return 2; }\n}\n"
)
_NAMESAKES = {
    "app/Alpha/X.php": _X_A,
    "app/Beta/X.php": _X_B,
}


def _caller(uses: str = "", annotation: str = "X",
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


# ── the binding: a claimed FQN selects among namesakes ────────────────────────


def test_use_selects_the_imported_one_of_two_namesakes(tmp_path: Path):
    """Acceptance #1: `use App\\Alpha\\X;` binds the receiver to `App\\Alpha\\X`
    and ONLY it — the `App\\Beta\\X` namesake gets nothing."""
    calls, r = _calls(tmp_path, {
        **_NAMESAKES,
        "app/Http/I.php": _caller("use App\\Alpha\\X;\n"),
    })

    go = _find(r, ".go()", "_go")
    alpha = _find(r, ".send()", "alpha")
    assert (go, alpha) in calls, "the imported namesake must bind"
    assert calls[(go, alpha)]["confidence"] == "INFERRED"
    assert _sends(calls, go) == [alpha], "the other namesake must get NO edge"


def test_renaming_alias_binds_its_target(tmp_path: Path):
    """Acceptance #2: `use App\\Alpha\\X as Y;` with `private Y $c;` follows the
    alias to `App\\Alpha\\X`. An unrelated in-corpus class actually NAMED `Y`
    is exactly the stranger #21 refused — it must stay refused, not bound."""
    calls, r = _calls(tmp_path, {
        **_NAMESAKES,
        "app/Other/Y.php": (
            "<?php\nnamespace App\\Other;\n"
            "class Y {\n    public function send(): int { return 9; }\n}\n"
        ),
        "app/Http/I.php": _caller("use App\\Alpha\\X as Y;\n", annotation="Y"),
    })

    go = _find(r, ".go()", "_go")
    alpha = _find(r, ".send()", "alpha")
    assert (go, alpha) in calls, "the alias must bind to its declared target"
    assert _sends(calls, go) == [alpha], \
        "neither the namesake nor the literal `Y` class may get an edge"


def test_group_use_selects_among_namesakes(tmp_path: Path):
    """The group form (`use App\\Alpha\\{X};`) carries the same claim (#19)."""
    calls, r = _calls(tmp_path, {
        **_NAMESAKES,
        "app/Http/I.php": _caller("use App\\Alpha\\{X};\n"),
    })

    go = _find(r, ".go()", "_go")
    assert _sends(calls, go) == [_find(r, ".send()", "alpha")]


def test_written_fqn_selects_among_namesakes(tmp_path: Path):
    """A fully-qualified annotation (#20 kept the written form) claims the same
    FQN a `use` would, with no import statement at all."""
    calls, r = _calls(tmp_path, {
        **_NAMESAKES,
        "app/Http/I.php": _caller(annotation="\\App\\Alpha\\X"),
    })

    go = _find(r, ".go()", "_go")
    assert _sends(calls, go) == [_find(r, ".send()", "alpha")]


def test_namespace_relative_annotation_selects_among_namesakes(tmp_path: Path):
    """Inside namespace `App`, the written `Alpha\\X` IS `App\\Alpha\\X`."""
    calls, r = _calls(tmp_path, {
        **_NAMESAKES,
        "app/I.php": _caller(annotation="Alpha\\X", namespace="App"),
    })

    go = _find(r, ".go()", "_go")
    assert _sends(calls, go) == [_find(r, ".send()", "alpha")]


def test_binding_is_case_insensitive(tmp_path: Path):
    """PHP namespace segments and class names match case-insensitively; the
    claimed FQN and the declared one are folded on both sides."""
    calls, r = _calls(tmp_path, {
        **_NAMESAKES,
        "app/Http/I.php": _caller("use app\\alpha\\x;\n", annotation="x"),
    })

    go = _find(r, ".go()", "_go")
    assert _sends(calls, go) == [_find(r, ".send()", "alpha")]


# ── the guards: what the index must NOT change ────────────────────────────────


def test_no_use_statement_keeps_the_namesake_refusal(tmp_path: Path):
    """Acceptance #3, ambiguous half: a bare `X` receiver with no `use` claims
    nothing, and two namesakes still refuse exactly as before."""
    calls, r = _calls(tmp_path, {
        **_NAMESAKES,
        "app/Http/I.php": _caller(),
    })

    go = _find(r, ".go()", "_go")
    assert _sends(calls, go) == [], \
        "no claim, two candidates: the pre-#22 refusal must stand"


def test_no_use_statement_keeps_the_unique_short_name_binding(tmp_path: Path):
    """Acceptance #3, unique half: with one in-corpus `X` and no claim, the
    corpus-wide unique-short-name fallback binds exactly as it always did."""
    calls, r = _calls(tmp_path, {
        "app/Alpha/X.php": _X_A,
        "app/Audit/Recorder.php": (
            "<?php\nnamespace App\\Audit;\n"
            "class Recorder {\n    public function send(): int { return 0; }\n}\n"
        ),
        "app/Http/I.php": _caller(),
    })

    go = _find(r, ".go()", "_go")
    assert _sends(calls, go) == [_find(r, ".send()", "alpha")]


def test_use_of_an_out_of_corpus_namesake_still_refuses(tmp_path: Path):
    """The #21 refusal is untouched: `use Vendor\\Sdk\\X;` matches no declared
    FQN, so the index stays silent and the claim refuses both namesakes."""
    calls, r = _calls(tmp_path, {
        **_NAMESAKES,
        "app/Http/I.php": _caller("use Vendor\\Sdk\\X;\n"),
    })

    go = _find(r, ".go()", "_go")
    assert _sends(calls, go) == []


def test_duplicate_declared_fqn_refuses_rather_than_guessing(tmp_path: Path):
    """Two files declaring the very same FQN (copied fixtures, vendored
    duplicates) poison that index entry: no binding, and the short-name census
    below refuses the pair as it always has."""
    calls, r = _calls(tmp_path, {
        "app/Alpha/X.php": _X_A,
        "vendor/copy/X.php": _X_A,
        "app/Http/I.php": _caller("use App\\Alpha\\X;\n"),
    })

    go = _find(r, ".go()", "_go")
    assert _sends(calls, go) == []


# ── the same bindings across an incremental rebuild (#23) ─────────────────────
#
# The context below is assembled exactly as watch.py builds it from graph.json:
# a field subset of the persisted AST nodes — including the persisted underscore
# markers, of which `_php_class_fqns` (#23) carries the declared FQNs the #22
# binding needs — plus the corpus's contains/method edges, both scoped to the
# files NOT being re-extracted.

_CTX_NODE_FIELDS = ("label", "source_file", "file_type", "type")
_CTX_MARKERS = ("_callable", "_callable_class", "_php_non_class_types",
                "_php_interfaces", "_php_class_fqns")


def _watch_resolution_context(result: dict, unchanged: set[str],
                              markers: tuple[str, ...] = _CTX_MARKERS):
    nodes = []
    for node in result["nodes"]:
        if not node.get("id") or node.get("source_file") not in unchanged:
            continue
        ctx = {"id": node["id"]}
        ctx.update({field: node.get(field) for field in _CTX_NODE_FIELDS})
        ctx.update({m: node[m] for m in markers if node.get(m)})
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


def _full_then_incremental(tmp_path: Path, files: dict[str, str], changed: str,
                           markers: tuple[str, ...] = _CTX_MARKERS):
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
        full, unchanged=set(files) - {changed}, markers=markers
    )
    inc = extract(
        [paths[changed]],
        cache_root=corpus,
        resolution_context_nodes=ctx_nodes,
        resolution_context_edges=ctx_edges,
    )
    return (_calls_of(full), full), (_calls_of(inc), inc)


_INCR_CALLER = "app/Http/I.php"


def test_namesake_selection_survives_incremental_rebuild(tmp_path: Path):
    """Acceptance (#23): the defining files are unchanged and NOT dispatched,
    so the declared FQNs reach the resolver only through the persisted marker —
    the full and incremental runs must agree edge for edge."""
    (full_calls, full), (inc_calls, inc) = _full_then_incremental(tmp_path, {
        **_NAMESAKES,
        _INCR_CALLER: _caller("use App\\Alpha\\X;\n"),
    }, changed=_INCR_CALLER)

    go = _find(inc, ".go()", "_go")
    # The targets live in unchanged files, so their ids come from the full run.
    alpha = _find(full, ".send()", "alpha")
    assert _sends(full_calls, go) == [alpha], "full-build baseline"
    assert _sends(inc_calls, go) == [alpha], \
        "an undispatched defining file must not lose the #22 binding"


def test_renaming_alias_survives_incremental_rebuild(tmp_path: Path):
    (full_calls, full), (inc_calls, inc) = _full_then_incremental(tmp_path, {
        **_NAMESAKES,
        _INCR_CALLER: _caller("use App\\Alpha\\X as Y;\n", annotation="Y"),
    }, changed=_INCR_CALLER)

    go = _find(inc, ".go()", "_go")
    alpha = _find(full, ".send()", "alpha")
    assert _sends(full_calls, go) == [alpha]
    assert _sends(inc_calls, go) == [alpha]


def test_written_fqn_selection_survives_incremental_rebuild(tmp_path: Path):
    (full_calls, full), (inc_calls, inc) = _full_then_incremental(tmp_path, {
        **_NAMESAKES,
        _INCR_CALLER: _caller(annotation="\\App\\Alpha\\X"),
    }, changed=_INCR_CALLER)

    go = _find(inc, ".go()", "_go")
    alpha = _find(full, ".send()", "alpha")
    assert _sends(full_calls, go) == [alpha]
    assert _sends(inc_calls, go) == [alpha]


# ── pre-marker graphs: a graph.json written before #23 ────────────────────────

_PRE_23_MARKERS = tuple(m for m in _CTX_MARKERS if m != "_php_class_fqns")


def test_pre_marker_graph_fails_closed(tmp_path: Path):
    """Acceptance (#23): a graph persisted before the marker existed carries no
    declared FQNs, so the rebuild cannot tell the namesakes apart — it must add
    NO edge (fail closed, matching the `_callable` precedent) and not crash,
    until the defining files are re-extracted."""
    (full_calls, full), (inc_calls, inc) = _full_then_incremental(tmp_path, {
        **_NAMESAKES,
        _INCR_CALLER: _caller("use App\\Alpha\\X;\n"),
    }, changed=_INCR_CALLER, markers=_PRE_23_MARKERS)

    go = _find(inc, ".go()", "_go")
    assert _sends(full_calls, go) == [_find(full, ".send()", "alpha")], \
        "full-build baseline still binds"
    assert _sends(inc_calls, go) == [], \
        "a pre-#23 graph must lose the binding, never misdirect it"


def test_pre_marker_graph_keeps_the_21_refusal(tmp_path: Path):
    """Fail-closed must not curdle into fail-open elsewhere: with no marker,
    an out-of-corpus claim still refuses on the path evidence (#21)."""
    (_, full), (inc_calls, inc) = _full_then_incremental(tmp_path, {
        "app/Alpha/X.php": _X_A,
        _INCR_CALLER: _caller("use Vendor\\Sdk\\X;\n"),
    }, changed=_INCR_CALLER, markers=_PRE_23_MARKERS)

    go = _find(inc, ".go()", "_go")
    assert _sends(inc_calls, go) == []


def test_pre_marker_graph_keeps_the_unique_name_binding(tmp_path: Path):
    """And the pre-#22 recall is untouched: a `use` naming the lone in-corpus
    class still binds through the PSR-4 path corroboration, exactly as the
    incremental path behaved before the marker existed (pinned here after
    `test_php_name_resolver.py`'s incremental tests moved onto the marker)."""
    (_, full), (inc_calls, inc) = _full_then_incremental(tmp_path, {
        "app/Alpha/X.php": _X_A,
        "app/Audit/Recorder.php": (
            "<?php\nnamespace App\\Audit;\n"
            "class Recorder {\n    public function send(): int { return 0; }\n}\n"
        ),
        _INCR_CALLER: _caller("use App\\Alpha\\X;\n"),
    }, changed=_INCR_CALLER, markers=_PRE_23_MARKERS)

    go = _find(inc, ".go()", "_go")
    alpha = _find(full, ".send()", "alpha")
    assert (go, alpha) in inc_calls, \
        "a pre-marker graph keeps the #21-era binding for a unique short name"
    assert (go, _find(full, ".send()", "recorder")) not in inc_calls


def test_non_psr4_layout_pre_marker_keeps_its_edge(tmp_path: Path):
    """The pre-marker variant of `test_non_psr4_layout_keeps_its_edge_incrementally`:
    composer maps a namespace PREFIX onto a directory (`App\\Weird\\` -> `src/`),
    and with the declaration unavailable the shorter path must not read as a
    contradiction — a stripped prefix looks exactly like one."""
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
    }, changed=_INCR_CALLER, markers=_PRE_23_MARKERS)

    go = _find(inc, ".go()", "_go")
    odd = _find(full, ".ping()", "odd")
    assert (go, odd) in full_calls
    assert (go, odd) in inc_calls
    assert (go, _find(full, ".ping()", "pinger")) not in inc_calls
