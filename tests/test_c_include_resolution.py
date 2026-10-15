"""Focused regression tests for C/C++/ObjC quoted include resolution (#4354).

Covers:
1. Core/Src/adc.c resolving "adc.h" to Core/Inc/adc.h.
2. Nested harness resolving headers from another directory.
3. Directory-qualified include (e.g., "sub/util.h").
4. Unique longest-shared-directory-prefix winner.
5. Equally scored candidates remaining unresolved (tie).
6. Exact-case matches taking precedence over case-insensitive alternatives.
7. Case-insensitive fallback when no exact match exists.
8. Failed relative paths (./ or ../) remaining unresolved.
9. Angle-bracket system includes not binding to local same-named files.
10. Existing sibling include behavior remaining unchanged.
11. Correct target IDs after .h/.c collision disambiguation.
12. Cache consistency and incremental extraction after a header is added or removed.
13. Objective-C parity for quoted #import / #include outside sibling directory.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest
import networkx as nx

from graphify.extract import extract
from graphify.build import build


def _real(tmp_path: Path) -> Path:
    return Path(os.path.realpath(tmp_path))


def test_stm32_core_src_resolves_to_core_inc(tmp_path: Path) -> None:
    """Core/Src/adc.c resolving "adc.h" to Core/Inc/adc.h."""
    root = _real(tmp_path)
    src_dir = root / "Core" / "Src"
    inc_dir = root / "Core" / "Inc"
    src_dir.mkdir(parents=True, exist_ok=True)
    inc_dir.mkdir(parents=True, exist_ok=True)

    adc_h = inc_dir / "adc.h"
    adc_h.write_text("void adc_init(void);\n", encoding="utf-8")

    adc_c = src_dir / "adc.c"
    adc_c.write_text('#include "adc.h"\nvoid adc_init(void) {}\n', encoding="utf-8")

    result = extract([adc_c, adc_h], root=root, cache_root=root)
    assert not result.get("error")

    import_edges = [
        e for e in result["edges"]
        if e.get("relation") == "imports" and "adc.c" in str(e.get("source_file", ""))
    ]
    assert len(import_edges) == 1
    edge = import_edges[0]

    header_nodes = [
        n for n in result["nodes"]
        if "adc.h" in str(n.get("source_file", "")) and n.get("label") == "adc.h"
    ]
    assert len(header_nodes) == 1
    assert edge["target"] == header_nodes[0]["id"]
    assert "target_file" not in edge

    # Verify build graph produces 0 external stub nodes for adc.h
    G = build([result], directed=True, root=root)
    stubs = [
        n for n, d in G.nodes(data=True)
        if d.get("external") and d.get("label") == "adc"
    ]
    assert not stubs, f"Expected no stub node for adc, found {stubs}"
    assert G.has_edge(edge["source"], edge["target"])


def test_nested_harness_resolves_headers_from_another_dir(tmp_path: Path) -> None:
    """A nested test harness resolving headers from another directory."""
    root = _real(tmp_path)
    tests_dir = root / "tests" / "harness"
    app_dir = root / "app"
    tests_dir.mkdir(parents=True, exist_ok=True)
    app_dir.mkdir(parents=True, exist_ok=True)

    nfc_h = app_dir / "nfc.h"
    nfc_h.write_text("void nfc_poll(void);\n", encoding="utf-8")

    harness_c = tests_dir / "harness.c"
    harness_c.write_text('#include "nfc.h"\nint main(void) { return 0; }\n', encoding="utf-8")

    result = extract([harness_c, nfc_h], root=root, cache_root=root)
    import_edges = [
        e for e in result["edges"]
        if e.get("relation") == "imports" and "harness.c" in str(e.get("source_file", ""))
    ]
    assert len(import_edges) == 1

    header_nodes = [
        n for n in result["nodes"]
        if "nfc.h" in str(n.get("source_file", "")) and n.get("label") == "nfc.h"
    ]
    assert len(header_nodes) == 1
    assert import_edges[0]["target"] == header_nodes[0]["id"]


def test_directory_qualified_include(tmp_path: Path) -> None:
    """Directory-qualified include such as "sub/util.h"."""
    root = _real(tmp_path)
    src_dir = root / "src"
    inc_sub_dir = root / "include" / "sub"
    other_dir = root / "other"
    src_dir.mkdir(parents=True, exist_ok=True)
    inc_sub_dir.mkdir(parents=True, exist_ok=True)
    other_dir.mkdir(parents=True, exist_ok=True)

    util_matching = inc_sub_dir / "util.h"
    util_matching.write_text("int sub_util(void);\n", encoding="utf-8")

    util_unrelated = other_dir / "util.h"
    util_unrelated.write_text("int other_util(void);\n", encoding="utf-8")

    main_c = src_dir / "main.c"
    main_c.write_text('#include "sub/util.h"\n', encoding="utf-8")

    result = extract([main_c, util_matching, util_unrelated], root=root, cache_root=root)
    import_edges = [
        e for e in result["edges"]
        if e.get("relation") == "imports" and "main.c" in str(e.get("source_file", ""))
    ]
    assert len(import_edges) == 1

    matching_header_node = next(
        n for n in result["nodes"]
        if "include" in str(n.get("source_file", "")) and n.get("label") == "util.h"
    )
    assert import_edges[0]["target"] == matching_header_node["id"]


def test_unique_longest_prefix_winner(tmp_path: Path) -> None:
    """Unique longest-shared-directory-prefix winner resolves."""
    root = _real(tmp_path)
    drv_src = root / "components" / "driver" / "src"
    drv_inc = root / "components" / "driver" / "include"
    sen_inc = root / "components" / "sensor" / "include"
    drv_src.mkdir(parents=True, exist_ok=True)
    drv_inc.mkdir(parents=True, exist_ok=True)
    sen_inc.mkdir(parents=True, exist_ok=True)

    drv_h = drv_inc / "adc.h"
    drv_h.write_text("int driver_adc(void);\n", encoding="utf-8")

    sen_h = sen_inc / "adc.h"
    sen_h.write_text("int sensor_adc(void);\n", encoding="utf-8")

    importer = drv_src / "adc.c"
    importer.write_text('#include "adc.h"\n', encoding="utf-8")

    result = extract([importer, drv_h, sen_h], root=root, cache_root=root)
    import_edges = [
        e for e in result["edges"]
        if e.get("relation") == "imports" and "adc.c" in str(e.get("source_file", ""))
    ]
    assert len(import_edges) == 1

    drv_header_node = next(
        n for n in result["nodes"]
        if "driver" in str(n.get("source_file", "")) and n.get("label") == "adc.h"
    )
    assert import_edges[0]["target"] == drv_header_node["id"]


def test_equally_scored_candidates_remain_unresolved(tmp_path: Path) -> None:
    """Equally scored candidates remain unresolved (tie fails closed)."""
    root = _real(tmp_path)
    test_dir = root / "test"
    mod_a = root / "module_a"
    mod_b = root / "module_b"
    test_dir.mkdir(parents=True, exist_ok=True)
    mod_a.mkdir(parents=True, exist_ok=True)
    mod_b.mkdir(parents=True, exist_ok=True)

    util_a = mod_a / "util.h"
    util_a.write_text("int util_a(void);\n", encoding="utf-8")

    util_b = mod_b / "util.h"
    util_b.write_text("int util_b(void);\n", encoding="utf-8")

    harness = test_dir / "harness.c"
    harness.write_text('#include "util.h"\n', encoding="utf-8")

    result = extract([harness, util_a, util_b], root=root, cache_root=root)
    import_edges = [
        e for e in result["edges"]
        if e.get("relation") == "imports" and "harness.c" in str(e.get("source_file", ""))
    ]
    assert len(import_edges) == 1
    edge = import_edges[0]

    # Target remains the fallback stem
    assert edge["target"] == "util"

    # Build creates an external stub node because of the tie
    G = build([result], directed=True, root=root)
    stub_data = G.nodes.get("util")
    assert stub_data is not None
    assert stub_data.get("external") is True


def test_exact_case_precedence_over_case_insensitive(tmp_path: Path) -> None:
    """Exact-case match takes precedence over case-insensitive alternatives."""
    root = _real(tmp_path)
    src_dir = root / "src"
    inc1_dir = root / "inc1"
    inc2_dir = root / "inc2"
    src_dir.mkdir(parents=True, exist_ok=True)
    inc1_dir.mkdir(parents=True, exist_ok=True)
    inc2_dir.mkdir(parents=True, exist_ok=True)

    exact_h = inc1_dir / "adc.h"
    exact_h.write_text("int exact_adc(void);\n", encoding="utf-8")

    upper_h = inc2_dir / "ADC.h"
    upper_h.write_text("int upper_adc(void);\n", encoding="utf-8")

    main_c = src_dir / "main.c"
    main_c.write_text('#include "adc.h"\n', encoding="utf-8")

    result = extract([main_c, exact_h, upper_h], root=root, cache_root=root)
    import_edges = [
        e for e in result["edges"]
        if e.get("relation") == "imports" and "main.c" in str(e.get("source_file", ""))
    ]
    assert len(import_edges) == 1

    exact_node = next(
        n for n in result["nodes"]
        if "inc1" in str(n.get("source_file", "")) and n.get("label") == "adc.h"
    )
    assert import_edges[0]["target"] == exact_node["id"]


def test_case_insensitive_fallback_when_no_exact_match(tmp_path: Path) -> None:
    """Case-insensitive fallback succeeds when no exact match exists."""
    root = _real(tmp_path)
    src_dir = root / "src"
    inc_dir = root / "inc"
    src_dir.mkdir(parents=True, exist_ok=True)
    inc_dir.mkdir(parents=True, exist_ok=True)

    upper_h = inc_dir / "ADC.h"
    upper_h.write_text("int upper_adc(void);\n", encoding="utf-8")

    main_c = src_dir / "main.c"
    main_c.write_text('#include "adc.h"\n', encoding="utf-8")

    result = extract([main_c, upper_h], root=root, cache_root=root)
    import_edges = [
        e for e in result["edges"]
        if e.get("relation") == "imports" and "main.c" in str(e.get("source_file", ""))
    ]
    assert len(import_edges) == 1

    upper_node = next(
        n for n in result["nodes"]
        if "inc" in str(n.get("source_file", "")) and n.get("label") == "ADC.h"
    )
    assert import_edges[0]["target"] == upper_node["id"]


def test_failed_relative_path_remains_unresolved(tmp_path: Path) -> None:
    """Failed relative paths (./ or ../) do not bind to unrelated corpus files."""
    root = _real(tmp_path)
    src_dir = root / "src"
    other_dir = root / "other"
    src_dir.mkdir(parents=True, exist_ok=True)
    other_dir.mkdir(parents=True, exist_ok=True)

    unrelated_h1 = other_dir / "missing.h"
    unrelated_h1.write_text("int missing1(void);\n", encoding="utf-8")

    unrelated_h2 = other_dir / "missing_parent.h"
    unrelated_h2.write_text("int missing2(void);\n", encoding="utf-8")

    other2_dir = root / "other2"
    other2_dir.mkdir(parents=True, exist_ok=True)
    unrelated_h1b = other2_dir / "missing.h"
    unrelated_h1b.write_text("int missing1b(void);\n", encoding="utf-8")

    unrelated_h2b = other2_dir / "missing_parent.h"
    unrelated_h2b.write_text("int missing2b(void);\n", encoding="utf-8")

    main_c = src_dir / "main.c"
    main_c.write_text(
        '#include "./missing.h"\n'
        '#include "../missing_parent.h"\n'
        'int main(void) { return 0; }\n',
        encoding="utf-8",
    )

    result = extract(
        [main_c, unrelated_h1, unrelated_h2, unrelated_h1b, unrelated_h2b],
        root=root,
        cache_root=root,
    )
    import_edges = [
        e for e in result["edges"]
        if e.get("relation") == "imports" and "main.c" in str(e.get("source_file", ""))
    ]
    assert len(import_edges) == 2

    other_node_ids = {
        n["id"] for n in result["nodes"]
        if "other" in str(n.get("source_file", ""))
    }

    # Neither edge should resolve to any of the "other" files
    for edge in import_edges:
        assert edge["target"] not in other_node_ids
        assert edge["target"] in ("missing", "missing_parent")

    G = build([result], directed=True, root=root)
    for stub_id in ("missing", "missing_parent"):
        data = G.nodes.get(stub_id)
        assert data is not None
        assert data.get("external") is True


def test_angle_bracket_system_includes_not_bound_locally(tmp_path: Path) -> None:
    """Angle-bracket system includes do not bind to local corpus files."""
    root = _real(tmp_path)
    src_dir = root / "src"
    inc1_dir = root / "include1"
    inc2_dir = root / "include2"
    src_dir.mkdir(parents=True, exist_ok=True)
    inc1_dir.mkdir(parents=True, exist_ok=True)
    inc2_dir.mkdir(parents=True, exist_ok=True)

    local_stdio1 = inc1_dir / "stdio.h"
    local_stdio1.write_text("// local fake stdio 1\n", encoding="utf-8")

    local_stdio2 = inc2_dir / "stdio.h"
    local_stdio2.write_text("// local fake stdio 2\n", encoding="utf-8")

    main_c = src_dir / "main.c"
    main_c.write_text('#include <stdio.h>\nint main(void) { return 0; }\n', encoding="utf-8")

    result = extract([main_c, local_stdio1, local_stdio2], root=root, cache_root=root)
    import_edges = [
        e for e in result["edges"]
        if e.get("relation") == "imports" and "main.c" in str(e.get("source_file", ""))
    ]
    assert len(import_edges) == 1
    edge = import_edges[0]

    local_stdio_ids = {
        n["id"] for n in result["nodes"]
        if "stdio.h" in str(n.get("source_file", ""))
    }
    assert edge["target"] not in local_stdio_ids
    assert edge["target"] == "stdio"

    G = build([result], directed=True, root=root)
    stub_data = G.nodes.get("stdio")
    assert stub_data is not None
    assert stub_data.get("external") is True


def test_existing_sibling_include_behavior_unchanged(tmp_path: Path) -> None:
    """Existing sibling include resolution remains prioritized and unchanged."""
    root = _real(tmp_path)
    src_dir = root / "src"
    other_dir = root / "other"
    src_dir.mkdir(parents=True, exist_ok=True)
    other_dir.mkdir(parents=True, exist_ok=True)

    sibling_h = src_dir / "helper.h"
    sibling_h.write_text("int sibling_helper(void);\n", encoding="utf-8")

    other_h = other_dir / "helper.h"
    other_h.write_text("int other_helper(void);\n", encoding="utf-8")

    main_c = src_dir / "main.c"
    main_c.write_text('#include "helper.h"\n', encoding="utf-8")

    result = extract([main_c, sibling_h, other_h], root=root, cache_root=root)
    import_edges = [
        e for e in result["edges"]
        if e.get("relation") == "imports" and "main.c" in str(e.get("source_file", ""))
    ]
    assert len(import_edges) == 1

    sibling_node = next(
        n for n in result["nodes"]
        if "src" in str(n.get("source_file", "")) and n.get("label") == "helper.h"
    )
    assert import_edges[0]["target"] == sibling_node["id"]


def test_collision_disambiguated_header_and_c_source(tmp_path: Path) -> None:
    """Header and C source with identical stem resolve to the header, not source."""
    root = _real(tmp_path)
    app_dir = root / "app"
    test_dir = root / "test"
    app_dir.mkdir(parents=True, exist_ok=True)
    test_dir.mkdir(parents=True, exist_ok=True)

    nfc_h = app_dir / "nfc.h"
    nfc_h.write_text("void nfc_run(void);\n", encoding="utf-8")

    nfc_c = app_dir / "nfc.c"
    nfc_c.write_text('#include "nfc.h"\nvoid nfc_run(void) {}\n', encoding="utf-8")

    main_c = test_dir / "main.c"
    main_c.write_text('#include "nfc.h"\n', encoding="utf-8")

    result = extract([main_c, nfc_h, nfc_c], root=root, cache_root=root)

    header_node = next(
        n for n in result["nodes"]
        if "nfc.h" in str(n.get("source_file", "")) and n.get("label") == "nfc.h"
    )
    source_node = next(
        n for n in result["nodes"]
        if "nfc.c" in str(n.get("source_file", "")) and n.get("label") == "nfc.c"
    )

    # Disambiguation must separate .h and .c
    assert header_node["id"] != source_node["id"]

    import_edge = next(
        e for e in result["edges"]
        if e.get("relation") == "imports" and "main.c" in str(e.get("source_file", ""))
    )
    assert import_edge["target"] == header_node["id"]


def test_cache_consistency_when_header_added_and_removed(tmp_path: Path) -> None:
    """Cache consistency: resolution dynamically reacts when header is added or removed."""
    root = _real(tmp_path)
    cache_dir = root / ".cache"
    src_dir = root / "src"
    inc_dir = root / "inc"
    src_dir.mkdir(parents=True, exist_ok=True)
    inc_dir.mkdir(parents=True, exist_ok=True)

    main_c = src_dir / "main.c"
    main_c.write_text('#include "util.h"\n', encoding="utf-8")

    # Pass 1: No util.h in project
    r1 = extract([main_c], root=root, cache_root=cache_dir)
    edge1 = next(e for e in r1["edges"] if e.get("relation") == "imports")
    assert edge1["target"] == "util"

    # Pass 2: Add inc/util.h. Even with main.c cached, whole-graph pass resolves it!
    util_h = inc_dir / "util.h"
    util_h.write_text("int util_func(void);\n", encoding="utf-8")

    r2 = extract([main_c, util_h], root=root, cache_root=cache_dir)
    edge2 = next(
        e for e in r2["edges"]
        if e.get("relation") == "imports" and "main.c" in str(e.get("source_file", ""))
    )
    header_node = next(
        n for n in r2["nodes"]
        if "util.h" in str(n.get("source_file", "")) and n.get("label") == "util.h"
    )
    assert edge2["target"] == header_node["id"]

    # Pass 3: Remove inc/util.h. It should revert to unresolved stem
    util_h.unlink()
    r3 = extract([main_c], root=root, cache_root=cache_dir)
    edge3 = next(e for e in r3["edges"] if e.get("relation") == "imports")
    assert edge3["target"] == "util"


def test_objc_quoted_include_and_import_parity(tmp_path: Path) -> None:
    """Objective-C parity: quoted #import / #include outside sibling resolves to header."""
    root = _real(tmp_path)
    src_dir = root / "App"
    inc_dir = root / "Shared" / "Headers"
    src_dir.mkdir(parents=True, exist_ok=True)
    inc_dir.mkdir(parents=True, exist_ok=True)

    helper_h = inc_dir / "Helper.h"
    helper_h.write_text(
        "@interface Helper : NSObject\n"
        "- (void)help;\n"
        "@end\n",
        encoding="utf-8",
    )

    app_m = src_dir / "AppDelegate.m"
    app_m.write_text(
        '#import "Helper.h"\n'
        '#import <Foundation/Foundation.h>\n'
        '@implementation AppDelegate\n'
        '@end\n',
        encoding="utf-8",
    )

    result = extract([app_m, helper_h], root=root, cache_root=root)
    import_edges = [
        e for e in result["edges"]
        if e.get("relation") == "imports" and "AppDelegate.m" in str(e.get("source_file", ""))
    ]
    assert len(import_edges) == 2

    helper_node = next(
        n for n in result["nodes"]
        if "Helper.h" in str(n.get("source_file", "")) and n.get("label") == "Helper.h"
    )

    helper_edge = next(e for e in import_edges if e["target"] == helper_node["id"])
    assert helper_edge is not None

    foundation_edge = next(e for e in import_edges if e["target"] == "foundation")
    assert foundation_edge is not None
