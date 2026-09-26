from __future__ import annotations

import os
from pathlib import Path
import pytest

import graphify.extract as ex

def test_generic_logging_extraction(tmp_path, monkeypatch):
    # Change working directory to tmp_path so the extractor looks for logging_config.yaml there
    monkeypatch.chdir(tmp_path)
    
    # Write logging_config.yaml
    config_content = """
logging_rules:
  java:
    query: |
      (method_invocation
        object: (identifier) @log_obj (#match? @log_obj "{pattern}")
        name: (identifier) @log_level
        arguments: (argument_list) @args
      )
    pattern: "(?i)^(log|logger|timber)$"
  kotlin:
    query: |
      (call_expression
        (navigation_expression
          (identifier) @log_obj (#match? @log_obj "{pattern}")
          (identifier) @log_level
        )
        (value_arguments) @args
      )
    pattern: "(?i)^(log|logger|timber)$"
  c:
    query: |
      (call_expression
        function: (identifier) @log_obj (#match? @log_obj "{pattern}")
        arguments: (argument_list) @args
      )
    pattern: "(?i)^(log_.*)$"
  cpp:
    query: |
      (call_expression
        function: (identifier) @log_obj (#match? @log_obj "{pattern}")
        arguments: (argument_list) @args
      )
    pattern: "(?i)^(log_.*)$"
"""
    (tmp_path / "logging_config.yaml").write_text(config_content)
    
    # Create test source files
    java_file = tmp_path / "Test.java"
    java_file.write_text("""
class Test {
    void doSomething() {
        logger.info("Java log message");
    }
}
""")
    
    kotlin_file = tmp_path / "Test.kt"
    kotlin_file.write_text("""
fun doKotlin() {
    logger.warn("Kotlin log message")
}
""")
    
    c_file = tmp_path / "test.c"
    c_file.write_text("""
void doC() {
    log_info("C log message");
}
""")
    
    cpp_file = tmp_path / "test.cpp"
    cpp_file.write_text("""
void doCpp() {
    LOG_WARN("Cpp log message");
}
""")

    # First run without any flag/env-var. It should be disabled by default.
    from graphify.generic_logger import GenericLogExtractor
    monkeypatch.setattr(ex, "log_extractor", GenericLogExtractor("logging_config.yaml"))
    
    files = [java_file, kotlin_file, c_file, cpp_file]
    result_disabled = ex.extract(files, cache_root=tmp_path / "cache_disabled", parallel=False)
    
    edges_disabled = result_disabled.get("edges", [])
    prints_log_edges_disabled = [e for e in edges_disabled if e.get("relation") == "PRINTS_LOG"]
    assert len(prints_log_edges_disabled) == 0, "Logging extraction should be disabled by default"
    
    # Now enable it via environment variable
    monkeypatch.setenv("GRAPHIFY_EXTRACT_LOGS", "1")
    # Reset internal loaded state to simulate fresh run
    ex.log_extractor._loaded = False
    
    result = ex.extract(files, cache_root=tmp_path / "cache_enabled", parallel=False)
    
    edges = result.get("edges", [])
    nodes = result.get("nodes", [])
    
    # Assert nodes exist
    log_nodes = [n for n in nodes if n.get("type") == "log"]
    assert len(log_nodes) >= 4
    
    # Assert edges exist
    prints_log_edges = [e for e in edges if e.get("relation") == "PRINTS_LOG"]
    assert len(prints_log_edges) == 4
    
    # Assert details of java log edge
    java_edge = next(e for e in prints_log_edges if e.get("metadata", {}).get("lang") == "java")
    assert java_edge["source"].endswith("_dosomething")
    assert java_edge["target"] == 'logger.info("Java log message")'
    
    # Assert details of kotlin log edge
    kotlin_edge = next(e for e in prints_log_edges if e.get("metadata", {}).get("lang") == "kotlin")
    assert kotlin_edge["source"].endswith("_dokotlin")
    assert kotlin_edge["target"] == 'logger.warn("Kotlin log message")'
    
    # Assert details of c log edge
    c_edge = next(e for e in prints_log_edges if e.get("metadata", {}).get("lang") == "c")
    assert c_edge["source"].endswith("_doc")
    assert c_edge["target"] == 'log_info("C log message")'
    
    # Assert details of cpp log edge
    cpp_edge = next(e for e in prints_log_edges if e.get("metadata", {}).get("lang") == "cpp")
    assert cpp_edge["source"].endswith("_docpp")
    assert cpp_edge["target"] == 'LOG_WARN("Cpp log message")'

