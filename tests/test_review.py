"""Evidence-preserving graph/model boundaries and optional interpretation."""
from __future__ import annotations

import copy
import json

import networkx as nx
import pytest

from graphify import review
from graphify.review_source import ReviewError, git_target
from tests.test_review_source import git, repository  # noqa: F401 — shared temporary Git fixture


@pytest.fixture
def model(repository):
    root, base, head = repository
    return review.build_review(root, git_target(root, base, head))


def reply_for(model, **changes):
    story = model["stories"][0]
    return json.dumps({"behavior_changes": [{"story_id": story["id"],
        "summary": "MFA credentials return a challenge before creating a session.",
        "before_pseudocode": "Create and return a session.",
        "after_pseudocode": "If MFA is required, return a challenge. Otherwise create and return a session.",
        "evidence_ids": story["evidence_ids"], "uncertainties": [], **changes}]})


def test_fixed_model_preserves_source_direction_and_confidence(model, repository):
    root, base, head = repository
    assert model["target"]["comparison_base"] == base
    assert model["target"]["head"] == head
    assert model["stories"][0]["seed_methods"]["head"] == "python_ast_span"
    assert model["graph_diff"]["new_nodes"]
    assert any("challenge" in n["label"] for n in model["graph_diff"]["new_nodes"])
    graph = model["stories"][0]["graphs"]["head"]
    labels = {n["id"]: n["label"] for n in graph["nodes"]}
    calls = [e for e in graph["edges"] if e["relation"] == "calls"]
    assert any("authenticate" in labels[e["source"]] and "challenge" in labels[e["target"]] for e in calls)
    assert all(e["confidence"] in review.CONFIDENCE for e in calls)
    assert {"base", "head"} <= {e["side"] for e in model["evidence"]}
    assert all("source_file" in n for n in model["graph_diff"]["new_nodes"])
    assert not (root / "graphify-out" / "graph.json").exists()


def test_incoming_blast_radius_retains_unchanged_caller(model):
    radius = model["blast_radius"]["head"]
    assert radius["direct_count"] >= 1
    assert radius["indirect_count"] >= 1
    assert any("login" in h["id"] for h in radius["indirect"])
    assert radius["depth"] == 2
    assert radius["communities"]
    assert radius["direct_count"] == 2  # authenticate + challenge, not the L1 file node
    assert "auth" not in radius["direct_ids"]


def test_body_only_change_has_source_story_without_topology_change(repository):
    root, _, head = repository
    text = (root / "auth.py").read_text().replace("return 'challenge'", "return 'challenge blocked'")
    (root / "auth.py").write_text(text, encoding="utf-8")
    git(root, "add", ".")
    git(root, "commit", "-qm", "error behavior")
    changed = git(root, "rev-parse", "HEAD")
    model = review.build_review(root, git_target(root, head, changed))
    assert model["graph_diff"]["summary"] == "no changes"
    assert model["stories"][0]["evidence_ids"]
    assert "challenge blocked" in model["stories"][0]["source"]["patch"]


def test_attribute_only_difference_is_rehydrated_not_upgraded():
    old, new = nx.DiGraph(), nx.DiGraph()
    for graph, line in ((old, "L1"), (new, "L2")):
        graph.add_node("a", label="a", source_file="a.py", source_location=line)
        graph.add_node("b", label="b", source_file="b.py", source_location="L1")
        graph.add_edge("a", "b", relation="calls", confidence="INFERRED", source_file="a.py", source_location=line)
    assert review.graph_diff(old, new)["summary"] == "no changes"
    edge = review._edge("a", "b", new.edges["a", "b"])
    assert edge["confidence"] == "INFERRED" and edge["source_location"] == "L2"


def test_deterministic_mode_does_not_discover_or_call_backend(repository, monkeypatch):
    import graphify.llm as llm
    def unexpected(*args, **kwargs):
        pytest.fail("deterministic review entered the provider boundary")
    monkeypatch.setattr(llm, "detect_backend", unexpected)
    monkeypatch.setattr(llm, "_call_llm", unexpected)
    root, base, head = repository
    model = review.build_review(root, git_target(root, base, head))
    assert model["behavior_analysis"]["status"] == "not_requested"


