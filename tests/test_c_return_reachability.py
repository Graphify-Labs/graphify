"""C/C++: do not emit calls edges for statements after an unconditional return.

Unreachable CubeMX tails after a USER CODE `return;` used to produce false
bridge edges (e.g. low_level_init -> Error_Handler) because walk_calls visited
every call_expression in the function body.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from graphify.extract import extract


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
