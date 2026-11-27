"""C/C++: call edges follow fall-through / goto / case reachability.

Unreachable CubeMX tails after a USER CODE `return;` must not become calls
edges. Labels reachable via goto (and switch cases) must still be extracted.
Static infinite loops without an exit share the terminal rule with return.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from graphify.extract import extract
from graphify.extractors.engine import (
    get_c_cpp_unreachable_warnings,
    set_c_cpp_unreachable_warnings,
)


def _real(tmp_path: Path) -> Path:
    return Path(os.path.realpath(tmp_path))


def _call_targets(result: dict, caller_label: str) -> set[str]:
    by_id = {n["id"]: n for n in result["nodes"]}
    callers = [n for n in result["nodes"] if n.get("label") == caller_label]
    assert len(callers) == 1, callers
    caller_id = callers[0]["id"]
    out: set[str] = set()
    for e in result["edges"]:
        if e.get("relation") != "calls":
            continue
        if e.get("source") != caller_id and e.get("_src") != caller_id:
            continue
        tgt = e.get("target") or e.get("_tgt")
        lab = by_id.get(tgt, {}).get("label", tgt)
        out.add(lab)
    return out


@pytest.fixture(autouse=True)
def _restore_unreachable_warning_flag():
    """Restore the module flag after each test; do not force it on.

    Forcing True here would hide regressions of the documented default
    (``_C_CPP_WARN_UNREACHABLE = True``).
    """
    prev = get_c_cpp_unreachable_warnings()
    yield
    set_c_cpp_unreachable_warnings(prev)


@pytest.mark.parametrize("suffix,lang", [(".c", "C"), (".cpp", "C++")])
def test_unconditional_return_skips_later_calls(tmp_path: Path, suffix: str, lang: str) -> None:
    root = _real(tmp_path)
    main = root / f"main{suffix}"
    eth = root / f"eth{suffix}"
    main.write_text(
        "void Error_Handler(void) { for (;;) {} }\n"
        "void keep_alive(void) {}\n"
        "void eth_phy_config(void) {}\n",
        encoding="utf-8",
    )
    eth.write_text(
        "void Error_Handler(void);\n"
        "void keep_alive(void);\n"
        "void eth_phy_config(void);\n"
        "void low_level_init(void) {\n"
        "  eth_phy_config();\n"
        "  return;\n"
        "  keep_alive();\n"
        "  Error_Handler();\n"
        "}\n",
        encoding="utf-8",
    )
    result = extract([main, eth], root=root, cache_root=root)
    assert not result.get("error"), result.get("error")
    targets = _call_targets(result, "low_level_init()")
    assert "eth_phy_config()" in targets, (lang, targets)
    assert "Error_Handler()" not in targets, (lang, targets)
    assert "keep_alive()" not in targets, (lang, targets)


@pytest.mark.parametrize("suffix", [".c", ".cpp"])
def test_return_inside_if_does_not_skip_following_sibling(tmp_path: Path, suffix: str) -> None:
    root = _real(tmp_path)
    main = root / f"main{suffix}"
    body = root / f"body{suffix}"
    main.write_text(
        "void Error_Handler(void) {}\n"
        "void after_if(void) {}\n",
        encoding="utf-8",
    )
    body.write_text(
        "void Error_Handler(void);\n"
        "void after_if(void);\n"
        "int flag;\n"
        "void f(void) {\n"
        "  if (flag) {\n"
        "    Error_Handler();\n"
        "    return;\n"
        "  }\n"
        "  after_if();\n"
        "}\n",
        encoding="utf-8",
    )
    result = extract([main, body], root=root, cache_root=root)
    targets = _call_targets(result, "f()")
    assert "Error_Handler()" in targets
    assert "after_if()" in targets


@pytest.mark.parametrize("suffix", [".c", ".cpp"])
def test_return_inside_preproc_if_skips_later_siblings(tmp_path: Path, suffix: str) -> None:
    """CubeMX: USER CODE return and dead Error_Handler share a #if body."""
    root = _real(tmp_path)
    main = root / f"main{suffix}"
    eth = root / f"eth{suffix}"
    main.write_text(
        "void Error_Handler(void) {}\n"
        "void eth_phy_config(void) {}\n",
        encoding="utf-8",
    )
    eth.write_text(
        "void Error_Handler(void);\n"
        "void eth_phy_config(void);\n"
        "#define FEATURE 1\n"
        "void low_level_init(void) {\n"
        "#if FEATURE\n"
        "  eth_phy_config();\n"
        "  return;\n"
        "  Error_Handler();\n"
        "#endif\n"
        "}\n",
        encoding="utf-8",
    )
    result = extract([main, eth], root=root, cache_root=root)
    targets = _call_targets(result, "low_level_init()")
    assert "eth_phy_config()" in targets
    assert "Error_Handler()" not in targets