def test_mocked_inference_reuses_backend_and_keeps_graph_facts_unchanged(model, monkeypatch):
    import graphify.llm as llm
    original = copy.deepcopy(model["graph_diff"])
    calls = []
    def call(prompt, **kwargs):
        calls.append((prompt, kwargs))
        kwargs["usage_out"].update(input=10, output=20)
        return reply_for(model)
    monkeypatch.setattr(llm, "_call_llm", call)
    review.infer_behavior(model, backend="ollama", model="configured-model")
    review.validate_review(model)
    assert model["behavior_analysis"]["status"] == "complete"
    assert model["stories"][0]["behavior"]["confidence"] == "INFERRED"
    assert calls[0][1]["backend"] == "ollama"
    assert calls[0][1]["model"] == "configured-model"
    assert "untrusted_source" in calls[0][0]
    assert model["behavior_analysis"]["usage"]["output"] == 20
    assert model["graph_diff"] == original


@pytest.mark.parametrize("changes", [{"evidence_ids": ["invented"]}, {"evidence_ids": []},
                                    {"summary": ""}, {"story_id": "invented"},
                                    {"uncertainties": [123]}])
def test_unsubstantiated_or_malformed_behavior_rejected(model, monkeypatch, changes):
    import graphify.llm as llm
    monkeypatch.setattr(llm, "_call_llm", lambda *args, **kwargs: reply_for(model, **changes))
    review.infer_behavior(model, backend="ollama")
    assert model["stories"][0]["behavior"] is None
    assert model["behavior_analysis"]["rejected"] == 1


def test_wrong_side_citations_rejected(model, monkeypatch):
    import graphify.llm as llm
    base_ids = [e["id"] for e in model["evidence"] if e["side"] == "base" and e["id"] in model["stories"][0]["evidence_ids"]]
    monkeypatch.setattr(llm, "_call_llm", lambda *args, **kwargs: reply_for(model, evidence_ids=base_ids))
    review.infer_behavior(model, backend="ollama")
    assert model["stories"][0]["behavior"] is None


@pytest.mark.parametrize("reply", ["not JSON", "[]", '{"behavior_changes":"wrong"}', "x" * 64001],
                         ids=["not-json", "wrong-shape", "wrong-entries", "oversized"])
def test_failed_inference_preserves_structural_output(model, monkeypatch, reply):
    import graphify.llm as llm
    before = copy.deepcopy(model["graph_diff"])
    monkeypatch.setattr(llm, "_call_llm", lambda *args, **kwargs: reply)
    review.infer_behavior(model, backend="ollama")
    assert model["behavior_analysis"]["status"] == "failed"
    assert model["graph_diff"] == before


def test_unavailable_and_abstained_are_explicit(model, monkeypatch):
    import graphify.llm as llm
    monkeypatch.setattr(llm, "detect_backend", lambda: None)
    review.infer_behavior(model)
    assert model["behavior_analysis"]["status"] == "unavailable"
    monkeypatch.setattr(llm, "_call_llm", lambda *args, **kwargs: '{"behavior_changes":[]}')
    review.infer_behavior(model, backend="ollama")
    assert model["behavior_analysis"]["status"] == "abstained"


def test_revision_and_range_validation(model):
    invalid = copy.deepcopy(model)
    invalid["evidence"][0]["revision"] = "c" * 40
    with pytest.raises(ReviewError, match="revision"):
        review.validate_review(invalid)
    invalid = copy.deepcopy(model)
    invalid["evidence"][0]["line_end"] += 20
    with pytest.raises(ReviewError, match="range"):
        review.validate_review(invalid)


def test_seed_cap_and_depth_are_disclosed(monkeypatch):
    graph = nx.DiGraph()
    graph.add_edge("caller", "one", relation="calls", confidence="EXTRACTED")
    graph.add_node("two")
    monkeypatch.setattr(review, "MAX_SEEDS", 1)
    result = review._context(graph, ["one", "two"], 1)
    assert result["omitted_seeds"] == 1
    assert result["indirect_count"] == 1
    assert review._context(graph, ["one"], 0)["indirect_count"] == 0


def test_stable_review_serialization(model, repository):
    root, base, head = repository
    again = review.build_review(root, git_target(root, base, head))
    assert json.dumps(model, sort_keys=True) == json.dumps(again, sort_keys=True)


