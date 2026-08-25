"""Tests for graphify ci-select module."""
from __future__ import annotations

import json
import textwrap
from pathlib import Path
from unittest.mock import patch

import networkx as nx
import pytest
from networkx.readwrite import json_graph

from graphify.ci_select import (
    TestPlan,
    bfs_reachable,
    ci_select,
    cli_main,
    find_nodes_for_file,
    load_test_jobs,
    match_patterns,
    parse_diff_files,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_graph() -> nx.DiGraph:
    """Build a small test graph with cross-repo structure."""
    G = nx.DiGraph()
    # service-a files
    G.add_node("fs_main", source_file="service-a/cmd/service-a/main.go", label="main.go")
    G.add_node("fs_clusters", source_file="service-a/internal/servers/clusters_server.go", label="clusters_server.go")
    G.add_node("fs_subnets", source_file="service-a/internal/servers/subnets_server.go", label="subnets_server.go")
    G.add_node("fs_proto", source_file="service-a/internal/api/public/v1/clusters_service.pb.go", label="clusters_service.pb.go")
    G.add_node("fs_db", source_file="service-a/internal/database/clusters.go", label="clusters.go")
    G.add_node("fs_lint", source_file="service-a/dev/lint.py", label="lint.py")
    G.add_node("fs_chart", source_file="service-a/charts/values.yaml", label="values.yaml")
    G.add_node("fs_it", source_file="service-a/it/integration_test.go", label="integration_test.go")

    # service-b-operator files
    G.add_node("op_ctrl", source_file="service-b-operator/internal/controller/cluster_controller.go", label="cluster_controller.go")
    G.add_node("op_api", source_file="service-b-operator/api/v1alpha1/cluster_types.go", label="cluster_types.go")

    # Edges: clusters_server -> proto -> operator controller
    G.add_edge("fs_clusters", "fs_proto", relation="references")
    G.add_edge("fs_clusters", "fs_db", relation="calls")
    G.add_edge("fs_proto", "op_ctrl", relation="references")
    G.add_edge("op_ctrl", "op_api", relation="references")
    G.add_edge("fs_main", "fs_clusters", relation="calls")
    G.add_edge("fs_clusters", "fs_subnets", relation="references")
    G.add_edge("fs_chart", "fs_it", relation="references")

    return G


def _save_graph(G: nx.DiGraph, path: Path) -> None:
    data = json_graph.node_link_data(G, edges="links")
    path.write_text(json.dumps(data), encoding="utf-8")


TEST_JOBS_YAML = textwrap.dedent("""\
    service-a:
      jobs:
        run-unit-tests:
          graph_patterns:
            - "internal/**"
            - "cmd/**"
          description: "Unit tests"
        run-integration-tests-helm:
          graph_patterns:
            - "charts/**"
            - "it/**"
          description: "Integration tests (Helm)"
        check-generated-code:
          graph_patterns:
            - "proto/**"
            - "internal/api/**"
          description: "Proto validation"
        check-python-code:
          graph_patterns:
            - "dev/**"
          description: "Python lint"
""")


# ---------------------------------------------------------------------------
# Tests: parse_diff_files
# ---------------------------------------------------------------------------

class TestParseDiffFiles:
    def test_basic_diff(self):
        diff = textwrap.dedent("""\
            diff --git a/internal/servers/clusters_server.go b/internal/servers/clusters_server.go
            --- a/internal/servers/clusters_server.go
            +++ b/internal/servers/clusters_server.go
            @@ -1,3 +1,4 @@
            +// new line
             package servers
        """)
        files = parse_diff_files(diff)
        assert files == ["internal/servers/clusters_server.go"]

    def test_multiple_files(self):
        diff = textwrap.dedent("""\
            diff --git a/file1.go b/file1.go
            +++ b/file1.go
            diff --git a/file2.go b/file2.go
            +++ b/file2.go
        """)
        files = parse_diff_files(diff)
        assert files == ["file1.go", "file2.go"]

    def test_no_duplicates(self):
        diff = textwrap.dedent("""\
            diff --git a/file1.go b/file1.go
            +++ b/file1.go
            diff --git a/file1.go b/file1.go
            +++ b/file1.go
        """)
        files = parse_diff_files(diff)
        assert files == ["file1.go"]

    def test_empty_diff(self):
        assert parse_diff_files("") == []


# ---------------------------------------------------------------------------
# Tests: find_nodes_for_file
# ---------------------------------------------------------------------------

class TestFindNodesForFile:
    def test_find_with_repo_prefix(self):
        G = _make_graph()
        nodes = find_nodes_for_file(G, "internal/servers/clusters_server.go", "service-a")
        assert "fs_clusters" in nodes

    def test_find_no_match(self):
        G = _make_graph()
        nodes = find_nodes_for_file(G, "nonexistent_file.go", "service-a")
        assert nodes == []


# ---------------------------------------------------------------------------
# Tests: bfs_reachable
# ---------------------------------------------------------------------------

class TestBfsReachable:
    def test_depth_0(self):
        G = _make_graph()
        reachable = bfs_reachable(G, ["fs_clusters"], max_depth=0)
        assert reachable == {"fs_clusters": 0}

    def test_depth_1(self):
        G = _make_graph()
        reachable = bfs_reachable(G, ["fs_clusters"], max_depth=1)
        assert "fs_clusters" in reachable
        assert "fs_proto" in reachable
        assert "fs_db" in reachable
        assert "fs_main" in reachable  # incoming edge
        assert "fs_subnets" in reachable

    def test_depth_2_crosses_repo(self):
        G = _make_graph()
        reachable = bfs_reachable(G, ["fs_clusters"], max_depth=2)
        assert "op_ctrl" in reachable  # 2 hops: clusters -> proto -> op_ctrl

    def test_depth_3(self):
        G = _make_graph()
        reachable = bfs_reachable(G, ["fs_clusters"], max_depth=3)
        assert "op_api" in reachable  # 3 hops: clusters -> proto -> op_ctrl -> op_api

    def test_multiple_seeds(self):
        G = _make_graph()
        reachable = bfs_reachable(G, ["fs_clusters", "fs_lint"], max_depth=1)
        assert "fs_clusters" in reachable
        assert "fs_lint" in reachable


# ---------------------------------------------------------------------------
# Tests: match_patterns
# ---------------------------------------------------------------------------

class TestMatchPatterns:
    def test_basic_match(self):
        assert match_patterns(["internal/servers/foo.go"], ["internal/**"]) == 1

    def test_no_match(self):
        assert match_patterns(["dev/lint.py"], ["internal/**"]) == 0

    def test_multiple_files(self):
        files = ["internal/a.go", "internal/b.go", "dev/c.py"]
        assert match_patterns(files, ["internal/**"]) == 2

    def test_multiple_patterns(self):
        files = ["cmd/main.go"]
        assert match_patterns(files, ["internal/**", "cmd/**"]) == 1


# ---------------------------------------------------------------------------
# Tests: load_test_jobs
# ---------------------------------------------------------------------------

class TestLoadTestJobs:
    def test_load_yaml(self, tmp_path):
        yaml_file = tmp_path / "test-jobs.yaml"
        yaml_file.write_text(TEST_JOBS_YAML)
        jobs = load_test_jobs(yaml_file)
        assert "run-unit-tests" in jobs
        assert "run-integration-tests-helm" in jobs
        assert "check-generated-code" in jobs
        assert "check-python-code" in jobs

    def test_missing_file(self, tmp_path):
        jobs = load_test_jobs(tmp_path / "nonexistent.yaml")
        assert jobs == {}


# ---------------------------------------------------------------------------
# Tests: ci_select (integration)
# ---------------------------------------------------------------------------

class TestCiSelect:
    def test_go_change_selects_unit_tests(self, tmp_path):
        G = _make_graph()
        graph_path = tmp_path / "graph.json"
        _save_graph(G, graph_path)
        jobs_path = tmp_path / "test-jobs.yaml"
        jobs_path.write_text(TEST_JOBS_YAML)

        plan = ci_select(
            graph_path=graph_path,
            changed_files=["internal/servers/clusters_server.go"],
            repo="service-a",
            test_jobs_path=jobs_path,
        )
        assert "run-unit-tests" in plan.must_run or "run-unit-tests" in plan.should_run
        assert plan.confidence >= 0.5

    def test_python_change_skips_go_tests(self, tmp_path):
        G = _make_graph()
        graph_path = tmp_path / "graph.json"
        _save_graph(G, graph_path)
        jobs_path = tmp_path / "test-jobs.yaml"
        jobs_path.write_text(TEST_JOBS_YAML)

        plan = ci_select(
            graph_path=graph_path,
            changed_files=["dev/lint.py"],
            repo="service-a",
            test_jobs_path=jobs_path,
        )
        assert "check-python-code" in plan.must_run or "check-python-code" in plan.should_run
        assert "run-unit-tests" in plan.skip

    def test_unknown_file_low_confidence(self, tmp_path):
        G = _make_graph()
        graph_path = tmp_path / "graph.json"
        _save_graph(G, graph_path)
        jobs_path = tmp_path / "test-jobs.yaml"
        jobs_path.write_text(TEST_JOBS_YAML)

        plan = ci_select(
            graph_path=graph_path,
            changed_files=["totally_unknown_file.xyz"],
            repo="service-a",
            test_jobs_path=jobs_path,
        )
        assert plan.confidence == 0.0
        assert len(plan.warnings) > 0

    def test_cross_repo_detection(self, tmp_path):
        G = _make_graph()
        graph_path = tmp_path / "graph.json"
        _save_graph(G, graph_path)

        plan = ci_select(
            graph_path=graph_path,
            changed_files=["internal/servers/clusters_server.go"],
            repo="service-a",
        )
        cross_repos = [cr["repo"] for cr in plan.cross_repo]
        assert "service-b-operator" in cross_repos

    def test_no_files_changed(self, tmp_path):
        G = _make_graph()
        graph_path = tmp_path / "graph.json"
        _save_graph(G, graph_path)

        plan = ci_select(
            graph_path=graph_path,
            changed_files=[],
            repo="service-a",
        )
        assert plan.confidence == 1.0
        assert plan.reasoning == "No files changed."

    def test_no_test_jobs_mapping(self, tmp_path):
        G = _make_graph()
        graph_path = tmp_path / "graph.json"
        _save_graph(G, graph_path)

        plan = ci_select(
            graph_path=graph_path,
            changed_files=["internal/servers/clusters_server.go"],
            repo="service-a",
        )
        # Without test-jobs.yaml, must_run/should_run/skip are empty
        assert plan.must_run == []
        assert plan.should_run == []
        assert plan.skip == []
        assert "No test-jobs.yaml mapping found" in plan.reasoning


# ---------------------------------------------------------------------------
# Tests: TestPlan
# ---------------------------------------------------------------------------

class TestTestPlan:
    def test_to_dict(self):
        plan = TestPlan(
            must_run=["unit-tests"],
            should_run=["integration-helm"],
            skip=["integration-kustomize"],
            cross_repo=[{"repo": "service-b-operator", "tests": ["check-generated-code"]}],
            reasoning="Test reasoning",
            confidence=0.85,
        )
        d = plan.to_dict()
        assert d["test_plan"]["must_run"] == ["unit-tests"]
        assert d["confidence"] == 0.85
        assert d["test_plan"]["cross_repo"][0]["repo"] == "service-b-operator"


# ---------------------------------------------------------------------------
# Tests: cli_main
# ---------------------------------------------------------------------------

class TestCliMain:
    def test_missing_repo_exits(self):
        with pytest.raises(SystemExit) as exc_info:
            cli_main(["--files", "foo.go"])
        assert exc_info.value.code == 1

    def test_no_input_exits(self, tmp_path):
        with patch("sys.stdin") as mock_stdin:
            mock_stdin.isatty.return_value = True
            with pytest.raises(SystemExit) as exc_info:
                cli_main(["--repo", "test-repo"])
            assert exc_info.value.code == 1


# ---------------------------------------------------------------------------
# Tests: Bug fixes
# ---------------------------------------------------------------------------

class TestBugFixes:
    """Tests for specific bug fixes from PR review."""

    def test_subdirectory_not_misclassified_as_cross_repo(self, tmp_path):
        """Regression: same-repo subdirectories should not be treated as cross-repo.

        Bug was: internal/servers/file.go was misclassified as cross-repo to "internal"
        because the code checked `"/" not in potential_repo`, which was always true.
        """
        # Graph with files WITHOUT repo prefix (edge case)
        G = nx.DiGraph()
        G.add_node("n1", source_file="internal/servers/clusters.go", label="clusters.go")
        G.add_node("n2", source_file="cmd/main.go", label="main.go")
        G.add_edge("n2", "n1")

        graph_path = tmp_path / "graph.json"
        _save_graph(G, graph_path)

        plan = ci_select(
            graph_path=graph_path,
            changed_files=["cmd/main.go"],
            repo="my-service",
            max_depth=1
        )

        # Should NOT detect "internal" or "cmd" as cross-repo
        cross_repo_names = [cr["repo"] for cr in plan.cross_repo]
        assert "internal" not in cross_repo_names
        assert "cmd" not in cross_repo_names

    def test_full_suite_fallback_schedules_all_jobs(self, tmp_path):
        """Regression: when no files match graph, should schedule ALL jobs as fallback.

        Bug was: fallback path returned empty must_run list despite claiming
        "Falling back to full test suite."
        """
        # Minimal graph
        G = nx.DiGraph()
        G.add_node("n1", source_file="existing_file.go", label="existing")

        graph_path = tmp_path / "graph.json"
        _save_graph(G, graph_path)

        # Test jobs
        jobs_yaml = textwrap.dedent("""\
            my-repo:
              jobs:
                unit-tests:
                  graph_patterns: ["**/*.go"]
                integration-tests:
                  graph_patterns: ["**/*.go"]
        """)
        jobs_file = tmp_path / "test-jobs.yaml"
        jobs_file.write_text(jobs_yaml)

        plan = ci_select(
            graph_path=graph_path,
            changed_files=["unknown_file.xyz"],
            repo="my-repo",
            test_jobs_path=jobs_file
        )

        # Should schedule ALL jobs when falling back
        assert plan.confidence == 0.0
        assert "Falling back to full test suite" in plan.reasoning
        assert len(plan.must_run) == 2
        assert "unit-tests" in plan.must_run
        assert "integration-tests" in plan.must_run

    def test_yaml_parser_preserves_list_values(self, tmp_path):
        """Regression: fallback YAML parser should preserve list values.

        Bug was: when encountering a key with list children like:
            graph_patterns:
              - "foo/**"
              - "bar/**"
        The parser created an empty dict for graph_patterns, then failed to
        append list items because the dict had no keys.
        """
        yaml_text = textwrap.dedent("""\
            service-a:
              jobs:
                run-unit-tests:
                  graph_patterns:
                    - "internal/**"
                    - "cmd/**"
                  description: "Unit tests"
        """)

        yaml_file = tmp_path / "test-jobs.yaml"
        yaml_file.write_text(yaml_text)

        # Load using the function that internally uses _parse_simple_yaml when pyyaml unavailable
        jobs = load_test_jobs(yaml_file)

        # Should have parsed the list correctly
        assert "run-unit-tests" in jobs
        patterns = jobs["run-unit-tests"]["graph_patterns"]
        assert isinstance(patterns, list)
        assert len(patterns) == 2
        assert "internal/**" in patterns
        assert "cmd/**" in patterns
