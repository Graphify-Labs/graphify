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
    prev = get_c_cpp_unreachable_warnings()
    set_c_cpp_unreachable_warnings(True)
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
        "void after(void) {}\n",
        encoding="utf-8",
    )
    body.write_text(
        "void a(void);\n"
        "void b(void);\n"
        "void after(void);\n"
        "void f(int x) {\n"
        "  switch (x) {\n"
        "  case 1:\n"
        "    a();\n"
        "    return;\n"
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

    set_c_cpp_unreachable_warnings(True)
    extract([main, body], root=root, cache_root=root)
    err_on = capsys.readouterr().err
    assert "fall-through-unreachable" in err_on
    assert "assembler jumps" in err_on or "asm" in err_on.lower()

    set_c_cpp_unreachable_warnings(False)
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
