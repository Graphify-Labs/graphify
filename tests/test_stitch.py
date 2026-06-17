"""Tests for incremental post-merge stitch pass."""
from __future__ import annotations

import json
from pathlib import Path

import networkx as nx

from graphify.build import build_from_json, build_merge
from graphify.stitch import stitch_incremental_links


def _calendar_graph() -> dict:
    cal_sf = "BoT-calendars-shared/src/CALENDAR_CALCULATIONS.md"
    return {
        "nodes": [
            {
                "id": "calendar_calculations_calculateworkingtimefromteamscalendar",
                "label": "calculateWorkingTimeFromTeamsCalendar",
                "file_type": "code",
                "source_file": cal_sf,
            },
            {
                "id": "calendar_calculations_createassignmentcalendarsnapshot",
                "label": "createAssignmentCalendarSnapshot",
                "file_type": "code",
                "source_file": cal_sf,
            },
        ],
        "edges": [],
        "input_tokens": 0,
        "output_tokens": 0,
    }


def _array_graph() -> dict:
    array_sf = "ARRAY_FIELDS_TYPED_APPROACH.md"
    return {
        "nodes": [
            {
                "id": "array_fields_typed_approach_sprint",
                "label": "Sprint",
                "file_type": "code",
                "source_file": array_sf,
            },
            {
                "id": "array_fields_typed_approach_document",
                "label": "Typed Array Fields Implementation",
                "file_type": "document",
                "source_file": array_sf,
            },
        ],
        "edges": [],
        "input_tokens": 0,
        "output_tokens": 0,
    }


def test_stitch_links_symbol_mentions_from_changed_markdown(tmp_path: Path) -> None:
    root = tmp_path / "corpus"
    root.mkdir()
    array_md = root / "ARRAY_FIELDS_TYPED_APPROACH.md"
    cal_dir = root / "BoT-calendars-shared" / "src"
    cal_dir.mkdir(parents=True)
    cal_md = cal_dir / "CALENDAR_CALCULATIONS.md"
    cal_md.write_text("# Calendar\n", encoding="utf-8")
    array_md.write_text(
        "# Typed Array Fields Implementation\n\n"
        "See `BoT-calendars-shared/src/CALENDAR_CALCULATIONS.md` and "
        "`calculateWorkingTimeFromTeamsCalendar`.\n",
        encoding="utf-8",
    )

    graph_path = tmp_path / "graph.json"
    G0 = build_from_json(_calendar_graph(), root=root)
    graph_path.write_text(
        json.dumps(nx.node_link_data(G0, edges="edges")),
        encoding="utf-8",
    )

    G = build_merge(
        [_array_graph()],
        graph_path=graph_path,
        prune_sources=None,
        dedup=False,
        root=root,
    )

    added = stitch_incremental_links(
        G,
        [str(array_md.relative_to(root))],
        root=root,
    )
    assert added >= 1

    refs = [
        (d.get("_src", u), d.get("_tgt", v))
        for u, v, d in G.edges(data=True)
        if d.get("relation") == "references"
    ]
    anchor = "array_fields_typed_approach_document"
    cal_fn = "calendar_calculations_calculateworkingtimefromteamscalendar"
    assert (anchor, cal_fn) in refs


def test_stitch_uses_new_node_ids_when_source_file_hallucinated(tmp_path: Path) -> None:
    """LLM may attribute nodes to wrong paths; stitch still wires via new_node_ids."""
    root = tmp_path / "corpus"
    root.mkdir()
    array_md = root / "ARRAY_FIELDS_TYPED_APPROACH.md"
    cal_dir = root / "BoT-calendars-shared" / "src"
    cal_dir.mkdir(parents=True)
    (cal_dir / "CALENDAR_CALCULATIONS.md").write_text("# Calendar\n", encoding="utf-8")
    array_md.write_text(
        "# Doc\n\nUse `calculateWorkingTimeFromTeamsCalendar`.\n",
        encoding="utf-8",
    )

    graph_path = tmp_path / "graph.json"
    G0 = build_from_json(_calendar_graph(), root=root)
    graph_path.write_text(
        json.dumps(nx.node_link_data(G0, edges="edges")),
        encoding="utf-8",
    )

    # Only nodes whose source_file is missing/wrong for *array_md* — do not
    # attribute nodes to another on-disk file (build_merge #1344 drops all nodes
    # for every source_file present in the re-extract batch).
    hallucinated = {
        "nodes": [
            {
                "id": "array_field_renderer_SprintArrayRenderer",
                "label": "SprintArrayRenderer",
                "file_type": "code",
                "source_file": "nextjsapp/app/utils/components/tasks/ArrayFieldRenderer.tsx",
            },
        ],
        "edges": [],
        "input_tokens": 0,
        "output_tokens": 0,
    }
    G = build_merge([hallucinated], graph_path=graph_path, prune_sources=None, dedup=False, root=root)
    added = stitch_incremental_links(
        G,
        [str(array_md.relative_to(root))],
        root=root,
        new_node_ids={"array_field_renderer_SprintArrayRenderer"},
    )
    assert added == 1
    refs = [
        (d.get("_src", u), d.get("_tgt", v))
        for u, v, d in G.edges(data=True)
        if d.get("relation") == "references"
    ]
    assert ("array_field_renderer_SprintArrayRenderer", "calendar_calculations_calculateworkingtimefromteamscalendar") in refs


def test_stitch_skips_ambiguous_symbol(tmp_path: Path) -> None:
    root = tmp_path / "corpus"
    root.mkdir()
    doc_a = root / "a.md"
    doc_b = root / "b.md"
    doc_a.write_text("Uses `handle`.\n", encoding="utf-8")
    doc_b.write_text("# B\n", encoding="utf-8")

    extraction = {
        "nodes": [
            {"id": "svc_a_handle", "label": "handle", "file_type": "code", "source_file": "svc/a.py"},
            {"id": "svc_b_handle", "label": "handle", "file_type": "code", "source_file": "svc/b.py"},
            {"id": "b_document", "label": "B", "file_type": "document", "source_file": "b.md"},
        ],
        "edges": [],
        "input_tokens": 0,
        "output_tokens": 0,
    }
    G = build_from_json(extraction, root=root)
    added = stitch_incremental_links(G, ["b.md"], root=root)
    assert added == 0