@pytest.mark.parametrize("suffix", [".c", ".cpp"])
def test_call_inside_return_expression_is_kept(tmp_path: Path, suffix: str) -> None:
    root = _real(tmp_path)
    main = root / f"main{suffix}"
    body = root / f"body{suffix}"
    main.write_text(
        "int compute(void) { return 1; }\n"
        "void dead(void) {}\n",
        encoding="utf-8",
    )
    body.write_text(
        "int compute(void);\n"
        "void dead(void);\n"
        "int f(void) {\n"
        "  return compute();\n"
        "  dead();\n"
        "}\n",
        encoding="utf-8",
    )
    result = extract([main, body], root=root, cache_root=root)
    targets = _call_targets(result, "f()")
    assert "compute()" in targets
    assert "dead()" not in targets


@pytest.mark.parametrize("suffix", [".c", ".cpp"])
def test_goto_cleanup_after_return_keeps_label_calls(tmp_path: Path, suffix: str) -> None:
    """Copilot #5338: return stops fall-through; goto cleanup still reaches release/finish."""
    root = _real(tmp_path)
    main = root / f"main{suffix}"
    body = root / f"body{suffix}"
    main.write_text(
        "void release(void) {}\n"
        "void finish(void) {}\n"
        "void early(void) {}\n",
        encoding="utf-8",
    )
    body.write_text(
        "void release(void);\n"
        "void finish(void);\n"
        "void early(void);\n"
        "void f(int fail) {\n"
        "  if (fail) goto cleanup;\n"
        "  early();\n"
        "  return;\n"
        "cleanup:\n"
        "  release();\n"
        "  finish();\n"
        "}\n",
        encoding="utf-8",
    )
    result = extract([main, body], root=root, cache_root=root)
    targets = _call_targets(result, "f()")
    assert "early()" in targets
    assert "release()" in targets
    assert "finish()" in targets


@pytest.mark.parametrize("suffix", [".c", ".cpp"])
def test_goto_after_return_inside_if_does_not_revive_label(tmp_path: Path, suffix: str) -> None:
    """#5338 P2: unreachable goto nested after return must not activate cleanup."""
    root = _real(tmp_path)
    main = root / f"main{suffix}"
    body = root / f"body{suffix}"
    main.write_text(
        "void release(void) {}\n"
        "void alive(void) {}\n",
        encoding="utf-8",
    )
    body.write_text(
        "void release(void);\n"
        "void alive(void);\n"
        "void f(int fail) {\n"
        "  if (fail) {\n"
        "    return;\n"
        "    goto cleanup;\n"
        "  }\n"
        "  alive();\n"
        "  return;\n"
        "cleanup:\n"
        "  release();\n"
        "}\n",
        encoding="utf-8",
    )
    result = extract([main, body], root=root, cache_root=root)
    targets = _call_targets(result, "f()")
    assert "alive()" in targets
    assert "release()" not in targets


@pytest.mark.parametrize("suffix", [".c", ".cpp"])
def test_sibling_goto_after_return_does_not_revive_label(tmp_path: Path, suffix: str) -> None:
    root = _real(tmp_path)
    main = root / f"main{suffix}"
    body = root / f"body{suffix}"
    main.write_text("void release(void) {}\n", encoding="utf-8")
    body.write_text(
        "void release(void);\n"
        "void f(void) {\n"
        "  return;\n"
        "  goto cleanup;\n"
        "cleanup:\n"
        "  release();\n"
        "}\n",
        encoding="utf-8",
    )
    result = extract([main, body], root=root, cache_root=root)
    assert "release()" not in _call_targets(result, "f()")


@pytest.mark.parametrize("suffix", [".c", ".cpp"])
def test_label_without_goto_after_return_stays_dead(tmp_path: Path, suffix: str) -> None:
    root = _real(tmp_path)
    main = root / f"main{suffix}"
    body = root / f"body{suffix}"
    main.write_text(
        "void alive(void) {}\n"
        "void dead(void) {}\n",
        encoding="utf-8",
    )
    body.write_text(
        "void alive(void);\n"
        "void dead(void);\n"
        "void f(void) {\n"
        "  alive();\n"
        "  return;\n"
        "orphan:\n"
        "  dead();\n"
        "}\n",
        encoding="utf-8",
    )
    result = extract([main, body], root=root, cache_root=root)
    targets = _call_targets(result, "f()")
    assert "alive()" in targets
    assert "dead()" not in targets


