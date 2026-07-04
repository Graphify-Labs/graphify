#!/usr/bin/env python3
"""
Graphify Benchmark Runner

Executes paired comparative trials:
- Baseline: Agent solves task WITHOUT Graphify
- Treatment: Agent solves SAME task WITH Graphify graph

Measures: success rate, tokens, turns, time, confidence.
"""

import argparse
import asyncio
import json
import os
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

# Stub for now—will integrate with anthropic/openai SDK
# when runner is actually invoked
class LLMClient:
    def __init__(self, backend: str, model: str):
        self.backend = backend
        self.model = model
        self.api_key = os.getenv(f"{backend.upper()}_API_KEY")
        if not self.api_key:
            print(f"Warning: {backend.upper()}_API_KEY not set")

    async def solve_task(
        self, task: dict, context: str, include_graph: bool = False
    ) -> dict:
        """
        Invoke LLM to solve a task.
        
        Args:
            task: Task definition (description, files, etc.)
            context: Code context from repository
            include_graph: Whether to include Graphify graph in prompt
        
        Returns:
            {
                "success": bool,
                "solution": str,
                "reasoning": str,
                "tokens": int,
                "turns": int,
                "time": float,
                "confidence": float,
                "model": str,
            }
        """
        # This is a stub. Real implementation would:
        # 1. Build prompt from task + context + optional graph
        # 2. Call LLM API (anthropic.Anthropic, openai.OpenAI, etc.)
        # 3. Parse response
        # 4. Extract tokens from response metadata
        # 5. Optionally call evaluator.py to validate solution
        
        return {
            "success": True,
            "solution": "# Stub solution",
            "reasoning": "LLM reasoning would go here",
            "tokens": 5000,
            "turns": 3,
            "time": 12.5,
            "confidence": 0.85,
            "model": self.model,
        }


@dataclass
class TaskResult:
    """Result of running a single task."""

    task_id: str
    task_title: str
    fixture: str
    condition: str  # "baseline" or "treatment"
    success: bool
    tokens: int
    turns: int
    time_seconds: float
    confidence: float
    solution: str
    reasoning: str
    model: str
    timestamp: str

    def to_dict(self) -> dict:
        return asdict(self)