def test_generic_logging_fallback_resolution(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    config_content = """
logging_rules:
  c:
    query: |
      (call_expression
        function: (identifier) @log_obj (#match? @log_obj "{pattern}")
        arguments: (argument_list) @args
      )
    pattern: "(?i)^(log_.*)$"
"""
    (tmp_path / "logging_config.yaml").write_text(config_content)
    
    # C file with log inside non-standard / macro or top-level structure
    c_file = tmp_path / "toplevel.c"
    c_file.write_text("""
void top_log_test(void) {
    log_debug("Top level debug log");
}
""")
    
    monkeypatch.setenv("GRAPHIFY_EXTRACT_LOGS", "1")
    from graphify.generic_logger import GenericLogExtractor
    monkeypatch.setattr(ex, "log_extractor", GenericLogExtractor("logging_config.yaml"))
    ex.log_extractor._loaded = False
    
    result = ex.extract([c_file], cache_root=tmp_path / "cache_fallback", parallel=False)
    edges = [e for e in result.get("edges", []) if e.get("relation") == "PRINTS_LOG"]
    assert len(edges) == 1
    assert edges[0]["source"].endswith("_top_log_test")
    assert edges[0]["target"] == 'log_debug("Top level debug log")'


def test_generic_logging_cache_invalidation_and_consistency(tmp_path, monkeypatch):
    """Test that toggling logging on/off does not leak stale cache entries or bypass extraction."""
    monkeypatch.chdir(tmp_path)
    config_file = tmp_path / "logging_config.yaml"
    config_file.write_text("""
logging_rules:
  c:
    query: |
      (call_expression
        function: (identifier) @log_obj (#match? @log_obj "{pattern}")
        arguments: (argument_list) @args
      )
    pattern: "(?i)^(log_.*)$"
""")

    c_file = tmp_path / "service.c"
    c_file.write_text("""
void handle_request(void) {
    log_info("Handling service request");
}
""")

    shared_cache = tmp_path / "shared_cache"
    from graphify.generic_logger import GenericLogExtractor

    # Run 1: Logging disabled. Must produce 0 log edges in the shared cache.
    monkeypatch.delenv("GRAPHIFY_EXTRACT_LOGS", raising=False)
    monkeypatch.setattr(ex, "log_extractor", GenericLogExtractor(str(config_file)))
    ex.log_extractor._loaded = False

    r1 = ex.extract([c_file], cache_root=shared_cache, parallel=False)
    edges1 = [e for e in r1.get("edges", []) if e.get("relation") == "PRINTS_LOG"]
    assert len(edges1) == 0

    # Run 2: Logging enabled. Must NOT be bypassed by Run 1's cache hit.
    monkeypatch.setenv("GRAPHIFY_EXTRACT_LOGS", "1")
    monkeypatch.setattr(ex, "log_extractor", GenericLogExtractor(str(config_file)))
    ex.log_extractor._loaded = False

    r2 = ex.extract([c_file], cache_root=shared_cache, parallel=False)
    edges2 = [e for e in r2.get("edges", []) if e.get("relation") == "PRINTS_LOG"]
    assert len(edges2) == 1
    assert edges2[0]["target"] == 'log_info("Handling service request")'

    # Run 3: Logging disabled again. Must NOT serve Run 2's cached log edges.
    monkeypatch.delenv("GRAPHIFY_EXTRACT_LOGS", raising=False)
    monkeypatch.setattr(ex, "log_extractor", GenericLogExtractor(str(config_file)))
    ex.log_extractor._loaded = False

    r3 = ex.extract([c_file], cache_root=shared_cache, parallel=False)
    edges3 = [e for e in r3.get("edges", []) if e.get("relation") == "PRINTS_LOG"]
    assert len(edges3) == 0

    # Run 4: Logging enabled, cache hit from Run 2 should be preserved.
    monkeypatch.setenv("GRAPHIFY_EXTRACT_LOGS", "1")
    monkeypatch.setattr(ex, "log_extractor", GenericLogExtractor(str(config_file)))
    ex.log_extractor._loaded = False

    r4 = ex.extract([c_file], cache_root=shared_cache, parallel=False)
    edges4 = [e for e in r4.get("edges", []) if e.get("relation") == "PRINTS_LOG"]
    assert len(edges4) == 1


def test_generic_logging_precise_function_name_resolution(tmp_path, monkeypatch):
    """Test that function names are accurately identified and not confused with return types or annotations."""
    monkeypatch.chdir(tmp_path)
    config_file = tmp_path / "logging_config.yaml"
    config_file.write_text("""
logging_rules:
  c:
    query: |
      (call_expression
        function: (identifier) @log_obj (#match? @log_obj "{pattern}")
        arguments: (argument_list) @args
      )
    pattern: "(?i)^(log_.*)$"
  java:
    query: |
      (method_invocation
        object: (identifier) @log_obj (#match? @log_obj "{pattern}")
        name: (identifier) @log_level
        arguments: (argument_list) @args
      )
    pattern: "(?i)^(logger)$"
""")

    # C source where return type is an identifier (size_t)
    c_file = tmp_path / "buffer.c"
    c_file.write_text("""
static size_t calculate_buffer_size(int count) {
    log_debug("Calculating buffer");
    return (size_t)count * 1024;
}
""")

    # Java source with annotation and generic return type
    java_file = tmp_path / "Worker.java"
    java_file.write_text("""
class Worker {
    @Override
    public <T> CustomResponse processTask(T task) {
        logger.info("Executing task");
        return null;
    }
}
""")

    monkeypatch.setenv("GRAPHIFY_EXTRACT_LOGS", "1")
    from graphify.generic_logger import GenericLogExtractor
    monkeypatch.setattr(ex, "log_extractor", GenericLogExtractor(str(config_file)))
    ex.log_extractor._loaded = False

    result = ex.extract([c_file, java_file], cache_root=tmp_path / "cache_precise", parallel=False)
    edges = [e for e in result.get("edges", []) if e.get("relation") == "PRINTS_LOG"]

    # C edge source must end with _calculate_buffer_size (NOT _size_t)
    c_edge = next(e for e in edges if e.get("metadata", {}).get("lang") == "c")
    assert c_edge["source"].endswith("_calculate_buffer_size")
    assert not c_edge["source"].endswith("_size_t")

    # Java edge source must end with _processtask (NOT _override or _customresponse)
    java_edge = next(e for e in edges if e.get("metadata", {}).get("lang") == "java")
    assert java_edge["source"].endswith("_processtask")
    assert not java_edge["source"].endswith("_override")
    assert not java_edge["source"].endswith("_customresponse")


def test_cli_logging_flags_dispatch(monkeypatch, tmp_path):
    """Test CLI dispatch handling for --enable-logging and --logging-config options."""
    import sys
    from graphify.cli import dispatch_command

    cfg = tmp_path / "custom_logging.yaml"
    cfg.write_text("logging_rules: {}")

    monkeypatch.delenv("GRAPHIFY_EXTRACT_LOGS", raising=False)
    monkeypatch.delenv("GRAPHIFY_LOGGING_CONFIG", raising=False)

    # Test 'update' dispatch with --enable-logging and --logging-config
    monkeypatch.setattr(sys, "argv", ["graphify", "update", "--enable-logging", f"--logging-config={cfg}", str(tmp_path)])
    
    called = {}
    def mock_rebuild(*args, **kwargs):
        called["rebuild"] = True
        return True

    import graphify.watch
    monkeypatch.setattr(graphify.watch, "_rebuild_code", mock_rebuild)
    try:
        dispatch_command("update")
        assert os.environ.get("GRAPHIFY_EXTRACT_LOGS") == "1"
        assert os.environ.get("GRAPHIFY_LOGGING_CONFIG") == str(cfg)
        assert called.get("rebuild") is True
    finally:
        os.environ.pop("GRAPHIFY_EXTRACT_LOGS", None)
        os.environ.pop("GRAPHIFY_LOGGING_CONFIG", None)


def test_generic_logging_malformed_yaml_resilience(tmp_path, monkeypatch):
    """Test that malformed or non-dictionary YAML configs are handled defensively without exceptions."""
    from graphify.generic_logger import GenericLogExtractor

    monkeypatch.setenv("GRAPHIFY_EXTRACT_LOGS", "1")

    # Case 1: YAML root is a list
    list_cfg = tmp_path / "list_config.yaml"
    list_cfg.write_text("- item1\n- item2\n")
    extractor1 = GenericLogExtractor(str(list_cfg))
    assert extractor1.is_enabled() is False
    assert extractor1.config == {}

    # Case 2: YAML root is a scalar
    scalar_cfg = tmp_path / "scalar_config.yaml"
    scalar_cfg.write_text("just_a_string")
    extractor2 = GenericLogExtractor(str(scalar_cfg))
    assert extractor2.is_enabled() is False
    assert extractor2.config == {}

    # Case 3: logging_rules is a list instead of a dict
    invalid_rules_cfg = tmp_path / "invalid_rules.yaml"
    invalid_rules_cfg.write_text("logging_rules:\n  - rule1\n  - rule2\n")
    extractor3 = GenericLogExtractor(str(invalid_rules_cfg))
    assert extractor3.is_enabled() is False
    assert extractor3.config == {}


def test_generic_logging_no_cache_poison_on_injection_failure(tmp_path, monkeypatch):
    """Test that if log injection fails, the partial result is not cached, enabling rerun self-healing."""
    monkeypatch.chdir(tmp_path)
    config_file = tmp_path / "logging_config.yaml"
    config_file.write_text("""
logging_rules:
  c:
    query: |
      (call_expression
        function: (identifier) @log_obj (#match? @log_obj "{pattern}")
        arguments: (argument_list) @args
      )
    pattern: "(?i)^(log_.*)$"
""")

    c_file = tmp_path / "test.c"
    c_file.write_text("""
void do_work(void) {
    log_info("Work done");
}
""")

    shared_cache = tmp_path / "test_cache"
    from graphify.generic_logger import GenericLogExtractor

    monkeypatch.setenv("GRAPHIFY_EXTRACT_LOGS", "1")
    extractor = GenericLogExtractor(str(config_file))
    monkeypatch.setattr(ex, "log_extractor", extractor)

    # Force inject_logs_to_graph to fail on first run
    def failing_inject(*args, **kwargs):
        raise RuntimeError("Simulated transient Tree-sitter or injection error")

    monkeypatch.setattr(extractor, "inject_logs_to_graph", failing_inject)

    # Run 1: Extraction succeeds overall, but log injection fails
    r1 = ex.extract([c_file], cache_root=shared_cache, parallel=False)
    assert "error" not in r1
    edges1 = [e for e in r1.get("edges", []) if e.get("relation") == "PRINTS_LOG"]
    assert len(edges1) == 0

    # Verify that the cache under cache_kind does not have this file cached
    from graphify.cache import load_cached
    cache_kind = extractor.get_cache_kind()
    cached_entry = load_cached(c_file, root=tmp_path, kind=cache_kind, cache_root=shared_cache)
    assert cached_entry is None, "Cache should NOT be populated after failed log injection"

    # Run 2: Self-healing rerun with fixed/working injection
    monkeypatch.undo()
    monkeypatch.setenv("GRAPHIFY_EXTRACT_LOGS", "1")
    extractor2 = GenericLogExtractor(str(config_file))
    monkeypatch.setattr(ex, "log_extractor", extractor2)

    r2 = ex.extract([c_file], cache_root=shared_cache, parallel=False)
    edges2 = [e for e in r2.get("edges", []) if e.get("relation") == "PRINTS_LOG"]
    assert len(edges2) == 1
    assert edges2[0]["target"] == 'log_info("Work done")'


def test_generic_logging_thread_safe_reload(tmp_path, monkeypatch):
    """Test concurrent access to _ensure_loaded during config path transitions."""
    import concurrent.futures
    from graphify.generic_logger import GenericLogExtractor

    cfg1 = tmp_path / "cfg1.yaml"
    cfg1.write_text("logging_rules:\n  c: {pattern: 'log_.*', query: 'foo'}\n")
    cfg2 = tmp_path / "cfg2.yaml"
    cfg2.write_text("logging_rules:\n  java: {pattern: 'logger', query: 'bar'}\n")

    monkeypatch.setenv("GRAPHIFY_EXTRACT_LOGS", "1")
    monkeypatch.setenv("GRAPHIFY_LOGGING_CONFIG", str(cfg1))

    extractor = GenericLogExtractor()
    extractor._ensure_loaded()
    assert "c" in extractor.config

    # Transition config in background while multiple threads call _ensure_loaded
    monkeypatch.setenv("GRAPHIFY_LOGGING_CONFIG", str(cfg2))

    errors = []
    def worker():
        try:
            for _ in range(50):
                extractor._ensure_loaded()
                cfg = extractor.config
                path = extractor._current_config_path
                # Ensure configuration matches path atomically
                if path == str(cfg1):
                    assert "c" in cfg
                elif path == str(cfg2):
                    assert "java" in cfg
        except Exception as e:
            errors.append(e)

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        futures = [pool.submit(worker) for _ in range(8)]
        concurrent.futures.wait(futures)

    assert errors == []


def test_cache_dir_ast_with_prompt_fp(tmp_path):
    """Test that cache_dir honors prompt_fp even when kind is prefixed with ast-."""
    from graphify.cache import cache_dir

    d_with_prompt = cache_dir(root=tmp_path, kind="ast-logging-12345678", prompt_fp="prompt123")
    assert "pprompt123" in str(d_with_prompt)

    d_without_prompt = cache_dir(root=tmp_path, kind="ast-logging-12345678", prompt_fp=None)
    assert "pprompt123" not in str(d_without_prompt)
    assert "v0." in str(d_without_prompt)


def test_generic_logging_internal_exception_prevents_cache_poison(tmp_path, monkeypatch):
    """Adversarial Test: Ensure real internal exceptions caught inside inject_logs_to_graph still prevent cache poisoning."""
    monkeypatch.chdir(tmp_path)
    # Config with an invalid tree-sitter query to trigger an actual tree-sitter QueryError inside inject_logs_to_graph
    config_file = tmp_path / "logging_config.yaml"
    config_file.write_text("""
logging_rules:
  c:
    query: "(invalid_syntax_node_xyz @bad_capture)"
    pattern: ".*"
""")

    c_file = tmp_path / "service.c"
    c_file.write_text("void run() { log_info(\"test\"); }")

    shared_cache = tmp_path / "adversarial_cache"
    from graphify.generic_logger import GenericLogExtractor

    monkeypatch.setenv("GRAPHIFY_EXTRACT_LOGS", "1")
    extractor = GenericLogExtractor(str(config_file))
    monkeypatch.setattr(ex, "log_extractor", extractor)

    # Run extraction: should catch QueryError internally, print warning, but NOT save corrupted result to cache
    res = ex.extract([c_file], cache_root=shared_cache, parallel=False)
    assert "error" not in res

    from graphify.cache import load_cached
    cache_kind = extractor.get_cache_kind()
    cached = load_cached(c_file, root=tmp_path, kind=cache_kind, cache_root=shared_cache)
    assert cached is None, "Cache MUST NOT be populated when inject_logs_to_graph fails internally"


def test_generic_logging_uppercase_and_cpp_extensions(tmp_path, monkeypatch):
    """Adversarial Test: Verify uppercase extensions (.C, .CPP, .Java) and C++ variants (.cxx) are supported."""
    monkeypatch.chdir(tmp_path)
    config_file = tmp_path / "logging_config.yaml"
    config_file.write_text("""
logging_rules:
  cpp:
    query: |
      (call_expression
        function: (identifier) @log_obj (#match? @log_obj "{pattern}")
        arguments: (argument_list) @args
      )
    pattern: "(?i)^(LOG_.*)$"
""")

    cpp_file = tmp_path / "worker.CPP"
    cpp_file.write_text("void execute() { LOG_DEBUG(\"CPP log\"); }")

    cxx_file = tmp_path / "module.cxx"
    cxx_file.write_text("void run() { LOG_DEBUG(\"CXX log\"); }")

    from graphify.generic_logger import GenericLogExtractor
    monkeypatch.setenv("GRAPHIFY_EXTRACT_LOGS", "1")
    extractor = GenericLogExtractor(str(config_file))
    monkeypatch.setattr(ex, "log_extractor", extractor)

    res = ex.extract([cpp_file, cxx_file], cache_root=tmp_path / "cache_ext", parallel=False)
    edges = [e for e in res.get("edges", []) if e.get("relation") == "PRINTS_LOG"]
    assert len(edges) == 2


def test_generic_logging_query_with_literal_braces(tmp_path, monkeypatch):
    """Adversarial Test: Verify tree-sitter queries with regex quantifiers {2,4} don't crash with KeyError."""
    monkeypatch.chdir(tmp_path)
    config_file = tmp_path / "logging_config.yaml"
    config_file.write_text("""
logging_rules:
  c:
    query: |
      (call_expression
        function: (identifier) @log_obj (#match? @log_obj "^[a-z]{3}_.*$")
        arguments: (argument_list) @args
      )
    pattern: "unused_pattern"
""")

    c_file = tmp_path / "test.c"
    c_file.write_text("void foo() { log_msg(\"hello\"); }")

    from graphify.generic_logger import GenericLogExtractor
    monkeypatch.setenv("GRAPHIFY_EXTRACT_LOGS", "1")
    extractor = GenericLogExtractor(str(config_file))
    monkeypatch.setattr(ex, "log_extractor", extractor)

    # Should not raise KeyError from .format()
    res = ex.extract([c_file], cache_root=tmp_path / "cache_braces", parallel=False)
    edges = [e for e in res.get("edges", []) if e.get("relation") == "PRINTS_LOG"]
    assert len(edges) == 1
    assert edges[0]["target"] == 'log_msg("hello")'


def test_generic_logging_no_dangling_edges_on_fallback(tmp_path, monkeypatch):
    """Adversarial Test: Verify that all PRINTS_LOG edge sources and targets exist in result nodes."""
    monkeypatch.chdir(tmp_path)
    config_file = tmp_path / "logging_config.yaml"
    config_file.write_text("""
logging_rules:
  c:
    query: |
      (call_expression
        function: (identifier) @log_obj (#match? @log_obj "{pattern}")
        arguments: (argument_list) @args
      )
    pattern: "(?i)^(log_.*)$"
""")

    c_file = tmp_path / "orphan.c"
    c_file.write_text("void test_fn() { log_info(\"log without matching node\"); }")

    from graphify.generic_logger import GenericLogExtractor
    monkeypatch.setenv("GRAPHIFY_EXTRACT_LOGS", "1")
    extractor = GenericLogExtractor(str(config_file))
    monkeypatch.setattr(ex, "log_extractor", extractor)

    res = ex.extract([c_file], cache_root=tmp_path / "cache_dangling", parallel=False)
    node_ids = {n["id"] for n in res.get("nodes", [])}
    for e in res.get("edges", []):
        assert e["source"] in node_ids, f"Dangling edge source detected: {e['source']}"
        assert e["target"] in node_ids, f"Dangling edge target detected: {e['target']}"