@pytest.mark.parametrize("suffix", [".c", ".cpp"])
def test_switch_case_after_return_in_prior_case_is_kept(tmp_path: Path, suffix: str) -> None:
    root = _real(tmp_path)
    main = root / f"main{suffix}"
    body = root / f"body{suffix}"
    main.write_text(
        "void a(void) {}\n"
        "void b(void) {}\n"
        "void after(void) {}\n"
        "void dead(void) {}\n",
        encoding="utf-8",
    )
    body.write_text(
        "void a(void);\n"
        "void b(void);\n"
        "void after(void);\n"
        "void dead(void);\n"
        "void f(int x) {\n"
        "  switch (x) {\n"
        "  case 1:\n"
        "    a();\n"
        "    return;\n"
        "    dead();\n"
        "  case 2:\n"
        "    b();\n"
        "    break;\n"
        "  }\n"
        "  after();\n"
        "}\n",
        encoding="utf-8",
    )
    result = extract([main, body], root=root, cache_root=root)
    targets = _call_targets(result, "f()")
    assert "a()" in targets
    assert "b()" in targets
    assert "after()" in targets
    assert "dead()" not in targets


@pytest.mark.parametrize("suffix", [".c", ".cpp"])
def test_static_infinite_while_skips_following_calls(tmp_path: Path, suffix: str) -> None:
    root = _real(tmp_path)
    main = root / f"main{suffix}"
    body = root / f"body{suffix}"
    main.write_text(
        "void tick(void) {}\n"
        "void dead(void) {}\n",
        encoding="utf-8",
    )
    body.write_text(
        "void tick(void);\n"
        "void dead(void);\n"
        "void f(void) {\n"
        "  while (1) {\n"
        "    tick();\n"
        "  }\n"
        "  dead();\n"
        "}\n",
        encoding="utf-8",
    )
    result = extract([main, body], root=root, cache_root=root)
    targets = _call_targets(result, "f()")
    assert "tick()" in targets
    assert "dead()" not in targets


@pytest.mark.parametrize("suffix", [".c", ".cpp"])
@pytest.mark.parametrize("cond", ["2", "0x2", "0xff", "2u", "2ul", "-1"])
def test_nonzero_constant_while_skips_following_calls(
    tmp_path: Path, suffix: str, cond: str
) -> None:
    """Nonzero integer conditions are static-infinite like while(1) (#5338 P2)."""
    root = _real(tmp_path)
    main = root / f"main{suffix}"
    body = root / f"body{suffix}"
    main.write_text(
        "void tick(void) {}\n"
        "void dead(void) {}\n",
        encoding="utf-8",
    )
    body.write_text(
        "void tick(void);\n"
        "void dead(void);\n"
        "void f(void) {\n"
        f"  while ({cond}) {{\n"
        "    tick();\n"
        "  }\n"
        "  dead();\n"
        "}\n",
        encoding="utf-8",
    )
    result = extract([main, body], root=root, cache_root=root)
    targets = _call_targets(result, "f()")
    assert "tick()" in targets, (cond, targets)
    assert "dead()" not in targets, (cond, targets)


@pytest.mark.parametrize("suffix", [".c", ".cpp"])
@pytest.mark.parametrize("cond", ["0", "0x0", "0u", "-0"])
def test_zero_constant_while_keeps_following_calls(
    tmp_path: Path, suffix: str, cond: str
) -> None:
    """while(0) can finish; fall-through after the loop stays reachable."""
    root = _real(tmp_path)
    main = root / f"main{suffix}"
    body = root / f"body{suffix}"
    main.write_text(
        "void tick(void) {}\n"
        "void after(void) {}\n",
        encoding="utf-8",
    )
    body.write_text(
        "void tick(void);\n"
        "void after(void);\n"
        "void f(void) {\n"
        f"  while ({cond}) {{\n"
        "    tick();\n"
        "  }\n"
        "  after();\n"
        "}\n",
        encoding="utf-8",
    )
    result = extract([main, body], root=root, cache_root=root)
    targets = _call_targets(result, "f()")
    assert "after()" in targets, (cond, targets)


def test_c_while_true_variable_keeps_following_calls(tmp_path: Path) -> None:
    """C ``true`` may be an ordinary variable; do not treat as infinite (#5338 P2)."""
    root = _real(tmp_path)
    main = root / "main.c"
    body = root / "body.c"
    main.write_text(
        "void tick(void) {}\n"
        "void after(void) {}\n",
        encoding="utf-8",
    )
    body.write_text(
        "void tick(void);\n"
        "void after(void);\n"
        "void f(void) {\n"
        "  int true = 0;\n"
        "  while (true) {\n"
        "    tick();\n"
        "  }\n"
        "  after();\n"
        "}\n",
        encoding="utf-8",
    )
    result = extract([main, body], root=root, cache_root=root)
    targets = _call_targets(result, "f()")
    assert "tick()" in targets
    assert "after()" in targets