class BenchmarkRunner:
    def __init__(
        self,
        backend: str = "claude",
        model: str = None,
        fixtures: list = None,
        tasks: list = None,
        runs_per_task: int = 1,
        output_dir: Path = None,
    ):
        self.backend = backend
        self.model = model or f"{backend}-default"
        self.fixtures = fixtures or ["all"]
        self.task_categories = tasks or ["all"]
        self.runs_per_task = runs_per_task
        self.output_dir = Path(output_dir or "benchmarks/results")
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.client = LLMClient(backend, self.model)
        self.results = []

    def load_fixtures(self) -> dict:
        """Load fixture metadata."""
        fixtures_dir = Path("benchmarks/fixtures")
        fixtures = {}

        if "all" in self.fixtures:
            self.fixtures = [d.name for d in fixtures_dir.iterdir() if d.is_dir()]

        for fixture_name in self.fixtures:
            fixture_path = fixtures_dir / fixture_name
            metadata_file = fixture_path / "metadata.json"

            if not metadata_file.exists():
                print(f"Warning: No metadata for fixture {fixture_name}")
                continue

            with open(metadata_file) as f:
                fixtures[fixture_name] = json.load(f)
                fixtures[fixture_name]["path"] = str(fixture_path)

        return fixtures

    def load_tasks(self) -> dict:
        """Load task definitions by category."""
        tasks_dir = Path("benchmarks/tasks")
        all_tasks = {}

        if "all" in self.task_categories:
            categories = [f.stem for f in tasks_dir.glob("*.json")]
        else:
            categories = self.task_categories

        for category in categories:
            task_file = tasks_dir / f"{category}.json"
            if not task_file.exists():
                print(f"Warning: No task file for category {category}")
                continue

            with open(task_file) as f:
                all_tasks[category] = json.load(f)

        return all_tasks

    async def run_single_task(
        self, task: dict, fixture: dict, include_graph: bool
    ) -> TaskResult:
        """Run a single task with or without graph."""
        # Load code context from fixture
        code_context = self._load_code_context(fixture, task.get("target_files", []))

        condition = "treatment" if include_graph else "baseline"

        # Load graph if treatment
        graph_context = ""
        if include_graph:
            graph_path = Path(fixture["path"]) / "graphify-out" / "GRAPH_REPORT.md"
            if graph_path.exists():
                with open(graph_path) as f:
                    graph_context = f.read()

        # Call LLM
        result = await self.client.solve_task(
            task, code_context, include_graph=include_graph
        )

        # Record result
        task_result = TaskResult(
            task_id=task.get("id", "unknown"),
            task_title=task.get("title", "unknown"),
            fixture=fixture.get("name", "unknown"),
            condition=condition,
            success=result["success"],
            tokens=result["tokens"],
            turns=result["turns"],
            time_seconds=result["time"],
            confidence=result["confidence"],
            solution=result["solution"],
            reasoning=result["reasoning"],
            model=result["model"],
            timestamp=datetime.utcnow().isoformat(),
        )

        return task_result

    def _load_code_context(self, fixture: dict, target_files: list) -> str:
        """Load code files from fixture."""
        context = ""
        fixture_path = Path(fixture["path"])

        # If specific files requested, load those; otherwise load all .py files
        if target_files:
            files_to_load = target_files
        else:
            files_to_load = list(fixture_path.glob("src/**/*.py")) + list(
                fixture_path.glob("*.py")
            )

        for file_path in files_to_load:
            if file_path.exists():
                try:
                    with open(file_path) as f:
                        content = f.read()
                        context += f"\n\n# File: {file_path.relative_to(fixture_path)}\n"
                        context += content
                except Exception as e:
                    print(f"Error reading {file_path}: {e}")

        return context

    async def run_all(self) -> list:
        """Execute all benchmark runs."""
        fixtures = self.load_fixtures()
        tasks_by_category = self.load_tasks()

        if not fixtures:
            print("Error: No fixtures found")
            return []

        if not tasks_by_category:
            print("Error: No tasks found")
            return []

        all_tasks = []
        for category, tasks in tasks_by_category.items():
            all_tasks.extend(tasks)

        print(
            f"Starting benchmark: {len(all_tasks)} tasks × 2 conditions × {self.runs_per_task} runs"
        )
        print(f"Fixtures: {', '.join(fixtures.keys())}")
        print(f"Backend: {self.backend} / {self.model}")
        print()

        run_count = 0
        for fixture_name, fixture_metadata in fixtures.items():
            print(f"📁 Fixture: {fixture_name}")

            for task in all_tasks:
                print(f"  📋 Task: {task.get('title', 'unknown')}")

                for run in range(self.runs_per_task):
                    for include_graph in [False, True]:
                        condition = "WITH" if include_graph else "WITHOUT"
                        print(f"    Run {run + 1}/{self.runs_per_task} {condition} graph...")

                        start = time.time()
                        result = await self.run_single_task(
                            task, fixture_metadata, include_graph
                        )
                        elapsed = time.time() - start

                        self.results.append(result)
                        run_count += 1

                        status = "✓" if result.success else "✗"
                        print(
                            f"      {status} Success={result.success} "
                            f"Tokens={result.tokens} Turns={result.turns} "
                            f"Time={elapsed:.1f}s"
                        )

        print(f"\n✅ Completed {run_count} runs")
        return self.results

    def save_results(self):
        """Save raw results and generate summary."""
        # Raw results
        raw_file = self.output_dir / "raw" / f"{datetime.utcnow().isoformat()}.json"
        raw_file.parent.mkdir(parents=True, exist_ok=True)

        with open(raw_file, "w") as f:
            json.dump([r.to_dict() for r in self.results], f, indent=2)

        print(f"\n📊 Saved raw results: {raw_file}")

        # Aggregated summary
        self._save_aggregated()

        # Human-readable report
        self._save_report()

    def _save_aggregated(self):
        """Compute and save summary statistics."""
        if not self.results:
            return

        # Group by fixture and condition
        summary = {}

        for result in self.results:
            key = f"{result.fixture}:{result.condition}"

            if key not in summary:
                summary[key] = {
                    "fixture": result.fixture,
                    "condition": result.condition,
                    "success_count": 0,
                    "total_count": 0,
                    "tokens": [],
                    "turns": [],
                    "times": [],
                    "confidences": [],
                }

            summary[key]["total_count"] += 1
            if result.success:
                summary[key]["success_count"] += 1

            summary[key]["tokens"].append(result.tokens)
            summary[key]["turns"].append(result.turns)
            summary[key]["times"].append(result.time_seconds)
            summary[key]["confidences"].append(result.confidence)

        # Compute statistics
        aggregated = {}
        for key, group in summary.items():
            aggregated[key] = {
                "fixture": group["fixture"],
                "condition": group["condition"],
                "success_rate": group["success_count"] / group["total_count"],
                "tokens": {
                    "mean": sum(group["tokens"]) / len(group["tokens"]),
                    "min": min(group["tokens"]),
                    "max": max(group["tokens"]),
                },
                "turns": {
                    "mean": sum(group["turns"]) / len(group["turns"]),
                    "min": min(group["turns"]),
                    "max": max(group["turns"]),
                },
                "time": {
                    "mean": sum(group["times"]) / len(group["times"]),
                    "total": sum(group["times"]),
                },
                "confidence": {
                    "mean": sum(group["confidences"]) / len(group["confidences"]),
                },
            }

        agg_file = self.output_dir / "aggregated.json"
        with open(agg_file, "w") as f:
            json.dump(aggregated, f, indent=2)

        print(f"📈 Saved aggregated results: {agg_file}")

    def _save_report(self):
        """Generate a human-readable markdown report."""
        if not self.results:
            return

        report = f"""# Graphify Benchmark Report

**Generated**: {datetime.utcnow().isoformat()}
**Backend**: {self.backend} / {self.model}
**Total Runs**: {len(self.results)}

## Summary

| Metric | Without Graphify | With Graphify | Improvement |
|--------|------------------|---------------|-------------|
| Success Rate | TBD | TBD | TBD |
| Avg Tokens | TBD | TBD | TBD |
| Avg Turns | TBD | TBD | TBD |

## Results by Fixture

"""

        # Group results by fixture
        by_fixture = {}
        for result in self.results:
            if result.fixture not in by_fixture:
                by_fixture[result.fixture] = {"baseline": [], "treatment": []}
            by_fixture[result.fixture][result.condition].append(result)

        for fixture_name, conditions in by_fixture.items():
            report += f"### {fixture_name}\n\n"

            baseline = conditions.get("baseline", [])
            treatment = conditions.get("treatment", [])

            if baseline:
                baseline_success = sum(1 for r in baseline if r.success) / len(
                    baseline
                )
                baseline_tokens = sum(r.tokens for r in baseline) / len(baseline)
                baseline_turns = sum(r.turns for r in baseline) / len(baseline)
                report += f"**Without Graphify**\n"
                report += f"- Success Rate: {baseline_success:.0%}\n"
                report += f"- Avg Tokens: {baseline_tokens:.0f}\n"
                report += f"- Avg Turns: {baseline_turns:.1f}\n\n"

            if treatment:
                treatment_success = sum(1 for r in treatment if r.success) / len(
                    treatment
                )
                treatment_tokens = sum(r.tokens for r in treatment) / len(treatment)
                treatment_turns = sum(r.turns for r in treatment) / len(treatment)
                report += f"**With Graphify**\n"
                report += f"- Success Rate: {treatment_success:.0%}\n"
                report += f"- Avg Tokens: {treatment_tokens:.0f}\n"
                report += f"- Avg Turns: {treatment_turns:.1f}\n\n"

                if baseline:
                    success_delta = treatment_success - baseline_success
                    token_delta = (baseline_tokens - treatment_tokens) / baseline_tokens
                    turn_delta = (baseline_turns - treatment_turns) / baseline_turns

                    report += f"**Delta**\n"
                    report += f"- Success: {success_delta:+.0%}\n"
                    report += f"- Tokens: {token_delta:+.0%}\n"
                    report += f"- Turns: {turn_delta:+.0%}\n\n"

        report_file = self.output_dir / "report.md"
        with open(report_file, "w") as f:
            f.write(report)

        print(f"📝 Saved report: {report_file}")


