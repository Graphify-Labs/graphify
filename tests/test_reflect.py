from datetime import datetime, timezone

from graphify.ingest import save_query_result
from graphify.reflect import (
    aggregate_lessons,
    load_learning_overlay,
    load_memory_docs,
    parse_memory_doc,
    reflect,
    render_lessons_md,
)
from graphify.helix.state import community_records, new_state
from tests.native_helpers import make_loaded


NOW = datetime(2026, 6, 1, tzinfo=timezone.utc)


def test_saved_memory_round_trips_frontmatter(tmp_path):
    path = save_query_result(
        'what is "attention"?', "softmax", tmp_path,
        source_nodes=["AttentionLayer"], outcome="useful",
    )
    parsed = parse_memory_doc(path.read_text())
    assert parsed["question"] == 'what is "attention"?'
    assert parsed["source_nodes"] == ["AttentionLayer"]
    assert parsed["outcome"] == "useful"
    assert len(load_memory_docs(tmp_path)) == 1


def test_aggregation_and_render_are_deterministic():
    docs = [
        {"question": "q1", "date": "2026-05-31T00:00:00+00:00", "outcome": "useful", "source_nodes": ["Auth"]},
        {"question": "q2", "date": "2026-05-31T01:00:00+00:00", "outcome": "useful", "source_nodes": ["Auth"]},
        {"question": "bad", "date": "2026-05-31T02:00:00+00:00", "outcome": "dead_end", "source_nodes": ["Old"]},
    ]
    aggregate = aggregate_lessons(docs, None, now=NOW, min_corroboration=2)
    assert aggregate["preferred"][0]["node"] == "Auth"
    assert aggregate["dead_ends"][0]["question"] == "bad"
    assert render_lessons_md(aggregate) == render_lessons_md(aggregate)


def test_reflect_persists_learning_inside_atomic_generation(tmp_path):
    memory = tmp_path / "memory"
    memory.mkdir()
    for index in (1, 2):
        (memory / f"q{index}.md").write_text(
            "---\n"
            f'type: "query"\ndate: "2026-05-{29 + index:02d}T00:00:00+00:00"\n'
            f'question: "q{index}"\noutcome: "useful"\nsource_nodes: ["Auth"]\n---\n'
        )
    state = new_state(communities=community_records({0: ["auth"]}, labels={0: "Security"}))
    loaded = make_loaded(
        tmp_path / "native",
        nodes=[{"id": "auth", "label": "Auth", "source_file": "auth.py"}],
        state=state,
    )
    output, aggregate = reflect(
        memory, tmp_path / "LESSONS.md", graph_path=loaded.store_path,
        now=NOW, min_corroboration=2,
    )
    assert output.is_file() and aggregate["preferred"]
    overlay = load_learning_overlay(loaded.store_path)
    assert overlay["auth"]["status"] == "preferred"
    assert "Security" in output.read_text()