def test_c_while_true_spelling_keeps_following_calls(tmp_path: Path) -> None:
    """C ``while (true)`` is not trusted without preprocess (e.g. stdbool.h)."""
    root = _real(tmp_path)
    main = root / "main.c"
    body = root / "body.c"
    main.write_text(
        "void tick(void) {}\n"
        "void after(void) {}\n",
        encoding="utf-8",
    )
    body.write_text(
        "void tick(void);\n"
        "void after(void);\n"
        "void f(void) {\n"
        "  while (true) {\n"
        "    tick();\n"
        "  }\n"
        "  after();\n"
        "}\n",
        encoding="utf-8",
    )
    result = extract([main, body], root=root, cache_root=root)
    targets = _call_targets(result, "f()")
    assert "tick()" in targets
    assert "after()" in targets


def test_cpp_while_true_skips_following_calls(tmp_path: Path) -> None:
    """C++ ``true`` is a keyword — static infinite loop still cuts fall-through."""
    root = _real(tmp_path)
    main = root / "main.cpp"
    body = root / "body.cpp"
    main.write_text(
        "void tick(void) {}\n"
        "void dead(void) {}\n",
        encoding="utf-8",
    )
    body.write_text(
        "void tick(void);\n"
        "void dead(void);\n"
        "void f(void) {\n"
        "  while (true) {\n"
        "    tick();\n"
        "  }\n"
        "  dead();\n"
        "}\n",
        encoding="utf-8",
    )
    result = extract([main, body], root=root, cache_root=root)
    targets = _call_targets(result, "f()")
    assert "tick()" in targets
    assert "dead()" not in targets


@pytest.mark.parametrize("suffix", [".c", ".cpp"])
def test_static_infinite_for_skips_following_calls(tmp_path: Path, suffix: str) -> None:
    root = _real(tmp_path)
    main = root / f"main{suffix}"
    body = root / f"body{suffix}"
    main.write_text(
        "void tick(void) {}\n"
        "void dead(void) {}\n",
        encoding="utf-8",
    )
    body.write_text(
        "void tick(void);\n"
        "void dead(void);\n"
        "void f(void) {\n"
        "  for (;;) {\n"
        "    tick();\n"
        "  }\n"
        "  dead();\n"
        "}\n",
        encoding="utf-8",
    )
    result = extract([main, body], root=root, cache_root=root)
    targets = _call_targets(result, "f()")
    assert "tick()" in targets
    assert "dead()" not in targets


@pytest.mark.parametrize("suffix", [".c", ".cpp"])
def test_infinite_while_with_break_keeps_following_calls(tmp_path: Path, suffix: str) -> None:
    root = _real(tmp_path)
    main = root / f"main{suffix}"
    body = root / f"body{suffix}"
    main.write_text(
        "void tick(void) {}\n"
        "void after(void) {}\n",
        encoding="utf-8",
    )
    body.write_text(
        "void tick(void);\n"
        "void after(void);\n"
        "int flag;\n"
        "void f(void) {\n"
        "  while (1) {\n"
        "    tick();\n"
        "    if (flag) break;\n"
        "  }\n"
        "  after();\n"
        "}\n",
        encoding="utf-8",
    )
    result = extract([main, body], root=root, cache_root=root)
    targets = _call_targets(result, "f()")
    assert "tick()" in targets
    assert "after()" in targets


# Loop-body layouts → whether after-loop calls stay extracted.
# keep_after=True means a reachable break (or equivalent) reopens fall-through.
_INFINITE_BREAK_LAYOUTS: dict[str, tuple[str, bool]] = {
    "break_after_return": (
        "while (1) {\n    tick();\n    return;\n    break;\n  }",
        False,
    ),
    "break_after_return_for": (
        "for (;;) {\n    tick();\n    return;\n    break;\n  }",
        False,
    ),
    "plain_break_after_tick": (
        "while (1) {\n    tick();\n    break;\n  }",
        True,
    ),
    "conditional_break": (
        "while (1) {\n    tick();\n    if (flag) break;\n  }",
        True,
    ),
    "break_in_else_after_return_then": (
        "while (1) {\n    if (flag) {\n      return;\n    } else {\n      break;\n    }\n  }",
        True,
    ),
    "break_only_after_return_in_then": (
        "while (1) {\n    if (flag) {\n      return;\n      break;\n    }\n    tick();\n  }",
        False,
    ),
    "nested_while_break_does_not_leave_outer": (
        "while (1) {\n    tick();\n    while (1) {\n      break;\n    }\n  }",
        False,
    ),
    "return_only": (
        "while (1) {\n    tick();\n    return;\n  }",
        False,
    ),
}