def test_nested_package_paths_remain_repo_relative(repository):
    root, _, head = repository
    package = root / "nested" / "package"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "service.py").write_text("def run():\n    return 1\n", encoding="utf-8")
    git(root, "add", ".")
    git(root, "commit", "-qm", "nested source")
    before = git(root, "rev-parse", "HEAD")
    (package / "service.py").write_text("def run():\n    return 2\n", encoding="utf-8")
    git(root, "add", ".")
    git(root, "commit", "-qm", "nested behavior")
    result = review.build_review(root, git_target(root, before, git(root, "rev-parse", "HEAD")))
    nodes = result["stories"][0]["graphs"]["head"]["nodes"]
    assert nodes
    assert all(n["source_file"] == "nested/package/service.py" for n in nodes)
    assert result["stories"][0]["seed_methods"]["head"] == "python_ast_span"


def test_insertion_after_existing_file_is_not_all_existing_symbols():
    graph = nx.DiGraph()
    graph.add_node("old", source_file="a.py", source_location="L1", file_type="code")
    seeds, method = review._seeds(graph, "a.py", "def old():\n    return 1\n", [(3, 3)])
    assert seeds == [] and method == "insertion_after_existing_source"


def test_cli_local_review_runs_end_to_end(repository, monkeypatch, capsys):
    root, base, head = repository
    monkeypatch.chdir(root)
    canonical = root / "graphify-out" / "graph.json"
    canonical.parent.mkdir()
    canonical.write_text('"existing graph"', encoding="utf-8")
    review.cmd_review(["--review", "--base", base, "--head", head])
    output = capsys.readouterr().out
    assert "Behavior analysis: not_requested" in output
    assert list((root / "graphify-out" / "reviews").glob("*/review.html"))
    assert canonical.read_text() == '"existing graph"'


def test_snapshot_dependent_id_is_excluded_with_explicit_coverage(tmp_path, monkeypatch):
    root = tmp_path.resolve()
    (root / "a.py").write_text("A = 1\n", encoding="utf-8")
    prefix = review.re.sub(r"\W+", "_", str(root)).strip("_")
    extraction = {"nodes": [{"id": prefix + "_a", "label": "synthetic", "source_file": "a.py", "source_location": "L1", "file_type": "code"}], "edges": []}
    monkeypatch.setattr(review, "extract", lambda *args, **kwargs: extraction)
    graph, coverage = review._structural_graph({"root": root, "sources": {"a.py": "A = 1\n"}, "omitted": []}, tmp_path / "cache")
    assert not graph
    assert coverage["path_dependent_nodes"] == 1
    assert coverage["path_dependent_sources"] == ["a.py"]


def test_first_line_definition_does_not_seed_the_whole_file():
    graph = nx.DiGraph()
    graph.add_node("file", label="a.py", source_file="a.py", source_location="L1", file_type="code")
    graph.add_node("function", label="run()", source_file="a.py", source_location="L1", file_type="code")
    graph.add_node("other", label="other()", source_file="a.py", source_location="L4", file_type="code")
    source = "def run():\n    return 2\n\ndef other():\n    return 1\n"
    seeds, method = review._seeds(graph, "a.py", source, [(2, 2)])
    assert seeds == ["function"] and method == "python_ast_span"


def test_one_hunk_seeds_all_changed_siblings_and_outer_logic():
    graph = nx.DiGraph()
    definitions = [("outer", 1), ("first", 2), ("second", 4), ("untouched", 9)]
    for name, line in definitions:
        graph.add_node(name, label=name + "()", source_file="a.py",
                       source_location=f"L{line}", file_type="code")
    source = ("def outer():\n"
              "    def first():\n        return 1\n"
              "    def second():\n        return 2\n"
              "    return first() + second()\n\n\n"
              "def untouched():\n    return 3\n")
    seeds, method = review._seeds(graph, "a.py", source, [(2, 5)])
    assert seeds == ["first", "second"] and method == "python_ast_span"
    seeds, _ = review._seeds(graph, "a.py", source, [(3, 6)])
    assert seeds == ["first", "outer", "second"]


def test_real_extraction_includes_both_methods_added_in_one_hunk(repository):
    root, _, head = repository
    (root / "auth.py").write_text((root / "auth.py").read_text() +
                                 "\ndef first_added():\n    return 1\n"
                                 "\ndef second_added():\n    return 2\n", encoding="utf-8")
    git(root, "add", ".")
    git(root, "commit", "-qm", "add two methods")
    result = review.build_review(root, git_target(root, head, git(root, "rev-parse", "HEAD")))
    direct = result["blast_radius"]["head"]["direct_ids"]
    assert len(direct) == 2
    assert any("first_added" in node for node in direct)
    assert any("second_added" in node for node in direct)
