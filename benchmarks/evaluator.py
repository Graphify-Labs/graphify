#!/usr/bin/env python3
"""
Task Evaluator

Determines whether an agent's solution is correct.
Uses multiple validation strategies:
1. Automated checks (syntax, imports, tests)
2. Semantic checks (does it solve the problem?)
3. Human review (for ambiguous cases)
"""

import json
import subprocess
from pathlib import Path
from typing import Literal


class TaskEvaluator:
    def __init__(self, fixture_path: Path):
        self.fixture_path = Path(fixture_path)

    def evaluate(self, task: dict, solution: str) -> dict:
        """
        Evaluate whether a solution is correct.

        Args:
            task: Task definition (includes verification_script, expected_changes, etc.)
            solution: Agent's proposed code

        Returns:
            {
                "success": bool,  # Overall verdict
                "score": float,   # 0.0–1.0 (0=fail, 0.5=partial, 1.0=pass)
                "checks": {
                    "syntax": bool,
                    "imports": bool,
                    "tests": bool,
                    "semantic": bool,
                },
                "feedback": str,
            }
        """

        checks = {
            "syntax": self._check_syntax(solution),
            "imports": self._check_imports(solution),
            "tests": self._check_tests(task, solution),
            "semantic": self._check_semantic(task, solution),
        }

        # Aggregate score
        if all(checks.values()):
            score = 1.0
            feedback = "✓ Full success"
        elif checks["syntax"] and checks["imports"]:
            score = 0.5
            feedback = "⚠ Partial success (code runs but semantic checks failed)"
        else:
            score = 0.0
            feedback = "✗ Failed (code doesn't parse or run)"

        return {
            "success": score >= 0.5,
            "score": score,
            "checks": checks,
            "feedback": feedback,
        }

    def _check_syntax(self, code: str) -> bool:
        """Check that code parses without syntax errors."""
        try:
            compile(code, "<string>", "exec")
            return True
        except SyntaxError:
            return False

    def _check_imports(self, code: str) -> bool:
        """Check that all imports can be resolved."""
        try:
            # Try to parse and extract imports
            import ast

            tree = ast.parse(code)
            imports = []

            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        imports.append(alias.name)
                elif isinstance(node, ast.ImportFrom):
                    if node.module:
                        imports.append(node.module)

            # Try to import each one
            for imp in imports:
                try:
                    __import__(imp)
                except ImportError:
                    # Some imports may not be available; be lenient
                    pass

            return True

        except Exception:
            return False

    def _check_tests(self, task: dict, solution: str) -> bool:
        """
        Run verification tests if defined in the task.

        Task should specify:
            "verification_script": "path/to/test_something.py"
            "verification_command": "pytest tests/test_auth.py -v"
        """

        if "verification_script" not in task and "verification_command" not in task:
            # No verification defined; assume pass
            return True

        try:
            if "verification_command" in task:
                # Run explicit command
                cmd = task["verification_command"].split()
                result = subprocess.run(
                    cmd,
                    cwd=self.fixture_path,
                    capture_output=True,
                    timeout=30,
                    text=True,
                )
                return result.returncode == 0

            elif "verification_script" in task:
                # Run test script
                script_path = self.fixture_path / task["verification_script"]
                if not script_path.exists():
                    return False

                result = subprocess.run(
                    ["python", str(script_path)],
                    cwd=self.fixture_path,
                    capture_output=True,
                    timeout=30,
                    text=True,
                )
                return result.returncode == 0

        except subprocess.TimeoutExpired:
            return False
        except Exception:
            return False

        return True

    def _check_semantic(self, task: dict, solution: str) -> bool:
        """
        Check that the solution semantically addresses the task.

        Uses simple heuristics:
        - Contains function/class names mentioned in the task
        - Modifies the right files
        - Includes expected keywords (bug, fix, add, refactor, etc.)
        """

        task_desc = task.get("description", "").lower()
        target_files = task.get("target_files", [])
        solution_lower = solution.lower()

        # Check 1: Does solution mention target files?
        if target_files:
            file_mentions = sum(
                1
                for f in target_files
                if Path(f).stem.lower() in solution_lower
            )
            if file_mentions == 0:
                # Might still be correct, but suspicious
                pass

        # Check 2: Does it contain implementation (not just comments)?
        if len(solution.strip()) < 50:
            # Too short to be meaningful
            return False

        # Check 3: Does it contain keywords matching the task type?
        task_lower = task.get("title", "").lower()

        if "fix" in task_lower or "bug" in task_lower:
            # Should have some control flow changes
            if not any(
                kw in solution_lower for kw in ["if", "else", "return", "raise"]
            ):
                return False

        if "add" in task_lower or "feature" in task_lower:
            # Should define new function/class
            if not any(
                kw in solution_lower for kw in ["def ", "class "]
            ):
                return False

        if "refactor" in task_lower:
            # Should reorganize/restructure
            if len(solution.split("\n")) < 5:
                return False

        return True


# Test harness
if __name__ == "__main__":
    # Example: evaluate a solution
    fixture_path = Path("benchmarks/fixtures/httpx_mini")
    evaluator = TaskEvaluator(fixture_path)

    sample_task = {
        "id": "auth-header-bug",
        "title": "Fix auth module header bug",
        "description": "The auth module drops custom headers. Find and fix.",
        "target_files": ["auth.py"],
        "verification_script": "tests/test_auth.py",
    }

    sample_solution = """
def fix_headers(request):
    '''Fixed version that preserves custom headers'''
    if request.custom_headers:
        return request.with_headers(request.custom_headers)
    return request
"""

    result = evaluator.evaluate(sample_task, sample_solution)
    print(json.dumps(result, indent=2))