@pytest.mark.parametrize("suffix", [".c", ".cpp"])
@pytest.mark.parametrize("layout", list(_INFINITE_BREAK_LAYOUTS))
def test_infinite_loop_break_reachability_layouts(
    tmp_path: Path, suffix: str, layout: str
) -> None:
    """Permanence uses body reachability: only reachable breaks reopen after-loop calls."""
    loop_src, keep_after = _INFINITE_BREAK_LAYOUTS[layout]
    root = _real(tmp_path)
    main = root / f"main{suffix}"
    body = root / f"body{suffix}"
    main.write_text(
        "void tick(void) {}\n"
        "void after(void) {}\n",
        encoding="utf-8",
    )
    body.write_text(
        "void tick(void);\n"
        "void after(void);\n"
        "int flag;\n"
        "void f(void) {\n"
        f"  {loop_src}\n"
        "  after();\n"
        "}\n",
        encoding="utf-8",
    )
    result = extract([main, body], root=root, cache_root=root)
    targets = _call_targets(result, "f()")
    if "tick()" in loop_src:
        assert "tick()" in targets, (layout, targets)
    if keep_after:
        assert "after()" in targets, (layout, targets)
    else:
        assert "after()" not in targets, (layout, targets)


@pytest.mark.parametrize("suffix", [".c", ".cpp"])
def test_infinite_while_with_return_skips_following_calls(tmp_path: Path, suffix: str) -> None:
    """return leaves the function; after() is not fall-through-reachable."""
    root = _real(tmp_path)
    main = root / f"main{suffix}"
    body = root / f"body{suffix}"
    main.write_text(
        "void tick(void) {}\n"
        "void after(void) {}\n",
        encoding="utf-8",
    )
    body.write_text(
        "void tick(void);\n"
        "void after(void);\n"
        "int flag;\n"
        "void f(void) {\n"
        "  while (1) {\n"
        "    tick();\n"
        "    if (flag) return;\n"
        "  }\n"
        "  after();\n"
        "}\n",
        encoding="utf-8",
    )
    result = extract([main, body], root=root, cache_root=root)
    targets = _call_targets(result, "f()")
    assert "tick()" in targets
    assert "after()" not in targets


@pytest.mark.parametrize("suffix", [".c", ".cpp"])
def test_infinite_while_goto_cleanup_skips_after_keeps_release(tmp_path: Path, suffix: str) -> None:
    """goto opens the label set; after() between loop and label stays dead."""
    root = _real(tmp_path)
    main = root / f"main{suffix}"
    body = root / f"body{suffix}"
    main.write_text(
        "void tick(void) {}\n"
        "void after(void) {}\n"
        "void release(void) {}\n",
        encoding="utf-8",
    )
    body.write_text(
        "void tick(void);\n"
        "void after(void);\n"
        "void release(void);\n"
        "int fail;\n"
        "void f(void) {\n"
        "  while (1) {\n"
        "    tick();\n"
        "    if (fail) goto cleanup;\n"
        "  }\n"
        "  after();\n"
        "cleanup:\n"
        "  release();\n"
        "}\n",
        encoding="utf-8",
    )
    result = extract([main, body], root=root, cache_root=root)
    targets = _call_targets(result, "f()")
    assert "tick()" in targets
    assert "release()" in targets
    assert "after()" not in targets


@pytest.mark.parametrize("suffix", [".c", ".cpp"])
def test_nested_goto_label_inside_if_after_return(tmp_path: Path, suffix: str) -> None:
    root = _real(tmp_path)
    main = root / f"main{suffix}"
    body = root / f"body{suffix}"
    main.write_text(
        "void release(void) {}\n"
        "void finish(void) {}\n"
        "void before_label(void) {}\n",
        encoding="utf-8",
    )
    body.write_text(
        "void release(void);\n"
        "void finish(void);\n"
        "void before_label(void);\n"
        "void f(int fail) {\n"
        "  if (fail) goto cleanup;\n"
        "  return;\n"
        "  if (0) {\n"
        "    before_label();\n"
        "  cleanup:\n"
        "    release();\n"
        "    finish();\n"
        "  }\n"
        "}\n",
        encoding="utf-8",
    )
    result = extract([main, body], root=root, cache_root=root)
    targets = _call_targets(result, "f()")
    assert "release()" in targets
    assert "finish()" in targets
    assert "before_label()" not in targets


@pytest.mark.parametrize("suffix", [".c", ".cpp"])
def test_unreachable_warning_default_on_and_toggle(tmp_path: Path, suffix: str, capsys: pytest.CaptureFixture[str]) -> None:
    root = _real(tmp_path)
    main = root / f"main{suffix}"
    body = root / f"body{suffix}"
    main.write_text("void dead(void) {}\n", encoding="utf-8")
    body.write_text(
        "void dead(void);\n"
        "void f(void) {\n"
        "  return;\n"
        "  dead();\n"
        "}\n",
        encoding="utf-8",
    )

    # Documented default is ON — do not call set(...True) before this extract.
    assert get_c_cpp_unreachable_warnings() is True
    extract([main, body], root=root, cache_root=root)
    err_on = capsys.readouterr().err
    assert "fall-through-unreachable" in err_on
    # Disclaimer phrase only (not a loose 'asm' substring).
    assert "assembler jumps" in err_on

    set_c_cpp_unreachable_warnings(False)
    assert get_c_cpp_unreachable_warnings() is False
    # Fresh cache_root leaf so extract runs again
    root2 = root / "off"
    root2.mkdir()
    main2 = root2 / f"main{suffix}"
    body2 = root2 / f"body{suffix}"
    main2.write_text(main.read_text(encoding="utf-8"), encoding="utf-8")
    body2.write_text(body.read_text(encoding="utf-8"), encoding="utf-8")
    extract([main2, body2], root=root2, cache_root=root2)
    err_off = capsys.readouterr().err
    assert "fall-through-unreachable" not in err_off


