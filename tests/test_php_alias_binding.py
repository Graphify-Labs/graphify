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