async def main():
    parser = argparse.ArgumentParser(
        description="Run Graphify benchmarks with paired comparative trials."
    )
    parser.add_argument(
        "--backend",
        default="claude",
        choices=["claude", "openai", "gemini"],
        help="LLM backend to use",
    )
    parser.add_argument(
        "--model",
        default=None,
        help="Specific model to use (e.g., claude-opus-4-6)",
    )
    parser.add_argument(
        "--fixtures",
        nargs="+",
        default=["all"],
        help="Fixture(s) to run (or 'all')",
    )
    parser.add_argument(
        "--tasks",
        nargs="+",
        default=["all"],
        help="Task categories to run (or 'all')",
    )
    parser.add_argument(
        "--runs",
        type=int,
        default=1,
        help="Number of runs per task",
    )
    parser.add_argument(
        "--output",
        default="benchmarks/results",
        help="Output directory",
    )

    args = parser.parse_args()

    runner = BenchmarkRunner(
        backend=args.backend,
        model=args.model,
        fixtures=args.fixtures,
        tasks=args.tasks,
        runs_per_task=args.runs,
        output_dir=args.output,
    )

    results = await runner.run_all()
    runner.save_results()

    if results:
        print("\n✅ Benchmarks complete!")
    else:
        print("\n❌ No results collected")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