_ALT_BRANCHES = {
    "else": (
        "#if FEATURE\n  a();\n  return;\n  dead();\n"
        "#else\n  b();\n#endif\n",
        {"a()", "b()"},
    ),
    "elif-chain": (
        "#if FEATURE\n  a();\n  return;\n  dead();\n"
        "#elif OTHER\n  c();\n  return;\n  dead2();\n"
        "#else\n  b();\n#endif\n",
        {"a()", "b()", "c()"},
    ),
    "ifdef-else": (
        "#ifdef FEATURE\n  a();\n  return;\n  dead();\n"
        "#else\n  b();\n#endif\n",
        {"a()", "b()"},
    ),
}


@pytest.mark.parametrize("suffix", [".c", ".cpp"])
@pytest.mark.parametrize("case", list(_ALT_BRANCHES))
def test_return_in_preproc_branch_keeps_alternate_branches(
    tmp_path: Path, suffix: str, case: str
) -> None:
    """#5357: #elif / #else are other build configs, not code after the return."""
    body, live = _ALT_BRANCHES[case]
    root = _real(tmp_path)
    src = root / f"f{suffix}"
    src.write_text(
        "".join(f"void {n}(void) {{}}\n" for n in ("a", "b", "c", "dead", "dead2", "after"))
        + "void f(void) {\n" + body + "  after();\n}\n",
        encoding="utf-8",
    )
    result = extract([src], root=root, cache_root=root)
    targets = _call_targets(result, "f()")
    assert live | {"after()"} <= targets
    assert not {"dead()", "dead2()"} & targets


# ---------------------------------------------------------------------------
# Function-level label activation: a reachable goto opens its label wherever it
# sits, and reachability flows on from there (break out, loop back edge, code
# after the loop). Unreachable gotos never open anything.
# ---------------------------------------------------------------------------

_CALLEES = (
    "a", "b", "head", "body", "more", "after", "release", "dead", "one", "two",
    "check", "inside", "q", "r", "tick",
)


def _targets_for(tmp_path: Path, suffix: str, fn_src: str) -> set[str]:
    root = _real(tmp_path)
    src = root / f"f{suffix}"
    src.write_text(
        "".join(f"void {n}(void) {{}}\n" for n in _CALLEES) + fn_src,
        encoding="utf-8",
    )
    result = extract([src], root=root, cache_root=root)
    return _call_targets(result, "f()")


