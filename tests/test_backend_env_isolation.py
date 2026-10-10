"""Backend-detection tests must not depend on the developer's shell (#3481).

`detect_backend()` reads a dozen environment variables. The autouse fixture in
conftest.py clears all of them; these tests keep that list complete and prove
the fixture makes the detection tests immune to ambient keys.
"""
import inspect
import os
import re
import subprocess
import sys
from pathlib import Path

from graphify import llm

ROOT = Path(__file__).resolve().parent.parent


def test_env_list_covers_every_variable_detect_backend_reads():
    source = inspect.getsource(llm.detect_backend) + inspect.getsource(llm._resolve_ollama_base_url)
    direct = set(re.findall(r'os\.environ\.get\("([A-Z_]+)"', source))
    builtin_keys = {key for name in llm.BACKENDS for key in llm._backend_env_keys(name)}
    listed = set(llm.backend_detection_env_vars())
    assert direct <= listed, sorted(direct - listed)
    assert builtin_keys <= listed, sorted(builtin_keys - listed)
    # The regression trigger from the report and the two Azure halves are in there.
    assert {"GOOGLE_API_KEY", "GEMINI_API_KEY", "AZURE_OPENAI_ENDPOINT", "OLLAMA_HOST"} <= listed


def test_autouse_fixture_clears_the_backend_environment():
    for key in llm.backend_detection_env_vars():
        assert key not in os.environ, key
    assert llm.detect_backend() is None


def test_detection_tests_pass_with_every_backend_variable_exported():
    """The report's repro: run the detection tests with ambient keys set."""
    env = {**os.environ, **{key: "ambient-dummy" for key in llm.backend_detection_env_vars()}}
    env["AZURE_OPENAI_ENDPOINT"] = "https://example.openai.azure.com"
    env["OLLAMA_BASE_URL"] = "http://localhost:11434/v1"
    env["OLLAMA_HOST"] = "http://localhost:11434"
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
         "tests/test_ollama.py", "tests/test_provider_registry.py", "tests/test_llm_backends.py",
         "-k", "detect_backend"],
        cwd=ROOT, env=env, capture_output=True, text=True, timeout=600,
    )
    assert result.returncode == 0, result.stdout[-3000:] + result.stderr[-1000:]