_LABEL_FLOW_CASES: dict[str, tuple[str, set[str], set[str]]] = {
    # #5338 P2: the goto lands on a label nested in an if inside while (1); the
    # break there leaves the loop, so after() is reachable.
    "goto_reached_nested_break_leaves_loop": (
        "  while (1) {\n"
        "    tick();\n"
        "    if (x) goto L;\n"
        "    return;\n"
        "    if (y) { L: more(); break; }\n"
        "  }\n"
        "  after();\n",
        {"tick()", "more()", "after()"},
        set(),
    ),
    # Jumping into a loop the fall-through never reaches: the back edge makes
    # the body before the label reachable, and a non-constant loop exits.
    "goto_into_dead_loop_back_edge_and_exit": (
        "  if (x) goto inside;\n"
        "  return;\n"
        "  while (y) {\n"
        "    head();\n"
        "  inside:\n"
        "    body();\n"
        "  }\n"
        "  after();\n",
        {"head()", "body()", "after()"},
        set(),
    ),
    "goto_into_dead_infinite_loop_with_break": (
        "  if (x) goto inside;\n"
        "  return;\n"
        "  while (1) {\n"
        "    head();\n"
        "  inside:\n"
        "    body();\n"
        "    if (y) break;\n"
        "  }\n"
        "  after();\n",
        {"head()", "body()", "after()"},
        set(),
    ),
    "goto_into_dead_infinite_loop_without_break": (
        "  if (x) goto inside;\n"
        "  return;\n"
        "  while (1) {\n"
        "    head();\n"
        "  inside:\n"
        "    body();\n"
        "  }\n"
        "  after();\n",
        {"head()", "body()"},
        {"after()"},
    ),
    # The goto that opens `first` is only found after `first` is passed, so a
    # second pass is needed.
    "backward_goto_needs_second_pass": (
        "  if (x) goto second;\n"
        "  return;\n"
        "first:\n"
        "  one();\n"
        "  return;\n"
        "second:\n"
        "  two();\n"
        "  goto first;\n",
        {"one()", "two()"},
        set(),
    ),
    # Only the label is entered: the dead if's own condition is not evaluated.
    "dead_if_condition_skipped_label_inside_kept": (
        "  if (x) goto L;\n"
        "  return;\n"
        "  if (y) { check(); L: inside(); }\n",
        {"inside()"},
        {"check()"},
    ),
    "goto_in_dead_code_opens_nothing": (
        "  a();\n"
        "  return;\n"
        "  goto L;\n"
        "  dead();\n"
        "L:\n"
        "  release();\n",
        {"a()"},
        {"dead()", "release()"},
    ),
    "do_while_one_without_break_cuts_after": (
        "  do {\n"
        "    tick();\n"
        "  } while (1);\n"
        "  after();\n",
        {"tick()"},
        {"after()"},
    ),
    "do_while_one_with_break_keeps_after": (
        "  do {\n"
        "    tick();\n"
        "    if (x) break;\n"
        "  } while (1);\n"
        "  after();\n",
        {"tick()", "after()"},
        set(),
    ),
    "do_while_zero_keeps_after": (
        "  do {\n"
        "    tick();\n"
        "  } while (0);\n"
        "  after();\n",
        {"tick()", "after()"},
        set(),
    ),
    # A case wrapped in #if is still a switch entry, even after a returning case.
    "case_inside_preproc_if_in_switch": (
        "  switch (x) {\n"
        "  case 0:\n"
        "    return;\n"
        "    dead();\n"
        "#if FEATURE\n"
        "  case 1:\n"
        "    q();\n"
        "    break;\n"
        "#endif\n"
        "  default:\n"
        "    r();\n"
        "  }\n"
        "  after();\n",
        {"q()", "r()", "after()"},
        {"dead()"},
    ),
    "continue_in_infinite_loop_does_not_exit": (
        "  for (;;) {\n"
        "    tick();\n"
        "    if (x) continue;\n"
        "    body();\n"
        "  }\n"
        "  after();\n",
        {"tick()", "body()"},
        {"after()"},
    ),
}


@pytest.mark.parametrize("suffix", [".c", ".cpp"])
@pytest.mark.parametrize("case", list(_LABEL_FLOW_CASES))
def test_label_activation_flows_through_loops(
    tmp_path: Path, suffix: str, case: str
) -> None:
    body, live, dead = _LABEL_FLOW_CASES[case]
    targets = _targets_for(
        tmp_path, suffix, "int x, y;\nvoid f(void) {\n" + body + "}\n"
    )
    assert live <= targets, (case, targets)
    assert not dead & targets, (case, targets)


_COMPUTED_GOTO_CASES: dict[str, tuple[str, set[str], set[str]]] = {
    # #5338 review: `goto *p;` may land on the address-taken label after return.
    "pointer": (
        "  void *p = &&cleanup;\n"
        "  a();\n"
        "  if (x) goto *p;\n"
        "  return;\n"
        "cleanup:\n"
        "  release();\n",
        {"a()", "release()"},
        set(),
    ),
    # `goto *table[i];` parses as an ERROR node; it still opens the labels.
    "table": (
        "  static void *table[] = { &&one_l, &&two_l };\n"
        "  if (x) goto *table[y];\n"
        "  return;\n"
        "one_l:\n"
        "  one();\n"
        "  return;\n"
        "two_l:\n"
        "  two();\n",
        {"one()", "two()"},
        set(),
    ),
    # Only labels whose address is taken can be computed-goto targets.
    "label_without_address_stays_dead": (
        "  void *p = &&cleanup;\n"
        "  if (x) goto *p;\n"
        "  return;\n"
        "other:\n"
        "  dead();\n"
        "cleanup:\n"
        "  release();\n",
        {"release()"},
        {"dead()"},
    ),
}


@pytest.mark.parametrize("suffix", [".c", ".cpp"])
@pytest.mark.parametrize("case", list(_COMPUTED_GOTO_CASES))
def test_computed_goto_opens_address_taken_labels(
    tmp_path: Path, suffix: str, case: str
) -> None:
    body, live, dead = _COMPUTED_GOTO_CASES[case]
    targets = _targets_for(
        tmp_path, suffix, "int x, y;\nvoid f(void) {\n" + body + "}\n"
    )
    assert live <= targets, (case, targets)
    assert not dead & targets, (case, targets)


def test_cpp_lambda_return_only_ends_the_lambda(tmp_path: Path) -> None:
    """A return inside a lambda body cuts the lambda's tail, not the caller's."""
    targets = _targets_for(
        tmp_path,
        ".cpp",
        "void f(void) {\n"
        "  auto l = []() {\n"
        "    a();\n"
        "    return;\n"
        "    dead();\n"
        "  };\n"
        "  after();\n"
        "}\n",
    )
    assert {"a()", "after()"} <= targets
    assert "dead()" not in targets


# Preprocessor branches that split one statement leave its real body stranded
# after a parse error; tree-sitter then sees a bare block that always returns.
# Patterns taken from STM32 HAL sources (HAL_PWREx_ConfigSupply, HAL_SAI_Init).
_SPLIT_BY_PREPROC_CASES: dict[str, str] = {
    "if_condition_per_branch": (
        "#if defined(FEATURE)\n"
        "  if (x == 0U)\n"
        "#else\n"
        "  if (y != 1)\n"
        "#endif /* FEATURE */\n"
        "  {\n"
        "    if (x) { return; } else { return; }\n"
        "  }\n"
        "  after();\n"
    ),
    "else_if_chain_with_wrapped_link": (
        "  if (x)\n"
        "  {\n"
        "    a();\n"
        "  }\n"
        "#if defined(FEATURE)\n"
        "  else if (y)\n"
        "  {\n"
        "    b();\n"
        "  }\n"
        "#endif /* FEATURE */\n"
        "  else\n"
        "  {\n"
        "    return;\n"
        "  }\n"
        "  after();\n"
    ),
}


@pytest.mark.parametrize(
    "case,suffix",
    [
        ("if_condition_per_branch", ".c"),
        ("if_condition_per_branch", ".cpp"),
        # tree-sitter-cpp loses `after();` out of the function body here, so
        # only the C parse (the HAL case) can keep it.
        ("else_if_chain_with_wrapped_link", ".c"),
    ],
)
def test_block_after_parse_error_does_not_cut_fall_through(
    tmp_path: Path, suffix: str, case: str
) -> None:
    targets = _targets_for(
        tmp_path,
        suffix,
        "int x, y;\nvoid f(void) {\n" + _SPLIT_BY_PREPROC_CASES[case] + "}\n",
    )
    assert "after()" in targets, (case, targets)


_REGION_LABEL_CASES: dict[str, tuple[str, set[str], set[str]]] = {
    # #5338 review: only the lambda takes &&L, so the outer computed goto must
    # not open the outer, unreachable L.
    "lambda_address_does_not_open_outer_label": (
        "  void *p = &&M;\n"
        "  auto g = [] { void *q = &&L; goto *q; L: inside(); };\n"
        "  goto *p;\n"
        "  return;\n"
        "  L: dead();\n"
        "  M: a();\n",
        {"a()", "inside()"},
        {"dead()"},
    ),
    # A lambda's &&M must not narrow the outer computed goto either: with no
    # outer address taken, it may land on every outer label.
    "lambda_address_does_not_hide_outer_labels": (
        "  auto g = [] { void *q = &&M; goto *q; M: inside(); };\n"
        "  void *p = (void *)x;\n"
        "  goto *p;\n"
        "  return;\n"
        "  L: release();\n",
        {"inside()", "release()"},
        set(),
    ),
    # A lambda's goto jumps inside the lambda only.
    "lambda_goto_does_not_open_outer_label": (
        "  auto g = [] { goto L; L: inside(); };\n"
        "  return;\n"
        "  L: dead();\n",
        {"inside()"},
        {"dead()"},
    ),
    # GNU statement expressions share the function's labels: a goto inside
    # one may leave for an outer label.
    "statement_expression_goto_leaves_for_outer_label": (
        "  int v = ({ if (x) goto fail; 1; });\n"
        "  a();\n"
        "  return;\n"
        "  fail: release();\n",
        {"a()", "release()"},
        set(),
    ),
    "statement_expression_computed_goto": (
        "  void *p = &&fail;\n"
        "  int v = ({ goto *p; 0; });\n"
        "  return;\n"
        "  fail: release();\n",
        {"release()"},
        set(),
    ),
    "unreachable_statement_expression_opens_nothing": (
        "  return;\n"
        "  { int v = ({ if (x) goto fail; 1; }); }\n"
        "  fail: dead();\n",
        set(),
        {"dead()"},
    ),
}


@pytest.mark.parametrize(
    "case,suffix",
    [
        *((c, ".cpp") for c in _REGION_LABEL_CASES if c.startswith("lambda")),
        *(
            (c, s)
            for c in _REGION_LABEL_CASES
            if not c.startswith("lambda")
            for s in (".c", ".cpp")
        ),
    ],
)
def test_label_scope_of_nested_regions(tmp_path: Path, suffix: str, case: str) -> None:
    body, live, dead = _REGION_LABEL_CASES[case]
    targets = _targets_for(
        tmp_path, suffix, "int x, y;\nvoid f(void) {\n" + body + "}\n"
    )
    assert live <= targets, (case, targets)
    assert not dead & targets, (case, targets)
